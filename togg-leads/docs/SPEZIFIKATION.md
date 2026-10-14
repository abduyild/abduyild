# Spezifikation & Umsetzungsstand

> Entstanden aus einem Design-Panel (drei unabhängige Entwürfe, Jury, Synthese) am 14.10.2026.
> Grundlage für die weitere Umsetzung. Fortschritt wird hier oben gepflegt.

## Stand

**Fertig (im Repo, getestet):**
- Interessenten-Formular + Admin mit CSV/Excel-Export
- Probefahrt-Warteschlange: Anmeldung (Kiosk/QR), Nummer, Live-Status mit Ton/Vibration,
  Aufruf-Anzeige, Admin mit Aufrufen/Start/Ende/No-Show, Kontakt per Anruf/SMS/WhatsApp,
  optionales Fahrtzeit-Tracking, Tagesabschluss, Export, QR-Aushang
- Einstellungen: Marke, Logo, Farbe, alle Texte (White-Label), Module, Admin-Passwort

**Als Nächstes (Reihenfolge laut Abschnitt F):**
1. Fahrzeuge-Kern (Abschnitt A + B) – `vehicles.csv`, `damages.csv`, Start-/Ende-Panels, Fahrzeuge-Tab
2. Bestandsfixes & Kunden-Seiten (Marketing-Opt-in, Kiosk-Dialog, Security-Header)
3. Tresor & Login (Abschnitt C2–C4, C12) – `vault.py`
4. DSGVO-Schicht (C7–C11) – Einwilligungsnachweis, Aufbewahrung, Personensuche, Protokoll, Backup
5. Lizenz (D5–D6) – `licensing.py`, `tools/license_cli.py`
6. Launcher, Verbinden, Packaging, Portal (D2–D4, D7–D8)
7. Realtest & Doku

Hinweis: Ein Linux-Test-Build mit PyInstaller (`--onefile`) lief erfolgreich (44 MB, App startet und antwortet).

---

# Finale Spezifikation: Fahrzeuge, DSGVO, Deployment & Lizenz für die Probefahrt-App

Grundlage ist der Entwurf **security-ops** (Jury-Sieger). Eingearbeitet aus **ux-minimal**: `damages.csv` statt Freitext-Zustandsnotiz, `start_checks` als konfigurierbare Zeilen, „Bekannt: …“-Zeile im Start-Panel, Ende-Dialog mit einer Entscheidung. Eingearbeitet aus **event-ops**: Tagesabschluss-Sperre bei offener Fahrt, Ein-Tap-Reparatur „Fahrt Nr. 12 beenden und Fahrzeug nehmen“, Status „überfällig“, Folge-Hinweis „Nächster: Nr. 15 aufrufen“, getrennte Marketing-Einwilligung (behebt den `queue_also_lead`-Mangel), Kiosk-Cookie, Port 8470, Reiserouter als Standard.

Verworfen laut Jury: ein Passwort für Tresor und LAN-Login (ersetzt durch Tresor-Passwort + Stand-PIN), `last_seen` im Klartext, `secret_key` im Vault, Cloudflare-Tunnel, `--onefile`, `macos-13`-Runner, Klartext-Lizenzen im öffentlichen Portal, Auto-Löschung ohne gesehene Warnung, Audit mit IP-Adressen, Fotos, km-Stand, Zonen-/Art-Chips, `drives.csv`, Wunschmodell, Unterschrift, Fahrtenbuch-Export, Begleitperson als Pflicht.

Bezug zum Bestand (`/home/user/abduyild/togg-leads`): `core.py` (`Table`, `DEFAULTS`, `SETTINGS_SCHEMA`, `login_required`, `check_csrf`, `csv_response`/`xlsx_response`), `app.py` (`inject_globals`, `admin_settings`, `ProxyFix`), `queue_routes.py` (Blueprint `queue`, `admin_queue_action`, `queue_state`, `public_base`), Templates `_queue_list.html`, `admin_queue.html`, `admin_base.html`, `settings.html`, `queue_signup.html`, `queue_ticket.html`, `queue_poster.html`, `static/style.css`.

Bestehende Fehler, die nebenbei behoben werden: QR-Codes mit `127.0.0.1` (`public_base()`), Leads aus der Warteschlange ohne passende Einwilligung (`queue_also_lead`), `requirements.txt` ohne `qrcode`/`waitress`, toter Datenschutz-Link im Kiosk (`pointer-events: none`), CSRF-Token wird beim Login nicht rotiert, `reopen` ohne Fahrzeugprüfung.

---

## A) Fahrzeuge

### A1 Globales Lock (core.py)

Alle Tabellen teilen sich **ein** `DATA_LOCK = threading.RLock()` in `core.py`. `Table._lock` entfällt; `all()`, `append()`, `edit()` nehmen `DATA_LOCK`. Verschachtelte `edit()`-Aufrufe über mehrere Tabellen sind damit deadlockfrei (RLock ist reentrant). Bei einigen hundert Zeilen pro Tag kostet das nichts.

### A2 `data/vehicles.csv.enc` (neue `Table("vehicles.csv", VEHICLE_FIELDS)`)

| Spalte | Typ | Pflicht | Bedeutung |
|---|---|---|---|
| `id` | `uuid4().hex[:10]` | auto | Primärschlüssel |
| `code` | str 1–3 Zeichen, Großschreibung | ja (vorbelegt: nächste freie Zahl „1“, „2“, …) | Kürzel auf dem Schlüsselanhänger; überall groß angezeigt |
| `model` | str ≤ 60 | ja | „T10X“ |
| `color` | str ≤ 30 | nein | „Weiß“ |
| `plate` | str ≤ 15, Großschreibung | nein | Kennzeichen, auch rotes 06er |
| `trim` | str ≤ 80 | nein | eine Zeile Ausstattung: „V2 Long Range · 20 Zoll“ |
| `blocked_reason` | str ≤ 60 | nein | leer = nicht gesperrt; sonst Grund („Laden“, „Schaden“, „Pause“, Freitext) |
| `blocked_at` | ts | auto | gesetzt mit `blocked_reason` |
| `archived_at` | ts | nein | Soft-Delete; Historie bleibt |
| `created_at`, `updated_at` | ts | auto | |

`VEHICLE_FIELDS = ["id","code","model","color","plate","trim","blocked_reason","blocked_at","archived_at","created_at","updated_at"]`

Eindeutigkeit: `code` unter nicht-archivierten Fahrzeugen; `plate` (falls gesetzt) unter nicht-archivierten Fahrzeugen. Verstoß → Inline-Fehler im Formular.

### A3 `data/damages.csv.enc` (neue `Table("damages.csv", DAMAGE_FIELDS)`)

| Spalte | Typ | Pflicht | Bedeutung |
|---|---|---|---|
| `id` | hex(10) | auto | |
| `vehicle_id` | str | ja | Referenz `vehicles.id` |
| `entry_id` | str | nein | `queue.id` der Fahrt, nach der der Schaden gemeldet wurde; leer = Vorschaden (manuell erfasst) |
| `created_at` | ts | auto | |
| `text` | str ≤ 300 | ja | „Kratzer Stoßstange hinten rechts, ca. 5 cm“ |
| `resolved_at` | ts | nein | „Behoben“; verschwindet aus der aktiven Liste, bleibt in der Historie |

`DAMAGE_FIELDS = ["id","vehicle_id","entry_id","created_at","text","resolved_at"]`

### A4 Erweiterung `queue.csv.enc` (ein Eintrag = ein Probefahrt-Vorgang)

Bestehende Spalten bleiben. Neue Spalten (angehängt; `Table._ensure()` schreibt alte Dateien automatisch um):

| Spalte | Typ | Bedeutung |
|---|---|---|
| `vehicle_id` | str | Referenz `vehicles.id` |
| `vehicle` | str (bestehend) | wird zum **Snapshot** beim Start: `"2 · T10X Weiß · S-06 1234"`; Export/Historie bleiben lesbar nach Umbenennen/Archivieren |
| `checks` | str | mit `\|` verbundene bestätigte Start-Prüfungen, z. B. `Führerschein gesehen\|Probefahrtvereinbarung unterschrieben`; Zeitpunkt = `started_at` |
| `staff` | str ≤ 20 | Kürzel/Vorname des Begleiters (optional, aus Einstellung `staff`) |
| `end_condition` | `ok` / `auffaellig` / `""` | Ergebnis beim Beenden |
| `end_note` | str ≤ 300 | Text bei `auffaellig` (identisch mit dem erzeugten `damages.text`) |
| `source` | `kiosk` / `handy` | Anmeldekanal (`kiosk`-Flag im POST) |
| `consent_ref` | str 12 hex | `sha256(fill(queue_consent_text))[:12]` (siehe C7) |
| `marketing_consent` | ts | leer = kein Marketing-Opt-in; sonst Zeitpunkt (siehe C7) |

`QUEUE_FIELDS = [..bestehend.., "vehicle_id","checks","staff","end_condition","end_note","source","consent_ref","marketing_consent"]`

`leads.csv.enc` bekommt zusätzlich `consent_ref` (12 hex).

### A5 Status-Logik (abgeleitet, nie gespeichert)

Funktion `vehicle_status(v, rows_queue, cfg)` in `vehicles.py`:

```
unterwegs  := es existiert ein queue-Eintrag mit status == "unterwegs" und vehicle_id == v.id
ueberfaellig := unterwegs und (now - started_at) > cfg["max_drive_minutes"] * 60
gesperrt   := nicht unterwegs und v.blocked_reason != ""
verfuegbar := sonst
archiviert := v.archived_at != ""   (nur in Historie/Export)
```

Regeln (alle serverseitig innerhalb `with queue_table.edit() as rows:` unter `DATA_LOCK`):

- **Start** (`action == "start"`, Tracking an): Fahrzeug muss existieren, nicht archiviert sein. Ist es `unterwegs` in einem anderen Eintrag → ohne `takeover=1`: **409** mit Text `Fahrzeug 2 ist noch unterwegs (Nr. 14).`; mit `takeover=1`: der andere Eintrag wird mit `end_condition=ok`, `ended_at=now`, `end_note="beendet beim Start von Nr. 15"` geschlossen, dann Start. Ist es `gesperrt` → nur mit `force=1` (Sperre wird aufgehoben, `blocked_reason=""`), sonst 409 `Fahrzeug 3 ist gesperrt: Laden.` Pflicht-Checks: alle Zeilen aus `start_checks` müssen in `request.form.getlist("checks")` enthalten sein, sonst 400 `Bitte alle Prüfungen bestätigen.`
- **Ende** (`action == "end"`): setzt `status=fertig`, `ended_at`, `end_condition`, `end_note`. Bei `end_condition == "auffaellig"`: `end_note` Pflicht (≥ 3 Zeichen), neuer `damages`-Eintrag mit `entry_id`; wenn `block_vehicle=1`: `blocked_reason="Schaden"`, `blocked_at=now`.
- **reopen**: nur wenn `vehicle_id` nicht in einem anderen `unterwegs`-Eintrag → sonst 409 `Fahrzeug 2 ist inzwischen bei Nr. 18.`
- **delete** auf einem `unterwegs`-Eintrag → 409 `Bitte zuerst die Fahrt beenden.`
- **Sperren während unterwegs** erlaubt; wirkt nach dem Ende (Anzeige „unterwegs · danach gesperrt“).
- **Archivieren** nur wenn nicht unterwegs. **Löschen** nur, wenn keine `queue`-Zeile und keine `damages`-Zeile auf die `id` zeigt; sonst nur Archivieren.
- **Tagesabschluss** (`admin_queue_clear`) wird verweigert, solange ein Eintrag `unterwegs` ist: Flash `Fahrzeug 2 ist noch unterwegs: Nr. 14 Müller. Bitte zuerst die Fahrt beenden.`
- **Wartezeit** (`queue_state`): `cars = max(1, Anzahl Fahrzeuge mit archived_at == "" und blocked_reason == "")`; nur wenn keine Fahrzeuge angelegt sind, gilt `cars_count`. Unterwegs zählt mit (wird frei), gesperrt nicht.
- **Tracking**: Das Fahrzeugmodul setzt `tracking_enabled` voraus. Beim Anlegen des ersten Fahrzeugs wird `tracking_enabled=True` gesetzt (Flash „Fahrtzeit-Tracking wurde eingeschaltet.“). Ohne Tracking (reine Warteschlange, keine Fahrzeuge) bleibt der Button `Erledigt ✓` wie heute, ohne Checks – wer Checks will, braucht Tracking.

### A6 Verknüpfung „wer hatte welches Auto wann“

Quelle der Wahrheit ist `queue.csv`: `number`, `name`, `phone`, `vehicle_id`, `vehicle`, `started_at`, `ended_at`, `checks`, `staff`, `end_condition`. Keine eigene Fahrten-Tabelle. Walk-ins ohne Anmeldung trägt der Vertreter über `/warteschlange?kiosk=1` auf seinem Handy ein und startet direkt.

Fahrzeug-Detail zeigt: alle Einträge mit `vehicle_id == id` des Tages (neueste zuerst); Schaden → Fahrt über `damages.entry_id`.

### A7 Auswertungen (aus `queue.csv` berechnet, keine Diagramme)

Auf der Fahrzeug-Karte eine `.muted`-Zeile: `Heute 5 Fahrten · 1:48 h · Ø 18 Min · letzte 14:02`. Im Detail drei `.stat`-Kacheln: **Heute** (Fahrten · Zeit unterwegs · Ø Dauer), **Gesamt** (Fahrten · Ø Dauer), **Offene Schäden**.

Export:
- Bestehender Export `/admin/warteschlange/export.csv|xlsx` erhält Spalten `Fahrzeug`, `Kennzeichen`, `Prüfungen`, `Begleiter`, `Zustand Ende`, `Bemerkung`, `Kanal`, `Einwilligung (Version)` und akzeptiert `?vehicle=<id>` als Filter.
- `GET /admin/fahrzeuge/export.xlsx`: Blatt „Fahrzeuge“ (Code, Modell, Farbe, Kennzeichen, Ausstattung, Status, Fahrten heute, Fahrten gesamt, Ø Dauer, offene Schäden), Blatt „Schäden“ (Fahrzeug, Datum, Text, nach Fahrt Nr., behoben am). `xlsx_response()` wird um einen optionalen Parameter `extra_sheets=[(title, header, rows)]` erweitert.

### A8 Einstellungen (`DEFAULTS` / `SETTINGS_SCHEMA`)

Abschnitt „Module“: `queue_also_lead` wird ersetzt durch `queue_marketing_optin` (bool, Standard **aus**, Label „Marketing-Opt-in in der Warteschlangen-Anmeldung anzeigen“, Hilfe „Nur mit gesetztem Haken entsteht ein Interessent.“). Beim ersten Start wird ein vorhandenes `queue_also_lead=true` in `queue_marketing_optin=true` übernommen.

Abschnitt „Probefahrt“:
- `cars_count` bleibt, Hilfetext „Nur relevant, solange keine Fahrzeuge angelegt sind.“
- `drive_minutes` bleibt.
- neu `max_drive_minutes` (int, Standard 45, „Ab dieser Fahrzeit wird eine Fahrt als überfällig markiert.“)
- neu `start_checks` (lines, Standard `Führerschein gesehen\nProbefahrtvereinbarung unterschrieben`, Hilfe „Pflicht-Bestätigungen vor jedem Start. Leer = keine.“)
- neu `staff` (lines, Standard leer, Label „Mitarbeiter am Stand (Vorname oder Kürzel, optional)“)
- `vehicles` (lines) **entfällt**. Migration beim ersten Entsperren: jede Zeile → `vehicles.csv` mit `model = Zeile`, `code` fortlaufend; Schlüssel wird danach ignoriert.
- `contact_message` bleibt.

Abschnitt „Texte – Warteschlange“: neu `queue_marketing_text` (textarea, Standard: „Ich möchte zusätzlich Informationen und Angebote der {firma} zu {marke} per E-Mail und Telefon erhalten. Widerruf jederzeit an {email}.“).

Neuer Abschnitt „Datenschutz“: `queue_retention_days` (int, 30), `lead_retention_days` (int, 90). Für `int`-Felder gilt neu `INT_RANGES = {"queue_retention_days": (7, 3650), "lead_retention_days": (7, 3650), "max_drive_minutes": (10, 600)}` in `core.py`, Standard `(1, 600)`.

Nicht im Schema, aber in `DEFAULTS` (werden auf `/admin/verbinden` gepflegt): `wifi_ssid` (""), `wifi_password` ("").

Entfällt: `admin_password_hash` (siehe C3).

---

## B) UX-Flows & Screens

Bausteine bleiben: `.card`, `.chip`, `.q-num`, `.option`, `.stat`, `.flash`, `.sticky-save`, `.danger-zone`, Akzentfarbe, `--green`/`--red`. Alle Panels sind `<details>` innerhalb der Karte, damit `busy()` in `admin_queue.html` die 5-Sekunden-Aktualisierung automatisch pausiert, solange ein Panel offen ist. Kein `<dialog>`.

### B1 Navigation (`admin_base.html`)

Tabs in neuer Reihenfolge: **Warteschlange · Fahrzeuge · Interessenten · Einstellungen** (Fahrzeuge nur wenn `module_queue` und Lizenz-Feature `vehicles`). Logo-Link und Login-Redirect zeigen auf `queue.admin_queue`, wenn `module_queue` aktiv ist, sonst auf `admin`. Endpoint `admin` (Interessenten) bleibt unter `/admin`.

Chips auf der Warteschlange: `Tablet-Modus ↗ · Aufruf-Anzeige ↗ · Geräte verbinden · QR-Aushang drucken · CSV · Excel`.

Banner (`.flash warn`) oben in `admin_base.html`, in dieser Reihenfolge, nur wenn zutreffend: Lizenz (D6), Systemzeit (D5), fällige Löschungen (C8), Einrichtung unvollständig („Die Datenschutzerklärung enthält noch den Platzhalter-Hinweis.“ solange `privacy_text` den String „Platzhalter“ enthält).

### B2 Fahrzeug-Leiste in `_queue_list.html` (Partial `_vehicle_strip.html`)

Ganz oben in `_queue_list.html` (also im 5-Sekunden-Fragment), über den `.stats`, nur wenn `tracking` und Fahrzeuge existieren:

```html
<nav class="v-strip" aria-label="Fahrzeuge">
  <a class="v-chip free"    href="#" data-start-vehicle="{{ v.id }}"><b>1</b> frei</a>
  <a class="v-chip driving" href="#q-{{ e.id }}"><b>2</b> Nr. 14 · <span data-elapsed="…">–</span></a>
  <a class="v-chip late"    href="#q-{{ e.id }}"><b>4</b> Nr. 9 · <span data-elapsed="…">–</span> ⚠</a>
  <a class="v-chip blocked" href="{{ url_for('vehicles.edit', vid=v.id) }}"><b>3</b> Laden 🔒</a>
</nav>
```

CSS: `.v-strip { display:flex; gap:8px; overflow-x:auto; padding-bottom:6px; margin-bottom:14px; }` `.v-chip { flex:none; border-radius:999px; padding:8px 14px; font-size:15px; text-decoration:none; border:1px solid var(--border); }` `.v-chip b { font-size:17px; margin-right:4px; }` `.free { background:#e9f8ec; color:#1f7a35; }` `.driving { background:var(--accent-soft); color:var(--accent-ink); }` `.late { background:#fdecea; color:var(--red); }` `.blocked { background:#f2f2f3; color:#555; }`

Verhalten:
- Tap auf `driving`/`late` scrollt zur Karte `#q-<id>` (jede `.q-card` bekommt `id="q-{{ e.id }}"`).
- Tap auf `free`: JS sucht die erste Karte in „Aufgerufen“, sonst „Wartend“, öffnet dort `details.start-panel`, setzt das Radio `vehicle_id` auf dieses Fahrzeug, scrollt hin. Gibt es niemanden: Hinweis `Niemand wartet – Fahrzeug 1 ist frei.` im `#queue-flash`.
- Tap auf `blocked`: Fahrzeug-Detail.

Stat-Kachel zusätzlich: `("Fahrzeuge frei", "2/4", True)` wenn Fahrzeuge existieren.

### B3 Fahrt starten (`_start_panel.html`, eingebunden in Karten „Aufgerufen“ und „Wartend“)

Ersetzt das Macro `start_form` bei `tracking and vehicles`:

```html
<details class="start-panel">
  <summary class="btn small primary">Fahrt starten ▶</summary>
  <form method="post" action="{{ url_for('queue.admin_queue_action', entry_id=e.id, action='start') }}" class="start-form-panel">
    <input type="hidden" name="csrf_token" value="{{ csrf_token }}">
    <p class="lbl">Fahrzeug</p>
    <div class="options">
      {% for v in vehicles %}
      <label class="option small {{ v.state }}">
        <input type="radio" name="vehicle_id" value="{{ v.id }}" {% if v.state != 'verfuegbar' %}data-state="{{ v.state }}" data-msg="{{ v.msg }}"{% endif %}>
        <span class="box"></span>
        <span><b>{{ v.code }}</b> · {{ v.model }} {{ v.color }}{% if v.plate %} · {{ v.plate }}{% endif %}
          <small>{{ v.sub }}</small></span>
      </label>
      {% endfor %}
    </div>
    <p class="known muted" hidden>Bekannt: <span></span></p>
    {% if start_checks %}
    <p class="lbl">Geprüft</p>
    <div class="options">
      {% for c in start_checks %}<label class="option small"><input type="checkbox" name="checks" value="{{ c }}"><span class="box"></span><span>{{ c }}</span></label>{% endfor %}
    </div>
    {% endif %}
    {% if staff %}
    <p class="lbl">Begleiter</p>
    <div class="chips staff-chips">{% for s in staff %}<label class="chip"><input type="radio" name="staff" value="{{ s }}" hidden>{{ s }}</label>{% endfor %}</div>
    {% endif %}
    <button class="btn primary wide" disabled>Fahrt starten ▶</button>
  </form>
</details>
```

- `v.sub`: bei `verfuegbar` die offenen Schäden kurz (`2 bekannte Schäden`), bei `unterwegs` `unterwegs · Nr. 14 · 12:31`, bei `gesperrt` `gesperrt: Laden`. Sortierung: verfügbar → unterwegs → gesperrt. Genau ein verfügbares Fahrzeug → vorausgewählt; mehrere → keine Vorauswahl.
- Auswahl eines Fahrzeugs füllt `.known` mit den offenen `damages.text` (Attribut `data-known` am Label), damit der Vertreter sie dem Kunden zeigen kann.
- Tap auf ein `unterwegs`-Fahrzeug: `confirm("Fahrzeug 2 ist noch unterwegs (Nr. 14). Fahrt Nr. 14 jetzt beenden und Fahrzeug 2 nehmen?")` → bei Ja wird `<input type=hidden name=takeover value=1>` gesetzt; Tap auf `gesperrt`: `confirm("Fahrzeug 3 ist gesperrt: Laden. Trotzdem starten? Die Sperre wird aufgehoben.")` → `force=1`.
- Button bleibt `disabled`, bis ein Fahrzeug gewählt ist und alle Checks angehakt sind (JS in `admin_queue.html`); Button-Text bei fehlenden Checks: `Prüfungen fehlen`.
- Zuletzt gewählter Begleiter wird in `localStorage["staff"]` gemerkt und vorausgewählt.
- Tap-Zählung Normalfall (ein freies Auto): Panel öffnen, 2 Checks, Start = 4 Taps.

Ohne Fahrzeuge (`tracking` an, keine Fahrzeuge): Button `Fahrt starten ▶` startet direkt wie heute (kein Panel). Ohne Tracking: `Erledigt ✓` wie heute.

### B4 Fahrt beenden (Karte „Unterwegs“ und Fahrzeug-Detail, Partial `_end_panel.html`)

Normalfall ist **ein Tap**: Button `✓ Fahrt beenden` (`btn small primary`) ist ein eigenes Formular mit `end_condition=ok` und sofortigem Submit. Daneben:

```html
<details class="end-panel">
  <summary class="btn small outline">⚠ Auffälligkeit</summary>
  <form method="post" action=".../end">
    <input type="hidden" name="csrf_token" …><input type="hidden" name="end_condition" value="auffaellig">
    <p class="lbl">Fahrzeug 2 zurück – was ist aufgefallen?</p>
    <textarea name="end_note" rows="2" required placeholder="Kratzer Felge vorne rechts …"></textarea>
    <label class="inline-check"><input type="checkbox" name="block_vehicle" value="1" checked> Fahrzeug sperren (Schaden)</label>
    <button class="btn primary">Beenden &amp; Schaden speichern</button>
  </form>
</details>
```

Die Unterwegs-Karte zeigt `.meta`: `🚗 2 · T10X Weiß · Start 11:04{% if e.staff %} · {{ e.staff }}{% endif %}`; bei `ueberfaellig` bekommt die Karte Klasse `late` (roter Rahmen) und `📞 Anrufen` wird primär.

Nach dem Beenden antwortet der Server im Fetch-Pfad mit `200` und JSON `{"ok": true, "hint": "Fahrzeug 2 ist frei · Nächster: Nr. 15 Schmidt", "next_id": "<id>"}`; das JS zeigt den Hinweis in `#queue-flash` mit Button `🔔 Nr. 15 aufrufen` (POST `call` auf `next_id`). Kette Rückgabe → Aufrufen = 2 Taps.

### B5 Fehler im Fetch-Pfad (JS in `admin_queue.html`)

`admin_queue_action` liefert für `X-Requested-With: fetch` bei Fehlern `409`/`400` mit `Content-Type: text/plain` und der Meldung. In `admin_queue.html` wird über `#queue-list` ein `<p id="queue-flash" class="flash error" hidden></p>` eingefügt (außerhalb des ersetzten Fragments). Submit-Handler:

```js
const r = await fetch(form.action, { method: "POST", body, headers: { "X-Requested-With": "fetch" } });
if (!r.ok) { showFlash(await r.text(), "error"); }
else if ((r.headers.get("content-type") || "").includes("json")) { const j = await r.json(); if (j.hint) showFlash(j.hint, "success", j.next_id); }
refresh(true);
```

`showFlash` blendet nach 8 s aus. Confirm-Texte bleiben via `data-confirm`.

### B6 Screen „Fahrzeuge“ – `GET /admin/fahrzeuge` (`admin_vehicles.html`, Blueprint `vehicles` in `vehicles.py`)

1. `title-row`: „Fahrzeuge“ · rechts `.count` `2 frei · 1 unterwegs · 1 gesperrt`
2. Chips: `+ Fahrzeug` (`chip active`) · `Excel` (`chip excel`) · `Archivierte anzeigen` (Toggle `?archiv=1`)
3. `.cards`, eine Karte je Fahrzeug, Reihenfolge: überfällig → unterwegs → verfügbar → gesperrt → archiviert:
   - links `.v-code` (wie `.q-num`, 56 px): Code; Hintergrund `--green` bei verfügbar, Akzent bei unterwegs, `--red` bei überfällig, `#9a9a9e` bei gesperrt
   - `h3` „T10X Weiß“, `.meta` „S-06 1234 · V2 Long Range“
   - Status-Tag rechts (`.tag`): `Verfügbar` / `Unterwegs · Nr. 14 · seit 12:31` / `Überfällig · Nr. 9 · 52 Min` / `Gesperrt: Laden`
   - `.notes` mit offenen Schäden (max. 3 Zeilen, „+2 weitere“)
   - Kennzahlen-Zeile (A7)
   - `.q-actions`: unterwegs → `✓ Fahrt beenden` + `⚠ Auffälligkeit` (Partial B4) + `📞 Anrufen`; verfügbar → `Sperren …` (Details-Panel: Chips `Laden` `Schaden` `Pause` `Sonstiges` + Textfeld `blocked_reason`, Button `Sperren`); gesperrt → `Freigeben ✓` (primär); immer `Bearbeiten` (ghost)
4. Leerzustand: „Noch kein Fahrzeug. Lege dein erstes Testfahrzeug an – dann kannst du Fahrten starten und siehst, wer welches Auto hat.“ + Button `+ Fahrzeug`.

Diese Seite wird nicht automatisch aktualisiert (Verwaltung, kein Live-Betrieb); „Aktualisieren“ in der `admin-bar` bleibt.

### B7 Fahrzeug anlegen / bearbeiten (`vehicle_form.html`)

Routen: `GET/POST /admin/fahrzeuge/neu` (Endpoint `vehicles.new`), `GET/POST /admin/fahrzeuge/<vid>` (`vehicles.edit`).

Ein `settings-card`-Formular, Felder in dieser Reihenfolge (alle `.field`):

1. **Modell** * (`<input name="model" list="models" autofocus autocapitalize="words">`, Datalist aus vorhandenen Modellen)
2. **Farbe** (`list="colors"`: Weiß, Schwarz, Grau, Silber, Blau, Rot, Grün)
3. **Kennzeichen** (`autocapitalize="characters"`, Placeholder „S-06 1234“, Hilfe „auch rotes Händlerkennzeichen“)
4. **Ausstattung / Variante** (eine Zeile)
5. **Kürzel** (`name="code"`, `maxlength="3"`, vorbelegt, Hilfe „Steht auf dem Schlüsselanhänger.“)
6. Nur beim Anlegen: **Vorschäden** (Textarea, Placeholder „eins pro Zeile: Kratzer Heckstoßstange links …“) → jede Zeile wird ein `damages`-Eintrag ohne `entry_id`.
7. `.sticky-save` → Button `Speichern`

Beim Bearbeiten darunter zwei Karten:
- **Schäden (3)**: Liste `12.10. 14:21 · Felge vorne rechts angekratzt · nach Fahrt Nr. 14` (Link auf `#q-<id>` in der Warteschlange, falls heute) · rechts `Behoben` (`link`). Aufklappbar „Behoben (2)“. Darunter Inline-Formular `+ Schaden`: Textfeld + Button `Hinzufügen`.
- **Fahrten heute**: `.q-table` Nr. · Name · Start–Ende · Dauer · ⚠ bei `auffaellig`. Link `Alle Fahrten dieses Fahrzeugs exportieren` → `/admin/warteschlange/export.xlsx?vehicle=<id>`.

`danger-zone` unten: `Archivieren` (nur wenn nicht unterwegs; Confirm „Fahrzeug 2 archivieren? Fahrten und Schäden bleiben erhalten.“) bzw. `Wiederherstellen` bei archivierten; `Löschen` nur wenn nie referenziert.

POST-Routen (alle `check_csrf()`, `login_required`, bei `X-Requested-With: fetch` → `204`):
`POST /admin/fahrzeuge/<vid>/sperren` (Felder `reason`, Chips füllen das Feld), `POST /admin/fahrzeuge/<vid>/freigeben`, `POST /admin/fahrzeuge/<vid>/archivieren`, `POST /admin/fahrzeuge/<vid>/wiederherstellen`, `POST /admin/fahrzeuge/<vid>/loeschen`, `POST /admin/fahrzeuge/<vid>/schaden` (Feld `text`), `POST /admin/fahrzeuge/schaden/<did>/behoben`, `POST /admin/fahrzeuge/schaden/<did>/loeschen`.

### B8 Kunden-Seiten

- `queue_signup.html`: unter der Pflicht-Einwilligung optional (nur wenn `queue_marketing_optin`) eine zweite `.consent`-Checkbox `marketing_consent` mit `t('queue_marketing_text')`, kein `*`. Lead entsteht nur mit Haken (Interesse = erste Zeile aus `interests`, die „fahrt“ enthält; `consent = marketing_consent`, `consent_ref` = Hash des Marketing-Textes, `source="Warteschlange"`).
- Kiosk: Link „Datenschutzerklärung“ öffnet den Text in einem `<dialog class="privacy-dialog">` (Inhalt `t('privacy_text')`, Button `Schließen`); CSS-Regel `body.kiosk .legal a { pointer-events: none; }` entfällt.
- `queue_ticket.html`: Telefonnummer maskiert: `… {{ entry.phone[-4:] }}`.
- `queue_status.html`: bei `unterwegs` Text „Gute Fahrt mit dem T10X Weiß!“ (aus `vehicle`-Snapshot, über `status_payload` als `vehicle_label`). Im Alerts-Block zusätzlich, wenn `location.protocol !== "https:"`: „Hinweis: Ton und Vibration funktionieren nur, solange diese Seite geöffnet bleibt.“ (JS blendet den Satz ein).
- `/warteschlange?kiosk=1` setzt Cookie `kiosk=1` (1 Jahr, `SameSite=Lax`); `admin_login` verweigert mit diesem Cookie: „Dieses Gerät ist als Kiosk markiert. Admin bitte vom eigenen Handy oder Laptop.“ Cookie wird gelöscht über `/warteschlange?kiosk=0`.

### B9 Aufruf-Anzeige

`/anzeige` bleibt unverändert (nur Nummern). Im eingeschränkten Lizenzmodus (D6) zeigt sie „Derzeit keine Anmeldung möglich.“ ohne Nummern.

---

## C) DSGVO & Datensicherheit

### C1 Schutzbedarf

Verarbeitet: Name, Telefon, E-Mail, PLZ, Notizen, Zeitpunkte, Fahrzeug, bestätigte Prüfungen, Begleiter-Kürzel. Keine besonderen Kategorien. Verantwortlicher ist der Händler/die Marke (`company`). Der App-Anbieter sieht nie Daten, hält keinen Schlüssel, ist kein Auftragsverarbeiter (kein AVV). Bedrohungen in Reihenfolge: gestohlener/unbeaufsichtigter Laptop, Datenordner in Cloud-Sync, Fremde im Stand-WLAN, Export auf dem Desktop, Vorgängerdaten am Kiosk.

### C2 Verschlüsselung at rest (Dateiebene) – `vault.py`

- Alle `Table`-Dateien heißen `leads.csv.enc`, `queue.csv.enc`, `vehicles.csv.enc`, `damages.csv.enc`, `audit.csv.enc`. `Table.__init__` setzt `self.path = DATA_DIR / (filename + ".enc")`.
- `Table._ensure`, `_read`, `_write`, `append` laufen über `vault.read_text(path, aad)` / `vault.write_text(path, text, aad)`; `append` wird read-modify-write; `_write` bleibt `.tmp` + `replace()`. Header-Prüfung in `_ensure` liest den entschlüsselten Text. Kein Dateizugriff beim Import (bleibt lazy).
- Dateiformat: `b"PFV1"` + 12 Byte Nonce + AES-256-GCM-Ciphertext; AAD = Dateiname ohne Pfad (`b"queue.csv.enc"`). Bibliothek `cryptography` (`AESGCM`).
- Unverschlüsselt bleiben: `settings.json` (keine Personendaten, kein Hash mehr), `media/` (Logo/Favicon), `license.key`, `vault.json` (nur gewrappte Schlüssel und ein verschlüsselter Block).
- Kein SQLCipher, keine Feldverschlüsselung, keine Fotos.

### C3 Schlüssel, Tresor-Passwort, Stand-PIN – `data/vault.json`

```json
{"v":1,
 "kdf":{"name":"scrypt","n":131072,"r":8,"p":1,"maxmem":268435456},
 "slots":{"password":{"salt":"<16B b64>","nonce":"<12B b64>","wrapped_dek":"<b64>"},
          "recovery":{"salt":"…","nonce":"…","wrapped_dek":"…"}},
 "sealed":{"nonce":"<12B b64>","ct":"<b64>"},
 "created_at":"2026-10-14 18:02:11"}
```

- **DEK**: 32 Byte Zufall. Zweimal gewrappt (AES-GCM, AAD = Slot-Name): mit dem KEK aus dem **Tresor-Passwort** (`hashlib.scrypt`, n=2^17, r=8, p=1, 16-Byte-Salt; ≈ 0,5 s) und mit dem KEK aus dem **Wiederherstellungscode** (24 Zeichen Crockford-Base32 in 6 Vierergruppen, ≈ 120 Bit, einmalig angezeigt).
- **`sealed`**: mit dem DEK verschlüsseltes JSON (AAD `b"sealed"`): `{"admin_pin_hash": "<werkzeug-hash>", "last_seen": "ts", "setup_at": "ts", "retention_notice_at": "ts|''"}`. Damit sind `last_seen` (Uhr-Schutz) und der PIN-Hash ohne Passwort weder lesbar noch manipulierbar.
- **Zwei Geheimnisse, bewusst getrennt**:
  - **Tresor-Passwort** (≥ 10 Zeichen): entsperrt die Daten. Wird ausschließlich über `/entsperren` eingegeben, und diese Route ist nur von Loopback erreichbar (C4). Es läuft nie durchs WLAN.
  - **Stand-PIN** (6–12 Zeichen, Ziffern oder Text): Admin-Login vom Handy/Tablet im LAN (`/admin/login`). Gibt nur eine Session, nie den Schlüssel. Hash liegt in `sealed`. Wird in der Einrichtung gesetzt und in den Einstellungen geändert (Karte „Stand-PIN“, Felder `new_pin`/`new_pin2`).
- `check_admin_password()` → `check_admin_pin(pin)`; `set_admin_password()` → `set_admin_pin(pin)` (schreibt `sealed` neu). `ENV_ADMIN_PASSWORD`, `TOGG_ADMIN_PASSWORD`, `using_default_password()` und das Standard-Passwort-Banner entfallen; das README wird angepasst.
- Tresor-Passwort ändern: nur über `/admin/einstellungen` **vom Laptop** (Loopback-Prüfung wie bei `/entsperren`), Felder `vault_old`, `vault_new`, `vault_new2`; DEK wird nur neu gewrappt, Recovery-Slot bleibt. Auf anderen Geräten ist die Karte sichtbar, aber deaktiviert mit Hinweis „Nur am Stand-Rechner möglich.“
- `app.secret_key = secrets.token_bytes(32)` pro Prozessstart; `.secret_key`-Datei und `TOGG_SECRET_KEY` entfallen. Folge: Admin-Sessions sind nach jedem Neustart ungültig – gewollt. `/entsperren` braucht nur den Prozess-Schlüssel für CSRF, funktioniert also auch vor dem Entsperren.
- Passwort weg + Code weg = Daten weg. Pflicht-Checkbox in der Einrichtung „Ich habe den Wiederherstellungscode notiert“, Button `Drucken`. Kein Generalschlüssel beim Anbieter.

### C4 Gesperrt/entsperrt, Loopback-Regel, Transport

- Prozessstart = gesperrt (`vault.STATE.dek is None`). `app.before_request` in `app.py`: ist nicht entsperrt und `request.endpoint` nicht in `{"unlock","setup","static","media","privacy","locked"}` → `render_template("locked.html"), 503` („Der Stand wird vorbereitet. Bitte am Stand-Rechner entsperren.“ mit Marke/Logo). Lizenzprüfung läuft auch gesperrt (`license.key` ist Klartext).
- `GET/POST /entsperren` (Template `unlock.html`, Feld `password`, Button `Entsperren`): nur wenn `is_local_request()` wahr ist: `request.remote_addr in ("127.0.0.1", "::1")` **und** keiner der Header `X-Forwarded-For`, `X-Forwarded-Proto`, `X-Forwarded-Host`, `Forwarded` vorhanden. Damit kann ein Tunnel (liefert von 127.0.0.1, setzt aber Forwarded-Header) die Seite nicht erreichen. `ProxyFix` bleibt bei `x_proto=1, x_host=1`, **kein** `x_for` (sonst wäre `remote_addr` spoofbar). Von anderen Adressen: `403` mit „Entsperren ist nur am Stand-Rechner möglich.“ Erfolg → DEK im Prozessspeicher, `session["admin"]=True`, Session-ID und CSRF-Token werden rotiert (`session.clear()` davor), Redirect auf `queue.admin_queue`. Danach laufen Migration (C12), Retention (C8), `last_seen`-Update.
- `/admin/login`: Feld `pin`, Label „Stand-PIN“, Button `Anmelden`. Bei Erfolg `session.clear()`, `session.permanent = True`, `session["admin"]=True`, neues `csrf_token`. `PERMANENT_SESSION_LIFETIME = timedelta(hours=12)`.
- Rate-Limit (`core.throttle`, In-Memory): Schlüssel `(remote_addr, X-Forwarded-For[:64])`; nach 5 Fehlversuchen Wartezeit `min(60, 2**(n-5))` Sekunden; zusätzlich globales Limit 30 Fehlversuche/Minute über alle Schlüssel (Backstop hinter einem Tunnel). Gilt für `/admin/login` und `/entsperren`. Fehlversuche vor dem Entsperren werden nur gezählt, nicht protokolliert (kein DEK).
- Transport im Stand-WLAN bleibt HTTP (kein selbstsigniertes TLS: Warnseiten auf Kundenhandys). Schutz: WPA2-Hotspot, Tresor-Passwort nie im LAN, PIN-Session 12 h, `HttpOnly`, `SameSite=Lax`. Das WLAN-Passwort auf dem Aushang (D4) ist optional; wer es druckt, akzeptiert, dass Gäste denselben Funkraum teilen – im Handbuch benannt, Reiserouter mit Gast-SSID empfohlen.
- Header in `app.after_request`: `Referrer-Policy: no-referrer`, `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY` (außer Endpoint `queue.display`), `Cache-Control: no-store` für Pfade unter `/admin`, `/q/`, `/entsperren`.

### C5 Zugriff nur über die App, Datenordner

- Dateien sind ohne laufende, entsperrte App unlesbar; Exporte nur über `login_required`-Routen.
- Datenordner (`launcher.py`): Liegt neben der ausführbaren Datei ein Ordner `data/` → portabler Modus. Sonst Windows `%LOCALAPPDATA%\Probefahrt\data`, macOS `~/Library/Application Support/Probefahrt/data`, Linux `~/.local/share/probefahrt/data`. `TOGG_DATA_DIR` bleibt als Override. Nie `Dokumente/` (Cloud-Sync). Button `Datenordner öffnen` in den Einstellungen (Karte „Daten & Backup“, nur lokal aktiv).
- Zweiter Prozess auf demselben Ordner wird über `data/.lock` (PID + Port) verhindert; Launcher zeigt „Läuft bereits auf Port 8470 – Browser wird geöffnet.“

### C6 Kiosk und Anzeige

Kiosk: `autocomplete=off` (vorhanden), Telefon maskiert, Datenschutz-Dialog, 60-Sekunden-Rücksprung, Kiosk-Cookie sperrt Admin-Login. Betriebsempfehlung im Handbuch: iPad „Geführter Zugriff“, Android „App anheften“. Anzeige zeigt nur Nummern, `/anzeige.json` enthält keine Personendaten. Status-Token `token_urlsafe(12)` + `compare_digest` bleibt.

### C7 Einwilligungsnachweis

- `consent_ref = sha256(fill(text, cfg).encode())[:12]` – gehasht wird der **ausgefüllte** Text (mit Firma/E-Mail), für `consent_text` (Leads), `queue_consent_text` (Queue) und `queue_marketing_text` (Queue-Lead).
- `data/consent_texts.json` (Klartext, keine Personendaten): `{"<ref>": {"text": "...", "first_used": ts, "last_used": ts}}`, gepflegt in `add_lead()` und `signup()`.
- Rechtsgrundlagen: Probefahrt-Daten (Name, Telefon, Fahrzeug, Zeiten, Checks) → Organisation der Probefahrt laut `queue_consent_text`; Marketing-Lead → nur mit `marketing_consent`. Export bekommt Spalten „Einwilligung am“, „Textversion“, „Kanal“; `GET /admin/einstellungen/einwilligungen.json` liefert `consent_texts.json` zum Nachweis.

### C8 Aufbewahrung – `retention.py`

Läuft nach jedem Entsperren und danach einmal täglich (Thread, `03:00`, nur wenn entsperrt). Jeder Lauf schreibt einen Audit-Eintrag.

- `queue_retention_days` (30): Einträge mit `created_at` älter → **anonymisieren**: `name="anonymisiert"`, `phone`, `email`, `note`, `end_note`, `token`, `consent_ref`, `marketing_consent` leeren; `number`, `day`, Zeiten, `vehicle_id`, `vehicle`, `checks`, `staff`, `status`, `end_condition` bleiben (Fahrzeugstatistik überlebt). `damages.text` wird nicht verändert (enthält per Konvention keine Personendaten; Placeholder sagt das).
- `lead_retention_days` (90): Leads **löschen**, aber nur mit gesehener Warnung: Ab 7 Tagen vor Fälligkeit erscheint das Banner „12 Interessenten werden am 14.01. gelöscht – jetzt exportieren.“ mit Link auf den Export. Beim ersten Anzeigen wird `sealed.retention_notice_at` gesetzt. Gelöscht wird, wenn `created_at + lead_retention_days <= heute` **und** `retention_notice_at + 7 Tage <= heute`. Nach einer Event-Pause sieht der Vertreter also immer erst die Warnung. Nach dem Lauf wird `retention_notice_at` geleert.
- `staff` in `queue.csv` bleibt (Kürzel/Vorname, Beschäftigtendaten minimal); wird mit `queue_retention_days` geleert.
- `audit.csv`: Einträge älter als 180 Tage werden gelöscht (fest, keine Einstellung).
- Platzhalter `{frist_leads}` und `{frist_warteschlange}` werden in `fill()` ergänzt und im Standard-`privacy_text` verwendet: „Speicherdauer: Interessenten {frist_leads} Tage, Probefahrt-Daten {frist_warteschlange} Tage (danach anonymisiert).“

### C9 Betroffenenrechte

- `GET /admin/person?q=<telefon|email|name>` (`admin_person.html`, Chip „Person suchen“ auf der Interessenten-Seite): sucht in `leads` und `queue`; Telefon über `phone_digits()` normalisiert; zeigt Treffer als Karten mit Quelle und Einwilligungsversion.
- `POST /admin/person/loeschen` (Felder `lead_ids[]`, `queue_ids[]`): Leads löschen, Queue-Einträge anonymisieren (wie C8). Confirm „Alle Daten dieser Person löschen bzw. anonymisieren?“. Danach werden alle Tages-Snapshots in `data/backup/` gelöscht und ein frischer Snapshot angelegt (sonst lebt die Person 7 Tage im Snapshot weiter). Flash: „Gelöscht. Hinweis: Heruntergeladene Backups und Exporte sind davon nicht betroffen.“
- `GET /admin/person/auskunft.xlsx?q=…`: Art.-15-Auskunft (Feld, Wert, Quelle, Einwilligung am, Textversion, Wortlaut) über `xlsx_response()`.
- Lead-Karte bekommt Link „Alle Daten dieser Person“ → `/admin/person?q=<email oder phone>`.

### C10 Export, Backup, Snapshots

- Exporte bleiben CSV/XLSX hinter Login, `safe_cell()` bleibt. Hinweis neben den Export-Chips (`.muted`): „Exporte sind unverschlüsselt – nach Übernahme ins CRM löschen.“ Jeder Export schreibt einen Audit-Eintrag (Typ, Zeilenzahl).
- `GET /admin/einstellungen/backup.zip` (Karte „Daten & Backup“, Button `Backup herunterladen`): `*.enc`, `vault.json`, `settings.json`, `consent_texts.json`, `license.key`, `media/`. Ohne Passwort/Code unbrauchbar. Wiederherstellen = Ordner einspielen, mit Passwort oder Wiederherstellungscode entsperren; beim Entsperren per Code bietet `unlock.html` direkt „Neues Tresor-Passwort setzen“.
- Snapshots: beim ersten Schreibvorgang eines Tages Kopie der `.enc`-Dateien nach `data/backup/YYYY-MM-DD/`, 7 Stück rotierend (Schutz gegen kaputte Datei nach Stromausfall). Werden bei Personenlöschung/Retention wie in C9 erneuert.

### C11 Audit – `audit.py`, `audit.csv.enc`

Spalten `ts, action, detail`. **Keine IP, keine Namen.** Aktionen: `unlock`, `login`, `login_failed`, `export_leads`, `export_queue`, `export_vehicles`, `export_person`, `delete_lead`, `delete_person`, `retention_run`, `license_set`, `backup`, `pin_changed`, `vault_password_changed`, `migration`. `detail` enthält nur IDs/Zahlen. Anzeige als Karte „Protokoll“ unter `/admin/einstellungen#protokoll` (Tabelle, letzte 200 Einträge, Link „Alle als CSV“). Waitress-Access-Log bleibt aus.

### C12 Migration bestehender Installationen

Beim ersten Start einer Version mit Vault existiert noch kein `vault.json`:

1. Launcher öffnet `/einrichtung` (D3). Der Assistent verlangt Tresor-Passwort, Wiederherstellungscode, Stand-PIN; das alte `admin_password_hash` wird ignoriert und aus `settings.json` entfernt.
2. Nach dem ersten Entsperren: `migrate.py` legt `data/alt-<datum>/` mit Kopien der Klartextdateien an, liest `leads.csv`, `queue.csv`, schreibt `.enc`, löscht die Klartextdateien, importiert `vehicles`-Zeilen aus den Einstellungen, übernimmt `queue_also_lead`→`queue_marketing_optin`, löscht `.secret_key`. Audit `migration`. Handbuch-Hinweis: Klartextreste auf SSDs sind forensisch nicht sicher gelöscht; BitLocker/FileVault empfohlen; den Ordner `alt-<datum>/` nach Prüfung löschen (Button in der Karte „Daten & Backup“: `Alte Klartextdaten endgültig löschen`).

### C13 Bewusst nicht (Sicherheit)

SQLCipher, Feldverschlüsselung, TLS mit eigener CA im Stand-WLAN, WebAuthn/2FA, Mehrbenutzer/Rollen, Remote-Wipe, Request-Logging, OS-Keyring-Auto-Unlock (verschiebt den Schutz auf das OS-Login; später als Option denkbar), Telemetrie (gibt es nicht).

---

## D) Deployment & Lizenz

### D1 Modell: Stand-Server auf dem Laptop, Browser-Clients

Ein Laptop am Stand führt `Probefahrt` aus; Kiosk-Tablet, Anzeige, Mitarbeiter-Handys sind nur Browser im selben WLAN. Kunden-Handys: Anruf/SMS/WhatsApp vom Mitarbeiter-Handy ist der Hauptkanal; die Live-Statusseite ist Bonus (braucht Stand-WLAN oder Online-Tunnel). Reine Offline-PWA, Cloud-SaaS, Raspberry-Kit, Electron und Docker sind verworfen (Gründe in E).

Netz-Empfehlung in dieser Reihenfolge: **(1) Reiserouter** (GL.iNet-Klasse, ~40 €, feste SSID, DHCP-Reservierung für den Laptop, optional Gast-SSID für Kunden), **(2) Handy-Hotspot des Vertreters** (ohne Hardware, bringt Uplink für den Online-Bonus, IP kann wechseln), **(3) Windows „Mobiler Hotspot“ / macOS Internetfreigabe** nur als Notlösung (startet ohne Uplink oft nicht).

### D2 Launcher und Netz – `launcher.py`

1. Datenordner bestimmen (C5), `data/.lock` prüfen.
2. Port **8470** (macOS belegt 5000 mit AirPlay); belegt → 8471 … 8479. Der tatsächlich gebundene Port steht in `app.config["PORT"]` und in allen QR-Codes.
3. LAN-IPs ermitteln (`socket.getaddrinfo` + UDP-Connect-Trick, optional `ifaddr`); Bevorzugung: `192.168.8.x` (GL.iNet), `172.20.10.x` (iPhone), `192.168.137.x` (Windows-Hotspot), sonst erste private Adresse. Ergebnis als `app.config["LAN_BASE"] = "http://<ip>:<port>"`.
4. `public_base()` in `queue_routes.py` wird: `settings.public_url` → sonst `app.config["LAN_BASE"]` → sonst `request.url_root`. Damit enthalten QR-Codes nie `127.0.0.1`.
5. Waitress auf `0.0.0.0:<port>`, `threads=8`; Browser öffnet `http://127.0.0.1:<port>/` (leitet auf `/einrichtung` oder `/entsperren` oder `/admin/warteschlange`).
6. Konsolenfenster (Windows) bzw. Terminal (macOS) zeigt `Probefahrt 1.0.0 · läuft auf http://192.168.8.100:8470 · Fenster schließen = Beenden`. Kein Tray-Icon in V1.
7. Wechselt die IP (anderer Hotspot), zeigt `/admin/verbinden` die aktuelle; Lesezeichen auf Tablets müssen dann neu gesetzt werden – steht in der Checkliste.

Online-Bonus (optional, nur bei vorhandenem Internet): **Tailscale Funnel** (`tailscale funnel 8470`), stabiler Hostname, TLS endet auf dem Laptop (Tailscale sieht keine Inhalte). URL in `public_url` eintragen → Kunden-QR funktioniert über Mobilfunk, HTTPS liefert Benachrichtigungen/Wake Lock. **Cloudflare Tunnel wird nicht empfohlen** (Quick-Tunnel-URL wechselt, TLS-Terminierung bei Cloudflare = Auftragsverarbeiter).

### D3 Startablauf für den Vertreter

**Einmalig:**
1. Portal (D8): Code eingeben, ZIP für Windows oder macOS laden, `license.key` speichern.
2. ZIP entpacken, `Probefahrt/Probefahrt.exe` bzw. `Probefahrt.app` starten. Windows: SmartScreen „Weitere Informationen → Trotzdem ausführen“, Firewall „Zugriff zulassen“ für **private und öffentliche** Netze. macOS: Systemeinstellungen → Datenschutz & Sicherheit → „Trotzdem öffnen“ (Rechtsklick-Öffnen reicht seit macOS 15 nicht).
3. Browser öffnet `http://127.0.0.1:8470/einrichtung` (`setup.html`, nur Loopback, nur solange kein `vault.json` existiert), vier Karten nacheinander mit Button `Weiter`:
   - **Lizenz**: `license.key` neben der EXE oder in `data/` wird automatisch gefunden; sonst Datei-Upload oder Einfügefeld. Anzeige „Autohaus Müller GmbH · Togg · gültig bis 31.12.2026“. Ohne Lizenz: Button `Ohne Lizenz testen (14 Tage)` → Demo-Modus (D6).
   - **Tresor-Passwort** (≥ 10 Zeichen, zweimal) + **Wiederherstellungscode** (angezeigt, Button `Drucken`, Pflicht-Checkbox „Ich habe den Wiederherstellungscode notiert“).
   - **Stand-PIN** (6–12 Zeichen, zweimal, Hilfe „Für die Anmeldung vom Handy und Tablet.“).
   - **Marke**: `brand_name`, `accent_color`, `company`, `privacy_email` – aus der Lizenz (`brand`, `cust`) vorbelegt.
   Button `Fertig` → entsperrt, Migration (C12), Redirect `/admin/verbinden`.

**Jeder Event-Tag:**
1. Router/Hotspot an, Laptop-Energiesparen aus (Checkliste).
2. `Probefahrt` starten → Browser → `/entsperren` → Tresor-Passwort → Warteschlange.
3. `/admin/verbinden` öffnen, Tablet/Anzeige/Handy per QR verbinden (D4).
4. Abends: Tagesabschluss (verweigert bei offener Fahrt), Fenster schließen.

### D4 Geräte verbinden – `GET /admin/verbinden` (`admin_connect.html`)

Drei Karten mit QR (`/qr.svg?p=…`) und Klartext-URL:
- **Kiosk-Tablet** → `/warteschlange?kiosk=1`; Hinweis „Zum Home-Bildschirm hinzufügen, dann Geführter Zugriff (iPad) bzw. App anheften (Android).“
- **Aufruf-Anzeige** → `/anzeige`; Hinweis „Einmal auf ‚Ton & Vollbild‘ tippen.“
- **Mitarbeiter-Handy** → `/admin/login` (kein Token in der URL).

Darunter Karte **Stand-WLAN (optional)**: Felder `wifi_ssid`, `wifi_password`, Button `Speichern` (→ `save_settings`), danach WLAN-QR (`WIFI:T:WPA;S:<ssid>;P:<pw>;;`). Wird auf dem Aushang wiederverwendet. Hinweis: „Wer das WLAN-Passwort aushängt, lässt Kunden in dasselbe Netz. Mit Reiserouter: Gast-WLAN verwenden.“

Karte **Selbsttest**: „Diese Adresse vom Handy öffnen: http://192.168.8.100:8470/ping – erscheint ‚OK‘, ist alles verbunden. Sonst: Firewall-Freigabe prüfen, Client-Isolation im Router ausschalten, Energiesparen aus.“ `GET /ping` liefert `OK` ohne Login, auch gesperrt.

`queue_poster.html`: zeigt zwei QR-Codes nebeneinander, wenn `wifi_ssid` gesetzt ist („1. WLAN verbinden“, „2. Anmelden“), sonst einen wie heute.

### D5 Lizenz – `licensing.py`

- Schlüsselpaar einmalig: `python tools/license_cli.py keygen` → `vendor_private.key` (nur beim Anbieter, Passwortmanager, nie im Repo) und Konstante `VENDOR_PUBLIC_KEYS = {"k1": "<32 Byte hex>"}` in `licensing.py`.
- Format: `PF1.<base64url(payload)>.<base64url(signatur)>`; Ed25519 über `b"PF1." + payload_b64`. Payload:
  ```json
  {"v":1,"kid":"k1","id":"LIC-2026-0042","cust":"Autohaus Müller GmbH","brand":"Togg",
   "nb":"2026-10-01","exp":"2026-12-31","grace":14,"feat":["leads","queue","vehicles"]}
  ```
- Ablage: `data/license.key` (bevorzugt) oder `license.key` neben der ausführbaren Datei. `POST /admin/einstellungen/lizenz` (Karte „Lizenz“ in den Einstellungen, Feld `license` oder Upload) prüft, speichert nach `data/license.key`, Audit `license_set`, gilt sofort ohne Neustart.
- `licensing.status()` (gecacht 60 s, bei jedem Request über `inject_globals` als `license` an Templates):
  1. Syntax, `kid` bekannt, Signatur, `v == 1` → sonst `invalid`.
  2. `effective_today = max(heute, sealed.last_seen.date())` wenn entsperrt, sonst `heute`. `last_seen` wird bei jedem Entsperren und jedem Schreibvorgang auf `max(last_seen, now)` gesetzt.
  3. `nb <= effective_today <= exp` → `valid`; `exp < effective_today <= exp + grace` → `grace`; `effective_today > exp + grace` → `expired`; `effective_today < nb` → `not_yet_valid`.
  4. Keine Datei: `setup_at + 14 Tage >= heute` → `demo` (voll nutzbar, Banner „Demo-Modus – noch 9 Tage“), sonst `none`.
  5. Zusätzlich `clock_suspect = heute < last_seen - 1 Tag` → nur Banner „Die Systemzeit scheint zurückgestellt (zuletzt gesehen: 14.10.2026). Bitte Datum prüfen.“ Keine Sperre durch die Uhr allein – gesperrt wird nur, wenn die Lizenz nach `effective_today` abgelaufen ist.
  6. `feat`: fehlt `vehicles` → Fahrzeuge-Tab und Start-Panel aus (Fahrzeugmodul inaktiv); fehlt `leads`/`queue` → Modul-Schalter erzwungen aus.
- Keine Hardware-Bindung (Laptop-Tausch am Messetag). `cust` und `id` stehen im Admin-Footer („Lizenz: Autohaus Müller GmbH · LIC-2026-0042 · bis 31.12.2026“).

### D6 Ablaufverhalten (Statuswirkung)

| Status | Kundenseiten `/`, `/warteschlange`, `/q/<token>`, `/anzeige` | Admin |
|---|---|---|
| `valid`, `demo` | normal | normal (Demo: Banner) |
| `grace` | normal | Banner `.flash warn`: „Lizenz abgelaufen am 31.12. – noch 9 Tage Kulanz. Neuen Schlüssel eingeben →“ |
| `expired`, `none`, `not_yet_valid`, `invalid` | `/`, `/warteschlange`: Seite `restricted.html` „Derzeit keine Anmeldung möglich.“; `/q/<token>` zeigt den eigenen Status weiterhin (lesend); `/anzeige` neutraler Text ohne Nummern | **erlaubt**: Entsperren, Login, alle Listen, alle Exporte, Auskunft, Person/Lead löschen, Backup, Protokoll, Einstellungen Abschnitte „Datenschutz“ und „Lizenz“, Aufbewahrungslauf, Tagesabschluss. **gesperrt** (403 + Flash „Lizenz abgelaufen – diese Aktion ist nicht möglich.“): Aktionen `call`, `start`, `end`, `requeue`, `reopen`; Fahrzeuge anlegen/ändern/sperren; übrige Einstellungen speichern |

Ab 14 Tagen vor `exp` Banner „Lizenz endet am 31.12. – neuen Schlüssel eingeben →“. Ablaufzeitpunkt `exp` 23:59 Lokalzeit. Umsetzung: Hilfsfunktion `license_write_allowed()` in `licensing.py`; `admin_queue_action` prüft pro `action` (Liste `LICENSED_ACTIONS`), `vehicles.py` prüft in jedem POST, `admin_settings` prüft pro Abschnitt.

### D7 Packaging und Update – `probefahrt.spec`, `.github/workflows/build.yml`

- PyInstaller **onedir**, als ZIP ausgeliefert: `probefahrt-1.0.0-windows.zip` (`Probefahrt/Probefahrt.exe`), `probefahrt-1.0.0-macos-arm64.zip` (`Probefahrt.app`, `BUNDLE` im Spec, `console=True` damit das Terminal die Adresse zeigt). Datas: `templates`, `static` (`--add-data` in Spec-Syntax, plattformneutral). Hiddenimports: `openpyxl`, `qrcode.image.svg`, `cryptography`.
- Matrix: `windows-latest`, `macos-14` (Apple Silicon). Kein Intel-macOS-Build in V1 (kein Runner mehr; Intel-Macs ≤ 2020 bei Bedarf lokal bauen).
- Release bei Tag `v*` mit SHA-256-Summen; `APP_VERSION` aus dem Tag, sichtbar im Admin-Footer und im Portal.
- `requirements.txt`: `flask>=3.0`, `waitress>=3.0`, `openpyxl>=3.1`, `qrcode>=7.4`, `cryptography>=42`; `requirements-build.txt`: `pyinstaller>=6.6`, optional `ifaddr`.
- Code-Signing: ohne Zertifikat Warnungen (SmartScreen, Gatekeeper); Apple Developer ID + Notarisierung und Windows-OV-Zertifikat als Workflow-Schritte vorbereitet, aktiv erst mit Secrets (Frage G2).
- Update: neues ZIP über den alten Ordner entpacken; `data/` liegt im Profil. `Table._ensure()`/`DEFAULTS` migrieren Spalten/Einstellungen; `vault.json` und Dateiformat tragen `v`. Kein Auto-Update, kein Phone-Home. Button `Auf Updates prüfen` (Karte „Lizenz“) ruft nur auf Klick `https://<portal>/version.json` ab.

### D8 Portal „Code eingeben → eigene Version“ – `portal/` (statisch, kein Backend)

- Kurzcode je Kunde: `XXXX-XXXX-XXXX`, Crockford-Base32, 60 Bit Zufall, z. B. `7K3Q-9ZPD-MX4T`. Nur Lookup-Schlüssel, keine Signatur.
- Ableitung (WebCrypto, PBKDF2-SHA256, 600 000 Iterationen, Code normalisiert ohne Bindestriche, Großschreibung): `name = hex(PBKDF2(code, salt="pf-portal-name"))[:32]`, `key = PBKDF2(code, salt="pf-portal-key")` (32 Byte). Datei `portal/licenses/<name>.bin` = 12 Byte Nonce + AES-256-GCM(key, JSON). Damit darf das Repo öffentlich sein: Dateinamen verraten nichts, Inhalte sind ohne Code unlesbar, Brute-Force über 60 Bit × 600k Iterationen ist unpraktikabel.
- JSON-Inhalt: `{"customer","brand","valid_until","license":"PF1…","version":"1.0.0","downloads":{"windows":"<Release-URL>","macos":"<Release-URL>"},"notes":""}`.
- `portal/index.html` (kein Framework): Eingabefeld, Button `Anzeigen`; Ergebnis „Ihre Version: Autohaus Müller GmbH · Togg · gültig bis 31.12.2026 · Version 1.0.0“, Buttons `Windows laden`, `macOS laden`, `license.key speichern`, `Schlüssel kopieren`, darunter die Kurzanleitung aus D3. Fehlertext: „Code nicht gefunden. Bitte Schreibweise prüfen.“
- `portal/version.json`: `{"version":"1.0.0","released":"2026-10-14"}`.
- Anbieter-Workflow: `license_cli.py issue --customer "Autohaus Müller GmbH" --brand Togg --nb 2026-10-01 --exp 2026-12-31 --feat leads,queue,vehicles` → gibt Kurzcode und Lizenz aus, schreibt `portal/licenses/<name>.bin` und einen Eintrag in `tools/issued.jsonl` (lokal, nicht im Repo); Commit + Push → Pages. `license_cli.py renew --id LIC-2026-0042 --exp 2027-03-31` überschreibt die `.bin` unter demselben Code; der Kunde holt den neuen Schlüssel und spielt ihn unter Einstellungen → Lizenz ein.

### D9 Dateiliste (neu/geändert)

Neu: `vault.py`, `vehicles.py`, `retention.py`, `audit.py`, `licensing.py`, `migrate.py`, `launcher.py`, `probefahrt.spec`, `tools/license_cli.py`, `portal/index.html`, `portal/version.json`, `portal/licenses/`, `.github/workflows/build.yml`, `requirements-build.txt`, Templates `_vehicle_strip.html`, `_start_panel.html`, `_end_panel.html`, `admin_vehicles.html`, `vehicle_form.html`, `admin_connect.html`, `admin_person.html`, `setup.html`, `unlock.html`, `locked.html`, `restricted.html`, `HANDBUCH.md` (Stand-Checkliste).
Geändert: `core.py`, `app.py`, `queue_routes.py`, `_queue_list.html`, `admin_queue.html`, `admin_base.html`, `settings.html`, `admin.html`, `login.html`, `queue_signup.html`, `queue_ticket.html`, `queue_status.html`, `queue_poster.html`, `display.html`, `privacy.html`, `style.css`, `requirements.txt`, `README.md`.

---

## E) Bewusst NICHT gebaut (mit Grund)

| Weggelassen | Grund |
|---|---|
| Fotos (Schäden, Führerschein) | Upload, Verkleinerung, verschlüsselte Ablage, Auslieferung, Backup-Größe verdoppeln das Fahrzeugmodul; Führerschein-Foto ist Datenmaximierung. Zustand: Stufe 2, falls Händler es verlangen. |
| Führerscheinnummer/-klasse, Adresse des Fahrers | Datenminimierung; gehört auf die Papier-Probefahrtvereinbarung. Gespeichert wird nur „Führerschein gesehen“ als bestätigter Check. |
| Digitale Unterschrift / PDF-Vereinbarung | Rechts-, Beweis- und Versionierungsfragen plus PDF-Generator; Papier ist Standard. App protokolliert nur „unterschrieben“. |
| Fahrtenbuch-Export für rote Kennzeichen | Verlangt Anschrift und FIN, die die App bewusst nicht erhebt; der Probefahrt-Export unterstützt nur. Rechtslage (FZV) ist vom Auftraggeber zu prüfen. |
| km-Stand, Tank-/Ladestand in Prozent | Werden im Trubel nicht gepflegt; „gesperrt: Laden“ ist die einzige Information, die die App braucht (ETA). |
| Zonen-/Art-Chips für Schäden, Schweregrad | Freitext reicht in der Praxis; neun Zonen und sechs Arten sind UI-Last ohne Mehrwert. |
| Eigene `drives.csv` | Der Warteschlangen-Eintrag ist die Fahrt; eine zweite Tabelle wäre dieselbe Wahrheit doppelt. |
| Wunschmodell in der Anmeldung | Verlängert Kiosk-Flow und Warteschlange pro Modell; Notizfeld und Interessen-Chips decken es ab. Stufe 2. |
| Zeitslots/Reservierung | Messe-Realität ist „wer da ist, ist dran“; Slots erzeugen No-Shows und ein zweites Statusmodell. |
| Kunde wählt Fahrzeug selbst | Vertreter verliert die Steuerung. |
| GPS/Live-Tracking | Überwachung des Fahrers, offline nicht machbar. |
| Mehrere Admin-Benutzer mit Rollen | Ein Stand-PIN plus Begleiter-Chip reicht; Rollen erst bei zentralem Betrieb. |
| Begleitperson des Kunden erfassen | Daten Dritter, kein Nutzen für den Ablauf. |
| Nach-Fahrt-Interessenabfrage auf dem Kundenhandy | Setzt Stand-WLAN voraus (widerspricht „Status ist Bonus“); Marketing-Opt-in am Kiosk ist der sauberere Ort. |
| Reine Offline-PWA | Kein gemeinsamer Zustand für Tablet, Anzeige, Handys. Clients sind „Zum Home-Bildschirm“; echte PWA-Installation braucht HTTPS. |
| Cloud-SaaS | Internet am Stand nötig, Anbieter wird Auftragsverarbeiter (AVV, TOMs, Haftung), Hostingkosten. Später als Stufe für zentralen Betrieb denkbar. |
| Raspberry-Pi-/Mini-PC-Kit | Hardware-Logistik; gleiche Software, nur ein Build-Target. Später als Option. |
| Electron/Tauri, Docker, Android als Server | Kein Nutzen gegenüber „Browser öffnet sich“; für Vertriebler nicht zumutbar. |
| Cloudflare Tunnel | Wechselnde URL (Aushang ungültig), TLS-Terminierung bei Cloudflare = Auftragsverarbeiter. Nur Tailscale Funnel. |
| Selbstsigniertes TLS im Stand-WLAN | Warnseiten auf Kundenhandys, QR-Flows brechen. |
| Hardware-Bindung der Lizenz | Bestraft ehrliche Kunden beim Laptop-Tausch am Messetag; kurze Laufzeiten und sichtbare Kundenkennung sind der Schutz. |
| Auto-Update, Telemetrie | Kein Internet, keine stille Änderung am Messetag; keine Daten verlassen den Stand. |
| Passwortgeschützte XLSX | `openpyxl` kann es nicht; Scheinsicherheit. |
| SMS-Gateway, Web-Push-Server | Kosten, Internet; `sms:`/`tel:`-Links vom Mitarbeiter-Handy sind zuverlässiger. |
| Intel-macOS-Build | GitHub bietet keinen Intel-Runner mehr; betroffene Macs sind ≥ 6 Jahre alt. |

---

## F) Umsetzungsreihenfolge (ein erfahrener Entwickler, Personentage realistisch)

| # | Schritt | Inhalt | PT |
|---|---|---|---|
| 1 | **Fahrzeuge-Kern** | `DATA_LOCK`, `vehicles.csv`, `damages.csv`, neue Queue-Spalten, `vehicles.py` (CRUD, Sperren, Archiv, Schäden), Status-Ableitung, `queue_state` mit Fahrzeugzahl, Start-Panel, Ende mit 1 Tap + Auffälligkeits-Panel, Takeover/Force, Guards für `reopen`/`delete`/Tagesabschluss, Fahrzeug-Leiste, Fehler-/Hinweis-JS, Fahrzeuge-Tab, Formular, Export-Spalten + `?vehicle=`, Settings-Änderungen, Migration der `vehicles`-Zeilen, `max_drive_minutes`/überfällig | 5–6 |
| 2 | **Bestandsfixes & Kunden-Seiten** | `public_base()` mit `LAN_BASE`, Marketing-Opt-in statt `queue_also_lead`, Kiosk-Dialog für Datenschutz, Telefon-Maskierung, Kiosk-Cookie, HTTP-Hinweis auf der Statusseite, Security-Header, `requirements.txt` | 1 |
| 3 | **Tresor & Login** | `vault.py` (AES-GCM-Dateien, scrypt, zwei Slots, `sealed`, Recovery-Code), `Table` über Vault, `/entsperren` mit Loopback-Regel, `locked.html`, Stand-PIN, Rate-Limit, Session-Rotation, Secret pro Prozess, `/einrichtung`-Assistent, `migrate.py` (Klartext → `.enc`, alte Hashes, `.secret_key`) | 4–5 |
| 4 | **DSGVO-Schicht** | `consent_ref` + `consent_texts.json`, `retention.py` mit Warnlogik, `/admin/person` (Suche, Löschen, Auskunft), `audit.py` + Protokoll-Karte, Backup-ZIP, Tages-Snapshots mit Bereinigung, Platzhalter `{frist_*}`, Settings-Abschnitt „Datenschutz“ | 2–3 |
| 5 | **Lizenz** | `licensing.py` (Ed25519, Statusmaschine, `last_seen`, Demo), Karte „Lizenz“, Gating pro Aktion/Route, Banner, `restricted.html`, `tools/license_cli.py` (keygen/issue/renew) | 2 |
| 6 | **Launcher, Verbinden, Packaging, Portal** | `launcher.py` (Datenordner, Lockfile, Port, IP-Erkennung, Browser), `/admin/verbinden` + `/ping`, WLAN-QR, Zwei-QR-Aushang, `probefahrt.spec`, Actions-Matrix + Release, `portal/` mit PBKDF2-Lookup, Signing-Schritte vorbereitet | 3–4 |
| 7 | **Realtest & Doku** | Testtag mit Laptop + Reiserouter + Tablet + TV + zwei Handys (Firewall, Schlaf, IP-Wechsel, 409-Fälle, Takeover, Lizenzablauf/Kulanz/Uhr zurück, Restore mit Recovery-Code), `HANDBUCH.md` (Stand-Checkliste), README, Datenschutz-Textvorlage | 2 |

Gesamt **19–23 PT**. Schritte 1–2 sind sofort am Stand nutzbar und unabhängig von 3–6; Schritt 3 vor 4 und 6 (Vault, Datenordner); Schritt 5 ist unabhängig von 3 (Lizenz liegt im Klartext) und kann parallel laufen.

---

## G) Offene Fragen an den Auftraggeber (blockierend)

1. **Lizenzmodell und Laufzeit**: pro Event (Tage), pro Saison oder pro Jahr und Händler? Darf eine Lizenz mehrere Stände parallel abdecken? Bestimmt `nb`/`exp`-Defaults im CLI, Kulanzdauer und ob `feat`-Stufen (ohne Fahrzeuge günstiger) gebraucht werden.
2. **Code-Signing-Budget**: Apple Developer ID (99 $/Jahr) + Notarisierung und Windows-OV-Zertifikat (200–300 €/Jahr) – ja oder nein? Ohne: SmartScreen/Gatekeeper-Warnungen und Supportaufwand am Messetag; der Build-Workflow wird je nach Antwort anders aufgesetzt.
3. **Produktname / White-Label**: Wie heißt die ausführbare Datei, der Datenordner (`Probefahrt`?) und das Portal? Muss vor Packaging und Portal feststehen.
4. **Papier bleibt Papier?** Probefahrtvereinbarung und Führerscheinkontrolle werden nur als Checks protokolliert (Empfehlung). Soll die App stattdessen Unterschrift, Führerscheindaten oder Fotos erfassen, ändert sich Datenmodell, Verschlüsselung und Aufbewahrung grundlegend.
5. **Rote Kennzeichen**: Soll die App das alleinige Fahrtenbuch sein (dann Pflichtfelder Anschrift/FIN und ein Jahr Aufbewahrung, was der Anonymisierung nach 30 Tagen widerspricht) oder ergänzt sie das Papier-Übergabeprotokoll (Empfehlung, aktuelle Spezifikation)?