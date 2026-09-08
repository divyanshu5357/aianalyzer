from app.database.connection import SessionLocal
from app.database.schema_init import ensure_all_database_tables

db = SessionLocal()
print("Connecting to DB...")
ensure_all_database_tables(db)
print("Tables ensured!")
db.close()
