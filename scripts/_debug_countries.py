from app import app
from tests.test_countries_page import create_test_user, cleanup_user

client = app.test_client()
with client.session_transaction() as sess:
    sess["user_id"] = 1

uids = []
for _ in range(51):
    uid, _ = create_test_user("pagetest", provinces=1)
    uids.append(uid)

resp = client.get("/countries")
print("status", resp.status_code)
html = resp.get_data(as_text=True)
print("contains Page 1 of 2?", "Page 1 of 2" in html)
print("contains sort=population?", "sort=population" in html)
print("count pagetest occurrences", html.count("pagetest"))
print("html length", len(html))
print(html[:4000])

for uid in uids:
    cleanup_user(uid, provinces=1)
