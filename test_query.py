import psycopg2.extensions
import psycopg2

def print_query(query, params):
    # This shows what psycopg2 actually sends to the database
    conn = psycopg2.connect("postgres://postgres:postgres@localhost:5432/ano_reborn")
    cur = conn.cursor()
    mogrified = cur.mogrify(query, params)
    print("Mogrified:", mogrified)

# We can't connect, so we mock the connection
class MockCursor:
    def __init__(self):
        pass
    def mogrify(self, query, params):
        return psycopg2.extensions.adapt(params).getquoted()

print("Adapted list:", psycopg2.extensions.adapt([914, 280]).getquoted())
