import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from contextlib import contextmanager

db_dir = "db"
os.makedirs(db_dir, exist_ok=True)

DATABASE_URL = "sqlite:///db/discord-bot.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine)

Base = declarative_base()

@contextmanager
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()