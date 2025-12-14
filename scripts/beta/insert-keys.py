import os

import openpyxl
import psycopg2
from dotenv import load_dotenv

load_dotenv()

conn = psycopg2.connect(
    database=os.getenv("PG_DATABASE"),
    user=os.getenv("PG_USER"),
    password=os.getenv("PG_PASSWORD"),
    host=os.getenv("PG_HOST"),
    port=os.getenv("PG_PORT"),
)

db = conn.cursor()

path = "./ano_betatesters.xlsx"
wb = openpyxl.load_workbook(path)
ws = wb["Sheet1"]
idx = 1
for cell in ws["D"]:  # key
    key = cell.value
    if key is not None and key != "Key":
        # I know this is a very bad practice, but for 88 rows
        # the performance impact is negligible.
        # Fix: switch to a single multi-row INSERT if more keys are required.
        db.execute("INSERT INTO keys (key) VALUES (%s)", (key,))
        print(f"{idx}. Inserted key - {key}")
        idx += 1

conn.commit()
conn.close()
