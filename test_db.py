import os
import sys
sys.path.insert(0, '/app')
from database import get_db_cursor
with get_db_cursor(read_only=True) as db:
    db.execute('SELECT * FROM offers LIMIT 5;')
    print('Offers:', db.fetchall())
    db.execute('SELECT * FROM trades LIMIT 5;')
    print('Trades:', db.fetchall())

