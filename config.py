import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
OWNER_ID = int(os.getenv("OWNER_ID", "0"))

DATA_DIR = os.getenv("DATA_DIR", "/data")
RECORDINGS_DIR = os.path.join(DATA_DIR, "recordings")
DATABASE_PATH = os.path.join(DATA_DIR, "bot.db")

DEFAULT_DURATION = int(os.getenv("DEFAULT_DURATION", "3600"))
MAX_DURATION = int(os.getenv("MAX_DURATION", "10800"))

DEFAULT_USER_LIMIT = int(os.getenv("DEFAULT_USER_LIMIT", "1"))
DEFAULT_RETRY = int(os.getenv("DEFAULT_RETRY", "3"))

UPLOAD_CHUNK_SIZE = 512 * 1024

os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(RECORDINGS_DIR, exist_ok=True)