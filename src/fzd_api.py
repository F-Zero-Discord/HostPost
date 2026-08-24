"""
Client for the FZD API (`api.fzd.gg`).

The API holds the database credentials; this bot asks it questions instead of
running SQL. Task 15-04 is the first command to go this way — `/update_host_for_event`
and `/remove_host_from_event` — and `src/fzd_db.py` still serves the other
eleven. The two coexist deliberately, and every command that moves is one fewer
reason for a Raspberry Pi in someone's house to hold a MySQL password.

Two things this module deliberately does not do:

- **No fallback to a direct connection.** If the API is unreachable the command
  fails, visibly, and says so. A fallback would put a second copy of the
  identity policy back in this bot, which is the thing the port removes.
- **No knowledge of `users.id`.** The API resolves a Discord account to a row
  itself and returns nothing about it. That is why this is a port and not an
  "ensure the user exists" endpoint.
"""

import asyncio
import logging
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
        updating its `.env` keeps all thirteen commands loaded and fails only
        these two, with an explanation. Making them required would take the whole
        bot down over a staff command — see Plan 15's "if lurch's deploy slips".
        """
        return bool(self._base_url and self._api_key)

    async def close(self) -> None:
        if self._session is not None and not self._session.closed:
            await self._session.close()
        self._session = None

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

    async def _request(self, method: str, path: str, json: dict[str, Any] | None = None) -> dict[str, Any]:
        if not self.configured:
            raise FzdApiNotConfigured("FZD_API_BASE_URL and FZD_API_KEY are not set in this bot's .env, so there is no API to call.")

        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(timeout=self._timeout)

        url = f"{self._base_url}{path}"
        try:
            async with self._session.request(method, url, json=json, headers={API_KEY_HEADER: self._api_key}) as response:
                body = await self._read_body(response)
                if response.status >= 400:
                    raise FzdApiError(self._message_for(response.status, body))
                return body

        except asyncio.TimeoutError as error:
            logger.error("[API] %s %s timed out", method, url)
            raise FzdApiError("The FZD API did not answer in time. Nothing was changed.") from error

        except aiohttp.ClientError as error:
            logger.error("[API] %s %s failed: %s", method, url, error)
            raise FzdApiError(f"Could not reach the FZD API ({error}). Nothing was changed.") from error

    @staticmethod
    async def _read_body(response: aiohttp.ClientResponse) -> dict[str, Any]:
        """Decode the response, tolerating one that is not JSON.

        A 502 from nginx is HTML, and an error path that raises while explaining
        an error tells the host nothing.
        """
        try:
            body = await response.json(content_type=None)
        except (ValueError, aiohttp.ContentTypeError):
            return {}
        return body if isinstance(body, dict) else {}

    @staticmethod
    def _message_for(status: int, body: dict[str, Any]) -> str:
        """Turn a failure into something worth reading in Discord.

        The API answers errors as RFC 9457 problem documents, so `detail` is
        already a sentence. 422 is the exception: FastAPI's validation errors are
        a list of field objects, which is a bug report rather than a message.
        """
        detail = body.get("detail")

        if status == 401:
            return "The FZD API rejected this bot's key. Its `FZD_API_KEY` needs to match what the API has configured."
        if status == 403:
            return "The FZD API refused this request."
        if status == 404:
            return f"The FZD API does not know that event. ({detail or 'not found'})"
        if status == 422:
            return f"The FZD API rejected the request as invalid: {detail if isinstance(detail, str) else body or 'no detail given'}"
        if status >= 500:
            return f"The FZD API failed ({status}). Nothing was changed; try again, and tell a dev if it keeps happening."
        return f"The FZD API answered {status}. ({detail or 'no detail given'})"
