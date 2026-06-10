import pandas as pd
import numpy as np
import smtplib
import os, re, glob, json, shutil
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

MONATE_DE = {1:"Januar",2:"Februar",3:"März",4:"April",5:"Mai",6:"Juni",
             7:"Juli",8:"August",9:"September",10:"Oktober",11:"November",12:"Dezember"}
datum_de  = f"{today.day}. {MONATE_DE[today.month]} {today.year}"
PAGES_URL = "https://schulznoah.github.io/stock-radar/"

WATCHLIST_TICKERS = [
    "AAPL","MSFT","NVDA","GOOGL","AMZN","META","TSLA",
    "AMD","ASML","VRT","AVGO","TSM","MELI","WDC",
    "SAP","MRVL","MU","AAON","BE"
]

# ============================================================
# HILFSFUNKTIONEN
# ============================================================
def pct_zu_num(s):
    return pd.to_numeric(s.astype(str).str.extract(r'(-?[0-9]+\.?[0-9]*)')[0], errors='coerce')

def zahl_bereinigen(s):
    x = s.astype(str).str.strip().replace(['-','NA','N/A','','nan'], np.nan)
    return pd.to_numeric(x.str.extract(r'(-?[0-9]+\.?[0-9]*)')[0], errors='coerce')

def mrd_bereinigen(s):
    x    = s.astype(str).str.strip()
    w    = pd.to_numeric(x.str.extract(r'(-?[0-9]+\.?[0-9]*)')[0], errors='coerce')
    e    = x.str.extract(r'([TBMKtbmk])$')[0]
    r    = w.copy()
    r[e.isin(['T','t'])] = w[e.isin(['T','t'])] * 1000
    r[e.isin(['B','b'])] = w[e.isin(['B','b'])]
    r[e.isin(['M','m'])] = w[e.isin(['M','m'])] / 1000
    r[e.isin(['K','k'])] = w[e.isin(['K','k'])] / 1_000_000
    return r

def kurs_bereinigen(s):
    return pd.to_numeric(s.astype(str).str.extract(r'^(-?[0-9]+\.?[0-9]*)')[0], errors='coerce')

def eps_split(s, pos=0):
    def ex(x):
        z = re.findall(r'-?[0-9]+\.?[0-9]*', str(x))
        return float(z[pos]) if len(z) > pos else np.nan
    return s.apply(ex)

def fmt(v, d=2, sfx=""):
    try:
        if pd.isna(v): return "–"
        f = f"{float(v):,.{d}f}".replace(",","X").replace(".",",").replace("X",".")
        return f"{f}{sfx}"
    except: return "–"

# ============================================================
# DATEN LADEN
# ============================================================
def lade_daten():
    sp_f = sorted(glob.glob(f"{DATA_DIR}/*_SP500_fundamentals.csv"))
    ns_f = sorted(glob.glob(f"{DATA_DIR}/*_NASDAQ_fundamentals.csv"))
    if not sp_f or not ns_f: raise FileNotFoundError("Keine CSVs gefunden!")
    sp = pd.read_csv(sp_f[-1], dtype=str, low_memory=False)
    ns = pd.read_csv(ns_f[-1], dtype=str, low_memory=False)
    print(f"SP500: {len(sp)} | NASDAQ: {len(ns)}")
    df = pd.concat([ns, sp[~sp['Ticker'].isin(ns['Ticker'])]], ignore_index=True)
    df = df.rename(columns={
        'Company':'Unternehmen','Sector':'Sektor','Industry':'Branche',
        'Market Cap':'Marktkapitalisierung_Mrd','P/E':'KGV','Forward P/E':'KGV_Forward',
        'EPS (ttm)':'EPS_TTM','EPS this Y':'EPS_dieses_Jahr_Pct',
        'EPS next Y Percentage':'EPS_naechstes_Jahr_Pct',
        'EPS next 5Y':'EPS_naechste_5J_Pct','EPS past 3/5Y':'EPS_vergangene_3_5J',
        'PEG':'PEG','Income':'Gewinn_Mrd','Sales':'Umsatz_Mrd',
        'Profit Margin':'Gewinnmarge_Pct','Gross Margin':'Bruttomarge_Pct',
        'Oper. Margin':'Operative_Marge_Pct','ROE':'ROE_Pct','ROA':'ROA_Pct',
        'Perf Week':'Perf_Woche_Pct','Perf Month':'Perf_Monat_Pct',
        'Perf Quarter':'Perf_Quartal_Pct','Perf Half Y':'Perf_Halbjahr_Pct',
        'Perf Year':'Perf_Jahr_Pct','Perf YTD':'Perf_YTD_Pct',
        'Perf 3Y':'Perf_3J_Pct','Perf 5Y':'Perf_5J_Pct','Perf 10Y':'Perf_10J_Pct',
        '52W High':'Hoch_52W','52W Low':'Tief_52W','RSI (14)':'RSI',
        'Recom':'Analyst_Empfehlung','Target Price':'Kursziel',
        'Short Float':'Short_Float_Pct','Price':'Preis','Beta':'Beta',
        'Debt/Eq':'Verschuldungsgrad',
    })
    for c in ['KGV','KGV_Forward','PEG','EPS_TTM','RSI','Beta',
              'Analyst_Empfehlung','Kursziel','Preis','Verschuldungsgrad']:
        if c in df.columns: df[c] = zahl_bereinigen(df[c])
    for c in ['Marktkapitalisierung_Mrd','Gewinn_Mrd','Umsatz_Mrd']:
        if c in df.columns: df[c] = mrd_bereinigen(df[c])
    df['Hoch_52W'] = kurs_bereinigen(df['Hoch_52W'])
    df['Tief_52W'] = kurs_bereinigen(df['Tief_52W'])
    for c in ['EPS_dieses_Jahr_Pct','EPS_naechstes_Jahr_Pct','EPS_naechste_5J_Pct',
              'Gewinnmarge_Pct','Bruttomarge_Pct','Operative_Marge_Pct','ROE_Pct','ROA_Pct',
              'Short_Float_Pct','Perf_Woche_Pct','Perf_Monat_Pct','Perf_Quartal_Pct',
              'Perf_Halbjahr_Pct','Perf_Jahr_Pct','Perf_YTD_Pct','Perf_3J_Pct',
              'Perf_5J_Pct','Perf_10J_Pct']:
        if c in df.columns: df[c] = pct_zu_num(df[c])
    df['EPS_vergangene_3J_Pct'] = eps_split(df['EPS_vergangene_3_5J'], 0)
    df['EPS_vergangene_5J_Pct'] = eps_split(df['EPS_vergangene_3_5J'], 1)
    df['Analyst_Upside_Pct']    = ((df['Kursziel']-df['Preis'])/df['Preis']*100).round(2)
    df = df[df['Preis'].notna()&(df['Preis']>0)&df['Unternehmen'].notna()].copy()
    print(f"Master: {len(df)} Unternehmen"); return df

# ============================================================
# SCORE CALCULATIONS
# ============================================================
def berechne_score(df):
    s = df[['Ticker','Unternehmen','Sektor','KGV','KGV_Forward',
            'EPS_naechste_5J_Pct','Gewinnmarge_Pct','PEG',
            'Analyst_Empfehlung','Marktkapitalisierung_Mrd']].copy()
    
    # Für das Ranking und Scoring bereinigen wir temporär unvollständige Daten
    s['kgv_c']  = s['KGV'].clip(1,100).fillna(50)
    s['fkgv_c'] = s['KGV_Forward'].clip(1,80).fillna(40)
    s['eps5_c'] = s['EPS_naechste_5J_Pct'].clip(-20,60).fillna(5)
    s['mg_c']   = s['Gewinnmarge_Pct'].clip(-10,50).fillna(5)
    s['peg_c']  = s['PEG'].clip(0.1,5).fillna(3)
    s['anl_c']  = s['Analyst_Empfehlung'].clip(1,5).fillna(3)
    
    def pr(x, inv=False): 
        r = x.rank(pct=True) * 100
        return 100 - r if inv else r

    s['S_EPS5']    = pr(s['eps5_c'])
    s['S_Marge']   = pr(s['mg_c'])
    s['S_FKGV']    = pr(s['fkgv_c'], True)
    s['S_KGV']     = pr(s['kgv_c'], True)
    s['S_PEG']     = pr(s['peg_c'], True)
    s['S_Analyst'] = pr(s['anl_c'], True)
    
    s['Score'] = (s['S_EPS5']*0.30 + s['S_Marge']*0.20 + s['S_FKGV']*0.20 +
                  s['S_KGV']*0.15  + s['S_PEG']*0.10   + s['S_Analyst']*0.05).round(1)
    s = s.sort_values('Score', ascending=False).reset_index(drop=True)
    s['Rang'] = s.index + 1
    return s[['Rang','Ticker','Unternehmen','Sektor','Score',
               'S_EPS5','S_Marge','S_FKGV','S_KGV','S_PEG','S_Analyst',
               'KGV','KGV_Forward','EPS_naechste_5J_Pct','Gewinnmarge_Pct',
               'PEG','Analyst_Empfehlung','Marktkapitalisierung_Mrd']]

# ============================================================
# STATISCHE MAIL (UNCHANGED CORE)
# ============================================================
def erstelle_mail(df):
    def pfc(v):
        try: return '#2DD4A0' if float(v)>=0 else '#FF5C72'
        except: return '#8AACC8'
    def sgn(v,d=1):
        try:
            n=float(v); s=fmt(abs(n),d,'%')
            return('+' if n>=0 else '−')+s
        except: return '–'

    avg_perf    = df['Perf_Monat_Pct'].mean()
    positiv_pct = (df['Perf_Monat_Pct']>0).mean()*100
    n_over      = int((df['RSI']<30).sum())
    n_over2     = int((df['RSI']>70).sum())
    n_ges       = len(df)
    avg_col     = '#2DD4A0' if avg_perf>=0 else '#FF5C72'

    df_pk = df.copy(); df_pk.loc[df_pk['KGV_Forward']<=0,'KGV_Forward']=np.nan
    sek = (df[df['Sektor'].notna()&(df['Sektor']!='nan')]
           .groupby('Sektor')
           .agg(Anzahl=('Ticker','count'),
                Pm=('Perf_Monat_Pct','mean'),
                Pj=('Perf_Jahr_Pct','mean'))
           .round(2).reset_index())
    km  = (df_pk[df_pk['Sektor'].notna()&(df_pk['Sektor']!='nan')]
           .groupby('Sektor')['KGV_Forward'].median().round(1)
           .rename('KM'))
    sek = sek.merge(km,on='Sektor',how='left').sort_values('Pm',ascending=False)

    sr = "".join(f"""<tr>
      <td style="padding:9px 10px;border-bottom:1px solid #1A2E45;color:#E0EAF5;font-size:13px">{r['Sektor']}</td>
      <td style="padding:9px 10px;border-bottom:1px solid #1A2E45;color:#8AACC8;font-size:13px;text-align:center">{int(r['Anzahl'])}</td>
      <td style="padding:9px 10px;border-bottom:1px solid #1A2E45;color:{pfc(r['Pm'])};font-size:13px;text-align:right;font-weight:600">{sgn(r['Pm'])}</td>
      <td style="padding:9px 10px;border-bottom:1px solid #1A2E45;color:{pfc(r['Pj'])};font-size:13px;text-align:right;font-weight:600">{sgn(r['Pj'])}</td>
      <td style="padding:9px 10px;border-bottom:1px solid #1A2E45;color:#C8D8E8;font-size:13px;text-align:right">{fmt(r['KM'],1)}</td>
    </tr>""" for _,r in sek.iterrows())

    wl = df[df['Ticker'].isin(WATCHLIST_TICKERS)].sort_values('Marktkapitalisierung_Mrd',ascending=False,na_position='last')
    wr = "".join(f"""<tr>
      <td style="padding:9px 10px;border-bottom:1px solid #1A2E45;color:#4DB8FF;font-size:12px;font-weight:700">{r.get('Ticker','–')}</td>
      <td style="padding:9px 10px;border-bottom:1px solid #1A2E45;color:#E0EAF5;font-size:12px">{str(r.get('Unternehmen','–'))[:22]}</td>
      <td style="padding:9px 10px;border-bottom:1px solid #1A2E45;color:#8AACC8;font-size:11px">{str(r.get('Sektor','–'))[:16]}</td>
      <td style="padding:9px 10px;border-bottom:1px solid #1A2E45;color:#C8D8E8;font-size:12px;text-align:right">{fmt(r.get('Marktkapitalisierung_Mrd'),1,' Mrd.')}</td>
      <td style="padding:9px 10px;border-bottom:1px solid #1A2E45;color:#C8D8E8;font-size:12px;text-align:right">{fmt(r.get('Gewinn_Mrd'),2,' Mrd.')}</td>
      <td style="padding:9px 10px;border-bottom:1px solid #1A2E45;color:#C8D8E8;font-size:12px;text-align:right">{fmt(r.get('KGV'),1)}</td>
      <td style="padding:9px 10px;border-bottom:1px solid #1A2E45;color:#C8D8E8;font-size:12px;text-align:right">{fmt(r.get('KGV_Forward'),1)}</td>
      <td style="padding:9px 10px;border-bottom:1px solid #1A2E45;color:{pfc(r.get('EPS_naechste_5J_Pct'))};font-size:12px;text-align:right;font-weight:600">{fmt(r.get('EPS_naechste_5J_Pct'),1,'%')}</td>
      <td style="padding:9px 10px;border-bottom:1px solid #1A2E45;color:#C8D8E8;font-size:12px;text-align:right">{fmt(r.get('PEG'),2)}</td>
      <td style="padding:9px 10px;border-bottom:1px solid #1A2E45;color:#C8D8E8;font-size:12px;text-align:right">{fmt(r.get('Analyst_Empfehlung'),2)}</td>
      <td style="padding:9px 10px;border-bottom:1px solid #1A2E45;color:{pfc(r.get('Gewinnmarge_Pct'))};font-size:12px;text-align:right;font-weight:600">{fmt(r.get('Gewinnmarge_Pct'),1,'%')}</td>
    </tr>""" for _,r in wl.iterrows())

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
      <div style="font-size:20px;font-weight:700;color:{avg_col};">{sgn(avg_perf)}</div>
      <div style="font-size:10px;color:#5A7A95;margin-top:4px;">Ø Perf. 1M</div></div></td>
    <td width="20%" style="padding:4px;"><div style="background:#111D2E;border:1px solid #1E3A5F;border-radius:10px;padding:14px 10px;text-align:center;">
      <div style="font-size:20px;font-weight:700;color:#4DB8FF;">{fmt(positiv_pct,1)}%</div>
      <div style="font-size:10px;color:#5A7A95;margin-top:4px;">Im Plus (1M)</div></div></td>
    <td width="20%" style="padding:4px;"><div style="background:#111D2E;border:1px solid #1E3A5F;border-radius:10px;padding:14px 10px;text-align:center;">
      <div style="font-size:20px;font-weight:700;color:#2DD4A0;">{fmt(n_over,0)}</div>
      <div style="font-size:10px;color:#5A7A95;margin-top:4px;">Überverkauft</div></div></td>
    <td width="20%" style="padding:4px;"><div style="background:#111D2E;border:1px solid #1E3A5F;border-radius:10px;padding:14px 10px;text-align:center;">
      <div style="font-size:20px;font-weight:700;color:#FF5C72;">{fmt(n_over2,0)}</div>
      <div style="font-size:10px;color:#5A7A95;margin-top:4px;">Überkauft</div></div></td>
    <td width="20%" style="padding:4px;"><div style="background:#111D2E;border:1px solid #1E3A5F;border-radius:10px;padding:14px 10px;text-align:center;">
      <div style="font-size:20px;font-weight:700;color:#4DB8FF;">{fmt(n_ges,0)}</div>
      <div style="font-size:10px;color:#5A7A95;margin-top:4px;">Analysiert</div></div></td>
  </tr></table>
</div>
<div style="background:linear-gradient(135deg,#0D2240,#112E50);border:1px solid #2A5080;border-radius:12px;padding:20px 24px;margin-bottom:16px;text-align:center;">
  <div style="font-size:15px;font-weight:600;color:#E0EAF5;margin-bottom:8px;">📊 Interaktives Dashboard</div>
  <div style="font-size:12px;color:#7B9BB5;margin-bottom:14px;">Sortierbare Tabellen · Dotplot · Streudiagramm · Aktien-Radar</div>
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
      <th style="padding:10px;color:#4DB8FF;font-size:11px;text-align:right;border-bottom:2px solid #1E3A5F;text-transform:uppercase">KGV Fwd. (Med.)</th>
    </tr></thead>
    <tbody>{sr}</tbody>
  </table></div>
</div>
<div style="background:#0D1520;border:1px solid #1A2E45;border-radius:12px;padding:20px;margin-bottom:16px;">
  <div style="font-size:17px;font-weight:700;color:#4DB8FF;margin-bottom:4px;padding-bottom:10px;border-bottom:1px solid #1A2E45;">⭐ Noahs Aktien-Watchlist</div>
  <div style="overflow-x:auto;"><table width="100%" cellpadding="0" cellspacing="0" style="min-width:700px;">
    <thead><tr style="background:#0A1628;">
      <th style="padding:9px 10px;color:#4DB8FF;font-size:10px;border-bottom:2px solid #1E3A5F;text-transform:uppercase">Ticker</th>
      <th style="padding:9px 10px;color:#4DB8FF;font-size:10px;border-bottom:2px solid #1E3A5F;text-transform:uppercase">Unternehmen</th>
      <th style="padding:9px 10px;color:#4DB8FF;font-size:10px;border-bottom:2px solid #1E3A5F;text-transform:uppercase">Sektor</th>
      <th style="padding:9px 10px;color:#4DB8FF;font-size:10px;border-bottom:2px solid #1E3A5F;text-transform:uppercase;text-align:right">Mkt Cap</th>
      <th style="padding:9px 10px;color:#4DB8FF;font-size:10px;border-bottom:2px solid #1E3A5F;text-transform:uppercase;text-align:right">Gewinn</th>
      <th style="padding:9px 10px;color:#4DB8FF;font-size:10px;border-bottom:2px solid #1E3A5F;text-transform:uppercase;text-align:right">KGV</th>
      <th style="padding:9px 10px;color:#4DB8FF;font-size:10px;border-bottom:2px solid #1E3A5F;text-transform:uppercase;text-align:right">KGV Fwd</th>
      <th style="padding:9px 10px;color:#4DB8FF;font-size:10px;border-bottom:2px solid #1E3A5F;text-transform:uppercase;text-align:right">EPS 5J</th>
      <th style="padding:9px 10px;color:#4DB8FF;font-size:10px;border-bottom:2px solid #1E3A5F;text-transform:uppercase;text-align:right">PEG</th>
      <th style="padding:9px 10px;color:#4DB8FF;font-size:10px;border-bottom:2px solid #1E3A5F;text-transform:uppercase;text-align:right">Analyst</th>
      <th style="padding:9px 10px;color:#4DB8FF;font-size:10px;border-bottom:2px solid #1E3A5F;text-transform:uppercase;text-align:right">Marge</th>
    </tr></thead>
    <tbody>{wr}</tbody>
  </table></div>
</div>
</div></body></html>"""

# ============================================================
# INTERAKTIVES DASHBOARD GENERATOR
# ============================================================
def erstelle_dashboard(df):
    # Generiere bereinigten Datensatz für das Web-Dashboard
    sd = berechne_score(df)
    
    # 1. Alle Unternehmen für den Quality & Growth Screen behalten (auch die mit NA)
    # Erzeuge ein Mapping, um Ränge/Scores für gematchte Ticker zu ergänzen
    score_lookup = sd.set_index('Ticker')['Score'].to_dict()
    rang_lookup = sd.set_index('Ticker')['Rang'].to_dict()
    
    qs_list = []
    for _, r in df.iterrows():
        t = r['Ticker']
        qs_list.append({
            'Ticker': t,
            'Unternehmen': str(r['Unternehmen']),
            'Sektor': str(r['Sektor']),
            'Marktkapitalisierung_Mrd': float(r['Marktkapitalisierung_Mrd']) if pd.notna(r['Marktkapitalisierung_Mrd']) else '',
            'KGV_Forward': float(r['KGV_Forward']) if pd.notna(r['KGV_Forward']) else '',
            'EPS_naechste_5J_Pct': float(r['EPS_naechste_5J_Pct']) if pd.notna(r['EPS_naechste_5J_Pct']) else '',
            'PEG': float(r['PEG']) if pd.notna(r['PEG']) else '',
            'Analyst_Empfehlung': float(r['Analyst_Empfehlung']) if pd.notna(r['Analyst_Empfehlung']) else '',
            'Gewinnmarge_Pct': float(r['Gewinnmarge_Pct']) if pd.notna(r['Gewinnmarge_Pct']) else '',
            'Analyst_Upside_Pct': float(r['Analyst_Upside_Pct']) if pd.notna(r['Analyst_Upside_Pct']) else '',
            'Score': float(score_lookup.get(t, 0)) if t in score_lookup else '',
            'Rang': int(rang_lookup.get(t, 9999)) if t in rang_lookup else ''
        })

    # Sektorliste extrahieren
    sektoren = sorted([str(s) for s in df['Sektor'].dropna().unique() if str(s) != 'nan'])
    
    # Aggregierte Daten für den globalen Zustand
    avg_perf = float(df['Perf_Monat_Pct'].mean())
    positiv_pct = float((df['Perf_Monat_Pct'] > 0).mean() * 100)
    n_over = int((df['RSI'] < 30).sum())
    n_over2 = int((df['RSI'] > 70).sum())
    n_ges = len(df)
    avg_col = 'var(--pos)' if avg_perf >= 0 else 'var(--neg)'

    # JavaScript JSON-Datenstrukturen injizieren
    js_data = f"""
    const DATUM = "{datum_de}";
    const AVG_PERF = {avg_perf};
    const POS_PCT = {positiv_pct};
    const N_OVER = {n_over};
    const N_OVER2 = {n_over2};
    const N_GES = {n_ges};
    const AVG_COL = "{avg_col}";
    const SEK = {json.dumps(sektoren, ensure_ascii=False)};
    const SD = {sd.to_json(orient='records', ensure_ascii=False)};
    const QS_DATA = {json.dumps(qs_list, ensure_ascii=False)};
    const WL_TICKERS = {json.dumps(WATCHLIST_TICKERS)};
    """

    html = """<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<link rel="icon" type="image/png" href="assets/logo.png">
<title>Duisburg Analytica | Executive Stock Radar</title>
<style>
:root {
  --bg: #060913; 
  --bg2: #0b1326; 
  --bg3: #111e38; 
  --bg4: #080f20;
  --brd: #16294a; 
  --brd2: #223e70; 
  --tx: #f0f5fa; 
  --tx2: #b5cbfa; 
  --tx3: #6c8ec7; 
  --tx4: #486594;
  --ac: #38bdf8; 
  --ac-rgb: 56,189,248;
  --pos: #10b981; 
  --neg: #f43f5e; 
  --warn: #f59e0b;
  --thbg: #e2e8f0;
}
html.light {
  --bg: #f4f7fc; 
  --bg2: #ffffff; 
  --bg3: #e2ecf8; 
  --bg4: #f8fafc;
  --brd: #cbd5e1; 
  --brd2: #94a3b8; 
  --tx: #0f172a; 
  --tx2: #334155; 
  --tx3: #64748b; 
  --tx4: #94a3b8;
  --ac: #0284c7; 
  --ac-rgb: 2,132,199;
  --pos: #059669; 
  --neg: #dc2626; 
  --warn: #d97706;
}
*{box-sizing:border-box;margin:0;padding:0}
body {
  font-family: 'Segoe UI', -apple-system, BlinkMacSystemFont, Roboto, sans-serif;
  background: var(--bg);
  color: var(--tx);
  padding: 40px 20px;
  min-height: 100vh;
  transition: background .3s, color .3s;
}
/* Premium Glassmorphism Wrapper */
.app-container {
  max-width: 1300px;
  margin: 0 auto;
  background: rgba(11, 19, 38, 0.4);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  border: 1px solid var(--brd);
  border-radius: 24px;
  padding: 32px;
  box-shadow: 0 20px 50px rgba(0, 0, 0, 0.3);
}
html.light .app-container {
  background: rgba(255, 255, 255, 0.7);
  box-shadow: 0 20px 40px rgba(148, 163, 184, 0.15);
}
/* HEADER UI */
.hdr {
  background: linear-gradient(135deg, rgba(13, 27, 46, 0.8), rgba(18, 37, 64, 0.8));
  border: 1px solid var(--brd2);
  border-radius: 20px;
  padding: 24px 32px;
  margin-bottom: 32px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 16px;
  box-shadow: 0 8px 32px rgba(56, 189, 248, 0.05);
}
html.light .hdr {
  background: linear-gradient(135deg, #e0f2fe, #bae6fd);
  border: 1px solid #7dd3fc;
}
.hdr-left { display: flex; align-items: center; gap: 20px; }
.hdr-logo {
  height: 60px; width: auto; object-fit: contain;
  filter: drop-shadow(0 4px 12px rgba(56, 189, 248, 0.3));
}
.hdr-text h1 { font-size: 28px; font-weight: 800; letter-spacing: -0.5px; }
.hdr-text h1 span { color: var(--ac); }
.hdr-text .sub { color: var(--tx3); font-size: 13px; margin-top: 4px; font-weight: 500; }

/* TOGGLE BUTTON SWITCH */
.tgl-wrap { display: flex; align-items: center; gap: 10px; font-size: 14px; font-weight: 600; color: var(--tx2); }
.tgl { position: relative; width: 54px; height: 28px; cursor: pointer; }
.tgl input { opacity: 0; width: 0; height: 0; }
.tgl-slider {
  position: absolute; inset: 0; background: var(--bg3);
  border-radius: 28px; transition: .3s; border: 1px solid var(--brd);
}
.tgl-slider::before {
  content: '🌙'; position: absolute; width: 22px; height: 22px;
  left: 2px; top: 2px; background: var(--bg2); border-radius: 50%;
  display: flex; align-items: center; justify-content: center; font-size: 12px;
  transition: .3s; box-shadow: 0 2px 6px rgba(0,0,0,0.4);
}
html.light .tgl-slider::before { content: '☀️'; background: #fff; }
.tgl input:checked + .tgl-slider { background: var(--ac); }
.tgl input:checked + .tgl-slider::before { transform: translateX(26px); }

/* GRID SYSTEMS */
.grid-top { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 16px; margin-bottom: 32px; }
.mv-box {
  background: var(--bg2); border: 1px solid var(--brd); border-radius: 16px;
  padding: 20px; text-align: center; transition: transform 0.2s, box-shadow 0.2s;
}
.mv-box:hover { transform: translateY(-2px); box-shadow: 0 8px 24px rgba(0,0,0,0.2); }
.mv-v { font-size: 24px; font-weight: 700; margin-bottom: 4px; }
.mv-l { font-size: 12px; color: var(--tx3); font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px; }

.layout-visuals { display: grid; grid-template-columns: 1fr 1fr; gap: 32px; margin-bottom: 32px; }
@media(max-width:950px){ .layout-visuals { grid-template-columns: 1fr; } }

/* CARDS */
.sec {
  background: var(--bg2); border: 1px solid var(--brd); border-radius: 20px;
  padding: 24px; margin-bottom: 32px; box-shadow: 0 4px 20px rgba(0,0,0,0.05);
}
.sec-title { font-size: 18px; font-weight: 700; color: var(--tx); margin-bottom: 6px; display: flex; align-items: center; gap: 8px; }
.sec-sub { font-size: 13px; color: var(--tx3); margin-bottom: 20px; line-height: 1.5; }

/* PREMIUM FILTERS */
.fb { display: flex; flex-wrap: wrap; gap: 16px; background: var(--bg4); padding: 16px; border-radius: 14px; border: 1px solid var(--brd); margin-bottom: 20px; }
.fg { display: flex; flex-direction: column; gap: 6px; }
.fl { font-size: 11px; font-weight: 700; color: var(--tx3); text-transform: uppercase; letter-spacing: 0.5px; }
.fi, .fs {
  background: var(--bg2); border: 1px solid var(--brd); color: var(--tx);
  padding: 8px 12px; border-radius: 8px; font-size: 13px; font-weight: 500; outline: none; transition: border-color 0.2s;
}
.fi:focus, .fs:focus { border-color: var(--ac); }
.fr {
  align-self: flex-end; background: var(--bg3); border: 1px solid var(--brd); color: var(--tx2);
  padding: 8px 16px; border-radius: 8px; font-size: 13px; font-weight: 600; cursor: pointer; transition: all 0.2s;
}
.fr:hover { background: var(--ac); color: #000; border-color: var(--ac); }

/* TABLES WITH SCROLLBARS */
.tw { overflow-x: auto; border-radius: 12px; border: 1px solid var(--brd); }
.dt { width: 100%; border-collapse: collapse; font-size: 13px; text-align: left; }
.dt th {
  background: var(--bg3); color: var(--tx2); font-weight: 600; padding: 12px 14px;
  cursor: pointer; user-select: none; border-bottom: 2px solid var(--brd); white-space: nowrap;
}
.dt th:hover { color: var(--tx); background: var(--brd); }
.dt th.asc::after { content: " ▴"; color: var(--ac); }
.dt th.desc::after { content: " ▾"; color: var(--ac); }
.dt td { padding: 10px 14px; border-bottom: 1px solid var(--brd); color: var(--tx2); white-space: nowrap; }
.dt tr:last-child td { border-bottom: none; }
.dt tr:hover td { background: var(--bg4); color: var(--tx); }

/* BADGES FOR STRATEGIES */
.badge-rec { padding: 4px 8px; border-radius: 6px; font-size: 11px; font-weight: 700; text-transform: uppercase; text-align: center; display: inline-block; }
.rec-sb { background: rgba(16, 185, 129, 0.15); color: #059669; border: 1px solid rgba(16, 185, 129, 0.3); } /* Dark green text */
html.light .rec-sb { color: #064e3b; background: rgba(16, 185, 129, 0.25); }
.rec-b  { background: rgba(52, 211, 153, 0.15); color: #34d399; border: 1px solid rgba(52, 211, 153, 0.3); } /* Light green */
html.light .rec-b { color: #047857; background: rgba(52, 211, 153, 0.25); }
.rec-h  { background: rgba(148, 163, 184, 0.15); color: var(--tx3); border: 1px solid rgba(148, 163, 184, 0.3); } /* Grey / Yellow */
.rec-s  { background: rgba(245, 158, 11, 0.15); color: #f59e0b; border: 1px solid rgba(245, 158, 11, 0.3); } /* Orange */
.rec-ss { background: rgba(244, 63, 94, 0.15); color: #f43f5e; border: 1px solid rgba(244, 63, 94, 0.3); } /* Red */

.td-pos { color: var(--pos) !important; font-weight: 600; }
.td-neg { color: var(--neg) !important; font-weight: 600; }
.ticker-link { color: var(--ac); font-weight: 700; cursor: pointer; text-decoration: none; }
.ticker-link:hover { text-decoration: underline; }

/* GRAPHICS & INTERACTIVE OVERLAYS */
.canvas-holder { position: relative; background: var(--bg4); border-radius: 14px; border: 1px solid var(--brd); padding: 16px; display: flex; justify-content: center; align-items: center; min-height: 300px; }
canvas { max-width: 100%; height: auto; display: block; }

/* PREMIUM OVERLAY REAL-TIME TOOLTIP */
.radar-overlay-tooltip {
  position: absolute; top: 12px; right: 12px; background: rgba(8, 15, 32, 0.9);
  border: 1px solid var(--brd2); border-radius: 10px; padding: 12px 14px; font-size: 12px;
  box-shadow: 0 8px 24px rgba(0,0,0,0.5); display: none; z-index: 10; min-width: 190px;
  pointer-events: none; backdrop-filter: blur(4px);
}
html.light .radar-overlay-tooltip { background: rgba(255, 255, 255, 0.95); border-color: var(--brd); box-shadow: 0 4px 16px rgba(0,0,0,0.1); }
.r-tt-row { display: flex; justify-content: space-between; margin-top: 4px; gap: 12px; }
.r-tt-lbl { color: var(--tx3); font-weight: 500; }
.r-tt-val { color: var(--tx); font-weight: 700; text-align: right; }

/* RADAR TARGET WRAPPER */
.radar-meta-block { text-align: center; margin-bottom: 12px; }
#rtitle { font-size: 16px; font-weight: 700; color: var(--ac); }
#rsub { font-size: 12px; color: var(--tx3); margin-top: 2px; }

/* FOOTER */
.ftr { text-align: center; margin-top: 4px; padding-top: 20px; border-top: 1px solid var(--brd); font-size: 12px; color: var(--tx4); font-weight: 500; }
.ftr a { color: var(--ac); text-decoration: none; font-weight: 600; }
</style>
</head>
<body>
<div class="app-container">

  <div class="hdr">
    <div class="hdr-left">
      <img src="assets/logo.png" class="hdr-logo" alt="Logo" onerror="this.style.display='none'">
      <div class="hdr-text">
        <h1>Duisburg Analytica <span>Stock Radar</span></h1>
        <div class="sub">Generiert am <span id="hdr-datum"></span> · Institutional Grade Data Pipeline</div>
      </div>
    </div>
    <div class="hdr-right">
      <div class="tgl-wrap">
        <span>Light Mode</span>
        <label class="tgl">
          <input type="checkbox" id="thm">
          <span class="tgl-slider"></span>
        </label>
      </div>
    </div>
  </div>

  <div class="grid-top">
    <div class="mv-box"><div class="mv-v" id="mv-p">--</div><div class="mv-l">Ø Perf. 1M</div></div>
    <div class="mv-box"><div class="mv-v" id="mv-pp">--</div><div class="mv-l">Im Plus (1M)</div></div>
    <div class="mv-box"><div class="mv-v" id="mv-ov">--</div><div class="mv-l">RSI Überverkauft</div></div>
    <div class="mv-box"><div class="mv-v" id="mv-ob">--</div><div class="mv-l">RSI Überkauft</div></div>
    <div class="mv-box"><div class="mv-v" id="mv-n">--</div><div class="mv-l">Unternehmen</div></div>
  </div>

  <div class="layout-visuals">
    
    <div class="sec" style="display:flex; flex-direction:column; justify-content:space-between;">
      <div>
        <div class="sec-title">🎯 Interaktiver Quant-Radar</div>
        <div class="sec-sub">Klicke auf ein beliebiges Ticker-Symbol in den Tabellen unten, um das hexagonale Faktorenprofil zu laden. Hover über das Chart für Rohkennzahlen.</div>
      </div>
      <div id="radar-wrapper" style="display:none; margin: auto 0;">
        <div class="radar-meta-block">
          <div id="rtitle">Ticker</div>
          <div id="rsub">Score</div>
        </div>
        <div class="canvas-holder">
          <div class="radar-overlay-tooltip" id="radar-tt">
            <div style="font-weight:700; border-bottom:1px solid var(--brd); padding-bottom:4px; margin-bottom:4px; color:var(--ac);" id="r-tt-name">Metric</div>
            <div class="r-tt-row"><span class="r-tt-lbl">EPS Wachstum 5J:</span><span class="r-tt-val" id="tt-eps"></span></div>
            <div class="r-tt-row"><span class="r-tt-lbl">Gewinnmarge:</span><span class="r-tt-val" id="tt-marge"></span></div>
            <div class="r-tt-row"><span class="r-tt-lbl">Forward KGV:</span><span class="r-tt-val" id="tt-fkgv"></span></div>
            <div class="r-tt-row"><span class="r-tt-lbl">Aktuelles KGV:</span><span class="r-tt-val" id="tt-kgv"></span></div>
            <div class="r-tt-row"><span class="r-tt-lbl">PEG Ratio:</span><span class="r-tt-val" id="tt-peg"></span></div>
            <div class="r-tt-row"><span class="r-tt-lbl">Analysten-Rating:</span><span class="r-tt-val" id="tt-anl"></span></div>
          </div>
          <canvas id="rc"></canvas>
        </div>
      </div>
      <div id="radar-placeholder" style="text-align:center; padding:60px 20px; color:var(--tx3); font-weight:500; border:1px dashed var(--brd); border-radius:14px; margin:auto 0;">
        Wähle eine Aktie in den Tabellen aus, um die fundamentale Radar-Analyse zu projizieren.
      </div>
    </div>

    <div class="sec">
      <div class="sec-title">📊 Univariates Faktoren-Cluster</div>
      <div class="sec-sub">Verteilung aller Aktien entlang einzelner Metriken. Die durchgezogene Linie repräsentiert ausschließlich den statistischen Median.</div>
      <div class="fb">
        <div class="fg">
          <span class="fl">Metrik wählen</span>
          <select class="fs" id="dot-col" onchange="renderDot()">
            <option value="KGV_Forward">KGV Forward</option>
            <option value="KGV">KGV Aktuell</option>
            <option value="EPS_naechste_5J_Pct">EPS Wachstum 5J (%)</option>
            <option value="Gewinnmarge_Pct">Gewinnmarge (%)</option>
            <option value="PEG">PEG Ratio</option>
            <option value="Analyst_Empfehlung">Analysten-Rating (1-5)</option>
          </select>
        </div>
        <div class="fg">
          <span class="fl">Sektor</span>
          <select class="fs" id="dot-sf" onchange="renderDot()"><option value="">Alle Sektoren</option></select>
        </div>
        <div class="fg">
          <span class="fl">Statistischer Filter</span>
          <select class="fs" id="dot-outliers" onchange="renderDot()">
            <option value="no" selected>Ohne Ausreißer (Default)</option>
            <option value="yes">Mit Ausreißer anzeigen</option>
          </select>
        </div>
      </div>
      <div class="canvas-holder"><canvas id="dotC"></canvas></div>
    </div>

  </div>

  <div class="sec">
    <div class="sec-title">📈 Risiko-Rendite Scatterplot Matrix</div>
    <div class="sec-sub">X-Achse: Bewertungsmultiplikator (KGV Forward) · Y-Achse: Zukünftiges EPS-Wachstum (5J %). Unten rechts = Günstiges Wachstum (Wachstums-Schnäppchen).</div>
    <div class="fb">
      <div class="fg">
        <span class="fl">Sektor-Filter</span>
        <select class="fs" id="sc-sf" onchange="renderSC()"><option value="">Alle Sektoren</option></select>
      </div>
      <div class="fg"><span class="fl">KGV Fwd. Max Cap</span><input class="fi" type="number" id="sc-kgv-max" value="60"></div>
      <div class="fg"><span class="fl">Min EPS %</span><input class="fi" type="number" id="sc-eps-min" value="-10"></div>
    </div>
    <div class="canvas-holder"><canvas id="scC"></canvas></div>
  </div>

  <div class="sec">
    <div class="sec-title">🔬 Quality &amp; Growth Screen (Inklusive NA-Werte)</div>
    <div class="sec-sub">Diese Tabelle zeigt alle Unternehmen, die deine Qualitätskriterien erfüllen **oder unvollständige Datenpunkte (NA-Werte) aufweisen**, um potenzielle Informationsasymmetrien auszunutzen.</div>
    <div class="fb">
      <div class="fg"><span class="fl">KGV Fwd (Max)</span><input class="fi" type="number" id="f1" value="40"></div>
      <div class="fg"><span class="fl">Mkt Cap Mrd (Min)</span><input class="fi" type="number" id="f2" placeholder="z.B. 1"></div>
      <div class="fg"><span class="fl">EPS 5J % (Min)</span><input class="fi" type="number" id="f3" value="10"></div>
      <div class="fg"><span class="fl">PEG (Max)</span><input class="fi" type="number" id="f4" placeholder="z.B. 3"></div>
      <div class="fg"><span class="fl">Gewinnmarge % (Min)</span><input class="fi" type="number" id="f6" value="10"></div>
      <button class="fr" onclick="resetF()">↺ Reset Filters</button>
    </div>
    <div class="tw">
      <table class="dt" id="tbl-qs">
        <thead>
          <tr>
            <th data-col="Rang">Rang</th>
            <th data-col="Ticker">Ticker</th>
            <th data-col="Unternehmen">Unternehmen</th>
            <th data-col="Sektor">Sektor</th>
            <th data-col="Marktkapitalisierung_Mrd">Mkt Cap (Mrd)</th>
            <th data-col="KGV_Forward">KGV Fwd</th>
            <th data-col="EPS_naechste_5J_Pct">EPS 5J %</th>
            <th data-col="PEG">PEG</th>
            <th data-col="Analyst_Empfehlung">Analyst</th>
            <th data-col="Gewinnmarge_Pct">Marge</th>
            <th data-col="Analyst_Upside_Pct">Upside</th>
            <th data-col="Score">Quant Score</th>
          </tr>
        </thead>
        <tbody id="tb-qs"></tbody>
      </table>
    </div>
  </div>

  <div class="sec">
    <div class="sec-title">⭐ Noahs Core Watchlist Matrix</div>
    <div class="sec-sub">Strategische Kerninvestments und Überwachungspositionen. Sortierbar durch Klick auf die Spaltenköpfe.</div>
    <div class="tw">
      <table class="dt" id="tbl-wl">
        <thead>
          <tr>
            <th data-col="Ticker">Ticker</th>
            <th data-col="Unternehmen">Unternehmen</th>
            <th data-col="Sektor">Sektor</th>
            <th data-col="Marktkapitalisierung_Mrd">Mkt Cap (Mrd.)</th>
            <th data-col="KGV">KGV</th>
            <th data-col="KGV_Forward">KGV Fwd.</th>
            <th data-col="EPS_naechste_5J_Pct">EPS 5J %</th>
            <th data-col="PEG">PEG</th>
            <th data-col="Analyst_Empfehlung">Analyst Rating</th>
            <th data-col="Gewinnmarge_Pct">Gewinnmarge</th>
          </tr>
        </thead>
        <tbody id="tb-wl"></tbody>
      </table>
    </div>
  </div>

  <div class="ftr">
    Duisburg Analytica Premium Terminal · Proprietäre Analytics Engine · Entwickelt von <a href="https://www.linkedin.com/in/noah-schulz-971031301/" target="_blank">Noah Schulz</a>
  </div>

</div>

<script>
"""
    # Füge injizierte Python-Daten hinzu
    html += js_data
    
    # Füge JavaScript Logik-Block an
    html += """
// ============================================================
// CORE DATA INITIALIZATION & FORMATTING
// ============================================================
document.getElementById('hdr-datum').textContent = DATUM;

function fDE(v, d=2, sfx='') {
  if (v === '' || v == null || isNaN(+v)) return '–';
  return (+v).toLocaleString('de-DE', {minimumFractionDigits: d, maximumFractionDigits: d}) + sfx;
}
function fP(v, d=1) { return fDE(v, d, '%'); }
function fM(v, d=1) { return fDE(v, d, ' Mrd.'); }
function sgn(v, d=1) {
  if (v === '' || isNaN(+v)) return '–';
  const n = +v; return (n >= 0 ? '+' : '−') + fDE(Math.abs(n), d, '%');
}
defCol = '#38bdf8';

// Setze Kopfzeilen-Karten Werte
const perfEl = document.getElementById('mv-p');
perfEl.textContent = sgn(AVG_PERF);
perfEl.style.color = AVG_COL;
document.getElementById('mv-pp').textContent = fDE(POS_PCT, 1, '%');
document.getElementById('mv-ov').textContent = fDE(N_OVER, 0);
document.getElementById('mv-ob').textContent = fDE(N_OVER2, 0);
document.getElementById('mv-n').textContent = fDE(N_GES, 0);

function cv(name) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

// ============================================================
// OPTIMIERTE DESIGN-FARBSKALA FÜR STRATEGISCHE RATING BADGES
// ============================================================
function getRecBadge(v) {
  if (v === '' || v == null || isNaN(+v)) return '–';
  const val = +v;
  // Dunkelgrün, Hellgrün, Gelb/Grau, Orange, Rot Stufen
  if (val <= 1.5) return `<span class="badge-rec rec-sb">Strong Buy</span>`;
  if (val <= 2.5) return `<span class="badge-rec rec-b">Buy</span>`;
  if (val <= 3.5) return `<span class="badge-rec rec-h">Hold</span>`;
  if (val <= 4.5) return `<span class="badge-rec rec-s">Sell</span>`;
  return `<span class="badge-rec rec-ss">Strong Sell</span>`;
}

// ============================================================
// THEME SWITCHING WITH CANVAS REDRAW
// ============================================================
const thmEl = document.getElementById('thm');
function applyTheme(light) {
  document.documentElement.classList.toggle('light', light);
  localStorage.setItem('theme', light ? 'light' : 'dark');
  setTimeout(() => { renderDot(); renderSC(); if(currentRadarData) _paintRadar(currentRadarData); }, 60);
}
thmEl.addEventListener('change', () => applyTheme(thmEl.checked));
(function() {
  if (localStorage.getItem('theme') === 'light') {
    document.documentElement.classList.add('light');
    thmEl.checked = true;
  }
})();

// Injiziere Sektorenoptionen
['dot-sf', 'sc-sf'].forEach(id => {
  const s = document.getElementById(id);
  SEK.forEach(sk => { const o = document.createElement('option'); o.value = sk; o.textContent = sk; s.appendChild(o); });
});

// ============================================================
// FLEXIBLE SORTIERUNG FÜR TABELLEN-WIDGETS
// ============================================================
function mkTbl(tblId, tbId, dataGetFn, renderRow, defCol='', defAsc=false) {
  const tbl = document.getElementById(tblId);
  const tb = document.getElementById(tbId);
  let st = { c: defCol, a: defAsc };

  function sortAndDraw() {
    const workingData = dataGetFn();
    if (st.c) {
      workingData.sort((a, b) => {
        let av = a[st.c]; let bv = b[st.c];
        if (av === '' || av == null) return 1;
        if (bv === '' || bv == null) return -1;
        return st.a ? (av < bv ? -1 : av > bv ? 1 : 0) : (av > bv ? -1 : av < bv ? 1 : 0);
      });
    }
    tb.innerHTML = workingData.map(renderRow).join('');
  }

  tbl.querySelectorAll('th[data-col]').forEach(th => {
    th.addEventListener('click', () => {
      const col = th.dataset.col;
      if (st.c === col) st.a = !st.a; else { st.c = col; st.a = true; }
      tbl.querySelectorAll('th').forEach(t => t.classList.remove('asc', 'desc'));
      th.classList.add(st.a ? 'asc' : 'desc');
      sortAndDraw();
    });
  });
  
  return sortAndDraw;
}

// ============================================================
// INTERAKTIVER CORE RADAR PLOT MIT ORIGINAL-METRIK OVERLAY
// ============================================================
let currentRadarData = null;
let radarScales = null;

function loadRadar(ticker) {
  const item = SD.find(d => d.Ticker === ticker);
  if (!item) {
    // Falls das Unternehmen nur im NA-Set existiert und unvollständig ist
    const rawItem = QS_DATA.find(d => d.Ticker === ticker);
    if(rawItem) {
      alert("Unternehmen " + ticker + " besitzt unzureichende Datenpunkte für eine vollständige mathematische Indizierung.");
    }
    return;
  }
  document.getElementById('radar-placeholder').style.display = 'none';
  document.getElementById('radar-wrapper').style.display = 'block';
  
  currentRadarData = item;
  
  const sc = item.Score;
  let scCol = 'var(--ac)';
  if (sc >= 75) scCol = 'var(--pos)'; else if (sc < 45) scCol = 'var(--neg)';
  
  document.getElementById('rtitle').innerHTML = `<a class="ticker-link" href="https://finviz.com/quote.ashx?t=${item.Ticker}" target="_blank">${item.Unternehmen} (${item.Ticker})</a>`;
  document.getElementById('rsub').innerHTML = `Quant-Gesamtscore: <span style="color:${scCol};font-weight:800;font-size:19px">${sc}/100</span> &nbsp;·&nbsp; Rang <strong>#${item.Rang}</strong> von ${SD.length}`;
  
  _paintRadar(item, sc, scCol);
}

function _paintRadar(d, sc, scCol) {
  const cnv = document.getElementById('rc');
  const ctx = cnv.getContext('2d');
  const W = Math.min(cnv.parentElement.offsetWidth || 400, 420);
  cnv.width = W; cnv.height = W;
  ctx.clearRect(0, 0, W, W);

  const cx = W / 2, cy = W / 2, R = W * 0.28;
  const lbls = ['EPS 5J Wachstum', 'Gewinnmarge', 'Forward KGV', 'KGV', 'PEG', 'Analyst'];
  const keys = ['S_EPS5', 'S_Marge', 'S_FKGV', 'S_KGV', 'S_PEG', 'S_Analyst'];
  const vals = keys.map(k => Math.max(0, Math.min(100, +d[k] || 0)));
  const N = lbls.length;

  // Hintergrund-Netzlinien zeichnen
  const steps = 4;
  for (let j = steps; j > 0; j--) {
    const r = R * (j / steps);
    ctx.strokeStyle = cv('--brd') || '#16294a';
    ctx.lineWidth = 1;
    ctx.beginPath();
    for (let i = 0; i < N; i++) {
      const a = (i * Math.PI * 2) / N - Math.PI / 2;
      ctx.lineTo(cx + Math.cos(a) * r, cy + Math.sin(a) * r);
    }
    ctx.closePath();
    ctx.fillStyle = j % 2 === 0 ? (cv('--bg4') || '#080f20') : (cv('--bg2') || '#0b1326');
    ctx.fill();
    ctx.stroke();
  }

  // Achsen-Strahlen
  ctx.strokeStyle = cv('--brd') || '#16294a';
  for (let i = 0; i < N; i++) {
    const a = (i * Math.PI * 2) / N - Math.PI / 2;
    ctx.beginPath(); ctx.moveTo(cx, cy); ctx.lineTo(cx + Math.cos(a) * R, cy + Math.sin(a) * R);
    ctx.stroke();
    
    // Labeling
    const lx = cx + Math.cos(a) * (R + 22);
    const ly = cy + Math.sin(a) * (R + 12);
    ctx.fillStyle = cv('--tx2') || '#b5cbfa';
    ctx.font = 'bold 11px Segoe UI,sans-serif';
    ctx.textAlign = Math.abs(Math.cos(a)) < 0.1 ? 'center' : (Math.cos(a) > 0 ? 'left' : 'right');
    ctx.fillText(lbls[i], lx, ly + 4);
  }

  // Polygonzug des Scores zeichnen
  ctx.strokeStyle = scCol;
  ctx.lineWidth = 2.5;
  ctx.fillStyle = 'rgba(' + (sc >= 75 ? '16,185,129' : (sc < 45 ? '244,63,94' : '56,189,248')) + ', 0.25)';
  ctx.beginPath();
  
  let vertexPoints = [];
  for (let i = 0; i < N; i++) {
    const a = (i * Math.PI * 2) / N - Math.PI / 2;
    const r = R * (vals[i] / 100);
    const vx = cx + Math.cos(a) * r;
    const vy = cy + Math.sin(a) * r;
    ctx.lineTo(vx, vy);
    vertexPoints.push({x: vx, y: vy, idx: i});
  }
  ctx.closePath(); ctx.fill(); ctx.stroke();

  // Datenpunkte einzeichnen
  vertexPoints.forEach(p => {
    ctx.beginPath(); ctx.arc(p.x, p.y, 4, 0, Math.PI*2);
    ctx.fillStyle = '#fff'; ctx.fill(); ctx.strokeStyle = scCol; ctx.lineWidth = 2; ctx.stroke();
  });
  
  // Registriere globale Koordinaten für Tooltip-Abfrage
  radarScales = { cx, cy, vertexPoints, rawData: d };
}

// HOVER MOUSE EVENT LISTENER FÜR DIE URSPRÜNGLICHEN ORIGINALEN KENNZAHLEN
const radarCanvas = document.getElementById('rc');
const radarTooltip = document.getElementById('radar-tt');

radarCanvas.addEventListener('mousemove', (e) => {
  if (!radarScales) return;
  const rect = radarCanvas.getBoundingClientRect();
  const mx = e.clientX - rect.left;
  const my = e.clientY - rect.top;
  
  // Berechne Abstand zum Mittelpunkt
  const dx = mx - radarScales.cx;
  const dy = my - radarScales.cy;
  const dist = Math.sqrt(dx*dx + dy*dy);
  
  if (dist <= radarCanvas.width * 0.45) {
    const rd = radarScales.rawData;
    document.getElementById('r-tt-name').textContent = rd.Unternehmen;
    document.getElementById('tt-eps').textContent = fP(rd.EPS_naechste_5J_Pct);
    document.getElementById('tt-marge').textContent = fP(rd.Gewinnmarge_Pct);
    document.getElementById('tt-fkgv').textContent = fDE(rd.KGV_Forward, 1);
    document.getElementById('tt-kgv').textContent = fDE(rd.KGV, 1);
    document.getElementById('tt-peg').textContent = fDE(rd.PEG, 2);
    document.getElementById('tt-anl').textContent = fDE(rd.Analyst_Empfehlung, 2) + " / 5,0";
    radarTooltip.style.display = 'block';
  } else {
    radarTooltip.style.display = 'none';
  }
});

radarCanvas.addEventListener('mouseleave', () => {
  radarTooltip.style.display = 'none';
});

// ============================================================
// UNIVARIATES FACTOR-CLUSTER (NUR MEDIAN, MIT AUSREISSER-LOGIK)
// ============================================================
function renderDot() {
  const col = document.getElementById('dot-col').value;
  const sf = document.getElementById('dot-sf').value;
  const showOutliers = document.getElementById('dot-outliers').value === 'yes';
  
  let data = SD.filter(d => d[col] !== '' && d[col] != null && !isNaN(+d[col]));
  if (sf) data = data.filter(d => d.Sektor === sf);
  
  let vals = data.map(d => +d[col]);
  if (!vals.length) return;

  // STATISTISCHE BERECHNUNG DER AUSREISSER (IQR Methode)
  const sortedVals = [...vals].sort((a,b) => a-b);
  const q1 = sortedVals[Math.floor(sortedVals.length * 0.25)];
  const q3 = sortedVals[Math.floor(sortedVals.length * 0.75)];
  const iqr = q3 - q1;
  const lowerBound = q1 - 1.5 * iqr;
  const upperBound = q3 + 1.5 * iqr;

  // Filter anwenden, falls Ausreißer standardmäßig ausgeschlossen werden sollen
  if (!showOutliers && iqr > 0) {
    data = data.filter(d => +d[col] >= lowerBound && +d[col] <= upperBound);
    vals = data.map(d => +d[col]);
  }

  const sorted_sv = [...vals].sort((a,b) => a-b);
  const med = sorted_sv[Math.floor(sorted_sv.length / 2)];

  const cnv = document.getElementById('dotC');
  const ctx = cnv.getContext('2d');
  const W = cnv.parentElement.offsetWidth || 550, H = 300;
  cnv.width = W; cnv.height = H;
  
  ctx.fillStyle = cv('--bg2') || '#0b1326'; ctx.fillRect(0,0,W,H);
  
  const P = { t: 30, r: 25, b: 40, l: 55 };
  const pw = W - P.l - P.r, ph = H - P.t - P.b;
  
  const mn = Math.min(...vals), mx = Math.max(...vals), rng = mx - mn || 1;
  const yMn = mn - rng * 0.08, yMx = mx + rng * 0.08;
  const ySc = v => P.t + ph - ((v - yMn) / (yMx - yMn)) * ph;

  // Y-Achsen Rasterlinien zeichnen
  for (let g = 0; g <= 5; g++) {
    const v = yMn + (yMx - yMn) * g / 5, y = ySc(v);
    ctx.strokeStyle = cv('--brd') || '#16294a'; ctx.lineWidth = 1;
    ctx.beginPath(); ctx.moveTo(P.l, y); ctx.lineTo(P.l+pw, y); ctx.stroke();
    ctx.fillStyle = cv('--tx3') || '#6c8ec7'; ctx.font = '10px Segoe UI'; ctx.textAlign = 'right';
    ctx.fillText(fDE(v, 1), P.l - 6, y + 3);
  }

  // Cluster Punkte zeichnen
  const sorted = [...data].sort((a,b) => +a[col] - +b[col]);
  sorted.forEach((d, i) => {
    const x = P.l + (i / Math.max(sorted.length - 1, 1)) * pw;
    const y = ySc(+d[col]);
    ctx.beginPath(); ctx.arc(x, y, 4, 0, Math.PI * 2);
    ctx.fillStyle = 'rgba(56, 189, 248, 0.6)'; ctx.fill();
  });

  // NUR DIE STATISTISCHE MEDIAN-LINIE ZEICHNEN (DURCHSCHNITT WURDE ENTFERNT)
  if (!isNaN(med)) {
    const yM = ySc(med);
    ctx.strokeStyle = varColor = cv('--pos') || '#10b981'; ctx.lineWidth = 2.5;
    ctx.beginPath(); ctx.moveTo(P.l, yM); ctx.lineTo(P.l+pw, yM); ctx.stroke();
    ctx.fillStyle = varColor; ctx.font = 'bold 11px Segoe UI'; ctx.textAlign = 'left';
    ctx.fillText('MEDIAN: ' + fDE(med, 1), P.l + 8, yM - 6);
  }
}

// ============================================================
// RISK-RETURN SCATTERPLOT MATRIX WIDGET
// ============================================================
function renderSC() {
  const sf = document.getElementById('sc-sf').value;
  const kMax = +document.getElementById('sc-kgv-max').value || 60;
  const eMin = +document.getElementById('sc-eps-min').value || -10;
  
  let data = SD.filter(d => d.KGV_Forward > 0 && d.KGV_Forward <= kMax && d.EPS_naechste_5J_Pct >= eMin);
  if (sf) data = data.filter(d => d.Sektor === sf);
  
  const cnv = document.getElementById('scC');
  const ctx = cnv.getContext('2d');
  const W = cnv.parentElement.offsetWidth || 1100, H = 340;
  cnv.width = W; cnv.height = H;
  ctx.fillStyle = cv('--bg2') || '#0b1326'; ctx.fillRect(0,0,W,H);
  
  const P = { t: 25, r: 25, b: 45, l: 55 };
  const pw = W - P.l - P.r, ph = H - P.t - P.b;
  
  const xSc = v => P.l + ((v - 0) / kMax) * pw;
  const ySc = v => P.t + ph - ((v - eMin) / (60 - eMin)) * ph;

  // Grid
  ctx.strokeStyle = cv('--brd') || '#16294a'; ctx.lineWidth = 1;
  for(let x=10; x<=kMax; x+=10) {
    ctx.beginPath(); ctx.moveTo(xSc(x), P.t); ctx.lineTo(xSc(x), P.t+ph); ctx.stroke();
    ctx.fillStyle = cv('--tx3'); ctx.font = '10px Segoe UI'; ctx.textAlign = 'center';
    ctx.fillText('KGV '+x, xSc(x), P.t+ph+14);
  }
  for(let y=0; y<=60; y+=15) {
    if(y < eMin) continue;
    ctx.beginPath(); ctx.moveTo(P.l, ySc(y)); ctx.lineTo(P.l+pw, ySc(y)); ctx.stroke();
    ctx.fillStyle = cv('--tx3'); ctx.font = '10px Segoe UI'; ctx.textAlign = 'right';
    ctx.fillText(y+'%', P.l-6, ySc(y)+3);
  }

  data.forEach(d => {
    const cx_ = xSc(d.KGV_Forward), cy_ = ySc(d.EPS_naechste_5J_Pct);
    ctx.beginPath(); ctx.arc(cx_, cy_, 5, 0, Math.PI*2);
    ctx.fillStyle = d.Score >= 70 ? 'var(--pos)' : (d.Score < 45 ? 'var(--neg)' : 'var(--ac)');
    ctx.fill();
    ctx.fillStyle = cv('--tx'); ctx.font = '9px Segoe UI'; ctx.textAlign = 'center';
    ctx.fillText(d.Ticker, cx_, cy_ - 8);
  });
}

// ============================================================
// TABLE RENDER PATTERNS
// ============================================================
function getRowQS(r) {
  return `<tr>
    <td>#${r.Rang || '–'}</td>
    <td><span class="ticker-link" onclick="loadRadar('${r.Ticker}')">${r.Ticker}</span></td>
    <td style="max-width:180px; overflow:hidden; text-transform:ellipsis;">${r.Unternehmen}</td>
    <td>${r.Sektor}</td>
    <td>${fDE(r.Marktkapitalisierung_Mrd, 1, ' Mrd.')}</td>
    <td>${fDE(r.KGV_Forward, 1)}</td>
    <td class="${r.EPS_naechste_5J_Pct >= 0 ? 'td-pos' : 'td-neg'}">${fP(r.EPS_naechste_5J_Pct)}</td>
    <td>${fDE(r.PEG, 2)}</td>
    <td>${getRecBadge(r.Analyst_Empfehlung)}</td>
    <td class="${r.Gewinnmarge_Pct >= 0 ? 'td-pos' : 'td-neg'}">${fP(r.Gewinnmarge_Pct)}</td>
    <td class="${r.Analyst_Upside_Pct >= 0 ? 'td-pos' : 'td-neg'}">${sgn(r.Analyst_Upside_Pct)}</td>
    <td style="font-weight:800; color:var(--ac);">${fDE(r.Score, 1)}</td>
  </tr>`;
}

function getRowWL(r) {
  return `<tr>
    <td><span class="ticker-link" onclick="loadRadar('${r.Ticker}')">${r.Ticker}</span></td>
    <td>${r.Unternehmen}</td>
    <td>${r.Sektor}</td>
    <td>${fM(r.Marktkapitalisierung_Mrd)}</td>
    <td>${fDE(r.KGV, 1)}</td>
    <td>${fDE(r.KGV_Forward, 1)}</td>
    <td class="${r.EPS_naechste_5J_Pct >= 0 ? 'td-pos' : 'td-neg'}">${fP(r.EPS_naechste_5J_Pct)}</td>
    <td>${fDE(r.PEG, 2)}</td>
    <td>${getRecBadge(r.Analyst_Empfehlung)}</td>
    <td class="${r.Gewinnmarge_Pct >= 0 ? 'td-pos' : 'td-neg'}">${fP(r.Gewinnmarge_Pct)}</td>
  </tr>`;
}

// ============================================================
// INPUT FILTER HANDLERS (WITH NA TOLERANCE)
// ============================================================
function getFilteredQSData() {
  const f1 = document.getElementById('f1').value; // Max KGV Fwd
  const f2 = document.getElementById('f2').value; // Min Mkt Cap
  const f3 = document.getElementById('f3').value; // Min EPS
  const f4 = document.getElementById('f4').value; // Max PEG
  const f6 = document.getElementById('f6').value; // Min Marge

  return QS_DATA.filter(d => {
    // Falls ein Feld NA ('') ist, wird es für den Filter ignoriert (Toleranz-Kriterium)
    if (f1 && d.KGV_Forward !== '' && d.KGV_Forward > +f1) return false;
    if (f2 && d.Marktkapitalisierung_Mrd !== '' && d.Marktkapitalisierung_Mrd < +f2) return false;
    if (f3 && d.EPS_naechste_5J_Pct !== '' && d.EPS_naechste_5J_Pct < +f3) return false;
    if (f4 && d.PEG !== '' && d.PEG > +f4) return false;
    if (f6 && d.Gewinnmarge_Pct !== '' && d.Gewinnmarge_Pct < +f6) return false;
    return true;
  });
}

const drawQS = mkTbl('tbl-qs', 'tb-qs', getFilteredQSData, getRowQS, 'Score', false);
const drawWL = mkTbl('tbl-wl', 'tb-wl', () => SD.filter(d => WL_TICKERS.includes(d.Ticker)), getRowWL, 'Marktkapitalisierung_Mrd', false);

// Event-Listener für dynamische Inputs anhängen
['f1', 'f2', 'f3', 'f4', 'f6'].forEach(id => {
  document.getElementById(id).addEventListener('input', drawQS);
});

function resetF() {
  document.getElementById('f1').value = 40; document.getElementById('f2').value = '';
  document.getElementById('f3').value = 10; document.getElementById('f4').value = '';
  document.getElementById('f6').value = 10;
  drawQS();
}

// ============================================================
// SYSTEM ENTRYPOINT
// ============================================================
window.addEventListener('resize', () => { renderDot(); renderSC(); if(currentRadarData) _paintRadar(currentRadarData); });
// Initiale Tabellenzeichnung
drawQS(); drawWL(); renderDot(); renderSC();
// Autoload erste Aktie der Watchlist für den Radarplot
if(WL_TICKERS.length > 0) { loadRadar(WL_TICKERS[0]); }
"""
    html += """</script></body></html>"""
    return html

# ============================================================
# MAIN EXECUTOR
# ============================================================
if __name__ == "__main__":
    print(f"📧 Starte Automated Corporate Finance Pipeline: {datum_de}")
    df = lade_daten()

    # 1. Statischen Mail-Newsletter abspeichern
    os.makedirs(DATA_DIR, exist_ok=True)
    mail = erstelle_mail(df)
    with open(f"{DATA_DIR}/{today_str}_newsletter.html", "w", encoding="utf-8") as f:
        f.write(mail)
    print("💾 Statisches Mail-HTML im Daten-Archiv gespeichert.")

    # 2. Interaktives Premium-Dashboard generieren
    os.makedirs(DOCS_DIR, exist_ok=True)
    dashboard_html = erstelle_dashboard(df)
    with open(f"{DOCS_DIR}/index.html", "w", encoding="utf-8") as f:
        f.write(dashboard_html)
    print("🖥️ Interaktives Dashboard für GitHub Pages (docs/index.html) erfolgreich generiert!")

    # 3. Logo-Asset Transfer-Schleife
    os.makedirs(f"{DOCS_DIR}/assets", exist_ok=True)
    logo_src = "assets/logo.png"
    logo_dst = f"{DOCS_DIR}/assets/logo.png"
    
    if os.path.exists(logo_src):
        shutil.copy2(logo_src, logo_dst)
        print("🖼️ Logo erfolgreich nach docs/assets/logo.png kopiert.")
    else:
        logo_root_src = "logo.png"
        if os.path.exists(logo_root_src):
            shutil.copy2(logo_root_src, logo_dst)
            print("🖼️ Logo aus Root erfolgreich nach docs/assets/logo.png kopiert.")
        else:
            print("⚠️ Warnung: logo.png wurde in keinem Verzeichnis detektiert.")

    # 4. Automatisierter SMTP SSL Versand
    if MAIL_SENDER and MAIL_PASSWORD and MAIL_RECEIVER:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"Noahs Finanzblog 📈 – {datum_de}"
        msg["From"]    = f"Noahs Finanzblog <{MAIL_SENDER}>"
        msg["To"]      = MAIL_RECEIVER
        msg.attach(MIMEText(mail, "html"))
        try:
            with smtplib.SMTP_SSL("smtp.gmail.com", 465) as s:
                s.login(MAIL_SENDER, MAIL_PASSWORD)
                s.sendmail(MAIL_SENDER, MAIL_RECEIVER, msg.as_string())
            print(f"✅ Mail erfolgreich an {MAIL_RECEIVER} verschickt.")
        except Exception as e:
            print(f"❌ Fehler beim SMTP-Versand: {e}")
    else:
        print("ℹ️ SMTP-Mailing übersprungen (Fehlende Environment Variables).")
