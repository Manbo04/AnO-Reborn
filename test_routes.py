import os
import sys
from flask import Flask
from werkzeug.test import EnvironBuilder

# We need to run inside the Flask app context
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
import os
os.environ["DATABASE_URL"] = "postgresql://postgres@localhost:5432/railway"
from app import app
app.config['TESTING'] = True

def test_routes():
    with app.test_request_context():
        # Mock session
        from flask import session
        session['user_id'] = 8

        print("Testing /account...")
        try:
            with app.test_client() as client:
                with client.session_transaction() as sess:
                    sess['user_id'] = 8
                response = client.get('/account')
                print("/account status:", response.status_code)
                if response.status_code == 500:
                    print("Error on /account")
        except Exception as e:
            print("Exception on /account:", e)

        print("Testing /treaties...")
        try:
            with app.test_client() as client:
                with client.session_transaction() as sess:
                    sess['user_id'] = 8
                response = client.get('/treaties')
                print("/treaties status:", response.status_code)
                if response.status_code == 500:
                    print("Error on /treaties")
        except Exception as e:
            print("Exception on /treaties:", e)

        print("Testing /countries...")
        try:
            with app.test_client() as client:
                with client.session_transaction() as sess:
                    sess['user_id'] = 8
                response = client.get('/countries')
                print("/countries status:", response.status_code)
                if response.status_code == 500:
                    print("Error on /countries")
        except Exception as e:
            print("Exception on /countries:", e)

if __name__ == '__main__':
    test_routes()
