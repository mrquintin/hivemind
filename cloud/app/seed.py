"""Idempotent database seeder for default users."""
from __future__ import annotations

import logging
import os

from sqlalchemy import Engine
from sqlalchemy.orm import sessionmaker

from app.models.user import User
from app.security import hash_password

logger = logging.getLogger("hivemind.cloud")

_DEFAULT_USERS = [
    {
        "username": "admin",
        "password_env": "DEFAULT_ADMIN_PASSWORD",
        "password_fallback": "hivemind-admin-2024",
        "role": "operator",
    },
    {
        "username": "client",
        "password_env": "DEFAULT_CLIENT_PASSWORD",
        "password_fallback": "hivemind-client-2024",
        "role": "client",
    },
]


def seed_default_users(engine: Engine) -> None:
    """Create default users if the users table is empty. Idempotent."""
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        count = session.query(User).count()
        if count > 0:
            return

        for u in _DEFAULT_USERS:
            password = os.environ.get(u["password_env"], u["password_fallback"])
            user = User(
                username=u["username"],
                password_hash=hash_password(password),
                role=u["role"],
            )
            session.add(user)

        session.commit()
        logger.info("Seeded %d default users.", len(_DEFAULT_USERS))
    except Exception:
        session.rollback()
        logger.exception("Failed to seed default users.")
    finally:
        session.close()
