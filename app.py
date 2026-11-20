import hmac
import os
import secrets
from flask import Flask, render_template, request, jsonify, abort, session
from jinja2 import TemplateNotFound
from werkzeug.middleware.proxy_fix import ProxyFix

from extensions import limiter
from routes.main import main_bp
from routes.admin import admin_bp


def create_app() -> Flask:
    app = Flask(__name__)

    secret_key = os.environ.get("SECRET_KEY")
    if not secret_key:
        secret_key = secrets.token_hex(32)
        print("⚠️ SECRET_KEY не задан в окружении — сгенерирован временный ключ для текущей сессии.")
    app.secret_key = secret_key

    app.config["MAX_CONTENT_LENGTH"] = 2 * 1024 * 1024
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    if os.environ.get("FLASK_ENV") == "production" or os.environ.get("HTTPS_ENABLED") == "1":
        app.config["SESSION_COOKIE_SECURE"] = True

    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)

    limiter.init_app(app)

    db_path = os.environ.get("DATABASE_PATH", "database.db")
    if not os.path.exists(db_path):
        from database import init_db
        init_db()

    upload_dir = os.path.join(app.root_path, "static", "uploads", "avatars")
    os.makedirs(upload_dir, exist_ok=True)

    def generate_csrf_token() -> str:
        token = session.get("_csrf_token")
        if not token:
            token = secrets.token_hex(16)
            session["_csrf_token"] = token
        return token

    app.jinja_env.globals["csrf_token"] = generate_csrf_token

    @app.before_request
    def csrf_protect():
        if request.method == "GET" and not request.path.startswith("/api/"):
            generate_csrf_token()
            return

        if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            expected_token = session.get("_csrf_token")
            provided_token = (
                request.form.get("_csrf_token")
                or request.headers.get("X-CSRF-Token")
            )
            if not expected_token or not provided_token:
                abort(400, description="Ошибка безопасности: Отсутствует CSRF-токен.")
            if not hmac.compare_digest(str(expected_token), str(provided_token)):
                abort(400, description="Ошибка безопасности: Неверный CSRF-токен.")

    @app.after_request
    def set_security_headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        return response

    def _wants_json() -> bool:
        return request.path.startswith("/api/") or request.is_json

    @app.errorhandler(400)
    def bad_request(e):
        description = getattr(e, "description", "Неверный запрос.")
        if _wants_json():
            return jsonify(error=description), 400
        try:
            return render_template("400.html", error_message=description), 400
        except TemplateNotFound:
            return render_template("404.html"), 400

    @app.errorhandler(404)
    def page_not_found(e):
        if _wants_json():
            return jsonify(error="Ресурс не найден."), 404
        return render_template("404.html"), 404

    @app.errorhandler(429)
    def ratelimit_handler(e):
        if _wants_json():
            return jsonify(error="Слишком много запросов."), 429
        try:
            return render_template("429.html"), 429
        except TemplateNotFound:
            return jsonify(error="Слишком много запросов."), 429

    app.register_blueprint(main_bp)
    app.register_blueprint(admin_bp)

    return app


app = create_app()

if __name__ == "__main__":
    app.run(debug=False, port=5000)