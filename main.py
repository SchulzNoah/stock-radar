import os
import sys
import time
import random
import threading
import urllib.parse
from io import StringIO
from datetime import datetime
from typing import List, Optional, Dict, Any
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd
import requests
from dotenv import load_dotenv
from finvizfinance.quote import finvizfinance

# 1. Lokale .env-Datei laden
load_dotenv()

# --- KONFIGURATION ---
WORKING_DIR = "data"
os.makedirs(WORKING_DIR, exist_ok=True)
os.chdir(WORKING_DIR)

MAX_WORKERS = 3
PAUSE_MIN = 1.0
PAUSE_MAX = 2.5
SAVE_INTERVAL = 100

save_lock = threading.Lock()
counter_lock = threading.Lock()
counter = {"done": 0, "success": 0, "failed": 0}
rate_limit_event = threading.Event()


# --- DYNAMISCHE PROXY ROTATION & SESSION PATCH ---

def get_rotated_proxy() -> Dict[str, str]:
    """
    Erstellt für jeden Request eine Proxy-URL mit zufälligem Sub-User (1-10).
    Liest Zugangsdaten ausschließlich aus Umgebungsvariablen.
    """
    raw_user = os.environ.get("PROXY_USERNAME")
    password = os.environ.get("PROXY_PASSWORD")

    if not raw_user or not password:
        return {}

    base_user = raw_user.split("-")[0]
    slot = random.randint(1, 10)
    user_with_slot = f"{base_user}-{slot}"

    enc_user = urllib.parse.quote(user_with_slot)
    enc_pass = urllib.parse.quote(password)

    proxy_url = f"http://{enc_user}:{enc_pass}@p.webshare.io:80"
    return {
        "http": proxy_url,
        "https": proxy_url
    }


# Globaler Patch für requests: Greift in ALLEN Threads & finvizfinance-Aufrufen
if not getattr(requests.Session.request, "_is_patched", False):
    _original_request = requests.Session.request

    def _patched_request(self, method, url, **kwargs):
        headers = kwargs.get("headers") or {}
        headers.setdefault("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
        headers.setdefault("Accept", "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8")
        headers.setdefault("Accept-Language", "en-US,en;q=0.9")
        headers["Connection"] = "close"  # Verhindert 407 durch Socket-Reusing über Threads hinweg
        kwargs["headers"] = headers

        # Proxy nur bei Finviz-Aufrufen dynamisch anhängen
        if "finviz.com" in str(url):
            proxy = get_rotated_proxy()
            if proxy:
                kwargs["proxies"] = proxy

        return _original_request(self, method, url, **kwargs)

    _patched_request._is_patched = True
    requests.Session.request = _patched_request


# --- TICKER RETRIEVAL (DIREKTER DOWNLOAD OHNE PROXY) ---

def get_sp500_tickers() -> List[str]:
    url = "https://raw.githubusercontent.com/datasets/s-and-p-500-companies/main/data/constituents.csv"
    try:
        resp = requests.get(url, timeout=10, proxies={"http": None, "https": None})
        resp.raise_for_status()
        df = pd.read_csv(StringIO(resp.text))
        tickers = [t.replace(".", "-") for t in df["Symbol"].astype(str).tolist()]
        print(f"✔ {len(tickers)} S&P 500 Tickers geladen.")
        return tickers
    except Exception as e:
        print(f"⚠ Fehler S&P500: {e}")
        return []


def get_nasdaq_tickers() -> List[str]:
    url = "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt"
    try:
        resp = requests.get(url, timeout=10, proxies={"http": None, "https": None})
        resp.raise_for_status()
        df = pd.read_csv(StringIO(resp.text), sep="|", skipfooter=1, engine="python")
        tickers = []
        for t in df["Symbol"].tolist():
            if isinstance(t, float):
                continue
            t_str = str(t).strip()
            if t_str and t_str not in ["Symbol", "nan", ""]:
                tickers.append(t_str)
        print(f"✔ {len(tickers)} NASDAQ Tickers geladen.")
        return tickers
    except Exception as e:
        print(f"⚠ Fehler NASDAQ: {e}")
        return []


# --- FINVIZ SCRAPING PER TICKER ---

def fetch_single_ticker(ticker: str, today_str: str, retries: int = 3) -> Optional[pd.DataFrame]:
    ticker_clean = ticker.replace(".", "-")

    for attempt in range(retries):
        if rate_limit_event.is_set():
            time.sleep(random.uniform(8, 15))

        try:
            stock = finvizfinance(ticker_clean)
            data = stock.ticker_fundament()

            if not data:
                return None

            df_temp = pd.DataFrame([data])
            df_temp["Ticker"] = ticker
            df_temp["Fetch_Date"] = today_str

            time.sleep(random.uniform(PAUSE_MIN, PAUSE_MAX))
            return df_temp

        except Exception as e:
            err = str(e)

            if "429" in err or "Too Many" in err:
                rate_limit_event.set()
                wait = 60 + random.randint(20, 40)
                print(f"  ⏳ Rate-Limit: {ticker} → warte {wait}s...")
                time.sleep(wait)
                rate_limit_event.clear()

            elif "403" in err or "blocked" in err.lower():
                wait = 30 + random.randint(10, 20)
                print(f"  🚫 Geblockt: {ticker} → warte {wait}s...")
                time.sleep(wait)

            elif "404" in err:
                return None

            else:
                time.sleep(3 + random.randint(1, 4))

    return None


# --- PARALLELER ABRUF MIT WORKERS & CHECKPOINTS ---

def fetch_and_save_fundamentals(tickers: List[str], base_name: str):
    if not tickers:
        return

    today_str = datetime.now().strftime("%Y-%m-%d")
    filename = f"{today_str}_{base_name}.csv"

    already_done = set()
    if os.path.exists(filename):
        existing = pd.read_csv(filename)
        if "Ticker" in existing.columns:
            already_done = set(existing["Ticker"].tolist())
        print(f"📂 Checkpoint: {len(already_done)} Ticker bereits vorhanden.")

    remaining = [t for t in tickers if t not in already_done]
    total = len(remaining)

    if total == 0:
        print(f"✅ {base_name} bereits vollständig.")
        return

    est_min = (total * ((PAUSE_MIN + PAUSE_MAX) / 2)) / MAX_WORKERS / 60
    print(f"\n--- {base_name}: {total} Ticker | {MAX_WORKERS} Worker-Threads ---")
    print(f"⏱️  Geschätzte Laufzeit: ~{est_min:.0f} Minuten")

    start_time = time.time()
    buffer = []

    def process_ticker(ticker):
        return fetch_single_ticker(ticker, today_str)

    def flush_buffer(buf, fname):
        if not buf:
            return []
        with save_lock:
            df_save = pd.concat(buf, ignore_index=True)
            if os.path.exists(fname):
                df_save.to_csv(fname, mode="a", header=False, index=False)
            else:
                df_save.to_csv(fname, index=False)
        return []

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(process_ticker, t): t for t in remaining}

        for future in as_completed(futures):
            ticker = futures[future]
            try:
                result = future.result()
                with counter_lock:
                    counter["done"] += 1
                    done = counter["done"]

                    if result is not None:
                        result["Source_Index"] = base_name.upper()
                        counter["success"] += 1
                        buffer.append(result)
                    else:
                        counter["failed"] += 1

                    if done % 25 == 0 or done == total:
                        elapsed = time.time() - start_time
                        rate = done / elapsed * 60
                        eta_min = (total - done) / (rate + 0.01)
                        print(f"  📊 {done}/{total} ({done/total*100:.1f}%) | "
                              f"{rate:.0f} Ticker/min | ETA: ~{eta_min:.0f} min | "
                              f"✅ {counter['success']} | ❌ {counter['failed']}")

                    if len(buffer) >= SAVE_INTERVAL:
                        buffer = flush_buffer(buffer, filename)
                        print(f"  💾 Zwischengespeichert.")

            except Exception as e:
                print(f"  ❌ Fehler bei {ticker}: {e}")

    if buffer:
        flush_buffer(buffer, filename)

    elapsed = time.time() - start_time
    print(f"\n✨ {base_name} fertig in {elapsed/60:.1f} Minuten!")
    counter["done"] = counter["success"] = counter["failed"] = 0


# --- MAIN ---

if __name__ == "__main__":
    start = time.time()

    if os.environ.get("PROXY_USERNAME") and os.environ.get("PROXY_PASSWORD"):
        print("🔒 Proxy-Zugangsdaten erfolgreich aus der Umgebung geladen.")
    else:
        print("⚠️ WARNUNG: Keine PROXY_USERNAME / PROXY_PASSWORD Umgebungsvariablen gefunden!")

    sp500_list = get_sp500_tickers()
    nasdaq_list = get_nasdaq_tickers()

    fetch_and_save_fundamentals(sp500_list, "SP500_fundamentals")
    fetch_and_save_fundamentals(nasdaq_list, "NASDAQ_fundamentals")

    print(f"\n🚀 Gesamt fertig in {(time.time() - start) / 60:.1f} Minuten.")
