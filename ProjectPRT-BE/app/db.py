from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.core.settings import settings
from app.models import Base

# pool_pre_ping/pool_recycle guard against dropped/stale connections causing OperationalError
engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
    pool_recycle=300,
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# This is typically used by Alembic
def init_db():
    Base.metadata.create_all(bind=engine)
