import os, sys, json
os.chdir("/Users/dede/AnO-Reborn")
sys.path.append("/Users/dede/AnO-Reborn")
from database import reuse_or_new_cursor
from psycopg2.extras import RealDictCursor

with reuse_or_new_cursor(cursor_factory=RealDictCursor) as db:
    db.execute("SELECT name FROM building_dictionary")
    print([r['name'] for r in db.fetchall()])
