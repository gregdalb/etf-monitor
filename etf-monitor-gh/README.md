# ETF Monitor – GitHub Pages Setup

Kostenloses Hosting auf GitHub Pages + GitHub Actions.
Einrichtung dauert ca. 10 Minuten.

---

## Schritt 1 – GitHub-Account

Falls noch nicht vorhanden: https://github.com/signup (kostenlos)

---

## Schritt 2 – Repository anlegen

1. Auf https://github.com/new gehen
2. Repository Name: `etf-monitor` (oder beliebig)
3. **Private** auswählen (empfohlen – niemand sieht deine Daten)
4. Auf **Create repository** klicken

---

## Schritt 3 – Dateien hochladen

### Option A: Per Browser (einfachster Weg)

1. Im neuen Repository auf **"uploading an existing file"** klicken
2. Alle Dateien aus diesem ZIP per Drag & Drop hochladen
   - Wichtig: Die Ordnerstruktur muss erhalten bleiben:
     ```
     .github/workflows/etf-check.yml
     checker/etf_checker.py
     dashboard/index.html
     dashboard/dashboard.json
     .gitignore
     ```
3. **Commit changes** klicken

### Option B: Per Git (falls installiert)

```bash
cd etf-monitor-gh
git init
git remote add origin https://github.com/DEIN-USERNAME/etf-monitor.git
git add .
git commit -m "Initial commit"
git push -u origin main
```

---

## Schritt 4 – Secrets eintragen

Die drei geheimen Werte kommen **nie** in den Code – nur als verschlüsselte Secrets:

1. Im Repository → **Settings** → **Secrets and variables** → **Actions**
2. Auf **New repository secret** klicken, drei Secrets anlegen:

| Name | Wert |
|------|------|
| `TELEGRAM_TOKEN` | Dein Bot-Token vom @BotFather |
| `TELEGRAM_CHAT_ID` | Deine numerische Chat-ID |
| `ANTHROPIC_API_KEY` | Dein Anthropic API-Key |

**Telegram Chat-ID herausfinden** (falls noch nicht bekannt):
1. Deinen Bot einmal anschreiben
2. Im Browser öffnen: `https://api.telegram.org/botDEIN_TOKEN/getUpdates`
3. In der Antwort: `"chat":{"id": XXXXXXX}` – diese Zahl ist deine Chat-ID

---

## Schritt 5 – GitHub Pages aktivieren

1. Im Repository → **Settings** → **Pages**
2. Source: **Deploy from a branch**
3. Branch: **main** / Ordner: **/dashboard**
4. **Save** klicken

Nach ~2 Minuten ist das Dashboard erreichbar unter:
`https://DEIN-USERNAME.github.io/etf-monitor`

---

## Schritt 6 – Ersten Lauf auslösen

Die Action läuft automatisch stündlich (Mo–Fr, 9–19 Uhr MEZ).
Zum sofortigen Test:

1. Im Repository → **Actions**
2. Links: **ETF Monitor** anklicken
3. **Run workflow** → **Run workflow**

Nach ~30 Sekunden erscheinen die ersten Daten im Dashboard.

---

## Wie es funktioniert

```
Stündlich (GitHub Actions)
  → etf_checker.py läuft
  → Kurse von Yahoo Finance holen
  → MA20 + RSI berechnen
  → KI-Einschätzung von Claude generieren
  → dashboard.json ins Repo schreiben
  → Bei grünem Signal: Telegram senden
  → Am 25.: Deadline-Erinnerung falls kein Signal kam

GitHub Pages
  → Serviert dashboard/index.html
  → Liest dashboard.json (stündlich aktuell)
  → Zeigt Ampel, Kurse, Indikatoren, KI-Einschätzung
```

---

## Kosten

| Dienst | Kosten |
|--------|--------|
| GitHub (privates Repo) | kostenlos |
| GitHub Actions (≤2.000 Min/Monat) | kostenlos · du brauchst ~60 Min/Monat |
| GitHub Pages | kostenlos |
| Anthropic API | ~$0.01–0.05 pro Monat (minimal) |
| Telegram Bot | kostenlos |

---

## Nützliche Links

- Dashboard: `https://DEIN-USERNAME.github.io/etf-monitor`
- Actions-Logs: `https://github.com/DEIN-USERNAME/etf-monitor/actions`
- Secrets: `https://github.com/DEIN-USERNAME/etf-monitor/settings/secrets/actions`
