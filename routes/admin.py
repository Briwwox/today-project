import csv
import io
import logging
import os
import secrets
from datetime import datetime, timedelta
from flask import (
    Blueprint,
    Response,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from werkzeug.security import check_password_hash, generate_password_hash
from utils import (
    UPLOAD_FOLDER,
    allowed_file,
    clip_text,
    db_connection,
    is_valid_hex_color,
    is_valid_image,
    login_required,
    parse_show_date,
    sanitize_csv_cell,
    superadmin_required,
)
from routes.main import (
    PROMO_HOLIDAY_ID,
    get_active_promo,
    get_active_promo_message,
)

logger = logging.getLogger(__name__)

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")

LOGIN_ATTEMPTS = {}
MAX_LOGIN_ATTEMPTS = 5
BLOCK_DURATION_SECONDS = 60
MIN_PASSWORD_LENGTH = 8
ALLOWED_HOLIDAY_TYPES = ("official", "unusual", "author")
ALLOWED_AVATAR_EXTS = {".png", ".jpg", ".jpeg", ".gif"}
MONTHS_DICT = {
    1: "Январь", 2: "Февраль", 3: "Март", 4: "Апрель", 5: "Май", 6: "Июнь",
    7: "Июль", 8: "Август", 9: "Сентябрь", 10: "Октябрь", 11: "Ноябрь", 12: "Декабрь",
}


def _get_client_ip() -> str:
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.remote_addr or "unknown"


def _prune_expired_login_attempts(now: datetime) -> None:
    expired_ips = [
        addr for addr, rec in LOGIN_ATTEMPTS.items()
        if rec.get("blocked_until") and now >= rec["blocked_until"]
    ]
    for addr in expired_ips:
        LOGIN_ATTEMPTS.pop(addr, None)


def _resolve_avatar(avatar_filename: str | None) -> str:
    filename = (avatar_filename or "default.png").strip()
    if not filename or filename == "default.png":
        return "default.png"
    safe_name = os.path.basename(filename)
    avatar_path = os.path.join(UPLOAD_FOLDER, safe_name)
    if os.path.isfile(avatar_path):
        return safe_name
    return "default.png"


def _delete_avatar_file(filename: str | None) -> None:
    if not filename or filename == "default.png":
        return
    safe_name = os.path.basename(filename)
    full_path = os.path.join(UPLOAD_FOLDER, safe_name)
    if os.path.isfile(full_path):
        try:
            os.remove(full_path)
        except OSError as exc:
            logger.warning("Не удалось удалить файл аватара %s: %s", safe_name, exc)


def _normalize_type(type_val: str | None) -> str:
    return type_val if type_val in ALLOWED_HOLIDAY_TYPES else "author"


def _extract_holiday_form_data(form) -> dict:
    show_date = clip_text(form.get("show_date"), 5)
    tint_raw = clip_text(form.get("tint"), 7)
    return {
        "title": clip_text(form.get("title"), 150),
        "emoji": clip_text(form.get("emoji"), 16) or "🎉",
        "tint": tint_raw if is_valid_hex_color(tint_raw) else "#f8dfe3",
        "description": clip_text(form.get("description"), 1500),
        "mission": clip_text(form.get("mission"), 300),
        "show_date": show_date,
        "day_number": parse_show_date(show_date),
        "active": 1 if form.get("active") else 0,
        "type": _normalize_type(clip_text(form.get("type"), 20) or "author"),
        "fact": clip_text(form.get("fact"), 600),
        "tags": clip_text(form.get("tags"), 250),
    }


def _parse_expires_at(form) -> datetime | None:
    duration = form.get("duration_hours", "24")
    if duration == "0":
        return None
    if duration == "custom":
        custom_time = form.get("custom_expires_at")
        if custom_time:
            try:
                return datetime.fromisoformat(custom_time)
            except ValueError:
                pass
        return datetime.now() + timedelta(hours=24)
    try:
        hours = int(duration)
    except ValueError:
        hours = 24
    return datetime.now() + timedelta(hours=hours)


def _set_promo_state(holiday_data: dict | None = None, message_data: dict | None = None, set_holiday: bool = False, set_message: bool = False) -> None:
    import routes.main as main_module
    if set_holiday:
        main_module.CURRENT_PROMO_HOLIDAY = holiday_data
    if set_message:
        main_module.CURRENT_PROMO_MESSAGE = message_data


@admin_bp.before_request
def _ensure_valid_avatar():
    if session.get("user_id"):
        resolved = _resolve_avatar(session.get("avatar"))
        if session.get("avatar") != resolved:
            session["avatar"] = resolved


@admin_bp.route("/login", methods=["GET", "POST"])
def admin_login():
    ip = _get_client_ip()
    now = datetime.now()
    _prune_expired_login_attempts(now)

    record = LOGIN_ATTEMPTS.get(ip)
    if record and record.get("blocked_until"):
        if now < record["blocked_until"]:
            if request.method == "POST":
                return render_template("429.html"), 429
        else:
            LOGIN_ATTEMPTS.pop(ip, None)

    error = None
    if request.method == "POST":
        username = clip_text(request.form.get("username"), 80)
        password = request.form.get("password") or ""
        with db_connection() as conn:
            user = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
            if user and check_password_hash(user["password_hash"], password):
                if user["is_banned"] == 1:
                    error = "Ваш аккаунт заблокирован!"
                else:
                    LOGIN_ATTEMPTS.pop(ip, None)
                    conn.execute(
                        "UPDATE users SET last_login = CURRENT_TIMESTAMP WHERE id = ?",
                        (user["id"],),
                    )
                    conn.commit()
                    session.clear()
                    session["user_id"] = user["id"]
                    session["username"] = user["username"]
                    session["role"] = user["role"]
                    session["avatar"] = _resolve_avatar(user["avatar"])
                    return redirect(url_for("admin.admin_dashboard"))

            rec = LOGIN_ATTEMPTS.setdefault(ip, {"fails": 0, "blocked_until": None})
            rec["fails"] += 1
            if rec["fails"] >= MAX_LOGIN_ATTEMPTS:
                rec["blocked_until"] = now + timedelta(seconds=BLOCK_DURATION_SECONDS)
                return render_template("429.html"), 429
            error = "Неверный логин или пароль"

    return render_template("admin/login.html", error=error)


@admin_bp.route("/")
@login_required
def admin_dashboard():
    search_query = clip_text(request.args.get("q"), 150)
    query = "SELECT * FROM holidays"
    params = []
    if search_query:
        query += " WHERE title LIKE ? OR description LIKE ?"
        params.extend([f"%{search_query}%", f"%{search_query}%"])
    query += " ORDER BY day_number ASC"

    with db_connection() as conn:
        holidays = conn.execute(query, params).fetchall()
        total_all = conn.execute("SELECT COUNT(*) FROM holidays").fetchone()[0]
        total_active = conn.execute("SELECT COUNT(*) FROM holidays WHERE active = 1").fetchone()[0]
        day_messages = conn.execute("SELECT * FROM day_messages ORDER BY id DESC").fetchall()

    grouped_holidays = {i: [] for i in range(1, 13)}
    for h in holidays:
        day_num = h["day_number"] or 1
        date_obj = datetime(2023, 1, 1) + timedelta(days=day_num - 1)
        grouped_holidays[date_obj.month].append(h)

    return render_template(
        "admin/dashboard.html",
        grouped_holidays=grouped_holidays,
        months_dict=MONTHS_DICT,
        search_query=search_query,
        total_all=total_all,
        total_active=total_active,
        total_inactive=total_all - total_active,
        total_filtered=len(holidays),
        current_promo=get_active_promo(),
        current_promo_message=get_active_promo_message(),
        day_messages=day_messages,
    )


@admin_bp.route("/logout")
def admin_logout():
    session.clear()
    return redirect(url_for("admin.admin_login"))


@admin_bp.route("/add", methods=["GET", "POST"])
@login_required
def admin_add():
    if request.method == "POST":
        data = _extract_holiday_form_data(request.form)
        if not data["title"] or not data["description"]:
            flash("Заполните название и описание праздника.", "error")
            return render_template("admin/form.html", holiday=None, title_text="Добавить праздник ✨")

        with db_connection() as conn:
            day_number = data["day_number"]
            if not day_number:
                max_day = conn.execute("SELECT MAX(day_number) FROM holidays").fetchone()[0]
                day_number = (max_day or 0) + 1

            conn.execute(
                """
                INSERT INTO holidays
                    (title, emoji, tint, description, mission, show_date, day_number, active, type, fact, tags)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    data["title"], data["emoji"], data["tint"], data["description"],
                    data["mission"], data["show_date"], day_number, data["active"],
                    data["type"], data["fact"], data["tags"],
                ),
            )
            conn.commit()
        flash("Праздник добавлен!", "success")
        return redirect(url_for("admin.admin_dashboard"))
    return render_template("admin/form.html", holiday=None, title_text="Добавить праздник ✨")


@admin_bp.route("/edit/<int:id>", methods=["GET", "POST"])
@login_required
def admin_edit(id):
    q = clip_text(request.args.get("q"), 150)
    with db_connection() as conn:
        holiday = conn.execute("SELECT * FROM holidays WHERE id = ?", (id,)).fetchone()
        if not holiday:
            flash("Праздник не найден.", "error")
            return redirect(url_for("admin.admin_dashboard", q=q))

        if request.method == "POST":
            data = _extract_holiday_form_data(request.form)
            target_day_number = data["day_number"] if data["day_number"] else holiday["day_number"]
            conn.execute(
                """
                UPDATE holidays
                SET title = ?, emoji = ?, tint = ?, description = ?, mission = ?,
                    show_date = ?, day_number = ?, active = ?, type = ?, fact = ?, tags = ?
                WHERE id = ?
                """,
                (
                    data["title"], data["emoji"], data["tint"], data["description"],
                    data["mission"], data["show_date"], target_day_number, data["active"],
                    data["type"], data["fact"], data["tags"], id,
                ),
            )
            conn.commit()
            flash("Праздник обновлён!", "success")
            return redirect(url_for("admin.admin_dashboard", q=q))

    return render_template("admin/form.html", holiday=holiday, title_text="Редактировать праздник ✨")


@admin_bp.route("/delete/<int:id>", methods=["POST"])
@superadmin_required
def admin_delete(id):
    q = clip_text(request.form.get("q"), 150)
    with db_connection() as conn:
        conn.execute("DELETE FROM holidays WHERE id = ?", (id,))
        conn.commit()
    flash("Праздник удалён.", "success")
    return redirect(url_for("admin.admin_dashboard", q=q))


@admin_bp.route("/suggestions")
@login_required
def admin_suggestions():
    with db_connection() as conn:
        suggestions = conn.execute("SELECT * FROM suggestions ORDER BY created_at DESC").fetchall()
    return render_template("admin/suggestions.html", suggestions=suggestions)


@admin_bp.route("/suggestions/approve/<int:id>", methods=["POST"])
@login_required
def admin_approve_suggestion(id):
    with db_connection() as conn:
        sug = conn.execute("SELECT * FROM suggestions WHERE id = ?", (id,)).fetchone()
        if sug:
            max_day = conn.execute("SELECT MAX(day_number) FROM holidays").fetchone()[0]
            next_day = (max_day or 0) + 1
            conn.execute(
                """
                INSERT INTO holidays
                    (title, emoji, tint, description, mission, day_number, active, type, fact, tags)
                VALUES (?, ?, ?, ?, ?, ?, 1, 'author', ?, ?)
                """,
                (
                    sug["title"],
                    sug["emoji"] or "🎉",
                    "#f8dfe3",
                    sug["description"],
                    sug["mission"] or "Отпраздновать этот день!",
                    next_day,
                    sug["suggested_by"] or "Аноним",
                    "пользовательский",
                ),
            )
            conn.execute("DELETE FROM suggestions WHERE id = ?", (id,))
            conn.commit()
            flash("Праздник одобрен!", "success")
    return redirect(url_for("admin.admin_suggestions"))


@admin_bp.route("/suggestions/delete/<int:id>", methods=["POST"])
@login_required
def admin_delete_suggestion(id):
    with db_connection() as conn:
        conn.execute("DELETE FROM suggestions WHERE id = ?", (id,))
        conn.commit()
    flash("Предложение удалено.", "success")
    return redirect(url_for("admin.admin_suggestions"))


@admin_bp.route("/promo/set", methods=["POST"])
@login_required
def promo_set():
    title = clip_text(request.form.get("title"), 150)
    emoji = clip_text(request.form.get("emoji"), 16) or "🎉"
    tint_raw = clip_text(request.form.get("tint"), 7)
    tint = tint_raw if is_valid_hex_color(tint_raw) else "#f7edc9"
    description = clip_text(request.form.get("description"), 1500)
    mission = clip_text(request.form.get("mission"), 300)
    fact = clip_text(request.form.get("fact"), 600) or "Спецвыпуск по случаю события!"
    expires_at = _parse_expires_at(request.form)

    _set_promo_state(
        holiday_data={
            "id": PROMO_HOLIDAY_ID,
            "title": title,
            "emoji": emoji,
            "tint": tint,
            "description": description,
            "mission": mission,
            "type": "author",
            "fact": fact,
            "expires_at": expires_at,
            "expires_str": expires_at.strftime("%H:%M %d.%m") if expires_at else "Бессрочно",
        },
        set_holiday=True,
    )
    flash("Промо-праздник успешно запущен в эфир!", "success")
    return redirect(url_for("admin.admin_dashboard"))


@admin_bp.route("/promo/clear", methods=["POST"])
@login_required
def promo_clear():
    _set_promo_state(holiday_data=None, set_holiday=True)
    flash("Промо-праздник выключен.", "success")
    return redirect(url_for("admin.admin_dashboard"))


@admin_bp.route("/promo_message/set", methods=["POST"])
@login_required
def promo_message_set():
    text = clip_text(request.form.get("text"), 400)
    expires_at = _parse_expires_at(request.form)

    _set_promo_state(
        message_data={
            "text": text,
            "expires_at": expires_at,
            "expires_str": expires_at.strftime("%H:%M %d.%m") if expires_at else "Бессрочно",
        },
        set_message=True,
    )
    flash("Срочное послание запущено!", "success")
    return redirect(url_for("admin.admin_dashboard"))


@admin_bp.route("/promo_message/clear", methods=["POST"])
@login_required
def promo_message_clear():
    _set_promo_state(message_data=None, set_message=True)
    flash("Послание выключено.", "success")
    return redirect(url_for("admin.admin_dashboard"))


@admin_bp.route("/messages/add", methods=["POST"])
@login_required
def add_message():
    text = clip_text(request.form.get("text"), 400)
    is_ajax = request.headers.get("X-Requested-With") == "XMLHttpRequest"
    if text:
        with db_connection() as conn:
            cur = conn.execute("INSERT INTO day_messages (text) VALUES (?)", (text,))
            conn.commit()
            new_id = cur.lastrowid
        if is_ajax:
            return jsonify({"id": new_id, "text": text}), 200
        flash("Фраза добавлена в базу!", "success")
    elif is_ajax:
        return jsonify({"error": "Пустая фраза"}), 400
    else:
        flash("Введите текст фразы.", "error")
    return redirect(url_for("admin.admin_dashboard"))


@admin_bp.route("/messages/edit/<int:id>", methods=["POST"])
@login_required
def edit_message(id):
    text = clip_text(request.form.get("text"), 400)
    is_ajax = request.headers.get("X-Requested-With") == "XMLHttpRequest"
    if text:
        with db_connection() as conn:
            conn.execute("UPDATE day_messages SET text = ? WHERE id = ?", (text, id))
            conn.commit()
        if is_ajax:
            return jsonify({"id": id, "text": text}), 200
        flash("Фраза обновлена!", "success")
    elif is_ajax:
        return jsonify({"error": "Пустая фраза"}), 400
    return redirect(url_for("admin.admin_dashboard"))


@admin_bp.route("/messages/delete/<int:id>", methods=["POST"])
@login_required
def delete_message(id):
    is_ajax = request.headers.get("X-Requested-With") == "XMLHttpRequest"
    with db_connection() as conn:
        conn.execute("DELETE FROM day_messages WHERE id = ?", (id,))
        conn.commit()
    if is_ajax:
        return jsonify({"deleted": True, "id": id}), 200
    flash("Фраза удалена.", "success")
    return redirect(url_for("admin.admin_dashboard"))


@admin_bp.route("/toggle/<int:id>", methods=["POST"])
@login_required
def toggle_holiday(id):
    with db_connection() as conn:
        holiday = conn.execute("SELECT active FROM holidays WHERE id = ?", (id,)).fetchone()
        if not holiday:
            return jsonify({"error": "Не найдено"}), 404
        new_status = 0 if holiday["active"] == 1 else 1
        conn.execute("UPDATE holidays SET active = ? WHERE id = ?", (new_status, id))
        conn.commit()
    return jsonify({"id": id, "active": new_status}), 200


@admin_bp.route("/export")
@login_required
def export_csv():
    with db_connection() as conn:
        holidays = conn.execute("SELECT * FROM holidays ORDER BY day_number ASC, id ASC").fetchall()

    output = io.StringIO()
    output.write("\ufeff")
    writer = csv.writer(output)
    writer.writerow(["id", "title", "emoji", "tint", "description", "mission", "show_date", "day_number", "active", "type", "fact", "tags"])
    for h in holidays:
        writer.writerow([
            sanitize_csv_cell(h["id"]),
            sanitize_csv_cell(h["title"]),
            sanitize_csv_cell(h["emoji"]),
            sanitize_csv_cell(h["tint"]),
            sanitize_csv_cell(h["description"]),
            sanitize_csv_cell(h["mission"]),
            sanitize_csv_cell(h["show_date"]),
            sanitize_csv_cell(h["day_number"]),
            sanitize_csv_cell(h["active"]),
            sanitize_csv_cell(h["type"]),
            sanitize_csv_cell(h["fact"]),
            sanitize_csv_cell(h["tags"]),
        ])

    return Response(
        output.getvalue(),
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment;filename=holidays_backup.csv"},
    )


@admin_bp.route("/import", methods=["POST"])
@superadmin_required
def import_csv():
    file = request.files.get("file")
    if not file or not file.filename or not file.filename.lower().endswith(".csv"):
        flash("Пожалуйста, выберите корректный CSV-файл.", "error")
        return redirect(url_for("admin.admin_dashboard"))

    try:
        stream = io.TextIOWrapper(file.stream, encoding="utf-8-sig")
        reader = csv.reader(stream)
        next(reader, None)

        prepared_rows = []
        for row in reader:
            if len(row) < 12:
                continue
            row_id = int(row[0]) if row[0].strip().isdigit() else None
            title = clip_text(row[1], 150)
            emoji = clip_text(row[2], 16) or "🎉"
            tint_raw = row[3].strip()
            tint = tint_raw if is_valid_hex_color(tint_raw) else "#f8dfe3"
            description = clip_text(row[4], 1500)
            mission = clip_text(row[5], 300)
            show_date = clip_text(row[6], 5)
            parsed_day = parse_show_date(show_date)
            raw_day = int(row[7]) if row[7].strip().lstrip("-").isdigit() else None
            candidate_day = parsed_day if parsed_day is not None else raw_day
            day_number = candidate_day if (candidate_day is not None and 1 <= candidate_day <= 366) else None
            active = 1 if str(row[8]).strip().lower() in ("1", "true", "yes") else 0
            type_val = _normalize_type(row[9].strip())
            fact = clip_text(row[10], 600)
            tags = clip_text(row[11], 250)

            if not title or not description:
                continue

            prepared_rows.append((
                row_id, title, emoji, tint, description, mission,
                show_date, day_number, active, type_val, fact, tags,
            ))

        if not prepared_rows:
            flash("В CSV не найдено валидных записей. База не изменена.", "error")
            return redirect(url_for("admin.admin_dashboard"))

        with db_connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute("DELETE FROM votes")
            conn.execute("DELETE FROM holidays")
            for r in prepared_rows:
                if r[0] is not None:
                    conn.execute(
                        """
                        INSERT INTO holidays
                            (id, title, emoji, tint, description, mission, show_date, day_number, active, type, fact, tags)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        r,
                    )
                else:
                    conn.execute(
                        """
                        INSERT INTO holidays
                            (title, emoji, tint, description, mission, show_date, day_number, active, type, fact, tags)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        r[1:],
                    )
            conn.commit()
        flash("База данных успешно импортирована из CSV!", "success")
    except Exception as exc:
        logger.exception("Ошибка импорта CSV: %s", exc)
        flash("Ошибка при обработке CSV-файла. Данные не изменены.", "error")

    return redirect(url_for("admin.admin_dashboard"))


@admin_bp.route("/users", methods=["GET", "POST"])
@superadmin_required
def admin_users():
    with db_connection() as conn:
        if request.method == "POST":
            username = clip_text(request.form.get("username"), 80)
            password = (request.form.get("password") or "").strip()
            role = clip_text(request.form.get("role"), 20) or "editor"
            if role not in ("editor", "superadmin"):
                role = "editor"

            if not username or not password:
                flash("Логин и пароль обязательны для заполнения!", "error")
            elif len(password) < MIN_PASSWORD_LENGTH:
                flash(f"Пароль должен быть не короче {MIN_PASSWORD_LENGTH} символов.", "error")
            else:
                existing = conn.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone()
                if existing:
                    flash("Пользователь с таким именем уже существует!", "error")
                else:
                    hashed_pw = generate_password_hash(password)
                    conn.execute(
                        "INSERT INTO users (username, password_hash, role, avatar) VALUES (?, ?, ?, ?)",
                        (username, hashed_pw, role, "default.png"),
                    )
                    conn.commit()
                    flash("Новый администратор успешно добавлен!", "success")

            return redirect(url_for("admin.admin_users"))

        users = conn.execute("SELECT * FROM users ORDER BY id ASC").fetchall()
    return render_template("admin/users.html", users=users)


@admin_bp.route("/user_action/<int:user_id>/make_superadmin", methods=["POST"])
@superadmin_required
def make_superadmin(user_id):
    with db_connection() as conn:
        conn.execute("UPDATE users SET role = 'superadmin' WHERE id = ?", (user_id,))
        conn.commit()
    flash("Права пользователя успешно повышены до супер-администратора!", "success")
    return redirect(url_for("admin.admin_users"))


@admin_bp.route("/user_action/<int:user_id>/make_editor", methods=["POST"])
@superadmin_required
def make_editor(user_id):
    if user_id == session.get("user_id"):
        flash("Нельзя понизить самого себя.", "error")
        return redirect(url_for("admin.admin_users"))

    with db_connection() as conn:
        target = conn.execute("SELECT role FROM users WHERE id = ?", (user_id,)).fetchone()
        if target and target["role"] == "superadmin":
            super_count = conn.execute("SELECT COUNT(*) FROM users WHERE role = 'superadmin'").fetchone()[0]
            if super_count <= 1:
                flash("Нельзя понизить последнего супер-администратора.", "error")
                return redirect(url_for("admin.admin_users"))
        conn.execute("UPDATE users SET role = 'editor' WHERE id = ?", (user_id,))
        conn.commit()
    flash("Права пользователя изменены на редактора.", "success")
    return redirect(url_for("admin.admin_users"))


@admin_bp.route("/user_action/<int:user_id>/ban", methods=["POST"])
@superadmin_required
def ban_user(user_id):
    if user_id == session.get("user_id"):
        flash("Нельзя заблокировать самого себя.", "error")
        return redirect(url_for("admin.admin_users"))

    with db_connection() as conn:
        conn.execute("UPDATE users SET is_banned = 1 WHERE id = ?", (user_id,))
        conn.commit()
    flash("Пользователь заблокирован.", "success")
    return redirect(url_for("admin.admin_users"))


@admin_bp.route("/user_action/<int:user_id>/unban", methods=["POST"])
@superadmin_required
def unban_user(user_id):
    with db_connection() as conn:
        conn.execute("UPDATE users SET is_banned = 0 WHERE id = ?", (user_id,))
        conn.commit()
    flash("Пользователь разблокирован.", "success")
    return redirect(url_for("admin.admin_users"))


@admin_bp.route("/user_action/<int:user_id>/delete", methods=["POST"])
@superadmin_required
def delete_user(user_id):
    if user_id == session.get("user_id"):
        flash("Нельзя удалить самого себя.", "error")
        return redirect(url_for("admin.admin_users"))

    with db_connection() as conn:
        target = conn.execute("SELECT role, avatar FROM users WHERE id = ?", (user_id,)).fetchone()
        if not target:
            flash("Пользователь не найден.", "error")
            return redirect(url_for("admin.admin_users"))
        if target["role"] == "superadmin":
            super_count = conn.execute("SELECT COUNT(*) FROM users WHERE role = 'superadmin'").fetchone()[0]
            if super_count <= 1:
                flash("Нельзя удалить последнего супер-администратора.", "error")
                return redirect(url_for("admin.admin_users"))
        conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
        conn.commit()
        _delete_avatar_file(target["avatar"])

    flash("Пользователь успешно удален из системы.", "success")
    return redirect(url_for("admin.admin_users"))


@admin_bp.route("/profile", methods=["GET", "POST"])
@login_required
def admin_profile():
    user_id = session.get("user_id")

    with db_connection() as conn:
        if request.method == "POST":
            action = request.form.get("action")

            if action == "upload_avatar":
                file = request.files.get("avatar")
                if file and allowed_file(file.filename) and is_valid_image(file):
                    ext = os.path.splitext(file.filename)[1].lower()
                    if ext not in ALLOWED_AVATAR_EXTS:
                        ext = ".jpg"
                    filename = secrets.token_hex(8) + ext
                    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
                    file.save(os.path.join(UPLOAD_FOLDER, filename))

                    old_user = conn.execute("SELECT avatar FROM users WHERE id = ?", (user_id,)).fetchone()
                    old_avatar = old_user["avatar"] if old_user else None

                    conn.execute("UPDATE users SET avatar = ? WHERE id = ?", (filename, user_id))
                    conn.commit()
                    if old_avatar and old_avatar != filename:
                        _delete_avatar_file(old_avatar)
                    session["avatar"] = filename
                    flash("Аватар успешно обновлен!", "success")
                else:
                    flash("Ошибка при загрузке изображения.", "error")

            elif action == "delete_avatar":
                old_user = conn.execute("SELECT avatar FROM users WHERE id = ?", (user_id,)).fetchone()
                old_avatar = old_user["avatar"] if old_user else None

                conn.execute("UPDATE users SET avatar = ? WHERE id = ?", ("default.png", user_id))
                conn.commit()
                if old_avatar:
                    _delete_avatar_file(old_avatar)
                session["avatar"] = "default.png"
                flash("Аватарка удалена, установлен стандартный вариант.", "success")

            elif action == "change_password":
                old_password = request.form.get("old_password", "")
                new_password = (request.form.get("new_password") or "").strip()
                confirm_password = (request.form.get("confirm_password") or "").strip()

                user = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()

                if not user or not check_password_hash(user["password_hash"], old_password):
                    flash("Неверный старый пароль!", "error")
                elif not new_password or new_password != confirm_password:
                    flash("Новые пароли не совпадают или пусты!", "error")
                elif len(new_password) < MIN_PASSWORD_LENGTH:
                    flash(f"Новый пароль должен быть не короче {MIN_PASSWORD_LENGTH} символов.", "error")
                else:
                    hashed_pw = generate_password_hash(new_password)
                    conn.execute("UPDATE users SET password_hash = ? WHERE id = ?", (hashed_pw, user_id))
                    conn.commit()
                    flash("Пароль успешно изменен!", "success")

            return redirect(url_for("admin.admin_profile"))

        user = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        resolved_avatar = _resolve_avatar(user["avatar"] if user else None)
        if user and user["avatar"] != resolved_avatar:
            conn.execute("UPDATE users SET avatar = ? WHERE id = ?", (resolved_avatar, user_id))
            conn.commit()
        session["avatar"] = resolved_avatar
        user = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()

    return render_template("admin/profile.html", user=user)