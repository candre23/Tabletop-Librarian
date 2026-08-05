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


def list_users() -> list[dict[str, Any]]:
    users = read_json(USERS_FILE, {"users": []}).get("users", [])
    return sorted(users, key=lambda user: str(user.get("username", "")).casefold())


def get_user(username: str) -> dict[str, Any] | None:
    normalized = username.strip().casefold()

    for user in list_users():
        if str(user.get("username", "")).casefold() == normalized:
            return user

    return None


def create_initial_gm(username: str, password: str) -> dict[str, Any]:
    if is_configured():
        raise ValueError("Initial setup has already been completed.")

    user = _build_user(username, password, "gm")
    write_json(USERS_FILE, {"users": [user]})

    config = ensure_server_config()
    config["setup_complete"] = True
    write_json(CONFIG_FILE, config)

    logger.info("Initial GM account created for user %s", user["username"])
    return user


def create_user(username: str, password: str, role: str = "player") -> dict[str, Any]:
    username = username.strip()

    if get_user(username):
        raise ValueError("A user with that name already exists.")

    role = "gm" if role == "gm" else "player"
    user = _build_user(username, password, role)

    data = read_json(USERS_FILE, {"users": []})
    data.setdefault("users", []).append(user)
    write_json(USERS_FILE, data)

    logger.info("User created: %s (%s)", user["username"], user["role"])
    return user


def set_user_enabled(username: str, enabled: bool) -> bool:
    data = read_json(USERS_FILE, {"users": []})
    normalized = username.strip().casefold()

    for user in data.get("users", []):
        if str(user.get("username", "")).casefold() == normalized:
            if user.get("role") == "gm" and not enabled:
                enabled_gms = [
                    item
                    for item in data.get("users", [])
                    if item.get("role") == "gm" and item.get("enabled", False)
                ]
                if len(enabled_gms) <= 1:
                    raise ValueError("The last enabled GM account cannot be disabled.")

            user["enabled"] = bool(enabled)
            write_json(USERS_FILE, data)
            logger.info("User %s enabled=%s", user["username"], enabled)
            return True

    return False


def reset_password(username: str, password: str) -> bool:
    _validate_password(password)

    data = read_json(USERS_FILE, {"users": []})
    normalized = username.strip().casefold()

    for user in data.get("users", []):
        if str(user.get("username", "")).casefold() == normalized:
            user["password_hash"] = password_hasher.hash(password)
            write_json(USERS_FILE, data)
            logger.info("Password reset for user %s", user["username"])
            return True

    return False


def delete_user(username: str) -> bool:
    data = read_json(USERS_FILE, {"users": []})
    normalized = username.strip().casefold()

    target = next(
        (
            user
            for user in data.get("users", [])
            if str(user.get("username", "")).casefold() == normalized
        ),
        None,
    )

    if not target:
        return False

    if target.get("role") == "gm":
        raise ValueError("GM accounts cannot be deleted from this screen.")

    data["users"] = [
        user
        for user in data.get("users", [])
        if str(user.get("username", "")).casefold() != normalized
    ]
    write_json(USERS_FILE, data)

    logger.info("User deleted: %s", target["username"])
    return True


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
        reset_password(user["username"], password)

    logger.info("Login succeeded for user %s", user["username"])
    return user


def _build_user(username: str, password: str, role: str) -> dict[str, Any]:
    username = username.strip()

    if not username:
        raise ValueError("Username is required.")

    if len(username) > 64:
        raise ValueError("Username must be 64 characters or fewer.")

    _validate_password(password)

    return {
        "username": username,
        "password_hash": password_hasher.hash(password),
        "role": role,
        "enabled": True,
    }


def _validate_password(password: str) -> None:
    if len(password) < 8:
        raise ValueError("Password must be at least 8 characters.")
