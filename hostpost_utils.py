from datetime import datetime, timedelta, timezone
import discord
# from discord import ui
from event_post_text import prix_info, time_offset_options


def create_prix_option_set() -> discord.SelectOption:
    dropdown_options = []
    for prix in prix_info:
        dropdown_options.append(
            discord.SelectOption(
                label=prix["emoji"] + " " + prix["mirror_emoji"] + prix["fullname"],
                description=prix["shortname"],
                value=prix["shortname"]
                )
            )
    return dropdown_options

def create_timeoffset_option_set() -> discord.SelectOption:
    dropdown_options = []
    for key, value in time_offset_options.items():
        dropdown_options.append(
            discord.SelectOption(
                label=key,
                # description=key,
                value=value
                )
            )
    return dropdown_options

def create_publicprivate_option_set() -> discord.SelectOption:
    dropdown_options = []
    dropdown_options.append(
        discord.SelectOption(
            label="Public",
            value="public"
            ))
    dropdown_options.append(
        discord.SelectOption(
            label="Private",
            value="private"
            ))
    return dropdown_options

def discord_timestamp(dt: datetime, format_type: str = "short") -> str:
    """Convert a datetime object to a Discord-formatted timestamp string."""
    match format_type:
        case "short":
            format_type = "t"
        case "relative":
            format_type = "R"
        case "long":
            format_type = "f"
    unix_timestamp = round(int(dt.timestamp()))
    return f"<t:{unix_timestamp}:{format_type}>"

def round_to_30_minutes(dt: datetime) -> datetime:
    """Round a datetime object to the nearest 30 minutes."""
    if dt.minute < 15:
        return dt.replace(minute=0, second=0, microsecond=0)
    elif dt.minute < 45:
        return dt.replace(minute=30, second=0, microsecond=0)
    else:
        return (dt + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)