import os, sys, traceback
sys.path.insert(0, '/app')
from app import app
from database import get_db_cursor
app.config['TESTING'] = True
errors = []
with app.test_client() as client:
    with get_db_cursor(read_only=True) as db:
        db.execute('SELECT id FROM users LIMIT 20')
        users = [row[0] for row in db.fetchall()]
    for u in users:
        try:
            with client.session_transaction() as sess:
                sess['user_id'] = u
            response = client.get('/my_offers')
            if response.status_code == 500:
                errors.append(f'User {u} got 500')
                if b'Traceback' in response.data or b'Exception' in response.data:
                    errors.append(response.data.decode(errors='ignore'))
        except Exception as e:
            errors.append(f'User {u} crashed: {e}')
print('Tested all users for /my_offers.')
if errors:
    print('Errors found:')
    for err in errors[:5]:
        print(err)
else:
    print('No errors found.')

