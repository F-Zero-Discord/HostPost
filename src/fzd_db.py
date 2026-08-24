"""
Contains database commands for accessing event information. Basic functionality 
taken from Nightmare's fzd_bot.
"""
import logging
from typing import Literal
import aiomysql
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

from src.settings import get_settings

logger = logging.getLogger(__name__)


async def _safe_rollback(conn, source: str = "unknown") -> None:
    """Rollback only when possible; never mask the original exception."""
    if not conn or getattr(conn, "closed", True):
        return
    try:
        await conn.rollback()
    except aiomysql.Error as rollback_error:
        logger.warning(f"[DB] Rollback skipped ({source}): {rollback_error}")


async def init_db_pool():
    _connection_pool = None
    settings = get_settings()

    POOL_SIZE = 16
    if _connection_pool is None:
        _connection_pool = await aiomysql.create_pool(
            minsize=1, maxsize=POOL_SIZE,
            **settings.db_config
        )
        print("✅ Database pool created!")
    return _connection_pool


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
            connection_pool.release(conn) #release_connection(conn)

async def execute_query(conn, query, params=None, fetch="all", isProc:bool = False):
    """
    Safely executes an SQL query with rollback on error.
    :conn: DB connection object
    :query: SQL query string
    :params: Optional tuple/list of parameters
    :fetch: "all", "one", or None (for INSERT/UPDATE/DELETE)
    :return: Query result or None if no result
    """
    cursor=None
    async with conn.cursor(aiomysql.DictCursor) as cursor:
        try:
            if isProc:
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

async def get_event_schedule(db):
    """ Executes sql process query to get scheduled events in future
    """         
    sql_events="SELECT event, utc_start, utc_end FROM vw_list_scheduled_events"
    events = await execute_query(db, sql_events, params=None, fetch="all", isProc=False)
    return events

async def get_scheduled_event_id(db, scheduled_event_name):
    """ Gets the id given a name scheduled_events
    """
    sql_scheduled_event_id = """SELECT id
                                FROM events_scheduled
                                WHERE display_name = %s   
                            """
    params = (scheduled_event_name,)
    event_id = await execute_query(db, sql_scheduled_event_id, params=params, fetch="one")
    return event_id["id"]

async def get_event_scores(db, scheduled_event_id):
    """ Gets the users and their scores from the selected event 
    """
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
    return await execute_query(db, sql_event_scores, params=params, isProc=False)


async def get_hosting_schedule(db):
    """ Gets current and future events and the associated hosts. Gets all future
        evets_scheduled.
        The output is a list of dicts with keys as follows:
            event_name: str
            start: datetime
            host: str | None
            active: integer (1 if active, 0 if not)
    """
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
    return await execute_query(db, sql_host_schedule, params=params, fetch="all", isProc=False)


# `update_host_in_db` and `remove_host_from_event_db` were here. Task 15-04
# replaced them with PUT and DELETE /v1/events/{id}/host: writing
# `events_scheduled.host_id` needs a `users.id`, and holding one is exactly what
# this bot stopped doing.


async def get_event_host_id(db, scheduled_event_id: int) -> int | None:
    """ Returns user id of a host if one assigned to scheduled event.
        Otherwise returns None.
    """
    sql_get_host_id = """
                        SELECT host_id
                        FROM events_scheduled
                        WHERE id = %s
                    """
    params = (scheduled_event_id,)
    host_id = await execute_query(db, sql_get_host_id, params=params, fetch="one", isProc=False)
    if host_id:
        return host_id["host_id"]
    else:
        return None
    

async def get_host_info(db, host_user_id) -> dict[str] | None:
    """ Retrieves host information from the database: specifically
        - bot_display_name
        - bot_pfp_filename
    """
    sql_get_host_info = """
                        SELECT bot_display_name AS bot_display_name, 
                                bot_pfp AS bot_pfp_filename
                        FROM hosts
                        WHERE user_id = %s
                        """
    params = (host_user_id,)
    host_info_dict = await execute_query(db, sql_get_host_info, 
                                         params=params, fetch="one", isProc=False)
    if host_info_dict:
        return host_info_dict
    else:
        return None


async def check_db_for_hosting_support(db, DATABASE):
    """ Checks database columns of 'events_scheduled' to see if 'host_id' column exists. 
    Returns True if exists, False if not.
    """
    sql_check_host_column = """
                            SELECT COUNT(*) AS count
                            FROM information_schema.columns
                            WHERE table_schema = %s
                            AND table_name = 'events_scheduled' 
                            AND column_name = 'host_id'
                            """
    params = (DATABASE,)
    result = await execute_query(db, sql_check_host_column, params=params, fetch='one', isProc=False)
    return result['count'] > 0


async def get_tracks_from_db(db):
    """ Gets track names from database and returns two lists: 
    one for 99 mode tracks and one for classic tracks.
    """
    sql_get_classic_tracks = '''
                                SELECT name
                                FROM tracks
                                WHERE type = 'classic'
                            '''
    sql_get_99_tracks = '''
                        SELECT name
                        FROM tracks
                        WHERE type <> 'classic'
                        '''
    classic_tracks = await execute_query(db, sql_get_classic_tracks, params=None, fetch='all', isProc=False)
    ninetynine_tracks = await execute_query(db, sql_get_99_tracks, params=None, fetch='all', isProc=False)
    return [track['name'] for track in classic_tracks], [track['name'] for track in ninetynine_tracks]


async def check_for_custom_message(db, event_name: str, 
                            post_type: Literal[
                                "one_hour",
                                "ten_minute",
                                "prix_open",
                                "prix_result",
                                "event_results"],
                            host_id: int | None):
    """
    """
    sql_check_host_message  = """
                            SELECT COUNT(*) AS count
                            FROM event_messages A
                            INNER JOIN events B ON A.event_id = B.id 
                            WHERE B.name = %s 
                                AND A.message_type = %s 
                                AND A.host_id = %s
                                    """
    params = (event_name, post_type, host_id,)
    num_posts = await execute_query(db, sql_check_host_message, params=params, fetch='one', isProc=False)
    if num_posts['count'] > 0:
        return True
    else:
        return False


async def get_post_template(db, event_name: str, 
                            post_type: Literal[
                                "one_hour",
                                "ten_minute",
                                "prix_open",
                                "prix_result",
                                "event_results"],
                            host_id: int | None):
    """
    """
    # Check to see if host_id has an assigned post of post_type in post table
    is_custom_message: bool = False
    if host_id:
        is_custom_message = await check_for_custom_message(db, 
                                                           event_name, 
                                                           post_type, 
                                                           host_id)
    if host_id and is_custom_message:
        sql_message = """
                SELECT A.post AS post
                FROM event_messages A
                INNER JOIN events B ON A.event_id = B.id 
                WHERE B.name = %s
                    AND A.message_type = %s
                    AND A.host_id <=> %s
                    """
        params = (event_name, post_type, host_id,)
    else:
        sql_message = """
                SELECT A.post AS post
                FROM event_messages A
                INNER JOIN events B ON A.event_id = B.id 
                WHERE B.name = %s
                    AND A.message_type = %s
                    AND A.host_id <=> NULL
                    """
        params = (event_name, post_type,)
        
    message = await execute_query(db, sql_message, params=params, fetch='one', isProc=False)
    return message["post"]