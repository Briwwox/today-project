from flask import Flask, render_template, jsonify, request, redirect, url_for, session, flash, Response, abort
import sqlite3
from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from werkzeug.middleware.proxy_fix import ProxyFix
import os
import re
import csv
import io
import secrets
from functools import wraps
from PIL import Image

from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

app = Flask(__name__)

# ==========================================
# БЕЗОПАСНОСТЬ: SECRET_KEY
# ==========================================
app.secret_key = os.environ.get('SECRET_KEY')
if not app.secret_key:
    if os.environ.get('RENDER') or os.environ.get('FLASK_ENV') == 'production':
        raise RuntimeError(
            "❌ SECRET_KEY обязателен в продакшене! "
            "Установите переменную окружения SECRET_KEY."
        )
    app.secret_key = 'local-dev-only-key'

app.config['MAX_CONTENT_LENGTH'] = 2 * 1024 * 1024

# ==========================================
# ПРОКСИ (нужен на Render/Heroku за балансировщиком)
# ==========================================
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)

# ==========================================
# RATE LIMITER
# ==========================================
limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["500 per day", "100 per hour"],
    storage_uri="memory://",
)

UPLOAD_FOLDER = os.path.join('static', 'uploads', 'avatars')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

# ==========================================
# АВТОСОЗДАНИЕ БД ПРИ СТАРТЕ
# ==========================================
if not os.path.exists('database.db'):
    from database import init_db
    init_db()


def get_db_connection():
    conn = sqlite3.connect('database.db')
    conn.row_factory = sqlite3.Row
    return conn


# ==========================================
# CSRF-ЗАЩИТА
# ==========================================
def generate_csrf_token():
    if '_csrf_token' not in session:
        session['_csrf_token'] = secrets.token_hex(16)
    return session['_csrf_token']

app.jinja_env.globals['csrf_token'] = generate_csrf_token


@app.before_request
def csrf_protect():
    if request.method == "POST":
        token = session.get('_csrf_token')
        form_token = request.form.get('_csrf_token')
        if not token or token != form_token:
            abort(400, description="Ошибка безопасности: Неверный CSRF-токен. Обновите страницу и попробуйте снова.")


# ==========================================
# SECURITY HEADERS
# ==========================================
@app.after_request
def set_security_headers(response):
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'SAMEORIGIN'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    response.headers['Permissions-Policy'] = 'geolocation=(), microphone=()'
    return response


# ==========================================
# ДЕКОРАТОРЫ И ХЕЛПЕРЫ
# ==========================================
def login_required(f):
    """Проверяет сессию + актуальное состояние пользователя в БД."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        uid = session.get('user_id')
        if not uid:
            return redirect(url_for('admin_login'))
        conn = get_db_connection()
        user = conn.execute(
            'SELECT is_banned, role, avatar, username FROM users WHERE id = ?', (uid,)
        ).fetchone()
        conn.close()
        if not user or user['is_banned'] == 1:
            session.clear()
            return redirect(url_for('admin_login'))
        # Синхронизируем актуальные данные в сессии
        session['role'] = user['role']
        session['avatar'] = user['avatar']
        session['username'] = user['username']
        return f(*args, **kwargs)
    return decorated_function


def superadmin_required(f):
    """Проверяет, что пользователь — супер-админ (с актуальной проверкой БД)."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        uid = session.get('user_id')
        if not uid:
            return redirect(url_for('admin_login'))
        conn = get_db_connection()
        user = conn.execute('SELECT is_banned, role FROM users WHERE id = ?', (uid,)).fetchone()
        conn.close()
        if not user or user['is_banned'] == 1:
            session.clear()
            return redirect(url_for('admin_login'))
        session['role'] = user['role']
        if user['role'] != 'superadmin':
            return "Доступ запрещен. Вы не Супер-Админ.", 403
        return f(*args, **kwargs)
    return decorated_function


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def is_valid_image(file_stream):
    try:
        img = Image.open(file_stream)
        img.verify()
        file_stream.seek(0)
        return True
    except Exception:
        return False


def is_valid_hex_color(color):
    if color and len(color) == 7 and color.startswith('#'):
        try:
            int(color[1:], 16)
            return True
        except ValueError:
            return False
    return False


def parse_show_date(show_date):
    """Возвращает day_number из 'ММ-ДД' или None, если формат неверный."""
    if not show_date:
        return None
    show_date = show_date.strip()
    if not re.fullmatch(r'\d{2}-\d{2}', show_date):
        return None
    try:
        month, day = map(int, show_date.split('-'))
        return (datetime(2023, month, day) - datetime(2023, 1, 1)).days + 1
    except (ValueError, TypeError):
        return None


# ==========================================
# ОБРАБОТЧИКИ ОШИБОК
# ==========================================
@app.errorhandler(429)
def ratelimit_handler(e):
    if request.path.startswith('/api/'):
        return jsonify(error=f"Слишком много запросов. Пожалуйста, подождите. Лимит: {e.description}"), 429
    return render_template('429.html'), 429


@app.errorhandler(413)
def too_large_handler(e):
    if request.path.startswith('/api/'):
        return jsonify(error="Файл слишком большой (макс. 2 МБ)"), 413
    flash('Файл слишком большой (максимум 2 МБ)', 'error')
    return redirect(request.referrer or url_for('admin_profile'))


@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404


@app.errorhandler(400)
def bad_request(e):
    return f"<h1>Ошибка 400</h1><p>{e.description}</p><a href='/admin'>Вернуться назад</a>", 400


# ==========================================
# МАРШРУТЫ
# ==========================================
@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/yesterday')
@limiter.limit("120 per minute")
def api_yesterday():
    conn = get_db_connection()
    now = datetime.now()
    yesterday = now - timedelta(days=1)
    day_number = (yesterday - datetime(yesterday.year, 1, 1)).days + 1
    is_leap = (yesterday.year % 4 == 0 and (yesterday.year % 100 != 0 or yesterday.year % 400 == 0))
    search_day = day_number - 1 if (is_leap and day_number > 59) else day_number
    holiday = conn.execute('SELECT * FROM holidays WHERE day_number = ? AND active = 1', (search_day,)).fetchone()
    conn.close()
    if not holiday:
        return jsonify({"error": "Нет праздников"}), 404
    return jsonify({
        "id": holiday["id"], "title": holiday["title"], "emoji": holiday["emoji"],
        "tint": holiday["tint"], "description": holiday["description"],
        "mission": holiday["mission"], "day_number": f"ВЧЕРА БЫЛ ДЕНЬ №{day_number}"
    })


@app.route('/api/today')
@limiter.limit("120 per minute")
def api_today():
    conn = get_db_connection()
    now = datetime.now()
    day_number = (now - datetime(now.year, 1, 1)).days + 1
    is_leap = (now.year % 4 == 0 and (now.year % 100 != 0 or now.year % 400 == 0))
    search_day = day_number - 1 if (is_leap and day_number > 59) else day_number
    holiday = conn.execute('SELECT * FROM holidays WHERE day_number = ? AND active = 1', (search_day,)).fetchone()
    conn.close()
    if not holiday:
        return jsonify({"error": "Нет праздников"}), 404
    return jsonify({
        "id": holiday["id"], "title": holiday["title"], "emoji": holiday["emoji"],
        "tint": holiday["tint"], "description": holiday["description"],
        "mission": holiday["mission"], "day_number": f"ДЕНЬ №{day_number}"
    })


@app.route('/api/random')
@limiter.limit("120 per minute")
def api_random():
    conn = get_db_connection()
    holiday = conn.execute('SELECT * FROM holidays WHERE active = 1 ORDER BY RANDOM() LIMIT 1').fetchone()
    conn.close()
    if not holiday:
        return jsonify({"error": "Нет праздников"}), 404
    return jsonify({
        "id": holiday["id"], "title": holiday["title"], "emoji": holiday["emoji"],
        "tint": holiday["tint"], "description": holiday["description"],
        "mission": holiday["mission"], "day_number": "СЛУЧАЙНЫЙ ПРАЗДНИК"
    })


@app.route('/admin/login', methods=['GET', 'POST'])
@limiter.limit("5 per minute", methods=["POST"])
def admin_login():
    error = None
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        conn = get_db_connection()
        user = conn.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()

        if user and check_password_hash(user['password_hash'], password):
            if user['is_banned'] == 1:
                error = 'Ваш аккаунт заблокирован!'
            else:
                conn.execute('UPDATE users SET last_login = CURRENT_TIMESTAMP WHERE id = ?', (user['id'],))
                conn.commit()
                session.clear()
                session['user_id'] = user['id']
                session['username'] = user['username']
                session['role'] = user['role']
                session['avatar'] = user['avatar']
                conn.close()
                return redirect(url_for('admin_dashboard'))
        else:
            error = 'Неверный логин или пароль'
        conn.close()

    return render_template('admin/login.html', error=error)


@app.route('/admin')
@login_required
def admin_dashboard():
    search_query = request.args.get('q', '').strip()
    conn = get_db_connection()
    query = 'SELECT * FROM holidays'
    params = []

    if search_query:
        query += ' WHERE title LIKE ? OR description LIKE ?'
        params.extend([f'%{search_query}%', f'%{search_query}%'])

    query += ' ORDER BY day_number ASC'
    holidays = conn.execute(query, params).fetchall()

    total_all = conn.execute('SELECT COUNT(*) FROM holidays').fetchone()[0]
    total_active = conn.execute('SELECT COUNT(*) FROM holidays WHERE active = 1').fetchone()[0]
    conn.close()

    months_dict = {1: "Январь", 2: "Февраль", 3: "Март", 4: "Апрель", 5: "Май", 6: "Июнь",
                   7: "Июль", 8: "Август", 9: "Сентябрь", 10: "Октябрь", 11: "Ноябрь", 12: "Декабрь"}

    grouped_holidays = {i: [] for i in range(1, 13)}
    for h in holidays:
        date_obj = datetime(2023, 1, 1) + timedelta(days=h['day_number'] - 1)
        grouped_holidays[date_obj.month].append(h)

    return render_template('admin/dashboard.html',
                           grouped_holidays=grouped_holidays,
                           months_dict=months_dict,
                           search_query=search_query,
                           total_all=total_all,
                           total_active=total_active,
                           total_inactive=total_all - total_active,
                           total_filtered=len(holidays))


@app.route('/admin/profile', methods=['GET', 'POST'])
@login_required
def admin_profile():
    conn = get_db_connection()
    user_id = session['user_id']

    if request.method == 'POST':
        action = request.form.get('action')

        if action == 'change_password':
            old_pass = request.form.get('old_password')
            new_pass = request.form.get('new_password')
            confirm_pass = request.form.get('confirm_password')

            user = conn.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()

            if not check_password_hash(user['password_hash'], old_pass):
                flash('Старый пароль неверный', 'error')
            elif len(new_pass) < 8:
                flash('Пароль должен быть не короче 8 символов', 'error')
            elif new_pass != confirm_pass:
                flash('Новые пароли не совпадают', 'error')
            else:
                new_hash = generate_password_hash(new_pass)
                conn.execute('UPDATE users SET password_hash = ? WHERE id = ?', (new_hash, user_id))
                conn.commit()
                session.clear()
                flash('Пароль успешно изменен! Пожалуйста, войдите заново.', 'success')
                return redirect(url_for('admin_login'))

        elif action == 'upload_avatar':
            if 'avatar' not in request.files:
                flash('Нет файла', 'error')
            else:
                file = request.files['avatar']
                if file.filename == '':
                    flash('Файл не выбран', 'error')
                elif file and allowed_file(file.filename):
                    if is_valid_image(file):
                        filename = secure_filename(f"user_{user_id}_{file.filename}")
                        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                        file.save(filepath)
                        conn.execute('UPDATE users SET avatar = ? WHERE id = ?', (filename, user_id))
                        conn.commit()
                        session['avatar'] = filename
                        flash('Аватарка обновлена!', 'success')
                    else:
                        flash('Файл поврежден или не является картинкой!', 'error')
                else:
                    flash('Недопустимый формат файла', 'error')

    user = conn.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()
    conn.close()
    return render_template('admin/profile.html', user=user)


@app.route('/admin/users', methods=['GET', 'POST'])
@superadmin_required
def admin_users():
    conn = get_db_connection()
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'add_user':
            username = request.form.get('username')
            password = request.form.get('password')
            role = request.form.get('role', 'editor')
            if len(password) < 8:
                flash('Пароль должен быть не короче 8 символов', 'error')
            else:
                try:
                    new_hash = generate_password_hash(password)
                    conn.execute('INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)',
                                 (username, new_hash, role))
                    conn.commit()
                    flash(f'Пользователь {username} добавлен!', 'success')
                except sqlite3.IntegrityError:
                    flash('Логин уже занят', 'error')

    users = conn.execute('SELECT * FROM users ORDER BY role DESC, id ASC').fetchall()
    conn.close()
    return render_template('admin/users.html', users=users)


@app.route('/admin/user_action/<int:id>/<action>', methods=['POST'])
@superadmin_required
def admin_user_action(id, action):
    conn = get_db_connection()
    user = conn.execute('SELECT username FROM users WHERE id = ?', (id,)).fetchone()

    if user and user['username'] != 'admin':
        if action == 'ban':
            conn.execute('UPDATE users SET is_banned = 1 WHERE id = ?', (id,))
        elif action == 'unban':
            conn.execute('UPDATE users SET is_banned = 0 WHERE id = ?', (id,))
        elif action == 'make_editor':
            conn.execute("UPDATE users SET role = 'editor' WHERE id = ?", (id,))
        elif action == 'make_superadmin':
            conn.execute("UPDATE users SET role = 'superadmin' WHERE id = ?", (id,))
        elif action == 'delete':
            conn.execute('DELETE FROM users WHERE id = ?', (id,))
            flash('Пользователь удален', 'success')
        conn.commit()
    else:
        flash('Нельзя изменить главного администратора!', 'error')
    conn.close()
    return redirect(url_for('admin_users'))


@app.route('/admin/add', methods=['GET', 'POST'])
@login_required
def admin_add():
    if request.method == 'POST':
        title = request.form.get('title')
        emoji = request.form.get('emoji')
        tint = request.form.get('tint')
        description = request.form.get('description')
        mission = request.form.get('mission')
        show_date = request.form.get('show_date', '').strip()
        active = 1 if request.form.get('active') else 0

        if not is_valid_hex_color(tint):
            tint = '#f8dfe3'

        day_number = parse_show_date(show_date)
        if show_date and not day_number:
            flash('Дата должна быть в формате ММ-ДД (например, 11-16)', 'error')
            return render_template('admin/form.html', holiday=None, title_text='Добавить праздник ✨')

        conn = get_db_connection()
        if not day_number:
            max_day = conn.execute('SELECT MAX(day_number) FROM holidays').fetchone()[0]
            day_number = (max_day or 0) + 1

        conn.execute(
            'INSERT INTO holidays (title, emoji, tint, description, mission, show_date, day_number, active) '
            'VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
            (title, emoji, tint, description, mission, show_date, day_number, active))
        conn.commit()
        conn.close()
        return redirect(url_for('admin_dashboard'))
    return render_template('admin/form.html', holiday=None, title_text='Добавить праздник ✨')


@app.route('/admin/edit/<int:id>', methods=['GET', 'POST'])
@login_required
def admin_edit(id):
    q = request.args.get('q', '')
    conn = get_db_connection()
    if request.method == 'POST':
        title = request.form.get('title')
        emoji = request.form.get('emoji')
        tint = request.form.get('tint')
        description = request.form.get('description')
        mission = request.form.get('mission')
        show_date = request.form.get('show_date', '').strip()
        active = 1 if request.form.get('active') else 0

        if not is_valid_hex_color(tint):
            tint = '#f8dfe3'

        day_number = parse_show_date(show_date)
        if show_date and not day_number:
            flash('Дата должна быть в формате ММ-ДД (например, 11-16)', 'error')
            holiday = conn.execute('SELECT * FROM holidays WHERE id = ?', (id,)).fetchone()
            conn.close()
            return render_template('admin/form.html', holiday=holiday, title_text='Редактировать праздник ✨')

        if day_number:
            conn.execute(
                'UPDATE holidays SET title=?, emoji=?, tint=?, description=?, mission=?, '
                'show_date=?, day_number=?, active=? WHERE id=?',
                (title, emoji, tint, description, mission, show_date, day_number, active, id))
        else:
            conn.execute(
                'UPDATE holidays SET title=?, emoji=?, tint=?, description=?, mission=?, '
                'show_date=?, active=? WHERE id=?',
                (title, emoji, tint, description, mission, show_date, active, id))
        conn.commit()
        conn.close()
        return redirect(url_for('admin_dashboard', q=q))

    holiday = conn.execute('SELECT * FROM holidays WHERE id = ?', (id,)).fetchone()
    conn.close()
    return render_template('admin/form.html', holiday=holiday, title_text='Редактировать праздник ✨')


@app.route('/admin/toggle/<int:id>', methods=['POST'])
@login_required
def admin_toggle(id):
    q = request.form.get('q', '')
    conn = get_db_connection()
    conn.execute('UPDATE holidays SET active = 1 - active WHERE id = ?', (id,))
    conn.commit()
    conn.close()
    return redirect(url_for('admin_dashboard', q=q))


@app.route('/admin/delete/<int:id>', methods=['POST'])
@superadmin_required
def admin_delete(id):
    q = request.form.get('q', '')
    conn = get_db_connection()
    conn.execute('DELETE FROM holidays WHERE id = ?', (id,))
    conn.commit()
    conn.close()
    return redirect(url_for('admin_dashboard', q=q))


@app.route('/admin/export')
@login_required
def admin_export():
    conn = get_db_connection()
    holidays = conn.execute('SELECT * FROM holidays ORDER BY day_number ASC').fetchall()
    conn.close()
    si = io.StringIO()
    cw = csv.writer(si, quoting=csv.QUOTE_MINIMAL, lineterminator='\n')
    cw.writerow(['title', 'emoji', 'tint', 'description', 'mission', 'show_date', 'day_number', 'active'])
    for h in holidays:
        cw.writerow([h['title'], h['emoji'], h['tint'], h['description'],
                     h['mission'], h['show_date'], h['day_number'], h['active']])
    output = si.getvalue().encode('utf-8-sig')
    return Response(output, mimetype="text/csv",
                    headers={"Content-Disposition": "attachment;filename=holidays_backup.csv"})


@app.route('/admin/import', methods=['POST'])
@superadmin_required
def admin_import():
    if 'file' not in request.files:
        flash('Файл не найден', 'error')
        return redirect(url_for('admin_dashboard'))
    file = request.files['file']
    if file.filename == '':
        flash('Файл не выбран', 'error')
        return redirect(url_for('admin_dashboard'))

    if file and file.filename.endswith('.csv'):
        try:
            stream = io.StringIO(file.stream.read().decode("utf-8-sig"), newline=None)
            csv_input = csv.reader(stream)
            next(csv_input, None)

            conn = get_db_connection()
            conn.execute('DELETE FROM holidays')

            inserted = 0
            skipped = 0
            for row in csv_input:
                if len(row) < 8:
                    skipped += 1
                    continue
                try:
                    day_num = int(float(row[6]))
                    active_val = int(float(row[7]))
                except (ValueError, TypeError, IndexError):
                    skipped += 1
                    continue
                conn.execute(
                    'INSERT INTO holidays (title, emoji, tint, description, mission, show_date, day_number, active) '
                    'VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
                    (row[0], row[1], row[2], row[3], row[4], row[5], day_num, active_val))
                inserted += 1

            conn.commit()
            conn.close()
            msg = f'Импорт завершён: добавлено {inserted}'
            if skipped:
                msg += f', пропущено {skipped} битых строк'
            flash(msg, 'success' if inserted else 'error')
        except Exception as e:
            flash(f'Ошибка при импорте: {str(e)}', 'error')
    else:
        flash('Неверный формат файла. Нужен .csv', 'error')
    return redirect(url_for('admin_dashboard'))


@app.route('/admin/logout')
def admin_logout():
    session.clear()
    return redirect(url_for('admin_login'))


if __name__ == '__main__':
    app.run(debug=False, port=5000)