"""
The /event_setup wizard: one ephemeral Components V2 message, rebuilt on every
click.

The host picks the type of event, answers one modal of settings, then builds
the schedule on one page. The draft is view state until Confirm, and nothing is
written before it. A modal asks what is typed or fixed; the message asks what
depends on the API's answer for a minute, because a modal cannot change while
it is open.

Every handler that asks the API defers first: a hop from the Raspberry Pi to the
VPS can outrun Discord's three-second interaction window.
"""

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Literal

import discord
from discord.ext import commands

from src.data.event_post_text import events
from src.data.slot_mapping import prix_emoji_name, prix_list_from_slots
from src.error_alerts import send_error_alert
from src.fzd_api import FzdApiError
from src.utils.hostpost_utils import discord_timestamp

logger = logging.getLogger(__name__)

# Under Discord's fifteen-minute interaction token. The view's clock restarts
# on every interaction, and the last interaction is the only handle for editing
# an ephemeral message, so a full fifteen would leave the timeout notice with
# nothing to be sent through.
WIZARD_TIMEOUT_SECONDS = 14 * 60

EventType = Literal["gpmp", "cmp", "race", "tb"]
EVENT_TYPES: dict[EventType, str] = {
    "gpmp": "Grand Prix and Mini Prix",
    "cmp": "Classic Mini Prix",
    "race": "Single races",
    "tb": "Team Battle",
}
# How FZD runs each type, not what the API admits: widening one is an edit here
# and a stage run. Each pair is one button on the type page.
LOBBIES: dict[EventType, tuple[str, ...]] = {
    "gpmp": ("public", "private", "mixed"),
    "cmp": ("private",),
    "race": ("public", "private"),
    "tb": ("public", "private"),
}
# Scored on points by how FZD runs it; the modal does not ask.
POINTS_ONLY: set[EventType] = {"tb"}
# The modes a single races slot may be, by short name, as the mode buttons name them.
RACE_MODES = {"99": "99 Race", "Pro": "Pro Tracks"}
# How a race slot names its mode in the schedule and the lineup select.
RACE_MODE_NAMES = {"99": "99", "Pro": "Pro Tracks", "TB": "Team Battle"}

# Minutes from the previous slot: what the time select offers, and what the
# next time moves on by after a slot is added.
PRIX_OFFSETS = (20, 25, 30, 35, 40)
PRIX_GAP = 30
RACE_OFFSETS = (5, 10, 15, 20, 30)
RACE_GAP = 5
# Ten offers: the minute at `now` and the nine after it.
RACE_OFFER_LOOKAHEAD_MINUTES = 9
PUBLIC_PRIX_LOOKAHEAD_MINUTES = 180
PUBLIC_PRIX_SHOWN = 6
BUTTONS_PER_ROW = 5
SELECT_LIMIT = 25

CLASSIC_MINI_PRIX = "cMP"
SCHEDULE_HEADING = "### Schedule\nHere you can see the schedule as you fill it out."
MACHINE_MASTERY_RULE = "Machine Mastery: each machine's score counts once; a repeated machine keeps its best."
MACHINE_MASTERY_HINT = "Each machine's score counts once; a repeated one keeps its best. Points scoring only."


@dataclass
class SlotDraft:
    """One slot as the host stated it, before the API resolves the lineup."""

    name: str
    starts_at: datetime
    lobby: str
    mode: str | None = None
    lineup_id: int | None = None
    # The custom emoji's name, or "". Resolved in the guild at render time.
    emoji_name: str = ""
    # The time the pick was offered from, which is where going back to this
    # slot offers again: a 99 pick at 22:07 was chosen from the offers at 22:05.
    offered_from: datetime = field(kw_only=True)

    def same_pick(self, other: "SlotDraft") -> bool:
        return (self.name, self.starts_at, self.lobby) == (other.name, other.starts_at, other.lobby)

    def entry(self) -> dict[str, Any]:
        """The slot as the schedule write takes it: exactly one of `lineup_id`
        and `mode`, which the API refuses both or neither of. A mode alone is
        resolved to what the game offers at the minute, or to the mode's
        placeholder."""
        named = {"lineup_id": self.lineup_id} if self.lineup_id is not None else {"mode": self.mode}
        return {**named, "starts_at": self.starts_at.isoformat(), "lobby": self.lobby}


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


def parse_hhmm(reference: datetime, text: str) -> datetime:
    """Raises ValueError for anything that is not a time of day as HH:MM."""
    hour, minute = (int(part) for part in text.strip().split(":"))
    return nearest_instant(reference, hour, minute)


def describe_slot(slot: dict[str, Any]) -> str:
    """A written slot as the API answered it: `20:00 public Grand Prix: Knight League`.
    `starts_at` and `lobby` are null on a slot entered without them. A slot on
    its mode's placeholder has no tracks, and its lineup name says only that,
    so it is shown by the mode alone."""
    name = slot["mode"]
    if slot["tracks"]:
        name += f": {slot['lineup_name']}"
    when = hhmm(parse_instant(slot["starts_at"])) if slot["starts_at"] else "time not entered,"
    return f"{when} {slot['lobby'] or 'lobby unknown'} {name}"


class WizardModal(discord.ui.Modal):
    """A modal whose failures take the wizard's error path, and its alert."""

    def __init__(self, wizard: "EventSetupView", *, title: str) -> None:
        super().__init__(title=title)
        self.wizard = wizard

    async def on_error(self, interaction: discord.Interaction, error: Exception) -> None:
        await self.wizard.fail(interaction, error, where=type(self).__name__)


class ExactTimeModal(WizardModal):
    def __init__(
        self,
        wizard: "EventSetupView",
        reference: datetime,
        on_time: Callable[[discord.Interaction, datetime], Awaitable[None]],
    ) -> None:
        super().__init__(wizard, title="Exact time (UTC)")
        self.reference = reference
        self.on_time = on_time
        self.time_input = discord.ui.TextInput(placeholder=hhmm(reference), min_length=4, max_length=5)
        self.add_item(discord.ui.Label(text="HH:MM, UTC", component=self.time_input))

    async def on_submit(self, interaction: discord.Interaction) -> None:
        try:
            instant = parse_hhmm(self.reference, self.time_input.value)
        except ValueError:
            await interaction.response.send_message("Enter the time as HH:MM, UTC.", ephemeral=True)
            return
        await self.on_time(interaction, instant)


class SettingsModal(WizardModal):
    """The event's settings. `scoring_only` leaves out the start time, which the
    slots depend on, so it can be reopened from the schedule page without
    touching what is entered there.

    A modal runs nothing until it is submitted, so no field can be disabled by
    another's answer: each says when it applies, and is ignored otherwise."""

    def __init__(self, wizard: "EventSetupView", *, scoring_only: bool) -> None:
        assert wizard.event_type is not None
        super().__init__(wizard, title=f"{EVENT_TYPES[wizard.event_type]}, {wizard.lobbies} lobbies")

        self.first_slot: discord.ui.TextInput | None = None
        if not scoring_only:
            self.first_slot = discord.ui.TextInput(default=wizard.first_slot_text, min_length=4, max_length=5)
            self.add_item(
                discord.ui.Label(
                    text="Event start time, HH:MM UTC",
                    description=f"Scheduled for {hhmm(wizard.starts_at)} UTC. The first slot starts then.",
                    component=self.first_slot,
                )
            )

        self.scoring: discord.ui.RadioGroup | None = None
        self.max_loss: discord.ui.TextInput | None = None
        if wizard.event_type not in POINTS_ONLY:
            self.scoring = discord.ui.RadioGroup(
                options=[
                    discord.RadioGroupOption(label=label, value=value, default=value == wizard.scoring)
                    for label, value in (("Points", "points"), ("Time", "time"))
                ]
            )
            self.add_item(discord.ui.Label(text="Scoring", component=self.scoring))

            self.max_loss = discord.ui.TextInput(
                default=wizard.max_loss_text, placeholder="60", required=False, max_length=8
            )
            self.add_item(
                discord.ui.Label(
                    text="Maximum time loss, seconds",
                    description="Time scoring only; ignored for points.",
                    component=self.max_loss,
                )
            )

        self.mulligans = discord.ui.TextInput(default=wizard.mulligans_text, max_length=3)
        self.add_item(
            discord.ui.Label(
                text="Mulligans",
                description="Results dropped before totalling. Ignored with Machine Mastery.",
                component=self.mulligans,
            )
        )

        self.machine_mastery = discord.ui.Checkbox(default=wizard.machine_mastery)
        self.add_item(
            discord.ui.Label(text="Machine Mastery", description=MACHINE_MASTERY_HINT, component=self.machine_mastery)
        )

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await self.wizard.on_settings(interaction, self)


class EventSetupView(discord.ui.LayoutView):
    """Pages: `type`, `schedule`, then `posting`. Confirm writes; `posting`
    asks how the event's posts go out and ends the wizard.

    When the view stops, `slots` is the schedule the API answered after the
    write, or None if nothing was written. `prix_list` and `autopost` are set
    only when the host answered `posting`, and the caller builds the posts.
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

        # Settings. Scoring is pre-filled from what the event already has; the
        # typed fields are kept as typed, so a modal that did not validate
        # reopens with the host's input rather than the last good value.
        self.event_type: EventType | None = None
        self.lobbies: str | None = None
        self.scoring: str | None = detail["scoring_method"] if detail["scoring_method"] in ("points", "time") else None
        self.mulligans: int = detail["scoring"]["num_mulligans"]
        self.machine_mastery: bool = detail["scoring"]["machine_counts_once"]
        self.max_time_loss_cs: int | None = detail["scoring"]["max_time_loss_cs"]
        self.max_loss_text = f"{self.max_time_loss_cs / 100:g}" if self.max_time_loss_cs else ""
        self.mulligans_text = str(self.mulligans)
        self.first_slot_text = hhmm(self.starts_at)
        self.first_start = self.starts_at
        # The sentence for a settings submit that did not validate; shown once.
        self.notice: str | None = None

        # The schedule.
        self.drafts: list[SlotDraft] = []
        self.cursor = 0
        self.slot_time = self.starts_at
        # The mode the slot at the cursor is picked in, on a single races event.
        self.race_mode = "99"
        self.candidates: list[SlotDraft] = []
        # Whether the game offered something at `slot_time` that falls outside
        # the slot's neighbours, as opposed to offering nothing.
        self.offered_outside = False
        self.private_leagues: list[dict[str, Any]] = []
        self.public_entries: list[SlotDraft] = []
        self.public_picks: list[int] = []

        # Outcome.
        self.slots: list[dict[str, Any]] | None = None
        self.prix_list: list[dict[str, Any]] | None = None
        self.autopost: bool | None = None
        self.validate = True

        self.page = "type"
        self.build()

    # --- plumbing ---------------------------------------------------------

    @property
    def kind(self) -> str:
        """`game_modes.kind`: the offsets between slots follow it."""
        return "race" if self.event_type in ("race", "tb") else "prix"

    @property
    def public_prix(self) -> bool:
        """The one page that picks from the rotation rather than slot by slot."""
        return self.event_type == "gpmp" and self.lobbies == "public"

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.invoker_id:
            return True
        await interaction.response.send_message("This setup belongs to whoever ran the command.", ephemeral=True)
        return False

    async def on_timeout(self) -> None:
        if self.slots is None:
            self.render_text("This event setup timed out and wrote nothing. Run /event_setup again.")
        else:
            self.render_text(
                f"{self.written()}\n\nThis event setup timed out before the posts were built. "
                "Run /event_setup again to build them; it replaces the schedule with what you pick."
            )
        try:
            await self.last_interaction.edit_original_response(view=self)
        except discord.HTTPException:
            pass

    async def on_error(self, interaction: discord.Interaction, error: Exception, item: discord.ui.Item) -> None:
        await self.fail(interaction, error, where=str(item))

    async def fail(self, interaction: discord.Interaction, error: Exception, *, where: str) -> None:
        logger.error("event_setup wizard failed on %s", where, exc_info=error)
        await send_error_alert(self.bot, where="event_setup wizard", error=error, interaction=interaction)
        await self.finish(interaction, "ERROR! Something went wrong, contact FZD staff for help!")

    async def show(self, interaction: discord.Interaction) -> None:
        """Render the current page into the one message, whichever way this
        interaction can still be answered."""
        self.last_interaction = interaction
        self.build()
        if interaction.response.is_done():
            await interaction.edit_original_response(view=self)
        else:
            await interaction.response.edit_message(view=self)

    def render_text(self, text: str) -> None:
        """A V2 message has no `content`; a closing sentence is a text block
        with nothing left to click."""
        self.clear_items()
        self.add_item(discord.ui.Container(discord.ui.TextDisplay(text)))

    async def finish(self, interaction: discord.Interaction, text: str) -> None:
        self.last_interaction = interaction
        self.render_text(text)
        if interaction.response.is_done():
            await interaction.edit_original_response(view=self)
        else:
            await interaction.response.edit_message(view=self)
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

    def button(
        self,
        label: str,
        handler: Callable[[discord.Interaction], Awaitable[None]],
        *,
        style: discord.ButtonStyle = discord.ButtonStyle.secondary,
        emoji: discord.Emoji | str | None = None,
        disabled: bool = False,
    ) -> discord.ui.Button:
        button = discord.ui.Button(label=label[:80], style=style, emoji=emoji, disabled=disabled)
        button.callback = handler
        return button

    def select(
        self,
        placeholder: str,
        options: list[discord.SelectOption],
        handler: Callable[[discord.Interaction, str], Awaitable[None]],
    ) -> discord.ui.ActionRow:
        select = discord.ui.Select(placeholder=placeholder, options=options[:SELECT_LIMIT])

        async def callback(interaction: discord.Interaction) -> None:
            await handler(interaction, select.values[0])

        select.callback = callback
        return discord.ui.ActionRow(select)

    def emoji(self, name: str) -> discord.Emoji | None:
        """The guild's custom emoji of that name; None when it has none, and a
        button or a line then simply goes without."""
        return discord.utils.get(self.guild_emojis, name=name) if name else None

    def slot_line(self, draft: SlotDraft) -> str:
        emoji = self.emoji(draft.emoji_name)
        return f"{f'{emoji} ' if emoji else ''}{hhmm(draft.starts_at)} {draft.lobby} {draft.name}"

    def header(self) -> str:
        return f"## {self.event_name}, scheduled {discord_timestamp(self.starts_at, 'long')}"

    def scoring_line(self) -> str:
        parts = [self.scoring or "not chosen"]
        if self.scoring == "time" and self.max_time_loss_cs:
            parts.append(f"maximum loss {self.max_time_loss_cs / 100:.2f} s")
        parts.append("Machine Mastery" if self.machine_mastery else f"{self.mulligans} mulligan(s)")
        return "Scoring: " + ", ".join(parts)

    def build(self) -> None:
        self.clear_items()
        box = discord.ui.Container()
        getattr(self, f"build_{self.page}")(box)
        self.add_item(box)

    # --- page: the type -----------------------------------------------------

    def build_type(self, box: discord.ui.Container) -> None:
        lines = [self.header()]
        if self.existing_slots:
            listed = "\n".join(f"{index}. {describe_slot(slot)}" for index, slot in enumerate(self.existing_slots, 1))
            lines.append(
                f"⚠️ This event already has a schedule:\n{listed}\n"
                "Continuing replaces it at Confirm; nothing changes before then. "
                "The API refuses the replacement once a result has been recorded."
            )
        lines.append("### What kind of event is this, and in which lobbies?")
        box.add_item(discord.ui.TextDisplay("\n".join(lines)))
        for event_type, label in EVENT_TYPES.items():
            box.add_item(discord.ui.TextDisplay(f"**{label}**"))
            box.add_item(
                discord.ui.ActionRow(
                    *(
                        self.button(
                            lobby.capitalize(),
                            self.type_chooser(event_type, lobby),
                            style=discord.ButtonStyle.primary
                            if (event_type, lobby) == (self.event_type, self.lobbies)
                            else discord.ButtonStyle.secondary,
                        )
                        for lobby in LOBBIES[event_type]
                    )
                )
            )
        if self.notice:
            box.add_item(discord.ui.TextDisplay(f"⚠️ {self.notice}"))
            self.notice = None
            box.add_item(
                discord.ui.ActionRow(self.button("Fix settings", self.on_fix_settings, style=discord.ButtonStyle.primary))
            )
        box.add_item(discord.ui.Separator())
        box.add_item(discord.ui.ActionRow(self.button("Cancel", self.on_cancel)))

    def type_chooser(self, event_type: EventType, lobby: str) -> Callable[[discord.Interaction], Awaitable[None]]:
        async def choose(interaction: discord.Interaction) -> None:
            self.event_type, self.lobbies = event_type, lobby
            await interaction.response.send_modal(SettingsModal(self, scoring_only=False))

        return choose

    async def on_fix_settings(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(SettingsModal(self, scoring_only=False))

    async def on_cancel(self, interaction: discord.Interaction) -> None:
        await self.finish(interaction, "Nothing changed.")

    async def on_settings(self, interaction: discord.Interaction, modal: SettingsModal) -> None:
        if modal.scoring is not None and modal.max_loss is not None:
            self.scoring = modal.scoring.value
            self.max_loss_text = modal.max_loss.value.strip()
        else:
            self.scoring = "points"
        self.machine_mastery = modal.machine_mastery.value
        self.mulligans_text = modal.mulligans.value.strip()
        if modal.first_slot is not None:
            self.first_slot_text = modal.first_slot.value.strip()

        self.notice = self.read_settings()
        if self.notice or modal.first_slot is None:
            await self.show(interaction)
        else:
            await self.call_then_show(interaction, self.begin_schedule)

    def read_settings(self) -> str | None:
        """Parse what the modal left as text. Answers the sentence for the
        first thing that does not parse, or None."""
        try:
            self.first_start = parse_hhmm(self.starts_at, self.first_slot_text)
        except ValueError:
            return "Enter the event start time as HH:MM, UTC."
        if self.machine_mastery:
            self.mulligans = 0
        elif self.mulligans_text.isdecimal():
            self.mulligans = int(self.mulligans_text)
        else:
            return "Enter the mulligans as a whole number, 0 or more."
        self.max_time_loss_cs = None
        if self.scoring == "time":
            if self.machine_mastery:
                return "Machine Mastery counts under points scoring only."
            try:
                centiseconds = round(float(self.max_loss_text) * 100)
            except ValueError:
                centiseconds = 0
            if centiseconds <= 0:
                return "Time scoring needs a maximum time loss in seconds, above zero."
            self.max_time_loss_cs = centiseconds
        return None

    # --- page: the schedule -------------------------------------------------

    # The page works on one slot at a time: `cursor` indexes `drafts`, and at
    # `len(drafts)` it is a new slot. Back and Forward move it without changing
    # anything, so an earlier slot is fixed where it stands and the slots after
    # it are kept.

    async def begin_schedule(self) -> None:
        self.page = "schedule"
        self.drafts = []
        self.cursor = 0
        if self.public_prix:
            await self.load_public_entries()
            return
        if self.event_type == "gpmp":
            leagues = await self.api.lineups("GP")
            self.private_leagues = [
                league
                for league in leagues
                # A private lobby cannot start Secret GP, the league with glitch tracks.
                if not any(track["type"] == "glitch" for track in league["tracks"])
            ]
        await self.enter_slot()

    async def load_public_entries(self) -> None:
        entries = await self.api.rotation(self.first_start, kind="prix", lookahead_minutes=PUBLIC_PRIX_LOOKAHEAD_MINUTES)
        self.public_entries = []
        for entry in entries[:PUBLIC_PRIX_SHOWN]:
            # The window containing the first slot opened earlier; the slot
            # starts when the host said, not when the game did.
            starts_at = max(parse_instant(entry["starts_at"]), self.first_start)
            self.public_entries.append(
                SlotDraft(
                    name=entry["lineup"] or entry["mode"],
                    starts_at=starts_at,
                    lobby="public",
                    mode=entry["mode_short_name"],
                    emoji_name=prix_emoji_name(entry["mode"], entry["lineup"]),
                    offered_from=starts_at,
                )
            )
        self.public_picks = [0] if self.public_entries else []
        self.drafts = self.public_entries[:1]

    async def enter_slot(self) -> None:
        """Point the page at `cursor`. An entered slot is offered again from
        the time it was first offered from; a new one from the previous slot
        plus the default gap."""
        if self.cursor < len(self.drafts):
            self.slot_time = self.drafts[self.cursor].offered_from
        elif self.drafts:
            self.slot_time = self.drafts[-1].starts_at + self.default_gap()
        else:
            self.slot_time = self.first_start
        if self.event_type == "race":
            # An entered slot keeps its mode; a new one follows the slot before it.
            nearest = self.drafts[min(self.cursor, len(self.drafts) - 1)] if self.drafts else None
            self.race_mode = nearest.mode if nearest and nearest.mode in RACE_MODES else "99"
        await self.load_candidates()

    @property
    def slot_mode(self) -> str:
        """The mode a race slot at the cursor is offered in."""
        return "TB" if self.event_type == "tb" else self.race_mode

    def neighbours(self) -> tuple[datetime | None, datetime | None]:
        """The starts of the slots either side of the cursor, where there are any."""
        before = self.drafts[self.cursor - 1].starts_at if self.cursor > 0 else None
        after = self.drafts[self.cursor + 1].starts_at if self.cursor + 1 < len(self.drafts) else None
        return before, after

    async def load_candidates(self) -> None:
        """What the slot at the cursor can be from `slot_time`, kept to what
        fits between its neighbours so that a fix cannot reorder the schedule."""
        at = self.slot_time
        offered: list[SlotDraft] = []
        if self.kind == "race":
            assert self.lobbies is not None
            mode = self.slot_mode
            offers = await self.api.lineup_offers(
                mode, lobby=self.lobbies, now=at, lookahead_minutes=RACE_OFFER_LOOKAHEAD_MINUTES
            )
            offered = [
                SlotDraft(
                    f"{RACE_MODE_NAMES[mode]}: {offer['lineup']}",
                    parse_instant(offer["starts_at"]),
                    self.lobbies,
                    mode=mode,
                    offered_from=at,
                )
                for offer in offers
            ] or await self.placeholder_minutes(mode, at)
        elif self.event_type == "cmp":
            offered = [
                SlotDraft(
                    "Classic Mini Prix",
                    at,
                    "private",
                    mode=CLASSIC_MINI_PRIX,
                    emoji_name=prix_emoji_name("Classic Mini Prix", None),
                    offered_from=at,
                )
            ]
        else:
            if self.lobbies == "mixed":
                entries = await self.api.rotation(at, kind="prix", lookahead_minutes=0)
                offered = [
                    SlotDraft(
                        entry["lineup"] or entry["mode"],
                        at,
                        "public",
                        mode=entry["mode_short_name"],
                        emoji_name=prix_emoji_name(entry["mode"], entry["lineup"]),
                        offered_from=at,
                    )
                    for entry in entries
                    if entry["mode_short_name"] != CLASSIC_MINI_PRIX
                ]
            offered.append(
                SlotDraft(
                    "Mini Prix", at, "private", mode="MP", emoji_name=prix_emoji_name("Mini Prix", None), offered_from=at
                )
            )
            offered += [
                SlotDraft(
                    league["name"],
                    at,
                    "private",
                    lineup_id=league["lineup_id"],
                    emoji_name=prix_emoji_name("Grand Prix", league["name"]),
                    offered_from=at,
                )
                for league in self.private_leagues
            ]
        before, after = self.neighbours()
        self.candidates = [
            draft
            for draft in offered
            if (before is None or draft.starts_at > before) and (after is None or draft.starts_at < after)
        ]
        self.offered_outside = bool(offered) and not self.candidates

    def build_schedule(self, box: discord.ui.Container) -> None:
        assert self.event_type is not None and self.lobbies is not None
        summary = [
            self.header(),
            f"**{EVENT_TYPES[self.event_type]}**, {self.lobbies} lobbies",
            self.scoring_line(),
        ]
        if self.machine_mastery:
            summary.append(MACHINE_MASTERY_RULE)
        first = self.drafts[0].starts_at if self.drafts else self.first_start
        if not self.starts_at <= first <= self.ends_at:
            summary.append(
                f"⚠️ The first slot, {hhmm(first)} UTC, is outside the scheduled window "
                f"({hhmm(self.starts_at)}–{hhmm(self.ends_at)} UTC). The calendar keeps the scheduled time."
            )
        if self.notice:
            summary.append(f"⚠️ {self.notice}")
            self.notice = None
        box.add_item(
            discord.ui.Section(discord.ui.TextDisplay("\n".join(summary)), accessory=self.button("Settings", self.on_scoring, emoji="⚙️"))
        )
        box.add_item(discord.ui.Separator())

        if self.public_prix:
            listed = "\n".join(f"{index}. {self.slot_line(draft)}" for index, draft in enumerate(self.drafts, 1))
            box.add_item(discord.ui.TextDisplay(f"{SCHEDULE_HEADING}\n{listed or 'No slots yet.'}"))
            box.add_item(discord.ui.Separator())
            self.build_public_prix(box)
        else:
            lines = [
                f"{'▶ ' if index == self.cursor else ''}{index + 1}. {self.slot_line(draft)}"
                for index, draft in enumerate(self.drafts)
            ]
            if self.cursor == len(self.drafts):
                lines.append(f"▶ {len(self.drafts) + 1}. (empty)")
            box.add_item(discord.ui.TextDisplay("\n".join([SCHEDULE_HEADING, *lines])))
            box.add_item(discord.ui.Separator())
            self.build_slot(box)

        box.add_item(discord.ui.Separator())
        box.add_item(
            discord.ui.ActionRow(
                self.button("Start over", self.on_start_over, style=discord.ButtonStyle.danger),
                self.button("Confirm", self.on_confirm, style=discord.ButtonStyle.success),
            )
        )

    def build_public_prix(self, box: discord.ui.Container) -> None:
        if not self.public_entries:
            box.add_item(
                discord.ui.TextDisplay(f"The game runs no prix from {hhmm(self.first_start)} UTC. Choose another first slot time.")
            )
        else:
            box.add_item(discord.ui.TextDisplay("Pick the prixs you want in your schedule"))
            buttons = [
                self.button(
                    f"{hhmm(draft.starts_at)} UTC {draft.name}",
                    self.public_toggle(index),
                    style=discord.ButtonStyle.success if index in self.public_picks else discord.ButtonStyle.secondary,
                    emoji=self.emoji(draft.emoji_name),
                )
                for index, draft in enumerate(self.public_entries)
            ]
            for start in range(0, len(buttons), BUTTONS_PER_ROW):
                box.add_item(discord.ui.ActionRow(*buttons[start : start + BUTTONS_PER_ROW]))
        box.add_item(discord.ui.ActionRow(self.button("Change start time", self.on_public_first_time, style=discord.ButtonStyle.primary)))

    def public_toggle(self, index: int) -> Callable[[discord.Interaction], Awaitable[None]]:
        async def toggle(interaction: discord.Interaction) -> None:
            self.public_picks = sorted(set(self.public_picks) ^ {index})
            self.drafts = [self.public_entries[pick] for pick in self.public_picks]
            await self.show(interaction)

        return toggle

    async def on_public_first_time(self, interaction: discord.Interaction) -> None:
        async def set_time(modal_interaction: discord.Interaction, instant: datetime) -> None:
            self.first_start = instant
            self.first_slot_text = hhmm(instant)
            await self.call_then_show(modal_interaction, self.load_public_entries)

        await interaction.response.send_modal(ExactTimeModal(self, self.first_start, set_time))

    def build_slot(self, box: discord.ui.Container) -> None:
        editing = self.drafts[self.cursor] if self.cursor < len(self.drafts) else None
        number = self.cursor + 1
        at = self.slot_time
        heading = f"### Editing: slot {number}" if editing else f"### Pick what you want to run in slot {number}"
        when = f"{hhmm(at)} UTC ({discord_timestamp(at, 'short')} your time)"
        # A race offer carries its own minute, so a race slot starts at the
        # pick, not at the time the offers were read from.
        starts = f"The offers here start at {when}." if self.kind == "race" else f"The slot is set to start at {when}."
        line = f"You can pick from the available selection here. {starts}"
        notes = []
        if self.offered_outside:
            before, after = self.neighbours()
            window = " and ".join(
                part
                for part in (
                    f"after slot {number - 1} ({hhmm(before)} UTC)" if before else "",
                    f"before slot {number + 1} ({hhmm(after)} UTC)" if after else "",
                )
                if part
            )
            notes.append(f"Slot {number} has to start {window}. Choose another time.")
        elif self.kind == "race" and not self.candidates:
            notes.append(
                f"The game offers no {RACE_MODE_NAMES[self.slot_mode]} race in a {self.lobbies} lobby "
                f"from {hhmm(at)} UTC. Choose another time."
            )
        elif self.lobbies == "mixed" and not any(candidate.lobby == "public" for candidate in self.candidates):
            notes.append(f"The game runs no public prix at {hhmm(at)} UTC; the private ones are still offered.")
        if editing:
            notes.append("Pick to replace it and move on, or Forward to keep it.")
        box.add_item(discord.ui.TextDisplay("\n".join([heading, line, *notes])))

        if self.event_type == "race":
            box.add_item(discord.ui.TextDisplay("**Choose the next mode**"))
            box.add_item(
                discord.ui.ActionRow(
                    *(
                        self.button(
                            label,
                            self.mode_chooser(mode),
                            style=discord.ButtonStyle.primary if mode == self.race_mode else discord.ButtonStyle.secondary,
                        )
                        for mode, label in RACE_MODES.items()
                    )
                )
            )

        if self.cursor > 0:
            previous = self.drafts[self.cursor - 1].starts_at
            offsets = RACE_OFFSETS if self.kind == "race" else PRIX_OFFSETS
            box.add_item(
                self.select(
                    "Time, from the previous slot",
                    [
                        discord.SelectOption(
                            label=f"{hhmm(later)} UTC (+{offset} min)", value=later.isoformat(), default=later == at
                        )
                        for offset in offsets
                        for later in [previous + timedelta(minutes=offset)]
                    ],
                    self.on_slot_time,
                )
            )

        if self.event_type == "cmp":
            if self.candidates:
                candidate = self.candidates[0]
                box.add_item(
                    discord.ui.ActionRow(
                        self.button(
                            self.candidate_label(candidate, editing),
                            self.on_pick_classic,
                            style=discord.ButtonStyle.primary,
                            emoji=self.emoji(candidate.emoji_name),
                        )
                    )
                )
        elif self.candidates:
            box.add_item(
                self.select(
                    "Choose your lineup for this slot",
                    [
                        discord.SelectOption(
                            label=self.candidate_label(candidate, editing),
                            value=str(index),
                            emoji=self.emoji(candidate.emoji_name),
                        )
                        for index, candidate in enumerate(self.candidates)
                    ],
                    self.on_pick,
                )
            )

        box.add_item(
            discord.ui.ActionRow(
                self.button("◀ Back", self.mover(-1), disabled=self.cursor == 0),
                self.button("Forward ▶", self.mover(1), disabled=editing is None),
                self.button("Exact time", self.on_exact_time),
                self.button("Remove this slot", self.on_remove, style=discord.ButtonStyle.danger, disabled=editing is None),
            )
        )

    def candidate_label(self, candidate: SlotDraft, editing: SlotDraft | None) -> str:
        label = f"{hhmm(candidate.starts_at)} {candidate.name}"
        if self.lobbies == "mixed":
            label = f"{candidate.lobby.capitalize()}: {label}"
        if editing and candidate.same_pick(editing):
            label += " (current)"
        return label[:100]

    def mode_chooser(self, mode: str) -> Callable[[discord.Interaction], Awaitable[None]]:
        async def choose(interaction: discord.Interaction) -> None:
            self.race_mode = mode
            await self.call_then_show(interaction, self.load_candidates)

        return choose

    async def placeholder_minutes(self, mode: str, at: datetime) -> list[SlotDraft]:
        """A mode with no stored lineups is scheduled on its placeholder: an
        entry naming the mode and no lineup, which the API resolves to it. A
        private lobby starts one at any minute; a public one only while the
        rotation runs the mode, since the schedule write refuses a public slot
        the game is not running."""
        minutes = [at + timedelta(minutes=offset) for offset in range(RACE_OFFER_LOOKAHEAD_MINUTES + 1)]
        if self.lobbies == "public":
            entries = await self.api.rotation(at, kind="race", lookahead_minutes=RACE_OFFER_LOOKAHEAD_MINUTES)
            windows = [
                (parse_instant(entry["starts_at"]), parse_instant(entry["ends_at"]))
                for entry in entries
                if entry["mode_short_name"] == mode
            ]
            minutes = [minute for minute in minutes if any(opens <= minute < closes for opens, closes in windows)]
        assert self.lobbies is not None
        return [
            SlotDraft(f"{RACE_MODE_NAMES[mode]}: Placeholder", minute, self.lobbies, mode=mode, offered_from=at)
            for minute in minutes
        ]

    def default_gap(self) -> timedelta:
        return timedelta(minutes=RACE_GAP if self.kind == "race" else PRIX_GAP)

    async def put(self, interaction: discord.Interaction, draft: SlotDraft) -> None:
        """Make `draft` the slot at the cursor and move on to the next one."""
        if self.cursor < len(self.drafts):
            self.drafts[self.cursor] = draft
        else:
            self.drafts.append(draft)
        self.cursor += 1
        await self.call_then_show(interaction, self.enter_slot)

    async def on_pick(self, interaction: discord.Interaction, value: str) -> None:
        await self.put(interaction, self.candidates[int(value)])

    async def on_pick_classic(self, interaction: discord.Interaction) -> None:
        await self.put(interaction, self.candidates[0])

    def mover(self, step: int) -> Callable[[discord.Interaction], Awaitable[None]]:
        async def move(interaction: discord.Interaction) -> None:
            self.cursor += step
            await self.call_then_show(interaction, self.enter_slot)

        return move

    async def on_remove(self, interaction: discord.Interaction) -> None:
        """Drop the slot at the cursor; the cursor is then on the one after it."""
        del self.drafts[self.cursor]
        await self.call_then_show(interaction, self.enter_slot)

    async def on_slot_time(self, interaction: discord.Interaction, value: str) -> None:
        self.slot_time = parse_instant(value)
        await self.call_then_show(interaction, self.load_candidates)

    async def on_exact_time(self, interaction: discord.Interaction) -> None:
        async def set_time(modal_interaction: discord.Interaction, instant: datetime) -> None:
            self.slot_time = instant
            await self.call_then_show(modal_interaction, self.load_candidates)

        await interaction.response.send_modal(ExactTimeModal(self, self.slot_time, set_time))

    async def on_scoring(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(SettingsModal(self, scoring_only=True))

    async def on_start_over(self, interaction: discord.Interaction) -> None:
        """Drop every slot entered so far and ask the type again."""
        self.drafts = []
        self.cursor = 0
        self.page = "type"
        await self.show(interaction)

    async def on_confirm(self, interaction: discord.Interaction) -> None:
        if not self.drafts:
            await interaction.response.send_message("Add at least one slot first.", ephemeral=True)
            return
        assert self.scoring is not None
        await interaction.response.defer()
        try:
            await self.api.set_scoring(
                self.event_id,
                scoring_method=self.scoring,
                num_mulligans=self.mulligans,
                max_time_loss_cs=self.max_time_loss_cs,
                machine_counts_once=self.machine_mastery,
            )
        except FzdApiError as error:
            await self.finish(interaction, f"Nothing was written. {error}")
            return
        try:
            slots = await self.api.replace_schedule(self.event_id, [draft.entry() for draft in self.drafts])
        except FzdApiError as error:
            await self.finish(
                interaction,
                f"The scoring was saved, but the schedule was not. {error}\nRun /event_setup again; both writes replace what is there.",
            )
            return
        self.slots = slots
        # `build_gp_posts` takes the score channel from `events`, so an event
        # missing there has no posts to build.
        if self.event_name not in {event["fullname"] for event in events}:
            await self.finish(
                interaction,
                f"{self.written()}\n\nNo posts were built: HostPost has no score channel for {self.event_name}.",
            )
            return
        # Pro Tracks and Team Battle slots have no post template.
        try:
            self.prix_list = prix_list_from_slots(slots)
        except ValueError as error:
            await self.finish(interaction, f"{self.written()}\n\nNo posts were built. {error}.")
            return
        self.page = "posting"
        await self.show(interaction)

    def written(self) -> str:
        assert self.slots is not None
        listed = "\n".join(f"{index}. {describe_slot(slot)}" for index, slot in enumerate(self.slots, 1))
        return f"{self.header()}\n{self.scoring_line()}\n### Schedule written\n{listed}"

    # --- page: posting ------------------------------------------------------

    def build_posting(self, box: discord.ui.Container) -> None:
        box.add_item(discord.ui.TextDisplay(self.written()))
        box.add_item(discord.ui.Separator())
        box.add_item(
            discord.ui.TextDisplay(
                "### Posts\n"
                "Should HostPost push the announcement, the 10-minute warning and each prix's GO post itself? "
                "Prix winners still wait for /post_prix_winner. Final results either wait for /validate_results "
                "or are posted as soon as the scoreboard closes.\n"
                "Either way, the drafts are posted in this channel with a text file."
            )
        )
        box.add_item(
            discord.ui.ActionRow(
                self.button("Autopost, I'll validate results", self.posting_chooser(True, True), style=discord.ButtonStyle.success),
                self.button("Autopost, skip validation", self.posting_chooser(True, False), style=discord.ButtonStyle.danger),
                self.button("I'll post myself", self.posting_chooser(False, True)),
            )
        )

    def posting_chooser(self, autopost: bool, validate: bool) -> Callable[[discord.Interaction], Awaitable[None]]:
        async def choose(interaction: discord.Interaction) -> None:
            self.autopost = autopost
            self.validate = validate
            await self.finish(interaction, f"{self.written()}\n\nBuilding the posts…")

        return choose
