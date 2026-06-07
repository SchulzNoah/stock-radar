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
PAGES_URL = "https://schulznoah.github.io/stock-radar/"

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
    sp = pd.read_csv(sp_dateien[-1], dtype=str, low_memory=False)
    ns = pd.read_csv(ns_dateien[-1], dtype=str, low_memory=False)
    print(f"SP500: {len(sp)} | NASDAQ: {len(ns)}")
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

    num_cols = ['KGV','KGV_Forward','PEG','EPS_TTM','RSI','Beta',
                'Analyst_Empfehlung','Kursziel','Preis','Verschuldungsgrad']
    for c in num_cols:
        if c in df.columns:
            df[c] = zahl_bereinigen(df[c])

    mrd_cols = ['Marktkapitalisierung_Mrd','Gewinn_Mrd','Umsatz_Mrd']
    for c in mrd_cols:
        if c in df.columns:
            df[c] = mrd_bereinigen(df[c])

    df['Hoch_52W'] = kurs_bereinigen(df['Hoch_52W'])
    df['Tief_52W'] = kurs_bereinigen(df['Tief_52W'])

    pct_cols = [
        'EPS_dieses_Jahr_Pct','EPS_naechstes_Jahr_Pct','EPS_naechste_5J_Pct',
        'Gewinnmarge_Pct','Bruttomarge_Pct','Operative_Marge_Pct',
        'ROE_Pct','ROA_Pct','Short_Float_Pct',
        'Perf_Woche_Pct','Perf_Monat_Pct','Perf_Quartal_Pct','Perf_Halbjahr_Pct',
        'Perf_Jahr_Pct','Perf_YTD_Pct','Perf_3J_Pct','Perf_5J_Pct','Perf_10J_Pct',
    ]
    for c in pct_cols:
        if c in df.columns:
            df[c] = pct_zu_num(df[c])

    df['EPS_vergangene_3J_Pct'] = eps_past_split(df['EPS_vergangene_3_5J'], pos=0)
    df['EPS_vergangene_5J_Pct'] = eps_past_split(df['EPS_vergangene_3_5J'], pos=1)
    df['Analyst_Upside_Pct'] = (
        (df['Kursziel'] - df['Preis']) / df['Preis'] * 100
    ).round(2)

    df = df[df['Preis'].notna() & (df['Preis'] > 0) & df['Unternehmen'].notna()].copy()
    print(f"✅ Master: {len(df)} Unternehmen")
    return df

# ============================================================
# SCORE BERECHNEN – VEREINFACHT & ZUVERLÄSSIG
# ============================================================
# Als Growth-Investor: Fokus auf Wachstum + Qualität + faire Bewertung
# 
# 6 Kategorien mit klarer wirtschaftlicher Logik:
# 1. EPS Wachstum 5J (30%) – wichtigste Metrik für Growth
# 2. Gewinnmarge    (20%) – Qualität des Geschäftsmodells
# 3. Forward KGV    (20%) – Bewertung (niedriger = günstiger)
# 4. KGV            (15%) – Bewertung trailing
# 5. PEG            (10%) – Wachstum relativ zur Bewertung
# 6. Analyst        ( 5%) – Markt-Konsens (1=Strong Buy)
# ============================================================

def berechne_score(df):
    cols_needed = ['Ticker','Unternehmen','Sektor','KGV','KGV_Forward',
                   'EPS_naechste_5J_Pct','Gewinnmarge_Pct','PEG',
                   'Analyst_Empfehlung','Marktkapitalisierung_Mrd']

    s = df[cols_needed].copy()

    # Nur Zeilen mit ausreichend Daten
    s = s[
        s['KGV_Forward'].notna() &
        s['EPS_naechste_5J_Pct'].notna() &
        s['Gewinnmarge_Pct'].notna() &
        (s['KGV_Forward'] > 0) &
        (s['KGV_Forward'] < 200) &
        (s['Marktkapitalisierung_Mrd'].fillna(0) > 0.3)
    ].copy()

    # Caps um Ausreisser zu begrenzen
    s['kgv_c']    = s['KGV'].clip(1, 100).fillna(50)
    s['fkgv_c']   = s['KGV_Forward'].clip(1, 80)
    s['eps5_c']   = s['EPS_naechste_5J_Pct'].clip(-20, 60)
    s['marge_c']  = s['Gewinnmarge_Pct'].clip(-10, 50)
    s['peg_c']    = s['PEG'].clip(0.1, 5).fillna(3)
    s['anl_c']    = s['Analyst_Empfehlung'].clip(1, 5).fillna(3)

    # Normierung 0-100 (percentile rank = robust gegen Ausreisser)
    def pr(series, invert=False):
        r = series.rank(pct=True) * 100
        return 100 - r if invert else r

    s['S_EPS5']    = pr(s['eps5_c'])           # hoch = gut
    s['S_Marge']   = pr(s['marge_c'])           # hoch = gut
    s['S_FKGV']    = pr(s['fkgv_c'],  True)     # niedrig = gut
    s['S_KGV']     = pr(s['kgv_c'],   True)     # niedrig = gut
    s['S_PEG']     = pr(s['peg_c'],   True)     # niedrig = gut
    s['S_Analyst'] = pr(s['anl_c'],   True)     # 1=Strong Buy = gut

    s['Score'] = (
        s['S_EPS5']    * 0.30 +
        s['S_Marge']   * 0.20 +
        s['S_FKGV']    * 0.20 +
        s['S_KGV']     * 0.15 +
        s['S_PEG']     * 0.10 +
        s['S_Analyst'] * 0.05
    ).round(1)

    s = s.sort_values('Score', ascending=False).reset_index(drop=True)
    s['Rang'] = s.index + 1

    return s[[
        'Rang','Ticker','Unternehmen','Sektor','Score',
        'S_EPS5','S_Marge','S_FKGV','S_KGV','S_PEG','S_Analyst',
        'KGV','KGV_Forward','EPS_naechste_5J_Pct',
        'Gewinnmarge_Pct','PEG','Analyst_Empfehlung'
    ]]

# ============================================================
# STATISCHE MAIL
# ============================================================

def erstelle_mail_html(df):
    positiv_pct  = (df['Perf_Monat_Pct'] > 0).mean() * 100
    avg_perf     = df['Perf_Monat_Pct'].mean()
    n_oversold   = int((df['RSI'] < 30).sum())
    n_overbought = int((df['RSI'] > 70).sum())
    n_gesamt     = len(df)

    # Nur positive KGVs für Median verwenden (negative = Verlustjahre → verzerren)
    df_pos_kgv = df.copy()
    df_pos_kgv.loc[df_pos_kgv['KGV_Forward'] <= 0, 'KGV_Forward'] = np.nan

    sektor_df = (
        df[df['Sektor'].notna() & (df['Sektor'] != 'nan')]
        .groupby('Sektor')
        .agg(
            Anzahl         = ('Ticker',         'count'),
            Perf_Monat_Avg = ('Perf_Monat_Pct', 'mean'),
            Perf_Jahr_Avg  = ('Perf_Jahr_Pct',  'mean'),
        )
        .round(2)
        .reset_index()
    )

    # KGV Forward Median separat mit nur positiven Werten berechnen
    kgv_med = (
        df_pos_kgv[df_pos_kgv['Sektor'].notna() & (df_pos_kgv['Sektor'] != 'nan')]
        .groupby('Sektor')['KGV_Forward']
        .median()
        .round(1)
        .rename('KGV_Forward_Median')
    )
    sektor_df = sektor_df.merge(kgv_med, on='Sektor', how='left')
    sektor_df = sektor_df.sort_values('Perf_Monat_Avg', ascending=False).reset_index(drop=True)

    def pfc(val):
        try: return '#2DD4A0' if float(val) >= 0 else '#FF5C72'
        except: return '#8AACC8'

    def sgn(val, dec=1):
        try:
            n = float(val)
            s = fmt_de(abs(n), dec, '%')
            return ('+' if n >= 0 else '−') + s
        except: return '–'

    sektor_rows = ""
    for _, r in sektor_df.iterrows():
        sektor_rows += f"""
        <tr>
          <td style="padding:9px 10px;border-bottom:1px solid #1A2E45;color:#E0EAF5;font-size:13px">{r['Sektor']}</td>
          <td style="padding:9px 10px;border-bottom:1px solid #1A2E45;color:#8AACC8;font-size:13px;text-align:center">{int(r['Anzahl'])}</td>
          <td style="padding:9px 10px;border-bottom:1px solid #1A2E45;color:{pfc(r['Perf_Monat_Avg'])};font-size:13px;text-align:right;font-weight:600">{sgn(r['Perf_Monat_Avg'])}</td>
          <td style="padding:9px 10px;border-bottom:1px solid #1A2E45;color:{pfc(r['Perf_Jahr_Avg'])};font-size:13px;text-align:right;font-weight:600">{sgn(r['Perf_Jahr_Avg'])}</td>
          <td style="padding:9px 10px;border-bottom:1px solid #1A2E45;color:#C8D8E8;font-size:13px;text-align:right">{fmt_de(r['KGV_Forward_Median'],1)}</td>
        </tr>"""

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
          <td style="padding:9px 10px;border-bottom:1px solid #1A2E45;color:{pfc(r.get('EPS_naechste_5J_Pct'))};font-size:12px;text-align:right;font-weight:600">{fmt_de(r.get('EPS_naechste_5J_Pct'),1,'%')}</td>
          <td style="padding:9px 10px;border-bottom:1px solid #1A2E45;color:#C8D8E8;font-size:12px;text-align:right">{fmt_de(r.get('PEG'),2)}</td>
          <td style="padding:9px 10px;border-bottom:1px solid #1A2E45;color:#C8D8E8;font-size:12px;text-align:right">{fmt_de(r.get('Analyst_Empfehlung'),2)}</td>
          <td style="padding:9px 10px;border-bottom:1px solid #1A2E45;color:{pfc(r.get('Gewinnmarge_Pct'))};font-size:12px;text-align:right;font-weight:600">{fmt_de(r.get('Gewinnmarge_Pct'),1,'%')}</td>
        </tr>"""

    avg_color = '#2DD4A0' if avg_perf >= 0 else '#FF5C72'

    return f"""<!DOCTYPE html>
<html lang="de"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Noahs Finanzblog</title></head>
<body style="margin:0;padding:0;background:#080C14;font-family:'Segoe UI',Arial,sans-serif;color:#E0EAF5;">
<div style="max-width:700px;margin:0 auto;padding:20px 16px;">

<div style="background:linear-gradient(135deg,#0D1B2E,#112240);border:1px solid #1E3A5F;border-radius:14px;padding:28px 24px;margin-bottom:16px;">
  <div style="font-size:26px;font-weight:700;color:#E8F4FD;">Noahs Finanzblog <span style="color:#4DB8FF">📈</span></div>
  <div style="color:#7B9BB5;font-size:13px;margin-top:5px;">{datum_de}</div>
</div>

<div style="background:#0D1520;border:1px solid #1A2E45;border-radius:12px;padding:20px;margin-bottom:16px;">
  <div style="font-size:17px;font-weight:700;color:#4DB8FF;margin-bottom:16px;padding-bottom:10px;border-bottom:1px solid #1A2E45;">🌍 Marktübersicht</div>
  <table width="100%" cellpadding="0" cellspacing="0"><tr>
    <td width="20%" style="padding:4px;"><div style="background:#111D2E;border:1px solid #1E3A5F;border-radius:10px;padding:14px 10px;text-align:center;">
      <div style="font-size:20px;font-weight:700;color:{avg_color};">{sgn(avg_perf)}</div>
      <div style="font-size:10px;color:#5A7A95;margin-top:4px;">Ø Perf. 1M</div></div></td>
    <td width="20%" style="padding:4px;"><div style="background:#111D2E;border:1px solid #1E3A5F;border-radius:10px;padding:14px 10px;text-align:center;">
      <div style="font-size:20px;font-weight:700;color:#4DB8FF;">{fmt_de(positiv_pct,1)}%</div>
      <div style="font-size:10px;color:#5A7A95;margin-top:4px;">Im Plus (1M)</div></div></td>
    <td width="20%" style="padding:4px;"><div style="background:#111D2E;border:1px solid #1E3A5F;border-radius:10px;padding:14px 10px;text-align:center;">
      <div style="font-size:20px;font-weight:700;color:#2DD4A0;">{fmt_de(n_oversold,0)}</div>
      <div style="font-size:10px;color:#5A7A95;margin-top:4px;">Überverkauft</div></div></td>
    <td width="20%" style="padding:4px;"><div style="background:#111D2E;border:1px solid #1E3A5F;border-radius:10px;padding:14px 10px;text-align:center;">
      <div style="font-size:20px;font-weight:700;color:#FF5C72;">{fmt_de(n_overbought,0)}</div>
      <div style="font-size:10px;color:#5A7A95;margin-top:4px;">Überkauft</div></div></td>
    <td width="20%" style="padding:4px;"><div style="background:#111D2E;border:1px solid #1E3A5F;border-radius:10px;padding:14px 10px;text-align:center;">
      <div style="font-size:20px;font-weight:700;color:#4DB8FF;">{fmt_de(n_gesamt,0)}</div>
      <div style="font-size:10px;color:#5A7A95;margin-top:4px;">Analysiert</div></div></td>
  </tr></table>
</div>

<div style="background:linear-gradient(135deg,#0D2240,#112E50);border:1px solid #2A5080;border-radius:12px;padding:20px 24px;margin-bottom:16px;text-align:center;">
  <div style="font-size:15px;font-weight:600;color:#E0EAF5;margin-bottom:8px;">📊 Interaktives Dashboard</div>
  <div style="font-size:12px;color:#7B9BB5;margin-bottom:14px;">Sortierbare Tabellen · KGV-Charts · Streudiagramm · Aktien-Radar</div>
  <a href="{PAGES_URL}" target="_blank" style="display:inline-block;background:#4DB8FF;color:#050C18;font-weight:700;font-size:14px;padding:12px 28px;border-radius:8px;text-decoration:none;">→ Zum Dashboard</a>
</div>

<div style="background:#0D1520;border:1px solid #1A2E45;border-radius:12px;padding:20px;margin-bottom:16px;">
  <div style="font-size:17px;font-weight:700;color:#4DB8FF;margin-bottom:16px;padding-bottom:10px;border-bottom:1px solid #1A2E45;">🏭 Sektorperformance</div>
  <div style="overflow-x:auto;"><table width="100%" cellpadding="0" cellspacing="0" style="min-width:420px;">
    <thead><tr style="background:#0A1628;">
      <th style="padding:10px;color:#4DB8FF;font-size:11px;text-align:left;border-bottom:2px solid #1E3A5F;text-transform:uppercase">Sektor</th>
      <th style="padding:10px;color:#4DB8FF;font-size:11px;text-align:center;border-bottom:2px solid #1E3A5F;text-transform:uppercase">Anzahl</th>
      <th style="padding:10px;color:#4DB8FF;font-size:11px;text-align:right;border-bottom:2px solid #1E3A5F;text-transform:uppercase">Perf. 1M</th>
      <th style="padding:10px;color:#4DB8FF;font-size:11px;text-align:right;border-bottom:2px solid #1E3A5F;text-transform:uppercase">Perf. 1J</th>
      <th style="padding:10px;color:#4DB8FF;font-size:11px;text-align:right;border-bottom:2px solid #1E3A5F;text-transform:uppercase">KGV Fwd.</th>
    </tr></thead>
    <tbody>{sektor_rows}</tbody>
  </table></div>
</div>

<div style="background:#0D1520;border:1px solid #1A2E45;border-radius:12px;padding:20px;margin-bottom:16px;">
  <div style="font-size:17px;font-weight:700;color:#4DB8FF;margin-bottom:16px;padding-bottom:10px;border-bottom:1px solid #1A2E45;">⭐ Noahs Aktien-Watchlist</div>
  <div style="overflow-x:auto;"><table width="100%" cellpadding="0" cellspacing="0" style="min-width:700px;">
    <thead><tr style="background:#0A1628;">
      <th style="padding:9px 10px;color:#4DB8FF;font-size:10px;text-align:left;border-bottom:2px solid #1E3A5F;text-transform:uppercase;white-space:nowrap">Ticker</th>
      <th style="padding:9px 10px;color:#4DB8FF;font-size:10px;border-bottom:2px solid #1E3A5F;text-transform:uppercase;white-space:nowrap">Unternehmen</th>
      <th style="padding:9px 10px;color:#4DB8FF;font-size:10px;border-bottom:2px solid #1E3A5F;text-transform:uppercase;white-space:nowrap">Sektor</th>
      <th style="padding:9px 10px;color:#4DB8FF;font-size:10px;text-align:right;border-bottom:2px solid #1E3A5F;text-transform:uppercase;white-space:nowrap">Mkt Cap</th>
      <th style="padding:9px 10px;color:#4DB8FF;font-size:10px;text-align:right;border-bottom:2px solid #1E3A5F;text-transform:uppercase;white-space:nowrap">Gewinn</th>
      <th style="padding:9px 10px;color:#4DB8FF;font-size:10px;text-align:right;border-bottom:2px solid #1E3A5F;text-transform:uppercase;white-space:nowrap">KGV</th>
      <th style="padding:9px 10px;color:#4DB8FF;font-size:10px;text-align:right;border-bottom:2px solid #1E3A5F;text-transform:uppercase;white-space:nowrap">KGV Fwd.</th>
      <th style="padding:9px 10px;color:#4DB8FF;font-size:10px;text-align:right;border-bottom:2px solid #1E3A5F;text-transform:uppercase;white-space:nowrap">EPS 5J</th>
      <th style="padding:9px 10px;color:#4DB8FF;font-size:10px;text-align:right;border-bottom:2px solid #1E3A5F;text-transform:uppercase;white-space:nowrap">PEG</th>
      <th style="padding:9px 10px;color:#4DB8FF;font-size:10px;text-align:right;border-bottom:2px solid #1E3A5F;text-transform:uppercase;white-space:nowrap">Analyst</th>
      <th style="padding:9px 10px;color:#4DB8FF;font-size:10px;text-align:right;border-bottom:2px solid #1E3A5F;text-transform:uppercase;white-space:nowrap">Gewinnmarge</th>
    </tr></thead>
    <tbody>{watchlist_rows}</tbody>
  </table></div>
</div>

<div style="text-align:center;color:#3A5A75;font-size:11px;padding:16px;border-top:1px solid #1A2E45;margin-top:8px;">
  Keine Anlageberatung – Newsletter erstellt von
  <a href="https://www.linkedin.com/in/noah-schulz-971031301/" target="_blank" style="color:#4DB8FF;text-decoration:none;">Noah Schulz</a>
</div>
</div></body></html>"""

# ============================================================
# DASHBOARD (docs/index.html)
# ============================================================

def erstelle_dashboard(df):
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
            x['EPS_naechste_5J_Pct'].rank(pct=True) * 0.35 +
            x['ROE_Pct'].rank(pct=True)              * 0.20 +
            (-x['KGV_Forward']).rank(pct=True)       * 0.20
        )
        .nlargest(200, 'Score')
        [['Ticker','Unternehmen','Sektor','Marktkapitalisierung_Mrd',
          'KGV_Forward','EPS_naechste_5J_Pct','Gewinnmarge_Pct',
          'PEG','Analyst_Empfehlung','Analyst_Upside_Pct']]
    )

    plot_df = df[
        df['KGV'].notna() & df['KGV_Forward'].notna() &
        df['EPS_naechste_5J_Pct'].notna() & df['Sektor'].notna() &
        (df['KGV'] > 0) & (df['KGV'] < 150) &
        (df['KGV_Forward'] > 0) & (df['KGV_Forward'] < 100)
    ][[
        'Ticker','Unternehmen','Sektor',
        'KGV','KGV_Forward',
        'EPS_naechste_5J_Pct','PEG',
        'Perf_Monat_Pct','Perf_Jahr_Pct'
    ]].copy()

    score_df      = berechne_score(df)
    sektoren_list = sorted(df['Sektor'].dropna().unique().tolist())

    # Marktmetriken
    positiv_pct  = round((df['Perf_Monat_Pct'] > 0).mean() * 100, 1)
    avg_perf     = round(df['Perf_Monat_Pct'].mean(), 2)
    n_oversold   = int((df['RSI'] < 30).sum())
    n_overbought = int((df['RSI'] > 70).sum())
    n_gesamt     = len(df)

    def sgn(v, dec=1):
        try:
            n = float(v)
            s = fmt_de(abs(n), dec, '%')
            return ('+' if n >= 0 else '−') + s
        except: return '–'

    avg_color = '#2DD4A0' if avg_perf >= 0 else '#FF5C72'

    # JSON
    wl_json   = watchlist_df.fillna('').to_json(orient='records')
    qs_json   = quality_df.fillna('').to_json(orient='records')
    pd_json   = plot_df.fillna('').to_json(orient='records')
    sc_json   = score_df.fillna('').to_json(orient='records')
    sek_json  = json.dumps(sektoren_list)

    return f"""<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Noahs Finanzblog 📈 – {datum_de}</title>
<style>
:root {{
  --bg:      #080C14;
  --bg2:     #0D1520;
  --bg3:     #111D2E;
  --bg4:     #0A1628;
  --border:  #1A2E45;
  --border2: #1E3A5F;
  --text:    #E8EDF5;
  --text2:   #C8D8E8;
  --text3:   #8AACC8;
  --text4:   #5A7A95;
  --text5:   #3A5A75;
  --accent:  #4DB8FF;
  --pos:     #2DD4A0;
  --neg:     #FF5C72;
  --warn:    #FFB347;
  --th-bg:   #0A1628;
}}
html.light {{
  --bg:      #F0F4F8;
  --bg2:     #FFFFFF;
  --bg3:     #EBF0F7;
  --bg4:     #DDE6F0;
  --border:  #C8D8E8;
  --border2: #A0B8D0;
  --text:    #0D1B2E;
  --text2:   #1E3A5F;
  --text3:   #2A5080;
  --text4:   #4A7090;
  --text5:   #7090A8;
  --accent:  #1A7ACC;
  --pos:     #1A8060;
  --neg:     #CC2040;
  --warn:    #C07000;
  --th-bg:   #DDE6F0;
}}
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:'Segoe UI',sans-serif;background:var(--bg);color:var(--text);padding:16px;max-width:980px;margin:0 auto;transition:background .3s,color .3s}}
/* HEADER */
.header{{background:linear-gradient(135deg,#0D1B2E,#112240);border:1px solid var(--border2);border-radius:16px;padding:26px 24px;margin-bottom:16px;display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:12px}}
html.light .header{{background:linear-gradient(135deg,#C8DCF0,#A8C8E8)}}
.header h1{{font-size:clamp(18px,4vw,28px);font-weight:700;color:var(--text)}}
.header h1 span{{color:var(--accent)}}
.hdt{{color:var(--text3);font-size:13px;margin-top:4px}}
/* DARK/LIGHT TOGGLE */
.toggle-wrap{{display:flex;align-items:center;gap:8px;font-size:12px;color:var(--text3)}}
.toggle{{position:relative;width:44px;height:24px;cursor:pointer}}
.toggle input{{opacity:0;width:0;height:0}}
.slider{{position:absolute;inset:0;background:var(--border2);border-radius:24px;transition:.3s}}
.slider::before{{content:'';position:absolute;width:18px;height:18px;left:3px;top:3px;background:var(--accent);border-radius:50%;transition:.3s}}
input:checked+.slider{{background:#1E3A5F}}
input:checked+.slider::before{{transform:translateX(20px)}}
/* SECTIONS */
.sec{{background:var(--bg2);border:1px solid var(--border);border-radius:12px;padding:20px;margin-bottom:16px}}
.sec-title{{font-size:17px;font-weight:700;color:var(--accent);margin-bottom:14px;padding-bottom:10px;border-bottom:1px solid var(--border);display:flex;align-items:center;gap:8px}}
.sec-sub{{font-size:11px;color:var(--text4);margin-top:-10px;margin-bottom:14px}}
/* METRICS */
.mg{{display:grid;grid-template-columns:repeat(auto-fit,minmax(110px,1fr));gap:10px;margin-bottom:4px}}
.mc{{background:var(--bg3);border:1px solid var(--border2);border-radius:10px;padding:14px 10px;text-align:center}}
.mv{{font-size:clamp(15px,3vw,21px);font-weight:700;color:var(--accent);line-height:1.2}}
.ml{{font-size:10px;color:var(--text4);margin-top:4px}}
.c-pos{{color:var(--pos)!important}}.c-neg{{color:var(--neg)!important}}
/* TABLES */
.tw{{overflow-x:auto;-webkit-overflow-scrolling:touch}}
table.dt{{width:100%;border-collapse:collapse;font-size:12px;min-width:460px}}
table.dt th{{background:var(--th-bg);color:var(--accent);padding:9px 8px;text-align:left;border-bottom:2px solid var(--border2);white-space:nowrap;cursor:pointer;user-select:none;font-weight:700;font-size:10px;text-transform:uppercase;letter-spacing:.5px;transition:background .15s}}
table.dt th:hover{{background:var(--border)}}
table.dt th.asc::after{{content:' ▲';color:var(--accent)}}
table.dt th.desc::after{{content:' ▼';color:var(--accent)}}
table.dt th:not(.asc):not(.desc)::after{{content:' ⇅';color:var(--text4)}}
table.dt td{{padding:8px;border-bottom:1px solid var(--border);color:var(--text2);white-space:nowrap;font-size:12px}}
table.dt tr:hover td{{background:var(--bg3)}}
.tp{{color:var(--accent);font-weight:700}}.tn{{color:var(--text)}}.ts{{color:var(--text3)}}
.td-pos{{color:var(--pos);font-weight:600}}.td-neg{{color:var(--neg);font-weight:600}}
/* PAGINATION */
.pg{{display:flex;justify-content:flex-end;align-items:center;gap:6px;margin-top:10px;font-size:12px;flex-wrap:wrap}}
.pb{{background:var(--bg3);border:1px solid var(--border2);color:var(--text3);padding:4px 10px;border-radius:6px;cursor:pointer;font-size:11px;transition:all .15s}}
.pb:hover,.pb.active{{background:var(--border2);color:var(--accent);border-color:var(--accent)}}
.pi{{color:var(--text4);font-size:11px}}
/* FILTERS */
.fb{{display:flex;flex-wrap:wrap;gap:8px;margin-bottom:14px;padding:14px;background:var(--bg4);border-radius:8px;border:1px solid var(--border)}}
.fg{{display:flex;flex-direction:column;gap:3px;flex:1;min-width:110px}}
.fl{{font-size:10px;color:var(--text4);text-transform:uppercase;letter-spacing:.5px}}
.fi,.fs{{background:var(--bg3);border:1px solid var(--border2);color:var(--text);padding:6px 8px;border-radius:6px;font-size:11px;font-family:inherit;width:100%;transition:border-color .2s}}
.fi:focus,.fs:focus{{outline:none;border-color:var(--accent)}}
.fr{{background:transparent;border:1px solid var(--border2);color:var(--text4);padding:6px 12px;border-radius:6px;cursor:pointer;font-size:11px;align-self:flex-end;transition:all .15s}}
.fr:hover{{border-color:var(--accent);color:var(--accent)}}
/* KGV TOGGLE */
.kgv-toggle{{display:flex;gap:0;margin-bottom:12px;border:1px solid var(--border2);border-radius:8px;overflow:hidden;width:fit-content}}
.kt-btn{{padding:7px 18px;font-size:12px;font-weight:600;cursor:pointer;border:none;background:var(--bg3);color:var(--text3);transition:all .2s;font-family:inherit}}
.kt-btn.active{{background:var(--accent);color:#050C18}}
/* CHART */
.cc{{position:relative;width:100%;margin-top:8px}}
canvas{{border-radius:8px;max-width:100%;display:block}}
.ct{{background:var(--bg2);border:1px solid var(--border2);border-radius:8px;padding:10px 14px;margin-top:10px;font-size:12px;color:var(--text2);display:none}}
/* SEARCH/RADAR */
.sw{{position:relative;margin-bottom:14px}}
.si{{width:100%;background:var(--bg3);border:1px solid var(--border2);color:var(--text);padding:10px 14px;border-radius:8px;font-size:13px;font-family:inherit;transition:border-color .2s}}
.si:focus{{outline:none;border-color:var(--accent)}}
.al{{position:absolute;top:100%;left:0;right:0;background:var(--bg3);border:1px solid var(--border2);border-top:none;border-radius:0 0 8px 8px;z-index:100;max-height:220px;overflow-y:auto;display:none}}
.ai{{padding:9px 14px;cursor:pointer;font-size:12px;color:var(--text2);border-bottom:1px solid var(--border);display:flex;justify-content:space-between;align-items:center}}
.ai:hover{{background:var(--border);color:var(--accent)}}
.ai-ticker{{color:var(--accent);font-weight:700;margin-right:10px}}
.ai-score{{color:var(--text4);font-size:10px}}
#rw{{display:none;margin-top:16px;text-align:center}}
.rt{{font-size:18px;font-weight:700;color:var(--text)}}
.rs{{font-size:13px;color:var(--text3);margin-top:4px}}
/* LEGEND */
.legend{{display:flex;flex-wrap:wrap;gap:10px;margin-bottom:10px;font-size:11px;color:var(--text3)}}
.legend-item{{display:flex;align-items:center;gap:5px}}
.legend-dot{{width:10px;height:10px;border-radius:50%;flex-shrink:0}}
/* SCORE INFO */
.score-info{{background:var(--bg4);border:1px solid var(--border);border-radius:8px;padding:12px 14px;margin-bottom:14px;font-size:12px;color:var(--text3);line-height:1.6}}
.score-info strong{{color:var(--text2)}}
/* ANALYST INFO */
.analyst-badge{{display:inline-flex;align-items:center;gap:4px;padding:3px 8px;border-radius:12px;font-size:10px;font-weight:700}}
/* FOOTER */
.footer{{text-align:center;color:var(--text5);font-size:11px;margin-top:20px;padding:16px;border-top:1px solid var(--border)}}
.footer a{{color:var(--accent);text-decoration:none}}
@media(max-width:600px){{
  body{{padding:10px}}.header{{padding:16px}}.sec{{padding:14px}}
  .fb{{flex-direction:column}}.fg{{min-width:100%}}
  .kgv-toggle{{width:100%}}.kt-btn{{flex:1;text-align:center}}
}}
</style>
</head>
<body>

<!-- HEADER -->
<div class="header">
  <div>
    <h1>Noahs Finanzblog <span>📈</span></h1>
    <div class="hdt">{datum_de}</div>
  </div>
  <div class="toggle-wrap">
    ☀️
    <label class="toggle">
      <input type="checkbox" id="theme-toggle" onchange="toggleTheme()">
      <span class="slider"></span>
    </label>
    🌙
  </div>
</div>

<!-- MARKTÜBERSICHT -->
<div class="sec">
  <div class="sec-title">🌍 Marktübersicht</div>
  <div class="mg">
    <div class="mc"><div class="mv" style="color:{avg_color}">{sgn(avg_perf)}</div><div class="ml">Ø Perf. 1M</div></div>
    <div class="mc"><div class="mv">{fmt_de(positiv_pct,1)}%</div><div class="ml">Im Plus (1M)</div></div>
    <div class="mc"><div class="mv c-pos">{fmt_de(n_oversold,0)}</div><div class="ml">Überverkauft (RSI&lt;30)</div></div>
    <div class="mc"><div class="mv c-neg">{fmt_de(n_overbought,0)}</div><div class="ml">Überkauft (RSI&gt;70)</div></div>
    <div class="mc"><div class="mv">{fmt_de(n_gesamt,0)}</div><div class="ml">Aktien analysiert</div></div>
  </div>
</div>

<!-- WATCHLIST -->
<div class="sec">
  <div class="sec-title">⭐ Noahs Aktien-Watchlist</div>
  <div class="sec-sub">Analyst: 1,0 = Strong Buy · 2,0 = Buy · 3,0 = Hold · 4,0 = Sell · 5,0 = Strong Sell</div>
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
        <th data-col="EPS_naechste_5J_Pct">EPS 5J %</th>
        <th data-col="PEG">PEG</th>
        <th data-col="Analyst_Empfehlung">Analyst (1–5)</th>
        <th data-col="Gewinnmarge_Pct">Gewinnmarge</th>
      </tr></thead>
      <tbody id="tb-wl"></tbody>
    </table>
  </div>
</div>

<!-- QUALITY SCREEN -->
<div class="sec">
  <div class="sec-title">🔬 Quality &amp; Growth Screen</div>
  <div class="sec-sub">Analyst: 1,0 = Strong Buy · 5,0 = Strong Sell · Upside = Differenz zum Analystenkursziel</div>
  <div class="fb">
    <div class="fg"><span class="fl">KGV Fwd. (max)</span><input class="fi" type="number" id="f1" value="40" min="0"></div>
    <div class="fg"><span class="fl">Mkt Cap Mrd. (min)</span><input class="fi" type="number" id="f2" placeholder="z.B. 1"></div>
    <div class="fg"><span class="fl">EPS 5J % (min)</span><input class="fi" type="number" id="f3" value="10"></div>
    <div class="fg"><span class="fl">PEG (max)</span><input class="fi" type="number" id="f4" placeholder="z.B. 3"></div>
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
        <th data-col="EPS_naechste_5J_Pct">EPS 5J %</th>
        <th data-col="Gewinnmarge_Pct">Gewinnmarge</th>
        <th data-col="PEG">PEG</th>
        <th data-col="Analyst_Empfehlung">Analyst (1–5)</th>
        <th data-col="Analyst_Upside_Pct">Upside %</th>
      </tr></thead>
      <tbody id="tb-qs"></tbody>
    </table>
  </div>
  <div class="pg" id="pg-qs"></div>
</div>

<!-- KGV CHART -->
<div class="sec">
  <div class="sec-title">📊 Univariater Dotplot – Kennzahlen im Überblick</div>
  <div style="display:flex;flex-wrap:wrap;gap:10px;align-items:center;margin-bottom:12px">
    <div class="kgv-toggle" id="metric-toggle">
      <button class="kt-btn active" onclick="setMetric('KGV')">KGV</button>
      <button class="kt-btn" onclick="setMetric('KGV_Forward')">Forward KGV</button>
      <button class="kt-btn" onclick="setMetric('PEG')">PEG</button>
      <button class="kt-btn" onclick="setMetric('EPS_naechste_5J_Pct')">EPS 5J %</button>
      <button class="kt-btn" onclick="setMetric('Perf_Monat_Pct')">Perf. 1M</button>
      <button class="kt-btn" onclick="setMetric('Perf_Jahr_Pct')">Perf. 1J</button>
    </div>
    <select class="fs" id="kgv-sf" onchange="renderKGV()" style="width:auto;min-width:170px">
      <option value="">Alle Sektoren</option>
    </select>
  </div>
  <div class="cc"><canvas id="kgvC" height="290"></canvas></div>
  <div class="ct" id="kgv-tt"></div>
</div>

<!-- SCATTER -->
<div class="sec">
  <div class="sec-title">📈 KGV vs. EPS-Wachstum 5J</div>
  <div style="display:flex;gap:8px;align-items:center;margin-bottom:12px;flex-wrap:wrap">
    <select class="fs" id="sc-sf" onchange="renderSC()" style="width:auto;min-width:170px">
      <option value="">Alle Sektoren</option>
    </select>
  </div>
  <div class="cc"><canvas id="scC" height="300"></canvas></div>
  <div class="ct" id="sc-tt"></div>
</div>

<!-- RADAR -->
<div class="sec">
  <div class="sec-title">🎯 Aktien-Score &amp; Radar</div>
  <div class="score-info">
    <strong>Score-Methodik (Growth-Investor-Perspektive):</strong><br>
    EPS Wachstum 5J <strong>30%</strong> · Gewinnmarge <strong>20%</strong> · Forward KGV <strong>20%</strong> · KGV <strong>15%</strong> · PEG <strong>10%</strong> · Analyst <strong>5%</strong><br>
    Alle Kategorien werden per Perzentil-Rang normiert (0–100). Score = gewichteter Durchschnitt.
  </div>
  <div class="sw">
    <input class="si" id="rs" type="text" placeholder="🔍 Unternehmen suchen – z.B. NVIDIA oder NV ..."
           oninput="onRS()" onblur="setTimeout(hideAC,200)">
    <div class="al" id="ac"></div>
  </div>
  <div id="rw">
    <div class="rt" id="rt"></div>
    <div class="rs" id="rsub"></div>
    <canvas id="rc" width="400" height="400" style="display:block;margin:16px auto 0"></canvas>
  </div>
</div>

<div class="footer">
  Keine Anlageberatung – Newsletter erstellt von
  <a href="https://www.linkedin.com/in/noah-schulz-971031301/" target="_blank">Noah Schulz</a>
</div>

<script>
// ============================================================
// DATA
// ============================================================
const WL  = {wl_json};
const QS  = {qs_json};
const PD  = {pd_json};
const SD  = {sc_json};
const SEK = {sek_json};

// ============================================================
// THEME TOGGLE
// ============================================================
function toggleTheme(){{
  const isDark = !document.getElementById('theme-toggle').checked;
  document.documentElement.classList.toggle('light', !isDark);
  localStorage.setItem('theme', isDark ? 'dark' : 'light');
  renderKGV(); renderSC();
}}
(function(){{
  const t = localStorage.getItem('theme');
  if(t === 'light'){{
    document.documentElement.classList.add('light');
    document.getElementById('theme-toggle').checked = true;
  }}
}})();

// ============================================================
// FORMAT HELPERS
// ============================================================
function fDE(v,d=2,sfx=''){{
  if(v===''||v===null||v===undefined||isNaN(+v))return'–';
  return(+v).toLocaleString('de-DE',{{minimumFractionDigits:d,maximumFractionDigits:d}})+sfx;
}}
function fP(v,d=1){{return fDE(v,d,'%')}}
function fM(v,d=1){{return fDE(v,d,' Mrd.')}}
function sgn(v,d=1){{
  if(v===''||isNaN(+v))return'–';
  const n=+v; return(n>=0?'+':'−')+fDE(Math.abs(n),d,'%');
}}
function cc(v){{if(v===''||isNaN(+v))return''; return +v>=0?'td-pos':'td-neg';}}
function getCSSVar(name){{return getComputedStyle(document.documentElement).getPropertyValue(name).trim();}}

// ============================================================
// SORTABLE TABLE FACTORY
// ============================================================
function mkTbl(tblId, tbId, data, renderRow, defaultSortCol='', defaultAsc=false){{
  const tbl=document.getElementById(tblId);
  const tb=document.getElementById(tbId);
  let st={{c:defaultSortCol,a:defaultAsc}};
  function draw(rows){{tb.innerHTML=rows.map(renderRow).join('');}}
  function sortData(){{
    if(!st.c)return;
    data.sort((a,b)=>{{
      const av=isNaN(+a[st.c])?String(a[st.c]||''):+a[st.c];
      const bv=isNaN(+b[st.c])?String(b[st.c]||''):+b[st.c];
      return st.a?(av<bv?-1:av>bv?1:0):(av>bv?-1:av<bv?1:0);
    }});
  }}
  tbl.querySelectorAll('th[data-col]').forEach(th=>{{
    th.addEventListener('click',()=>{{
      const col=th.dataset.col;
      if(st.c===col)st.a=!st.a; else{{st.c=col;st.a=true;}}
      tbl.querySelectorAll('th').forEach(t=>t.classList.remove('asc','desc'));
      th.classList.add(st.a?'asc':'desc');
      sortData(); draw(data);
    }});
  }});
  sortData();
  // Set initial sort indicator
  if(st.c){{
    const th=tbl.querySelector(`th[data-col="${{st.c}}"]`);
    if(th)th.classList.add(st.a?'asc':'desc');
  }}
  draw(data);
}}

// WATCHLIST
mkTbl('tbl-wl','tb-wl',[...WL],r=>`<tr>
  <td class="tp">${{r.Ticker||'–'}}</td>
  <td class="tn">${{(r.Unternehmen||'–').substring(0,24)}}</td>
  <td class="ts">${{(r.Sektor||'–').substring(0,18)}}</td>
  <td style="text-align:right">${{fM(r.Marktkapitalisierung_Mrd)}}</td>
  <td style="text-align:right">${{fM(r.Gewinn_Mrd,2)}}</td>
  <td style="text-align:right">${{fDE(r.KGV,1)}}</td>
  <td style="text-align:right">${{fDE(r.KGV_Forward,1)}}</td>
  <td style="text-align:right" class="${{cc(r.EPS_naechste_5J_Pct)}}">${{fP(r.EPS_naechste_5J_Pct)}}</td>
  <td style="text-align:right">${{fDE(r.PEG,2)}}</td>
  <td style="text-align:right">${{fDE(r.Analyst_Empfehlung,2)}}</td>
  <td style="text-align:right" class="${{cc(r.Gewinnmarge_Pct)}}">${{fP(r.Gewinnmarge_Pct)}}</td>
</tr>`,'Marktkapitalisierung_Mrd',false);

// ============================================================
// QUALITY SCREEN + FILTER + PAGINATION
// ============================================================
let qPage=1; const PS=10;
let qSort={{c:'EPS_naechste_5J_Pct',a:false}};

function getQF(){{
  const kmax=+document.getElementById('f1').value||Infinity;
  const mmin=+document.getElementById('f2').value||-Infinity;
  const emin=+document.getElementById('f3').value||-Infinity;
  const pmax=+document.getElementById('f4').value||Infinity;
  const gmin=+document.getElementById('f6').value||-Infinity;
  return QS.filter(r=>
    (+r.KGV_Forward||Infinity)<=kmax &&
    (+r.Marktkapitalisierung_Mrd||-Infinity)>=mmin &&
    (+r.EPS_naechste_5J_Pct||-Infinity)>=emin &&
    (+r.PEG||Infinity)<=pmax &&
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
    <td class="tn">${{(r.Unternehmen||'–').substring(0,24)}}</td>
    <td class="ts">${{(r.Sektor||'–').substring(0,18)}}</td>
    <td style="text-align:right">${{fM(r.Marktkapitalisierung_Mrd)}}</td>
    <td style="text-align:right">${{fDE(r.KGV_Forward,1)}}</td>
    <td style="text-align:right" class="${{cc(r.EPS_naechste_5J_Pct)}}">${{fP(r.EPS_naechste_5J_Pct)}}</td>
    <td style="text-align:right" class="${{cc(r.Gewinnmarge_Pct)}}">${{fP(r.Gewinnmarge_Pct)}}</td>
    <td style="text-align:right">${{fDE(r.PEG,2)}}</td>
    <td style="text-align:right">${{fDE(r.Analyst_Empfehlung,2)}}</td>
    <td style="text-align:right" class="${{cc(r.Analyst_Upside_Pct)}}">${{sgn(r.Analyst_Upside_Pct)}}</td>
  </tr>`).join('');
  const pg=document.getElementById('pg-qs');
  pg.innerHTML='';
  const sp=document.createElement('span');sp.className='pi';
  const s=(qPage-1)*PS+1,e=Math.min(qPage*PS,data.length);
  sp.textContent=`${{s}}–${{e}} von ${{data.length}}`;pg.appendChild(sp);
  for(let i=1;i<=tp;i++){{
    const b=document.createElement('button');b.className='pb'+(i===qPage?' active':'');
    b.textContent=i;b.onclick=(p=>()=>{{qPage=p;renderQ();}})(i);pg.appendChild(b);
  }}
}}
document.getElementById('tbl-qs').querySelectorAll('th[data-col]').forEach(th=>{{
  th.addEventListener('click',()=>{{
    const c=th.dataset.col;
    if(qSort.c===c)qSort.a=!qSort.a; else{{qSort.c=c;qSort.a=false;}}
    document.getElementById('tbl-qs').querySelectorAll('th').forEach(t=>t.classList.remove('asc','desc'));
    th.classList.add(qSort.a?'asc':'desc');qPage=1;renderQ();
  }});
}});
['f1','f2','f3','f4','f6'].forEach(id=>{{
  document.getElementById(id).addEventListener('input',()=>{{qPage=1;renderQ();}});
}});
function resetF(){{
  document.getElementById('f1').value=40;
  ['f2','f4'].forEach(id=>document.getElementById(id).value='');
  document.getElementById('f3').value=10;document.getElementById('f6').value=10;
  qPage=1;renderQ();
}}
renderQ();

// ============================================================
// SEKTOR SELECTS
// ============================================================
['kgv-sf','sc-sf'].forEach(id=>{{
  const s=document.getElementById(id);
  SEK.forEach(sk=>{{const o=document.createElement('option');o.value=sk;o.textContent=sk;s.appendChild(o);}});
}});

// ============================================================
// UNIVARIATER DOTPLOT – MEHRERE METRIKEN
// ============================================================
const METRIC_CFG = {{
  'KGV':               {{ label:'KGV (Trailing)',       color:'rgba(77,184,255,0.65)',  lc:'#4DB8FF', cap:[0,150],  pct:false, dec:1, suffix:'' }},
  'KGV_Forward':       {{ label:'Forward KGV',          color:'rgba(45,212,160,0.65)',  lc:'#2DD4A0', cap:[0,100],  pct:false, dec:1, suffix:'' }},
  'PEG':               {{ label:'PEG Ratio',            color:'rgba(255,179,71,0.65)',  lc:'#FFB347', cap:[0,5],    pct:false, dec:2, suffix:'' }},
  'EPS_naechste_5J_Pct':{{ label:'EPS Wachstum 5J (%)', color:'rgba(164,120,255,0.65)',lc:'#A478FF', cap:[-20,60], pct:true,  dec:1, suffix:'%' }},
  'Perf_Monat_Pct':    {{ label:'Performance 1M (%)',   color:'rgba(255,92,114,0.65)', lc:'#FF5C72', cap:[-50,100],pct:true,  dec:1, suffix:'%' }},
  'Perf_Jahr_Pct':     {{ label:'Performance 1J (%)',   color:'rgba(255,215,0,0.65)',  lc:'#FFD700', cap:[-80,300],pct:true,  dec:1, suffix:'%' }},
}};

let currentMetric = 'KGV';
let kgvData = [];
let kgvScales = {{}};

function setMetric(m) {{
  currentMetric = m;
  document.querySelectorAll('#metric-toggle .kt-btn').forEach((b,i) => {{
    b.classList.toggle('active', b.textContent.trim() === Object.values(METRIC_CFG)[i]?.label.split(' ')[0] || b.onclick.toString().includes(`'${{m}}'`));
  }});
  // Einfachere Variante: alle inaktiv, dann das passende aktiv
  document.querySelectorAll('#metric-toggle .kt-btn').forEach(b => {{
    b.classList.remove('active');
    if(b.getAttribute('onclick') && b.getAttribute('onclick').includes(`'${{m}}'`)) b.classList.add('active');
  }});
  document.getElementById('kgv-tt').style.display = 'none';
  renderKGV();
}}

function renderKGV() {{
  const cfg = METRIC_CFG[currentMetric];
  const sek = document.getElementById('kgv-sf').value;
  const col = currentMetric;

  kgvData = PD.filter(d => {{
    if(!d[col] && d[col] !== 0) return false;
    const v = +d[col];
    if(isNaN(v)) return false;
    if(sek && d.Sektor !== sek) return false;
    return v >= cfg.cap[0] && v <= cfg.cap[1];
  }});

  const vals = kgvData.map(d => +d[col]);
  if(!vals.length) return;

  // Für KGV/PEG: Mittelwert und Median nur über positive Werte
  // (negative KGVs = Verlustunternehmen → verzerren den Durchschnitt stark)
  const posMetrics = ['KGV','KGV_Forward','PEG'];
  const valsForStats = posMetrics.includes(col)
    ? vals.filter(v => v > 0)
    : vals;
  const statN = valsForStats.length || 1;
  const avg = valsForStats.reduce((a,b) => a+b, 0) / statN;
  const sorted_vals = [...valsForStats].sort((a,b) => a-b);
  const med = sorted_vals[Math.floor(sorted_vals.length / 2)];

  const cv = document.getElementById('kgvC');
  const ctx = cv.getContext('2d');
  const W = cv.parentElement.offsetWidth || 820, H = 290;
  cv.width = W; cv.height = H;

  const bg    = getCSSVar('--bg2')    || '#0D1520';
  const gridC = getCSSVar('--border') || '#1A2E45';
  const textC = getCSSVar('--text4')  || '#5A7A95';

  ctx.fillStyle = bg; ctx.fillRect(0, 0, W, H);

  const P = {{t:32, r:20, b:40, l:58}};
  const pw = W - P.l - P.r, ph = H - P.t - P.b;

  // Y-Skala: Min/Max aus Daten + 10% Puffer
  const minVal = Math.min(...vals);
  const maxVal = Math.max(...vals);
  const range  = maxVal - minVal || 1;
  const yMin   = minVal - range * 0.08;
  const yMax   = maxVal + range * 0.08;
  const ySc    = v => P.t + ph - ((v - yMin) / (yMax - yMin)) * ph;

  // Grid + Y-Achse (5 Linien)
  for(let g = 0; g <= 5; g++) {{
    const v = yMin + (yMax - yMin) * g / 5;
    const y = ySc(v);
    ctx.strokeStyle = gridC; ctx.lineWidth = 1;
    ctx.beginPath(); ctx.moveTo(P.l, y); ctx.lineTo(P.l + pw, y); ctx.stroke();
    ctx.fillStyle = textC; ctx.font = '10px Segoe UI,sans-serif'; ctx.textAlign = 'right';
    ctx.fillText(fDE(v, cfg.dec) + cfg.suffix, P.l - 5, y + 3);
  }}

  // Nulllinie bei Perf-Metriken
  if(cfg.pct && yMin < 0 && yMax > 0) {{
    const y0 = ySc(0);
    ctx.strokeStyle = getCSSVar('--text4') || '#5A7A95';
    ctx.lineWidth = 1.5; ctx.setLineDash([4,3]);
    ctx.beginPath(); ctx.moveTo(P.l, y0); ctx.lineTo(P.l + pw, y0); ctx.stroke();
    ctx.setLineDash([]);
  }}

  // Punkte sortiert nach Wert (X-Achse = Rang)
  const sorted = [...kgvData].sort((a,b) => +a[col] - +b[col]);
  kgvScales = {{sorted, col, ySc, pw, ph, P, yMin, yMax, W, H, cfg}};

  sorted.forEach((d, i) => {{
    const x = P.l + (i / (sorted.length - 1 || 1)) * pw;
    const y = ySc(+d[col]);
    ctx.beginPath(); ctx.arc(x, y, 3.5, 0, Math.PI * 2);
    ctx.fillStyle = cfg.color; ctx.fill();
  }});

  // Mittelwert + Median Linien
  function hl(val, lbl, dash) {{
    const y = ySc(val);
    ctx.strokeStyle = cfg.lc; ctx.lineWidth = 1.8;
    ctx.setLineDash(dash || []);
    ctx.beginPath(); ctx.moveTo(P.l, y); ctx.lineTo(P.l + pw, y); ctx.stroke();
    ctx.setLineDash([]);
    ctx.fillStyle = cfg.lc; ctx.font = 'bold 9px Segoe UI,sans-serif';
    ctx.textAlign = 'left';
    ctx.fillText(lbl + ': ' + fDE(val, cfg.dec) + cfg.suffix, P.l + 4, y - 3);
  }}
  hl(avg, 'Ø', []);
  hl(med, 'Median', [6, 4]);

  // Titel + Info
  ctx.fillStyle = cfg.lc; ctx.font = 'bold 11px Segoe UI,sans-serif';
  ctx.textAlign = 'center';
  ctx.fillText(cfg.label, P.l + pw / 2, P.t - 10);

  // Info-Zeile: bei KGV/PEG Hinweis auf positive-only Stats
  const posMetricsInfo = ['KGV','KGV_Forward','PEG'];
  const statsNote = posMetricsInfo.includes(col)
    ? ` | Ø & Median: nur positive Werte (${{valsForStats.length}})`
    : '';
  ctx.fillStyle = textC; ctx.font = '10px Segoe UI,sans-serif';
  ctx.fillText(
    `${{kgvData.length}} Unternehmen | ${{sek || 'Alle Sektoren'}}${{statsNote}} | Klick für Details`,
    P.l + pw / 2, H - 5
  );
}}

// CLICK → Tooltip
document.getElementById('kgvC').addEventListener('click', function(e) {{
  if(!kgvScales.sorted || !kgvScales.sorted.length) return;
  const rect = this.getBoundingClientRect();
  const mx = (e.clientX - rect.left) * (this.width / rect.width);
  const my = (e.clientY - rect.top)  * (this.height / rect.height);
  const {{sorted, col, ySc, pw, P, cfg}} = kgvScales;

  let cl = null, md = Infinity;
  sorted.forEach((d, i) => {{
    const x = P.l + (i / (sorted.length - 1 || 1)) * pw;
    const y = ySc(+d[col]);
    const dist = Math.sqrt((x - mx) ** 2 + (y - my) ** 2);
    if(dist < md) {{ md = dist; cl = d; }}
  }});

  const tt = document.getElementById('kgv-tt');
  if(md < 18 && cl) {{
    tt.style.display = 'block';
    // Alle verfügbaren Metriken anzeigen
    const extras = [
      cl.KGV           ? `KGV: <strong>${{fDE(cl.KGV,1)}}</strong>` : '',
      cl.KGV_Forward   ? `Fwd KGV: <strong>${{fDE(cl.KGV_Forward,1)}}</strong>` : '',
      cl.EPS_naechste_5J_Pct !== '' ? `EPS 5J: <strong>${{fDE(cl.EPS_naechste_5J_Pct,1)}}%</strong>` : '',
      cl.PEG           ? `PEG: <strong>${{fDE(cl.PEG,2)}}</strong>` : '',
      cl.Perf_Monat_Pct !== '' ? `Perf 1M: <strong>${{fDE(cl.Perf_Monat_Pct,1)}}%</strong>` : '',
      cl.Perf_Jahr_Pct  !== '' ? `Perf 1J: <strong>${{fDE(cl.Perf_Jahr_Pct,1)}}%</strong>` : '',
    ].filter(Boolean).join(' &nbsp;|&nbsp; ');

    tt.innerHTML = `
      <div style="margin-bottom:6px">
        <strong style="color:var(--accent);font-size:13px">${{cl.Ticker}}</strong>
        &nbsp;<span style="color:var(--text)">${{cl.Unternehmen || ''}}</span>
        &nbsp;<span style="color:var(--text3);font-size:11px">(${{cl.Sektor || ''}})</span>
      </div>
      <div style="font-size:11px;color:var(--text2)">${{extras}}</div>
      <div style="margin-top:4px;font-size:10px;color:var(--accent)">
        ${{cfg.label}}: <strong style="font-size:13px">${{fDE(+cl[col], cfg.dec)}}${{cfg.suffix}}</strong>
      </div>`;
  }} else {{
    tt.style.display = 'none';
  }}
}});

// ============================================================
// SCATTER CHART
// ============================================================
let scScales={{}};

function renderSC(){{
  const sek=document.getElementById('sc-sf').value;
  const data=PD.filter(d=>(!sek||d.Sektor===sek)&&+d.KGV>0&&+d.KGV<100&&+d.EPS_naechste_5J_Pct>-50&&+d.EPS_naechste_5J_Pct<100);
  scScales={{data}};

  const cv=document.getElementById('scC');
  const ctx=cv.getContext('2d');
  const W=cv.parentElement.offsetWidth||820,H=300;
  cv.width=W;cv.height=H;

  const bg=getCSSVar('--bg2')||'#0D1520';
  const gridC=getCSSVar('--border')||'#1A2E45';
  const textC=getCSSVar('--text4')||'#5A7A95';

  ctx.fillStyle=bg;ctx.fillRect(0,0,W,H);
  const P={{t:28,r:20,b:48,l:54}};
  const pw=W-P.l-P.r,ph=H-P.t-P.b;
  if(!data.length)return;

  const xv=data.map(d=>+d.KGV),yv=data.map(d=>+d.EPS_naechste_5J_Pct);
  const xmx=Math.min(Math.ceil(Math.max(...xv)*1.1/10)*10,100);
  const ymn=Math.min(Math.floor(Math.min(...yv)/5)*5,0);
  const ymx=Math.ceil(Math.max(...yv)*1.1/5)*5;
  const xs=v=>P.l+(v/xmx)*pw;
  const ys=v=>P.t+ph-((v-ymn)/(ymx-ymn))*ph;
  scScales={{data,xs,ys}};

  for(let i=0;i<=5;i++){{
    const xval=xmx*i/5,yval=ymn+(ymx-ymn)*i/5;
    ctx.strokeStyle=gridC;ctx.lineWidth=1;
    ctx.beginPath();ctx.moveTo(xs(xval),P.t);ctx.lineTo(xs(xval),P.t+ph);ctx.stroke();
    ctx.beginPath();ctx.moveTo(P.l,ys(yval));ctx.lineTo(P.l+pw,ys(yval));ctx.stroke();
    ctx.fillStyle=textC;ctx.font='9px Segoe UI,sans-serif';
    ctx.textAlign='center';ctx.fillText(fDE(xval,0),xs(xval),P.t+ph+13);
    ctx.textAlign='right';ctx.fillText(fDE(yval,0)+'%',P.l-4,ys(yval)+3);
  }}

  const SC={{
    'Technology':'#4DB8FF','Healthcare':'#2DD4A0','Financials':'#FFB347',
    'Consumer Cyclical':'#FF7BAC','Energy':'#FFD700','Industrials':'#A78BFA',
    'Consumer Defensive':'#6EE7B7','Utilities':'#93C5FD',
    'Communication Services':'#F472B6','Basic Materials':'#D4A574','Real Estate':'#FCA5A5'
  }};

  data.forEach(d=>{{
    ctx.beginPath();ctx.arc(xs(+d.KGV),ys(+d.EPS_naechste_5J_Pct),4,0,Math.PI*2);
    ctx.fillStyle=(SC[d.Sektor]||'#4DB8FF')+'99';ctx.fill();
  }});

  ctx.fillStyle=textC;ctx.font='10px Segoe UI,sans-serif';ctx.textAlign='center';
  ctx.fillText('KGV (Trailing)',P.l+pw/2,H-5);
  ctx.save();ctx.translate(14,P.t+ph/2);ctx.rotate(-Math.PI/2);
  ctx.fillText('EPS-Wachstum 5J (%)',0,0);ctx.restore();
  ctx.fillText(`${{data.length}} Unternehmen | ${{sek||'Alle Sektoren'}}`,P.l+pw/2,P.t-8);
}}

document.getElementById('scC').addEventListener('mousemove',function(e){{
  if(!scScales.data||!scScales.data.length)return;
  const rect=this.getBoundingClientRect();
  const mx=(e.clientX-rect.left)*(this.width/rect.width);
  const my=(e.clientY-rect.top)*(this.height/rect.height);
  const {{data,xs,ys}}=scScales;
  let cl=null,md=Infinity;
  data.forEach(d=>{{
    const dx=xs(+d.KGV)-mx,dy=ys(+d.EPS_naechste_5J_Pct)-my;
    const dist=Math.sqrt(dx*dx+dy*dy);
    if(dist<md){{md=dist;cl=d;}}
  }});
  const tt=document.getElementById('sc-tt');
  if(md<18&&cl){{
    tt.style.display='block';
    tt.innerHTML=`<strong style="color:var(--accent)">${{cl.Ticker}}</strong> – ${{cl.Unternehmen||''}}
      &nbsp;|&nbsp; KGV: <strong>${{fDE(cl.KGV,1)}}</strong>
      &nbsp;|&nbsp; EPS 5J: <strong>${{fDE(cl.EPS_naechste_5J_Pct,1)}}%</strong>
      &nbsp;|&nbsp; <span style="color:var(--text3)">${{cl.Sektor||''}}</span>`;
  }}else{{tt.style.display='none';}}
}});

// ============================================================
// RADAR / SCORE
// ============================================================
function onRS(){{
  const q=document.getElementById('rs').value.toLowerCase().trim();
  const ac=document.getElementById('ac');
  if(q.length<1){{ac.style.display='none';return;}}
  const m=SD.filter(d=>
    d.Ticker.toLowerCase().includes(q)||(d.Unternehmen||'').toLowerCase().includes(q)
  ).slice(0,8);
  if(!m.length){{ac.style.display='none';return;}}
  ac.innerHTML=m.map(d=>`
    <div class="ai" onclick="selR('${{d.Ticker}}')">
      <span><span class="ai-ticker">${{d.Ticker}}</span>${{d.Unternehmen||''}}</span>
      <span class="ai-score">Score: ${{d.Score}} | Rang ${{d.Rang}}</span>
    </div>`).join('');
  ac.style.display='block';
}}
function hideAC(){{document.getElementById('ac').style.display='none';}}
function selR(tk){{
  const d=SD.find(r=>r.Ticker===tk);
  if(!d)return;
  document.getElementById('rs').value=d.Ticker+' – '+(d.Unternehmen||'');
  hideAC();
  drawRadar(d);
}}

function drawRadar(d){{
  // Erst sichtbar machen, dann im nächsten Frame rendern
  // (damit der Canvas die korrekte Größe hat)
  const rw = document.getElementById('rw');
  rw.style.display = 'block';

  const sc     = +d.Score;
  const scCol  = sc >= 70 ? '#2DD4A0' : sc >= 45 ? '#FFB347' : '#FF5C72';

  document.getElementById('rt').textContent =
    `${{d.Rang}}. ${{d.Unternehmen}} (${{d.Ticker}})`;
  document.getElementById('rsub').innerHTML =
    `Score: <span style="color:${{scCol}};font-weight:700;font-size:20px">${{sc}}/100</span>
     &nbsp;·&nbsp; Rang <strong>${{d.Rang}}</strong> von ${{SD.length}} Unternehmen`;

  // Kurze Verzögerung damit display:block wirkt bevor Canvas gezeichnet wird
  requestAnimationFrame(() => _paintRadar(d, sc, scCol));
}}

function _paintRadar(d, sc, scCol) {{
  const cv  = document.getElementById('rc');
  const ctx = cv.getContext('2d');

  // Canvas-Größe dynamisch an Container anpassen
  const container = cv.parentElement;
  const size = Math.min(container.offsetWidth || 400, 420);
  cv.width  = size;
  cv.height = size;
  ctx.clearRect(0, 0, size, size);

  const W = size, H = size;
  const cx = W/2, cy = H/2 + 8, R = Math.min(W,H) * 0.30;

  const lbls=[
    'EPS 5J Wachstum','Gewinnmarge','Forward KGV','KGV (trailing)','PEG','Analyst'
  ];
  const keys=['S_EPS5','S_Marge','S_FKGV','S_KGV','S_PEG','S_Analyst'];
  const vals=keys.map(k=>Math.max(0,Math.min(100,+d[k]||0)));
  const N=lbls.length;

  // Hintergrund
  ctx.fillStyle=getCSSVar('--bg2')||'#0D1520';
  ctx.fillRect(0,0,W,H);

  // Ringe
  for(let ring=1;ring<=5;ring++){{
    const r=R*ring/5;
    ctx.strokeStyle=getCSSVar('--border')||'#1A2E45';
    ctx.lineWidth=1;ctx.beginPath();
    for(let i=0;i<=N;i++){{
      const a=(i/N)*Math.PI*2-Math.PI/2;
      i===0?ctx.moveTo(cx+r*Math.cos(a),cy+r*Math.sin(a))
           :ctx.lineTo(cx+r*Math.cos(a),cy+r*Math.sin(a));
    }}
    ctx.closePath();ctx.stroke();
    // Ring-Labels
    ctx.fillStyle=getCSSVar('--text4')||'#5A7A95';
    ctx.font='8px Segoe UI,sans-serif';ctx.textAlign='center';
    ctx.fillText((ring*20).toString(),cx+3,cy-r+3);
  }}

  // Achsen
  for(let i=0;i<N;i++){{
    const a=(i/N)*Math.PI*2-Math.PI/2;
    ctx.strokeStyle=getCSSVar('--border')||'#1A2E45';ctx.lineWidth=1;
    ctx.beginPath();ctx.moveTo(cx,cy);
    ctx.lineTo(cx+R*Math.cos(a),cy+R*Math.sin(a));ctx.stroke();
  }}

  // Datenfläche
  ctx.beginPath();
  vals.forEach((v,i)=>{{
    const a=(i/N)*Math.PI*2-Math.PI/2,r=R*v/100;
    i===0?ctx.moveTo(cx+r*Math.cos(a),cy+r*Math.sin(a))
         :ctx.lineTo(cx+r*Math.cos(a),cy+r*Math.sin(a));
  }});
  ctx.closePath();
  ctx.fillStyle=scCol+'2A';ctx.fill();
  ctx.strokeStyle=scCol;ctx.lineWidth=2.5;ctx.stroke();

  // Datenpunkte
  vals.forEach((v,i)=>{{
    const a=(i/N)*Math.PI*2-Math.PI/2,r=R*v/100;
    ctx.beginPath();ctx.arc(cx+r*Math.cos(a),cy+r*Math.sin(a),5,0,Math.PI*2);
    ctx.fillStyle=scCol;ctx.fill();
    ctx.strokeStyle=getCSSVar('--bg2')||'#0D1520';ctx.lineWidth=1.5;ctx.stroke();
  }});

  // Labels außen
  lbls.forEach((lb,i)=>{{
    const a=(i/N)*Math.PI*2-Math.PI/2;
    const lR=R+36;
    const lx=cx+lR*Math.cos(a),ly=cy+lR*Math.sin(a);
    ctx.fillStyle=getCSSVar('--text2')||'#C8D8E8';
    ctx.font='bold 10px Segoe UI,sans-serif';
    ctx.textAlign='center';ctx.textBaseline='middle';
    ctx.fillText(lb,lx,ly-8);
    ctx.fillStyle=scCol;ctx.font='9px Segoe UI,sans-serif';
    ctx.fillText(fDE(vals[i],0)+'/100',lx,ly+6);
  }});

  // Score in der Mitte
  ctx.textAlign='center';ctx.textBaseline='middle';
  ctx.fillStyle=scCol;ctx.font=`bold 32px Segoe UI,sans-serif`;
  ctx.fillText(sc.toString(),cx,cy-10);
  ctx.fillStyle=getCSSVar('--text3')||'#8AACC8';
  ctx.font='11px Segoe UI,sans-serif';
  ctx.fillText('Score',cx,cy+14);
}}

// INIT
setMetric('KGV');
renderSC();
</script>
</body>
</html>"""

# ============================================================
# MAIL VERSENDEN
# ============================================================

def sende_newsletter(html):
    if not all([MAIL_SENDER, MAIL_PASSWORD, MAIL_RECEIVER]):
        print("❌ Mail-Credentials fehlen."); return False
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"Noahs Finanzblog 📈 – {datum_de}"
    msg["From"]    = f"Noahs Finanzblog <{MAIL_SENDER}>"
    msg["To"]      = MAIL_RECEIVER
    msg.attach(MIMEText(html, "html"))
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as s:
            s.login(MAIL_SENDER, MAIL_PASSWORD)
            s.sendmail(MAIL_SENDER, MAIL_RECEIVER, msg.as_string())
        print(f"✅ Mail versendet an {MAIL_RECEIVER}"); return True
    except Exception as e:
        print(f"❌ Fehler: {e}"); return False

# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":
    print(f"📧 Newsletter: {datum_de}")
    df = lade_und_bereite_auf()

    mail_html = erstelle_mail_html(df)
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(f"{DATA_DIR}/{today_str}_newsletter.html","w",encoding="utf-8") as f:
        f.write(mail_html)
    print("💾 Mail-HTML gespeichert")

    os.makedirs(DOCS_DIR, exist_ok=True)
    dashboard = erstelle_dashboard(df)
    with open(f"{DOCS_DIR}/index.html","w",encoding="utf-8") as f:
        f.write(dashboard)
    print("💾 Dashboard: docs/index.html")

    sende_newsletter(mail_html)
