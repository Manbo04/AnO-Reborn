import sys
from app import create_app
app = create_app()
from app import app as application
with application.test_client() as c:
    response = c.get('/country/id=1')
    print(response.status_code)
    if response.status_code == 500:
        print(response.data.decode('utf-8'))
