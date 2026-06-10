"""
Contains database commands for accessing event information. Basic functionality 
taken from Nightmare's fzd_bot.
"""

import os
import aiomysql
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
import logging
import sys

#logging.basicConfig(filename='output.log', level=logging.DEBUG,
#                    format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
stdout_handler = logging.StreamHandler(sys.stdout)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
stdout_handler.setFormatter(formatter)
logger.addHandler(stdout_handler)

_connection_pool = None
async def init_db_pool():
    global _connection_pool
    DB_CONFIG = {
        'user': os.getenv("DB_USER"),
        'password': os.getenv("DB_PASSWORD"),
        'host': os.getenv("DB_HOST", "localhost"),
        'db': os.getenv("DB_NAME"),
        'port': int(os.getenv("DB_PORT", 3306)),
        'autocommit': False
    }
    POOL_SIZE = 16
    if _connection_pool is None:
        _connection_pool = await aiomysql.create_pool(
            minsize=1, maxsize=POOL_SIZE,
            **DB_CONFIG
        )
        print("✅ Database pool created!")
    return _connection_pool


async def get_connection_from_pool():
    """
    Context manager that safely checks out a connection from the pool,
    and returns it afterward (even if errors happen).
    Automatically rebuilds the pool if it breaks.
    """
    global _connection_pool
    conn = None
    try:
        conn = await _connection_pool.acquire()
        logger.info(f"[DB] Got connection from pool: id={id(conn)}")
    except aiomysql.Error:
        logger.warning("[DB CONNECTION] POOL IS DEAD...")
    return conn

@asynccontextmanager
async def get_db_connection():
    """
    Context manager for safely acquiring and releasing a DB connection.
    Rolls back on error and retries once if connection is lost.
    """
    conn = None
    try:
        conn = await get_connection_from_pool()
         # Test connection quickly (cheap ping)
        #conn.ping(reconnect=True, attempts=1, delay=0)

        yield conn  # hand off to the calling code

    except aiomysql.Error as e:
        # Handle lost connection
        #if conn:
        #    release_connection(conn)
        #    conn = None
        #    print("[DB] Connection rolled back and released")
        await conn.rollback()
        print(f"[DB ERROR] Rolled back transaction: {e}")
         
        raise  # propagate error up to cog

    finally:
        if conn:
            _connection_pool.release(conn) #release_connection(conn)

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

async def get_user_id(db, discord_id: str):
    """ Given a discord user id (discord_id), returns the database
        id of that user
    """
    sql_getuser = "SELECT id from users WHERE discord_user_id = %s"
    user = await execute_query(db, sql_getuser, params=(discord_id,),  fetch="one")
    if user:
        return user['id']
    else:
        return None

async def add_new_user(db, discord_username, display_name=None) -> None:
    """ Adds new user to the database
    """ 
    
    # Assuming "discord_display_name" isn't required 
    sql_newuser="INSERT INTO users (tag, discord_user_id) VALUES (%s, %s);"

    if display_name is None: # Defaults to user's server display name 
        display_name = discord_username.nick[0:10]
    await execute_query(db, sql_newuser, params=(display_name, discord_username.name), fetch=None)


############################################
# ^ Above are Nightmare-Bot functions
############################################


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
                                users.discord_user_id AS discord_name,
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

async def update_host_in_db(db, scheduled_event_id, host_user_id):
    """ Updates the host column for the given scheduled event
    """
    sql_update_host = """UPDATE events_scheduled
                        SET host_id = CAST(%s AS SIGNED)
                        WHERE id = CAST(%s AS SIGNED)
                    """
    params = (host_user_id, scheduled_event_id)
    await execute_query(db, sql_update_host, params=params, fetch=None)

async def remove_host_from_event_db(db, scheduled_event_id):
    """ Sets the host_id column in events_scheduled to NULL for a given scheduled event.
    """
    sql_remove_host = """UPDATE events_scheduled
                        SET host_id = NULL
                        WHERE id = CAST(%s AS SIGNED)
                    """
    params = (scheduled_event_id,)
    await execute_query(db, sql_remove_host, params=params, fetch=None)