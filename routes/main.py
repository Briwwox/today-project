import random
import sqlite3
from datetime import datetime, timedelta
from flask import Blueprint, flash, jsonify, redirect, render_template, request, url_for
from extensions import limiter
from utils import clip_text, db_connection

main_bp = Blueprint("main", __name__)

CURRENT_PROMO_HOLIDAY = None
CURRENT_PROMO_MESSAGE = None

DEFAULT_PREVIEW_URL = "/static/img/og-preview.jpg"
PROMO_HOLIDAY_ID = -1


def get_active_promo():
    global CURRENT_PROMO_HOLIDAY
    if CURRENT_PROMO_HOLIDAY and CURRENT_PROMO_HOLIDAY.get("expires_at"):
        if datetime.now() >= CURRENT_PROMO_HOLIDAY["expires_at"]:
            CURRENT_PROMO_HOLIDAY = None
    return CURRENT_PROMO_HOLIDAY


def get_active_promo_message():
    global CURRENT_PROMO_MESSAGE
    if CURRENT_PROMO_MESSAGE and CURRENT_PROMO_MESSAGE.get("expires_at"):
        if datetime.now() >= CURRENT_PROMO_MESSAGE["expires_at"]:
            CURRENT_PROMO_MESSAGE = None
    return CURRENT_PROMO_MESSAGE


def _is_leap_year(year: int) -> bool:
    return year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)


def _get_holiday_for_date(target_dt: datetime):
    date_str = target_dt.strftime("%m-%d")
    day_number = (target_dt - datetime(target_dt.year, 1, 1)).days + 1
    effective_day = day_number - 1 if (_is_leap_year(target_dt.year) and day_number > 59) else day_number

    with db_connection() as conn:
        holiday = conn.execute(
            "SELECT * FROM holidays WHERE show_date = ? AND active = 1",
            (date_str,),
        ).fetchone()
        if not holiday:
            holiday = conn.execute(
                "SELECT * FROM holidays WHERE day_number = ? AND active = 1",
                (effective_day,),
            ).fetchone()

    return holiday, effective_day


def _serialize_holiday(holiday, day_label: str) -> dict:
    return {
        "id": holiday["id"],
        "title": holiday["title"],
        "emoji": holiday["emoji"],
        "tint": holiday["tint"],
        "description": holiday["description"],
        "mission": holiday["mission"],
        "day_number": day_label,
        "type": holiday["type"] or "author",
        "fact": holiday["fact"] or "",
        "image_url": DEFAULT_PREVIEW_URL,
    }


@main_bp.route("/")
def index():
    return render_template("index.html")


@main_bp.route("/yandex_b26e4807b4245943.html")
def yandex_verification():
    return render_template("yandex_b26e4807b4245943.html")


@main_bp.route("/google871f65d840611d5f.html")
def google_verification():
    return render_template("google871f65d840611d5f.html")


@main_bp.route("/api/today")
def api_today():
    promo = get_active_promo()
    if promo:
        return jsonify({
            "id": PROMO_HOLIDAY_ID,
            "title": promo["title"],
            "emoji": promo["emoji"],
            "tint": promo["tint"],
            "description": promo["description"],
            "mission": promo["mission"],
            "day_number": "СПЕЦВЫПУСК ✨",
            "type": promo["type"],
            "fact": promo["fact"],
            "image_url": DEFAULT_PREVIEW_URL,
        })

    holiday, day_number = _get_holiday_for_date(datetime.now())
    if not holiday:
        return jsonify({"error": "Нет праздников"}), 404

    return jsonify(_serialize_holiday(holiday, f"ДЕНЬ №{day_number}"))


@main_bp.route("/api/yesterday")
def api_yesterday():
    yesterday = datetime.now() - timedelta(days=1)
    holiday, day_number = _get_holiday_for_date(yesterday)
    if not holiday:
        return jsonify({"error": "Нет праздников"}), 404

    return jsonify(_serialize_holiday(holiday, f"ВЧЕРА БЫЛ ДЕНЬ №{day_number}"))


@main_bp.route("/api/random")
def api_random():
    exclude_id = request.args.get("exclude", type=int)
    with db_connection() as conn:
        if exclude_id:
            total = conn.execute(
                "SELECT COUNT(*) FROM holidays WHERE active = 1 AND id != ?",
                (exclude_id,),
            ).fetchone()[0]
            if total > 0:
                offset = random.randrange(total)
                holiday = conn.execute(
                    "SELECT * FROM holidays WHERE active = 1 AND id != ? LIMIT 1 OFFSET ?",
                    (exclude_id, offset),
                ).fetchone()
                if holiday:
                    return jsonify(_serialize_holiday(holiday, "СЛУЧАЙНЫЙ ПРАЗДНИК"))

        total_all = conn.execute("SELECT COUNT(*) FROM holidays WHERE active = 1").fetchone()[0]
        if total_all == 0:
            return jsonify({"error": "Нет праздников"}), 404
        offset = random.randrange(total_all)
        holiday = conn.execute(
            "SELECT * FROM holidays WHERE active = 1 LIMIT 1 OFFSET ?",
            (offset,),
        ).fetchone()

    if not holiday:
        return jsonify({"error": "Нет праздников"}), 404

    return jsonify(_serialize_holiday(holiday, "СЛУЧАЙНЫЙ ПРАЗДНИК"))


@main_bp.route("/api/message")
def api_message():
    promo_msg = get_active_promo_message()
    if promo_msg:
        return jsonify({"text": promo_msg["text"]})

    with db_connection() as conn:
        messages = conn.execute("SELECT text FROM day_messages ORDER BY id ASC").fetchall()

    if not messages:
        return jsonify({"text": "Сегодня отличный день, чтобы улыбнуться!"})

    now = datetime.now()
    day_number = (now - datetime(now.year, 1, 1)).days + 1
    msg = messages[(day_number - 1) % len(messages)]["text"]
    return jsonify({"text": msg})


@main_bp.route("/api/likes/<int:holiday_id>")
def api_get_likes(holiday_id):
    if holiday_id == PROMO_HOLIDAY_ID:
        return jsonify({"likes": 0})

    with db_connection() as conn:
        count = conn.execute(
            "SELECT COUNT(*) FROM votes WHERE holiday_id = ?",
            (holiday_id,),
        ).fetchone()[0]
    return jsonify({"likes": count})


@main_bp.route("/api/like/<int:holiday_id>", methods=["POST"])
@limiter.limit("60 per minute")
def api_toggle_like(holiday_id):
    if holiday_id == PROMO_HOLIDAY_ID:
        return jsonify({"error": "Лайки для спецвыпуска недоступны"}), 400

    data = request.get_json(silent=True) or {}
    voter_hash = clip_text(data.get("voter_hash"), 100)
    if not voter_hash:
        return jsonify({"error": "Не передан идентификатор пользователя"}), 400

    with db_connection() as conn:
        holiday_exists = conn.execute(
            "SELECT id FROM holidays WHERE id = ?",
            (holiday_id,),
        ).fetchone()
        if not holiday_exists:
            return jsonify({"error": "Праздник не найден"}), 404

        existing = conn.execute(
            "SELECT id FROM votes WHERE holiday_id = ? AND voter_hash = ?",
            (holiday_id, voter_hash),
        ).fetchone()
        liked = False
        if existing:
            conn.execute(
                "DELETE FROM votes WHERE holiday_id = ? AND voter_hash = ?",
                (holiday_id, voter_hash),
            )
        else:
            try:
                conn.execute(
                    "INSERT INTO votes (holiday_id, voter_hash) VALUES (?, ?)",
                    (holiday_id, voter_hash),
                )
                liked = True
            except sqlite3.IntegrityError:
                pass
        conn.commit()
        new_count = conn.execute(
            "SELECT COUNT(*) FROM votes WHERE holiday_id = ?",
            (holiday_id,),
        ).fetchone()[0]

    return jsonify({"liked": liked, "likes": new_count})


@main_bp.route("/suggest", methods=["GET", "POST"])
@limiter.limit("10 per hour; 30 per day")
def suggest_holiday():
    if request.method == "POST":
        title = clip_text(request.form.get("title"), 150)
        emoji = clip_text(request.form.get("emoji"), 16) or "🎉"
        description = clip_text(request.form.get("description"), 1500)
        mission = clip_text(request.form.get("mission"), 300)
        suggested_by = clip_text(request.form.get("suggested_by"), 80) or "Аноним"

        if not title or not description:
            flash("Название и описание обязательны для заполнения!", "error")
            return render_template("suggest.html")

        with db_connection() as conn:
            conn.execute(
                "INSERT INTO suggestions (title, emoji, description, mission, suggested_by) VALUES (?, ?, ?, ?, ?)",
                (title, emoji, description, mission, suggested_by),
            )
            conn.commit()

        flash("Спасибо! Твой праздник отправлен на модерацию.", "success")
        return redirect(url_for("main.suggest_holiday"))
    return render_template("suggest.html")