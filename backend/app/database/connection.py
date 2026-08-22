from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config.settings import settings


import os

db_url = settings.database_url

# Auto-fix internal Render hostnames when running in local dev outside Render
if "dpg-" in db_url and ".render.com" not in db_url and not os.getenv("RENDER"):
    # Replace internal host dpg-xxx with external domain dpg-xxx.oregon-postgres.render.com
    import re
    db_url = re.sub(r"@(dpg-[^/:\?]+)", r"@\1.oregon-postgres.render.com", db_url)

connect_args = {}
if "render.com" in db_url:
    connect_args = {
        "sslmode": "require",
        "connect_timeout": 10,
    }

engine = create_engine(
    db_url,
    pool_pre_ping=True,
    pool_recycle=30,
    pool_size=5,
    max_overflow=10,
    connect_args=connect_args,
)




SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)


def get_db():
    db = SessionLocal()

    try:
        yield db
    finally:
        db.close()