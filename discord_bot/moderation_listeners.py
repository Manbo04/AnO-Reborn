"""Auto-mod filter checks, run against every non-bot message.

Requires the message_content intent (see main.py) — without it every
message's .content is empty and every filter below is a silent no-op.
"""

import logging
import re
from collections import defaultdict, deque
from typing import Deque, Dict, Tuple

import discord

from discord_bot import moderation_store as store

logger = logging.getLogger("ano_discord_bot")

_INVITE_RE = re.compile(r"(discord\.gg|discord(?:app)?\.com/invite)/\S+", re.IGNORECASE)

# In-memory sliding window for spam detection — fine for a single-process bot,
# not shared across restarts/shards (there is only one process today).
_recent_messages: Dict[Tuple[str, str], Deque[float]] = defaultdict(deque)


def _is_spam(guild_id: str, user_id: str, limit: int, interval_seconds: int, now: float) -> bool:
    key = (guild_id, user_id)
    window = _recent_messages[key]
    window.append(now)
    cutoff = now - interval_seconds
    while window and window[0] < cutoff:
        window.popleft()
    return len(window) > limit


def _contains_bad_word(content: str, bad_words) -> bool:
    lowered = content.lower()
    for word in bad_words:
        if re.search(rf"\b{re.escape(word)}\b", lowered):
            return True
    return False


async def _take_action(message: discord.Message, config, reason: str) -> None:
    try:
        await message.delete()
    except (discord.Forbidden, discord.NotFound):
        pass
    except Exception as exc:
        logger.warning("Automod delete failed in guild %s: %s", message.guild.id, exc)

    member = message.author
    guild_id = str(message.guild.id)
    case_action = "warn"
    duration = None

    if config.filter_action == "delete_timeout" and isinstance(member, discord.Member):
        from datetime import timedelta

        duration = config.filter_timeout_minutes
        try:
            await member.timeout(timedelta(minutes=duration), reason=reason)
            case_action = "timeout"
        except discord.Forbidden:
            logger.warning("Missing permission to timeout in guild %s", guild_id)
        except Exception as exc:
            logger.warning("Automod timeout failed in guild %s: %s", guild_id, exc)
    elif config.filter_action == "delete_only":
        case_action = None

    if case_action:
        store.create_case(
            guild_id=guild_id,
            action=case_action,
            target_user_id=str(member.id),
            moderator_user_id=str(message.guild.me.id) if message.guild.me else "0",
            reason=reason,
            duration_minutes=duration,
        )

    if config.log_channel_id:
        channel = message.guild.get_channel(int(config.log_channel_id))
        if isinstance(channel, discord.TextChannel):
            embed = discord.Embed(
                title="Auto-mod action",
                description=f"{member.mention} ({member}) in {message.channel.mention}\n{reason}",
                color=discord.Color.red(),
            )
            try:
                await channel.send(embed=embed)
            except discord.Forbidden:
                pass


async def handle_automod_message(message: discord.Message) -> None:
    if not message.guild or message.author.bot:
        return
    if not isinstance(message.author, discord.Member):
        return
    if message.author.guild_permissions.manage_messages:
        return  # never auto-mod staff

    guild_id = str(message.guild.id)
    config = store.get_moderation_config(guild_id)
    content = message.content or ""

    if config.filter_invites_enabled and _INVITE_RE.search(content):
        await _take_action(message, config, "Posted an invite link")
        return

    if config.filter_mass_mentions_enabled:
        mention_count = len(message.mentions) + len(message.role_mentions)
        if mention_count > config.filter_mass_mentions_limit:
            await _take_action(message, config, f"Mass-mentioned {mention_count} users/roles")
            return

    if config.filter_bad_words_enabled:
        bad_words = store.list_bad_words(guild_id)
        if bad_words and _contains_bad_word(content, bad_words):
            await _take_action(message, config, "Used a filtered word")
            return

    if config.filter_spam_enabled:
        import time

        if _is_spam(
            guild_id,
            str(message.author.id),
            config.filter_spam_message_limit,
            config.filter_spam_interval_seconds,
            time.monotonic(),
        ):
            await _take_action(
                message,
                config,
                f"Sent more than {config.filter_spam_message_limit} messages in "
                f"{config.filter_spam_interval_seconds}s",
            )
            return
