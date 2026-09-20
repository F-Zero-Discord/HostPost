"""
Turns the slots the FZD API answers for a schedule into the `prix_list` the
post builder consumes.

The post templates in `event_post_text` are keyed on `prix_info[].shortname`;
a slot on the wire carries the mode's name and the lineup's name. This is the
only place the two vocabularies meet.
"""

from datetime import datetime
from typing import Any

from src.data.event_post_text import prix_info

# `(mode name, lineup name)` as `GET /v1/events/{id}/schedule` spells them.
# A Grand Prix slot is known by its league; every other mode by the mode alone.
LEAGUE_SHORTNAMES = {
    "Knight League": "knight",
    "mirror Knight League": "mknight",
    "Queen League": "queen",
    "mirror Queen League": "mqueen",
    "King League": "king",
    "mirror King League": "mking",
    "Ace League": "ace",
    "mirror Ace League": "mace",
    "Secret GP": "glitchgp",
}

MODE_SHORTNAMES = {
    "Mini Prix": "miniprix",
    "Classic Mini Prix": "classicprix",
    "World Tour": "worldtour",
    "Mini World Tour": "miniwt",
    "99": "race99",
}

# A track list in `prix_list[].lineup` makes the posts print the set and hand
# out a passcode, so it is filled only for a private Mini Prix: a public one
# joins whatever the game runs, a league's tracks are implied by its name, and
# a 99 slot's pair is decided by the vote.
MODES_WITH_TRACK_LIST = {"Mini Prix", "Classic Mini Prix"}


def prix_shortname(slot: dict[str, Any]) -> str:
    mode = slot["mode"]
    if mode == "Grand Prix":
        league = slot["lineup_name"]
        if league not in LEAGUE_SHORTNAMES:
            raise ValueError(f"No post template for a Grand Prix on {league!r}")
        return LEAGUE_SHORTNAMES[league]
    if mode not in MODE_SHORTNAMES:
        raise ValueError(f"No post template for mode {mode!r}")
    return MODE_SHORTNAMES[mode]


def prix_emoji_name(mode: str, lineup: str | None) -> str:
    """The name of the custom emoji `prix_info` gives the prix a rotation entry
    names, `GPKnight` from `<:GPKnight:1195…>`, or "" for a prix with no
    template and so no emoji. A name and not an id: each guild the bot runs in
    carries its own copy of the emoji, under the same name."""
    try:
        shortname = prix_shortname({"mode": mode, "lineup_name": lineup})
    except ValueError:
        return ""
    markup = next(prix["emoji"] for prix in prix_info if prix["shortname"] == shortname)
    return markup.split(":")[1] if markup else ""


def track_names(slot: dict[str, Any]) -> list[str]:
    if slot["mode"] not in MODES_WITH_TRACK_LIST or slot["lobby"] != "private":
        return []
    return [track["name"] for track in slot["tracks"]]


def prix_list_from_slots(slots: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The `prix_list` shape `build_posts` and `build_autopost_dict` take:
    `{prix, time, prix_type, lineup}` per slot, in schedule order."""
    return [
        {
            "prix": prix_shortname(slot),
            "time": datetime.fromisoformat(slot["starts_at"]),
            "prix_type": slot["lobby"],
            "lineup": track_names(slot),
        }
        for slot in slots
    ]
