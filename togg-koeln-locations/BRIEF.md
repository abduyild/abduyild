# Togg Brand Event Köln — Location-Vergleich (PDF)

Status: **blockiert durch Netzwerk-Policy**. Inhalt und Werkzeuge stehen, es fehlt
ausschließlich der ausgehende HTTPS-Zugriff.

## Auftrag

Kompaktes PDF, A4, ca. 6 Seiten, Akzentfarbe Rot, schlicht/modern.

- **Seite 1 — Übersicht:** echte Köln-Karte (OpenStreetMap) mit 5 nummerierten Pins,
  Dom/Hbf markiert, Hauptstraßen und Rhein sichtbar. Tabelle
  `Location | Auto zum Dom | ÖPNV zum Dom | Ebenerdig | Bewertung (5 Sterne)`.
  Fazit in 2–3 Sätzen.
- **Seiten 2–6 — je eine Location:** Name, Adresse, Bewertung; anklickbarer
  Google-Maps-Link + QR-Code; Kartenausschnitt mit Straßennamen und markiertem
  Standort; 2–3 Fotos (min. 1 außen, 1 innen) mit Quellenangabe unter jedem Foto
  (bevorzugt offizielle Website); Kurztabelle (Auto zum Zentrum km + Min, ÖPNV
  Linie + Min, Ebenerdigkeit / mit Fahrzeug befahrbar, Parken); „Was sie
  einzigartig macht" (3 Stichpunkte); „Worauf achten" (1–2 Sätze).

Regeln: Fahrzeiten per echter Routenplanung (Ziel Kölner Dom/Hbf, werktags ohne
Stau). Alle Fakten auf den Websites prüfen, nichts erfinden, Unklares als
„anfragen" markieren. Alle Locations haben mindestens eine Tiefgarage.
Gästeanzahl ist irrelevant.

## Locations (Kundenangaben — zu prüfen, nicht zu übernehmen)

| # | Location | Adresse | Web | Bewertung lt. Kunde |
|---|---|---|---|---|
| 1 | BAUWERK | Dillenburger Str. 73, 51105 Köln-Kalk | bauwerk-event.de | 4,5/5 |
| 2 | Schokoladenmuseum (Eventbereich) | Am Schokoladenmuseum 1a, 50678 Köln | schokoladenmuseum-event.de | 4/5 |
| 3 | HARBOUR.CLUB | Hafenstraße 4, 51063 Köln-Mülheim | harbour-club.de | 3,5/5 |
| 4 | Sessel Hub Rheinauhafen | Kranhaus Nord, Im Zollhafen 12, 50678 Köln | sesselkampagne.koeln/raum-mieten | 3/5 |
| 5 | Sturmfreie Bude | Uni-Center, Luxemburger Str. 124–126, 50939 Köln | budenfreunde.de/eventlocation-koeln | 2,5/5 |

Offene Punkte, die die Recherche klären muss:
- **2 Schokoladenmuseum:** Fahrzeuge in den Räumen? Tiefgarage Rheinauhafen
  Einfahrtshöhe 1,90 m bestätigen.
- **3 HARBOUR.CLUB:** Befahrbarkeit und Parken komplett unklar.
- **1 BAUWERK:** 666 m², 6 Event-Boxen, LED-Wall 6×3,5 m, Catering gebunden,
  Referenzen Volvo/Polestar verifizieren.
- **4 Sessel Hub:** ca. 250 m², ÖPNV Linie 15/16 Ubierring bzw. Bus 133.
- **5 Sturmfreie Bude:** 29. Stock, 300 m², nicht ebenerdig, Wohnhaus → nur bis 22 Uhr.

## Blocker

Die Egress-Policy dieser Umgebung lässt nur GitHub und Paket-Registries durch.
Gemessen: alle fünf Location-Domains, `tile.openstreetmap.org` und
`upload.wikimedia.org` antworten mit 403 am Gateway (`connect_rejected`).
`*.googleapis.com` ist erreichbar, verlangt aber einen Maps-API-Key.

Damit unmöglich: Fotos, Karten, Faktenprüfung, echte Routenplanung.

## Benötigte Freigaben

Am robustesten ist eine offene Outbound-HTTPS-Policy — eine Allowlist trifft sonst
laufend nicht gelistete Bild-CDNs der Websites. Falls eine Allowlist nötig ist:

    bauwerk-event.de, www.bauwerk-event.de
    schokoladenmuseum-event.de, www.schokoladenmuseum-event.de
    harbour-club.de, www.harbour-club.de
    sesselkampagne.koeln, www.sesselkampagne.koeln
    budenfreunde.de, www.budenfreunde.de
    tile.openstreetmap.org, a.tile.openstreetmap.org,
    b.tile.openstreetmap.org, c.tile.openstreetmap.org   # Kartenkacheln
    nominatim.openstreetmap.org                          # Geocoding der Adressen
    router.project-osrm.org                              # Auto-Routing
    v6.db.transport.rest                                 # ÖPNV (VRS/KVB), keyless

Die Policy hängt am Environment, nicht an der Session, und der Proxy ist beim
Containerstart fixiert: nach der Änderung eine **neue Session** starten.
Doku: https://code.claude.com/docs/en/claude-code-on-the-web

## Werkzeuge — bereits geprüft, funktionieren

- PyPI ist per `noProxy` direkt erreichbar: `pip install reportlab qrcode pillow` läuft.
- Chromium liegt unter `/opt/pw-browsers` (HTML→PDF-Rendering möglich).
- Empfohlener Weg: HTML/CSS mit `@page`-Regeln für A4 → Chromium headless → PDF.
  Karten aus OSM-Kacheln zusammensetzen, Pins und Beschriftung als SVG-Overlay.

## Nächste Schritte nach der Freigabe

1. Websites abrufen, Fakten gegen die Kundenangaben prüfen, Abweichungen und
   Unklarheiten als „anfragen" markieren.
2. Fotos herunterladen (min. 1 außen + 1 innen je Location), Quell-URL je Foto festhalten.
3. Adressen geocodieren, Auto- und ÖPNV-Routen zum Dom/Hbf berechnen.
4. Übersichtskarte und fünf Umgebungsausschnitte rendern.
5. PDF bauen, gegenlesen, committen.
