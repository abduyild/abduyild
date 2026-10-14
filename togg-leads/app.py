"""Togg Leads – Interessenten-Formular, Probefahrt-Warteschlange und Admin-Bereich.

Öffentlich:  /                Interessenten-Formular
             /warteschlange   Anmeldung zur Probefahrt (Warteschlange)
             /anzeige         Aufruf-Bildschirm für den Stand
Admin:       /admin           Interessenten, Warteschlange, Einstellungen (Passwort-geschützt)

Alle Daten liegen lokal im Ordner data/ (CSV + settings.json).
"""

import os
import secrets
import uuid
from datetime import datetime
from pathlib import Path

from flask import (
    Flask,
    abort,
    flash,
    redirect,
    render_template,
    request,
    send_from_directory,
    session,
    url_for,
)
from werkzeug.middleware.proxy_fix import ProxyFix

from core import (
    DATA_DIR,
    DEFAULTS,
    EMAIL_RE,
    MEDIA_DIR,
    PHONE_RE,
    SETTINGS_SCHEMA,
    ZIP_RE,
    add_lead,
    check_admin_password,
    check_csrf,
    csrf_token,
    csv_response,
    de_date,
    fill,
    get_settings,
    leads_table,
    lines,
    login_required,
    parse_ts,
    safe_cell,
    save_settings,
    set_admin_password,
    using_default_password,
    xlsx_response,
)
from queue_routes import bp as queue_bp

MEDIA_TYPES = {".png", ".jpg", ".jpeg", ".webp", ".svg", ".gif", ".ico"}


def _secret_key():
    if os.environ.get("TOGG_SECRET_KEY"):
        return os.environ["TOGG_SECRET_KEY"]
    path = DATA_DIR / ".secret_key"
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text(secrets.token_hex(32))
    return path.read_text().strip()


app = Flask(__name__)
app.secret_key = _secret_key()
app.config["MAX_CONTENT_LENGTH"] = 2 * 1024 * 1024
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
# Hinter `tailscale serve` / Reverse-Proxy die echte Adresse (https, Host) übernehmen
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)


# --------------------------------------------------------------------------- #
# Template-Helfer
# --------------------------------------------------------------------------- #
@app.context_processor
def inject_globals():
    cfg = get_settings()

    def media_url(key, default):
        name = cfg.get(key)
        if name and (MEDIA_DIR / name).exists():
            return url_for("media", filename=name)
        return url_for("static", filename=default)

    return {
        "csrf_token": csrf_token(),
        "cfg": cfg,
        "t": lambda key, **extra: fill(cfg.get(key, ""), cfg, **extra),
        "logo_url": media_url("logo", "togg-logo.png"),
        "favicon_url": media_url("favicon", "favicon.png"),
    }


app.add_template_filter(de_date, "de_date")


@app.template_filter("de_time")
def de_time(value):
    ts = parse_ts(value)
    return ts.strftime("%H:%M") if ts else ""


def interests_list(cfg=None):
    return lines((cfg or get_settings())["interests"])


# --------------------------------------------------------------------------- #
# Öffentliches Interessenten-Formular
# --------------------------------------------------------------------------- #
def validate_lead(form, interests):
    data = {
        "name": form.get("name", "").strip(),
        "email": form.get("email", "").strip(),
        "phone": form.get("phone", "").strip(),
        "zip_code": form.get("zip_code", "").strip(),
        "notes": form.get("notes", "").strip(),
        "interests": [i for i in form.getlist("interests") if i in interests],
        "consent": bool(form.get("consent")),
    }
    errors = {}
    if not data["name"]:
        errors["name"] = "Bitte geben Sie Ihren Namen an."
    if not EMAIL_RE.match(data["email"]):
        errors["email"] = "Bitte geben Sie eine gültige E-Mail-Adresse an."
    if data["phone"] and not PHONE_RE.match(data["phone"]):
        errors["phone"] = "Bitte geben Sie eine gültige Telefonnummer an."
    if data["zip_code"] and not ZIP_RE.match(data["zip_code"]):
        errors["zip_code"] = "Bitte geben Sie eine gültige Postleitzahl an."
    if interests and not data["interests"]:
        errors["interests"] = "Bitte wählen Sie mindestens ein Interesse."
    if len(data["notes"]) > 2000:
        errors["notes"] = "Maximal 2000 Zeichen."
    if not data["consent"]:
        errors["consent"] = "Bitte bestätigen Sie die Einwilligung."
    return data, errors


@app.route("/", methods=["GET", "POST"])
def index():
    cfg = get_settings()
    if not cfg["module_leads"]:
        if cfg["module_queue"]:
            return redirect(url_for("queue.signup"))
        abort(404)
    interests = interests_list(cfg)
    data, errors = {"interests": []}, {}
    if request.method == "POST":
        check_csrf()
        if request.form.get("website"):  # Honeypot gegen Spam-Bots
            return redirect(url_for("thanks"))
        data, errors = validate_lead(request.form, interests)
        if not errors:
            add_lead(data["name"], data["email"], data["phone"], data["zip_code"], data["interests"], data["notes"])
            return redirect(url_for("thanks"))
    return render_template("index.html", data=data, errors=errors, interests=interests)


@app.route("/danke")
def thanks():
    return render_template("thanks.html")


@app.route("/datenschutz")
def privacy():
    return render_template("privacy.html")


@app.route("/media/<path:filename>")
def media(filename):
    resp = send_from_directory(MEDIA_DIR, filename, max_age=3600)
    # Hochgeladene SVGs dürfen kein Script ausführen
    resp.headers["Content-Security-Policy"] = "default-src 'none'; style-src 'unsafe-inline'; img-src data:"
    resp.headers["X-Content-Type-Options"] = "nosniff"
    return resp


@app.route("/sw.js")
def service_worker():
    # Service Worker im Root-Scope, damit Benachrichtigungen auch auf Android funktionieren
    resp = send_from_directory(app.static_folder, "sw.js", max_age=0)
    resp.headers["Service-Worker-Allowed"] = "/"
    return resp


# --------------------------------------------------------------------------- #
# Admin: Login
# --------------------------------------------------------------------------- #
@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        check_csrf()
        if check_admin_password(request.form.get("password", "")):
            session["admin"] = True
            nxt = request.args.get("next", "")
            return redirect(nxt if nxt.startswith("/admin") else url_for("admin"))
        flash("Falsches Passwort.", "error")
    return render_template("login.html")


@app.route("/admin/logout", methods=["POST"])
def admin_logout():
    check_csrf()
    session.pop("admin", None)
    return redirect(url_for("admin_login"))


# --------------------------------------------------------------------------- #
# Admin: Interessenten
# --------------------------------------------------------------------------- #
def load_leads():
    leads = leads_table.all()
    for lead in leads:
        lead["interest_list"] = [i for i in lead["interests"].split("|") if i]
    return leads


def filtered_leads(q, interest):
    q = q.lower()
    return [
        l
        for l in reversed(load_leads())  # neueste zuerst
        if (not interest or interest in l["interest_list"])
        and (not q or q in " ".join([l["name"], l["email"], l["phone"], l["zip_code"], l["notes"]]).lower())
    ]


@app.route("/admin")
@login_required
def admin():
    cfg = get_settings()
    if not cfg["module_leads"] and cfg["module_queue"] and not request.args:
        return redirect(url_for("queue.admin_queue"))
    leads = load_leads()
    interests = interests_list(cfg)
    q = request.args.get("q", "").strip()
    interest = request.args.get("interest", "")
    if interest not in interests:
        interest = ""
    today = datetime.now().strftime("%Y-%m-%d")
    stats = [("Gesamt", len(leads), False)]
    stats += [(i, sum(i in l["interest_list"] for l in leads), True) for i in interests]
    stats.append(("Heute", sum(l["created_at"].startswith(today) for l in leads), False))
    return render_template(
        "admin.html",
        leads=filtered_leads(q, interest),
        total=len(leads),
        stats=stats,
        q=q,
        interest=interest,
        interests=interests,
        default_password=using_default_password(),
    )


@app.route("/admin/lead/<lead_id>/delete", methods=["POST"])
@login_required
def admin_delete(lead_id):
    check_csrf()
    with leads_table.edit() as rows:
        before = len(rows)
        rows[:] = [r for r in rows if r["id"] != lead_id]
        if len(rows) == before:
            abort(404)
    return redirect(url_for("admin", q=request.form.get("q", ""), interest=request.form.get("interest", "")))


def lead_export_rows():
    interests = interests_list()
    header = ["Datum", "Name", "E-Mail", "Telefon", "PLZ", *interests, "Notizen", "Quelle", "Einwilligung"]
    rows = []
    for l in filtered_leads(request.args.get("q", ""), request.args.get("interest", "")):
        rows.append(
            [
                de_date(l["created_at"]),
                safe_cell(l["name"]),
                safe_cell(l["email"]),
                safe_cell(l["phone"]),
                l["zip_code"],
                *["Ja" if i in l["interest_list"] else "Nein" for i in interests],
                safe_cell(l["notes"]),
                l["source"] or "Formular",
                de_date(l["consent"]),
            ]
        )
    return header, rows


@app.route("/admin/export.csv")
@login_required
def export_csv():
    return csv_response(*lead_export_rows(), "interessenten")


@app.route("/admin/export.xlsx")
@login_required
def export_xlsx():
    return xlsx_response(*lead_export_rows(), "interessenten", "Interessenten")


# --------------------------------------------------------------------------- #
# Admin: Einstellungen
# --------------------------------------------------------------------------- #
def _store_upload(key, file):
    ext = Path(file.filename or "").suffix.lower()
    if ext not in MEDIA_TYPES:
        raise ValueError("Dateityp nicht erlaubt (PNG, JPG, WebP, SVG, GIF, ICO).")
    MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    name = f"{key}-{uuid.uuid4().hex[:8]}{ext}"
    file.save(MEDIA_DIR / name)
    return name


def _remove_media(name):
    if name:
        (MEDIA_DIR / Path(name).name).unlink(missing_ok=True)


@app.route("/admin/einstellungen", methods=["GET", "POST"])
@login_required
def admin_settings():
    cfg = get_settings()
    if request.method == "POST":
        check_csrf()
        updates, errors = {}, []
        for _, fields in SETTINGS_SCHEMA:
            for key, label, kind, _ in fields:
                if kind == "bool":
                    updates[key] = key in request.form
                elif kind == "int":
                    try:
                        updates[key] = max(1, min(int(request.form.get(key, "")), 600))
                    except ValueError:
                        errors.append(f"{label}: bitte eine Zahl eingeben.")
                elif kind == "file":
                    upload = request.files.get(key)
                    if request.form.get(f"{key}_reset"):
                        _remove_media(cfg.get(key))
                        updates[key] = ""
                    elif upload and upload.filename:
                        try:
                            updates[key] = _store_upload(key, upload)
                            _remove_media(cfg.get(key))
                        except ValueError as exc:
                            errors.append(f"{label}: {exc}")
                elif kind == "color":
                    value = request.form.get(key, "")
                    if len(value) == 7 and value.startswith("#"):
                        updates[key] = value
                else:
                    updates[key] = request.form.get(key, "").replace("\r\n", "\n").strip()
        if not lines(updates.get("interests", "x")):
            errors.append("Bitte mindestens ein Interesse angeben.")
            updates.pop("interests")

        pw, pw2 = request.form.get("new_password", ""), request.form.get("new_password2", "")
        if pw or pw2:
            if pw != pw2:
                errors.append("Die Passwörter stimmen nicht überein.")
            elif len(pw) < 6:
                errors.append("Das Passwort muss mindestens 6 Zeichen haben.")
            else:
                set_admin_password(pw)
                flash("Admin-Passwort geändert.", "success")

        save_settings(updates)
        for err in errors:
            flash(err, "error")
        if not errors:
            flash("Einstellungen gespeichert.", "success")
        return redirect(url_for("admin_settings"))
    return render_template("settings.html", schema=SETTINGS_SCHEMA, default_password=using_default_password())


@app.route("/admin/einstellungen/reset", methods=["POST"])
@login_required
def admin_settings_reset():
    """Alle Texte und Marken-Einstellungen auf Standard (Togg) zurücksetzen. Passwort bleibt."""
    check_csrf()
    cfg = get_settings()
    _remove_media(cfg.get("logo"))
    _remove_media(cfg.get("favicon"))
    save_settings({k: v for k, v in DEFAULTS.items() if k != "admin_password_hash"})
    flash("Einstellungen auf Standard zurückgesetzt.", "success")
    return redirect(url_for("admin_settings"))


@app.errorhandler(413)
def too_large(_):
    flash("Datei ist zu groß (max. 2 MB).", "error")
    return redirect(request.referrer or url_for("admin"))


app.register_blueprint(queue_bp)


if __name__ == "__main__":
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", 5000))
    if using_default_password():
        print("WARNUNG: Standard-Admin-Passwort 'admin' aktiv – bitte unter /admin/einstellungen ändern!")
    try:
        from waitress import serve

        print(f"Togg Leads läuft auf http://{host}:{port}  (Admin: /admin)")
        serve(app, host=host, port=port, threads=8)
    except ImportError:
        app.run(host=host, port=port, debug=False)
