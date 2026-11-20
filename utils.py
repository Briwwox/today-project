import logging
import os
import re
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from functools import wraps
from flask import g, redirect, session, url_for
from PIL import Image

logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, "static", "uploads", "avatars")
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif"}
CSV_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def _resolve_db_path() -> str:
    return os.environ.get("DATABASE_PATH") or os.path.join(BASE_DIR, "database.db")


def get_db_connection(db_path: str | None = None) -> sqlite3.Connection:
    target_path = db_path or _resolve_db_path()
    conn = sqlite3.connect(target_path, timeout=10.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


@contextmanager
def db_connection(db_path: str | None = None):
    conn = get_db_connection(db_path)
    try:
        yield conn
    finally:
        conn.close()


def allowed_file(filename: str | None) -> bool:
    return (
        bool(filename)
        and isinstance(filename, str)
        and "." in filename
        and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS
    )


def is_valid_image(file_stream) -> bool:
    try:
        file_stream.seek(0)
        with Image.open(file_stream) as img:
            img.verify()
        file_stream.seek(0)
        with Image.open(file_stream) as img:
            img.load()
        file_stream.seek(0)
        return True
    except Exception as exc:
        logger.debug("Проверка изображения не пройдена: %s", exc)
        return False


def is_valid_hex_color(color: str | None) -> bool:
    if not isinstance(color, str) or len(color) != 7 or not color.startswith("#"):
        return False
    try:
        int(color[1:], 16)
        return True
    except ValueError:
        return False


def parse_show_date(show_date: str | None) -> int | None:
    """Возвращает порядковый номер дня (1..365) для строки вида 'MM-DD'."""
    if not show_date or not isinstance(show_date, str):
        return None
    normalized = show_date.strip()
    if not re.fullmatch(r"\d{2}-\d{2}", normalized):
        return None
    try:
        month, day = map(int, normalized.split("-"))
        return (datetime(2023, month, day) - datetime(2023, 1, 1)).days + 1
    except (ValueError, TypeError):
        return None


def clip_text(value: str | None, max_len: int) -> str:
    text = (value or "").strip()
    return text[:max_len]


def sanitize_csv_cell(value) -> str:
    text = "" if value is None else str(value)
    if text.startswith(CSV_FORMULA_PREFIXES):
        return "'" + text
    return text


def _sync_session_user_fields(user: sqlite3.Row) -> None:
    updates = {
        "role": user["role"],
        "avatar": user["avatar"],
        "username": user["username"],
    }
    for key, val in updates.items():
        if session.get(key) != val:
            session[key] = val


def _load_active_admin():
    if hasattr(g, "_active_admin_loaded"):
        return getattr(g, "_active_admin", None)

    uid = session.get("user_id")
    if not uid:
        g._active_admin_loaded = True
        g._active_admin = None
        return None

    with db_connection() as conn:
        user = conn.execute(
            "SELECT is_banned, role, avatar, username FROM users WHERE id = ?",
            (uid,),
        ).fetchone()

    if not user or user["is_banned"] == 1:
        session.clear()
        g._active_admin_loaded = True
        g._active_admin = None
        return None

    _sync_session_user_fields(user)
    g._active_admin_loaded = True
    g._active_admin = user
    return user


def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not _load_active_admin():
            return redirect(url_for("admin.admin_login"))
        return f(*args, **kwargs)
    return decorated_function


def superadmin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        user = _load_active_admin()
        if not user:
            return redirect(url_for("admin.admin_login"))
        if user["role"] != "superadmin":
            return "Доступ запрещен. Вы не Супер-Админ.", 403
        return f(*args, **kwargs)
    return decorated_function