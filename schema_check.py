import psycopg2

def main():
    try:
        conn = psycopg2.connect("postgresql://localhost")
        cur = conn.cursor()
        
        print("=== TABLES ===")
        cur.execute("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public'
        """)
        tables = [row[0] for row in cur.fetchall()]
        for table in tables:
            print(table)
            
        print("\n=== FOREIGN KEYS WITHOUT INDEXES ===")
        # Query to find foreign keys without corresponding indexes
        cur.execute("""
            WITH fk_actions AS (
                SELECT
                    conrelid::regclass AS table_name,
                    conname AS fk_name,
                    a.attname AS column_name
                FROM
                    pg_constraint c
                JOIN pg_attribute a ON a.attnum = ANY(c.conkey) AND a.attrelid = c.conrelid
                WHERE
                    contype = 'f'
            ),
            index_columns AS (
                SELECT
                    indrelid::regclass AS table_name,
                    a.attname AS column_name
                FROM
                    pg_index i
                JOIN pg_attribute a ON a.attnum = ANY(i.indkey) AND a.attrelid = i.indrelid
            )
            SELECT f.table_name, f.fk_name, f.column_name
            FROM fk_actions f
            LEFT JOIN index_columns i ON f.table_name = i.table_name AND f.column_name = i.column_name
            WHERE i.column_name IS NULL;
        """)
        missing_indexes = cur.fetchall()
        for row in missing_indexes:
            print(row)
            
        print("\n=== DUPLICATE TABLES OR BLOAT ===")
        # Basic check for sizes or duplicate names
        cur.execute("""
            SELECT relname, pg_size_pretty(pg_total_relation_size(C.oid)) AS "total_size"
            FROM pg_class C
            LEFT JOIN pg_namespace N ON (N.oid = C.relnamespace)
            WHERE nspname NOT IN ('pg_catalog', 'information_schema')
              AND C.relkind <> 'i'
              AND nspname !~ '^pg_toast'
            ORDER BY pg_total_relation_size(C.oid) DESC
            LIMIT 20;
        """)
        for row in cur.fetchall():
            print(row)
            
    except Exception as e:
        print(f"Error: {e}")

if __name__ == '__main__':
    main()
