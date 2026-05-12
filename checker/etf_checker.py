#!/usr/bin/env python3
"""
ETF Kaufzeitpunkt-Monitor – GitHub Actions Version
Läuft stündlich, schreibt docs/dashboard.json ins Repo,
sendet Telegram bei grünem Signal, generiert KI-Einschätzung.
"""

import os
import json
import time
import logging
import requests
from datetime import datetime, timezone
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

# ── Konfiguration ─────────────────────────────────────────────────────────────
TELEGRAM_TOKEN    = os.environ.get("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID  = os.environ.get("TELEGRAM_CHAT_ID", "")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

MA_THRESHOLD_PCT = float(os.getenv("MA_THRESHOLD_PCT", "3.0"))
RSI_THRESHOLD    = float(os.getenv("RSI_THRESHOLD", "38"))
MA_PERIOD        = int(os.getenv("MA_PERIOD", "20"))
RSI_PERIOD       = int(os.getenv("RSI_PERIOD", "14"))

# Ausgabepfad (relativ zum Repo-Root)
OUTPUT_FILE = Path("docs/dashboard.json")
STATE_FILE  = Path("docs/state.json")

ALPHAVANTAGE_KEY = os.environ.get("ALPHAVANTAGE_KEY", "")

ETFS = [
    {"name": "MSCI World",            "ticker": "SPPW.DEX", "isin": "IE00BFY0GT14"},
    {"name": "MSCI Emerging Markets", "ticker": "IS3N.DEX",  "isin": "IE00B4L5YC18"},
]

AV_URL = "https://www.alphavantage.co/query?function=TIME_SERIES_DAILY&symbol={ticker}&outputsize=compact&apikey={key}"

# ── Datenabruf ────────────────────────────────────────────────────────────────
def fetch_data(ticker: str) -> dict:
    url = AV_URL.format(ticker=ticker, key=ALPHAVANTAGE_KEY)
    r   = requests.get(url, timeout=15)
    r.raise_for_status()
    data = r.json()

    if "Note" in data:
        raise Exception("Alpha Vantage Rate Limit erreicht – bitte später erneut versuchen.")
    if "Error Message" in data:
        raise Exception(f"Alpha Vantage Fehler: {data['Error Message']}")
    if "Time Series (Daily)" not in data:
        raise Exception(f"Unerwartete Antwort: {list(data.keys())}")

    series = data["Time Series (Daily)"]
    dates  = sorted(series.keys(), reverse=True)  # Neueste zuerst
    closes = [float(series[d]["4. close"]) for d in dates][:60]  # Letzte 60 Tage
    closes.reverse()  # Älteste zuerst für MA/RSI-Berechnung

    price      = closes[-1]
    prev_close = closes[-2] if len(closes) >= 2 else price

    return {
        "price":      price,
        "prev_close": prev_close,
        "currency":   "EUR",
        "closes":     closes,
    }

# ── Indikatoren ───────────────────────────────────────────────────────────────
def calc_ma(closes, period):
    if len(closes) < period:
        return None
    return sum(closes[-period:]) / period

def calc_rsi(closes, period):
    if len(closes) < period + 1:
        return None
    gains = losses = 0.0
    for i in range(-period, 0):
        diff = closes[i] - closes[i - 1]
        if diff > 0: gains  += diff
        else:        losses -= diff
    avg_gain = gains  / period
    avg_loss = losses / period
    if avg_loss == 0:
        return 100.0
    return round(100 - 100 / (1 + avg_gain / avg_loss), 1)

# ── Signalbewertung ───────────────────────────────────────────────────────────
def evaluate(data: dict) -> dict:
    price  = data["price"]
    closes = data["closes"]
    ma20   = calc_ma(closes, MA_PERIOD)
    rsi    = calc_rsi(closes, RSI_PERIOD)
    score  = 0
    reasons = []
    diff_pct = None

    if ma20:
        diff_pct = (price - ma20) / ma20 * 100
        if diff_pct < -MA_THRESHOLD_PCT:
            score += 2; reasons.append(f"Kurs {abs(diff_pct):.1f}% unter MA{MA_PERIOD} ✓")
        elif diff_pct < -MA_THRESHOLD_PCT / 2:
            score += 1; reasons.append(f"Kurs {abs(diff_pct):.1f}% unter MA{MA_PERIOD} (leicht)")
        elif diff_pct > MA_THRESHOLD_PCT:
            score -= 2; reasons.append(f"Kurs {diff_pct:.1f}% über MA{MA_PERIOD}")
        else:
            reasons.append(f"Kurs nahe MA{MA_PERIOD} ({diff_pct:+.1f}%)")

    if rsi is not None:
        if rsi < RSI_THRESHOLD:
            score += 2; reasons.append(f"RSI {rsi} – überverkauft ✓")
        elif rsi < RSI_THRESHOLD + 10:
            score += 1; reasons.append(f"RSI {rsi} – leicht schwach")
        elif rsi > 65:
            score -= 1; reasons.append(f"RSI {rsi} – überkauft")
        else:
            reasons.append(f"RSI {rsi} – neutral")

    if score >= 3:   signal, label = "green",   "Günstig kaufen"
    elif score >= 1: signal, label = "yellow",  "Leicht günstig"
    elif score < 0:  signal, label = "red",     "Eher teuer"
    else:            signal, label = "neutral", "Neutral"

    change_pct = (price - data["prev_close"]) / data["prev_close"] * 100 if data["prev_close"] else 0

    return {
        "price":      round(price, 2),
        "currency":   data["currency"],
        "change_pct": round(change_pct, 2),
        "ma20":       round(ma20, 2) if ma20 else None,
        "diff_pct":   round(diff_pct, 2) if diff_pct is not None else None,
        "rsi":        rsi,
        "score":      score,
        "signal":     signal,
        "label":      label,
        "reasons":    reasons,
        "closes":     closes[-30:],  # Letzten 30 Tage fürs Dashboard
    }

# ── KI-Einschätzung ───────────────────────────────────────────────────────────
def generate_ai_assessment(results: list[dict]) -> str:
    if not ANTHROPIC_API_KEY:
        return ""

    today = datetime.now().strftime("%d. %B %Y")
    etf_lines = []
    for r in results:
        etf = r["etf"]
        ev  = r["evaluation"]
        etf_lines.append(
            f"- {etf['name']} ({etf['ticker']}):\n"
            f"  Kurs: {ev['price']} {ev['currency']} ({'+' if ev['change_pct'] >= 0 else ''}{ev['change_pct']}% heute)\n"
            f"  MA20: {ev['ma20']} EUR (Abstand: {ev['diff_pct']}%)\n"
            f"  RSI(14): {ev['rsi']}\n"
            f"  Signal: {ev['label']}"
        )

    prompt = (
        f"Du bist ein nüchterner ETF-Anlageassistent. Der Nutzer investiert monatlich "
        f"100–200 € in zwei ETFs (langfristiger Vermögensaufbau), zahlt 2,50 € Gebühr "
        f"pro Kauf und kauft genau einmal pro Monat. Heute ist der {today}.\n\n"
        f"Aktuelle Kursdaten:\n" + "\n".join(etf_lines) + "\n\n"
        f"Gib eine knappe, direkte Einschätzung ob heute ein guter Kaufzeitpunkt ist.\n"
        f"Format: 4–5 Stichpunkte als Liste, dann ein Fazit-Satz. Kein Fließtext, "
        f"keine Haftungshinweise. Direkt und ehrlich."
    )

    try:
        r = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key":         ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "Content-Type":      "application/json",
            },
            json={
                "model":      "claude-sonnet-4-6",
                "max_tokens": 400,
                "messages":   [{"role": "user", "content": prompt}],
            },
            timeout=30,
        )
        r.raise_for_status()
        text = r.json()["content"][0]["text"]
        log.info("KI-Einschätzung generiert.")
        return text
    except Exception as e:
        log.error(f"KI-Einschätzung fehlgeschlagen: {e}")
        return ""

# ── Deadline-Check (25. des Monats) ──────────────────────────────────────────
def check_deadline(state: dict) -> bool:
    """Sendet am 25. eine Erinnerung wenn in diesem Monat noch kein grünes Signal kam."""
    now = datetime.now(timezone.utc)
    if now.day != 25:
        return False

    month_key = now.strftime("%Y-%m")
    if state.get("deadline_sent") == month_key:
        return False  # Bereits diese Monat gesendet

    # War diesen Monat schon ein grünes Signal?
    green_this_month = state.get("last_green_month") == month_key
    if green_this_month:
        return False  # Grünes Signal war schon da, keine Erinnerung nötig

    return True

# ── Telegram ──────────────────────────────────────────────────────────────────
def send_telegram(message: str):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        log.warning("Telegram nicht konfiguriert.")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    r   = requests.post(url, json={
        "chat_id":    TELEGRAM_CHAT_ID,
        "text":       message,
        "parse_mode": "HTML",
    }, timeout=10)
    r.raise_for_status()
    log.info("Telegram gesendet.")

def build_signal_message(results: list[dict], ai_text: str) -> str:
    now = datetime.now().strftime("%d.%m.%Y %H:%M")
    lines = [f"<b>📊 ETF-Monitor – {now}</b>\n"]
    for r in results:
        etf = r["etf"]
        ev  = r["evaluation"]
        chg = f"+{ev['change_pct']}%" if ev["change_pct"] >= 0 else f"{ev['change_pct']}%"
        lines.append(f"<b>{etf['name']}</b> ({etf['ticker']})")
        lines.append(f"Kurs: <b>{ev['price']} {ev['currency']}</b>  ({chg})")
        lines.append(f"MA{MA_PERIOD}: {ev['ma20']}  |  RSI: {ev['rsi']}")
        lines.append(f"Signal: <b>{ev['label']}</b>")
        lines.append("  • " + "\n  • ".join(ev["reasons"]))
        lines.append("")
    lines.append("💡 <i>Jetzt könnte ein guter Zeitpunkt zum Kauf sein!</i>")
    if ai_text:
        lines.append(f"\n🤖 <i>{ai_text[:300]}…</i>" if len(ai_text) > 300 else f"\n🤖 <i>{ai_text}</i>")
    return "\n".join(lines)

# ── State ─────────────────────────────────────────────────────────────────────
def load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except Exception:
            pass
    return {}

def save_state(state: dict):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2))

# ── Hauptfunktion ─────────────────────────────────────────────────────────────
def run():
    log.info("ETF-Check gestartet.")
    state   = load_state()
    results = []
    any_green = False
    notify    = False
    now_month = datetime.now(timezone.utc).strftime("%Y-%m")

    for etf in ETFS:
        try:
            data = fetch_data(etf["ticker"])
            ev   = evaluate(data)
            results.append({"etf": etf, "evaluation": ev})
            log.info(f"{etf['ticker']}: {ev['price']} {ev['currency']} | {ev['signal']} | RSI {ev['rsi']} | MA-Δ {ev['diff_pct']}%")

            prev_signal = state.get(etf["ticker"], {}).get("signal")
            if ev["signal"] == "green" and prev_signal != "green":
                notify = True
            if ev["signal"] == "green":
                any_green = True

            state[etf["ticker"]] = {
                "signal":  ev["signal"],
                "price":   ev["price"],
                "updated": datetime.now(timezone.utc).isoformat(),
            }
        except Exception as e:
            log.error(f"Fehler bei {etf['ticker']}: {e}")

        # Pause zwischen Anfragen – Alpha Vantage erlaubt max. 5/Minute
        time.sleep(15)

    # KI-Einschätzung generieren
    ai_text = generate_ai_assessment(results) if results else ""

    # Dashboard JSON schreiben
    dashboard_data = {
        "updated": datetime.now(timezone.utc).isoformat(),
        "etfs": [
            {
                "name":    r["etf"]["name"],
                "ticker":  r["etf"]["ticker"],
                "isin":    r["etf"]["isin"],
                **{k: v for k, v in r["evaluation"].items() if k != "closes"},
                "closes":  r["evaluation"]["closes"],
            }
            for r in results
        ],
        "ai_assessment": ai_text,
        "config": {
            "ma_threshold_pct": MA_THRESHOLD_PCT,
            "rsi_threshold":    RSI_THRESHOLD,
            "ma_period":        MA_PERIOD,
        }
    }
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.write_text(json.dumps(dashboard_data, indent=2, ensure_ascii=False))
    log.info(f"dashboard.json geschrieben → {OUTPUT_FILE}")

    # Telegram: Kaufsignal
    if notify and results:
        try:
            send_telegram(build_signal_message(results, ai_text))
        except Exception as e:
            log.error(f"Telegram-Fehler: {e}")

    # Telegram: Deadline-Erinnerung am 25.
    if check_deadline(state):
        try:
            deadline_msg = (
                "⏰ <b>Kaufdeadline – 25. des Monats</b>\n\n"
                "Diesen Monat kam kein grünes Kaufsignal.\n"
                "Laut deiner Strategie: <b>Jetzt trotzdem kaufen!</b>\n\n"
                "Nicht kaufen kostet im Schnitt mehr als ein suboptimaler Zeitpunkt."
            )
            send_telegram(deadline_msg)
            state["deadline_sent"] = now_month
            log.info("Deadline-Erinnerung gesendet.")
        except Exception as e:
            log.error(f"Deadline-Telegram-Fehler: {e}")

    if any_green:
        state["last_green_month"] = now_month

    save_state(state)
    log.info("ETF-Check abgeschlossen.")

if __name__ == "__main__":
    run()
