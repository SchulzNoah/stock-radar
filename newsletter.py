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
    if not sp_f or not ns_f: raise FileNotFoundError("Keine CSVs!")
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
# SCORE
# ============================================================
def berechne_score(df):
    s = df[['Ticker','Unternehmen','Sektor','KGV','KGV_Forward',
            'EPS_naechste_5J_Pct','Gewinnmarge_Pct','PEG',
            'Analyst_Empfehlung','Marktkapitalisierung_Mrd']].copy()
    s = s[s['KGV_Forward'].notna()&s['EPS_naechste_5J_Pct'].notna()&
          s['Gewinnmarge_Pct'].notna()&(s['KGV_Forward']>0)&
          (s['KGV_Forward']<200)&(s['Marktkapitalisierung_Mrd'].fillna(0)>0.3)].copy()
    s['kgv_c']  = s['KGV'].clip(1,100).fillna(50)
    s['fkgv_c'] = s['KGV_Forward'].clip(1,80)
    s['eps5_c'] = s['EPS_naechste_5J_Pct'].clip(-20,60)
    s['mg_c']   = s['Gewinnmarge_Pct'].clip(-10,50)
    s['peg_c']  = s['PEG'].clip(0.1,5).fillna(3)
    s['anl_c']  = s['Analyst_Empfehlung'].clip(1,5).fillna(3)
    def pr(x, inv=False): r=x.rank(pct=True)*100; return 100-r if inv else r
    s['S_EPS5']    = pr(s['eps5_c'])
    s['S_Marge']   = pr(s['mg_c'])
    s['S_FKGV']    = pr(s['fkgv_c'],True)
    s['S_KGV']     = pr(s['kgv_c'],True)
    s['S_PEG']     = pr(s['peg_c'],True)
    s['S_Analyst'] = pr(s['anl_c'],True)
    s['Score'] = (s['S_EPS5']*0.30+s['S_Marge']*0.20+s['S_FKGV']*0.20+
                  s['S_KGV']*0.15+s['S_PEG']*0.10+s['S_Analyst']*0.05).round(1)
    s = s.sort_values('Score',ascending=False).reset_index(drop=True)
    s['Rang'] = s.index+1
    return s[['Rang','Ticker','Unternehmen','Sektor','Score',
               'S_EPS5','S_Marge','S_FKGV','S_KGV','S_PEG','S_Analyst',
               'KGV','KGV_Forward','EPS_naechste_5J_Pct','Gewinnmarge_Pct',
               'PEG','Analyst_Empfehlung']]

# ============================================================
# STATISCHE MAIL
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
  <div style="font-size:11px;color:#5A7A95;margin-bottom:12px;">Analyst: 1,0 = Strong Buy · 2,0 = Buy · 3,0 = Hold · 4,0 = Sell · 5,0 = Strong Sell</div>
  <div style="overflow-x:auto;"><table width="100%" cellpadding="0" cellspacing="0" style="min-width:700px;">
    <thead><tr style="background:#0A1628;">
      <th style="padding:9px 10px;color:#4DB8FF;font-size:10px;border-bottom:2px solid #1E3A5F;text-transform:uppercase;white-space:nowrap">Ticker</th>
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
    <tbody>{wr}</tbody>
  </table></div>
</div>
<div style="text-align:center;color:#3A5A75;font-size:11px;padding:16px;border-top:1px solid #1A2E45;margin-top:8px;">
  Keine Anlageberatung – Newsletter erstellt von
  <a href="https://www.linkedin.com/in/noah-schulz-971031301/" target="_blank" style="color:#4DB8FF;text-decoration:none;">Noah Schulz</a>
</div>
</div></body></html>"""

# ============================================================
# DASHBOARD – vollständig als raw string (kein f-string im JS)
# ============================================================
def erstelle_dashboard(df):
    # Daten vorbereiten
    wl_df = df[df['Ticker'].isin(WATCHLIST_TICKERS)].copy()
    wl_df = wl_df.sort_values('Marktkapitalisierung_Mrd', ascending=False)

    qs_df = (df[df['Gewinnmarge_Pct'].notna()&df['EPS_naechste_5J_Pct'].notna()&
                df['KGV_Forward'].notna()&(df['Gewinnmarge_Pct']>10)&
                (df['EPS_naechste_5J_Pct']>10)&(df['KGV_Forward']>0)&
                (df['KGV_Forward']<40)&(df['ROE_Pct'].fillna(0)>15)]
             .assign(Score=lambda x:
                x['Gewinnmarge_Pct'].rank(pct=True)*0.25+
                x['EPS_naechste_5J_Pct'].rank(pct=True)*0.35+
                x['ROE_Pct'].rank(pct=True)*0.20+
                (-x['KGV_Forward']).rank(pct=True)*0.20)
             .nlargest(200,'Score')
             [['Ticker','Unternehmen','Sektor','Marktkapitalisierung_Mrd',
               'KGV_Forward','EPS_naechste_5J_Pct','Gewinnmarge_Pct',
               'PEG','Analyst_Empfehlung','Analyst_Upside_Pct']])

    pd_df = df[df['KGV'].notna()&df['KGV_Forward'].notna()&
               df['EPS_naechste_5J_Pct'].notna()&df['Sektor'].notna()&
               (df['KGV']>0)&(df['KGV']<150)&
               (df['KGV_Forward']>0)&(df['KGV_Forward']<100)
               ][['Ticker','Unternehmen','Sektor','KGV','KGV_Forward',
                  'EPS_naechste_5J_Pct','PEG','Perf_Monat_Pct','Perf_Jahr_Pct']].copy()

    sc_df    = berechne_score(df)
    sek_list = sorted(df['Sektor'].dropna().unique().tolist())

    avg_perf    = float(round(df['Perf_Monat_Pct'].mean(), 2))
    positiv_pct = float(round((df['Perf_Monat_Pct']>0).mean()*100, 1))
    n_over      = int((df['RSI']<30).sum())
    n_over2     = int((df['RSI']>70).sum())
    n_ges       = len(df)
    avg_col     = "#2DD4A0" if avg_perf >= 0 else "#FF5C72"

    # JSON
    wl_json  = wl_df.fillna("").to_json(orient="records")
    qs_json  = qs_df.fillna("").to_json(orient="records")
    pd_json  = pd_df.fillna("").to_json(orient="records")
    sc_json  = sc_df.fillna("").to_json(orient="records")
    sek_json = json.dumps(sek_list)

    # Python-generierte Werte als JS-Block (normaler f-string, kein JS drin)
    data_block = (
        f'const DATUM="{datum_de}";'
        f'const AVG_PERF={avg_perf};'
        f'const AVG_COL="{avg_col}";'
        f'const POS_PCT={positiv_pct};'
        f'const N_OVER={n_over};'
        f'const N_OVER2={n_over2};'
        f'const N_GES={n_ges};'
        f'const WL={wl_json};'
        f'const QS={qs_json};'
        f'const PD={pd_json};'
        f'const SD={sc_json};'
        f'const SEK={sek_json};'
    )

    # HTML/CSS/JS als reiner raw string – kein {{ }} nötig
    html = """<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<link rel="icon" type="image/png" href="assets/logo.png">

<title>Noahs Finanzblog 📈</title>
<style>
:root {
  --bg:#080C14; --bg2:#0D1520; --bg3:#111D2E; --bg4:#0A1628;
  --brd:#1A2E45; --brd2:#1E3A5F;
  --tx:#E8EDF5; --tx2:#C8D8E8; --tx3:#8AACC8; --tx4:#5A7A95; --tx5:#3A5A75;
  --ac:#4DB8FF; --pos:#2DD4A0; --neg:#FF5C72; --warn:#FFB347; --thbg:#0A1628;
}
html.light {
  --bg:#F0F4F8; --bg2:#FFFFFF; --bg3:#EBF0F7; --bg4:#DDE6F0;
  --brd:#C8D8E8; --brd2:#A0B8D0;
  --tx:#0D1B2E; --tx2:#1E3A5F; --tx3:#2A5080; --tx4:#4A7090; --tx5:#7090A8;
  --ac:#1A7ACC; --pos:#1A8060; --neg:#CC2040; --warn:#C07000; --thbg:#DDE6F0;
}
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:'Segoe UI',sans-serif;background:var(--bg);color:var(--tx);
     padding:16px;max-width:1000px;margin:0 auto;transition:background .3s,color .3s}

/* HEADER */
.hdr{background:linear-gradient(135deg,#0D1B2E,#122540);border:1px solid var(--brd2);
     border-radius:16px;padding:20px 24px;margin-bottom:16px;
     display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:12px}
html.light .hdr{background:linear-gradient(135deg,#C8DCF0,#A8C8E8)}
.hdr-left{display:flex;align-items:center;gap:16px}
.hdr-logo{height:64px;width:auto;object-fit:contain;filter:drop-shadow(0 2px 8px rgba(77,184,255,0.3))}
.hdr-text h1{font-size:clamp(17px,3.5vw,26px);font-weight:700;color:var(--tx)}
.hdr-text h1 span{color:var(--ac)}
.hdr-text .sub{color:var(--tx3);font-size:12px;margin-top:3px}
.hdr-right{display:flex;align-items:center;gap:12px}

/* DARK/LIGHT TOGGLE */
.tgl-wrap{display:flex;align-items:center;gap:8px;font-size:15px}
.tgl{position:relative;width:50px;height:27px;cursor:pointer;flex-shrink:0}
.tgl input{opacity:0;width:0;height:0;position:absolute}
.tgl-slider{position:absolute;inset:0;background:var(--brd2);border-radius:27px;
            transition:.3s;border:1px solid var(--brd2)}
.tgl-slider::before{content:'';position:absolute;width:21px;height:21px;
                    left:3px;top:2px;background:var(--ac);
                    border-radius:50%;transition:.3s;box-shadow:0 1px 4px rgba(0,0,0,.3)}
.tgl input:checked + .tgl-slider{background:#1E3A5F}
.tgl input:checked + .tgl-slider::before{transform:translateX(23px)}

/* SECTIONS */
.sec{background:var(--bg2);border:1px solid var(--brd);border-radius:12px;
     padding:20px;margin-bottom:16px}
.sec-title{font-size:17px;font-weight:700;color:var(--ac);margin-bottom:14px;
           padding-bottom:10px;border-bottom:1px solid var(--brd)}
.sec-sub{font-size:11px;color:var(--tx4);margin-top:-10px;margin-bottom:14px;line-height:1.6}

/* METRICS */
.mg{display:grid;grid-template-columns:repeat(auto-fit,minmax(110px,1fr));gap:10px}
.mc{background:var(--bg3);border:1px solid var(--brd2);border-radius:10px;
    padding:14px 10px;text-align:center}
.mv{font-size:clamp(15px,3vw,21px);font-weight:700;color:var(--ac);line-height:1.2}
.ml{font-size:10px;color:var(--tx4);margin-top:4px}
.c-pos{color:var(--pos)!important}.c-neg{color:var(--neg)!important}

/* TABLES */
.tw{overflow-x:auto;-webkit-overflow-scrolling:touch}
table.dt{width:100%;border-collapse:collapse;font-size:12px;min-width:460px}
table.dt th{background:var(--thbg);color:var(--ac);padding:9px 8px;text-align:left;
            border-bottom:2px solid var(--brd2);white-space:nowrap;cursor:pointer;
            user-select:none;font-weight:700;font-size:10px;text-transform:uppercase;
            letter-spacing:.5px;transition:background .15s}
table.dt th:hover{background:var(--brd)}
table.dt th.asc::after{content:' ▲';color:var(--ac)}
table.dt th.desc::after{content:' ▼';color:var(--ac)}
table.dt th:not(.asc):not(.desc)::after{content:' ⇅';color:var(--tx4)}
table.dt td{padding:8px;border-bottom:1px solid var(--brd);
            color:var(--tx2);white-space:nowrap;font-size:12px}
table.dt tr:hover td{background:var(--bg3)}
.tp{color:var(--ac);font-weight:700}.tn{color:var(--tx)}.ts{color:var(--tx3)}
.td-pos{color:var(--pos);font-weight:600}.td-neg{color:var(--neg);font-weight:600}

/* PAGINATION */
.pg{display:flex;justify-content:flex-end;align-items:center;gap:6px;margin-top:10px;flex-wrap:wrap}
.pb{background:var(--bg3);border:1px solid var(--brd2);color:var(--tx3);
    padding:4px 10px;border-radius:6px;cursor:pointer;font-size:11px;transition:all .15s}
.pb:hover,.pb.active{background:var(--brd2);color:var(--ac);border-color:var(--ac)}
.pi{color:var(--tx4);font-size:11px}

/* FILTERS */
.fb{display:flex;flex-wrap:wrap;gap:8px;margin-bottom:14px;
    padding:14px;background:var(--bg4);border-radius:8px;border:1px solid var(--brd)}
.fg{display:flex;flex-direction:column;gap:3px;flex:1;min-width:110px}
.fl{font-size:10px;color:var(--tx4);text-transform:uppercase;letter-spacing:.5px}
.fi,.fs{background:var(--bg3);border:1px solid var(--brd2);color:var(--tx);
        padding:6px 8px;border-radius:6px;font-size:11px;font-family:inherit;
        width:100%;transition:border-color .2s}
.fi:focus,.fs:focus{outline:none;border-color:var(--ac)}
.fr{background:transparent;border:1px solid var(--brd2);color:var(--tx4);
    padding:6px 12px;border-radius:6px;cursor:pointer;font-size:11px;
    align-self:flex-end;transition:all .15s;font-family:inherit}
.fr:hover{border-color:var(--ac);color:var(--ac)}

/* METRIC TOGGLE */
.mt-wrap{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin-bottom:12px}
.mt-grp{display:flex;border:1px solid var(--brd2);border-radius:8px;overflow:hidden;flex-wrap:wrap}
.mt-btn{padding:7px 14px;font-size:11px;font-weight:600;cursor:pointer;border:none;
        background:var(--bg3);color:var(--tx3);transition:all .2s;font-family:inherit;
        border-right:1px solid var(--brd2)}
.mt-btn:last-child{border-right:none}
.mt-btn.active{background:var(--ac);color:#050C18}
.mt-btn:hover:not(.active){background:var(--brd);color:var(--tx)}

/* CHART */
.cc{position:relative;width:100%;margin-top:8px}
canvas{border-radius:8px;max-width:100%;display:block}
.ct{background:var(--bg3);border:1px solid var(--brd2);border-radius:8px;
    padding:10px 14px;margin-top:10px;font-size:12px;color:var(--tx2);display:none;
    line-height:1.6}

/* SEARCH / RADAR */
.sw{position:relative;margin-bottom:14px}
.si{width:100%;background:var(--bg3);border:1px solid var(--brd2);color:var(--tx);
    padding:10px 14px;border-radius:8px;font-size:13px;font-family:inherit;
    transition:border-color .2s}
.si:focus{outline:none;border-color:var(--ac)}
.al{position:absolute;top:100%;left:0;right:0;background:var(--bg3);
    border:1px solid var(--brd2);border-top:none;border-radius:0 0 8px 8px;
    z-index:100;max-height:230px;overflow-y:auto;display:none}
.ai{padding:9px 14px;cursor:pointer;font-size:12px;color:var(--tx2);
    border-bottom:1px solid var(--brd);
    display:flex;justify-content:space-between;align-items:center}
.ai:hover{background:var(--brd);color:var(--ac)}
.ai-tk{color:var(--ac);font-weight:700;margin-right:10px}
.ai-sc{color:var(--tx4);font-size:10px}
#rw{display:none;margin-top:16px;text-align:center}
.rt{font-size:18px;font-weight:700;color:var(--tx)}
.rs{font-size:13px;color:var(--tx3);margin-top:4px}

/* SCORE INFO */
.score-info{background:var(--bg4);border:1px solid var(--brd);border-radius:8px;
            padding:12px 14px;margin-bottom:14px;font-size:12px;
            color:var(--tx3);line-height:1.8}
.score-info strong{color:var(--tx2)}

/* FOOTER */
.footer{text-align:center;color:var(--tx5);font-size:11px;
        margin-top:20px;padding:16px;border-top:1px solid var(--brd)}
.footer a{color:var(--ac);text-decoration:none}

@media(max-width:620px){
  body{padding:10px}
  .hdr{padding:14px 16px}
  .hdr-logo{height:48px}
  .sec{padding:14px}
  .fb{flex-direction:column}
  .fg{min-width:100%}
  .mt-grp{width:100%}
  .mt-btn{flex:1;text-align:center;font-size:10px;padding:6px 8px}
}
</style>
</head>
<body>

<!-- HEADER -->
<div class="hdr">
  <div class="hdr-left">
    <img class="hdr-logo" src="assets/logo.png" alt="Duisburg Analytica Logo">
    <div class="hdr-text">
      <h1>Noahs Finanzblog <span>📈</span></h1>
      <div class="sub" id="hdr-datum">–</div>
    </div>
  </div>
  <div class="hdr-right">
    <div class="tgl-wrap">
      <span>☀️</span>
      <label class="tgl">
        <input type="checkbox" id="thm">
        <span class="tgl-slider"></span>
      </label>
      <span>🌙</span>
    </div>
  </div>
</div>

<!-- MARKTÜBERSICHT -->
<div class="sec">
  <div class="sec-title">🌍 Marktübersicht</div>
  <div class="mg">
    <div class="mc"><div class="mv" id="mv-p"></div><div class="ml">Ø Perf. 1M</div></div>
    <div class="mc"><div class="mv" id="mv-pp"></div><div class="ml">Im Plus (1M)</div></div>
    <div class="mc"><div class="mv c-pos" id="mv-ov"></div><div class="ml">Überverkauft (RSI&lt;30)</div></div>
    <div class="mc"><div class="mv c-neg" id="mv-ob"></div><div class="ml">Überkauft (RSI&gt;70)</div></div>
    <div class="mc"><div class="mv" id="mv-n"></div><div class="ml">Aktien analysiert</div></div>
  </div>
</div>

<!-- WATCHLIST -->
<div class="sec">
  <div class="sec-title">⭐ Noahs Aktien-Watchlist</div>
  <div class="sec-sub">
    Analyst-Skala: <strong style="color:var(--pos)">1,0 = Strong Buy</strong> &nbsp;·&nbsp;
    <strong style="color:var(--pos)">2,0 = Buy</strong> &nbsp;·&nbsp;
    <strong style="color:var(--tx3)">3,0 = Hold</strong> &nbsp;·&nbsp;
    <strong style="color:var(--neg)">4,0 = Sell</strong> &nbsp;·&nbsp;
    <strong style="color:var(--neg)">5,0 = Strong Sell</strong>
  </div>
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
  <div class="sec-sub">
    Analyst: <strong>1,0 = Strong Buy</strong> · <strong>5,0 = Strong Sell</strong> &nbsp;·&nbsp;
    Upside = Abstand zum Analystenkursziel
  </div>
  <div class="fb">
    <div class="fg"><span class="fl">KGV Fwd. (max)</span><input class="fi" type="number" id="f1" value="40"></div>
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

<!-- DOTPLOT -->
<div class="sec">
  <div class="sec-title">📊 Univariater Dotplot</div>
  <div class="mt-wrap">
    <div class="mt-grp" id="mt-grp">
      <button class="mt-btn active" data-m="KGV">KGV</button>
      <button class="mt-btn" data-m="KGV_Forward">Forward KGV</button>
      <button class="mt-btn" data-m="PEG">PEG</button>
      <button class="mt-btn" data-m="EPS_naechste_5J_Pct">EPS 5J %</button>
      <button class="mt-btn" data-m="Perf_Monat_Pct">Perf. 1M</button>
      <button class="mt-btn" data-m="Perf_Jahr_Pct">Perf. 1J</button>
    </div>
    <select class="fs" id="dot-sf" style="width:auto;min-width:170px">
      <option value="">Alle Sektoren</option>
    </select>
  </div>
  <div class="cc"><canvas id="dotC" height="290"></canvas></div>
  <div class="ct" id="dot-tt"></div>
</div>

<!-- SCATTER -->
<div class="sec">
  <div class="sec-title">📈 KGV vs. EPS-Wachstum 5J</div>
  <div style="display:flex;gap:8px;align-items:center;margin-bottom:12px;flex-wrap:wrap">
    <select class="fs" id="sc-sf" style="width:auto;min-width:170px">
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
    EPS Wachstum 5J <strong>30 %</strong> &nbsp;·&nbsp;
    Gewinnmarge <strong>20 %</strong> &nbsp;·&nbsp;
    Forward KGV <strong>20 %</strong> &nbsp;·&nbsp;
    KGV <strong>15 %</strong> &nbsp;·&nbsp;
    PEG <strong>10 %</strong> &nbsp;·&nbsp;
    Analyst <strong>5 %</strong><br>
    Normierung per Perzentil-Rang (0–100). Score = gewichteter Durchschnitt.
  </div>
  <div class="sw">
    <input class="si" id="rs" type="text"
           placeholder="🔍 Unternehmen suchen – z.B. NVIDIA oder NV ...">
    <div class="al" id="ac"></div>
  </div>
  <div id="rw">
    <div class="rt" id="rt"></div>
    <div class="rs" id="rsub"></div>
    <canvas id="rc" style="display:block;margin:16px auto 0"></canvas>
  </div>
</div>

<div class="footer">
  Keine Anlageberatung – Newsletter erstellt von
  <a href="https://www.linkedin.com/in/noah-schulz-971031301/" target="_blank">Noah Schulz</a>
</div>


"""

    js = """
// ============================================================
// INIT
// ============================================================
document.getElementById('hdr-datum').textContent = DATUM;

// Marktübersicht befüllen
function fDE(v,d=2,sfx=''){
  if(v===''||v==null||isNaN(+v))return'–';
  return(+v).toLocaleString('de-DE',{minimumFractionDigits:d,maximumFractionDigits:d})+sfx;
}
function fP(v,d=1){return fDE(v,d,'%')}
function fM(v,d=1){return fDE(v,d,' Mrd.')}
function sgn(v,d=1){
  if(v===''||isNaN(+v))return'–';
  const n=+v;return(n>=0?'+':'−')+fDE(Math.abs(n),d,'%');
}
function cc(v){if(v===''||isNaN(+v))return'';return +v>=0?'td-pos':'td-neg';}
function cv(name){return getComputedStyle(document.documentElement).getPropertyValue(name).trim();}

const perfEl=document.getElementById('mv-p');
perfEl.textContent=sgn(AVG_PERF);
perfEl.style.color=AVG_COL;
document.getElementById('mv-pp').textContent=fDE(POS_PCT,1,'%');
document.getElementById('mv-ov').textContent=fDE(N_OVER,0);
document.getElementById('mv-ob').textContent=fDE(N_OVER2,0);
document.getElementById('mv-n').textContent=fDE(N_GES,0);

// ============================================================
// THEME TOGGLE
// ============================================================
const thmEl=document.getElementById('thm');
function applyTheme(light){
  document.documentElement.classList.toggle('light',light);
  localStorage.setItem('theme',light?'light':'dark');
  setTimeout(()=>{renderDot();renderSC();},50);
}
thmEl.addEventListener('change',()=>applyTheme(thmEl.checked));
(function(){
  if(localStorage.getItem('theme')==='light'){
    document.documentElement.classList.add('light');
    thmEl.checked=true;
  }
})();

// ============================================================
// SEKTOR-SELECTS
// ============================================================
['dot-sf','sc-sf'].forEach(id=>{
  const s=document.getElementById(id);
  SEK.forEach(sk=>{const o=document.createElement('option');o.value=sk;o.textContent=sk;s.appendChild(o);});
});

// ============================================================
// SORTIERBARE TABELLEN
// ============================================================
function mkTbl(tblId,tbId,data,renderRow,defCol='',defAsc=false){
  const tbl=document.getElementById(tblId);
  const tb=document.getElementById(tbId);
  let st={c:defCol,a:defAsc};
  function sort(){
    if(!st.c)return;
    data.sort((a,b)=>{
      const av=isNaN(+a[st.c])?String(a[st.c]||''):+a[st.c];
      const bv=isNaN(+b[st.c])?String(b[st.c]||''):+b[st.c];
      return st.a?(av<bv?-1:av>bv?1:0):(av>bv?-1:av<bv?1:0);
    });
  }
  function draw(rows){tb.innerHTML=rows.map(renderRow).join('');}
  tbl.querySelectorAll('th[data-col]').forEach(th=>{
    th.addEventListener('click',()=>{
      const col=th.dataset.col;
      if(st.c===col)st.a=!st.a;else{st.c=col;st.a=true;}
      tbl.querySelectorAll('th').forEach(t=>t.classList.remove('asc','desc'));
      th.classList.add(st.a?'asc':'desc');
      sort();draw(data);
    });
  });
  if(st.c){const th=tbl.querySelector(`th[data-col="${st.c}"]`);if(th)th.classList.add(st.a?'asc':'desc');}
  sort();draw(data);
}

mkTbl('tbl-wl','tb-wl',[...WL],r=>`<tr>
  <td class="tp">${r.Ticker||'–'}</td>
  <td class="tn">${(r.Unternehmen||'–').substring(0,24)}</td>
  <td class="ts">${(r.Sektor||'–').substring(0,18)}</td>
  <td style="text-align:right">${fM(r.Marktkapitalisierung_Mrd)}</td>
  <td style="text-align:right">${fM(r.Gewinn_Mrd,2)}</td>
  <td style="text-align:right">${fDE(r.KGV,1)}</td>
  <td style="text-align:right">${fDE(r.KGV_Forward,1)}</td>
  <td style="text-align:right" class="${cc(r.EPS_naechste_5J_Pct)}">${fP(r.EPS_naechste_5J_Pct)}</td>
  <td style="text-align:right">${fDE(r.PEG,2)}</td>
  <td style="text-align:right">${fDE(r.Analyst_Empfehlung,2)}</td>
  <td style="text-align:right" class="${cc(r.Gewinnmarge_Pct)}">${fP(r.Gewinnmarge_Pct)}</td>
</tr>`,'Marktkapitalisierung_Mrd',false);

// ============================================================
// QUALITY SCREEN
// ============================================================
let qPage=1;const PS=10;
let qSort={c:'EPS_naechste_5J_Pct',a:false};

function getQF(){
  const kmax=+document.getElementById('f1').value||Infinity;
  const mmin=+document.getElementById('f2').value||-Infinity;
  const emin=+document.getElementById('f3').value||-Infinity;
  const pmax=+document.getElementById('f4').value||Infinity;
  const gmin=+document.getElementById('f6').value||-Infinity;
  return QS.filter(r=>
    (+r.KGV_Forward||Infinity)<=kmax&&
    (+r.Marktkapitalisierung_Mrd||-Infinity)>=mmin&&
    (+r.EPS_naechste_5J_Pct||-Infinity)>=emin&&
    (+r.PEG||Infinity)<=pmax&&
    (+r.Gewinnmarge_Pct||-Infinity)>=gmin);
}
function renderQ(){
  let data=getQF();
  data.sort((a,b)=>{
    const c=qSort.c;
    const av=isNaN(+a[c])?String(a[c]||''):+a[c];
    const bv=isNaN(+b[c])?String(b[c]||''):+b[c];
    return qSort.a?(av<bv?-1:av>bv?1:0):(av>bv?-1:av<bv?1:0);
  });
  const tp=Math.ceil(data.length/PS)||1;
  if(qPage>tp)qPage=1;
  const sl=data.slice((qPage-1)*PS,qPage*PS);
  document.getElementById('tb-qs').innerHTML=sl.map(r=>`<tr>
    <td class="tp">${r.Ticker||'–'}</td>
    <td class="tn">${(r.Unternehmen||'–').substring(0,24)}</td>
    <td class="ts">${(r.Sektor||'–').substring(0,18)}</td>
    <td style="text-align:right">${fM(r.Marktkapitalisierung_Mrd)}</td>
    <td style="text-align:right">${fDE(r.KGV_Forward,1)}</td>
    <td style="text-align:right" class="${cc(r.EPS_naechste_5J_Pct)}">${fP(r.EPS_naechste_5J_Pct)}</td>
    <td style="text-align:right" class="${cc(r.Gewinnmarge_Pct)}">${fP(r.Gewinnmarge_Pct)}</td>
    <td style="text-align:right">${fDE(r.PEG,2)}</td>
    <td style="text-align:right">${fDE(r.Analyst_Empfehlung,2)}</td>
    <td style="text-align:right" class="${cc(r.Analyst_Upside_Pct)}">${sgn(r.Analyst_Upside_Pct)}</td>
  </tr>`).join('');
  const pg=document.getElementById('pg-qs');pg.innerHTML='';
  const sp=document.createElement('span');sp.className='pi';
  const s=(qPage-1)*PS+1,e=Math.min(qPage*PS,data.length);
  sp.textContent=`${s}–${e} von ${data.length}`;pg.appendChild(sp);
  for(let i=1;i<=tp;i++){
    const b=document.createElement('button');b.className='pb'+(i===qPage?' active':'');
    b.textContent=i;b.onclick=(p=>()=>{qPage=p;renderQ();})(i);pg.appendChild(b);
  }
}
document.getElementById('tbl-qs').querySelectorAll('th[data-col]').forEach(th=>{
  th.addEventListener('click',()=>{
    const c=th.dataset.col;
    if(qSort.c===c)qSort.a=!qSort.a;else{qSort.c=c;qSort.a=false;}
    document.getElementById('tbl-qs').querySelectorAll('th').forEach(t=>t.classList.remove('asc','desc'));
    th.classList.add(qSort.a?'asc':'desc');qPage=1;renderQ();
  });
});
['f1','f2','f3','f4','f6'].forEach(id=>{
  document.getElementById(id).addEventListener('input',()=>{qPage=1;renderQ();});
});
function resetF(){
  document.getElementById('f1').value=40;
  ['f2','f4'].forEach(id=>document.getElementById(id).value='');
  document.getElementById('f3').value=10;document.getElementById('f6').value=10;
  qPage=1;renderQ();
}
renderQ();

// ============================================================
// DOTPLOT – 6 METRIKEN
// ============================================================
const METRICS={
  KGV:               {label:'KGV (Trailing)',       col:'KGV',               clr:'rgba(77,184,255,0.6)',  lc:'#4DB8FF',cap:[0,150],  pct:false,dec:1,sfx:''},
  KGV_Forward:       {label:'Forward KGV',          col:'KGV_Forward',       clr:'rgba(45,212,160,0.6)',  lc:'#2DD4A0',cap:[0,100],  pct:false,dec:1,sfx:''},
  PEG:               {label:'PEG Ratio',            col:'PEG',               clr:'rgba(255,179,71,0.6)',  lc:'#FFB347',cap:[0,5],    pct:false,dec:2,sfx:''},
  EPS_naechste_5J_Pct:{label:'EPS Wachstum 5J (%)',col:'EPS_naechste_5J_Pct',clr:'rgba(164,120,255,0.6)',lc:'#A478FF',cap:[-20,60], pct:true, dec:1,sfx:'%'},
  Perf_Monat_Pct:    {label:'Performance 1M (%)',   col:'Perf_Monat_Pct',    clr:'rgba(255,92,114,0.6)', lc:'#FF5C72',cap:[-60,120],pct:true, dec:1,sfx:'%'},
  Perf_Jahr_Pct:     {label:'Performance 1J (%)',   col:'Perf_Jahr_Pct',     clr:'rgba(255,215,0,0.6)',  lc:'#FFD700',cap:[-90,400],pct:true, dec:1,sfx:'%'},
};
let curM='KGV';
let dotScales={};

document.getElementById('mt-grp').querySelectorAll('.mt-btn').forEach(btn=>{
  btn.addEventListener('click',()=>{
    curM=btn.dataset.m;
    document.getElementById('mt-grp').querySelectorAll('.mt-btn').forEach(b=>b.classList.remove('active'));
    btn.classList.add('active');
    document.getElementById('dot-tt').style.display='none';
    renderDot();
  });
});
document.getElementById('dot-sf').addEventListener('change',renderDot);

function renderDot(){
  const cfg=METRICS[curM];
  const sek=document.getElementById('dot-sf').value;
  const col=cfg.col;

  const data=PD.filter(d=>{
    const v=+d[col];
    if(isNaN(v)||d[col]==='')return false;
    if(sek&&d.Sektor!==sek)return false;
    return v>=cfg.cap[0]&&v<=cfg.cap[1];
  });
  const vals=data.map(d=>+d[col]);
  if(!vals.length)return;

  const posOnly=['KGV','KGV_Forward','PEG'];
  const sv=posOnly.includes(col)?vals.filter(v=>v>0):vals;
  const avg=sv.reduce((a,b)=>a+b,0)/(sv.length||1);
  const sorted_sv=[...sv].sort((a,b)=>a-b);
  const med=sorted_sv[Math.floor(sorted_sv.length/2)];

  const cnv=document.getElementById('dotC');
  const ctx=cnv.getContext('2d');
  const W=cnv.parentElement.offsetWidth||820,H=290;
  cnv.width=W;cnv.height=H;

  const bgC=cv('--bg2')||'#0D1520';
  const grC=cv('--brd')||'#1A2E45';
  const txC=cv('--tx4')||'#5A7A95';

  ctx.fillStyle=bgC;ctx.fillRect(0,0,W,H);
  const P={t:32,r:20,b:40,l:60};
  const pw=W-P.l-P.r,ph=H-P.t-P.b;
  const mn=Math.min(...vals),mx=Math.max(...vals),rng=mx-mn||1;
  const yMn=mn-rng*.08,yMx=mx+rng*.08;
  const ySc=v=>P.t+ph-((v-yMn)/(yMx-yMn))*ph;

  for(let g=0;g<=5;g++){
    const v=yMn+(yMx-yMn)*g/5,y=ySc(v);
    ctx.strokeStyle=grC;ctx.lineWidth=1;
    ctx.beginPath();ctx.moveTo(P.l,y);ctx.lineTo(P.l+pw,y);ctx.stroke();
    ctx.fillStyle=txC;ctx.font='10px Segoe UI,sans-serif';ctx.textAlign='right';
    ctx.fillText(fDE(v,cfg.dec)+cfg.sfx,P.l-5,y+3);
  }
  if(cfg.pct&&yMn<0&&yMx>0){
    const y0=ySc(0);ctx.strokeStyle=txC;ctx.lineWidth=1.5;ctx.setLineDash([4,3]);
    ctx.beginPath();ctx.moveTo(P.l,y0);ctx.lineTo(P.l+pw,y0);ctx.stroke();ctx.setLineDash([]);
  }

  const sorted=[...data].sort((a,b)=>+a[col]-+b[col]);
  dotScales={sorted,col,ySc,pw,P,cfg};

  sorted.forEach((d,i)=>{
    const x=P.l+(i/Math.max(sorted.length-1,1))*pw;
    const y=ySc(+d[col]);
    ctx.beginPath();ctx.arc(x,y,3.5,0,Math.PI*2);
    ctx.fillStyle=cfg.clr;ctx.fill();
  });

  function hl(val,lbl,dash){
    if(isNaN(val))return;
    const y=ySc(val);
    ctx.strokeStyle=cfg.lc;ctx.lineWidth=1.8;ctx.setLineDash(dash||[]);
    ctx.beginPath();ctx.moveTo(P.l,y);ctx.lineTo(P.l+pw,y);ctx.stroke();ctx.setLineDash([]);
    ctx.fillStyle=cfg.lc;ctx.font='bold 9px Segoe UI,sans-serif';ctx.textAlign='left';
    ctx.fillText(lbl+': '+fDE(val,cfg.dec)+cfg.sfx,P.l+4,y-3);
  }
  hl(avg,'Ø',[]);
  hl(med,'Median',[6,4]);

  ctx.fillStyle=cfg.lc;ctx.font='bold 11px Segoe UI,sans-serif';ctx.textAlign='center';
  ctx.fillText(cfg.label,P.l+pw/2,P.t-10);
  const note=posOnly.includes(col)?` | Ø/Median: ${sv.length} pos. Werte`:'';
  ctx.fillStyle=txC;ctx.font='10px Segoe UI,sans-serif';
  ctx.fillText(`${data.length} Unternehmen | ${sek||'Alle Sektoren'}${note} | Klick für Details`,P.l+pw/2,H-5);
}

document.getElementById('dotC').addEventListener('click',function(e){
  if(!dotScales.sorted||!dotScales.sorted.length)return;
  const rect=this.getBoundingClientRect();
  const mx=(e.clientX-rect.left)*(this.width/rect.width);
  const my=(e.clientY-rect.top)*(this.height/rect.height);
  const {sorted,col,ySc,pw,P,cfg}=dotScales;
  let cl=null,md=Infinity;
  sorted.forEach((d,i)=>{
    const x=P.l+(i/Math.max(sorted.length-1,1))*pw;
    const y=ySc(+d[col]);
    const dist=Math.sqrt((x-mx)**2+(y-my)**2);
    if(dist<md){md=dist;cl=d;}
  });
  const tt=document.getElementById('dot-tt');
  if(md<20&&cl){
    tt.style.display='block';
    const ex=[
      cl.KGV            ?`KGV: <strong>${fDE(cl.KGV,1)}</strong>`:'',
      cl.KGV_Forward    ?`Fwd KGV: <strong>${fDE(cl.KGV_Forward,1)}</strong>`:'',
      cl.EPS_naechste_5J_Pct!==''?`EPS 5J: <strong>${fDE(cl.EPS_naechste_5J_Pct,1)}%</strong>`:'',
      cl.PEG            ?`PEG: <strong>${fDE(cl.PEG,2)}</strong>`:'',
      cl.Perf_Monat_Pct!==''?`Perf 1M: <strong>${fDE(cl.Perf_Monat_Pct,1)}%</strong>`:'',
      cl.Perf_Jahr_Pct !==''?`Perf 1J: <strong>${fDE(cl.Perf_Jahr_Pct,1)}%</strong>`:'',
    ].filter(Boolean).join(' &nbsp;|&nbsp; ');
    tt.innerHTML=`
      <div style="margin-bottom:5px">
        <strong style="color:var(--ac);font-size:13px">${cl.Ticker}</strong>
        &nbsp;<span style="color:var(--tx)">${cl.Unternehmen||''}</span>
        &nbsp;<span style="color:var(--tx3);font-size:11px">(${cl.Sektor||''})</span>
      </div>
      <div style="font-size:11px;color:var(--tx2)">${ex}</div>
      <div style="margin-top:4px;font-size:10px;color:var(--ac)">
        ${cfg.label}: <strong style="font-size:13px">${fDE(+cl[col],cfg.dec)}${cfg.sfx}</strong>
      </div>`;
  }else{tt.style.display='none';}
});

// ============================================================
// SCATTER
// ============================================================
let scSc={};
function renderSC(){
  const sek=document.getElementById('sc-sf').value;
  const data=PD.filter(d=>(!sek||d.Sektor===sek)&&+d.KGV>0&&+d.KGV<100&&+d.EPS_naechste_5J_Pct>-50&&+d.EPS_naechste_5J_Pct<100);
  scSc={data};
  const cnv=document.getElementById('scC');
  const ctx=cnv.getContext('2d');
  const W=cnv.parentElement.offsetWidth||820,H=300;
  cnv.width=W;cnv.height=H;
  const bgC=cv('--bg2')||'#0D1520';
  const grC=cv('--brd')||'#1A2E45';
  const txC=cv('--tx4')||'#5A7A95';
  ctx.fillStyle=bgC;ctx.fillRect(0,0,W,H);
  if(!data.length)return;
  const P={t:28,r:20,b:48,l:54};
  const pw=W-P.l-P.r,ph=H-P.t-P.b;
  const xv=data.map(d=>+d.KGV),yv=data.map(d=>+d.EPS_naechste_5J_Pct);
  const xmx=Math.min(Math.ceil(Math.max(...xv)*1.1/10)*10,100);
  const ymn=Math.min(Math.floor(Math.min(...yv)/5)*5,0);
  const ymx=Math.ceil(Math.max(...yv)*1.1/5)*5;
  const xs=v=>P.l+(v/xmx)*pw;
  const ys=v=>P.t+ph-((v-ymn)/(ymx-ymn))*ph;
  scSc={data,xs,ys};
  for(let i=0;i<=5;i++){
    const xval=xmx*i/5,yval=ymn+(ymx-ymn)*i/5;
    ctx.strokeStyle=grC;ctx.lineWidth=1;
    ctx.beginPath();ctx.moveTo(xs(xval),P.t);ctx.lineTo(xs(xval),P.t+ph);ctx.stroke();
    ctx.beginPath();ctx.moveTo(P.l,ys(yval));ctx.lineTo(P.l+pw,ys(yval));ctx.stroke();
    ctx.fillStyle=txC;ctx.font='9px Segoe UI,sans-serif';
    ctx.textAlign='center';ctx.fillText(fDE(xval,0),xs(xval),P.t+ph+13);
    ctx.textAlign='right';ctx.fillText(fDE(yval,0)+'%',P.l-4,ys(yval)+3);
  }
  const SC={Technology:'#4DB8FF',Healthcare:'#2DD4A0',Financials:'#FFB347',
    'Consumer Cyclical':'#FF7BAC',Energy:'#FFD700',Industrials:'#A78BFA',
    'Consumer Defensive':'#6EE7B7',Utilities:'#93C5FD',
    'Communication Services':'#F472B6','Basic Materials':'#D4A574','Real Estate':'#FCA5A5'};
  data.forEach(d=>{
    ctx.beginPath();ctx.arc(xs(+d.KGV),ys(+d.EPS_naechste_5J_Pct),4,0,Math.PI*2);
    ctx.fillStyle=(SC[d.Sektor]||'#4DB8FF')+'99';ctx.fill();
  });
  ctx.fillStyle=txC;ctx.font='10px Segoe UI,sans-serif';ctx.textAlign='center';
  ctx.fillText('KGV (Trailing)',P.l+pw/2,H-5);
  ctx.save();ctx.translate(14,P.t+ph/2);ctx.rotate(-Math.PI/2);
  ctx.fillText('EPS-Wachstum 5J (%)',0,0);ctx.restore();
  ctx.fillText(`${data.length} Unternehmen | ${sek||'Alle Sektoren'}`,P.l+pw/2,P.t-8);
}
document.getElementById('scC').addEventListener('mousemove',function(e){
  if(!scSc.data||!scSc.data.length)return;
  const rect=this.getBoundingClientRect();
  const mx=(e.clientX-rect.left)*(this.width/rect.width);
  const my=(e.clientY-rect.top)*(this.height/rect.height);
  const {data,xs,ys}=scSc;
  let cl=null,md=Infinity;
  data.forEach(d=>{
    const dx=xs(+d.KGV)-mx,dy=ys(+d.EPS_naechste_5J_Pct)-my;
    const dist=Math.sqrt(dx*dx+dy*dy);if(dist<md){md=dist;cl=d;}
  });
  const tt=document.getElementById('sc-tt');
  if(md<18&&cl){
    tt.style.display='block';
    tt.innerHTML=`<strong style="color:var(--ac)">${cl.Ticker}</strong> – ${cl.Unternehmen||''}
      &nbsp;|&nbsp; KGV: <strong>${fDE(cl.KGV,1)}</strong>
      &nbsp;|&nbsp; EPS 5J: <strong>${fDE(cl.EPS_naechste_5J_Pct,1)}%</strong>
      &nbsp;|&nbsp; <span style="color:var(--tx3)">${cl.Sektor||''}</span>`;
  }else{tt.style.display='none';}
});
document.getElementById('sc-sf').addEventListener('change',renderSC);

// ============================================================
// RADAR
// ============================================================
const rsEl=document.getElementById('rs');
rsEl.addEventListener('input',onRS);
rsEl.addEventListener('blur',()=>setTimeout(hideAC,200));

function onRS(){
  const q=rsEl.value.toLowerCase().trim();
  const ac=document.getElementById('ac');
  if(q.length<1){ac.style.display='none';return;}
  const m=SD.filter(d=>d.Ticker.toLowerCase().includes(q)||(d.Unternehmen||'').toLowerCase().includes(q)).slice(0,8);
  if(!m.length){ac.style.display='none';return;}
  ac.innerHTML=m.map(d=>`<div class="ai" onclick="selR('${d.Ticker}')">
    <span><span class="ai-tk">${d.Ticker}</span>${d.Unternehmen||''}</span>
    <span class="ai-sc">Score: ${d.Score} | Rang ${d.Rang}</span>
  </div>`).join('');
  ac.style.display='block';
}
function hideAC(){document.getElementById('ac').style.display='none';}
function selR(tk){
  const d=SD.find(r=>r.Ticker===tk);if(!d)return;
  rsEl.value=d.Ticker+' – '+(d.Unternehmen||'');
  hideAC();drawRadar(d);
}
function drawRadar(d){
  const rw=document.getElementById('rw');
  const sc=+d.Score;
  const scCol=sc>=70?'#2DD4A0':sc>=45?'#FFB347':'#FF5C72';
  document.getElementById('rt').textContent=`${d.Rang}. ${d.Unternehmen} (${d.Ticker})`;
  document.getElementById('rsub').innerHTML=
    `Score: <span style="color:${scCol};font-weight:700;font-size:20px">${sc}/100</span>
     &nbsp;·&nbsp; Rang <strong>${d.Rang}</strong> von ${SD.length}`;
  rw.style.display='block';
  requestAnimationFrame(()=>_paintRadar(d,sc,scCol));
}
function _paintRadar(d,sc,scCol){
  const cnv=document.getElementById('rc');
  const ctx=cnv.getContext('2d');
  const W=Math.min(cnv.parentElement.offsetWidth||420,440);
  cnv.width=W;cnv.height=W;
  ctx.clearRect(0,0,W,W);
  const cx=W/2,cy=W/2,R=W*.30;
  const lbls=['EPS 5J Wachstum','Gewinnmarge','Forward KGV','KGV','PEG','Analyst'];
  const keys=['S_EPS5','S_Marge','S_FKGV','S_KGV','S_PEG','S_Analyst'];
  const vals=keys.map(k=>Math.max(0,Math.min(100,+d[k]||0)));
  const N=lbls.length;
  const bgC=cv('--bg2')||'#0D1520';
  const grC=cv('--brd')||'#1A2E45';
  const txC=cv('--tx2')||'#C8D8E8';
  const tx4C=cv('--tx4')||'#5A7A95';
  ctx.fillStyle=bgC;ctx.fillRect(0,0,W,W);
  for(let ring=1;ring<=5;ring++){
    const r=R*ring/5;ctx.strokeStyle=grC;ctx.lineWidth=1;ctx.beginPath();
    for(let i=0;i<=N;i++){
      const a=(i/N)*Math.PI*2-Math.PI/2;
      i===0?ctx.moveTo(cx+r*Math.cos(a),cy+r*Math.sin(a)):ctx.lineTo(cx+r*Math.cos(a),cy+r*Math.sin(a));
    }
    ctx.closePath();ctx.stroke();
    ctx.fillStyle=tx4C;ctx.font='8px Segoe UI,sans-serif';
    ctx.textAlign='center';ctx.textBaseline='middle';
    ctx.fillText((ring*20).toString(),cx+3,cy-r+4);
  }
  for(let i=0;i<N;i++){
    const a=(i/N)*Math.PI*2-Math.PI/2;ctx.strokeStyle=grC;ctx.lineWidth=1;
    ctx.beginPath();ctx.moveTo(cx,cy);ctx.lineTo(cx+R*Math.cos(a),cy+R*Math.sin(a));ctx.stroke();
  }
  ctx.beginPath();
  vals.forEach((v,i)=>{
    const a=(i/N)*Math.PI*2-Math.PI/2,r=R*v/100;
    i===0?ctx.moveTo(cx+r*Math.cos(a),cy+r*Math.sin(a)):ctx.lineTo(cx+r*Math.cos(a),cy+r*Math.sin(a));
  });
  ctx.closePath();ctx.fillStyle=scCol+'30';ctx.fill();
  ctx.strokeStyle=scCol;ctx.lineWidth=2.5;ctx.stroke();
  vals.forEach((v,i)=>{
    const a=(i/N)*Math.PI*2-Math.PI/2,r=R*v/100;
    ctx.beginPath();ctx.arc(cx+r*Math.cos(a),cy+r*Math.sin(a),5,0,Math.PI*2);
    ctx.fillStyle=scCol;ctx.fill();ctx.strokeStyle=bgC;ctx.lineWidth=1.5;ctx.stroke();
  });
  lbls.forEach((lb,i)=>{
    const a=(i/N)*Math.PI*2-Math.PI/2,lR=R+36;
    const lx=cx+lR*Math.cos(a),ly=cy+lR*Math.sin(a);
    ctx.fillStyle=txC;ctx.font='bold 10px Segoe UI,sans-serif';
    ctx.textAlign='center';ctx.textBaseline='middle';
    ctx.fillText(lb,lx,ly-8);ctx.fillStyle=scCol;ctx.font='9px Segoe UI,sans-serif';
    ctx.fillText(fDE(vals[i],0)+'/100',lx,ly+7);
  });
  ctx.textAlign='center';ctx.textBaseline='middle';
  ctx.fillStyle=scCol;ctx.font=`bold 30px Segoe UI,sans-serif`;
  ctx.fillText(sc.toString(),cx,cy-10);
  ctx.fillStyle=tx4C;ctx.font='11px Segoe UI,sans-serif';
  ctx.fillText('Score',cx,cy+12);
}

// START
renderDot();
renderSC();
"""

    closing = "\n</script>\n</body>\n</html>"
    return html + "\n<script>\n" + data_block + "\n" + js + closing

# ============================================================
# MAIL VERSENDEN
# ============================================================
def sende_mail(html):
    if not all([MAIL_SENDER,MAIL_PASSWORD,MAIL_RECEIVER]):
        print("❌ Credentials fehlen"); return False
    msg=MIMEMultipart("alternative")
    msg["Subject"]=f"Noahs Finanzblog 📈 – {datum_de}"
    msg["From"]=f"Noahs Finanzblog <{MAIL_SENDER}>"
    msg["To"]=MAIL_RECEIVER
    msg.attach(MIMEText(html,"html"))
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com",465) as s:
            s.login(MAIL_SENDER,MAIL_PASSWORD)
            s.sendmail(MAIL_SENDER,MAIL_RECEIVER,msg.as_string())
        print(f"✅ Mail an {MAIL_RECEIVER}"); return True
    except Exception as e:
        print(f"❌ {e}"); return False

# ============================================================
# MAIN
# ============================================================
if __name__=="__main__":
    print(f"📧 Starte Verarbeitung für: {datum_de}")
    
    # Falls main.py das Arbeitsverzeichnis verändert hat, arbeiten wir mit absoluten Pfaden
    root_dir = os.path.dirname(os.path.abspath(__file__)) if '__file__' in locals() else os.getcwd()
    abs_data_dir = os.path.join(root_dir, DATA_DIR)
    abs_docs_dir = os.path.join(root_dir, DOCS_DIR)
    
    df = lade_daten()

    # 1. Mail-HTML generieren & im Daten-Archiv sichern
    os.makedirs(abs_data_dir, exist_ok=True)
    mail_html = erstelle_mail(df)
    with open(os.path.join(abs_data_dir, f"{today_str}_newsletter.html"), "w", encoding="utf-8") as f:
        f.write(mail_html)
    print("💾 Statisches Mail-HTML im Daten-Archiv gespeichert.")

    # 2. Interaktives Dashboard für GitHub Pages bauen!
    os.makedirs(abs_docs_dir, exist_ok=True)
    dashboard_html = erstelle_dashboard(df) # <-- JETZT WIRD DAS INTERAKTIVE JS-DASHBOARD GENERIERT!
    
    with open(os.path.join(abs_docs_dir, "index.html"), "w", encoding="utf-8") as f:
        f.write(dashboard_html)
    print("🖥️ Interaktives Dashboard für GitHub Pages (docs/index.html) erfolgreich generiert!")

    # 3. Logo in docs/assets/ kopieren
    os.makedirs(os.path.join(abs_docs_dir, "assets"), exist_ok=True)
    logo_src = os.path.join(root_dir, "assets", "logo.png")
    logo_dst = os.path.join(abs_docs_dir, "assets", "logo.png")
    
    if os.path.exists(logo_src):
        shutil.copy2(logo_src, logo_dst)
        print("🖼️ Logo erfolgreich nach docs/assets/logo.png kopieren.")
    else:
        # Falls das Logo direkt im Hauptverzeichnis liegt
        logo_root_src = os.path.join(root_dir, "logo.png")
        if os.path.exists(logo_root_src):
            shutil.copy2(logo_root_src, logo_dst)
            print("🖼️ Logo aus Root erfolgreich nach docs/assets/logo.png kopiert.")
        else:
            print("⚠️ Hinweis: logo.png wurde weder im Hauptverzeichnis noch in /assets gefunden.")

    # 4. Newsletter-E-Mail absenden
    sende_erfolgreich = sende_mail(mail_html)
    if sende_erfolgreich:
        print("🚀 Mail-Versand erfolgreich abgeschlossen.")
    else:
        print("❌ Mail-Versand fehlgeschlagen.")
