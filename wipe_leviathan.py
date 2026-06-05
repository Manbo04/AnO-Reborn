import os
import psycopg2
from psycopg2.extras import RealDictCursor

def wipe_leviathan():
    conn = psycopg2.connect(os.getenv("DATABASE_URL"), cursor_factory=RealDictCursor)
    cur = conn.cursor()
    
    # Get colid for Leviathan
    cur.execute("SELECT id FROM colNames WHERE name ILIKE '%leviathan%'")
    row = cur.fetchone()
    if not row:
        print("Leviathan not found")
        return
    colid = row['id']
    
    # Get member IDs
    cur.execute("SELECT u.id FROM coalitions_legacy c JOIN users u ON c.userid = u.id WHERE c.colid = %s", (colid,))
    member_ids = [r['id'] for r in cur.fetchall()]
    
    if member_ids:
        # Wipe their gold
        cur.execute("UPDATE stats SET gold = 100000 WHERE id = ANY(%s)", (member_ids,))
        print(f"Wiped gold for {len(member_ids)} members")
        
        # Wipe their resources
        cur.execute("UPDATE user_economy SET quantity = 0 WHERE user_id = ANY(%s)", (member_ids,))
        print(f"Wiped resources for {len(member_ids)} members")
    
    # Wipe coalition bank
    cur.execute("""
        UPDATE colBanks SET 
        money=0, iron=0, coal=0, lumber=0, bauxite=0, oil=0, uranium=0, 
        lead=0, copper=0, rations=0, steel=0, aluminium=0, gasoline=0, 
        ammunition=0, consumer_goods=0, components=0 
        WHERE colId = %s
    """, (colid,))
    print("Wiped Leviathan coalition bank")
    
    conn.commit()
    cur.close()
    conn.close()

if __name__ == "__main__":
    wipe_leviathan()
