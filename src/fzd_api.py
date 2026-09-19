"""
Client for the FZD API (`api.fzd.gg`).

The API holds the database credentials; this bot asks it questions instead of
running SQL.
"""

import logging
from datetime import datetime
from typing import Any

import aiohttp

logger = logging.getLogger(__name__)

API_KEY_HEADER = "X-API-Key"


class FzdApiError(Exception):
    """Something went wrong talking to the API.

    Carries a message written for a Discord reply, because every caller's
    failure path is telling a member of Circuit Crew what happened.
    """


class FzdApiNotConfigured(FzdApiError):
    """No base URL or no key in `.env`.

    A distinct type so the caller can say "not configured" rather than "could not
    reach", which are different problems with different fixes.
    """


class FzdApi:
    """Calls the FZD API on behalf of the bot.

    One instance, built in `main.HostBot.setup_hook` and closed in
    `HostBot.close`. The `aiohttp` session is created on first use rather than in
    `__init__` so that constructing this needs no running event loop.

    Every method answers the decoded JSON body as the API sent it: dicts and
    lists of dicts, datetimes as ISO 8601 strings. Callers parse what they use.
    """

    def __init__(
        self, base_url: str, api_key: str, timeout_seconds: float = 10.0
    ) -> None:
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

    async def calendar(self, days: int = 14) -> list[dict[str, Any]]:
        """The scheduled events not yet over, earliest first."""
        return await self._request("GET", "/v1/events", params={"days": days})

    async def event_detail(self, scheduled_event_id: int) -> dict[str, Any]:
        """One scheduled event with its slots and scoring configuration."""
        return await self._request("GET", f"/v1/events/{scheduled_event_id}")

    async def schedule(self, scheduled_event_id: int) -> list[dict[str, Any]]:
        """The slots of a scheduled event, in position order."""
        return await self._request("GET", f"/v1/events/{scheduled_event_id}/schedule")

    async def replace_schedule(
        self, scheduled_event_id: int, entries: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Make `entries`, in order, the whole schedule. Answers the schedule as
        stored, with each slot's lineup resolved by the API.

        Each entry is `{mode | lineup_id, starts_at, lobby}`; the API refuses
        the whole write if a result already exists on the event.
        """
        return await self._request(
            "PUT", f"/v1/events/{scheduled_event_id}/schedule", json=entries
        )

    async def set_scoring(
        self,
        scheduled_event_id: int,
        *,
        scoring_method: str,
        num_mulligans: int,
        max_time_loss_cs: int | None,
    ) -> dict[str, Any]:
        """Set how the event is scored. `max_time_loss_cs` is required under
        `time` and must be None under `points`; the API refuses a mismatch."""
        return await self._request(
            "PUT",
            f"/v1/events/{scheduled_event_id}/scoring",
            json={
                "scoring_method": scoring_method,
                "num_mulligans": num_mulligans,
                "max_time_loss_cs": max_time_loss_cs,
            },
        )

    async def assign_host(
        self,
        scheduled_event_id: int,
        *,
        discord_user_id: int,
        discord_user_name: str,
        tag: str | None = None,
    ) -> dict[str, Any]:
        """Make a Discord account the host of a scheduled event.

        `discord_user_id` is the snowflake and it is sent as a string: it exceeds
        2^53, so a JSON number is rounded by anything reading this API from a
        browser.

        `tag` is only used if the account has no row yet, and the API rejects one
        over ten characters rather than truncating it — so the caller decides
        what to cut.
        """
        return await self._request(
            "PUT",
            f"/v1/events/{scheduled_event_id}/host",
            json={
                "discord_user_id": str(discord_user_id),
                "discord_user_name": discord_user_name,
                "tag": tag,
            },
        )

    async def remove_host(self, scheduled_event_id: int) -> dict[str, Any]:
        """Leave a scheduled event with no host. Resolves nobody."""
        return await self._request("DELETE", f"/v1/events/{scheduled_event_id}/host")

    # --- what the game runs -----------------------------------------------

    async def rotation(
        self, now: datetime, *, kind: str, lookahead_minutes: int
    ) -> list[dict[str, Any]]:
        """What the public game offers at `now` and within the lookahead, one
        entry per window, for modes of `kind` (`prix` or `race`)."""
        return await self._request(
            "GET",
            "/v1/ingame/rotation",
            params={
                "now": now.isoformat(),
                "kind": kind,
                "lookahead_minutes": lookahead_minutes,
            },
        )

    async def lineup_offers(
        self, mode: str, *, lobby: str, now: datetime, lookahead_minutes: int
    ) -> list[dict[str, Any]]:
        """What one mode offers one kind of lobby, minute by minute from `now`."""
        return await self._request(
            "GET",
            "/v1/ingame/lineups",
            params={
                "mode": mode,
                "lobby": lobby,
                "now": now.isoformat(),
                "lookahead_minutes": lookahead_minutes,
            },
        )

    async def lineups(self, mode: str) -> list[dict[str, Any]]:
        """The catalogue of lineups a slot can name, for one mode."""
        return await self._request("GET", "/v1/lineups", params={"mode": mode})

    # --- transport --------------------------------------------------------

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: Any = None,
    ) -> Any:
        if not self.configured:
            raise FzdApiNotConfigured(
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
            raise FzdApiError(
                "The FZD API did not answer in time. Nothing was changed."
            ) from error

        except aiohttp.ClientError as error:
            logger.error("[API] %s %s failed: %s", method, url, error)
            raise FzdApiError(
                f"Could not reach the FZD API ({error}). Nothing was changed."
            ) from error

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
            return f"The FZD API failed ({status}). Nothing was changed; try again, and tell a dev if it keeps happening."
        return f"The FZD API answered {status}. ({detail or 'no detail given'})"
