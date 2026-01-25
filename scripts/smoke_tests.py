from app import app
from urllib.parse import urlencode

print("Starting smoke tests...")

def check_countries():
    with app.test_client() as c:
        resp = c.get('/countries?'+urlencode({'sort':'population','sortway':'asc','search':'testsearch'}))
        data = resp.get_data(as_text=True)
        print('countries GET status:', resp.status_code)
        print('population selected present:', 'value="population"' in data and 'selected' in data.split('value="population"')[1][:50])
        print('sortway asc selected present:', 'value="asc"' in data and 'selected' in data.split('value="asc"')[1][:50])
        print('search value present:', 'value="testsearch"' in data)

def check_coalitions():
    with app.test_client() as c:
        resp = c.get('/coalitions?'+urlencode({'sort':'open','sortway':'asc','search':'coaltest'}))
        data = resp.get_data(as_text=True)
        print('\ncoalitions GET status:', resp.status_code)
        print('open selected present:', 'value="open"' in data and 'selected' in data.split('value="open"')[1][:50])
        print('sortway asc selected present:', 'value="asc"' in data and 'selected' in data.split('value="asc"')[1][:50])
        print('coalitions search value present:', 'value="coaltest"' in data)

def check_login():
    with app.test_client() as c:
        resp = c.post('/login', data={})
        print('\nlogin missing fields status:', resp.status_code)
        resp = c.post('/login', data={'username':'nosuch','password':'pw'})
        print('login bad creds status:', resp.status_code)

def check_password_reset():
    with app.test_client() as c:
        resp = c.post('/request_password_reset', data={'email':'noone@example.com'})
        print('\nrequest_password_reset nonexistent email status:', resp.status_code, 'location:', resp.headers.get('Location'))
        resp = c.post('/reset_password/invalidcode', data={'password':'newpass123'})
        print('reset_password invalid code status:', resp.status_code)

def check_countries_post():
    with app.test_client() as c:
        resp = c.post('/countries', data={'search':'abc'})
        print('\ncountries POST status:', resp.status_code)

if __name__ == '__main__':
    check_countries()
    check_coalitions()
    check_login()
    check_password_reset()
    check_countries_post()
    print('\nSmoke tests completed')
