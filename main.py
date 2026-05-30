import pandas as pd
from finvizfinance.quote import finvizfinance
import requests
import os
import time
import random
from datetime import datetime
from typing import List, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

# --- KONFIGURATION ---
WORKING_DIR   = "data"
os.makedirs(WORKING_DIR, exist_ok=True)
os.chdir(WORKING_DIR)

MAX_WORKERS   = 3
PAUSE_MIN     = 1.0
PAUSE_MAX     = 2.5
SAVE_INTERVAL = 100

save_lock    = threading.Lock()
counter_lock = threading.Lock()
counter      = {"done": 0, "success": 0, "failed": 0}

# --- PROXY SETUP ---

def get_proxy() -> dict:
    username = os.environ.get("PROXY_USERNAME", "")
    password = os.environ.get("PROXY_PASSWORD", "")

    if not username or not password:
        print("⚠️ Keine Proxy-Credentials gefunden → ohne Proxy")
        return {}

    proxy_url = f"http://{username}:{password}@p.webshare.io:80"
    print(f"🔀 Proxy aktiv: p.webshare.io:80")
    return {
        "http":  proxy_url,
        "https": proxy_url,
    }

PROXY = get_proxy()

# --- TICKER RETRIEVAL ---

def get_sp500_tickers() -> List[str]:
    url = "https://raw.githubusercontent.com/datasets/s-and-p-500-companies/main/data/constituents.csv"
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        resp    = requests.get(url, headers=headers, timeout=10)
        resp.raise_for_status()
        from io import StringIO
        df      = pd.read_csv(StringIO(resp.text))
        tickers = [t.replace(".", "-") for t in df["Symbol"].astype(str).tolist()]
        print(f"✔ {len(tickers)} S&P 500 Tickers geladen.")
        return tickers
    except Exception as e:
        print(f"⚠ Fehler S&P500: {e}")
        return []

def get_nasdaq_tickers() -> List[str]:
    url = "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt"
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        resp    = requests.get(url, headers=headers, timeout=10)
        resp.raise_for_status()
        from io import StringIO
        df      = pd.read_csv(StringIO(resp.text), sep='|', skipfooter=1, engine='python')
        tickers = []
        for t in df['Symbol'].astype(str).tolist():
            # Float-Werte (NaN) und leere Strings überspringen
            if t and t not in ['Symbol', 'nan', '']:
                tickers.append(t.strip())
        print(f"✔ {len(tickers)} NASDAQ Tickers geladen.")
        return tickers
    except Exception as e:
        print(f"⚠ Fehler NASDAQ: {e}")
        return []

# --- FINVIZ MIT PROXY ---

rate_limit_event = threading.Event()

def patch_finviz_session():
    """
    Überschreibt die interne requests-Session von finvizfinance
    mit unserer Proxy-Session.
    """
    session = requests.Session()
    session.headers.update({
        "User-Agent":      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept":          "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    })
    if PROXY:
        session.proxies.update(PROXY)
    return session

SESSION = patch_finviz_session()


def fetch_single_ticker(ticker: str, today_str: str, retries: int = 3) -> Optional[pd.DataFrame]:
    ticker_clean = ticker.replace(".", "-")

    for attempt in range(retries):
        if rate_limit_event.is_set():
            time.sleep(random.uniform(8, 15))

        try:
            # Session mit Proxy direkt in finvizfinance injizieren
            import finvizfinance.quote as fq
            fq.scraper = SESSION

            stock = finvizfinance(ticker_clean)
            data  = stock.ticker_fundament()

            if not data:
                return None

            df_temp               = pd.DataFrame([data])
            df_temp["Ticker"]     = ticker
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


# --- PARALLELER ABRUF ---

def fetch_and_save_fundamentals(tickers: List[str], base_name: str):
    if not tickers:
        return

    today_str = datetime.now().strftime("%Y-%m-%d")
    filename  = f"{today_str}_{base_name}.csv"

    already_done = set()
    if os.path.exists(filename):
        existing     = pd.read_csv(filename)
        already_done = set(existing["Ticker"].tolist())
        print(f"📂 Checkpoint: {len(already_done)} Tickers bereits vorhanden.")

    remaining = [t for t in tickers if t not in already_done]
    total     = len(remaining)

    if total == 0:
        print(f"✅ {base_name} bereits vollständig.")
        return

    est_min = (total * ((PAUSE_MIN + PAUSE_MAX) / 2)) / MAX_WORKERS / 60
    print(f"\n--- {base_name}: {total} Tickers | {MAX_WORKERS} Threads ---")
    print(f"⏱️  Geschätzte Laufzeit: ~{est_min:.0f} Minuten")

    start_time = time.time()
    buffer     = []

    def process_ticker(ticker):
        return fetch_single_ticker(ticker, today_str)

    def flush_buffer(buf, filename):
        if not buf:
            return []
        with save_lock:
            df_save = pd.concat(buf, ignore_index=True)
            if os.path.exists(filename):
                df_save.to_csv(filename, mode='a', header=False, index=False)
            else:
                df_save.to_csv(filename, index=False)
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
                        rate    = done / elapsed * 60
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
    sp500_list  = get_sp500_tickers()
    nasdaq_list = get_nasdaq_tickers()
    fetch_and_save_fundamentals(sp500_list,  "SP500_fundamentals")
    fetch_and_save_fundamentals(nasdaq_list, "NASDAQ_fundamentals")
    print(f"\n🚀 Gesamt fertig in {(time.time()-start)/60:.1f} Minuten.")
