"""
ClaimFlow - Shared SQLAlchemy declarative base.
All model files must import `Base` from here to ensure a single metadata registry.
"""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass
