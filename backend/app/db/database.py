from collections.abc import Generator

from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings


class DatabaseConnectionError(RuntimeError):
    pass


engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def check_database_connection() -> int:
    try:
        with engine.connect() as connection:
            return int(connection.execute(text("SELECT 1")).scalar_one())
    except SQLAlchemyError as exc:
        raise DatabaseConnectionError("PostgreSQL connection failed") from exc
