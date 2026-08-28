import asyncio
import os
import re
import time
from collections import defaultdict, deque
from pathlib import Path

from aiogram import (
    Bot,
    Dispatcher,
    F
)

from aiogram.filters import Command
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton
)

from config import *

from database import *

from recorder import Recorder, RecorderError

from uploader import (
    upload_document,
    UploadCancelled
)


bot = Bot(BOT_TOKEN)

dp = Dispatcher()

queue = deque()

active_jobs = {}

user_engines = defaultdict(
    lambda: "ffmpeg"
)


def bar(percent, size=18):

    percent = max(
        0,
        min(
            100,
            percent
        )
    )

    filled = int(
        size * percent / 100
    )

    return (
        "█" * filled +
        "░" * (size - filled)
    )


def fmt(seconds):

    seconds = int(
        max(
            0,
            seconds
        )
    )

    h = seconds // 3600

    m = (
        seconds % 3600
    ) // 60

    s = seconds % 60

    return (
        f"{h:02d}:"
        f"{m:02d}:"
        f"{s:02d}"
    )


def safe_filename(url):

    name = "recording"

    match = re.search(
        r"[?&]id=([^&]+)",
        url
    )

    if match:

        name += "_" + match.group(1)

    timestamp = time.strftime(
        "%Y-%m-%d_%H-%M-%S"
    )

    return (
        f"{name}_{timestamp}.mkv"
    )


def keyboard():

    return InlineKeyboardMarkup(
        inline_keyboard=[

            [
                InlineKeyboardButton(
                    text="🎥 Record",
                    callback_data="record_help"
                ),

                InlineKeyboardButton(
                    text="⚙️ Engine",
                    callback_data="engine_help"
                )
            ],

            [
                InlineKeyboardButton(
                    text="📊 Status",
                    callback_data="status"
                ),

                InlineKeyboardButton(
                    text="📋 Queue",
                    callback_data="queue"
                )
            ],

            [
                InlineKeyboardButton(
                    text="🛑 Cancel",
                    callback_data="cancel"
                ),

                InlineKeyboardButton(
                    text="📖 Help",
                    callback_data="help"
                )
            ]

        ]
    )


async def allowed(message):

    return await is_authorized(
        message.from_user.id,
        OWNER_ID
    )


async def deny(message):

    await message.answer(
        "⛔ <b>Access Denied</b>\n\n"
        "Owner se authorization maango.\n\n"
        "Apni ID dekhne ke liye:\n"
        "<code>/id</code>",
        parse_mode="HTML"
    )


@dp.message(Command("start"))
async def start(message: Message):

    await create_user(
        message.from_user.id,
        message.from_user.username or "",
        message.from_user.first_name or ""
    )

    if not await allowed(message):

        return await deny(message)

    await message.answer(
        "🎬 <b>M3U8 Recorder Pro</b>\n\n"
        "Multi-engine stream recorder.\n\n"
        "🎥 FFmpeg\n"
        "⚡ Streamlink\n"
        "🧰 N_m3u8DL-RE\n"
        "📥 yt-dlp\n\n"
        "Use /help for commands.",
        parse_mode="HTML",
        reply_markup=keyboard()
    )


@dp.message(Command("id"))
async def get_id(message: Message):

    await message.answer(
        f"🆔 Your Telegram ID:\n"
        f"<code>{message.from_user.id}</code>",
        parse_mode="HTML"
    )


@dp.message(Command("help"))
async def help_command(message: Message):

    if not await allowed(message):

        return await deny(message)

    text = """
<b>🎬 M3U8 Recorder Commands</b>

<b>Recording</b>

/record URL 60
/engine ffmpeg
/engine streamlink
/engine yt-dlp
/engine n-m3u8dl-re

<b>Control</b>

/status
/queue
/cancel

<b>Account</b>

/id
/profile

<b>Owner</b>

/authorize ID
/remove ID
/users
/setlimit ID NUMBER
/setduration ID MINUTES
/stats
/broadcast TEXT

<b>Examples</b>

/engine ffmpeg

/record https://example.com/live.m3u8 60

Duration maximum depends on your configured/user limit.
"""

    await message.answer(
        text,
        parse_mode="HTML"
    )


@dp.message(Command("profile"))
async def profile(message: Message):

    if not await allowed(message):

        return await deny(message)

    limit, duration = await get_user_limits(
        message.from_user.id
    )

    await message.answer(
        f"👤 <b>Your Profile</b>\n\n"
        f"ID: <code>{message.from_user.id}</code>\n"
        f"Engine: <code>{user_engines[message.from_user.id]}</code>\n"
        f"Concurrent jobs: <b>{limit}</b>\n"
        f"Max duration: <b>{fmt(duration)}</b>",
        parse_mode="HTML"
    )


@dp.message(Command("engine"))
async def engine_command(message: Message):

    if not await allowed(message):

        return await deny(message)

    args = message.text.split()

    if len(args) < 2:

        return await message.answer(
            "Usage:\n"
            "/engine ffmpeg\n"
            "/engine streamlink\n"
            "/engine yt-dlp\n"
            "/engine n-m3u8dl-re"
        )

    engine = args[1].lower()

    aliases = {
        "n-m3u8dl-re": "n_m3u8dl_re",
        "n_m3u8dl_re": "n_m3u8dl_re"
    }

    engine = aliases.get(
        engine,
        engine
    )

    if engine not in (
        "ffmpeg",
        "streamlink",
        "yt-dlp",
        "n_m3u8dl_re"
    ):

        return await message.answer(
            "❌ Unknown engine."
        )

    user_engines[
        message.from_user.id
    ] = engine

    await message.answer(
        f"✅ Engine changed to "
        f"<code>{engine}</code>",
        parse_mode="HTML"
    )


@dp.message(Command("record"))
async def record_command(message: Message):

    if not await allowed(message):

        return await deny(message)

    args = message.text.split()

    if len(args) < 2:

        return await message.answer(
            "Usage:\n"
            "<code>/record URL MINUTES</code>",
            parse_mode="HTML"
        )

    url = args[1]

    minutes = 60

    if len(args) >= 3:

        try:

            minutes = int(args[2])

        except ValueError:

            return await message.answer(
                "❌ Minutes number hona chahiye."
            )

    user_limit, user_duration = (
        await get_user_limits(
            message.from_user.id
        )
    )

    duration = minutes * 60

    duration = min(
        duration,
        user_duration,
        MAX_DURATION
    )

    if duration <= 0:

        return await message.answer(
            "❌ Invalid duration."
        )

    running = sum(
        1
        for j in active_jobs.values()
        if j["user_id"] ==
        message.from_user.id
    )

    pending = sum(
        1
        for j in queue
        if j["user_id"] ==
        message.from_user.id
    )

    if running + pending >= user_limit:

        return await message.answer(
            "⚠️ Your job limit reached.\n"
            "Please wait for the current recording."
        )

    engine = user_engines[
        message.from_user.id
    ]

    filename = safe_filename(url)

    job = {
        "user_id":
            message.from_user.id,

        "chat_id":
            message.chat.id,

        "url":
            url,

        "duration":
            duration,

        "engine":
            engine,

        "filename":
            filename,

        "message_id":
            message.message_id
    }

    job["id"] = await add_job(
        message.from_user.id,
        url,
        engine,
        duration,
        filename
    )

    queue.append(job)

    await message.answer(
        f"📋 <b>Added to queue</b>\n\n"
        f"Job: <code>#{job['id']}</code>\n"
        f"Engine: <code>{engine}</code>\n"
        f"Duration: <code>{fmt(duration)}</code>\n\n"
        f"Queue position: {len(queue)}",
        parse_mode="HTML"
    )

    asyncio.create_task(
        queue_worker()
    )


async def queue_worker():

    if not queue:

        return

    while queue:

        job = queue.popleft()

        uid = job["user_id"]

        user_limit, _ = (
            await get_user_limits(uid)
        )

        running = sum(
            1
            for j in active_jobs.values()
            if j["user_id"] == uid
        )

        if running >= user_limit:

            queue.append(job)

            await asyncio.sleep(5)

            continue

        active_jobs[
            job["id"]
        ] = job

        try:

            await run_job(job)

        finally:

            active_jobs.pop(
                job["id"],
                None
            )


async def run_job(job):

    uid = job["user_id"]

    chat_id = job["chat_id"]

    duration = job["duration"]

    engine = job["engine"]

    output = Path(
        RECORDINGS_DIR
    ) / job["filename"]

    recorder = Recorder(engine)

    job["recorder"] = recorder

    status_message = await bot.send_message(
        chat_id,
        "🚀 <b>Starting recording...</b>",
        parse_mode="HTML"
    )

    async def record_progress(
        percent,
        elapsed,
        total
    ):

        try:

            await status_message.edit_text(
                "🔴 <b>Recording</b>\n\n"
                f"{bar(percent)} "
                f"<b>{percent:.1f}%</b>\n\n"
                f"⏱ {fmt(elapsed)} / "
                f"{fmt(total)}\n"
                f"⚙️ Engine: "
                f"<code>{engine}</code>\n\n"
                "🛑 /cancel to stop",
                parse_mode="HTML"
            )

        except Exception:
            pass

    await update_job(
        job["id"],
        "recording"
    )

    try:

        await recorder.start(
            job["url"],
            output,
            duration,
            record_progress,
            DEFAULT_RETRY
        )

    except Exception as e:

        await update_job(
            job["id"],
            "failed"
        )

        await status_message.edit_text(
            "❌ <b>Recording Failed</b>\n\n"
            f"<code>{str(e)[:2500]}</code>",
            parse_mode="HTML"
        )

        return

    if not output.exists():

        await status_message.edit_text(
            "❌ Recording file not found."
        )

        return

    await update_job(
        job["id"],
        "uploading"
    )

    cancel_event = asyncio.Event()

    job["upload_cancel"] = cancel_event

    async def upload_progress(
        percent,
        sent,
        total,
        speed
    ):

        try:

            mb_sent = sent / 1024 / 1024

            mb_total = total / 1024 / 1024

            mb_speed = speed / 1024 / 1024

            await status_message.edit_text(
                "⬆️ <b>Uploading</b>\n\n"
                f"{bar(percent)} "
                f"<b>{percent:.1f}%</b>\n\n"
                f"📦 {mb_sent:.1f} / "
                f"{mb_total:.1f} MB\n"
                f"🚀 {mb_speed:.2f} MB/s\n\n"
                "🛑 /cancel to stop",
                parse_mode="HTML"
            )

        except Exception:
            pass

    try:

        await upload_document(

            chat_id,

            str(output),

            (
                f"🎬 <b>Recording Complete</b>\n\n"
                f"Engine: <code>{engine}</code>\n"
                f"Duration: <code>{fmt(duration)}</code>\n"
                f"Job: <code>#{job['id']}</code>"
            ),

            upload_progress,

            cancel_event
        )

        await update_job(
            job["id"],
            "completed"
        )

        await status_message.edit_text(
            "✅ <b>Upload completed!</b>",
            parse_mode="HTML"
        )

    except UploadCancelled:

        await update_job(
            job["id"],
            "cancelled"
        )

        await status_message.edit_text(
            "🛑 <b>Upload cancelled.</b>",
            parse_mode="HTML"
        )

    except Exception as e:

        await update_job(
            job["id"],
            "upload_failed"
        )

        await status_message.edit_text(
            "❌ <b>Upload failed</b>\n\n"
            f"<code>{str(e)[:2500]}</code>",
            parse_mode="HTML"
        )

    finally:

        try:

            output.unlink(
                missing_ok=True
            )

        except Exception:
            pass


@dp.message(Command("status"))
async def status(message: Message):

    if not await allowed(message):

        return await deny(message)

    jobs = [
        j for j in active_jobs.values()
        if j["user_id"] ==
        message.from_user.id
    ]

    if not jobs:

        return await message.answer(
            "ℹ️ No active recording."
        )

    text = "📊 <b>Active Jobs</b>\n\n"

    for job in jobs:

        text += (
            f"#{job['id']} — "
            f"<code>{job['engine']}</code>\n"
        )

    await message.answer(
        text,
        parse_mode="HTML"
    )


@dp.message(Command("queue"))
async def queue_command(message: Message):

    if not await allowed(message):

        return await deny(message)

    if not queue:

        return await message.answer(
            "📋 Queue empty."
        )

    text = "📋 <b>Queue</b>\n\n"

    for index, job in enumerate(
        list(queue),
        1
    ):

        text += (
            f"{index}. "
            f"#{job['id']} — "
            f"{job['engine']} — "
            f"{fmt(job['duration'])}\n"
        )

    await message.answer(
        text,
        parse_mode="HTML"
    )


@dp.message(Command("cancel"))
async def cancel(message: Message):

    if not await allowed(message):

        return await deny(message)

    uid = message.from_user.id

    for job in list(
        active_jobs.values()
    ):

        if job["user_id"] != uid:
            continue

        if "recorder" in job:

            await job[
                "recorder"
            ].cancel()

        if "upload_cancel" in job:

            job[
                "upload_cancel"
            ].set()

        await message.answer(
            "🛑 Stop request sent."
        )

        return

    for job in list(queue):

        if job["user_id"] == uid:

            queue.remove(job)

            await update_job(
                job["id"],
                "cancelled"
            )

            return await message.answer(
                "🛑 Queued job cancelled."
            )

    await message.answer(
        "ℹ️ No active job."
    )


@dp.message(Command("authorize"))
async def authorize(message: Message):

    if message.from_user.id != OWNER_ID:

        return await message.answer(
            "⛔ Owner only."
        )

    args = message.text.split()

    if len(args) != 2:

        return await message.answer(
            "/authorize TELEGRAM_ID"
        )

    try:

        uid = int(args[1])

    except ValueError:

        return await message.answer(
            "❌ Invalid Telegram ID."
        )

    await authorize_user(uid)

    await message.answer(
        f"✅ Authorized:\n"
        f"<code>{uid}</code>",
        parse_mode="HTML"
    )


@dp.message(Command("remove"))
async def remove(message: Message):

    if message.from_user.id != OWNER_ID:

        return await message.answer(
            "⛔ Owner only."
        )

    args = message.text.split()

    if len(args) != 2:

        return await message.answer(
            "/remove TELEGRAM_ID"
        )

    uid = int(args[1])

    await remove_user(uid)

    await message.answer(
        f"🗑 Access removed:\n"
        f"<code>{uid}</code>",
        parse_mode="HTML"
    )


@dp.message(Command("users"))
async def users(message: Message):

    if message.from_user.id != OWNER_ID:

        return await message.answer(
            "⛔ Owner only."
        )

    rows = await get_users()

    if not rows:

        return await message.answer(
            "No users."
        )

    text = "👥 <b>Users</b>\n\n"

    for row in rows:

        uid, username, name, auth, limit, duration = row

        status = (
            "✅"
            if auth
            else "❌"
        )

        text += (
            f"{status} "
            f"<code>{uid}</code> "
            f"{username or name or '-'}\n"
            f"   Jobs: {limit} | "
            f"Duration: {fmt(duration)}\n\n"
        )

    await message.answer(
        text[:4000],
        parse_mode="HTML"
    )


@dp.message(Command("setlimit"))
async def setlimit(message: Message):

    if message.from_user.id != OWNER_ID:

        return await message.answer(
            "⛔ Owner only."
        )

    args = message.text.split()

    if len(args) != 3:

        return await message.answer(
            "/setlimit USER_ID NUMBER"
        )

    uid = int(args[1])

    limit = max(
        1,
        int(args[2])
    )

    await set_limit(
        uid,
        limit
    )

    await message.answer(
        "✅ Limit updated."
    )


@dp.message(Command("setduration"))
async def setduration(message: Message):

    if message.from_user.id != OWNER_ID:

        return await message.answer(
            "⛔ Owner only."
        )

    args = message.text.split()

    if len(args) != 3:

        return await message.answer(
            "/setduration USER_ID MINUTES"
        )

    uid = int(args[1])

    minutes = int(args[2])

    duration = min(
        minutes * 60,
        MAX_DURATION
    )

    await set_duration(
        uid,
        duration
    )

    await message.answer(
        f"✅ Max duration set to "
        f"{fmt(duration)}"
    )


@dp.message(Command("stats"))
async def stats(message: Message):

    if message.from_user.id != OWNER_ID:

        return await message.answer(
            "⛔ Owner only."
        )

    users, jobs, completed = (
        await get_stats()
    )

    await message.answer(
        f"📊 <b>Bot Statistics</b>\n\n"
        f"👥 Users: {users}\n"
        f"🎥 Jobs: {jobs}\n"
        f"✅ Completed: {completed}",
        parse_mode="HTML"
    )


@dp.message(Command("broadcast"))
async def broadcast(message: Message):

    if message.from_user.id != OWNER_ID:

        return await message.answer(
            "⛔ Owner only."
        )

    text = message.text.partition(
        " "
    )[2]

    if not text:

        return await message.answer(
            "/broadcast MESSAGE"
        )

    rows = await get_users()

    sent = 0

    for row in rows:

        uid = row[0]

        try:

            await bot.send_message(
                uid,
                text
            )

            sent += 1

            await asyncio.sleep(
                0.05
            )

        except Exception:
            pass

    await message.answer(
        f"📢 Broadcast finished.\n"
        f"Sent: {sent}"
    )


@dp.callback_query(
    F.data == "record_help"
)
async def record_help(
    callback: CallbackQuery
):

    await callback.answer()

    await callback.message.answer(
        "<code>/record URL 60</code>\n\n"
        "60 = minutes",
        parse_mode="HTML"
    )


@dp.callback_query(
    F.data == "engine_help"
)
async def engine_help(
    callback: Callback
):

    await callback.answer()

    await callback.message.answer(
        "/engine ffmpeg\n"
        "/engine streamlink\n"
        "/engine yt-dlp\n"
        "/engine n-m3u8dl-re"
    )


@dp.callback_query(
    F.data == "status"
)
async def callback_status(
    callback: CallbackQuery
):

    await callback.answer()

    await status(
        callback.message
    )


@dp.callback_query(
    F.data == "queue"
)
async def callback_queue(
    callback: CallbackQuery
):

    await callback.answer()

    await queue_command(
        callback.message
    )


@dp.callback_query(
    F.data == "cancel"
)
async def callback_cancel(
    callback: CallbackQuery
):

    await callback.answer()

    await cancel(
        callback.message
    )


@dp.callback_query(
    F.data == "help"
)
async def callback_help(
    callback: CallbackQuery
):

    await callback.answer()

    await help_command(
        callback.message
    )


async def main():

    if not BOT_TOKEN:

        raise RuntimeError(
            "BOT_TOKEN missing"
        )

    if not OWNER_ID:

        raise RuntimeError(
            "OWNER_ID missing"
        )

    await init_db()

    print(
        "M3U8 Recorder Bot started."
    )

    await dp.start_polling(
        bot
    )


if __name__ == "__main__":

    asyncio.run(main())