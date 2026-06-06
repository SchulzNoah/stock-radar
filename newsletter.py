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

today     = datetime.now()
today_str = today.strftime("%Y-%m-%d")
DATA_DIR  = "data"
DOCS_DIR  = "docs"

MONATE_DE = {
    1:"Januar",2:"Februar",3:"März",4:"April",5:"Mai",6:"Juni",
    7:"Juli",8:"August",9:"September",10:"Oktober",11:"November",12:"Dezember"
}
datum_de = f"{today.day}. {MONATE_DE[today.month]} {today.year}"

GITHUB_PAGES_URL = "https://schulznoah.github.io/finance-pipeline/"

WATCHLIST_TICKERS = [
    "AAPL","MSFT","NVDA","GOOGL","AMZN","META","TSLA",
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
    try:
        if pd.isna(val): return "–"
        num = float(val)
        formatted = f"{num:,.{decimals}f}"
        formatted = formatted.replace(",", "X").replace(".", ",").replace("X", ".")
        return f"{formatted}{suffix}"
    except:
        return "–"

# ============================================================
# DATEN LADEN
# ============================================================

def lade_und_bereite_auf():
    sp_dateien = sorted(glob.glob(f"{DATA_DIR}/*_SP500_fundamentals.csv"))
    ns_dateien = sorted(glob.glob(f"{DATA_DIR}/*_NASDAQ_fundamentals.csv"))

    if not sp_dateien or not ns_dateien:
        raise FileNotFoundError(f"Keine CSVs in '{DATA_DIR}/' gefunden!")

    sp_file = sp_dateien[-1]
    ns_file = ns_dateien[-1]
    print(f"📂 Lade: {sp_file}")
    print(f"📂 Lade: {ns_file}")

    sp = pd.read_csv(sp_file, dtype=str, low_memory=False)
    ns = pd.read_csv(ns_file, dtype=str, low_memory=False)
    print(f"   SP500: {len(sp)} | NASDAQ: {len(ns)}")

    sp_only = sp[~sp['Ticker'].isin(ns['Ticker'])]
    df      = pd.concat([ns, sp_only], ignore_index=True)

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

    df = df[df['Preis'].notna() & (df['Preis'] > 0) & df['Unternehmen'].notna()].copy()
    print(f"✅ Master bereinigt: {len(df)} Unternehmen")
    return df

# ============================================================
# SCORE BERECHNEN
# ============================================================

def berechne_score(df):
    score_df = df[[
        'Ticker','Unternehmen','Sektor',
        'KGV','KGV_Forward','EPS_naechste_5J_Pct',
        'Gewinnmarge_Pct','PEG','Analyst_Empfehlung',
        'Marktkapitalisierung_Mrd'
    ]].copy()

    score_df = score_df[
        score_df['KGV'].notna() & score_df['KGV_Forward'].notna() &
        score_df['EPS_naechste_5J_Pct'].notna() &
        score_df['Gewinnmarge_Pct'].notna() &
        (score_df['KGV'] > 0) & (score_df['KGV_Forward'] > 0) &
        (score_df['Marktkapitalisierung_Mrd'].fillna(0) > 0.5)
    ].copy()

    def norm(series, invert=False):
        mn, mx = series.min(), series.max()
        if mx == mn: return pd.Series(50.0, index=series.index)
        r = (series - mn) / (mx - mn) * 100
        return 100 - r if invert else r

    score_df['KGV_cap']    = score_df['KGV'].clip(0, 100)
    score_df['FKGV_cap']   = score_df['KGV_Forward'].clip(0, 80)
    score_df['PEG_cap']    = score_df['PEG'].clip(0, 5).fillna(3)
    score_df['Recom_fill'] = score_df['Analyst_Empfehlung'].fillna(3)

    score_df['S_KGV']      = norm(score_df['KGV_cap'],    invert=True)
    score_df['S_FKGV']     = norm(score_df['FKGV_cap'],   invert=True)
    score_df['S_Wachstum'] = norm(score_df['EPS_naechste_5J_Pct'])
    score_df['S_Marge']    = norm(score_df['Gewinnmarge_Pct'])
    score_df['S_PEG']      = norm(score_df['PEG_cap'],    invert=True)
    score_df['S_Analyst']  = norm(score_df['Recom_fill'], invert=True)

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
        'KGV','KGV_Forward','EPS_naechste_5J_Pct','Gewinnmarge_Pct',
        'PEG','Analyst_Empfehlung'
    ]]

# ============================================================
# STATISCHE MAIL-HTML
# ============================================================

def erstelle_mail_html(df):
    """Einfache statische Mail – kein JavaScript nötig."""

    positiv_pct  = (df['Perf_Monat_Pct'] > 0).mean() * 100
    avg_perf     = df['Perf_Monat_Pct'].mean()
    n_oversold   = int((df['RSI'] < 30).sum())
    n_overbought = int((df['RSI'] > 70).sum())
    n_gesamt     = len(df)

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

    def pct_farbe(val):
        try:
            return '#2DD4A0' if float(val) >= 0 else '#FF5C72'
        except:
            return '#8AACC8'

    def sign_str(val, dec=1):
        try:
            n = float(val)
            s = fmt_de(abs(n), dec, '%')
            return ('+' if n >= 0 else '−') + s
        except:
            return '–'

    # Sektor-Tabellenzeilen
    sektor_rows = ""
    for _, r in sektor_df.iterrows():
        mp = r['Perf_Monat_Avg']
        jp = r['Perf_Jahr_Avg']
        sektor_rows += f"""
        <tr>
          <td style="padding:9px 10px;border-bottom:1px solid #1A2E45;color:#E0EAF5;font-size:13px">{r['Sektor']}</td>
          <td style="padding:9px 10px;border-bottom:1px solid #1A2E45;color:#8AACC8;font-size:13px;text-align:center">{int(r['Anzahl'])}</td>
          <td style="padding:9px 10px;border-bottom:1px solid #1A2E45;color:{pct_farbe(mp)};font-size:13px;text-align:right;font-weight:600">{sign_str(mp)}</td>
          <td style="padding:9px 10px;border-bottom:1px solid #1A2E45;color:{pct_farbe(jp)};font-size:13px;text-align:right;font-weight:600">{sign_str(jp)}</td>
          <td style="padding:9px 10px;border-bottom:1px solid #1A2E45;color:#C8D8E8;font-size:13px;text-align:right">{fmt_de(r['KGV_Forward_Median'],1)}</td>
        </tr>"""

    # Watchlist-Tabellenzeilen
    watchlist_df = df[df['Ticker'].isin(WATCHLIST_TICKERS)].copy()
    watchlist_df = watchlist_df.sort_values('Marktkapitalisierung_Mrd', ascending=False, na_position='last')

    watchlist_rows = ""
    for _, r in watchlist_df.iterrows():
        watchlist_rows += f"""
        <tr>
          <td style="padding:9px 10px;border-bottom:1px solid #1A2E45;color:#4DB8FF;font-size:12px;font-weight:700">{r.get('Ticker','–')}</td>
          <td style="padding:9px 10px;border-bottom:1px solid #1A2E45;color:#E0EAF5;font-size:12px">{str(r.get('Unternehmen','–'))[:22]}</td>
          <td style="padding:9px 10px;border-bottom:1px solid #1A2E45;color:#8AACC8;font-size:11px">{str(r.get('Sektor','–'))[:16]}</td>
          <td style="padding:9px 10px;border-bottom:1px solid #1A2E45;color:#C8D8E8;font-size:12px;text-align:right">{fmt_de(r.get('Marktkapitalisierung_Mrd'),1,' Mrd.')}</td>
          <td style="padding:9px 10px;border-bottom:1px solid #1A2E45;color:#C8D8E8;font-size:12px;text-align:right">{fmt_de(r.get('Gewinn_Mrd'),2,' Mrd.')}</td>
          <td style="padding:9px 10px;border-bottom:1px solid #1A2E45;color:#C8D8E8;font-size:12px;text-align:right">{fmt_de(r.get('KGV'),1)}</td>
          <td style="padding:9px 10px;border-bottom:1px solid #1A2E45;color:#C8D8E8;font-size:12px;text-align:right">{fmt_de(r.get('KGV_Forward'),1)}</td>
          <td style="padding:9px 10px;border-bottom:1px solid #1A2E45;color:{pct_farbe(r.get('EPS_naechste_5J_Pct'))};font-size:12px;text-align:right;font-weight:600">{fmt_de(r.get('EPS_naechste_5J_Pct'),1,'%')}</td>
          <td style="padding:9px 10px;border-bottom:1px solid #1A2E45;color:#C8D8E8;font-size:12px;text-align:right">{fmt_de(r.get('PEG'),2)}</td>
          <td style="padding:9px 10px;border-bottom:1px solid #1A2E45;color:#C8D8E8;font-size:12px;text-align:right">{fmt_de(r.get('Analyst_Empfehlung'),2)}</td>
          <td style="padding:9px 10px;border-bottom:1px solid #1A2E45;color:{pct_farbe(r.get('Gewinnmarge_Pct'))};font-size:12px;text-align:right;font-weight:600">{fmt_de(r.get('Gewinnmarge_Pct'),1,'%')}</td>
        </tr>"""

    # Avg Performance Farbe
    avg_color = '#2DD4A0' if avg_perf >= 0 else '#FF5C72'
    avg_sign  = sign_str(avg_perf)

    html = f"""<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Noahs Finanzblog</title>
</head>
<body style="margin:0;padding:0;background:#080C14;font-family:'Segoe UI',Arial,sans-serif;color:#E0EAF5;">
<div style="max-width:700px;margin:0 auto;padding:20px 16px;">

  <!-- HEADER -->
  <div style="background:linear-gradient(135deg,#0D1B2E,#112240);border:1px solid #1E3A5F;border-radius:14px;padding:28px 24px;margin-bottom:16px;">
    <div style="font-size:26px;font-weight:700;color:#E8F4FD;letter-spacing:-0.5px;">
      Noahs Finanzblog <span style="color:#4DB8FF">📈</span>
    </div>
    <div style="color:#7B9BB5;font-size:13px;margin-top:5px;">{datum_de}</div>
  </div>

  <!-- MARKTÜBERSICHT -->
  <div style="background:#0D1520;border:1px solid #1A2E45;border-radius:12px;padding:20px;margin-bottom:16px;">
    <div style="font-size:17px;font-weight:700;color:#4DB8FF;margin-bottom:16px;padding-bottom:10px;border-bottom:1px solid #1A2E45;">
      🌍 Marktübersicht
    </div>
    <table width="100%" cellpadding="0" cellspacing="0">
      <tr>
        <td width="20%" style="padding:4px;">
          <div style="background:#111D2E;border:1px solid #1E3A5F;border-radius:10px;padding:14px 10px;text-align:center;">
            <div style="font-size:22px;font-weight:700;color:{avg_color};">{avg_sign}</div>
            <div style="font-size:10px;color:#5A7A95;margin-top:4px;">Ø Perf. 1M</div>
          </div>
        </td>
        <td width="20%" style="padding:4px;">
          <div style="background:#111D2E;border:1px solid #1E3A5F;border-radius:10px;padding:14px 10px;text-align:center;">
            <div style="font-size:22px;font-weight:700;color:#4DB8FF;">{fmt_de(positiv_pct,1)}%</div>
            <div style="font-size:10px;color:#5A7A95;margin-top:4px;">Im Plus (1M)</div>
          </div>
        </td>
        <td width="20%" style="padding:4px;">
          <div style="background:#111D2E;border:1px solid #1E3A5F;border-radius:10px;padding:14px 10px;text-align:center;">
            <div style="font-size:22px;font-weight:700;color:#2DD4A0;">{fmt_de(n_oversold,0)}</div>
            <div style="font-size:10px;color:#5A7A95;margin-top:4px;">Überverkauft</div>
          </div>
        </td>
        <td width="20%" style="padding:4px;">
          <div style="background:#111D2E;border:1px solid #1E3A5F;border-radius:10px;padding:14px 10px;text-align:center;">
            <div style="font-size:22px;font-weight:700;color:#FF5C72;">{fmt_de(n_overbought,0)}</div>
            <div style="font-size:10px;color:#5A7A95;margin-top:4px;">Überkauft</div>
          </div>
        </td>
        <td width="20%" style="padding:4px;">
          <div style="background:#111D2E;border:1px solid #1E3A5F;border-radius:10px;padding:14px 10px;text-align:center;">
            <div style="font-size:22px;font-weight:700;color:#4DB8FF;">{fmt_de(n_gesamt,0)}</div>
            <div style="font-size:10px;color:#5A7A95;margin-top:4px;">Analysiert</div>
          </div>
        </td>
      </tr>
    </table>
  </div>

  <!-- INTERAKTIV-BUTTON -->
  <div style="background:linear-gradient(135deg,#0D2240,#112E50);border:1px solid #2A5080;border-radius:12px;padding:20px 24px;margin-bottom:16px;text-align:center;">
    <div style="font-size:15px;font-weight:600;color:#E0EAF5;margin-bottom:8px;">
      📊 Interaktive Analyse & Charts
    </div>
    <div style="font-size:12px;color:#7B9BB5;margin-bottom:14px;">
      Sortierbare Tabellen · KGV-Charts · Streudiagramme · Aktien-Radar mit Score
    </div>
    <a href="{GITHUB_PAGES_URL}" target="_blank"
       style="display:inline-block;background:#4DB8FF;color:#050C18;font-weight:700;
              font-size:14px;padding:12px 28px;border-radius:8px;text-decoration:none;
              letter-spacing:0.3px;">
      → Zum interaktiven Dashboard
    </a>
  </div>

  <!-- SEKTORPERFORMANCE -->
  <div style="background:#0D1520;border:1px solid #1A2E45;border-radius:12px;padding:20px;margin-bottom:16px;">
    <div style="font-size:17px;font-weight:700;color:#4DB8FF;margin-bottom:16px;padding-bottom:10px;border-bottom:1px solid #1A2E45;">
      🏭 Sektorperformance
    </div>
    <div style="overflow-x:auto;">
    <table width="100%" cellpadding="0" cellspacing="0" style="min-width:420px;">
      <thead>
        <tr style="background:#0A1628;">
          <th style="padding:10px;color:#4DB8FF;font-size:11px;text-align:left;border-bottom:2px solid #1E3A5F;text-transform:uppercase;letter-spacing:0.5px;">Sektor</th>
          <th style="padding:10px;color:#4DB8FF;font-size:11px;text-align:center;border-bottom:2px solid #1E3A5F;text-transform:uppercase;letter-spacing:0.5px;">Anzahl</th>
          <th style="padding:10px;color:#4DB8FF;font-size:11px;text-align:right;border-bottom:2px solid #1E3A5F;text-transform:uppercase;letter-spacing:0.5px;">Perf. 1M</th>
          <th style="padding:10px;color:#4DB8FF;font-size:11px;text-align:right;border-bottom:2px solid #1E3A5F;text-transform:uppercase;letter-spacing:0.5px;">Perf. 1J</th>
          <th style="padding:10px;color:#4DB8FF;font-size:11px;text-align:right;border-bottom:2px solid #1E3A5F;text-transform:uppercase;letter-spacing:0.5px;">KGV Fwd. (Med.)</th>
        </tr>
      </thead>
      <tbody>{sektor_rows}</tbody>
    </table>
    </div>
  </div>

  <!-- WATCHLIST -->
  <div style="background:#0D1520;border:1px solid #1A2E45;border-radius:12px;padding:20px;margin-bottom:16px;">
    <div style="font-size:17px;font-weight:700;color:#4DB8FF;margin-bottom:16px;padding-bottom:10px;border-bottom:1px solid #1A2E45;">
      ⭐ Noahs Aktien-Watchlist
    </div>
    <div style="overflow-x:auto;">
    <table width="100%" cellpadding="0" cellspacing="0" style="min-width:700px;">
      <thead>
        <tr style="background:#0A1628;">
          <th style="padding:9px 10px;color:#4DB8FF;font-size:10px;text-align:left;border-bottom:2px solid #1E3A5F;text-transform:uppercase;white-space:nowrap;">Ticker</th>
          <th style="padding:9px 10px;color:#4DB8FF;font-size:10px;text-align:left;border-bottom:2px solid #1E3A5F;text-transform:uppercase;white-space:nowrap;">Unternehmen</th>
          <th style="padding:9px 10px;color:#4DB8FF;font-size:10px;text-align:left;border-bottom:2px solid #1E3A5F;text-transform:uppercase;white-space:nowrap;">Sektor</th>
          <th style="padding:9px 10px;color:#4DB8FF;font-size:10px;text-align:right;border-bottom:2px solid #1E3A5F;text-transform:uppercase;white-space:nowrap;">Mkt Cap</th>
          <th style="padding:9px 10px;color:#4DB8FF;font-size:10px;text-align:right;border-bottom:2px solid #1E3A5F;text-transform:uppercase;white-space:nowrap;">Gewinn</th>
          <th style="padding:9px 10px;color:#4DB8FF;font-size:10px;text-align:right;border-bottom:2px solid #1E3A5F;text-transform:uppercase;white-space:nowrap;">KGV</th>
          <th style="padding:9px 10px;color:#4DB8FF;font-size:10px;text-align:right;border-bottom:2px solid #1E3A5F;text-transform:uppercase;white-space:nowrap;">KGV Fwd.</th>
          <th style="padding:9px 10px;color:#4DB8FF;font-size:10px;text-align:right;border-bottom:2px solid #1E3A5F;text-transform:uppercase;white-space:nowrap;">EPS 5J</th>
          <th style="padding:9px 10px;color:#4DB8FF;font-size:10px;text-align:right;border-bottom:2px solid #1E3A5F;text-transform:uppercase;white-space:nowrap;">PEG</th>
          <th style="padding:9px 10px;color:#4DB8FF;font-size:10px;text-align:right;border-bottom:2px solid #1E3A5F;text-transform:uppercase;white-space:nowrap;">Analyst</th>
          <th style="padding:9px 10px;color:#4DB8FF;font-size:10px;text-align:right;border-bottom:2px solid #1E3A5F;text-transform:uppercase;white-space:nowrap;">Gewinnmarge</th>
        </tr>
      </thead>
      <tbody>{watchlist_rows}</tbody>
    </table>
    </div>
  </div>

  <!-- FOOTER -->
  <div style="text-align:center;color:#3A5A75;font-size:11px;padding:16px;border-top:1px solid #1A2E45;margin-top:8px;">
    Keine Anlageberatung – Newsletter erstellt von
    <a href="https://www.linkedin.com/in/noah-schulz-971031301/" target="_blank"
       style="color:#4DB8FF;text-decoration:none;">Noah Schulz</a>
  </div>

</div>
</body>
</html>"""

    return html

# ============================================================
# INTERAKTIVE DASHBOARD-SEITE (docs/index.html)
# ============================================================

def erstelle_dashboard(df):
    """Vollständige interaktive HTML-Seite für GitHub Pages."""

    watchlist_df = df[df['Ticker'].isin(WATCHLIST_TICKERS)].copy()
    watchlist_df = watchlist_df.sort_values('Marktkapitalisierung_Mrd', ascending=False)

    quality_df = (
        df[
            df['Gewinnmarge_Pct'].notna() & df['EPS_naechste_5J_Pct'].notna() &
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
        .nlargest(200, 'Score')
        [[
            'Ticker','Unternehmen','Sektor','Marktkapitalisierung_Mrd',
            'KGV_Forward','EPS_naechste_5J_Pct','Gewinnmarge_Pct',
            'PEG','Analyst_Empfehlung','Analyst_Upside_Pct'
        ]]
    )

    plot_df = df[
        df['KGV'].notna() & df['KGV_Forward'].notna() &
        df['EPS_naechste_5J_Pct'].notna() & df['Sektor'].notna() &
        (df['KGV'] > 0) & (df['KGV'] < 150) &
        (df['KGV_Forward'] > 0) & (df['KGV_Forward'] < 100)
    ][['Ticker','Unternehmen','Sektor','KGV','KGV_Forward','EPS_naechste_5J_Pct']].copy()

    score_df      = berechne_score(df)
    sektoren_list = sorted(df['Sektor'].dropna().unique().tolist())

    watchlist_json = watchlist_df.fillna('').to_json(orient='records')
    quality_json   = quality_df.fillna('').to_json(orient='records')
    plot_json      = plot_df.fillna('').to_json(orient='records')
    score_json     = score_df.fillna('').to_json(orient='records')
    sektoren_json  = json.dumps(sektoren_list)

    # Marktmetriken für Dashboard
    positiv_pct  = (df['Perf_Monat_Pct'] > 0).mean() * 100
    avg_perf     = df['Perf_Monat_Pct'].mean()
    n_oversold   = int((df['RSI'] < 30).sum())
    n_overbought = int((df['RSI'] > 70).sum())
    n_gesamt     = len(df)

    def sign_str(val, dec=1):
        try:
            n = float(val)
            s = fmt_de(abs(n), dec, '%')
            return ('+' if n >= 0 else '−') + s
        except:
            return '–'

    avg_color = '#2DD4A0' if avg_perf >= 0 else '#FF5C72'

    html = f"""<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Noahs Finanzblog 📈 – {datum_de}</title>
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Serif+Display&family=DM+Sans:wght@300;400;500;600&display=swap');
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:'DM Sans',sans-serif;background:#080C14;color:#E8EDF5;padding:16px;max-width:960px;margin:0 auto}}
.header{{background:linear-gradient(135deg,#0D1B2E,#112240);border:1px solid #1E3A5F;border-radius:16px;padding:28px;margin-bottom:16px}}
.header h1{{font-family:'DM Serif Display',serif;font-size:clamp(20px,4vw,30px);color:#E8F4FD}}
.header h1 span{{color:#4DB8FF}}
.header .dt{{color:#7B9BB5;font-size:13px;margin-top:5px}}
.sec{{background:#0D1520;border:1px solid #1A2E45;border-radius:12px;padding:20px;margin-bottom:16px}}
.sec-title{{font-family:'DM Serif Display',serif;font-size:17px;color:#4DB8FF;margin-bottom:14px;padding-bottom:10px;border-bottom:1px solid #1A2E45}}
.mg{{display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));gap:10px;margin-bottom:4px}}
.mc{{background:#111D2E;border:1px solid #1E3A5F;border-radius:10px;padding:14px 10px;text-align:center}}
.mv{{font-size:clamp(16px,3vw,22px);font-weight:600;color:#4DB8FF;line-height:1.2}}
.ml{{font-size:10px;color:#5A7A95;margin-top:4px}}
.pos{{color:#2DD4A0!important}}.neg{{color:#FF5C72!important}}
.tw{{overflow-x:auto;-webkit-overflow-scrolling:touch}}
table.dt{{width:100%;border-collapse:collapse;font-size:12px;min-width:480px}}
table.dt th{{background:#0A1628;color:#4DB8FF;padding:9px 8px;text-align:left;border-bottom:2px solid #1E3A5F;white-space:nowrap;cursor:pointer;user-select:none;font-weight:600;font-size:10px;text-transform:uppercase;letter-spacing:.5px}}
table.dt th:hover{{background:#112240}}
table.dt th.asc::after{{content:' ▲';color:#4DB8FF}}
table.dt th.desc::after{{content:' ▼';color:#4DB8FF}}
table.dt th:not(.asc):not(.desc)::after{{content:' ⇅';color:#2A4A6A}}
table.dt td{{padding:8px;border-bottom:1px solid #141E2E;color:#C8D8E8;white-space:nowrap;font-size:12px}}
table.dt tr:hover td{{background:#0F1E32}}
.tp{{color:#4DB8FF;font-weight:700}}.tn{{color:#E8EDF5}}.ts{{color:#8AACC8}}
.td-pos{{color:#2DD4A0;font-weight:600}}.td-neg{{color:#FF5C72;font-weight:600}}
.pg{{display:flex;justify-content:flex-end;align-items:center;gap:6px;margin-top:10px;font-size:12px;flex-wrap:wrap}}
.pb{{background:#111D2E;border:1px solid #1E3A5F;color:#7B9BB5;padding:4px 10px;border-radius:6px;cursor:pointer;font-size:11px;transition:all .15s}}
.pb:hover,.pb.active{{background:#1E3A5F;color:#4DB8FF;border-color:#4DB8FF}}
.pi{{color:#5A7A95;font-size:11px}}
.fb{{display:flex;flex-wrap:wrap;gap:8px;margin-bottom:14px;padding:14px;background:#090F1A;border-radius:8px;border:1px solid #141E2E}}
.fg{{display:flex;flex-direction:column;gap:3px;flex:1;min-width:110px}}
.fl{{font-size:10px;color:#5A7A95;text-transform:uppercase;letter-spacing:.5px}}
.fi,.fs{{background:#111D2E;border:1px solid #1E3A5F;color:#C8D8E8;padding:6px 8px;border-radius:6px;font-size:11px;font-family:'DM Sans',sans-serif;width:100%}}
.fi:focus,.fs:focus{{outline:none;border-color:#4DB8FF}}
.fr{{background:transparent;border:1px solid #1E3A5F;color:#5A7A95;padding:6px 12px;border-radius:6px;cursor:pointer;font-size:11px;align-self:flex-end;transition:all .15s}}
.fr:hover{{border-color:#4DB8FF;color:#4DB8FF}}
.cc{{position:relative;width:100%;margin-top:8px}}
canvas{{border-radius:8px;max-width:100%}}
.sw{{position:relative;margin-bottom:14px}}
.si{{width:100%;background:#111D2E;border:1px solid #1E3A5F;color:#C8D8E8;padding:10px 14px;border-radius:8px;font-size:13px;font-family:'DM Sans',sans-serif;transition:border-color .2s}}
.si:focus{{outline:none;border-color:#4DB8FF}}
.al{{position:absolute;top:100%;left:0;right:0;background:#111D2E;border:1px solid #1E3A5F;border-top:none;border-radius:0 0 8px 8px;z-index:100;max-height:200px;overflow-y:auto;display:none}}
.ai{{padding:8px 14px;cursor:pointer;font-size:12px;color:#C8D8E8}}
.ai:hover{{background:#1A2E45;color:#4DB8FF}}
.ai span{{color:#4DB8FF;font-weight:700;margin-right:8px}}
#rw{{display:none;margin-top:14px;text-align:center}}
.rt{{font-family:'DM Serif Display',serif;font-size:18px;color:#E8EDF5}}
.rs{{font-size:13px;color:#7B9BB5;margin-top:4px}}
.footer{{text-align:center;color:#3A5A75;font-size:11px;margin-top:20px;padding:16px;border-top:1px solid #1A2E45}}
.footer a{{color:#4DB8FF;text-decoration:none}}
@media(max-width:600px){{body{{padding:10px}}.header{{padding:18px}}.sec{{padding:14px}}.fb{{flex-direction:column}}.fg{{min-width:100%}}}}
</style>
</head>
<body>

<div class="header">
  <h1>Noahs Finanzblog <span>📈</span></h1>
  <div class="dt">{datum_de}</div>
</div>

<!-- MARKTÜBERSICHT -->
<div class="sec">
  <div class="sec-title">🌍 Marktübersicht</div>
  <div class="mg">
    <div class="mc"><div class="mv" style="color:{avg_color}">{sign_str(avg_perf)}</div><div class="ml">Ø Perf. 1M</div></div>
    <div class="mc"><div class="mv">{fmt_de(positiv_pct,1)}%</div><div class="ml">Im Plus (1M)</div></div>
    <div class="mc"><div class="mv pos">{fmt_de(n_oversold,0)}</div><div class="ml">Überverkauft</div></div>
    <div class="mc"><div class="mv neg">{fmt_de(n_overbought,0)}</div><div class="ml">Überkauft</div></div>
    <div class="mc"><div class="mv">{fmt_de(n_gesamt,0)}</div><div class="ml">Analysiert</div></div>
  </div>
</div>

<!-- WATCHLIST -->
<div class="sec">
  <div class="sec-title">⭐ Noahs Aktien-Watchlist</div>
  <div class="tw">
    <table class="dt" id="tbl-wl">
      <thead><tr>
        <th data-col="Ticker">Ticker</th>
        <th data-col="Unternehmen">Unternehmen</th>
        <th data-col="Sektor">Sektor</th>
        <th data-col="Marktkapitalisierung_Mrd">Mkt Cap (Mrd.)</th>
        <th data-col="Gewinn_Mrd">Gewinn (Mrd.)</th>
        <th data-col="KGV">KGV</th>
        <th data-col="KGV_Forward">KGV Fwd.</th>
        <th data-col="EPS_naechste_5J_Pct">EPS 5J</th>
        <th data-col="PEG">PEG</th>
        <th data-col="Analyst_Empfehlung">Analyst</th>
        <th data-col="Gewinnmarge_Pct">Gewinnmarge</th>
      </tr></thead>
      <tbody id="tb-wl"></tbody>
    </table>
  </div>
</div>

<!-- QUALITY SCREEN -->
<div class="sec">
  <div class="sec-title">🔬 Quality &amp; Growth Screen</div>
  <div class="fb">
    <div class="fg"><span class="fl">KGV Fwd. (max)</span><input class="fi" type="number" id="f1" value="40"></div>
    <div class="fg"><span class="fl">Mkt Cap Mrd. (min)</span><input class="fi" type="number" id="f2" value=""></div>
    <div class="fg"><span class="fl">EPS 5J % (min)</span><input class="fi" type="number" id="f3" value="10"></div>
    <div class="fg"><span class="fl">PEG (max)</span><input class="fi" type="number" id="f4" value=""></div>
    <div class="fg"><span class="fl">Analyst (max)</span><input class="fi" type="number" id="f5" value=""></div>
    <div class="fg"><span class="fl">Gewinnmarge % (min)</span><input class="fi" type="number" id="f6" value="10"></div>
    <button class="fr" onclick="resetF()">↺ Reset</button>
  </div>
  <div class="tw">
    <table class="dt" id="tbl-qs">
      <thead><tr>
        <th data-col="Ticker">Ticker</th>
        <th data-col="Unternehmen">Unternehmen</th>
        <th data-col="Sektor">Sektor</th>
        <th data-col="Marktkapitalisierung_Mrd">Mkt Cap</th>
        <th data-col="KGV_Forward">KGV Fwd.</th>
        <th data-col="EPS_naechste_5J_Pct">EPS 5J</th>
        <th data-col="Gewinnmarge_Pct">Gewinnmarge</th>
        <th data-col="PEG">PEG</th>
        <th data-col="Analyst_Empfehlung">Analyst</th>
        <th data-col="Analyst_Upside_Pct">Upside</th>
      </tr></thead>
      <tbody id="tb-qs"></tbody>
    </table>
  </div>
  <div class="pg" id="pg-qs"></div>
</div>

<!-- KGV CHART -->
<div class="sec">
  <div class="sec-title">📊 KGV &amp; Forward KGV</div>
  <div style="display:flex;gap:8px;align-items:center;margin-bottom:10px;flex-wrap:wrap">
    <span style="font-size:10px;color:#5A7A95;text-transform:uppercase;letter-spacing:.5px">Sektor:</span>
    <select class="fs" id="kgv-sf" onchange="renderKGV()" style="width:auto;min-width:160px">
      <option value="">Alle Sektoren</option>
    </select>
  </div>
  <div class="cc"><canvas id="kgvC" height="280"></canvas></div>
</div>

<!-- SCATTER CHART -->
<div class="sec">
  <div class="sec-title">📈 KGV vs. EPS-Wachstum 5J</div>
  <div style="display:flex;gap:8px;align-items:center;margin-bottom:10px;flex-wrap:wrap">
    <span style="font-size:10px;color:#5A7A95;text-transform:uppercase;letter-spacing:.5px">Sektor:</span>
    <select class="fs" id="sc-sf" onchange="renderSC()" style="width:auto;min-width:160px">
      <option value="">Alle Sektoren</option>
    </select>
  </div>
  <div class="cc"><canvas id="scC" height="300"></canvas></div>
  <div id="sc-tt" style="display:none;background:#0D1520;border:1px solid #1E3A5F;border-radius:8px;padding:10px 14px;margin-top:10px;font-size:12px;color:#C8D8E8"></div>
</div>

<!-- RADAR -->
<div class="sec">
  <div class="sec-title">🎯 Aktien-Score &amp; Radar</div>
  <p style="color:#5A7A95;font-size:11px;margin-bottom:12px">Composite Score 0–100 · KGV · Fwd. KGV · EPS 5J · Gewinnmarge · PEG · Analyst</p>
  <div class="sw">
    <input class="si" id="rs" type="text" placeholder="🔍 Unternehmen suchen – z.B. NVIDIA oder NV..."
           oninput="onRS()" onblur="setTimeout(hideAC,200)">
    <div class="al" id="ac"></div>
  </div>
  <div id="rw">
    <div class="rt" id="rt"></div>
    <div class="rs" id="rsub"></div>
    <canvas id="rc" width="380" height="380" style="display:block;margin:14px auto 0"></canvas>
  </div>
</div>

<div class="footer">
  Keine Anlageberatung – Newsletter erstellt von
  <a href="https://www.linkedin.com/in/noah-schulz-971031301/" target="_blank">Noah Schulz</a>
</div>

<script>
const WL   = {watchlist_json};
const QS   = {quality_json};
const PD   = {plot_json};
const SD   = {score_json};
const SEKT = {sektoren_json};

// ---- FORMAT ----
function fDE(v,d=2,sfx=''){{
  if(v===''||v===null||v===undefined||isNaN(+v))return'–';
  return (+v).toLocaleString('de-DE',{{minimumFractionDigits:d,maximumFractionDigits:d}})+sfx;
}}
function fP(v,d=1){{return fDE(v,d,'%')}}
function fM(v,d=1){{return fDE(v,d,' Mrd.')}}
function sgn(v,d=1){{
  if(v===''||isNaN(+v))return'–';
  const n=+v,s=fDE(Math.abs(n),d,'%');
  return(n>=0?'+':'−')+s;
}}
function cc(v){{
  if(v===''||isNaN(+v))return'';
  return +v>=0?'td-pos':'td-neg';
}}

// ---- SORT TABLE ----
function mkTbl(tId,bId,data,renderRow){{
  const tbl=document.getElementById(tId);
  const tb=document.getElementById(bId);
  let st={{c:null,a:true}};
  function draw(rows){{tb.innerHTML=rows.map(renderRow).join('');}}
  tbl.querySelectorAll('th[data-col]').forEach(th=>{{
    th.addEventListener('click',()=>{{
      const col=th.dataset.col;
      if(st.c===col)st.a=!st.a; else{{st.c=col;st.a=true;}}
      tbl.querySelectorAll('th').forEach(t=>t.classList.remove('asc','desc'));
      th.classList.add(st.a?'asc':'desc');
      data.sort((a,b)=>{{
        const av=isNaN(+a[col])?String(a[col]||''):+a[col];
        const bv=isNaN(+b[col])?String(b[col]||''):+b[col];
        return st.a?(av<bv?-1:av>bv?1:0):(av>bv?-1:av<bv?1:0);
      }});
      draw(data);
    }});
  }});
  draw(data);
}}

// Watchlist
mkTbl('tbl-wl','tb-wl',WL,r=>`<tr>
  <td class="tp">${{r.Ticker||'–'}}</td>
  <td class="tn">${{(r.Unternehmen||'–').substring(0,22)}}</td>
  <td class="ts">${{(r.Sektor||'–').substring(0,16)}}</td>
  <td style="text-align:right;color:#C8D8E8">${{fM(r.Marktkapitalisierung_Mrd)}}</td>
  <td style="text-align:right;color:#C8D8E8">${{fM(r.Gewinn_Mrd,2)}}</td>
  <td style="text-align:right;color:#C8D8E8">${{fDE(r.KGV,1)}}</td>
  <td style="text-align:right;color:#C8D8E8">${{fDE(r.KGV_Forward,1)}}</td>
  <td style="text-align:right" class="${{cc(r.EPS_naechste_5J_Pct)}}">${{fP(r.EPS_naechste_5J_Pct)}}</td>
  <td style="text-align:right;color:#C8D8E8">${{fDE(r.PEG,2)}}</td>
  <td style="text-align:right;color:#C8D8E8">${{fDE(r.Analyst_Empfehlung,2)}}</td>
  <td style="text-align:right" class="${{cc(r.Gewinnmarge_Pct)}}">${{fP(r.Gewinnmarge_Pct)}}</td>
</tr>`);

// ---- QUALITY SCREEN + FILTER + PAGINATION ----
let qPage=1; const PS=10;
let qSort={{c:'EPS_naechste_5J_Pct',a:false}};

function getQF(){{
  const kmax=+document.getElementById('f1').value||Infinity;
  const mmin=+document.getElementById('f2').value||-Infinity;
  const emin=+document.getElementById('f3').value||-Infinity;
  const pmax=+document.getElementById('f4').value||Infinity;
  const amax=+document.getElementById('f5').value||Infinity;
  const gmin=+document.getElementById('f6').value||-Infinity;
  return QS.filter(r=>
    (+r.KGV_Forward||Infinity)<=kmax &&
    (+r.Marktkapitalisierung_Mrd||-Infinity)>=mmin &&
    (+r.EPS_naechste_5J_Pct||-Infinity)>=emin &&
    (+r.PEG||Infinity)<=pmax &&
    (+r.Analyst_Empfehlung||Infinity)<=amax &&
    (+r.Gewinnmarge_Pct||-Infinity)>=gmin
  );
}}

function renderQ(){{
  let data=getQF();
  data.sort((a,b)=>{{
    const c=qSort.c;
    const av=isNaN(+a[c])?String(a[c]||''):+a[c];
    const bv=isNaN(+b[c])?String(b[c]||''):+b[c];
    return qSort.a?(av<bv?-1:av>bv?1:0):(av>bv?-1:av<bv?1:0);
  }});
  const tp=Math.ceil(data.length/PS)||1;
  if(qPage>tp)qPage=1;
  const sl=data.slice((qPage-1)*PS,qPage*PS);
  document.getElementById('tb-qs').innerHTML=sl.map(r=>`<tr>
    <td class="tp">${{r.Ticker||'–'}}</td>
    <td class="tn">${{(r.Unternehmen||'–').substring(0,22)}}</td>
    <td class="ts">${{(r.Sektor||'–').substring(0,16)}}</td>
    <td style="text-align:right;color:#C8D8E8">${{fM(r.Marktkapitalisierung_Mrd)}}</td>
    <td style="text-align:right;color:#C8D8E8">${{fDE(r.KGV_Forward,1)}}</td>
    <td style="text-align:right" class="${{cc(r.EPS_naechste_5J_Pct)}}">${{fP(r.EPS_naechste_5J_Pct)}}</td>
    <td style="text-align:right" class="${{cc(r.Gewinnmarge_Pct)}}">${{fP(r.Gewinnmarge_Pct)}}</td>
    <td style="text-align:right;color:#C8D8E8">${{fDE(r.PEG,2)}}</td>
    <td style="text-align:right;color:#C8D8E8">${{fDE(r.Analyst_Empfehlung,2)}}</td>
    <td style="text-align:right" class="${{cc(r.Analyst_Upside_Pct)}}">${{sgn(r.Analyst_Upside_Pct)}}</td>
  </tr>`).join('');
  const pg=document.getElementById('pg-qs');
  pg.innerHTML='';
  const sp=document.createElement('span');
  sp.className='pi';
  const s=(qPage-1)*PS+1, e=Math.min(qPage*PS,data.length);
  sp.textContent=`${{s}}–${{e}} von ${{data.length}}`;
  pg.appendChild(sp);
  for(let i=1;i<=tp;i++){{
    const b=document.createElement('button');
    b.className='pb'+(i===qPage?' active':'');
    b.textContent=i;
    b.onclick=(()=>{{const p=i;return()=>{{qPage=p;renderQ();}}}})();
    pg.appendChild(b);
  }}
}}
document.getElementById('tbl-qs').querySelectorAll('th[data-col]').forEach(th=>{{
  th.addEventListener('click',()=>{{
    const c=th.dataset.col;
    if(qSort.c===c)qSort.a=!qSort.a; else{{qSort.c=c;qSort.a=false;}}
    document.getElementById('tbl-qs').querySelectorAll('th').forEach(t=>t.classList.remove('asc','desc'));
    th.classList.add(qSort.a?'asc':'desc');
    qPage=1; renderQ();
  }});
}});
['f1','f2','f3','f4','f5','f6'].forEach(id=>
  document.getElementById(id).addEventListener('input',()=>{{qPage=1;renderQ();}}));
function resetF(){{
  document.getElementById('f1').value=40;
  ['f2','f4','f5'].forEach(id=>document.getElementById(id).value='');
  document.getElementById('f3').value=10;
  document.getElementById('f6').value=10;
  qPage=1;renderQ();
}}
renderQ();

// ---- SEKTOREN FILTER ----
['kgv-sf','sc-sf'].forEach(id=>{{
  const s=document.getElementById(id);
  SEKT.forEach(sk=>{{const o=document.createElement('option');o.value=sk;o.textContent=sk;s.appendChild(o);}});
}});

// ---- KGV CHART ----
function renderKGV(){{
  const sek=document.getElementById('kgv-sf').value;
  const data=PD.filter(d=>(!sek||d.Sektor===sek)&&+d.KGV>0&&+d.KGV<150&&+d.KGV_Forward>0&&+d.KGV_Forward<100);
  const kv=data.map(d=>+d.KGV),fv=data.map(d=>+d.KGV_Forward);
  const avg=a=>a.reduce((s,v)=>s+v,0)/a.length;
  const med=a=>{{const s=[...a].sort((x,y)=>x-y);return s[Math.floor(s.length/2)];}};
  const aK=avg(kv),aF=avg(fv),mK=med(kv),mF=med(fv);

  const cv=document.getElementById('kgvC');
  const ctx=cv.getContext('2d');
  const W=cv.parentElement.offsetWidth||800,H=280;
  cv.width=W;cv.height=H;
  const P={{t:28,r:20,b:38,l:44}};
  const pw=W-P.l-P.r,ph=H-P.t-P.b;
  ctx.fillStyle='#090F1A';ctx.fillRect(0,0,W,H);
  const mx=Math.min(Math.ceil(Math.max(...kv,...fv)*1.1/10)*10,150);
  const sc=v=>P.t+ph-(v/mx)*ph;

  for(let g=0;g<=5;g++){{
    const v=mx*g/5,y=sc(v);
    ctx.strokeStyle='#1A2E45';ctx.lineWidth=1;
    ctx.beginPath();ctx.moveTo(P.l,y);ctx.lineTo(P.l+pw,y);ctx.stroke();
    ctx.fillStyle='#5A7A95';ctx.font='10px DM Sans,sans-serif';ctx.textAlign='right';
    ctx.fillText(fDE(v,0),P.l-5,y+3);
  }}

  const step=Math.max(1,Math.floor(data.length/100));
  data.filter((_,i)=>i%step===0).forEach((d,i)=>{{
    const x=P.l+(i/(data.length/step))*pw;
    ctx.beginPath();ctx.arc(x,sc(+d.KGV),3.5,0,Math.PI*2);
    ctx.fillStyle='rgba(77,184,255,0.55)';ctx.fill();
    ctx.beginPath();ctx.arc(x,sc(+d.KGV_Forward),3.5,0,Math.PI*2);
    ctx.fillStyle='rgba(45,212,160,0.55)';ctx.fill();
  }});

  function hl(val,col,lbl){{
    const y=sc(val);
    ctx.strokeStyle=col;ctx.lineWidth=1.5;ctx.setLineDash([6,4]);
    ctx.beginPath();ctx.moveTo(P.l,y);ctx.lineTo(P.l+pw,y);ctx.stroke();
    ctx.setLineDash([]);
    ctx.fillStyle=col;ctx.font='bold 9px DM Sans,sans-serif';ctx.textAlign='left';
    ctx.fillText(lbl+': '+fDE(val,1),P.l+4,y-3);
  }}
  hl(aK,'#4DB8FF','Ø KGV');hl(mK,'rgba(77,184,255,.5)','Med KGV');
  hl(aF,'#2DD4A0','Ø Fwd');hl(mF,'rgba(45,212,160,.5)','Med Fwd');

  const lgd=[['KGV','rgba(77,184,255,.8)'],['Fwd. KGV','rgba(45,212,160,.8)']];
  let lx=P.l;
  lgd.forEach(([lb,co])=>{{
    ctx.beginPath();ctx.arc(lx+5,P.t-10,4,0,Math.PI*2);ctx.fillStyle=co;ctx.fill();
    ctx.fillStyle='#C8D8E8';ctx.font='10px DM Sans,sans-serif';ctx.textAlign='left';
    ctx.fillText(lb,lx+12,P.t-7);lx+=ctx.measureText(lb).width+26;
  }});
  ctx.fillStyle='#5A7A95';ctx.font='10px DM Sans,sans-serif';ctx.textAlign='center';
  ctx.fillText(`${{data.length}} Unternehmen | ${{sek||'Alle Sektoren'}}`,P.l+pw/2,H-5);
}}

// ---- SCATTER ----
let scData=[];
function renderSC(){{
  const sek=document.getElementById('sc-sf').value;
  scData=PD.filter(d=>(!sek||d.Sektor===sek)&&+d.KGV>0&&+d.KGV<100&&+d.EPS_naechste_5J_Pct>-50&&+d.EPS_naechste_5J_Pct<100);
  const cv=document.getElementById('scC');
  const ctx=cv.getContext('2d');
  const W=cv.parentElement.offsetWidth||800,H=300;
  cv.width=W;cv.height=H;
  const P={{t:28,r:20,b:48,l:52}};
  const pw=W-P.l-P.r,ph=H-P.t-P.b;
  ctx.fillStyle='#090F1A';ctx.fillRect(0,0,W,H);

  const xv=scData.map(d=>+d.KGV),yv=scData.map(d=>+d.EPS_naechste_5J_Pct);
  const xmx=Math.min(Math.ceil(Math.max(...xv)*1.1/10)*10,100);
  const ymn=Math.min(Math.floor(Math.min(...yv)/5)*5,0);
  const ymx=Math.ceil(Math.max(...yv)*1.1/5)*5;
  const xs=v=>P.l+((v/xmx))*pw;
  const ys=v=>P.t+ph-((v-ymn)/(ymx-ymn))*ph;

  cv._xs=xs;cv._ys=ys;cv._d=scData;

  for(let i=0;i<=5;i++){{
    const xval=xmx*i/5,yval=ymn+(ymx-ymn)*i/5;
    ctx.strokeStyle='#1A2E45';ctx.lineWidth=1;
    ctx.beginPath();ctx.moveTo(xs(xval),P.t);ctx.lineTo(xs(xval),P.t+ph);ctx.stroke();
    ctx.beginPath();ctx.moveTo(P.l,ys(yval));ctx.lineTo(P.l+pw,ys(yval));ctx.stroke();
    ctx.fillStyle='#5A7A95';ctx.font='9px DM Sans,sans-serif';
    ctx.textAlign='center';ctx.fillText(fDE(xval,0),xs(xval),P.t+ph+13);
    ctx.textAlign='right';ctx.fillText(fDE(yval,0)+'%',P.l-4,ys(yval)+3);
  }}

  const SC={{
    'Technology':'#4DB8FF','Healthcare':'#2DD4A0','Financials':'#FFB347',
    'Consumer Cyclical':'#FF7BAC','Energy':'#FFD700','Industrials':'#A78BFA',
    'Consumer Defensive':'#6EE7B7','Utilities':'#93C5FD','Communication Services':'#F472B6',
    'Basic Materials':'#D4A574','Real Estate':'#FCA5A5'
  }};

  scData.forEach(d=>{{
    ctx.beginPath();ctx.arc(xs(+d.KGV),ys(+d.EPS_naechste_5J_Pct),4,0,Math.PI*2);
    ctx.fillStyle=(SC[d.Sektor]||'#4DB8FF')+'99';ctx.fill();
  }});

  ctx.fillStyle='#5A7A95';ctx.font='10px DM Sans,sans-serif';ctx.textAlign='center';
  ctx.fillText('KGV (Trailing)',P.l+pw/2,H-4);
  ctx.save();ctx.translate(14,P.t+ph/2);ctx.rotate(-Math.PI/2);
  ctx.fillText('EPS Wachstum 5J (%)',0,0);ctx.restore();
  ctx.fillText(`${{scData.length}} Unternehmen | ${{sek||'Alle Sektoren'}}`,P.l+pw/2,P.t-8);
}}

document.getElementById('scC').addEventListener('mousemove',function(e){{
  if(!this._d||!this._d.length)return;
  const rect=this.getBoundingClientRect();
  const mx=(e.clientX-rect.left)*(this.width/rect.width);
  const my=(e.clientY-rect.top)*(this.height/rect.height);
  let cl=null,md=Infinity;
  this._d.forEach(d=>{{
    const dx=this._xs(+d.KGV)-mx,dy=this._ys(+d.EPS_naechste_5J_Pct)-my;
    const dist=Math.sqrt(dx*dx+dy*dy);
    if(dist<md){{md=dist;cl=d;}}
  }});
  const tt=document.getElementById('sc-tt');
  if(md<18&&cl){{
    tt.style.display='block';
    tt.innerHTML=`<strong style="color:#4DB8FF">${{cl.Ticker}}</strong> – ${{cl.Unternehmen||''}}
      &nbsp;|&nbsp; KGV: ${{fDE(cl.KGV,1)}}
      &nbsp;|&nbsp; EPS 5J: ${{fDE(cl.EPS_naechste_5J_Pct,1)}}%
      &nbsp;|&nbsp; <span style="color:#8AACC8">${{cl.Sektor||''}}</span>`;
  }}else{{
    tt.style.display='none';
  }}
}});

// ---- RADAR ----
function onRS(){{
  const q=document.getElementById('rs').value.toLowerCase().trim();
  const ac=document.getElementById('ac');
  if(q.length<1){{ac.style.display='none';return;}}
  const m=SD.filter(d=>d.Ticker.toLowerCase().includes(q)||(d.Unternehmen||'').toLowerCase().includes(q)).slice(0,8);
  if(!m.length){{ac.style.display='none';return;}}
  ac.innerHTML=m.map(d=>`<div class="ai" onclick="selR('${{d.Ticker}}')"><span>${{d.Ticker}}</span>${{d.Unternehmen||''}} <span style="float:right;color:#5A7A95;font-size:10px">Score: ${{d.Score}}</span></div>`).join('');
  ac.style.display='block';
}}
function hideAC(){{document.getElementById('ac').style.display='none';}}
function selR(tk){{
  const d=SD.find(r=>r.Ticker===tk);
  if(!d)return;
  document.getElementById('rs').value=d.Ticker+' – '+(d.Unternehmen||'');
  hideAC();drawRadar(d);
}}
function drawRadar(d){{
  document.getElementById('rw').style.display='block';
  const sc=+d.Score;
  const scCol=sc>=70?'#2DD4A0':sc>=45?'#FFB347':'#FF5C72';
  document.getElementById('rt').textContent=`${{d.Rang}}. ${{d.Unternehmen}} (${{d.Ticker}})`;
  document.getElementById('rsub').innerHTML=`Score: <span style="color:${{scCol}};font-weight:700;font-size:17px">${{sc}}/100</span> &nbsp;|&nbsp; Rang ${{d.Rang}} von ${{SD.length}}`;
  const cv=document.getElementById('rc');
  const ctx=cv.getContext('2d');
  const W=cv.width,H=cv.height;
  ctx.clearRect(0,0,W,H);
  const cx=W/2,cy=H/2,R=Math.min(W,H)*0.33;
  const lbls=['KGV','Fwd. KGV','EPS 5J','Gewinnmarge','PEG','Analyst'];
  const keys=['S_KGV','S_FKGV','S_Wachstum','S_Marge','S_PEG','S_Analyst'];
  const vals=keys.map(k=>Math.max(0,Math.min(100,+d[k]||0)));
  const N=lbls.length;

  for(let ring=1;ring<=5;ring++){{
    const r=R*ring/5;
    ctx.strokeStyle='#1A2E45';ctx.lineWidth=1;ctx.beginPath();
    for(let i=0;i<=N;i++){{const a=(i/N)*Math.PI*2-Math.PI/2;i===0?ctx.moveTo(cx+r*Math.cos(a),cy+r*Math.sin(a)):ctx.lineTo(cx+r*Math.cos(a),cy+r*Math.sin(a));}}
    ctx.closePath();ctx.stroke();
  }}
  for(let i=0;i<N;i++){{
    const a=(i/N)*Math.PI*2-Math.PI/2;
    ctx.strokeStyle='#1A2E45';ctx.lineWidth=1;
    ctx.beginPath();ctx.moveTo(cx,cy);ctx.lineTo(cx+R*Math.cos(a),cy+R*Math.sin(a));ctx.stroke();
  }}
  ctx.beginPath();
  vals.forEach((v,i)=>{{
    const a=(i/N)*Math.PI*2-Math.PI/2,r=R*v/100;
    i===0?ctx.moveTo(cx+r*Math.cos(a),cy+r*Math.sin(a)):ctx.lineTo(cx+r*Math.cos(a),cy+r*Math.sin(a));
  }});
  ctx.closePath();ctx.fillStyle=scCol+'33';ctx.fill();
  ctx.strokeStyle=scCol;ctx.lineWidth=2;ctx.stroke();
  vals.forEach((v,i)=>{{
    const a=(i/N)*Math.PI*2-Math.PI/2,r=R*v/100;
    ctx.beginPath();ctx.arc(cx+r*Math.cos(a),cy+r*Math.sin(a),4,0,Math.PI*2);
    ctx.fillStyle=scCol;ctx.fill();
  }});
  lbls.forEach((lb,i)=>{{
    const a=(i/N)*Math.PI*2-Math.PI/2,lR=R+30;
    ctx.fillStyle='#C8D8E8';ctx.font='bold 10px DM Sans,sans-serif';
    ctx.textAlign='center';ctx.textBaseline='middle';
    ctx.fillText(lb,cx+lR*Math.cos(a),cy+lR*Math.sin(a)-7);
    ctx.fillStyle=scCol;ctx.font='9px DM Sans,sans-serif';
    ctx.fillText(fDE(vals[i],0)+'/100',cx+lR*Math.cos(a),cy+lR*Math.sin(a)+7);
  }});
  ctx.fillStyle=scCol;ctx.font='bold 26px DM Serif Display,serif';
  ctx.textAlign='center';ctx.textBaseline='middle';
  ctx.fillText(sc,cx,cy-8);
  ctx.fillStyle='#7B9BB5';ctx.font='10px DM Sans,sans-serif';
  ctx.fillText('Score',cx,cy+11);
}}

renderKGV();renderSC();
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
    print(f"📧 Newsletter: {datum_de}")
    df = lade_und_bereite_auf()

    # 1. Statische Mail
    mail_html = erstelle_mail_html(df)
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(f"{DATA_DIR}/{today_str}_newsletter.html","w",encoding="utf-8") as f:
        f.write(mail_html)
    print(f"💾 Mail-HTML gespeichert")

    # 2. Interaktives Dashboard für GitHub Pages
    os.makedirs(DOCS_DIR, exist_ok=True)
    dashboard_html = erstelle_dashboard(df)
    with open(f"{DOCS_DIR}/index.html","w",encoding="utf-8") as f:
        f.write(dashboard_html)
    print(f"💾 Dashboard gespeichert: {DOCS_DIR}/index.html")

    # 3. Mail versenden
    sende_newsletter(mail_html)
