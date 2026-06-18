import psycopg2
import os
def spawn():
    conn = psycopg2.connect(os.environ['DATABASE_PUBLIC_URL'])
    db = conn.cursor()
    # get user Dede
    db.execute("SELECT id FROM users WHERE username='Dede'")
    res = db.fetchone()
    if not res:
        print("User Dede not found!")
        return
    uid = res[0]
    
    # 1. ensure user has a province
    db.execute("SELECT id FROM provinces WHERE userId=%s", (uid,))
    provinces = db.fetchall()
    if not provinces:
        db.execute("INSERT INTO provinces (userId, provinceName, pop_children) VALUES (%s, 'Dede Capital', 500000) RETURNING id", (uid,))
        pId = db.fetchone()[0]
    else:
        pId = provinces[0][0]
    
    # 2. insert buildings in user_buildings (user_id, province_id, building_id, quantity)
    db.execute("SELECT id, name FROM building_dictionary")
    b_dict = {row[1]: row[0] for row in db.fetchall()}
    
    for bname in ['farm', 'mine', 'factory', 'oil_well', 'steel_mill']:
        if bname in b_dict:
            bid = b_dict[bname]
            # using postgres upsert
            db.execute("""
                INSERT INTO user_buildings (user_id, province_id, building_id, quantity) 
                VALUES (%s, %s, %s, %s) 
                ON CONFLICT (user_id, province_id, building_id) 
                DO UPDATE SET quantity = EXCLUDED.quantity
            """, (uid, pId, bid, 50))
    
    # 3. set user_economy values
    db.execute("SELECT id, name FROM resource_dictionary")
    r_dict = {row[1]: row[0] for row in db.fetchall()}
    
    resources_to_give = [
        ('gold', 1000000), 
        ('food', 500000), 
        ('materials', 500000), 
        ('oil', 100000), 
        ('steel', 100000), 
        ('consumer_goods', 100000)
    ]
    for rname, ramount in resources_to_give:
        if rname in r_dict:
            rid = r_dict[rname]
            db.execute("""
                INSERT INTO user_economy (user_id, resource_id, amount) 
                VALUES (%s, %s, %s) 
                ON CONFLICT (user_id, resource_id) 
                DO UPDATE SET amount = EXCLUDED.amount
            """, (uid, rid, ramount))
            
    # 4. population
    db.execute("UPDATE provinces SET pop_children=500000, pop_teens=500000, pop_adults=1000000, pop_seniors=200000 WHERE id=%s", (pId,))
    conn.commit()
    print(f"Successfully spawned economy for user 'Dede' in province {pId}.")
    
if __name__ == '__main__':
    spawn()
