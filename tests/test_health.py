import requests
from init import BASE_URL


def test_health_endpoint():
    r = requests.get(f"{BASE_URL}/health")
    assert r.status_code == 200
    assert r.text == "ok"
