"""SQLAlchemy 2.0 + PyMySQL data access.

The LLM NEVER touches this layer. All product reads are deterministic Python.
"""
import os
from functools import lru_cache
from typing import List

from sqlalchemy import (
    Boolean,
    DECIMAL,
    Integer,
    String,
    Text,
    create_engine,
    select,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker


def _database_url() -> str:
    user = os.getenv("MYSQL_USER", "root")
    password = os.getenv("MYSQL_PASSWORD", "rootpass")
    host = os.getenv("MYSQL_HOST", "localhost")
    port = os.getenv("MYSQL_PORT", "3306")
    db = os.getenv("MYSQL_DB", "ordering")
    return f"mysql+pymysql://{user}:{password}@{host}:{port}/{db}?charset=utf8mb4"


@lru_cache(maxsize=1)
def get_engine():
    # pool_pre_ping keeps long-lived connections healthy against MySQL timeouts.
    return create_engine(_database_url(), pool_pre_ping=True, future=True)


@lru_cache(maxsize=1)
def get_sessionmaker():
    return sessionmaker(bind=get_engine(), class_=Session, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class Product(Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    price: Mapped[float] = mapped_column(DECIMAL(10, 2), default=0)
    category: Mapped[str] = mapped_column(String(100), default="")
    is_available: Mapped[bool] = mapped_column(Boolean, default=True)


def init_db() -> None:
    """Create tables if they do not exist (used by the seed script)."""
    Base.metadata.create_all(get_engine())


def fetch_available_products() -> List[Product]:
    """Return all in-stock products. Matching happens in Python over this list."""
    with get_sessionmaker()() as session:
        rows = session.scalars(
            select(Product).where(Product.is_available.is_(True))
        ).all()
        return list(rows)


def check_mysql() -> bool:
    """Lightweight reachability probe for /health."""
    try:
        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
