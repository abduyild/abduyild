# Togg Leads (Python / Flask)

Nachbau von *togg-leads.vercel.app* (Interessenten-Formular) und *togg-leads-admin.vercel.app* (Admin-Ansicht) –
komplett lokal mit **CSV-Datei als Datenbank**.

## Start

```bash
cd togg-leads
python3 -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# Admin-Passwort setzen (Standard ist "admin")
export TOGG_ADMIN_PASSWORD="meinGeheimesPasswort"    # Windows: set TOGG_ADMIN_PASSWORD=...

python app.py
```

| Seite                | URL                                |
|----------------------|------------------------------------|
| Formular             | http://127.0.0.1:5000/             |
| Admin-Ansicht        | http://127.0.0.1:5000/admin        |
| Datenschutz          | http://127.0.0.1:5000/datenschutz  |

## Funktionen

**Formular** – Name*, E-Mail*, Telefonnummer, Postleitzahl, Interesse* (Testfahrt / Finanzierung, Mehrfachauswahl),
Notizen, DSGVO-Einwilligung*. Serverseitige Validierung, CSRF-Schutz, Honeypot gegen Spam-Bots.

**Admin (`/admin`)** – Passwort-Login, Kacheln (Gesamt / Testfahrt / Finanzierung / Heute), Suche über
Name, E-Mail, Telefon, PLZ und Notizen, Filter-Chips, Export als **CSV** und **Excel** (berücksichtigt aktive
Filter/Suche), Löschen von Einträgen.

## Daten

Alle Einträge liegen in `data/leads.csv` (wird beim ersten Start angelegt, ist in `.gitignore`).
Spalten: `id, created_at, name, email, phone, zip_code, interests, notes, consent`
(`interests` ist mit `|` getrennt, `consent` = Zeitpunkt der Einwilligung).

Optionale Umgebungsvariablen:

| Variable              | Bedeutung                                   | Standard        |
|-----------------------|---------------------------------------------|-----------------|
| `TOGG_ADMIN_PASSWORD` | Passwort für `/admin`                       | `admin`         |
| `TOGG_DATA_DIR`       | Ordner für CSV + Session-Schlüssel          | `./data`        |
| `TOGG_SECRET_KEY`     | Flask-Session-Schlüssel                     | wird generiert  |
| `HOST` / `PORT`       | Server-Adresse                              | `127.0.0.1:5000`|

> Für den Zugriff aus dem Heimnetz (z. B. vom Handy): `HOST=0.0.0.0 python app.py` und dann
> `http://<IP-des-Rechners>:5000` öffnen.
