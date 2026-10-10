"""Pure helper functions for displaying Discord usernames on country/nation profiles."""
from typing import Optional, Any


def should_show_discord(
    show_discord: Optional[bool],
    discord_username: Optional[str],
    discord_id: Optional[Any] = None,
) -> bool:
    """
    Check if a Discord username should be displayed on the nation profile.
    Only True when show_discord is True and discord_username is a non-empty string.
    """
    if not show_discord:
        return False
    if discord_username is None:
        return False
    clean_name = str(discord_username).strip()
    return len(clean_name) > 0


def get_discord_display_name(
    show_discord: Optional[bool],
    discord_username: Optional[str],
    discord_id: Optional[Any] = None,
) -> Optional[str]:
    """
    Returns the Discord username to display on the nation profile,
    or None if the setting is off or no username is known.
    """
    if not should_show_discord(show_discord, discord_username, discord_id):
        return None
    return str(discord_username).strip()
