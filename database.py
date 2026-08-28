import aiosqlite
from config import DATABASE_PATH


async def init_db():

    async with aiosqlite.connect(DATABASE_PATH) as db:

        await db.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            authorized INTEGER DEFAULT 0,
            max_jobs INTEGER DEFAULT 1,
            max_duration INTEGER DEFAULT 3600,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)

        await db.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
        """)

        await db.execute("""
        CREATE TABLE IF NOT EXISTS jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            url TEXT,
            engine TEXT,
            duration INTEGER,
            status TEXT,
            filename TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)

        await db.commit()


async def create_user(user_id, username="", first_name=""):

    async with aiosqlite.connect(DATABASE_PATH) as db:

        await db.execute("""
        INSERT OR IGNORE INTO users
        (user_id, username, first_name)
        VALUES (?, ?, ?)
        """, (user_id, username, first_name))

        await db.commit()


async def authorize_user(user_id):

    async with aiosqlite.connect(DATABASE_PATH) as db:

        await db.execute("""
        INSERT OR IGNORE INTO users
        (user_id)
        VALUES (?)
        """, (user_id,))

        await db.execute("""
        UPDATE users
        SET authorized = 1
        WHERE user_id = ?
        """, (user_id,))

        await db.commit()


async def remove_user(user_id):

    async with aiosqlite.connect(DATABASE_PATH) as db:

        await db.execute("""
        UPDATE users
        SET authorized = 0
        WHERE user_id = ?
        """, (user_id,))

        await db.commit()


async def is_authorized(user_id, owner_id):

    if user_id == owner_id:
        return True

    async with aiosqlite.connect(DATABASE_PATH) as db:

        cur = await db.execute("""
        SELECT authorized
        FROM users
        WHERE user_id = ?
        """, (user_id,))

        row = await cur.fetchone()

        return bool(row and row[0])


async def set_limit(user_id, limit):

    async with aiosqlite.connect(DATABASE_PATH) as db:

        await db.execute("""
        INSERT OR IGNORE INTO users
        (user_id)
        VALUES (?)
        """, (user_id,))

        await db.execute("""
        UPDATE users
        SET max_jobs = ?
        WHERE user_id = ?
        """, (limit, user_id))

        await db.commit()


async def set_duration(user_id, duration):

    async with aiosqlite.connect(DATABASE_PATH) as db:

        await db.execute("""
        INSERT OR IGNORE INTO users
        (user_id)
        VALUES (?)
        """, (user_id,))

        await db.execute("""
        UPDATE users
        SET max_duration = ?
        WHERE user_id = ?
        """, (duration, user_id))

        await db.commit()


async def get_user_limits(user_id):

    async with aiosqlite.connect(DATABASE_PATH) as db:

        cur = await db.execute("""
        SELECT max_jobs, max_duration
        FROM users
        WHERE user_id = ?
        """, (user_id,))

        row = await cur.fetchone()

        if not row:
            return 1, 3600

        return row[0], row[1]


async def get_users():

    async with aiosqlite.connect(DATABASE_PATH) as db:

        cur = await db.execute("""
        SELECT user_id, username, first_name, authorized,
               max_jobs, max_duration
        FROM users
        ORDER BY user_id
        """)

        return await cur.fetchall()


async def add_job(user_id, url, engine, duration, filename):

    async with aiosqlite.connect(DATABASE_PATH) as db:

        cur = await db.execute("""
        INSERT INTO jobs
        (user_id, url, engine, duration, status, filename)
        VALUES (?, ?, ?, ?, ?, ?)
        """, (
            user_id,
            url,
            engine,
            duration,
            "queued",
            filename
        ))

        await db.commit()

        return cur.lastrowid


async def update_job(job_id, status):

    async with aiosqlite.connect(DATABASE_PATH) as db:

        await db.execute("""
        UPDATE jobs
        SET status = ?
        WHERE id = ?
        """, (status, job_id))

        await db.commit()


async def get_stats():

    async with aiosqlite.connect(DATABASE_PATH) as db:

        cur = await db.execute(
            "SELECT COUNT(*) FROM users"
        )

        users = (await cur.fetchone())[0]

        cur = await db.execute(
            "SELECT COUNT(*) FROM jobs"
        )

        jobs = (await cur.fetchone())[0]

        cur = await db.execute(
            "SELECT COUNT(*) FROM jobs WHERE status='completed'"
        )

        completed = (await cur.fetchone())[0]

        return users, jobs, completed