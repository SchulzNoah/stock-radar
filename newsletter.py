import pandas as pd
import numpy as np
import smtplib
import os
import re
import glob
import json
from email.mime.multipart import MIMEMultipart
from email.mime.text      import MIMEText
from datetime             import datetime

# ============================================================
# KONFIGURATION
# ============================================================

MAIL_SENDER   = os.environ.get("MAIL_SENDER",   "")
MAIL_PASSWORD = os.environ.get("MAIL_PASSWORD", "")
MAIL_RECEIVER = os.environ.get("MAIL_RECEIVER", "")

today         = datetime.now()
today_str     = today.strftime("%Y-%m-%d")
DATA_DIR      = "data"

MONATE_DE = {
    1:"Januar",2:"Februar",3:"März",4:"April",5:"Mai",6:"Juni",
    7:"Juli",8:"August",9:"September",10:"Oktober",11:"November",12:"Dezember"
}
datum_de = f"{today.day}. {MONATE_DE[today.month]} {today.year}"

WATCHLIST_TICKERS = [
    "AAPL","MSFT","NVDA","GOOGL","AMZN","META","TSLA",  # Magnificent Seven
    "AMD","ASML","VRT","AVGO","TSM","MELI","WDC",
    "SAP","MRVL","MU","AAON","BE"
]

# ============================================================
# HILFSFUNKTIONEN
# ============================================================

def pct_zu_num(series):
    return pd.to_numeric(
        series.astype(str).str.extract(r'(-?[0-9]+\.?[0-9]*)')[0],
        errors='coerce'
    )

def zahl_bereinigen(series):
    s = series.astype(str).str.strip()
    s = s.replace(['-','NA','N/A','','nan'], np.nan)
    return pd.to_numeric(
        s.str.extract(r'(-?[0-9]+\.?[0-9]*)')[0],
        errors='coerce'
    )

def mrd_bereinigen(series):
    s       = series.astype(str).str.strip()
    wert    = pd.to_numeric(s.str.extract(r'(-?[0-9]+\.?[0-9]*)')[0], errors='coerce')
    einheit = s.str.extract(r'([TBMKtbmk])$')[0]
    result  = wert.copy()
    result[einheit.isin(['T','t'])] = wert[einheit.isin(['T','t'])] * 1000
    result[einheit.isin(['B','b'])] = wert[einheit.isin(['B','b'])]
    result[einheit.isin(['M','m'])] = wert[einheit.isin(['M','m'])] / 1000
    result[einheit.isin(['K','k'])] = wert[einheit.isin(['K','k'])] / 1_000_000
    return result

def kurs_bereinigen(series):
    return pd.to_numeric(
        series.astype(str).str.extract(r'^(-?[0-9]+\.?[0-9]*)')[0],
        errors='coerce'
    )

def eps_past_split(series, pos=0):
    def extract(x):
        zahlen = re.findall(r'-?[0-9]+\.?[0-9]*', str(x))
        return float(zahlen[pos]) if len(zahlen) > pos else np.nan
    return series.apply(extract)

def fmt_de(val, decimals=2, suffix=""):
    """Deutsche Zahlenformatierung: 1234.56 → '1.234,56'"""
    try:
        if pd.isna(val):
            return "–"
        num = float(val)
        formatted = f"{num:,.{decimals}f}"
        # Tausenderpunkt und Dezimalkomma tauschen
        formatted = formatted.replace(",", "X").replace(".", ",").replace("X", ".")
        return f"{formatted}{suffix}"
    except:
        return "–"

def fmt_pct(val, decimals=1):
    return fmt_de(val, decimals, "%")

def fmt_mrd(val, decimals=1):
    return fmt_de(val, decimals, " Mrd.")

# ============================================================
# DATEN LADEN & AUFBEREITEN
# ============================================================

def lade_und_bereite_auf():
    # Neueste verfügbare Dateien nehmen (unabhängig vom Datum)
    sp_dateien = sorted(glob.glob(f"{DATA_DIR}/*_SP500_fundamentals.csv"))
    ns_dateien = sorted(glob.glob(f"{DATA_DIR}/*_NASDAQ_fundamentals.csv"))

    if not sp_dateien or not ns_dateien:
        raise FileNotFoundError(f"Keine CSVs in '{DATA_DIR}/' gefunden!")

    sp_file = sp_dateien[-1]   # Neueste SP500-Datei
    ns_file = ns_dateien[-1]   # Neueste NASDAQ-Datei

    print(f"📂 Lade SP500:  {sp_file}")
    print(f"📂 Lade NASDAQ: {ns_file}")

    sp = pd.read_csv(sp_file, dtype=str, low_memory=False)
    ns = pd.read_csv(ns_file, dtype=str, low_memory=False)

    print(f"   SP500:  {len(sp)} Zeilen")
    print(f"   NASDAQ: {len(ns)} Zeilen")

    if len(sp) < 10 or len(ns) < 10:
        raise ValueError("CSVs scheinen leer – Pipeline-Fehler?")

    sp_only = sp[~sp['Ticker'].isin(ns['Ticker'])]
    df      = pd.concat([ns, sp_only], ignore_index=True)
    print(f"✅ Master: {len(df)} Unternehmen")

    df = df.rename(columns={
        'Company':               'Unternehmen',
        'Sector':                'Sektor',
        'Industry':              'Branche',
        'Market Cap':            'Marktkapitalisierung_Mrd',
        'P/E':                   'KGV',
        'Forward P/E':           'KGV_Forward',
        'EPS (ttm)':             'EPS_TTM',
        'EPS this Y':            'EPS_dieses_Jahr_Pct',
        'EPS next Y Percentage': 'EPS_naechstes_Jahr_Pct',
        'EPS next 5Y':           'EPS_naechste_5J_Pct',
        'EPS past 3/5Y':         'EPS_vergangene_3_5J',
        'PEG':                   'PEG',
        'Income':                'Gewinn_Mrd',
        'Sales':                 'Umsatz_Mrd',
        'Profit Margin':         'Gewinnmarge_Pct',
        'Gross Margin':          'Bruttomarge_Pct',
        'Oper. Margin':          'Operative_Marge_Pct',
        'ROE':                   'ROE_Pct',
        'ROA':                   'ROA_Pct',
        'Perf Week':             'Perf_Woche_Pct',
        'Perf Month':            'Perf_Monat_Pct',
        'Perf Quarter':          'Perf_Quartal_Pct',
        'Perf Half Y':           'Perf_Halbjahr_Pct',
        'Perf Year':             'Perf_Jahr_Pct',
        'Perf YTD':              'Perf_YTD_Pct',
        'Perf 3Y':               'Perf_3J_Pct',
        'Perf 5Y':               'Perf_5J_Pct',
        'Perf 10Y':              'Perf_10J_Pct',
        '52W High':              'Hoch_52W',
        '52W Low':               'Tief_52W',
        'RSI (14)':              'RSI',
        'Recom':                 'Analyst_Empfehlung',
        'Target Price':          'Kursziel',
        'Short Float':           'Short_Float_Pct',
        'Price':                 'Preis',
        'Beta':                  'Beta',
        'Debt/Eq':               'Verschuldungsgrad',
    })

    df['Marktkapitalisierung_Mrd'] = mrd_bereinigen(df['Marktkapitalisierung_Mrd'])
    df['Gewinn_Mrd']               = mrd_bereinigen(df['Gewinn_Mrd'])
    df['Umsatz_Mrd']               = mrd_bereinigen(df['Umsatz_Mrd'])
    df['KGV']                      = zahl_bereinigen(df['KGV'])
    df['KGV_Forward']              = zahl_bereinigen(df['KGV_Forward'])
    df['PEG']                      = zahl_bereinigen(df['PEG'])
    df['EPS_TTM']                  = zahl_bereinigen(df['EPS_TTM'])
    df['RSI']                      = zahl_bereinigen(df['RSI'])
    df['Beta']                     = zahl_bereinigen(df['Beta'])
    df['Analyst_Empfehlung']       = zahl_bereinigen(df['Analyst_Empfehlung'])
    df['Kursziel']                 = zahl_bereinigen(df['Kursziel'])
    df['Preis']                    = zahl_bereinigen(df['Preis'])
    df['Verschuldungsgrad']        = zahl_bereinigen(df['Verschuldungsgrad'])
    df['Hoch_52W']                 = kurs_bereinigen(df['Hoch_52W'])
    df['Tief_52W']                 = kurs_bereinigen(df['Tief_52W'])

    pct_cols = [
        'EPS_dieses_Jahr_Pct','EPS_naechstes_Jahr_Pct','EPS_naechste_5J_Pct',
        'Gewinnmarge_Pct','Bruttomarge_Pct','Operative_Marge_Pct',
        'ROE_Pct','ROA_Pct','Short_Float_Pct',
        'Perf_Woche_Pct','Perf_Monat_Pct','Perf_Quartal_Pct','Perf_Halbjahr_Pct',
        'Perf_Jahr_Pct','Perf_YTD_Pct','Perf_3J_Pct','Perf_5J_Pct','Perf_10J_Pct',
    ]
    for col in pct_cols:
        if col in df.columns:
            df[col] = pct_zu_num(df[col])

    df['EPS_vergangene_3J_Pct'] = eps_past_split(df['EPS_vergangene_3_5J'], pos=0)
    df['EPS_vergangene_5J_Pct'] = eps_past_split(df['EPS_vergangene_3_5J'], pos=1)

    df['Analyst_Upside_Pct'] = (
        (df['Kursziel'] - df['Preis']) / df['Preis'] * 100
    ).round(2)

    df = df[
        df['Preis'].notna() &
        (df['Preis'] > 0) &
        df['Unternehmen'].notna()
    ].copy()

    return df

# ============================================================
# COMPOSITE SCORE BERECHNEN
# ============================================================

def berechne_score(df):
    """
    Composite Score 0-100 auf Basis von 6 Kategorien:
    1. KGV-Bewertung      (niedrig = besser)
    2. Forward KGV        (niedrig = besser)
    3. EPS Wachstum 5J    (hoch = besser)
    4. Gewinnmarge        (hoch = besser)
    5. PEG                (niedrig = besser, <1 ideal)
    6. Analystenrating    (niedrig = besser, 1=Strong Buy)
    """
    df = df.copy()
    score_df = df[[
        'Ticker','Unternehmen','Sektor',
        'KGV','KGV_Forward','EPS_naechste_5J_Pct',
        'Gewinnmarge_Pct','PEG','Analyst_Empfehlung',
        'Marktkapitalisierung_Mrd'
    ]].copy()

    score_df = score_df[
        score_df['KGV'].notna() &
        score_df['KGV_Forward'].notna() &
        score_df['EPS_naechste_5J_Pct'].notna() &
        score_df['Gewinnmarge_Pct'].notna() &
        (score_df['KGV'] > 0) &
        (score_df['KGV_Forward'] > 0) &
        (score_df['Marktkapitalisierung_Mrd'] > 0.5)
    ].copy()

    def norm(series, invert=False):
        mn, mx = series.min(), series.max()
        if mx == mn:
            return pd.Series(50, index=series.index)
        r = (series - mn) / (mx - mn) * 100
        return 100 - r if invert else r

    # KGV: cap bei 100 (Ausreisser begrenzen)
    score_df['KGV_cap']     = score_df['KGV'].clip(0, 100)
    score_df['FKGV_cap']    = score_df['KGV_Forward'].clip(0, 80)
    score_df['PEG_cap']     = score_df['PEG'].clip(0, 5).fillna(3)
    score_df['Recom_fill']  = score_df['Analyst_Empfehlung'].fillna(3)

    score_df['S_KGV']       = norm(score_df['KGV_cap'],    invert=True)
    score_df['S_FKGV']      = norm(score_df['FKGV_cap'],   invert=True)
    score_df['S_Wachstum']  = norm(score_df['EPS_naechste_5J_Pct'])
    score_df['S_Marge']     = norm(score_df['Gewinnmarge_Pct'])
    score_df['S_PEG']       = norm(score_df['PEG_cap'],    invert=True)
    score_df['S_Analyst']   = norm(score_df['Recom_fill'], invert=True)

    score_df['Score'] = (
        score_df['S_KGV']      * 0.15 +
        score_df['S_FKGV']     * 0.20 +
        score_df['S_Wachstum'] * 0.25 +
        score_df['S_Marge']    * 0.20 +
        score_df['S_PEG']      * 0.10 +
        score_df['S_Analyst']  * 0.10
    ).round(1)

    score_df = score_df.sort_values('Score', ascending=False).reset_index(drop=True)
    score_df['Rang'] = score_df.index + 1

    return score_df[[
        'Rang','Ticker','Unternehmen','Sektor','Score',
        'S_KGV','S_FKGV','S_Wachstum','S_Marge','S_PEG','S_Analyst',
        'KGV','KGV_Forward','EPS_naechste_5J_Pct','Gewinnmarge_Pct','PEG','Analyst_Empfehlung'
    ]]

# ============================================================
# HTML-NEWSLETTER ERSTELLEN
# ============================================================

def erstelle_newsletter(df):
    # --- Marktübersicht ---
    positiv_pct  = (df['Perf_Monat_Pct'] > 0).mean() * 100
    avg_perf     = df['Perf_Monat_Pct'].mean()
    n_oversold   = int((df['RSI'] < 30).sum())
    n_overbought = int((df['RSI'] > 70).sum())
    n_gesamt     = len(df)

    # --- Sektorperformance ---
    sektor_df = (
        df[df['Sektor'].notna() & (df['Sektor'] != 'nan')]
        .groupby('Sektor')
        .agg(
            Anzahl             = ('Ticker',         'count'),
            Perf_Monat_Avg     = ('Perf_Monat_Pct', 'mean'),
            Perf_Jahr_Avg      = ('Perf_Jahr_Pct',  'mean'),
            KGV_Forward_Median = ('KGV_Forward',    'median'),
        )
        .round(2)
        .sort_values('Perf_Monat_Avg', ascending=False)
        .reset_index()
    )

    # --- Watchlist ---
    watchlist_df = df[df['Ticker'].isin(WATCHLIST_TICKERS)].copy()
    watchlist_cols = [
        'Ticker','Unternehmen','Sektor',
        'Marktkapitalisierung_Mrd','Gewinn_Mrd','KGV','KGV_Forward',
        'EPS_naechste_5J_Pct','PEG','Analyst_Empfehlung','Gewinnmarge_Pct'
    ]
    watchlist_df = watchlist_df[watchlist_cols].sort_values(
        'Marktkapitalisierung_Mrd', ascending=False
    )

    # --- Quality Screen ---
    quality_df = (
        df[
            df['Gewinnmarge_Pct'].notna() &
            df['EPS_naechste_5J_Pct'].notna() &
            df['KGV_Forward'].notna() &
            (df['Gewinnmarge_Pct']     > 10) &
            (df['EPS_naechste_5J_Pct'] > 10) &
            (df['KGV_Forward']          > 0)  &
            (df['KGV_Forward']          < 40) &
            (df['ROE_Pct'].fillna(0)   > 15)
        ]
        .assign(Score=lambda x:
            x['Gewinnmarge_Pct'].rank(pct=True)     * 0.25 +
            x['EPS_naechste_5J_Pct'].rank(pct=True) * 0.30 +
            x['ROE_Pct'].rank(pct=True)              * 0.25 +
            (-x['KGV_Forward']).rank(pct=True)       * 0.20
        )
        .nlargest(100, 'Score')
        [[
            'Ticker','Unternehmen','Sektor','Marktkapitalisierung_Mrd',
            'KGV_Forward','EPS_naechste_5J_Pct','Gewinnmarge_Pct',
            'PEG','Analyst_Empfehlung','Analyst_Upside_Pct'
        ]]
    )

    # --- Score-Daten für Radarplot ---
    score_df = berechne_score(df)

    # --- Chart-Daten für Plots ---
    plot_df = df[
        df['KGV'].notna() &
        df['KGV_Forward'].notna() &
        df['EPS_naechste_5J_Pct'].notna() &
        df['Sektor'].notna() &
        (df['KGV'] > 0) & (df['KGV'] < 150) &
        (df['KGV_Forward'] > 0) & (df['KGV_Forward'] < 100)
    ][['Ticker','Unternehmen','Sektor','KGV','KGV_Forward','EPS_naechste_5J_Pct','Gewinnmarge_Pct']].copy()

    # JSON für JavaScript
    watchlist_json  = watchlist_df.fillna('').to_json(orient='records')
    quality_json    = quality_df.fillna('').to_json(orient='records')
    score_json      = score_df.fillna('').to_json(orient='records')
    plot_json       = plot_df.fillna('').to_json(orient='records')
    sektor_json     = sektor_df.fillna('').to_json(orient='records')

    # Sektoren-Liste für Filter
    sektoren_liste  = sorted(df['Sektor'].dropna().unique().tolist())
    sektoren_json   = json.dumps(sektoren_liste)

    html = f"""<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Noahs Finanzblog 📈 – {datum_de}</title>
<style>
  @import url('https://fonts.googleapis.com/css2?family=DM+Serif+Display&family=DM+Sans:wght@300;400;500;600&display=swap');

  * {{ box-sizing: border-box; margin: 0; padding: 0; }}

  body {{
    font-family: 'DM Sans', sans-serif;
    background: #080C14;
    color: #E8EDF5;
    padding: 16px;
    max-width: 900px;
    margin: 0 auto;
  }}

  /* HEADER */
  .header {{
    background: linear-gradient(135deg, #0D1B2E 0%, #112240 50%, #0A192F 100%);
    border: 1px solid #1E3A5F;
    border-radius: 16px;
    padding: 32px 28px;
    margin-bottom: 20px;
    position: relative;
    overflow: hidden;
  }}
  .header::before {{
    content: '';
    position: absolute;
    top: -40px; right: -40px;
    width: 200px; height: 200px;
    background: radial-gradient(circle, rgba(100,200,255,0.08) 0%, transparent 70%);
    border-radius: 50%;
  }}
  .header h1 {{
    font-family: 'DM Serif Display', serif;
    font-size: clamp(22px, 4vw, 32px);
    color: #E8F4FD;
    letter-spacing: -0.5px;
  }}
  .header h1 span {{ color: #4DB8FF; }}
  .header .datum {{
    color: #7B9BB5;
    font-size: 13px;
    margin-top: 6px;
    font-weight: 300;
  }}

  /* SECTIONS */
  .section {{
    background: #0D1520;
    border: 1px solid #1A2E45;
    border-radius: 12px;
    padding: 20px;
    margin-bottom: 16px;
  }}
  .section-title {{
    font-family: 'DM Serif Display', serif;
    font-size: 18px;
    color: #4DB8FF;
    margin-bottom: 16px;
    padding-bottom: 10px;
    border-bottom: 1px solid #1A2E45;
  }}

  /* METRIKEN */
  .metric-grid {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(130px, 1fr));
    gap: 10px;
    margin-bottom: 4px;
  }}
  .metric-card {{
    background: #111D2E;
    border: 1px solid #1E3A5F;
    border-radius: 10px;
    padding: 14px 12px;
    text-align: center;
  }}
  .metric-val {{
    font-size: clamp(18px, 3vw, 24px);
    font-weight: 600;
    color: #4DB8FF;
    line-height: 1.2;
  }}
  .metric-lbl {{
    font-size: 11px;
    color: #5A7A95;
    margin-top: 4px;
    font-weight: 300;
  }}
  .pos {{ color: #2DD4A0 !important; }}
  .neg {{ color: #FF5C72 !important; }}

  /* TABELLEN */
  .tbl-wrap {{ overflow-x: auto; -webkit-overflow-scrolling: touch; }}
  table.dt {{
    width: 100%;
    border-collapse: collapse;
    font-size: 12px;
    min-width: 500px;
  }}
  table.dt th {{
    background: #0A1628;
    color: #4DB8FF;
    padding: 10px 8px;
    text-align: left;
    border-bottom: 2px solid #1E3A5F;
    white-space: nowrap;
    cursor: pointer;
    user-select: none;
    font-weight: 600;
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
  }}
  table.dt th:hover {{ background: #112240; }}
  table.dt th .sort-icon {{ color: #2A4A6A; margin-left: 4px; }}
  table.dt th.asc .sort-icon::after  {{ content: ' ▲'; color: #4DB8FF; }}
  table.dt th.desc .sort-icon::after {{ content: ' ▼'; color: #4DB8FF; }}
  table.dt th:not(.asc):not(.desc) .sort-icon::after {{ content: ' ⇅'; }}
  table.dt td {{
    padding: 9px 8px;
    border-bottom: 1px solid #141E2E;
    color: #C8D8E8;
    white-space: nowrap;
    font-size: 12px;
  }}
  table.dt tr:hover td {{ background: #0F1E32; }}
  table.dt tr:last-child td {{ border-bottom: none; }}
  .td-pos {{ color: #2DD4A0; font-weight: 500; }}
  .td-neg {{ color: #FF5C72; font-weight: 500; }}
  .td-ticker {{ color: #4DB8FF; font-weight: 600; }}
  .td-name {{ color: #E8EDF5; max-width: 160px; overflow: hidden; text-overflow: ellipsis; }}

  /* PAGINATION */
  .pagination {{
    display: flex;
    justify-content: flex-end;
    align-items: center;
    gap: 6px;
    margin-top: 10px;
    font-size: 12px;
  }}
  .page-btn {{
    background: #111D2E;
    border: 1px solid #1E3A5F;
    color: #7B9BB5;
    padding: 4px 10px;
    border-radius: 6px;
    cursor: pointer;
    font-size: 12px;
    transition: all 0.15s;
  }}
  .page-btn:hover, .page-btn.active {{
    background: #1E3A5F;
    color: #4DB8FF;
    border-color: #4DB8FF;
  }}
  .page-info {{ color: #5A7A95; }}

  /* FILTER */
  .filter-bar {{
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    margin-bottom: 14px;
    padding: 14px;
    background: #090F1A;
    border-radius: 8px;
    border: 1px solid #141E2E;
  }}
  .filter-group {{ display: flex; flex-direction: column; gap: 3px; flex: 1; min-width: 120px; }}
  .filter-label {{ font-size: 10px; color: #5A7A95; text-transform: uppercase; letter-spacing: 0.5px; }}
  .filter-select, .filter-input {{
    background: #111D2E;
    border: 1px solid #1E3A5F;
    color: #C8D8E8;
    padding: 6px 8px;
    border-radius: 6px;
    font-size: 11px;
    font-family: 'DM Sans', sans-serif;
    width: 100%;
  }}
  .filter-select:focus, .filter-input:focus {{
    outline: none;
    border-color: #4DB8FF;
  }}
  .filter-reset {{
    background: transparent;
    border: 1px solid #1E3A5F;
    color: #5A7A95;
    padding: 6px 12px;
    border-radius: 6px;
    cursor: pointer;
    font-size: 11px;
    align-self: flex-end;
    transition: all 0.15s;
  }}
  .filter-reset:hover {{ border-color: #4DB8FF; color: #4DB8FF; }}

  /* CANVAS CHARTS */
  .chart-container {{
    position: relative;
    width: 100%;
    margin-top: 10px;
  }}
  canvas {{ border-radius: 8px; max-width: 100%; }}

  /* SEARCH */
  .search-wrap {{
    position: relative;
    margin-bottom: 16px;
  }}
  .search-input {{
    width: 100%;
    background: #111D2E;
    border: 1px solid #1E3A5F;
    color: #C8D8E8;
    padding: 10px 14px;
    border-radius: 8px;
    font-size: 14px;
    font-family: 'DM Sans', sans-serif;
    transition: border-color 0.2s;
  }}
  .search-input:focus {{ outline: none; border-color: #4DB8FF; }}
  .autocomplete-list {{
    position: absolute;
    top: 100%; left: 0; right: 0;
    background: #111D2E;
    border: 1px solid #1E3A5F;
    border-top: none;
    border-radius: 0 0 8px 8px;
    z-index: 100;
    max-height: 200px;
    overflow-y: auto;
    display: none;
  }}
  .autocomplete-item {{
    padding: 8px 14px;
    cursor: pointer;
    font-size: 13px;
    color: #C8D8E8;
    transition: background 0.1s;
  }}
  .autocomplete-item:hover {{ background: #1A2E45; color: #4DB8FF; }}
  .autocomplete-item span {{ color: #4DB8FF; font-weight: 600; margin-right: 8px; }}

  /* RADAR */
  #radar-wrapper {{
    display: none;
    margin-top: 16px;
  }}
  .radar-header {{
    text-align: center;
    margin-bottom: 12px;
  }}
  .radar-title {{
    font-family: 'DM Serif Display', serif;
    font-size: 20px;
    color: #E8EDF5;
  }}
  .radar-score {{
    font-size: 14px;
    color: #7B9BB5;
    margin-top: 4px;
  }}
  #radarCanvas {{ display: block; margin: 0 auto; }}

  /* FOOTER */
  .footer {{
    text-align: center;
    color: #3A5A75;
    font-size: 11px;
    margin-top: 24px;
    padding: 16px;
    border-top: 1px solid #1A2E45;
  }}
  .footer a {{ color: #4DB8FF; text-decoration: none; }}

  /* RESPONSIVE */
  @media (max-width: 600px) {{
    body {{ padding: 10px; }}
    .header {{ padding: 20px 16px; }}
    .section {{ padding: 14px; }}
    .filter-bar {{ flex-direction: column; }}
    .filter-group {{ min-width: 100%; }}
  }}
</style>
</head>
<body>

<!-- HEADER -->
<div class="header">
  <h1>Noahs Finanzblog <span>📈</span></h1>
  <div class="datum">{datum_de}</div>
</div>

<!-- MARKTÜBERSICHT -->
<div class="section">
  <div class="section-title">🌍 Marktübersicht</div>
  <div class="metric-grid">
    <div class="metric-card">
      <div class="metric-val {'pos' if avg_perf >= 0 else 'neg'}">{fmt_pct(avg_perf)}</div>
      <div class="metric-lbl">Ø Performance (1M)</div>
    </div>
    <div class="metric-card">
      <div class="metric-val">{fmt_de(positiv_pct, 1)}%</div>
      <div class="metric-lbl">Aktien im Plus (1M)</div>
    </div>
    <div class="metric-card">
      <div class="metric-val pos">{n_oversold:,}</div>
      <div class="metric-lbl">Überverkauft (RSI&lt;30)</div>
    </div>
    <div class="metric-card">
      <div class="metric-val neg">{n_overbought:,}</div>
      <div class="metric-lbl">Überkauft (RSI&gt;70)</div>
    </div>
    <div class="metric-card">
      <div class="metric-val">{n_gesamt:,}</div>
      <div class="metric-lbl">Aktien analysiert</div>
    </div>
  </div>
</div>

<!-- SEKTORPERFORMANCE -->
<div class="section">
  <div class="section-title">🏭 Sektorperformance</div>
  <div class="tbl-wrap">
    <table class="dt" id="tbl-sektor">
      <thead><tr>
        <th data-col="Sektor">Sektor<span class="sort-icon"></span></th>
        <th data-col="Anzahl">Anzahl<span class="sort-icon"></span></th>
        <th data-col="Perf_Monat_Avg">Perf. 1M<span class="sort-icon"></span></th>
        <th data-col="Perf_Jahr_Avg">Perf. 1J<span class="sort-icon"></span></th>
        <th data-col="KGV_Forward_Median">KGV Forward (Median)<span class="sort-icon"></span></th>
      </tr></thead>
      <tbody id="tbody-sektor"></tbody>
    </table>
  </div>
</div>

<!-- WATCHLIST -->
<div class="section">
  <div class="section-title">⭐ Noahs Aktien-Watchlist</div>
  <div class="tbl-wrap">
    <table class="dt" id="tbl-watchlist">
      <thead><tr>
        <th data-col="Ticker">Ticker<span class="sort-icon"></span></th>
        <th data-col="Unternehmen">Unternehmen<span class="sort-icon"></span></th>
        <th data-col="Sektor">Sektor<span class="sort-icon"></span></th>
        <th data-col="Marktkapitalisierung_Mrd">Mkt Cap (Mrd.)<span class="sort-icon"></span></th>
        <th data-col="Gewinn_Mrd">Gewinn (Mrd.)<span class="sort-icon"></span></th>
        <th data-col="KGV">KGV<span class="sort-icon"></span></th>
        <th data-col="KGV_Forward">KGV Fwd.<span class="sort-icon"></span></th>
        <th data-col="EPS_naechste_5J_Pct">EPS 5J<span class="sort-icon"></span></th>
        <th data-col="PEG">PEG<span class="sort-icon"></span></th>
        <th data-col="Analyst_Empfehlung">Analyst<span class="sort-icon"></span></th>
        <th data-col="Gewinnmarge_Pct">Gewinnmarge<span class="sort-icon"></span></th>
      </tr></thead>
      <tbody id="tbody-watchlist"></tbody>
    </table>
  </div>
</div>

<!-- QUALITY SCREEN -->
<div class="section">
  <div class="section-title">🔬 Quality &amp; Growth Screen</div>
  <div class="filter-bar" id="quality-filters">
    <div class="filter-group">
      <span class="filter-label">KGV Forward (max)</span>
      <input class="filter-input" type="number" id="f-kgv-max" placeholder="z.B. 40" value="40">
    </div>
    <div class="filter-group">
      <span class="filter-label">Mkt Cap (Mrd., min)</span>
      <input class="filter-input" type="number" id="f-mktcap-min" placeholder="z.B. 1" value="">
    </div>
    <div class="filter-group">
      <span class="filter-label">EPS 5J Wachstum (min%)</span>
      <input class="filter-input" type="number" id="f-eps5-min" placeholder="z.B. 10" value="10">
    </div>
    <div class="filter-group">
      <span class="filter-label">PEG (max)</span>
      <input class="filter-input" type="number" id="f-peg-max" placeholder="z.B. 3" value="">
    </div>
    <div class="filter-group">
      <span class="filter-label">Analyst (max, 1=Buy)</span>
      <input class="filter-input" type="number" id="f-analyst-max" placeholder="z.B. 2.5" value="">
    </div>
    <div class="filter-group">
      <span class="filter-label">Gewinnmarge (min%)</span>
      <input class="filter-input" type="number" id="f-marge-min" placeholder="z.B. 10" value="10">
    </div>
    <button class="filter-reset" onclick="resetQualityFilters()">↺ Reset</button>
  </div>
  <div class="tbl-wrap">
    <table class="dt" id="tbl-quality">
      <thead><tr>
        <th data-col="Ticker">Ticker<span class="sort-icon"></span></th>
        <th data-col="Unternehmen">Unternehmen<span class="sort-icon"></span></th>
        <th data-col="Sektor">Sektor<span class="sort-icon"></span></th>
        <th data-col="Marktkapitalisierung_Mrd">Mkt Cap<span class="sort-icon"></span></th>
        <th data-col="KGV_Forward">KGV Fwd.<span class="sort-icon"></span></th>
        <th data-col="EPS_naechste_5J_Pct">EPS 5J<span class="sort-icon"></span></th>
        <th data-col="Gewinnmarge_Pct">Gewinnmarge<span class="sort-icon"></span></th>
        <th data-col="PEG">PEG<span class="sort-icon"></span></th>
        <th data-col="Analyst_Empfehlung">Analyst<span class="sort-icon"></span></th>
        <th data-col="Analyst_Upside_Pct">Upside<span class="sort-icon"></span></th>
      </tr></thead>
      <tbody id="tbody-quality"></tbody>
    </table>
  </div>
  <div class="pagination" id="pg-quality"></div>
</div>

<!-- CHARTS -->
<div class="section">
  <div class="section-title">📊 KGV &amp; Forward KGV – Marktübersicht</div>
  <div style="margin-bottom:10px;display:flex;gap:8px;flex-wrap:wrap;align-items:center;">
    <span style="font-size:11px;color:#5A7A95;text-transform:uppercase;letter-spacing:0.5px;">Sektor:</span>
    <select class="filter-select" id="kgv-sektor-filter" style="width:auto;min-width:150px;" onchange="renderKGVChart()">
      <option value="">Alle Sektoren</option>
    </select>
  </div>
  <div class="chart-container"><canvas id="kgvChart" height="300"></canvas></div>
</div>

<div class="section">
  <div class="section-title">📈 KGV vs. EPS-Wachstum 5J – Streudiagramm</div>
  <div style="margin-bottom:10px;display:flex;gap:8px;flex-wrap:wrap;align-items:center;">
    <span style="font-size:11px;color:#5A7A95;text-transform:uppercase;letter-spacing:0.5px;">Sektor:</span>
    <select class="filter-select" id="scatter-sektor-filter" style="width:auto;min-width:150px;" onchange="renderScatterChart()">
      <option value="">Alle Sektoren</option>
    </select>
  </div>
  <div class="chart-container"><canvas id="scatterChart" height="320"></canvas></div>
</div>

<!-- AKTIEN-RADAR -->
<div class="section">
  <div class="section-title">🎯 Aktien-Score &amp; Radar-Analyse</div>
  <p style="color:#5A7A95;font-size:12px;margin-bottom:12px;">
    Composite Score 0–100 basierend auf KGV, Forward KGV, EPS-Wachstum 5J, Gewinnmarge, PEG und Analystenrating.
  </p>
  <div class="search-wrap">
    <input class="search-input" id="radar-search" type="text"
           placeholder="🔍 Unternehmen suchen – z.B. 'NVIDIA' oder 'NV'..."
           oninput="onRadarSearch()" onblur="setTimeout(()=>hideAutocomplete(),200)">
    <div class="autocomplete-list" id="autocomplete-list"></div>
  </div>
  <div id="radar-wrapper">
    <div class="radar-header">
      <div class="radar-title" id="radar-title"></div>
      <div class="radar-score" id="radar-subtitle"></div>
    </div>
    <canvas id="radarCanvas" width="420" height="420"></canvas>
  </div>
</div>

<!-- FOOTER -->
<div class="footer">
  Keine Anlageberatung – Newsletter erstellt von
  <a href="https://www.linkedin.com/in/noah-schulz-971031301/" target="_blank">Noah Schulz</a>
</div>

<script>
// ============================================================
// DATEN
// ============================================================
const WATCHLIST_DATA = {watchlist_json};
const QUALITY_DATA   = {quality_json};
const SEKTOR_DATA    = {sektor_json};
const PLOT_DATA      = {plot_json};
const SCORE_DATA     = {score_json};
const SEKTOREN_LIST  = {sektoren_json};

// ============================================================
// HILFSFUNKTIONEN
// ============================================================
function fmtDE(val, decimals=2, suffix='') {{
  if (val === '' || val === null || val === undefined || isNaN(Number(val))) return '–';
  const num = Number(val);
  return num.toLocaleString('de-DE', {{
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals
  }}) + suffix;
}}
function fmtPct(val, dec=1)  {{ return fmtDE(val, dec, '%'); }}
function fmtMrd(val, dec=1)  {{ return fmtDE(val, dec, ' Mrd.'); }}
function fmtNum(val, dec=2)  {{ return fmtDE(val, dec); }}

function colorClass(val) {{
  if (val === '' || isNaN(Number(val))) return '';
  return Number(val) >= 0 ? 'td-pos' : 'td-neg';
}}
function signStr(val, dec=1, suffix='%') {{
  if (val === '' || isNaN(Number(val))) return '–';
  const n = Number(val);
  const s = fmtDE(Math.abs(n), dec, suffix);
  return n >= 0 ? '+' + s : '−' + s;
}}

// ============================================================
// SORTIERBARE TABELLEN
// ============================================================
function makeTable(tbodyId, data, renderRow, sortState={{col:null,asc:true}}) {{
  const tbody = document.getElementById(tbodyId);
  const table = tbody.closest('table');
  const ths   = table.querySelectorAll('th[data-col]');

  function render(rows) {{
    tbody.innerHTML = rows.map(renderRow).join('');
  }}

  function sort(col) {{
    if (sortState.col === col) sortState.asc = !sortState.asc;
    else {{ sortState.col = col; sortState.asc = true; }}
    ths.forEach(th => {{
      th.classList.remove('asc','desc');
      if (th.dataset.col === col) th.classList.add(sortState.asc ? 'asc' : 'desc');
    }});
    data.sort((a,b) => {{
      const av = isNaN(Number(a[col])) ? String(a[col]||'') : Number(a[col]);
      const bv = isNaN(Number(b[col])) ? String(b[col]||'') : Number(b[col]);
      if (av < bv) return sortState.asc ? -1 : 1;
      if (av > bv) return sortState.asc ?  1 : -1;
      return 0;
    }});
    render(data);
  }}

  ths.forEach(th => th.addEventListener('click', () => sort(th.dataset.col)));
  render(data);
  return {{ render, sort }};
}}

// Sektor-Tabelle
makeTable('tbody-sektor', SEKTOR_DATA, row => `
  <tr>
    <td>${{row.Sektor||'–'}}</td>
    <td>${{row.Anzahl||'–'}}</td>
    <td class="${{colorClass(row.Perf_Monat_Avg)}}">${{signStr(row.Perf_Monat_Avg)}}</td>
    <td class="${{colorClass(row.Perf_Jahr_Avg)}}">${{signStr(row.Perf_Jahr_Avg)}}</td>
    <td>${{fmtNum(row.KGV_Forward_Median)}}</td>
  </tr>
`);

// Watchlist-Tabelle
makeTable('tbody-watchlist', WATCHLIST_DATA, row => `
  <tr>
    <td class="td-ticker">${{row.Ticker||'–'}}</td>
    <td class="td-name">${{row.Unternehmen||'–'}}</td>
    <td style="color:#8AACC8">${{row.Sektor||'–'}}</td>
    <td>${{fmtMrd(row.Marktkapitalisierung_Mrd)}}</td>
    <td>${{fmtMrd(row.Gewinn_Mrd)}}</td>
    <td>${{fmtNum(row.KGV)}}</td>
    <td>${{fmtNum(row.KGV_Forward)}}</td>
    <td class="${{colorClass(row.EPS_naechste_5J_Pct)}}">${{fmtPct(row.EPS_naechste_5J_Pct)}}</td>
    <td>${{fmtNum(row.PEG)}}</td>
    <td>${{fmtNum(row.Analyst_Empfehlung)}}</td>
    <td class="${{colorClass(row.Gewinnmarge_Pct)}}">${{fmtPct(row.Gewinnmarge_Pct)}}</td>
  </tr>
`);

// ============================================================
// QUALITY SCREEN MIT PAGINATION + FILTER
// ============================================================
let qualityFiltered = [...QUALITY_DATA];
let qualitySortState = {{col: 'EPS_naechste_5J_Pct', asc: false}};
const PAGE_SIZE = 10;
let qualityPage = 1;

function getQualityFiltered() {{
  const kgvMax    = parseFloat(document.getElementById('f-kgv-max').value)    || Infinity;
  const mktMin    = parseFloat(document.getElementById('f-mktcap-min').value) || -Infinity;
  const eps5Min   = parseFloat(document.getElementById('f-eps5-min').value)   || -Infinity;
  const pegMax    = parseFloat(document.getElementById('f-peg-max').value)    || Infinity;
  const anlMax    = parseFloat(document.getElementById('f-analyst-max').value)|| Infinity;
  const margeMin  = parseFloat(document.getElementById('f-marge-min').value)  || -Infinity;

  return QUALITY_DATA.filter(r => {{
    const kgv   = Number(r.KGV_Forward)             || Infinity;
    const mkt   = Number(r.Marktkapitalisierung_Mrd)|| -Infinity;
    const eps5  = Number(r.EPS_naechste_5J_Pct)     || -Infinity;
    const peg   = Number(r.PEG)                     || Infinity;
    const anl   = Number(r.Analyst_Empfehlung)      || Infinity;
    const marge = Number(r.Gewinnmarge_Pct)         || -Infinity;
    return kgv <= kgvMax && mkt >= mktMin && eps5 >= eps5Min &&
           peg <= pegMax && anl <= anlMax && marge >= margeMin;
  }});
}}

function renderQualityTable() {{
  qualityFiltered = getQualityFiltered();

  // Sortieren
  qualityFiltered.sort((a,b) => {{
    const col = qualitySortState.col;
    const av  = isNaN(Number(a[col])) ? String(a[col]||'') : Number(a[col]);
    const bv  = isNaN(Number(b[col])) ? String(b[col]||'') : Number(b[col]);
    if (av < bv) return qualitySortState.asc ? -1 : 1;
    if (av > bv) return qualitySortState.asc ?  1 : -1;
    return 0;
  }});

  const totalPages = Math.ceil(qualityFiltered.length / PAGE_SIZE) || 1;
  if (qualityPage > totalPages) qualityPage = 1;

  const start  = (qualityPage - 1) * PAGE_SIZE;
  const rows   = qualityFiltered.slice(start, start + PAGE_SIZE);
  const tbody  = document.getElementById('tbody-quality');

  tbody.innerHTML = rows.map(row => `
    <tr>
      <td class="td-ticker">${{row.Ticker||'–'}}</td>
      <td class="td-name">${{row.Unternehmen||'–'}}</td>
      <td style="color:#8AACC8">${{row.Sektor||'–'}}</td>
      <td>${{fmtMrd(row.Marktkapitalisierung_Mrd)}}</td>
      <td>${{fmtNum(row.KGV_Forward)}}</td>
      <td class="${{colorClass(row.EPS_naechste_5J_Pct)}}">${{fmtPct(row.EPS_naechste_5J_Pct)}}</td>
      <td class="${{colorClass(row.Gewinnmarge_Pct)}}">${{fmtPct(row.Gewinnmarge_Pct)}}</td>
      <td>${{fmtNum(row.PEG)}}</td>
      <td>${{fmtNum(row.Analyst_Empfehlung)}}</td>
      <td class="${{colorClass(row.Analyst_Upside_Pct)}}">${{signStr(row.Analyst_Upside_Pct)}}</td>
    </tr>
  `).join('');

  // Pagination
  const pg = document.getElementById('pg-quality');
  pg.innerHTML = '';
  const span = document.createElement('span');
  span.className = 'page-info';
  span.textContent = `${{start+1}}–${{Math.min(start+PAGE_SIZE, qualityFiltered.length)}} von ${{qualityFiltered.length}}`;
  pg.appendChild(span);

  for (let i = 1; i <= totalPages; i++) {{
    const btn = document.createElement('button');
    btn.className = 'page-btn' + (i === qualityPage ? ' active' : '');
    btn.textContent = i;
    btn.onclick = () => {{ qualityPage = i; renderQualityTable(); }};
    pg.appendChild(btn);
  }}
}}

// Quality Sort
document.getElementById('tbl-quality').querySelectorAll('th[data-col]').forEach(th => {{
  th.addEventListener('click', () => {{
    const col = th.dataset.col;
    if (qualitySortState.col === col) qualitySortState.asc = !qualitySortState.asc;
    else {{ qualitySortState.col = col; qualitySortState.asc = false; }}
    document.getElementById('tbl-quality').querySelectorAll('th').forEach(t => t.classList.remove('asc','desc'));
    th.classList.add(qualitySortState.asc ? 'asc' : 'desc');
    qualityPage = 1;
    renderQualityTable();
  }});
}});

// Filter Events
['f-kgv-max','f-mktcap-min','f-eps5-min','f-peg-max','f-analyst-max','f-marge-min'].forEach(id => {{
  document.getElementById(id).addEventListener('input', () => {{ qualityPage = 1; renderQualityTable(); }});
}});

function resetQualityFilters() {{
  document.getElementById('f-kgv-max').value    = 40;
  document.getElementById('f-mktcap-min').value = '';
  document.getElementById('f-eps5-min').value   = 10;
  document.getElementById('f-peg-max').value    = '';
  document.getElementById('f-analyst-max').value= '';
  document.getElementById('f-marge-min').value  = 10;
  qualityPage = 1;
  renderQualityTable();
}}

renderQualityTable();

// ============================================================
// SEKTORFILTER FÜR CHARTS BEFÜLLEN
// ============================================================
['kgv-sektor-filter','scatter-sektor-filter'].forEach(id => {{
  const sel = document.getElementById(id);
  SEKTOREN_LIST.forEach(s => {{
    const opt = document.createElement('option');
    opt.value = s; opt.textContent = s;
    sel.appendChild(opt);
  }});
}});

// ============================================================
// KGV CHART (Canvas)
// ============================================================
function renderKGVChart() {{
  const sektor = document.getElementById('kgv-sektor-filter').value;
  let data = PLOT_DATA.filter(d =>
    (!sektor || d.Sektor === sektor) &&
    Number(d.KGV) > 0 && Number(d.KGV) < 150 &&
    Number(d.KGV_Forward) > 0 && Number(d.KGV_Forward) < 100
  );

  const kgvVals  = data.map(d => Number(d.KGV));
  const fkgvVals = data.map(d => Number(d.KGV_Forward));
  const avgKGV   = kgvVals.reduce((a,b)=>a+b,0)/kgvVals.length;
  const avgFKGV  = fkgvVals.reduce((a,b)=>a+b,0)/fkgvVals.length;
  const medKGV   = [...kgvVals].sort((a,b)=>a-b)[Math.floor(kgvVals.length/2)];
  const medFKGV  = [...fkgvVals].sort((a,b)=>a-b)[Math.floor(fkgvVals.length/2)];

  const canvas = document.getElementById('kgvChart');
  const ctx    = canvas.getContext('2d');
  const W = canvas.offsetWidth || 800;
  const H = 300;
  canvas.width  = W;
  canvas.height = H;

  const PAD = {{top:30, right:20, bottom:40, left:45}};
  const plotW = W - PAD.left - PAD.right;
  const plotH = H - PAD.top  - PAD.bottom;

  ctx.fillStyle = '#090F1A';
  ctx.fillRect(0, 0, W, H);

  // Skala
  const allVals = [...kgvVals, ...fkgvVals];
  const maxVal  = Math.min(Math.ceil(Math.max(...allVals) * 1.1 / 10) * 10, 150);
  const scale   = v => PAD.top + plotH - (v / maxVal) * plotH;

  // Grid
  ctx.strokeStyle = '#1A2E45';
  ctx.lineWidth   = 1;
  for (let g = 0; g <= 5; g++) {{
    const v = maxVal * g / 5;
    const y = scale(v);
    ctx.beginPath(); ctx.moveTo(PAD.left, y); ctx.lineTo(PAD.left + plotW, y);
    ctx.stroke();
    ctx.fillStyle = '#5A7A95';
    ctx.font = '10px DM Sans, sans-serif';
    ctx.textAlign = 'right';
    ctx.fillText(fmtDE(v,0), PAD.left - 6, y + 3);
  }}

  // Punkte: KGV
  const step = Math.max(1, Math.floor(data.length / 120));
  data.filter((_,i) => i % step === 0).forEach((d,i) => {{
    const x = PAD.left + (i / (data.length/step)) * plotW;
    const y = scale(Number(d.KGV));
    ctx.beginPath();
    ctx.arc(x, y, 3, 0, Math.PI*2);
    ctx.fillStyle = 'rgba(77,184,255,0.6)';
    ctx.fill();
  }});

  // Punkte: Forward KGV
  data.filter((_,i) => i % step === 0).forEach((d,i) => {{
    const x = PAD.left + (i / (data.length/step)) * plotW;
    const y = scale(Number(d.KGV_Forward));
    ctx.beginPath();
    ctx.arc(x, y, 3, 0, Math.PI*2);
    ctx.fillStyle = 'rgba(45,212,160,0.6)';
    ctx.fill();
  }});

  // Mittelwert-Linien
  function drawHLine(val, color, label) {{
    const y = scale(val);
    ctx.strokeStyle = color;
    ctx.lineWidth   = 1.5;
    ctx.setLineDash([6,4]);
    ctx.beginPath(); ctx.moveTo(PAD.left, y); ctx.lineTo(PAD.left+plotW, y);
    ctx.stroke();
    ctx.setLineDash([]);
    ctx.fillStyle  = color;
    ctx.font       = 'bold 10px DM Sans, sans-serif';
    ctx.textAlign  = 'left';
    ctx.fillText(label + ': ' + fmtDE(val,1), PAD.left+4, y-4);
  }}

  drawHLine(avgKGV,  '#4DB8FF', 'Ø KGV');
  drawHLine(medKGV,  'rgba(77,184,255,0.5)', 'Med. KGV');
  drawHLine(avgFKGV, '#2DD4A0', 'Ø Fwd KGV');
  drawHLine(medFKGV, 'rgba(45,212,160,0.5)', 'Med. Fwd KGV');

  // Legende
  const lgd = [
    ['KGV', 'rgba(77,184,255,0.8)'],
    ['Forward KGV', 'rgba(45,212,160,0.8)']
  ];
  let lx = PAD.left;
  lgd.forEach(([lbl, col]) => {{
    ctx.beginPath(); ctx.arc(lx+6, PAD.top-10, 5, 0, Math.PI*2);
    ctx.fillStyle = col; ctx.fill();
    ctx.fillStyle = '#C8D8E8';
    ctx.font = '11px DM Sans, sans-serif';
    ctx.textAlign = 'left';
    ctx.fillText(lbl, lx+14, PAD.top-6);
    lx += ctx.measureText(lbl).width + 30;
  }});

  // Achsenbeschriftung
  ctx.fillStyle = '#5A7A95';
  ctx.font = '11px DM Sans, sans-serif';
  ctx.textAlign = 'center';
  ctx.fillText(`${{data.length}} Unternehmen | Sektor: ${{sektor||'Alle'}}`, PAD.left + plotW/2, H-6);
}}

// ============================================================
// SCATTER CHART
// ============================================================
let scatterTooltip = {{visible: false, x:0, y:0, d:null}};

function renderScatterChart() {{
  const sektor = document.getElementById('scatter-sektor-filter').value;
  const data   = PLOT_DATA.filter(d =>
    (!sektor || d.Sektor === sektor) &&
    Number(d.KGV) > 0 && Number(d.KGV) < 100 &&
    Number(d.EPS_naechste_5J_Pct) > -50 && Number(d.EPS_naechste_5J_Pct) < 100
  );

  const canvas = document.getElementById('scatterChart');
  const ctx    = canvas.getContext('2d');
  const W = canvas.offsetWidth || 800;
  const H = 320;
  canvas.width  = W;
  canvas.height = H;

  const PAD = {{top:30, right:20, bottom:50, left:55}};
  const plotW = W - PAD.left - PAD.right;
  const plotH = H - PAD.top  - PAD.bottom;

  const xVals = data.map(d => Number(d.KGV));
  const yVals = data.map(d => Number(d.EPS_naechste_5J_Pct));
  const xMin  = 0, xMax = Math.min(Math.ceil(Math.max(...xVals)*1.1/10)*10, 100);
  const yMin  = Math.min(Math.floor(Math.min(...yVals)/5)*5, 0);
  const yMax  = Math.ceil(Math.max(...yVals)*1.1/5)*5;

  const xScale = v => PAD.left + ((v - xMin)/(xMax - xMin)) * plotW;
  const yScale = v => PAD.top  + plotH - ((v - yMin)/(yMax - yMin)) * plotH;

  ctx.fillStyle = '#090F1A';
  ctx.fillRect(0, 0, W, H);

  // Grid
  ctx.strokeStyle = '#1A2E45'; ctx.lineWidth = 1;
  for (let i=0; i<=5; i++) {{
    const xv = xMin + (xMax-xMin)*i/5;
    const x  = xScale(xv);
    ctx.beginPath(); ctx.moveTo(x, PAD.top); ctx.lineTo(x, PAD.top+plotH); ctx.stroke();
    ctx.fillStyle = '#5A7A95'; ctx.font = '10px DM Sans, sans-serif';
    ctx.textAlign = 'center';
    ctx.fillText(fmtDE(xv,0), x, PAD.top+plotH+14);

    const yv = yMin + (yMax-yMin)*i/5;
    const y  = yScale(yv);
    ctx.beginPath(); ctx.moveTo(PAD.left, y); ctx.lineTo(PAD.left+plotW, y); ctx.stroke();
    ctx.textAlign = 'right';
    ctx.fillText(fmtDE(yv,0)+'%', PAD.left-6, y+3);
  }}

  // Nulllinie
  if (yMin < 0 && yMax > 0) {{
    const y0 = yScale(0);
    ctx.strokeStyle = '#2A4A6A'; ctx.lineWidth = 1.5;
    ctx.beginPath(); ctx.moveTo(PAD.left, y0); ctx.lineTo(PAD.left+plotW, y0); ctx.stroke();
  }}

  // Punkte
  const sektorColors = {{
    'Technology':'#4DB8FF','Healthcare':'#2DD4A0','Financials':'#FFB347',
    'Consumer Cyclical':'#FF7BAC','Energy':'#FFD700','Industrials':'#A78BFA',
    'Consumer Defensive':'#6EE7B7','Utilities':'#93C5FD','Real Estate':'#FCA5A5',
    'Communication Services':'#F472B6','Basic Materials':'#D4A574'
  }};

  data.forEach(d => {{
    const x = xScale(Number(d.KGV));
    const y = yScale(Number(d.EPS_naechste_5J_Pct));
    ctx.beginPath();
    ctx.arc(x, y, 4, 0, Math.PI*2);
    ctx.fillStyle = (sektorColors[d.Sektor] || '#4DB8FF') + 'AA';
    ctx.fill();
  }});

  // Achsenlabels
  ctx.fillStyle = '#7B9BB5'; ctx.font = '11px DM Sans, sans-serif';
  ctx.textAlign = 'center';
  ctx.fillText('KGV (Trailing)', PAD.left + plotW/2, H-6);
  ctx.save();
  ctx.translate(14, PAD.top + plotH/2);
  ctx.rotate(-Math.PI/2);
  ctx.fillText('EPS Wachstum 5J (%)', 0, 0);
  ctx.restore();
  ctx.fillText(`${{data.length}} Unternehmen | Sektor: ${{sektor||'Alle'}}`, PAD.left+plotW/2, PAD.top-8);

  // Tooltip on hover
  canvas._data = data;
  canvas._scales = {{xScale, yScale, xMin, xMax, yMin, yMax}};
}}

// Scatter Tooltip
document.getElementById('scatterChart').addEventListener('mousemove', function(e) {{
  if (!this._data) return;
  const rect = this.getBoundingClientRect();
  const mx   = (e.clientX - rect.left) * (this.width / rect.width);
  const my   = (e.clientY - rect.top)  * (this.height / rect.height);
  const PAD  = {{top:30, right:20, bottom:50, left:55}};
  const {{xScale, yScale}} = this._scales;

  let closest = null, minDist = Infinity;
  this._data.forEach(d => {{
    const dx = xScale(Number(d.KGV)) - mx;
    const dy = yScale(Number(d.EPS_naechste_5J_Pct)) - my;
    const dist = Math.sqrt(dx*dx + dy*dy);
    if (dist < minDist) {{ minDist = dist; closest = d; }}
  }});

  const ctx = this.getContext('2d');
  renderScatterChart();

  if (minDist < 20 && closest) {{
    const tx = xScale(Number(closest.KGV));
    const ty = yScale(Number(closest.EPS_naechste_5J_Pct));
    ctx.fillStyle = 'rgba(9,15,26,0.95)';
    ctx.strokeStyle = '#4DB8FF';
    ctx.lineWidth   = 1;
    const bx = tx + 10, by = ty - 60, bw = 160, bh = 55;
    ctx.beginPath();
    ctx.roundRect(bx, by, bw, bh, 6);
    ctx.fill(); ctx.stroke();
    ctx.fillStyle = '#4DB8FF';
    ctx.font = 'bold 11px DM Sans, sans-serif';
    ctx.textAlign = 'left';
    ctx.fillText(closest.Ticker + ' – ' + (closest.Unternehmen||'').substring(0,18), bx+8, by+16);
    ctx.fillStyle = '#C8D8E8';
    ctx.font = '10px DM Sans, sans-serif';
    ctx.fillText('KGV: ' + fmtDE(closest.KGV,1), bx+8, by+30);
    ctx.fillText('EPS 5J: ' + fmtDE(closest.EPS_naechste_5J_Pct,1) + '%', bx+8, by+44);
  }}
}});

// ============================================================
// RADAR PLOT
// ============================================================
function onRadarSearch() {{
  const q = document.getElementById('radar-search').value.toLowerCase().trim();
  const list = document.getElementById('autocomplete-list');
  if (q.length < 1) {{ list.style.display = 'none'; return; }}

  const matches = SCORE_DATA.filter(d =>
    d.Ticker.toLowerCase().includes(q) ||
    (d.Unternehmen||'').toLowerCase().includes(q)
  ).slice(0, 8);

  if (!matches.length) {{ list.style.display = 'none'; return; }}

  list.innerHTML = matches.map(d =>
    `<div class="autocomplete-item" onclick="selectRadar('${{d.Ticker}}')">
      <span>${{d.Ticker}}</span>${{d.Unternehmen||''}}
      <span style="float:right;color:#5A7A95;font-size:10px">Score: ${{d.Score}}</span>
    </div>`
  ).join('');
  list.style.display = 'block';
}}

function hideAutocomplete() {{
  document.getElementById('autocomplete-list').style.display = 'none';
}}

function selectRadar(ticker) {{
  const d = SCORE_DATA.find(r => r.Ticker === ticker);
  if (!d) return;
  document.getElementById('radar-search').value = d.Ticker + ' – ' + d.Unternehmen;
  hideAutocomplete();
  drawRadar(d);
}}

function drawRadar(d) {{
  const wrapper = document.getElementById('radar-wrapper');
  wrapper.style.display = 'block';

  document.getElementById('radar-title').textContent =
    `${{d.Rang}}. ${{d.Unternehmen}} (${{d.Ticker}})`;

  const score = Number(d.Score);
  const scoreColor = score >= 70 ? '#2DD4A0' : score >= 45 ? '#FFB347' : '#FF5C72';
  document.getElementById('radar-subtitle').innerHTML =
    `Score: <span style="color:${{scoreColor}};font-weight:600;font-size:18px">${{score}}/100</span>
     &nbsp;|&nbsp; Rang ${{d.Rang}} von ${{SCORE_DATA.length}} Unternehmen`;

  const canvas = document.getElementById('radarCanvas');
  const ctx    = canvas.getContext('2d');
  const W = canvas.width, H = canvas.height;
  ctx.clearRect(0, 0, W, H);

  const cx = W/2, cy = H/2, R = Math.min(W,H)*0.35;
  const labels = ['KGV','Fwd. KGV','EPS 5J','Gewinnmarge','PEG','Analyst'];
  const keys   = ['S_KGV','S_FKGV','S_Wachstum','S_Marge','S_PEG','S_Analyst'];
  const vals   = keys.map(k => Math.max(0, Math.min(100, Number(d[k])||0)));
  const N      = labels.length;

  // Hintergrundkreise
  for (let ring = 1; ring <= 5; ring++) {{
    const r = R * ring / 5;
    ctx.strokeStyle = '#1A2E45';
    ctx.lineWidth   = 1;
    ctx.beginPath();
    for (let i = 0; i <= N; i++) {{
      const ang = (i/N)*Math.PI*2 - Math.PI/2;
      const x = cx + r*Math.cos(ang), y = cy + r*Math.sin(ang);
      i === 0 ? ctx.moveTo(x,y) : ctx.lineTo(x,y);
    }}
    ctx.closePath(); ctx.stroke();
    ctx.fillStyle = '#5A7A95';
    ctx.font = '9px DM Sans, sans-serif';
    ctx.textAlign = 'center';
    ctx.fillText((ring*20)+'', cx+4, cy - r + 3);
  }}

  // Achsen
  for (let i = 0; i < N; i++) {{
    const ang = (i/N)*Math.PI*2 - Math.PI/2;
    ctx.strokeStyle = '#1A2E45'; ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(cx, cy);
    ctx.lineTo(cx + R*Math.cos(ang), cy + R*Math.sin(ang));
    ctx.stroke();
  }}

  // Datenpunkte
  ctx.beginPath();
  vals.forEach((v, i) => {{
    const ang = (i/N)*Math.PI*2 - Math.PI/2;
    const r   = R * v / 100;
    const x = cx + r*Math.cos(ang), y = cy + r*Math.sin(ang);
    i === 0 ? ctx.moveTo(x,y) : ctx.lineTo(x,y);
  }});
  ctx.closePath();
  ctx.fillStyle   = scoreColor + '33';
  ctx.strokeStyle = scoreColor;
  ctx.lineWidth   = 2;
  ctx.fill(); ctx.stroke();

  // Punkte
  vals.forEach((v, i) => {{
    const ang = (i/N)*Math.PI*2 - Math.PI/2;
    const r   = R * v / 100;
    ctx.beginPath();
    ctx.arc(cx + r*Math.cos(ang), cy + r*Math.sin(ang), 4, 0, Math.PI*2);
    ctx.fillStyle = scoreColor; ctx.fill();
  }});

  // Labels
  labels.forEach((lbl, i) => {{
    const ang   = (i/N)*Math.PI*2 - Math.PI/2;
    const lR    = R + 28;
    const x     = cx + lR*Math.cos(ang);
    const y     = cy + lR*Math.sin(ang);
    ctx.fillStyle  = '#C8D8E8';
    ctx.font       = 'bold 11px DM Sans, sans-serif';
    ctx.textAlign  = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText(lbl, x, y-7);
    ctx.fillStyle = scoreColor;
    ctx.font      = '10px DM Sans, sans-serif';
    ctx.fillText(fmtDE(vals[i],0)+'/100', x, y+7);
  }});

  // Score in der Mitte
  ctx.fillStyle    = scoreColor;
  ctx.font         = 'bold 28px DM Serif Display, serif';
  ctx.textAlign    = 'center';
  ctx.textBaseline = 'middle';
  ctx.fillText(score, cx, cy-8);
  ctx.fillStyle = '#7B9BB5';
  ctx.font      = '11px DM Sans, sans-serif';
  ctx.fillText('Score', cx, cy+12);
}}

// ============================================================
// INITIALISIERUNG
// ============================================================
renderKGVChart();
renderScatterChart();
</script>

</body>
</html>"""

    return html

# ============================================================
# MAIL VERSENDEN
# ============================================================

def sende_newsletter(html_content):
    if not MAIL_SENDER or not MAIL_PASSWORD or not MAIL_RECEIVER:
        print("❌ Mail-Credentials fehlen.")
        return False

    msg            = MIMEMultipart("alternative")
    msg["Subject"] = f"Noahs Finanzblog 📈 – {datum_de}"
    msg["From"]    = f"Noahs Finanzblog <{MAIL_SENDER}>"
    msg["To"]      = MAIL_RECEIVER
    msg.attach(MIMEText(html_content, "html"))

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(MAIL_SENDER, MAIL_PASSWORD)
            server.sendmail(MAIL_SENDER, MAIL_RECEIVER, msg.as_string())
        print(f"✅ Newsletter versendet an {MAIL_RECEIVER}")
        return True
    except Exception as e:
        print(f"❌ Fehler: {e}")
        return False

# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":
    print(f"📧 Newsletter-Generierung: {datum_de}")
    df   = lade_und_bereite_auf()
    html = erstelle_newsletter(df)

    os.makedirs(DATA_DIR, exist_ok=True)
    with open(f"{DATA_DIR}/{today_str}_newsletter.html", "w", encoding="utf-8") as f:
        f.write(html)
    print(f"💾 HTML gespeichert: {DATA_DIR}/{today_str}_newsletter.html")

    sende_newsletter(html)
