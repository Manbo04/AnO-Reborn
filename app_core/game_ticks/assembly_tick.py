from database import get_db_connection
from datetime import datetime

def run_assembly_tick():
    """
    Checks for expired Assembly proposals, resolves them, applies effects,
    and also cleans up expired sanctions.
    """
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            # 1. Resolve open proposals whose closes_at has passed
            cur.execute('''
                SELECT id, type, proposer_id, target_nation_id, target_currency_id, currency_cap_amount, text
                FROM assembly_proposals
                WHERE status = 'open' AND closes_at <= NOW()
            ''')
            proposals = cur.fetchall()
            
            for prop in proposals:
                prop_id, p_type, proposer, target_nation, target_curr, cap_amount, p_text = prop
                
                # Fetch votes for this proposal
                cur.execute('''
                    SELECT 
                        COALESCE(SUM(CASE WHEN vote = 'for' THEN weight ELSE 0 END), 0) as for_w,
                        COALESCE(SUM(CASE WHEN vote = 'against' THEN weight ELSE 0 END), 0) as against_w,
                        COUNT(voter_id) as turnout
                    FROM assembly_votes WHERE proposal_id = %s
                ''', (prop_id,))
                vote_res = cur.fetchone()
                
                for_w = vote_res[0] if vote_res and vote_res[0] else 0
                against_w = vote_res[1] if vote_res and vote_res[1] else 0
                turnout = vote_res[2] if vote_res and vote_res[2] else 0
                
                total_w = for_w + against_w
                
                # Condition: >50% For AND >= 5 turnout
                passed = False
                if turnout >= 5 and total_w > 0 and (for_w / total_w) > 0.5:
                    passed = True
                    
                new_status = 'passed' if passed else 'failed'
                
                # Update status
                cur.execute("UPDATE assembly_proposals SET status = %s WHERE id = %s", (new_status, prop_id))
                
                if passed:
                    # Apply effects based on type
                    if p_type == 'sanction':
                        # Default 14 days
                        cur.execute('''
                            INSERT INTO assembly_effects (proposal_id, target_nation_id, effect_type, active, expires_at)
                            VALUES (%s, %s, 'sanction', TRUE, NOW() + INTERVAL '14 days')
                        ''', (prop_id, target_nation))
                    elif p_type == 'condemn':
                        # Small influence penalty on target
                        cur.execute("UPDATE users SET influence = GREATEST(0, influence - 10) WHERE id = %s", (target_nation,))
                    elif p_type == 'lift_sanction':
                        cur.execute("UPDATE assembly_effects SET active = FALSE, expires_at = NOW() WHERE target_nation_id = %s AND effect_type = 'sanction' AND active = TRUE", (target_nation,))
                    elif p_type == 'currency_cap':
                        cur.execute('''
                            INSERT INTO assembly_effects (proposal_id, target_currency_id, effect_type, active, expires_at)
                            VALUES (%s, %s, 'currency_cap', TRUE, NOW() + INTERVAL '14 days')
                        ''', (prop_id, target_curr))
                        
                    # Also write to news or world_affairs (if such table exists for global news)
                    # using global chat or just user notifications
                    # Let's insert a news item for the target if they exist
                    if target_nation:
                        msg = f"A World Assembly proposal targeting your nation has PASSED. Type: {p_type}."
                        cur.execute("INSERT INTO news (userId, title, message) VALUES (%s, 'Assembly Proposal Passed', %s)", (target_nation, msg))
                
            # 2. Expire old sanctions
            cur.execute('''
                UPDATE assembly_effects 
                SET active = FALSE 
                WHERE active = TRUE AND expires_at <= NOW()
            ''')
            
        conn.commit()

