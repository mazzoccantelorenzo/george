import json
import os
from typing import Any

CONFIG_DIR = os.path.expanduser("~/.george_config")
CONFIG_FILE = os.path.join(CONFIG_DIR, "keys.json")
HISTORY_FILE = os.path.join(CONFIG_DIR, "recent_vaults.json")
COLORS_FILE = os.path.join(CONFIG_DIR, "colors.json")
SESSION_FILE = os.path.join(CONFIG_DIR, "last_session.json")
BOOKMARKS_FILE = os.path.join(CONFIG_DIR, "bookmarks.json")
CHAT_DIR = os.path.join(CONFIG_DIR, "chats")
APP_VERSION = "v12.0"
UPDATE_REPO = os.environ.get("GEORGE_UPDATE_REPO", "mazzoccantelorenzo/george")
UPDATE_CHECK_ON_STARTUP = True
ANNOTATION_COLORS = {
    "Giallo": ("#fceea7", (0.98, 0.93, 0.65)),
    "Verde": ("#b5f5b5", (0.71, 0.96, 0.71)),
    "Rosa": ("#f5b5f5", (0.96, 0.71, 0.96)),
    "Azzurro": ("#b5dcf5", (0.71, 0.86, 0.96)),
}


def initialize() -> None:
    os.makedirs(CONFIG_DIR, exist_ok=True)
    if not os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "w") as file:
            json.dump({"next_page": "Right", "prev_page": "Left", "mode_highlight": "E",
                "mode_eraser": "Q", "mode_postit": "P", "save": "S"}, file, indent=4)
    if not os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, "w") as file:
            json.dump([], file)


def load_last_session() -> dict[str, Any]:
    try:
        with open(SESSION_FILE) as f:
            session = json.load(f)
        return session if isinstance(session, dict) else {}
    except (OSError, ValueError):
        return {}
