"""Pure, GUI-independent authentication settings migration helpers."""

def migrate_auth_config(config: dict) -> dict:
    """Keep username while discarding legacy plaintext password data."""
    return {"username": str(config.get("username", ""))}


def auth_config_for_save(username: str) -> dict:
    """Build the only authentication data that may be persisted."""
    return {"username": username}
