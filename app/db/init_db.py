from app.db.base import Base
from app.db.session import engine
import app.models.job  # noqa: F401 — ensures models are registered


def create_tables() -> None:
    Base.metadata.create_all(bind=engine)
