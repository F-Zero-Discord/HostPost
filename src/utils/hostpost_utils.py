from datetime import datetime, timedelta


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
