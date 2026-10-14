"""Probefahrt-Warteschlange: Anmeldung am Stand, Live-Status, Aufruf-Anzeige und Admin."""

import io
import math
import re
import secrets
import uuid
from datetime import datetime
from urllib.parse import quote

from flask import Blueprint, Response, abort, jsonify, redirect, render_template, request, url_for

from core import (
    EMAIL_RE,
    PHONE_RE,
    add_lead,
    check_csrf,
    csv_response,
    fill,
    get_settings,
    lines,
    login_required,
    now,
    parse_ts,
    queue_table,
    safe_cell,
    xlsx_response,
)

bp = Blueprint("queue", __name__)

WAITING, CALLED, DRIVING, DONE, NO_SHOW, CANCELLED = (
    "wartend", "aufgerufen", "unterwegs", "fertig", "nicht_erschienen", "abgesagt",
)
ACTIVE = (WAITING, CALLED, DRIVING)
LABELS = {
    WAITING: "Wartet",
    CALLED: "Aufgerufen",
    DRIVING: "Unterwegs",
    DONE: "Erledigt",
    NO_SHOW: "Nicht erschienen",
    CANCELLED: "Abgesagt",
}


# --------------------------------------------------------------------------- #
# Hilfsfunktionen
# --------------------------------------------------------------------------- #
def _require_module():
    if not get_settings()["module_queue"]:
        abort(404)


def _today():
    return datetime.now().strftime("%Y-%m-%d")


def _sort_key(e):
    return (e["created_at"], int(e["number"] or 0))


def _duration_seconds(e):
    start, end = parse_ts(e["started_at"]), parse_ts(e["ended_at"])
    if start and end:
        return max(0, int((end - start).total_seconds()))
    return None


def fmt_duration(seconds):
    if seconds is None:
        return "–"
    h, rest = divmod(seconds, 3600)
    m, s = divmod(rest, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def avg_drive_minutes(rows, cfg):
    """Echter Durchschnitt der letzten 20 Fahrten (mit Tracking), sonst Einstellung."""
    if cfg["tracking_enabled"]:
        durations = [d for d in (_duration_seconds(e) for e in rows if e["status"] == DONE) if d]
        durations = durations[-20:]
        if len(durations) >= 3:
            return max(1, round(sum(durations) / len(durations) / 60))
    return int(cfg["drive_minutes"])


def queue_state(rows, cfg):
    waiting = sorted((e for e in rows if e["status"] == WAITING), key=_sort_key)
    busy = sum(e["status"] in (CALLED, DRIVING) for e in rows)
    cars = max(1, int(cfg["cars_count"]))
    avg = avg_drive_minutes(rows, cfg)

    def eta(ahead):
        """Grobe Schätzung in Minuten, auf 5 Minuten gerundet."""
        rounds = (ahead + busy) // cars
        if rounds == 0:
            return 0
        return int(math.ceil(rounds * avg / 5.0) * 5)

    return waiting, busy, avg, eta


def phone_digits(phone):
    """Telefonnummer für wa.me: nur Ziffern, deutsche 0… → 49…"""
    digits = re.sub(r"\D", "", phone or "")
    if phone.strip().startswith("+"):
        return digits
    if digits.startswith("00"):
        return digits[2:]
    if digits.startswith("0"):
        return "49" + digits[1:]
    return digits


def contact_links(e, cfg):
    msg = fill(cfg["contact_message"], cfg, name=e["name"].split(" ")[0], nummer=e["number"])
    phone = e["phone"].strip()
    return {
        "tel": f"tel:{re.sub(r'[^0-9+]', '', phone)}",
        "sms": f"sms:{re.sub(r'[^0-9+]', '', phone)}?&body={quote(msg)}",
        "whatsapp": f"https://wa.me/{phone_digits(phone)}?text={quote(msg)}",
    }


def public_base():
    base = get_settings()["public_url"].strip().rstrip("/")
    return base or request.url_root.rstrip("/")


def find_by_token(rows, token):
    entry = next((e for e in rows if secrets.compare_digest(e["token"], token)), None)
    if entry is None:
        abort(404)
    return entry


def status_payload(entry, rows, cfg):
    waiting, _, _, eta = queue_state(rows, cfg)
    ahead = next((i for i, e in enumerate(waiting) if e["id"] == entry["id"]), None)
    return {
        "number": entry["number"],
        "status": entry["status"],
        "label": LABELS.get(entry["status"], entry["status"]),
        "ahead": ahead,
        "eta": eta(ahead) if (ahead is not None and cfg["show_eta"]) else None,
        "called_at": entry["called_at"],
    }


# --------------------------------------------------------------------------- #
# Öffentlich: Anmeldung, Status, Anzeige
# --------------------------------------------------------------------------- #
@bp.route("/warteschlange", methods=["GET", "POST"])
def signup():
    _require_module()
    cfg = get_settings()
    kiosk = request.values.get("kiosk") == "1"
    data, errors = {}, {}
    if request.method == "POST":
        check_csrf()
        if request.form.get("website"):  # Honeypot
            return redirect(url_for("queue.signup", kiosk="1" if kiosk else None))
        data = {k: request.form.get(k, "").strip() for k in ("name", "phone", "email")}
        if not data["name"]:
            errors["name"] = "Bitte geben Sie Ihren Namen an."
        if not PHONE_RE.match(data["phone"]):
            errors["phone"] = "Bitte geben Sie eine gültige Telefonnummer an."
        if data["email"] and not EMAIL_RE.match(data["email"]):
            errors["email"] = "Bitte geben Sie eine gültige E-Mail-Adresse an."
        if not request.form.get("consent"):
            errors["consent"] = "Bitte bestätigen Sie die Einwilligung."
        if not errors:
            today = _today()
            entry = {
                "id": uuid.uuid4().hex[:10],
                "token": secrets.token_urlsafe(12),
                "day": today,
                "name": data["name"],
                "phone": data["phone"],
                "email": data["email"],
                "consent": now(),
                "status": WAITING,
                "created_at": now(),
            }
            with queue_table.edit() as rows:
                numbers = [int(e["number"]) for e in rows if e["day"] == today and e["number"].isdigit()]
                entry["number"] = str(max(numbers, default=0) + 1)
                rows.append(entry)
            if cfg["queue_also_lead"]:
                interests = lines(cfg["interests"])
                interest = next((i for i in interests if "fahrt" in i.lower()), interests[0] if interests else "")
                add_lead(
                    data["name"], data["email"], data["phone"], "", [interest] if interest else [],
                    f"Stand-Warteschlange Nr. {entry['number']}", source="Warteschlange",
                )
            if kiosk:
                return redirect(url_for("queue.ticket", token=entry["token"]))
            return redirect(url_for("queue.status", token=entry["token"]))
    return render_template("queue_signup.html", data=data, errors=errors, kiosk=kiosk, state=display_payload())


@bp.route("/warteschlange/ticket/<token>")
def ticket(token):
    """Kiosk-Ansicht nach der Anmeldung: Nummer + QR-Code für das eigene Handy."""
    _require_module()
    entry = find_by_token(queue_table.all(), token)
    status_url = public_base() + url_for("queue.status", token=token)
    return render_template("queue_ticket.html", entry=entry, status_url=status_url)


@bp.route("/q/<token>")
def status(token):
    _require_module()
    rows = queue_table.all()
    cfg = get_settings()
    entry = find_by_token(rows, token)
    return render_template("queue_status.html", entry=entry, state=status_payload(entry, rows, cfg))


@bp.route("/q/<token>.json")
def status_json(token):
    _require_module()
    rows = queue_table.all()
    entry = find_by_token(rows, token)
    resp = jsonify(status_payload(entry, rows, get_settings()))
    resp.headers["Cache-Control"] = "no-store"
    return resp


@bp.route("/q/<token>/absagen", methods=["POST"])
def cancel(token):
    _require_module()
    check_csrf()
    with queue_table.edit() as rows:
        entry = find_by_token(rows, token)
        if entry["status"] in (WAITING, CALLED):
            entry["status"] = CANCELLED
            entry["ended_at"] = now()
    return redirect(url_for("queue.status", token=token))


def display_payload():
    rows = queue_table.all()
    cfg = get_settings()
    waiting, _, _, eta = queue_state(rows, cfg)
    called = sorted((e for e in rows if e["status"] == CALLED), key=lambda e: e["called_at"], reverse=True)
    return {
        "called": [e["number"] for e in called],
        "last_called_at": max((e["called_at"] for e in called), default=""),
        "next": [e["number"] for e in waiting[:6]],
        "waiting": len(waiting),
        "eta": eta(len(waiting)) if cfg["show_eta"] else None,
    }


@bp.route("/anzeige")
def display():
    _require_module()
    signup_url = public_base() + url_for("queue.signup")
    return render_template("display.html", state=display_payload(), signup_url=signup_url)


@bp.route("/anzeige.json")
def display_json():
    _require_module()
    resp = jsonify(display_payload())
    resp.headers["Cache-Control"] = "no-store"
    return resp


@bp.route("/qr.svg")
def qr_svg():
    """QR-Code nur für Adressen dieser App (kein offener QR-Generator)."""
    import qrcode
    import qrcode.image.svg

    path = request.args.get("p", "/")
    if not path.startswith("/") or path.startswith("//"):
        abort(400)
    img = qrcode.make(public_base() + path, image_factory=qrcode.image.svg.SvgPathImage, box_size=20, border=2)
    buf = io.BytesIO()
    img.save(buf)
    resp = Response(buf.getvalue(), mimetype="image/svg+xml")
    resp.headers["Cache-Control"] = "no-store"
    return resp


# --------------------------------------------------------------------------- #
# Admin
# --------------------------------------------------------------------------- #
def admin_context():
    cfg = get_settings()
    rows = queue_table.all()
    waiting, busy, avg, eta = queue_state(rows, cfg)
    today = _today()
    called = sorted((e for e in rows if e["status"] == CALLED), key=lambda e: e["called_at"])
    driving = sorted((e for e in rows if e["status"] == DRIVING), key=lambda e: e["started_at"])
    finished = sorted(
        (e for e in rows if e["status"] in (DONE, NO_SHOW, CANCELLED) and e["day"] == today),
        key=lambda e: e["ended_at"] or e["created_at"],
        reverse=True,
    )
    drives_today = [e for e in rows if e["status"] == DONE and e["day"] == today]
    durations = [d for d in (_duration_seconds(e) for e in drives_today) if d]
    for i, e in enumerate(waiting):
        e["ahead"] = i
        e["eta"] = eta(i)
    current = datetime.now()
    for e in waiting + called + driving + finished:
        since = parse_ts(e["started_at"] if e["status"] == DRIVING else e["called_at"] or e["created_at"])
        e["elapsed"] = int((current - since).total_seconds()) if since else 0
        e["links"] = contact_links(e, cfg)
        e["label"] = LABELS.get(e["status"], e["status"])
        e["duration"] = fmt_duration(_duration_seconds(e))
    stats = [
        ("Wartend", len(waiting), True),
        ("Aufgerufen", len(called), False),
    ]
    if cfg["tracking_enabled"]:
        stats.append(("Unterwegs", len(driving), True))
        stats.append(("Ø Fahrzeit", f"{round(sum(durations) / len(durations) / 60)} Min." if durations else "–", False))
    stats.append(("Heute erledigt", len(drives_today), False))
    stats.append(("Wartezeit neu", f"~{eta(len(waiting))} Min." if waiting or busy else "keine", False))
    return {
        "waiting": waiting,
        "called": called,
        "driving": driving,
        "finished": finished,
        "stats": stats,
        "vehicles": lines(cfg["vehicles"]),
        "tracking": cfg["tracking_enabled"],
        "avg": avg,
    }


@bp.route("/admin/warteschlange")
@login_required
def admin_queue():
    return render_template("admin_queue.html", **admin_context())


@bp.route("/admin/warteschlange/liste")
@login_required
def admin_queue_list():
    return render_template("_queue_list.html", **admin_context())


@bp.route("/admin/warteschlange/<entry_id>/<action>", methods=["POST"])
@login_required
def admin_queue_action(entry_id, action):
    check_csrf()
    tracking = get_settings()["tracking_enabled"]
    with queue_table.edit() as rows:
        entry = next((e for e in rows if e["id"] == entry_id), None)
        if entry is None:
            abort(404)
        if action == "call" and entry["status"] in (WAITING, CALLED):
            entry["status"] = CALLED
            entry["called_at"] = now()  # erneutes Aufrufen löst den Alarm erneut aus
        elif action == "start" and entry["status"] in (WAITING, CALLED):
            if tracking:
                entry["status"] = DRIVING
                entry["started_at"] = now()
                entry["vehicle"] = request.form.get("vehicle", "").strip()[:100]
            else:
                entry["status"] = DONE
                entry["ended_at"] = now()
            entry["called_at"] = entry["called_at"] or now()
        elif action == "end" and entry["status"] == DRIVING:
            entry["status"] = DONE
            entry["ended_at"] = now()
        elif action == "noshow" and entry["status"] in (WAITING, CALLED):
            entry["status"] = NO_SHOW
            entry["ended_at"] = now()
        elif action == "requeue" and entry["status"] in (CALLED, NO_SHOW, CANCELLED):
            entry["status"] = WAITING
            entry["called_at"] = entry["ended_at"] = ""
        elif action == "reopen" and entry["status"] == DONE and entry["started_at"]:
            entry["status"] = DRIVING  # versehentlich beendet → Fahrt läuft weiter
            entry["ended_at"] = ""
        elif action == "delete":
            rows.remove(entry)
        elif action == "note":
            entry["note"] = request.form.get("note", "").strip()[:500]
    if request.headers.get("X-Requested-With") == "fetch":
        return ("", 204)
    return redirect(url_for("queue.admin_queue"))


@bp.route("/admin/warteschlange/leeren", methods=["POST"])
@login_required
def admin_queue_clear():
    """Tagesabschluss: alle noch Wartenden/Aufgerufenen als abgesagt markieren."""
    check_csrf()
    with queue_table.edit() as rows:
        for e in rows:
            if e["status"] in (WAITING, CALLED):
                e["status"] = CANCELLED
                e["ended_at"] = now()
    return redirect(url_for("queue.admin_queue"))


def queue_export_rows():
    header = ["Datum", "Nr.", "Name", "Telefon", "E-Mail", "Status", "Angemeldet", "Aufgerufen",
              "Fahrt Start", "Fahrt Ende", "Dauer", "Fahrzeug", "Notiz"]
    rows = []
    for e in sorted(queue_table.all(), key=_sort_key):
        rows.append([
            datetime.strptime(e["day"], "%Y-%m-%d").strftime("%d.%m.%Y") if e["day"] else "",
            int(e["number"]) if e["number"].isdigit() else e["number"],
            safe_cell(e["name"]),
            safe_cell(e["phone"]),
            safe_cell(e["email"]),
            LABELS.get(e["status"], e["status"]),
            e["created_at"][11:16],
            e["called_at"][11:16],
            e["started_at"][11:16],
            e["ended_at"][11:16] if e["started_at"] else "",
            fmt_duration(_duration_seconds(e)) if e["started_at"] and e["ended_at"] else "",
            safe_cell(e["vehicle"]),
            safe_cell(e["note"]),
        ])
    return header, rows


@bp.route("/admin/warteschlange/export.csv")
@login_required
def export_csv():
    return csv_response(*queue_export_rows(), "probefahrten")


@bp.route("/admin/warteschlange/export.xlsx")
@login_required
def export_xlsx():
    return xlsx_response(*queue_export_rows(), "probefahrten", "Probefahrten")


@bp.route("/admin/warteschlange/aushang")
@login_required
def poster():
    """Druckbarer Aushang mit QR-Code zur Anmeldung."""
    return render_template("queue_poster.html", signup_url=public_base() + url_for("queue.signup"))
