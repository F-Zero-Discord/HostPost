"""
The /event_setup wizard: one ephemeral message, edited page by page.

The draft is view state until Confirm, and nothing is written before it. The
pages ask only what the API cannot answer: which minute a slot starts, which
kind of lobby it is raced in, and which league a private Grand Prix runs. What
the public game offers at a minute is read from the API and shown as a choice.

Every page that asks the API defers first: a hop from the Raspberry Pi to the
VPS can outrun Discord's three-second interaction window.
"""

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

import discord
from discord.ext import commands

from src.data.slot_mapping import prix_emoji_name
from src.error_alerts import send_error_alert
from src.fzd_api import FzdApiError
from src.utils.hostpost_utils import discord_timestamp

logger = logging.getLogger(__name__)

# Under Discord's fifteen-minute interaction token. The view's clock restarts
# on every interaction, and the last interaction is the only handle for editing
# an ephemeral message, so a full fifteen would leave the timeout notice with
# nothing to be sent through.
WIZARD_TIMEOUT_SECONDS = 14 * 60

FIRST_SLOT_OFFSETS = (-60, -30, 0, 30, 60)
PRIX_OFFSETS = (20, 25, 30, 35, 40, 45, 60)
RACE_OFFSETS = (5, 10, 15, 20, 30)
RACE_GAP = timedelta(minutes=5)
# Ten offers: the minute at `now` and the nine after it.
RACE_OFFER_LOOKAHEAD_MINUTES = 9
PUBLIC_PRIX_LOOKAHEAD_MINUTES = 180
# One button each, two to a row on rows 0-3; row 4 is Finish and Back.
PUBLIC_PRIX_SHOWN = 6
SELECT_LIMIT = 25

KIND_AND_LOBBIES = (
    ("Prix, all public", "prix:public"),
    ("Prix, all private", "prix:private"),
    ("Prix, mixed (lobby chosen per slot)", "prix:mixed"),
    ("Single races, all public", "race:public"),
    ("Single races, all private", "race:private"),
    ("Single races, mixed (lobby chosen per slot)", "race:mixed"),
)
KIND_LABELS = {value: label for label, value in KIND_AND_LOBBIES}

MACHINE_MASTERY_RULE = "Machine Mastery: each machine's score counts once; a repeated machine keeps its best."


@dataclass
class SlotDraft:
    """One slot as the host stated it, before the API resolves the lineup."""

    label: str
    starts_at: datetime
    lobby: str
    mode: str | None = None
    lineup_id: int | None = None
    # The custom emoji's name, or "". Resolved in the guild at render time.
    emoji_name: str = ""

    def entry(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "lineup_id": self.lineup_id,
            "starts_at": self.starts_at.isoformat(),
            "lobby": self.lobby,
        }


def parse_instant(value: str) -> datetime:
    return datetime.fromisoformat(value)


def hhmm(instant: datetime) -> str:
    return f"{instant:%H:%M}"


def nearest_instant(reference: datetime, hour: int, minute: int) -> datetime:
    """The instant at HH:MM UTC closest to `reference`, so a host typing 00:30
    for an event that starts at 23:00 gets the next day."""
    at = reference.replace(hour=hour, minute=minute, second=0, microsecond=0)
    return min(
        (at + timedelta(days=days) for days in (-1, 0, 1)),
        key=lambda candidate: abs(candidate - reference),
    )


def describe_slot(slot: dict[str, Any]) -> str:
    """A written slot as the API answered it: `20:00 public Grand Prix: Knight League`.
    `starts_at` and `lobby` are null on a slot entered without them."""
    name = slot["mode"]
    if slot["lineup_name"] and slot["lineup_name"] != slot["mode"]:
        name += f": {slot['lineup_name']}"
    when = hhmm(parse_instant(slot["starts_at"])) if slot["starts_at"] else "time not entered,"
    return f"{when} {slot['lobby'] or 'lobby unknown'} {name}"


class ExactTimeModal(discord.ui.Modal, title="Exact time (UTC)"):
    time_input = discord.ui.TextInput(label="HH:MM, UTC", placeholder="19:00", min_length=4, max_length=5)

    def __init__(
        self,
        reference: datetime,
        on_time: Callable[[discord.Interaction, datetime], Awaitable[None]],
    ) -> None:
        super().__init__()
        self.reference = reference
        self.on_time = on_time

    async def on_submit(self, interaction: discord.Interaction) -> None:
        try:
            hour, minute = (int(part) for part in self.time_input.value.split(":"))
            instant = nearest_instant(self.reference, hour, minute)
        except ValueError:
            await interaction.response.send_message("Enter the time as HH:MM, UTC.", ephemeral=True)
            return
        await self.on_time(interaction, instant)


class MaxLossModal(discord.ui.Modal, title="Maximum time loss"):
    seconds_input = discord.ui.TextInput(label="Seconds behind the leader", placeholder="60", max_length=8)

    def __init__(self, wizard: "EventSetupView") -> None:
        super().__init__()
        self.wizard = wizard

    async def on_submit(self, interaction: discord.Interaction) -> None:
        try:
            centiseconds = round(float(self.seconds_input.value) * 100)
        except ValueError:
            centiseconds = 0
        if centiseconds <= 0:
            await interaction.response.send_message("Enter the maximum loss in seconds, above zero.", ephemeral=True)
            return
        self.wizard.max_time_loss_cs = centiseconds
        await self.wizard.show(interaction)


class MulligansModal(discord.ui.Modal, title="Mulligans"):
    count_input = discord.ui.TextInput(label="Results dropped before totalling", placeholder="1", max_length=3)

    def __init__(self, wizard: "EventSetupView") -> None:
        super().__init__()
        self.wizard = wizard

    async def on_submit(self, interaction: discord.Interaction) -> None:
        count = self.count_input.value.strip()
        if not count.isdecimal():
            await interaction.response.send_message("Enter the mulligans as a whole number, 0 or more.", ephemeral=True)
            return
        self.wizard.mulligans = int(count)
        await self.wizard.show(interaction)


class EventSetupView(discord.ui.View):
    """Pages: `replace` (only when the event already has slots), `config`,
    then `public_prix` or one `slot` page per slot, `review`, and after Confirm
    the `autopost` and `validate` questions the post pipeline asks.

    When the view stops, `slots` is the schedule the API answered after the
    write, or None if nothing was written.
    """

    def __init__(self, bot: commands.Bot, interaction: discord.Interaction, detail: dict[str, Any]) -> None:
        super().__init__(timeout=WIZARD_TIMEOUT_SECONDS)
        self.bot = bot
        self.api = bot.api
        self.invoker_id = interaction.user.id
        self.last_interaction = interaction
        self.guild_emojis = interaction.guild.emojis if interaction.guild else ()

        self.event_id: int = detail["scheduled_event_id"]
        self.event_name: str = detail["event"]
        self.starts_at = parse_instant(detail["starts_at"])
        self.ends_at = parse_instant(detail["ends_at"])
        self.existing_slots: list[dict[str, Any]] = detail["slots"]

        # Page 1. Scoring is pre-filled from what the event already has.
        self.scoring: str | None = detail["scoring_method"] if detail["scoring_method"] in ("points", "time") else None
        self.mulligans: int = detail["scoring"]["num_mulligans"]
        self.max_time_loss_cs: int | None = detail["scoring"]["max_time_loss_cs"]
        self.machine_mastery: bool = detail["scoring"]["machine_counts_once"]
        self.kind: str | None = None
        self.lobbies: str | None = None
        self.first_start: datetime | None = None

        # Slots.
        self.drafts: list[SlotDraft] = []
        self.public_entries: list[SlotDraft] = []
        self.public_picks: list[int] = []
        self.slot_lobby: str | None = None
        self.slot_time: datetime | None = None
        self.slot_candidates: list[SlotDraft] = []
        self.slot_pick: int | None = None

        # Outcome.
        self.slots: list[dict[str, Any]] | None = None
        self.autopost = False
        self.validate = True

        self.page = "replace" if self.existing_slots else "config"
        self.build()

    # --- plumbing ---------------------------------------------------------

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.invoker_id:
            return True
        await interaction.response.send_message("This setup belongs to whoever ran the command.", ephemeral=True)
        return False

    async def on_timeout(self) -> None:
        if self.slots is None:
            text = "This event setup timed out and wrote nothing. Run /event_setup again."
        else:
            text = "The schedule was written, but the setup timed out before the posts were built. Run /event_setup again and confirm the same schedule."
        try:
            await self.last_interaction.edit_original_response(content=text, view=None)
        except discord.HTTPException:
            pass

    async def on_error(self, interaction: discord.Interaction, error: Exception, item: discord.ui.Item) -> None:
        logger.error("event_setup wizard failed on %s", item, exc_info=error)
        await send_error_alert(self.bot, where="event_setup wizard", error=error, interaction=interaction)
        await self.finish(interaction, "ERROR! Something went wrong, contact FZD staff for help!")

    async def show(self, interaction: discord.Interaction) -> None:
        """Render the current page into the one message, whichever way this
        interaction can still be answered."""
        self.last_interaction = interaction
        self.build()
        if interaction.response.is_done():
            await interaction.edit_original_response(content=self.content(), view=self)
        else:
            await interaction.response.edit_message(content=self.content(), view=self)

    async def finish(self, interaction: discord.Interaction, text: str) -> None:
        self.last_interaction = interaction
        if interaction.response.is_done():
            await interaction.edit_original_response(content=text, view=None)
        else:
            await interaction.response.edit_message(content=text, view=None)
        self.stop()

    async def call_then_show(self, interaction: discord.Interaction, work: Callable[[], Awaitable[None]]) -> None:
        """Defer, ask the API, re-render. An API failure ends the wizard with
        the API's sentence; nothing has been written at that point."""
        await interaction.response.defer()
        try:
            await work()
        except FzdApiError as error:
            await self.finish(interaction, f"Nothing was written. {error}")
            return
        await self.show(interaction)

    def add_select(
        self,
        placeholder: str,
        options: list[discord.SelectOption],
        handler: Callable[[discord.Interaction, list[str]], Awaitable[None]],
        *,
        row: int,
        max_values: int = 1,
    ) -> None:
        select = discord.ui.Select(
            placeholder=placeholder, options=options[:SELECT_LIMIT], row=row, max_values=max_values
        )

        async def callback(interaction: discord.Interaction) -> None:
            await handler(interaction, select.values)

        select.callback = callback
        self.add_item(select)

    def add_button(
        self,
        label: str,
        handler: Callable[[discord.Interaction], Awaitable[None]],
        *,
        style: discord.ButtonStyle = discord.ButtonStyle.secondary,
        row: int = 4,
        emoji: discord.Emoji | None = None,
        disabled: bool = False,
    ) -> None:
        button = discord.ui.Button(label=label, style=style, row=row, emoji=emoji, disabled=disabled)
        button.callback = handler
        self.add_item(button)

    @staticmethod
    def options(pairs: list[tuple[str, str]], chosen: set[str]) -> list[discord.SelectOption]:
        return [discord.SelectOption(label=label[:100], value=value, default=value in chosen) for label, value in pairs]

    def emoji(self, name: str) -> discord.Emoji | None:
        """The guild's custom emoji of that name; None when it has none, and a
        button or a line then simply goes without."""
        return discord.utils.get(self.guild_emojis, name=name) if name else None

    def header(self) -> str:
        return f"## {self.event_name}, scheduled {discord_timestamp(self.starts_at, 'long')}"

    def scoring_line(self) -> str:
        if not self.scoring:
            return "Scoring: not chosen"
        parts = [self.scoring]
        if self.scoring == "time":
            cap = f"{self.max_time_loss_cs / 100:.2f} s" if self.max_time_loss_cs else "not set"
            parts.append(f"maximum loss {cap}")
        parts.append("Machine Mastery" if self.machine_mastery else f"{self.mulligans} mulligan(s)")
        return "Scoring: " + ", ".join(parts)

    # --- rendering --------------------------------------------------------

    def build(self) -> None:
        self.clear_items()
        getattr(self, f"build_{self.page}")()

    def content(self) -> str:
        return getattr(self, f"content_{self.page}")()

    # Page: replace?

    def content_replace(self) -> str:
        listed = "\n".join(f"{index}. {describe_slot(slot)}" for index, slot in enumerate(self.existing_slots, start=1))
        return (
            f"{self.header()}\nThis event already has a schedule:\n{listed}\n\n"
            "Replace it? The whole schedule is rewritten at Confirm, and nothing changes before then. "
            "The API refuses the replacement once a result has been recorded."
        )

    def build_replace(self) -> None:
        self.add_button("Replace", self.on_replace, style=discord.ButtonStyle.danger)
        self.add_button("Cancel", self.on_cancel)

    async def on_replace(self, interaction: discord.Interaction) -> None:
        self.page = "config"
        await self.show(interaction)

    async def on_cancel(self, interaction: discord.Interaction) -> None:
        await self.finish(interaction, "Nothing changed.")

    # Page: configuration.

    def content_config(self) -> str:
        lines = [self.header(), self.scoring_line()]
        if self.machine_mastery:
            lines.append(MACHINE_MASTERY_RULE)
        if self.kind:
            lines.append(f"Event: {KIND_LABELS[f'{self.kind}:{self.lobbies}']}")
        if self.first_start:
            lines.append(f"First slot: {hhmm(self.first_start)} UTC, {discord_timestamp(self.first_start, 'short')} your time")
            if not self.starts_at <= self.first_start <= self.ends_at:
                lines.append(
                    f"⚠️ That is outside the scheduled window ({hhmm(self.starts_at)}–{hhmm(self.ends_at)} UTC). "
                    "The calendar keeps the scheduled time; the posts follow the first slot."
                )
        return "\n".join(lines)

    def build_config(self) -> None:
        self.add_select(
            "Scoring",
            self.options([("Points", "points"), ("Time", "time")], {self.scoring or ""}),
            self.on_scoring,
            row=0,
        )
        self.add_select(
            "Kind of event, and its lobbies",
            self.options(list(KIND_AND_LOBBIES), {f"{self.kind}:{self.lobbies}"}),
            self.on_kind,
            row=1,
        )
        # Discord has no checkbox outside a modal, so the rule is a button whose
        # label carries its state. Mulligans and the rule exclude each other on
        # this page: `on_machine_mastery` zeroes them and this locks the button.
        self.add_button("Mulligans", self.on_mulligans, row=2, disabled=self.machine_mastery)
        self.add_button(f"{'☑' if self.machine_mastery else '☐'} Machine Mastery", self.on_machine_mastery, row=2)
        chosen = self.first_start.isoformat() if self.first_start else ""
        self.add_select(
            "First slot time",
            self.options(
                [
                    (f"{hhmm(at)} UTC ({offset:+d} min from the scheduled start)", at.isoformat())
                    for offset in FIRST_SLOT_OFFSETS
                    for at in [self.starts_at + timedelta(minutes=offset)]
                ],
                {chosen},
            ),
            self.on_first_start,
            row=3,
        )
        self.add_button("Exact first time", self.on_exact_first_time)
        if self.scoring == "time":
            self.add_button("Maximum time loss", self.on_max_loss)
        self.add_button("Next", self.on_config_next, style=discord.ButtonStyle.primary)

    async def on_scoring(self, interaction: discord.Interaction, values: list[str]) -> None:
        self.scoring = values[0]
        if self.scoring == "points":
            self.max_time_loss_cs = None
        await self.show(interaction)

    async def on_kind(self, interaction: discord.Interaction, values: list[str]) -> None:
        self.kind, self.lobbies = values[0].split(":")
        await self.show(interaction)

    async def on_mulligans(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(MulligansModal(self))

    async def on_machine_mastery(self, interaction: discord.Interaction) -> None:
        self.machine_mastery = not self.machine_mastery
        if self.machine_mastery:
            self.mulligans = 0
        await self.show(interaction)

    async def on_first_start(self, interaction: discord.Interaction, values: list[str]) -> None:
        self.first_start = parse_instant(values[0])
        await self.show(interaction)

    async def on_exact_first_time(self, interaction: discord.Interaction) -> None:
        async def set_time(modal_interaction: discord.Interaction, instant: datetime) -> None:
            self.first_start = instant
            await self.show(modal_interaction)

        await interaction.response.send_modal(ExactTimeModal(self.starts_at, set_time))

    async def on_max_loss(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(MaxLossModal(self))

    async def on_config_next(self, interaction: discord.Interaction) -> None:
        missing = []
        if not self.scoring:
            missing.append("the scoring")
        if self.scoring == "time" and not self.max_time_loss_cs:
            missing.append("the maximum time loss")
        if not self.kind:
            missing.append("the kind of event")
        if not self.first_start:
            missing.append("the first slot time")
        if missing:
            await interaction.response.send_message(f"Choose {', '.join(missing)} first.", ephemeral=True)
            return

        self.drafts = []
        if self.kind == "prix" and self.lobbies == "public":
            await self.call_then_show(interaction, self.load_public_entries)
        else:
            await self.call_then_show(interaction, self.begin_slot)

    # Page: all-public prix, one toggle button per rotation entry.

    async def load_public_entries(self) -> None:
        assert self.first_start is not None
        entries = await self.api.rotation(
            self.first_start, kind="prix", lookahead_minutes=PUBLIC_PRIX_LOOKAHEAD_MINUTES
        )
        self.public_entries = []
        for entry in entries[:PUBLIC_PRIX_SHOWN]:
            # The window containing the first slot opened earlier; the slot
            # starts when the host said, not when the game did.
            starts_at = max(parse_instant(entry["starts_at"]), self.first_start)
            self.public_entries.append(
                SlotDraft(
                    label=f"{hhmm(starts_at)} {entry['lineup'] or entry['mode']}",
                    starts_at=starts_at,
                    lobby="public",
                    mode=entry["mode_short_name"],
                    emoji_name=prix_emoji_name(entry["mode"], entry["lineup"]),
                )
            )
        self.public_picks = [0] if self.public_entries else []
        self.page = "public_prix"

    def content_public_prix(self) -> str:
        assert self.first_start is not None
        lines = [self.header(), self.scoring_line()]
        if not self.public_entries:
            lines.append(f"The game runs no prix from {hhmm(self.first_start)} UTC. Go back and choose another first slot time.")
        else:
            lines.append("Pick the prix the event runs; green is in. The API resolves each league and Mini Prix set at Confirm.")
            picked = [
                f"{self.emoji(draft.emoji_name) or ''} {draft.label}".strip()
                for draft in (self.public_entries[index] for index in self.public_picks)
            ]
            lines.append("Picked: " + (", ".join(picked) if picked else "nothing yet"))
        return "\n".join(lines)

    def build_public_prix(self) -> None:
        for index, draft in enumerate(self.public_entries):
            picked = index in self.public_picks
            self.add_button(
                draft.label,
                self.public_toggle(index),
                style=discord.ButtonStyle.success if picked else discord.ButtonStyle.secondary,
                row=index // 2,
                emoji=self.emoji(draft.emoji_name),
            )
        if self.public_entries:
            self.add_button("Finish", self.on_public_finish, style=discord.ButtonStyle.primary)
        self.add_button("Back", self.on_back)

    def public_toggle(self, index: int) -> Callable[[discord.Interaction], Awaitable[None]]:
        async def toggle(interaction: discord.Interaction) -> None:
            self.public_picks = sorted(set(self.public_picks) ^ {index})
            await self.show(interaction)

        return toggle

    async def on_public_finish(self, interaction: discord.Interaction) -> None:
        if not self.public_picks:
            await interaction.response.send_message("Pick at least one prix.", ephemeral=True)
            return
        self.drafts = [self.public_entries[index] for index in self.public_picks]
        self.page = "review"
        await self.show(interaction)

    async def on_back(self, interaction: discord.Interaction) -> None:
        self.drafts = []
        self.page = "config"
        await self.show(interaction)

    # Page: one slot at a time.

    async def begin_slot(self) -> None:
        previous = self.drafts[-1].starts_at if self.drafts else None
        self.slot_lobby = None if self.lobbies == "mixed" else self.lobbies
        if previous is None:
            self.slot_time = self.first_start
        elif self.kind == "race":
            self.slot_time = previous + RACE_GAP
        else:
            self.slot_time = None
        self.page = "slot"
        await self.load_candidates()

    async def load_candidates(self) -> None:
        """What the entry select offers for this slot's lobby and minute."""
        self.slot_candidates = []
        self.slot_pick = None
        lobby, at = self.slot_lobby, self.slot_time
        if lobby is None or at is None:
            return

        if self.kind == "race":
            offers = await self.api.lineup_offers(
                "99", lobby=lobby, now=at, lookahead_minutes=RACE_OFFER_LOOKAHEAD_MINUTES
            )
            self.slot_candidates = [
                SlotDraft(f"{hhmm(starts)} {offer['lineup']}", starts, lobby, mode="99")
                for offer in offers
                for starts in [parse_instant(offer["starts_at"])]
            ]
        elif lobby == "public":
            entries = await self.api.rotation(at, kind="prix", lookahead_minutes=0)
            self.slot_candidates = [
                SlotDraft(f"{hhmm(at)} {entry['lineup'] or entry['mode']}", at, "public", mode=entry["mode_short_name"])
                for entry in entries
            ]
        else:
            leagues = await self.api.lineups("GP")
            self.slot_candidates = [
                SlotDraft(f"{hhmm(at)} Mini Prix", at, "private", mode="MP"),
                SlotDraft(f"{hhmm(at)} Classic Mini Prix", at, "private", mode="cMP"),
            ] + [
                SlotDraft(f"{hhmm(at)} {league['name']}", at, "private", lineup_id=league["lineup_id"])
                for league in leagues
                # A private lobby cannot start Secret GP, the league with glitch tracks.
                if not any(track["type"] == "glitch" for track in league["tracks"])
            ]

    def content_slot(self) -> str:
        number = len(self.drafts) + 1
        lines = [self.header(), self.scoring_line()]
        if self.drafts:
            lines.append("So far: " + "; ".join(f"{draft.label} ({draft.lobby})" for draft in self.drafts))
        lines.append(f"### Slot {number}")
        if self.lobbies == "mixed":
            lines.append(f"Lobby: {self.slot_lobby or 'choose one'}")
        lines.append(f"Time: {hhmm(self.slot_time) + ' UTC' if self.slot_time else 'choose one'}")
        if self.slot_pick is not None:
            lines.append(f"Pick: {self.slot_candidates[self.slot_pick].label}")
        elif self.slot_lobby and self.slot_time and not self.slot_candidates:
            what = "a 99 race" if self.kind == "race" else "a prix"
            lines.append(f"The game offers nothing for {what} in a {self.slot_lobby} lobby at {hhmm(self.slot_time)} UTC. Choose another time.")
        return "\n".join(lines)

    def build_slot(self) -> None:
        if self.lobbies == "mixed":
            self.add_select(
                "Lobby",
                self.options([("Public", "public"), ("Private", "private")], {self.slot_lobby or ""}),
                self.on_slot_lobby,
                row=0,
            )
        if self.drafts:
            previous = self.drafts[-1].starts_at
            offsets = RACE_OFFSETS if self.kind == "race" else PRIX_OFFSETS
            chosen = self.slot_time.isoformat() if self.slot_time else ""
            self.add_select(
                "Time, from the previous slot",
                self.options(
                    [
                        (f"{hhmm(at)} UTC (+{offset} min)", at.isoformat())
                        for offset in offsets
                        for at in [previous + timedelta(minutes=offset)]
                    ],
                    {chosen},
                ),
                self.on_slot_time,
                row=1,
            )
            self.add_button("Exact time", self.on_exact_slot_time)
        if self.slot_candidates:
            placeholder = "Race" if self.kind == "race" else "Prix"
            pairs = [(draft.label, str(index)) for index, draft in enumerate(self.slot_candidates)]
            self.add_select(
                placeholder,
                self.options(pairs, {str(self.slot_pick) if self.slot_pick is not None else ""}),
                self.on_slot_pick,
                row=2,
            )
        self.add_button("Next slot", self.on_slot_next, style=discord.ButtonStyle.primary)
        self.add_button("Finish", self.on_slot_finish, style=discord.ButtonStyle.success)
        self.add_button("Back", self.on_back)

    async def on_slot_lobby(self, interaction: discord.Interaction, values: list[str]) -> None:
        self.slot_lobby = values[0]
        await self.call_then_show(interaction, self.load_candidates)

    async def on_slot_time(self, interaction: discord.Interaction, values: list[str]) -> None:
        self.slot_time = parse_instant(values[0])
        await self.call_then_show(interaction, self.load_candidates)

    async def on_exact_slot_time(self, interaction: discord.Interaction) -> None:
        async def set_time(modal_interaction: discord.Interaction, instant: datetime) -> None:
            self.slot_time = instant
            await self.call_then_show(modal_interaction, self.load_candidates)

        await interaction.response.send_modal(ExactTimeModal(self.drafts[-1].starts_at, set_time))

    async def on_slot_pick(self, interaction: discord.Interaction, values: list[str]) -> None:
        self.slot_pick = int(values[0])
        await self.show(interaction)

    async def take_slot(self, interaction: discord.Interaction) -> bool:
        if self.slot_pick is None:
            await interaction.response.send_message("Pick what this slot runs first.", ephemeral=True)
            return False
        self.drafts.append(self.slot_candidates[self.slot_pick])
        return True

    async def on_slot_next(self, interaction: discord.Interaction) -> None:
        if await self.take_slot(interaction):
            await self.call_then_show(interaction, self.begin_slot)

    async def on_slot_finish(self, interaction: discord.Interaction) -> None:
        if await self.take_slot(interaction):
            self.page = "review"
            await self.show(interaction)

    # Page: review and confirm.

    def content_review(self) -> str:
        listed = "\n".join(
            f"{index}. {draft.label} ({draft.lobby})" for index, draft in enumerate(self.drafts, start=1)
        )
        return (
            f"{self.header()}\n{self.scoring_line()}\n{listed}\n\n"
            "Confirm writes the scoring, then the schedule. The API resolves each public league and Mini Prix set."
        )

    def build_review(self) -> None:
        self.add_button("Confirm", self.on_confirm, style=discord.ButtonStyle.success)
        self.add_button("Back", self.on_back)
        self.add_button("Cancel", self.on_cancel)

    async def on_confirm(self, interaction: discord.Interaction) -> None:
        assert self.scoring is not None
        await interaction.response.defer()
        try:
            await self.api.set_scoring(
                self.event_id,
                scoring_method=self.scoring,
                num_mulligans=self.mulligans,
                max_time_loss_cs=self.max_time_loss_cs if self.scoring == "time" else None,
                machine_counts_once=self.machine_mastery,
            )
        except FzdApiError as error:
            await self.finish(interaction, f"Nothing was written. {error}")
            return
        try:
            self.slots = await self.api.replace_schedule(self.event_id, [draft.entry() for draft in self.drafts])
        except FzdApiError as error:
            await self.finish(
                interaction,
                f"The scoring was saved, but the schedule was not. {error}\nRun /event_setup again; both writes replace what is there.",
            )
            return
        self.page = "autopost"
        await self.show(interaction)

    # Pages after the write: what the post pipeline asks.

    def written_summary(self) -> str:
        assert self.slots is not None
        listed = "\n".join(f"{index}. {describe_slot(slot)}" for index, slot in enumerate(self.slots, start=1))
        return f"{self.header()}\nSchedule written:\n{listed}\n\n"

    def content_autopost(self) -> str:
        return (
            f"{self.written_summary()}### :bangbang: Would you like the bot to push the announcement and prix "
            "opening posts automatically? (Note that prix and event results posts continue to require manual "
            "intervention through slash commands.)"
        )

    def build_autopost(self) -> None:
        self.add_button("Hail to the Machines", self.on_auto, style=discord.ButtonStyle.danger)
        self.add_button("I'll do it myself", self.on_manual, style=discord.ButtonStyle.success)

    async def on_auto(self, interaction: discord.Interaction) -> None:
        self.autopost = True
        self.page = "validate"
        await self.show(interaction)

    async def on_manual(self, interaction: discord.Interaction) -> None:
        self.autopost = False
        await self.finish(interaction, f"{self.written_summary()}User will post all event posts.")

    def content_validate(self) -> str:
        return f"{self.written_summary()}### :bangbang: Would you like to validate final scores before scores are posted?"

    def build_validate(self) -> None:
        self.add_button("Skip validation", self.on_skip_validation, style=discord.ButtonStyle.danger)
        self.add_button("I'll validate", self.on_validate, style=discord.ButtonStyle.success)

    async def on_skip_validation(self, interaction: discord.Interaction) -> None:
        self.validate = False
        await self.finish(
            interaction,
            f"{self.written_summary()}Event announcement and prix opening posts will be posted automatically. Results will be pushed without validation.",
        )

    async def on_validate(self, interaction: discord.Interaction) -> None:
        self.validate = True
        await self.finish(
            interaction,
            f"{self.written_summary()}Event announcement and prix opening posts will be posted automatically. Host will be prompted to validate results before posting.",
        )
