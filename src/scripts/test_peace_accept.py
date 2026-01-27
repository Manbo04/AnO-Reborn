# Temporary test script to reproduce and validate peace acceptance
# Usage: run with the project's venv python to perform an acceptance flow using Flask test_client

from src.app import app
from src.database import get_db_connection

# Use the test client
with app.test_client() as client:
    # Create two test users and a war & peace offer
    from dotenv import load_dotenv

    load_dotenv()

    # Insert two test users (or use existing debug users) and create war and peace offers
    with get_db_connection() as conn:
        db = conn.cursor()
        # Create two users
        db.execute("DELETE FROM users WHERE username LIKE 'testuser_peace%';")
        db.execute(
            "INSERT INTO users (username,email,hash,date,auth_type) VALUES ('testuser_peace_a','a@a.com','hash', '2020-01-01', 'normal')"
        )
        db.execute(
            "INSERT INTO users (username,email,hash,date,auth_type) VALUES ('testuser_peace_b','b@b.com','hash', '2020-01-01', 'normal')"
        )
        db.execute("SELECT id FROM users WHERE username='testuser_peace_a'")
        a_id = db.fetchone()[0]
        db.execute("SELECT id FROM users WHERE username='testuser_peace_b'")
        b_id = db.fetchone()[0]

        # ensure resources for both exist
        db.execute(
            "INSERT INTO resources (id) VALUES (%s) ON CONFLICT (id) DO NOTHING",
            (a_id,),
        )
        db.execute(
            "INSERT INTO resources (id) VALUES (%s) ON CONFLICT (id) DO NOTHING",
            (b_id,),
        )
        db.execute("UPDATE resources SET rations=1000 WHERE id=%s", (b_id,))

        # create a war by using the app route to ensure all necessary columns are set
    # Login as attacker using the test client session
    with client.session_transaction() as sess:
        sess["user_id"] = a_id
    # Declare war from attacker to defender using the application's route
    resp_declare = client.post(
        "/declare_war",
        data={"defender": str(b_id), "warType": "Raze", "description": "Test war"},
        follow_redirects=True,
    )
    # Find the last war id created between these parties
    with get_db_connection() as conn:
        db = conn.cursor()
        db.execute(
            "SELECT id FROM wars WHERE attacker=%s AND defender=%s ORDER BY id DESC LIMIT 1",
            (a_id, b_id),
        )
        war_id = db.fetchone()[0]

        # create a peace offer by attacker demanding resources
        db.execute(
            "INSERT INTO peace (author, demanded_resources, demanded_amount) VALUES (%s, %s, %s)",
            (a_id, "rations", "100"),
        )
        db.execute("SELECT CURRVAL('peace_id_seq')")
        peace_id = db.fetchone()[0]
        db.execute("UPDATE wars SET peace_offer_id=%s WHERE id=%s", (peace_id, war_id))

    # Now log in as defender with test client by setting session
    with client.session_transaction() as sess:
        sess["user_id"] = b_id

    # Now perform the POST to accept offer
    resp = client.post(
        "/peace_offers",
        data={"peace_offer": str(peace_id), "decision": "1"},
        follow_redirects=True,
    )
    print("Post response status:", resp.status_code)
    print(resp.data[:500])

# End of script
