from __future__ import annotations

import logging
import secrets
from typing import Any

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

from app.config import CONFIG_FILE, USERS_FILE
from app.storage import read_json, write_json

logger = logging.getLogger(__name__)
password_hasher = PasswordHasher()


def is_configured() -> bool:
    config = read_json(CONFIG_FILE, {})
    users = read_json(USERS_FILE, {"users": []})
    return bool(config.get("setup_complete")) and bool(users.get("users"))


def ensure_server_config() -> dict[str, Any]:
    config = read_json(CONFIG_FILE, {})
    changed = False

    if "session_secret" not in config:
        config["session_secret"] = secrets.token_urlsafe(48)
        changed = True

    if "setup_complete" not in config:
        config["setup_complete"] = False
        changed = True

    if changed:
        write_json(CONFIG_FILE, config)

    return config


def get_user(username: str) -> dict[str, Any] | None:
    users = read_json(USERS_FILE, {"users": []}).get("users", [])
    normalized = username.strip().casefold()

    for user in users:
        if str(user.get("username", "")).casefold() == normalized:
            return user

    return None


def create_initial_gm(username: str, password: str) -> dict[str, Any]:
    username = username.strip()

    if not username:
        raise ValueError("Username is required.")

    if len(username) > 64:
        raise ValueError("Username must be 64 characters or fewer.")

    if len(password) < 8:
        raise ValueError("Password must be at least 8 characters.")

    if is_configured():
        raise ValueError("Initial setup has already been completed.")

    user = {
        "username": username,
        "password_hash": password_hasher.hash(password),
        "role": "gm",
        "enabled": True,
    }

    write_json(USERS_FILE, {"users": [user]})

    config = ensure_server_config()
    config["setup_complete"] = True
    write_json(CONFIG_FILE, config)

    logger.info("Initial GM account created for user %s", username)
    return user


def authenticate(username: str, password: str) -> dict[str, Any] | None:
    user = get_user(username)

    if not user or not user.get("enabled", False):
        logger.warning("Login failed for user %s", username)
        return None

    try:
        valid = password_hasher.verify(user["password_hash"], password)
    except (VerifyMismatchError, KeyError):
        valid = False

    if not valid:
        logger.warning("Login failed for user %s", username)
        return None

    if password_hasher.check_needs_rehash(user["password_hash"]):
        _rehash_password(user["username"], password)

    logger.info("Login succeeded for user %s", user["username"])
    return user


def _rehash_password(username: str, password: str) -> None:
    data = read_json(USERS_FILE, {"users": []})

    for user in data.get("users", []):
        if str(user.get("username", "")).casefold() == username.casefold():
            user["password_hash"] = password_hasher.hash(password)
            write_json(USERS_FILE, data)
            return
