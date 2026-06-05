from datetime import datetime, timezone
from .repositories import WorldMapRepository

class WorldMapService:
    @staticmethod
    def get_user_coalition(user_id):
        return WorldMapRepository.get_user_coalition(user_id)

    @staticmethod
    def get_all_nodes():
        nodes = WorldMapRepository.get_nodes()
        node_list = []
        for n in nodes:
            node_list.append({
                "id": n[0],
                "name": n[1],
                "type": n[2],
                "x": n[3],
                "y": n[4],
                "controlling_coalition_id": n[5],
                "coalition_name": n[6],
                "health": n[7],
                "shield_expires_at": n[8].isoformat() if n[8] else None,
                "tier": n[9] if len(n) > 9 else 1,
            })
        return node_list

    @staticmethod
    def declare_siege(user_id, node_id):
        user_col = WorldMapRepository.get_user_coalition(user_id)
        if not user_col:
            return {"status": "error", "message": "You must be in a Coalition to attack nodes."}
            
        coalition_id, coalition_name = user_col
        
        stats = WorldMapRepository.get_user_stats_for_update(user_id)
        if not stats:
            return {"status": "error", "message": "User stats not found."}
        money = stats[0]
        
        military = WorldMapRepository.get_user_military_for_update(user_id)
        if not military:
            return {"status": "error", "message": "Military stats not found."}
        soldiers = military[0]
        
        node = WorldMapRepository.get_node_for_update(node_id)
        if not node:
            return {"status": "error", "message": "Node not found."}
            
        node_name, controlling_id, shield_expires_at, tier = node
        
        cost_gold = 5000000 * tier
        cost_soldiers = 50000 * tier
        shield_hours = 4 * tier
        
        if money < cost_gold:
            return {"status": "error", "message": f"You need ${cost_gold:,} to fund a Tier {tier} siege deployment."}
            
        if soldiers < cost_soldiers:
            return {"status": "error", "message": f"You need {cost_soldiers:,} Soldiers to launch a Tier {tier} siege!"}
        
        if controlling_id == coalition_id:
            return {"status": "error", "message": "Your coalition already controls this node!"}
            
        if shield_expires_at:
            if shield_expires_at > datetime.now(timezone.utc):
                return {"status": "error", "message": "This node is currently protected by a shield."}
        
        WorldMapRepository.apply_capture(
            user_id=user_id, 
            node_id=node_id, 
            coalition_id=coalition_id, 
            cost_gold=cost_gold, 
            cost_soldiers=cost_soldiers, 
            shield_hours=shield_hours
        )
        
        return {"status": "success", "message": f"Successfully captured {node_name} for {coalition_name}!"}
