"""Idempotent database seeder for default users."""
from __future__ import annotations

import logging

from sqlalchemy import Engine
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.models.user import User
from app.security import hash_password

logger = logging.getLogger("hivemind.cloud")


def seed_default_users(engine: Engine) -> None:
    """Create default users if the users table is empty. Idempotent."""
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        count = session.query(User).count()
        if count > 0:
            return

        users_to_create = [
            ("admin", settings.DEFAULT_ADMIN_PASSWORD, "operator"),
            ("client", settings.DEFAULT_CLIENT_PASSWORD, "client"),
        ]

        for username, password, role in users_to_create:
            user = User(
                username=username,
                password_hash=hash_password(password),
                role=role,
            )
            session.add(user)

        session.commit()
        logger.info("Seeded %d default users.", len(users_to_create))
    except Exception:
        session.rollback()
        logger.exception("Failed to seed default users.")
    finally:
        session.close()
