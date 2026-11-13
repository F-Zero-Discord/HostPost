"""
Client for the FZD API (`api.fzd.gg`).

The API holds the database credentials; this bot asks it questions instead of
running SQL.
"""

import logging
from datetime import datetime
from typing import Any, Literal

import aiohttp

from src.api_types import (
    CatalogueLineupResponse,
    EventDetailResponse,
    EventHostResponse,
    EventResponse,
    EventScoringRequest,
    EventScoringResponse,
    HostAssignmentRequest,
    LineupOfferResponse,
    ModeKind,
    RotationEntryResponse,
    ScoreboardResponse,
    SlotEntryRequest,
    SlotResponse,
)

logger = logging.getLogger(__name__)

API_KEY_HEADER = "X-API-Key"

TAG_MAX_LENGTH = 10
"""`users.tag` is `varchar(10)`, matching F-Zero 99's in-game name limit. The API
rejects a longer one rather than truncating it, so `assign_host` trims."""


class FzdApiError(Exception):
    """Something went wrong talking to the API.

    Carries a message written for a Discord reply, because every caller's
    failure path is telling a member of Circuit Crew what happened.
    """


class FzdApiNotConfiguredError(FzdApiError):
    """No base URL or no key in `.env`.

    A distinct type so the caller can say "not configured" rather than "could not
    reach", which are different problems with different fixes.
    """


class FzdApi:
    """Calls the FZD API on behalf of the bot.

    One instance, built in `main.HostBot.setup_hook` and closed in
    `HostBot.close`. The `aiohttp` session is created on first use rather than in
    `__init__` so that constructing this needs no running event loop.

    Every method answers the decoded JSON body as the API sent it, typed as the
    `TypedDict` in `api_types` of the schema it reads. Nothing validates the
    body against that type.
    """

    def __init__(self, base_url: str, api_key: str, timeout_seconds: float = 10.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._timeout = aiohttp.ClientTimeout(total=timeout_seconds)
        self._session: aiohttp.ClientSession | None = None

    @property
    def configured(self) -> bool:
        """Whether there is anything to call.

        Both settings default to empty, so a bot that pulls this change without
        updating its `.env` keeps every command loaded and fails only the ones
        that call the API, with an explanation.
        """
        return bool(self._base_url and self._api_key)

    async def close(self) -> None:
        if self._session is not None and not self._session.closed:
            await self._session.close()
        self._session = None

    # --- scheduled events -------------------------------------------------

    async def calendar(self, days: int = 7) -> list[EventResponse]:
        """The scheduled events not yet over, earliest first."""
        return await self._request("GET", "/v1/events", params={"days": days})

    async def event_detail(self, scheduled_event_id: int) -> EventDetailResponse:
        return await self._request("GET", f"/v1/events/{scheduled_event_id}")

    async def schedule(self, scheduled_event_id: int) -> list[SlotResponse]:
        return await self._request("GET", f"/v1/events/{scheduled_event_id}/schedule")

    async def scoreboard(self, scheduled_event_id: int) -> ScoreboardResponse:
        """The event's board as the API ranks it: multipliers applied, mulligans
        dropped, rows best first. Public on the API; the key is sent anyway."""
        return await self._request("GET", f"/v1/events/{scheduled_event_id}/scoreboard")

    async def replace_schedule(self, scheduled_event_id: int, entries: list[SlotEntryRequest]) -> list[SlotResponse]:
        """Make `entries`, in order, the whole schedule. The API refuses the
        whole write if a result already exists on the event."""
        return await self._request("PUT", f"/v1/events/{scheduled_event_id}/schedule", json=entries)

    async def set_scoring(
        self,
        scheduled_event_id: int,
        *,
        scoring_method: Literal["points", "time"],
        num_mulligans: int,
        max_time_loss_cs: int | None,
        machine_counts_once: bool,
    ) -> EventScoringResponse:
        body = EventScoringRequest(
            scoring_method=scoring_method,
            num_mulligans=num_mulligans,
            max_time_loss_cs=max_time_loss_cs,
            machine_counts_once=machine_counts_once,
        )
        return await self._request("PUT", f"/v1/events/{scheduled_event_id}/scoring", json=body)

    async def assign_host(
        self,
        scheduled_event_id: int,
        *,
        discord_user_id: int,
        discord_user_name: str,
        tag: str,
    ) -> EventHostResponse:
        """Make a Discord account the host of a scheduled event. The API resolves
        the account to a row in `users` itself; this bot never sees the id.
        `tag` is used only if the account has no row yet."""
        body = HostAssignmentRequest(
            discord_user_id=str(discord_user_id),
            discord_user_name=discord_user_name,
            tag=tag[:TAG_MAX_LENGTH],
        )
        return await self._request("PUT", f"/v1/events/{scheduled_event_id}/host", json=body)

    async def remove_host(self, scheduled_event_id: int) -> EventHostResponse:
        """Leave a scheduled event with no host. Resolves nobody."""
        return await self._request("DELETE", f"/v1/events/{scheduled_event_id}/host")

    # --- what the game runs -----------------------------------------------

    async def rotation(self, now: datetime, *, kind: ModeKind, lookahead_minutes: int) -> list[RotationEntryResponse]:
        """What the public game offers at `now` and within the lookahead, one
        entry per window."""
        return await self._request(
            "GET",
            "/v1/ingame/rotation",
            params={"now": now.isoformat(), "kind": kind, "lookahead_minutes": lookahead_minutes},
        )

    async def lineup_offers(
        self, mode: str, *, lobby: str, now: datetime, lookahead_minutes: int
    ) -> list[LineupOfferResponse]:
        """What one mode offers one kind of lobby, minute by minute from `now`."""
        return await self._request(
            "GET",
            "/v1/ingame/lineups",
            params={"mode": mode, "lobby": lobby, "now": now.isoformat(), "lookahead_minutes": lookahead_minutes},
        )

    async def lineups(self, mode: str) -> list[CatalogueLineupResponse]:
        """The catalogue of lineups a slot can name, for one mode."""
        return await self._request("GET", "/v1/lineups", params={"mode": mode})

    # --- transport --------------------------------------------------------

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, str | int] | None = None,
        json: Any = None,
    ) -> Any:
        if not self.configured:
            raise FzdApiNotConfiguredError(
                "FZD_API_BASE_URL and FZD_API_KEY are not set in this bot's .env, so there is no API to call."
            )

        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(timeout=self._timeout)

        url = f"{self._base_url}{path}"
        try:
            async with self._session.request(
                method,
                url,
                params=params,
                json=json,
                headers={API_KEY_HEADER: self._api_key},
            ) as response:
                body = await self._read_body(response)
                if response.status >= 400:
                    raise FzdApiError(self._message_for(response.status, body))
                return body

        except TimeoutError as error:
            logger.error("[API] %s %s timed out", method, url)
            raise FzdApiError("The FZD API did not answer in time. Nothing was changed.") from error

        except aiohttp.ClientError as error:
            logger.error("[API] %s %s failed: %s", method, url, error)
            raise FzdApiError(f"Could not reach the FZD API ({error}). Nothing was changed.") from error

    @staticmethod
    async def _read_body(response: aiohttp.ClientResponse) -> Any:
        """Decode the response, tolerating one that is not JSON.

        A 502 from nginx is HTML, and an error path that raises while explaining
        an error tells the host nothing.
        """
        try:
            body = await response.json(content_type=None)
        except (ValueError, aiohttp.ContentTypeError):
            return {}
        return body if isinstance(body, (dict, list)) else {}

    @staticmethod
    def _message_for(status: int, body: Any) -> str:
        """Turn a failure into something worth reading in Discord.

        The API answers errors as RFC 9457 problem documents, so `detail` is
        already a sentence. 422 is the exception: FastAPI's validation errors are
        a list of field objects, which is a bug report rather than a message.
        """
        detail = body.get("detail") if isinstance(body, dict) else None

        if status == 401:
            return "The FZD API rejected this bot's key. Its `FZD_API_KEY` needs to match what the API has configured."
        if status == 403:
            return "The FZD API refused this request."
        if status == 404:
            return f"The FZD API does not know that event. ({detail or 'not found'})"
        if status == 409:
            return f"The FZD API refused to change this: {detail or 'a result already exists on the event'}"
        if status == 422:
            return f"The FZD API rejected the request as invalid: {detail if isinstance(detail, str) else body or 'no detail given'}"
        if status >= 500:
            return (
                f"The FZD API failed ({status}). Nothing was changed; try again, and tell a dev if it keeps happening."
            )
        return f"The FZD API answered {status}. ({detail or 'no detail given'})"
