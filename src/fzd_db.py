"""
Contains database commands for accessing event information. Basic functionality
taken from Nightmare's fzd_bot.
"""

import logging
from collections.abc import Sequence
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any, Literal, TypedDict

import aiomysql

from src.settings import get_settings

logger = logging.getLogger(__name__)


async def _safe_rollback(conn: aiomysql.Connection | None, source: str = "unknown") -> None:
    """Rollback only when possible; never mask the original exception."""
    if not conn or getattr(conn, "closed", True):
        return
    try:
        await conn.rollback()
    except aiomysql.Error as rollback_error:
        logger.warning(f"[DB] Rollback skipped ({source}): {rollback_error}")


async def init_db_pool() -> aiomysql.Pool:
    settings = get_settings()
    pool = await aiomysql.create_pool(
        minsize=1,
        maxsize=16,
        user=settings.db_user,
        password=settings.db_password,
        host=settings.db_host,
        db=settings.db_name,
        port=settings.db_port,
        autocommit=False,
    )
    print("✅ Database pool created!")
    return pool


async def get_connection_from_pool(connection_pool: aiomysql.Pool):
    """
    Context manager that safely checks out a connection from the pool,
    and returns it afterward (even if errors happen).
    Automatically rebuilds the pool if it breaks.
    """

    conn = None
    if connection_pool is None:
        raise RuntimeError("Database pool is not initialized")

    try:
        conn = await connection_pool.acquire()
        await conn.ping(reconnect=True)
        logger.debug("[DB] Got connection from pool: id=%s", id(conn))
    except Exception as e:
        logger.warning(f"[DB CONNECTION] Failed to get healthy pooled connection: {e}")
        if conn:
            conn.close()
            connection_pool.release(conn)
        raise
    return conn


@asynccontextmanager
async def get_db_connection(connection_pool: aiomysql.Pool):
    """
    Context manager for safely acquiring and releasing a DB connection.
    Rolls back on error and retries once if connection is lost.
    """
    conn = None
    try:
        conn = await get_connection_from_pool(connection_pool)
        # Test connection quickly (cheap ping)
        # conn.ping(reconnect=True, attempts=1, delay=0)

        yield conn  # hand off to the calling code

    except aiomysql.Error as e:
        await _safe_rollback(conn, source="get_db_connection")
        logger.error("[DB ERROR] %s", e)
        raise  # propagate error up to cog

    finally:
        if conn:
            connection_pool.release(conn)  # release_connection(conn)


async def execute_query(
    conn: aiomysql.Connection,
    query: str,
    params: Sequence[object] | None = None,
    fetch: Literal["all", "one"] | None = "all",
    is_proc: bool = False,
) -> Any:
    """Commits, or rolls back and re-raises. The rows are whatever the SQL
    selects; the caller's return type is the claim about their shape."""
    async with conn.cursor(aiomysql.DictCursor) as cursor:
        try:
            if is_proc:
                await cursor.callproc(query, params or ())
            else:
                await cursor.execute(query, params or ())

            if fetch == "all":
                result = await cursor.fetchall()
            elif fetch == "one":
                result = await cursor.fetchone()
            else:
                result = None

            await conn.commit()
            return result

        except Exception as e:
            await conn.rollback()
            logger.error(f"[DB QUERY ERROR]: {e}\nQuery: {query}\nParams: {params}")
            raise


############################################
# ^ Above are Nightmare-Bot functions
############################################
#
# `get_user_id` and `add_new_user` used to live here, copied from fzd-bot. They
# were HostPost's only write path against `users`, and task 15-04 deleted them:
# the FZD API resolves a Discord account to a row now, and this bot never learns
# the `users.id` that comes back. See `src/fzd_api.py`.
#
# They also carried the bug this plan exists to fix. `get_user_id` matched on a
# column named `discord_user_id` that held a *username*, so a host who renamed
# their Discord account missed and got a second row. Nothing here should reach
# for `users` by name again.


############################################
# v Below are functions specific to HostPost
############################################


async def get_scheduled_event_id(db: aiomysql.Connection, scheduled_event_name: str) -> int:
    sql_scheduled_event_id = """SELECT id
                                FROM events_scheduled
                                WHERE display_name = %s
                            """
    params = (scheduled_event_name,)
    event_id = await execute_query(db, sql_scheduled_event_id, params=params, fetch="one")
    return event_id["id"]


class ScoreRow(TypedDict):
    name: str
    """`users.tag`."""
    user_id: str
    discord_name: str
    """`users.discord_user_name`, what `discord.utils.get(members, name=...)` matches."""
    score: str
    """The summed points, cast to a string by the query."""


async def get_event_scores(db: aiomysql.Connection, scheduled_event_id: int) -> list[ScoreRow]:
    """Best first."""
    sql_event_scores = """SELECT users.tag AS name,
                                CAST(r.user_id AS CHAR) AS user_id,
                                users.discord_user_name AS discord_name,
                                CAST(SUM(r.score) AS CHAR) AS score
                            FROM event_result_points r
                            INNER JOIN users ON r.user_id = users.id
                            WHERE scheduled_event_id = %s
                            GROUP BY r.user_id
                            ORDER BY SUM(r.score) DESC
                        """
    params = (scheduled_event_id,)
    return await execute_query(db, sql_event_scores, params=params, is_proc=False)


class HostingScheduleRow(TypedDict):
    event_id: str
    event_name: str
    start: datetime
    """Naive, in UTC."""
    host: str | None
    """The host's `users.tag`, or None with no host."""
    active: int
    """1 if scheduled, 0 if cancelled."""


async def get_hosting_schedule(db: aiomysql.Connection) -> list[HostingScheduleRow]:
    """Every scheduled event not yet over, earliest first."""
    sql_host_schedule = """SELECT CAST(e.id AS CHAR) AS event_id,
                            events.name AS event_name,
                            e.utc_start_dt AS start,
                            users.tag AS host,
                            CAST(e.active AS SIGNED) AS active

                            FROM events_scheduled e
                            LEFT JOIN users ON e.host_id = users.id
                            INNER JOIN events ON e.event_id = events.id
                            WHERE e.utc_end_dt >= CURRENT_TIMESTAMP
                            ORDER BY e.utc_start_dt
                        """
    params = ()
    return await execute_query(db, sql_host_schedule, params=params, fetch="all", is_proc=False)


# `update_host_in_db` and `remove_host_from_event_db` were here. Task 15-04
# replaced them with PUT and DELETE /v1/events/{id}/host: writing
# `events_scheduled.host_id` needs a `users.id`, and holding one is exactly what
# this bot stopped doing.


async def get_event_host_id(db: aiomysql.Connection, scheduled_event_id: int) -> int | None:
    """Returns user id of a host if one assigned to scheduled event.
    Otherwise returns None.
    """
    sql_get_host_id = """
                        SELECT host_id
                        FROM events_scheduled
                        WHERE id = %s
                    """
    params = (scheduled_event_id,)
    host_id = await execute_query(db, sql_get_host_id, params=params, fetch="one", is_proc=False)
    if host_id:
        return host_id["host_id"]
    else:
        return None


class HostInfo(TypedDict):
    bot_display_name: str
    bot_pfp_filename: str
    """A file under `images/`."""


async def get_host_info(db: aiomysql.Connection, host_user_id: int) -> HostInfo | None:
    """None for a host with no `hosts` row."""
    sql_get_host_info = """
                        SELECT bot_display_name AS bot_display_name,
                                bot_pfp AS bot_pfp_filename
                        FROM hosts
                        WHERE user_id = %s
                        """
    params = (host_user_id,)
    host_info_dict = await execute_query(db, sql_get_host_info, params=params, fetch="one", is_proc=False)
    if host_info_dict:
        return host_info_dict
    else:
        return None


async def check_db_for_hosting_support(db: aiomysql.Connection, database: str) -> bool:
    """Checks database columns of 'events_scheduled' to see if 'host_id' column exists.
    Returns True if exists, False if not.
    """
    sql_check_host_column = """
                            SELECT COUNT(*) AS count
                            FROM information_schema.columns
                            WHERE table_schema = %s
                            AND table_name = 'events_scheduled'
                            AND column_name = 'host_id'
                            """
    params = (database,)
    result = await execute_query(db, sql_check_host_column, params=params, fetch="one", is_proc=False)
    return result["count"] > 0


async def check_for_custom_message(
    db: aiomysql.Connection,
    event_name: str,
    post_type: Literal["one_hour", "ten_minute", "prix_open", "prix_result", "event_results"],
    host_id: int | None,
) -> bool:
    sql_check_host_message = """
                            SELECT COUNT(*) AS count
                            FROM event_messages A
                            INNER JOIN events B ON A.event_id = B.id
                            WHERE B.name = %s
                                AND A.message_type = %s
                                AND A.host_id = %s
                                    """
    params = (
        event_name,
        post_type,
        host_id,
    )
    num_posts = await execute_query(db, sql_check_host_message, params=params, fetch="one", is_proc=False)
    return num_posts["count"] > 0


async def get_post_template(
    db: aiomysql.Connection,
    event_name: str,
    post_type: Literal["one_hour", "ten_minute", "prix_open", "prix_result", "event_results"],
    host_id: int | None,
) -> str:
    # Check to see if host_id has an assigned post of post_type in post table
    is_custom_message: bool = False
    if host_id:
        is_custom_message = await check_for_custom_message(db, event_name, post_type, host_id)
    if host_id and is_custom_message:
        sql_message = """
                SELECT A.post AS post
                FROM event_messages A
                INNER JOIN events B ON A.event_id = B.id
                WHERE B.name = %s
                    AND A.message_type = %s
                    AND A.host_id <=> %s
                    """
        params = (
            event_name,
            post_type,
            host_id,
        )
    else:
        sql_message = """
                SELECT A.post AS post
                FROM event_messages A
                INNER JOIN events B ON A.event_id = B.id
                WHERE B.name = %s
                    AND A.message_type = %s
                    AND A.host_id <=> NULL
                    """
        params = (
            event_name,
            post_type,
        )

    message = await execute_query(db, sql_message, params=params, fetch="one", is_proc=False)
    return message["post"]
