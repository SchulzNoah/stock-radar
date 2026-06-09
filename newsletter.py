import pandas as pd
import numpy as np
import smtplib
import os, re, glob, json, shutil
from email.mime.multipart import MIMEMultipart
from email.mime.text      import MIMEText
from datetime import datetime

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
# HILFSFUNKTIONEN ZUR DATENBEREINIGUNG
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
# DATEN LADEN & PIPELINE
# ============================================================
def lade_daten():
    sp_f = sorted(glob.glob(f"{DATA_DIR}/*_SP500_fundamentals.csv"))
    ns_f = sorted(glob.glob(f"{DATA_DIR}/*_NASDAQ_fundamentals.csv"))
    if not sp_f or not ns_f: raise FileNotFoundError("Keine fundamentalen CSV-Dateien im Ordner gefunden!")
    sp = pd.read_csv(sp_f[-1], dtype=str, low_memory=False)
    ns = pd.read_csv(ns_f[-1], dtype=str, low_memory=False)
    print(f"SP500 Datensätze: {len(sp)} | NASDAQ Datensätze: {len(ns)}")
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
    print(f"Master-Dataframe erstellt: {len(df)} gültige Unternehmen"); return df

# ============================================================
# SCORING ENGINE
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
# STATISCHER NEWSLETTER (MAIL-GENERIERUNG)
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
 Keine Anlageberatung – Newsletter erstellt von <a href="https://www.linkedin.com/in/noah-schulz-971031301/" target="_blank" style="color:#4DB8FF;text-decoration:none;">Noah Schulz</a>
</div>
</div></body></html>"""

# ============================================================
# INTERAKTIVE WEBSEITE (DASHBOARD-GENERIERUNG)
# ============================================================
def erstelle_dashboard(df):
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

    wl_json  = wl_df.fillna("").to_json(orient="records")
    qs_json  = qs_df.fillna("").to_json(orient="records")
    pd_json  = pd_df.fillna("").to_json(orient="records")
    sc_json  = sc_df.fillna("").to_json(orient="records")
    sek_json = json.dumps(sek_list)

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

    # HTML/CSS/JS als reiner raw string – alle JavaScript-Klammern sind unberührt!
    html = """<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Noahs Finanzblog 📈 – Duisburg Analytica</title>
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

/* WATCHLIST SPEZIFISCH: LIVE-GRAPH */
#kgv-plot {
  min-height: 50px;
}

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
}
</style>
</head>
<body>

<div class="hdr">
  <div class="hdr-left">
    <img class="hdr-logo" src="assets/logo.png" alt="Logo" onerror="this.style.display='none'">
    <div class="hdr-text">
      <h1>Noahs Finanzblog <span>📈</span></h1>
      <div class="sub" id="hdr-date">Lade Datum...</div>
    </div>
  </div>
  <div class="hdr-right">
    <div class="tgl-wrap">
      <span>☀️</span>
      <label class="tgl">
        <input type="checkbox" id="theme-checkbox" onchange="toggleTheme()">
        <span class="tgl-slider"></span>
      </label>
      <span>🌙</span>
    </div>
  </div>
</div>

<div class="sec">
  <div class="sec-title">🌍 Marktübersicht</div>
  <div class="mg">
    <div class="mc"><div class="mv" id="m-perf">-</div><div class="ml">Ø Perf. 1M</div></div>
    <div class="mc"><div class="mv" id="m-pos">-</div><div class="ml">Im Plus (1M)</div></div>
    <div class="mc"><div class="mv" id="m-over">-</div><div class="ml">Überverkauft (RSI&lt;30)</div></div>
    <div class="mc"><div class="mv" id="m-over2">-</div><div class="ml">Überkauft (RSI&gt;70)</div></div>
    <div class="mc"><div class="mv" id="m-ges">-</div><div class="ml">Analysiert</div></div>
  </div>
</div>

<div class="sec">
  <div class="sec-title">🔍 Interaktives Aktien-Radar</div>
  <div class="sec-sub">Tippe einen Ticker oder Namen ein, um das detaillierte mathematische Scoring aus dem Multi-Faktor-Modell live abzufragen.</div>
  <div class="sw">
    <input type="text" class="si" id="radar-search" placeholder="Ticker oder Firmenname suchen..." oninput="searchRadar()">
    <div class="al" id="radar-results"></div>
  </div>
  <div id="rw">
    <div class="rt" id="r-title">-</div>
    <div class="rs" id="r-score">-</div>
  </div>
</div>

<div class="sec">
  <div class="sec-title">⭐ Live Watchlist Analyse</div>
  <div class="sec-sub">Diese Tabelle und Visualisierung wird asynchron direkt aus den aktuellen Fundamental-CSVs deiner S&amp;P 500 und NASDAQ Datensätze gespeist.</div>
  <div class="tw" style="margin-bottom: 15px;">
    <table class="dt" id="watchlist-table">
      <thead>
        <tr>
          <th>Ticker</th>
          <th>KGV (ttm)</th>
          <th>Forward KGV</th>
          <th>PEG Ratio</th>
        </tr>
      </thead>
      <tbody>
        <tr><td colspan="4" style="text-align:center; padding:20px; color:var(--tx4);">Lade Daten über Fetch...</td></tr>
      </tbody>
    </table>
  </div>
  <div id="kgv-plot"></div>
</div>

<div class="sec">
  <div class="sec-title">🏆 Top Rangliste (Multi-Faktor-Modell)</div>
  <div class="score-info">
    Das Scoring basiert auf einer prozentualen Rang-Gewichtung: <strong>30% EPS-Wachstum nä. 5 Jahre</strong>, <strong>20% Gewinnmarge</strong>, <strong>20% Forward KGV</strong>, <strong>15% Aktuelles KGV</strong>, <strong>10% PEG Ratio</strong> und <strong>5% Analysten-Empfehlung</strong>.
  </div>
  <div class="fb">
    <div class="fg"><span class="fl">Sektor</span>
      <select class="fs" id="f-sektor" onchange="filterScore()"><option value="">Alle Sektoren</option></select>
    </div>
    <div class="fg"><span class="fl">Mindest-Score</span>
      <input type="number" class="fi" id="f-score" min="0" max="100" placeholder="z.B. 70" oninput="filterScore()">
    </div>
    <div class="fg"><span class="fl">Suche</span>
      <input type="text" class="fi" id="f-search" placeholder="Ticker..." oninput="filterScore()">
    </div>
    <button class="fr" onclick="resetScoreFilter()">Reset</button>
  </div>
  <div class="tw">
    <table class="dt" id="score-table">
      <thead>
        <tr>
          <th onclick="sortScore(0)">Rang</th>
          <th onclick="sortScore(1)">Ticker</th>
          <th onclick="sortScore(2)">Unternehmen</th>
          <th onclick="sortScore(3)">Sektor</th>
          <th onclick="sortScore(4)">Score</th>
          <th onclick="sortScore(5)">KGV Fwd</th>
          <th onclick="sortScore(6)">EPS 5J</th>
          <th onclick="sortScore(7)">Marge</th>
        </tr>
      </thead>
      <tbody></tbody>
    </table>
  </div>
  <div class="pg" id="score-pg"></div>
</div>

<div class="footer">
  Keine Anlageberatung · Datenaktualisierung automatisiert über GitHub Actions · Erstellt von Noah Schulz
</div>

<script>
""" + data_block + """
// ============================================================
// CORE APPLICATION LOGIC (RAW STRINGS - PROTECTED BRACES)
// ============================================================
let scoreFiltered = [...SD];
let scoreSortCol = 0;
let scoreSortAsc = true;
let scorePage = 1;
const scorePageSize = 15;

document.addEventListener("DOMContentLoaded", () => {
  // Theme Initialisierung
  const savedTheme = localStorage.getItem("theme") || "dark";
  if (savedTheme === "light") {
    document.documentElement.classList.add("light");
    document.getElementById("theme-checkbox").checked = true;
  }
  
  // Statische Kennzahlen befüllen
  document.getElementById("hdr-date").innerText = DATUM;
  document.getElementById("m-perf").innerText = (AVG_PERF >= 0 ? "+" : "") + AVG_PERF.toFixed(2) + "%";
  if (AVG_PERF < 0) document.getElementById("m-perf").classList.add("c-neg");
  else document.getElementById("m-perf").classList.add("c-pos");
  
  document.getElementById("m-pos").innerText = POS_PCT.toFixed(1) + "%";
  document.getElementById("m-over").innerText = N_OVER;
  document.getElementById("m-over2").innerText = N_OVER2;
  document.getElementById("m-ges").innerText = N_GES;
  
  // Sektor-Filter Optionen bauen
  const sel = document.getElementById("f-sektor");
  SEK.forEach(s => {
    const o = document.createElement("option");
    o.value = s; o.innerText = s; sel.appendChild(o);
  });
  
  // Tabellen-Rendering starten
  filterScore();
  
  // HIER DER FIX: Startet den asynchronen Fetch der beiden CSVs relativ vom docs/-Verzeichnis aus
  ladeDatenVomServer();
});

// ============================================================
// REVOLUTIONÄRER LIVE-FETCH BEIDER CSV-DATEIEN
// ============================================================
async function ladeDatenVomServer() {
  try {
    const [resSP500, resNasdaq] = await Promise.all([
      fetch('../data/SP500_fundamentals.csv'),
      fetch('../data/NASDAQ_fundamentals.csv')
    ]);
    
    let combinedStocks = [];
    if (resSP500.ok) combinedStocks = combinedStocks.concat(csvToObjects(await resSP500.text()));
    if (resNasdaq.ok) combinedStocks = combinedStocks.concat(csvToObjects(await resNasdaq.text()));
    
    stockData = combinedStocks.filter(stock => stock && stock.Ticker && watchlistTickers.includes(stock.Ticker));
    console.log("Watchlist Live-Daten geladen:", stockData);
    
    tabelleBauen();
    diagrammBauen();
  } catch (error) {
    console.error("Fehler beim Fetching der CSVs:", error);
    document.querySelector("#watchlist-table tbody").innerHTML = `<tr><td colspan="4" style="color:var(--neg); text-align:center;">Fehler beim asynchronen Laden der CSVs.</td></tr>`;
  }
}

function csvToObjects(csvText) {
  const lines = csvText.split(/\\r?\\n/);
  if (lines.length < 2) return [];
  const headers = lines[0].split(',');
  return lines.slice(1).map(line => {
    const data = line.split(',');
    if (data.length !== headers.length) return null;
    return headers.reduce((obj, header, index) => {
      obj[header.trim()] = data[index].trim();
      return obj;
    }, {});
  }).filter(Boolean);
}

function tabelleBauen() {
  const tbody = document.querySelector("#watchlist-table tbody");
  tbody.innerHTML = "";
  if(stockData.length === 0) {
    tbody.innerHTML = `<tr><td colspan="4" style="text-align:center; color:var(--tx4);">Keine Daten übereinstimmend.</td></tr>`;
    return;
  }
  stockData.forEach(stock => {
    const row = document.createElement("tr");
    row.innerHTML = `
      <td style="font-weight: bold; color: var(--ac);">${stock.Ticker || "-"}</td>
      <td>${stock['P/E'] || stock.P_E || "-"}</td>
      <td>${stock['Forward P/E'] || stock.Forward_P_E || "-"}</td>
      <td>${stock.PEG || "-"}</td>
    `;
    tbody.appendChild(row);
  });
}

function diagrammBauen() {
  const plotDiv = document.getElementById("kgv-plot");
  if (stockData.length === 0) {
    plotDiv.innerHTML = "<p style='font-size:12px;color:var(--tx4); text-align:center;'>Warte auf Watchlist-Daten...</p>";
    return;
  }
  let htmlPlot = '<div style="display:flex; flex-direction:column; gap:10px; width:100%; background:var(--bg3); padding:14px; border-radius:8px; border:1px solid var(--brd);">';
  htmlPlot += '<div style="font-size:11px; color:var(--tx4); font-weight:bold; margin-bottom:4px; text-transform:uppercase;">Visualisierung: Aktuelles KGV (Blau) vs. Forward KGV (Grün)</div>';
  
  stockData.forEach(stock => {
    const pe = parseFloat(stock['P/E'] || stock.P_E) || 0;
    const fpe = parseFloat(stock['Forward P/E'] || stock.Forward_P_E) || 0;
    if(pe > 0 || fpe > 0) {
      htmlPlot += `
        <div style="font-size:12px; margin-bottom:2px;"><strong>${stock.Ticker}</strong> <span style="color:var(--tx4); font-size:10px;">(KGV: ${pe || '-'} | F-KGV: ${fpe || '-'})</span></div>
        <div style="display:flex; flex-direction:column; gap:3px; width:100%; margin-bottom:6px; border-left:2px solid var(--brd2); padding-left:6px;">
          <div style="background:#1A7ACC; height:8px; width:${Math.min(pe * 2, 100)}%; max-width:400px; border-radius:0 4px 4px 0;" title="KGV: ${pe}"></div>
          <div style="background:#2DD4A0; height:8px; width:${Math.min(fpe * 2, 100)}%; max-width:400px; border-radius:0 4px 4px 0;" title="Forward KGV: ${fpe}"></div>
        </div>
      `;
    }
  });
  htmlPlot += '</div>';
  plotDiv.innerHTML = htmlPlot;
}

// ============================================================
// INTERAKTIVE RANGLISTE & FILTER LOGIK
// ============================================================
function filterScore() {
  const sek = document.getElementById("f-sektor").value;
  const minS = parseFloat(document.getElementById("f-score").value) || 0;
  const query = document.getElementById("f-search").value.toUpperCase().strip ? document.getElementById("f-search").value.toUpperCase().strip() : document.getElementById("f-search").value.toUpperCase();
  
  scoreFiltered = SD.filter(r => {
    if (sek && r.Sektor !== sek) return false;
    if (r.Score < minS) return false;
    if (query && !r.Ticker.includes(query) && !r.Unternehmen.toUpperCase().includes(query)) return false;
    return true;
  });
  
  scorePage = 1;
  renderScoreTable();
}

function resetScoreFilter() {
  document.getElementById("f-sektor").value = "";
  document.getElementById("f-score").value = "";
  document.getElementById("f-search").value = "";
  scoreFiltered = [...SD];
  scorePage = 1;
  renderScoreTable();
}

function renderScoreTable() {
  const tbody = document.querySelector("#score-table tbody");
  tbody.innerHTML = "";
  
  const start = (scorePage - 1) * scorePageSize;
  const end = Math.min(start + scorePageSize, scoreFiltered.length);
  const pageData = scoreFiltered.slice(start, end);
  
  if (pageData.length === 0) {
    tbody.innerHTML = '<tr><td colspan="8" style="text-align:center;padding:20px;color:var(--tx4)">Keine Treffer für die gewählten Filter.</td></tr>';
    renderPagination(0); return;
  }
  
  pageData.forEach(r => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td class="ts">${r.Rang}</td>
      <td class="tp">${r.Ticker}</td>
      <td class="tn" style="white-space:normal; max-width:180px;">${r.Unternehmen}</td>
      <td class="ts">${r.Sektor || "–"}</td>
      <td style="font-weight:700; color:var(--ac)">${r.Score.toFixed(1)}</td>
      <td>${r.KGV_Forward ? r.KGV_Forward.toFixed(1) : "–"}</td>
      <td class="${r.EPS_naechste_5J_Pct >= 0 ? 'td-pos' : 'td-neg'}">${r.EPS_naechste_5J_Pct ? r.EPS_naechste_5J_Pct.toFixed(1) + "%" : "–"}</td>
      <td class="${r.Gewinnmarge_Pct >= 0 ? 'td-pos' : 'td-neg'}">${r.Gewinnmarge_Pct ? r.Gewinnmarge_Pct.toFixed(1) + "%" : "–"}</td>
    `;
    tbody.appendChild(tr);
  });
  renderPagination(scoreFiltered.length);
}

function renderPagination(totalRows) {
  const wrap = document.getElementById("score-pg");
  wrap.innerHTML = "";
  const totalPages = Math.ceil(totalRows / scorePageSize);
  if (totalPages <= 1) return;
  
  const info = document.createElement("span");
  info.className = "pi";
  info.innerText = `Seite ${scorePage} von ${totalPages} (${totalRows} Treffer)`;
  wrap.appendChild(info);
  
  const btnPrev = document.createElement("button");
  btnPrev.className = "pb"; btnPrev.innerText = "◀";
  if (scorePage === 1) btnPrev.style.opacity = 0.4;
  else btnPrev.onclick = () => { scorePage--; renderScoreTable(); };
  wrap.appendChild(btnPrev);
  
  let startP = Math.max(1, scorePage - 2);
  let endP = Math.min(totalPages, startP + 4);
  if (endP - startP < 4) startP = Math.max(1, endP - 4);
  
  for (let i = startP; i <= endP; i++) {
    const b = document.createElement("button");
    b.className = "pb" + (i === scorePage ? " active" : "");
    b.innerText = i;
    b.onclick = () => { scorePage = i; renderScoreTable(); };
    wrap.appendChild(b);
  }
  
  const btnNext = document.createElement("button");
  btnNext.className = "pb"; btnNext.innerText = "▶";
  if (scorePage === totalPages) btnNext.style.opacity = 0.4;
  else btnNext.onclick = () => { scorePage++; renderScoreTable(); };
  wrap.appendChild(btnNext);
}

function sortScore(colIndex) {
  const keys = ["Rang", "Ticker", "Unternehmen", "Sektor", "Score", "KGV_Forward", "EPS_naechste_5J_Pct", "Gewinnmarge_Pct"];
  const key = keys[colIndex];
  
  if (scoreSortCol === colIndex) { scoreSortAsc = !scoreSortAsc; }
  else { scoreSortCol = colIndex; scoreSortAsc = true; }
  
  const ths = document.querySelectorAll("#score-table th");
  ths.forEach((th, idx) => {
    th.classList.remove("asc", "desc");
    if (idx === colIndex) th.classList.add(scoreSortAsc ? "asc" : "desc");
  });
  
  scoreFiltered.sort((a, b) => {
    let va = a[key]; let vb = b[key];
    if (va === null || va === undefined) return scoreSortAsc ? 1 : -1;
    if (vb === null || vb === undefined) return scoreSortAsc ? -1 : 1;
    if (typeof va === "string") return scoreSortAsc ? va.localeCompare(vb) : vb.localeCompare(va);
    return scoreSortAsc ? va - vb : vb - va;
  });
  
  scorePage = 1;
  renderScoreTable();
}

// ============================================================
# SEARCH ENGINE / RADAR DIALOG
// ============================================================
function searchRadar() {
  const q = document.getElementById("radar-search").value.toUpperCase();
  const resDiv = document.getElementById("radar-results");
  if (!q) { resDiv.style.display = "none"; return; }
  
  const matches = SD.filter(r => r.Ticker.includes(q) || r.Unternehmen.toUpperCase().includes(q)).slice(0, 6);
  if (matches.length === 0) { resDiv.innerHTML = '<div class="ai">Kein Unternehmen gefunden</div>'; resDiv.style.display = "block"; return; }
  
  resDiv.innerHTML = "";
  matches.forEach(m => {
    const div = document.createElement("div");
    div.className = "ai";
    div.innerHTML = `<div><span class="ai-tk">${m.Ticker}</span><span style="color:var(--tx2)">${m.Unternehmen}</span></div><span class="ai-sc">Score: ${m.Score.toFixed(1)}</span>`;
    div.onclick = () => {
      document.getElementById("r-title").innerText = `${m.Unternehmen} (${m.Ticker}) – Rang ${m.Rang}`;
      document.getElementById("r-score").innerHTML = `
        <div style="margin-top:10px; display:grid; grid-template-columns: repeat(auto-fit, minmax(130px, 1fr)); gap:10px; text-align:left;">
          <div style="background:var(--bg4); padding:10px; border-radius:6px; border:1px solid var(--brd);"><strong>Gesamt-Score:</strong> <span style="color:var(--ac);font-weight:bold;">${m.Score.toFixed(1)}</span></div>
          <div style="background:var(--bg4); padding:10px; border-radius:6px; border:1px solid var(--brd);"><strong>Forward KGV:</strong> ${m.KGV_Forward ? m.KGV_Forward.toFixed(1) : "–"}</div>
          <div style="background:var(--bg4); padding:10px; border-radius:6px; border:1px solid var(--brd);"><strong>KGV (ttm):</strong> ${m.KGV ? m.KGV.toFixed(1) : "–"}</div>
          <div style="background:var(--bg4); padding:10px; border-radius:6px; border:1px solid var(--brd);"><strong>PEG Ratio:</strong> ${m.PEG ? m.PEG.toFixed(2) : "–"}</div>
          <div style="background:var(--bg4); padding:10px; border-radius:6px; border:1px solid var(--brd);"><strong>EPS 5J Wachstum:</strong> ${m.EPS_naechste_5J_Pct ? m.EPS_naechste_5J_Pct.toFixed(1) + "%" : "–"}</div>
          <div style="background:var(--bg4); padding:10px; border-radius:6px; border:1px solid var(--brd);"><strong>Gewinnmarge:</strong> ${m.Gewinnmarge_Pct ? m.Gewinnmarge_Pct.toFixed(1) + "%" : "–"}</div>
        </div>
      `;
      document.getElementById("rw").style.display = "block";
      resDiv.style.display = "none";
      document.getElementById("radar-search").value = m.Ticker;
    };
    resDiv.appendChild(div);
  });
  resDiv.style.display = "block";
}

function toggleTheme() {
  const isLight = document.documentElement.classList.toggle("light");
  localStorage.setItem("theme", isLight ? "light" : "dark");
}
</script>
</body>
</html>"""
    return html

# ============================================================
# MAIN EXECUTOR (EXECUTION PIPELINE)
# ============================================================
if __name__ == "__main__":
    print(f"✨ Starte Daily Finance Automation: {datum_de} ✨")
    df = lade_daten()

    root_dir = os.path.dirname(os.path.abspath(__file__)) if "__file__" in locals() else os.getcwd()
    abs_data_dir = os.path.join(root_dir, DATA_DIR)
    abs_docs_dir = os.path.join(root_dir, DOCS_DIR)

    # 1. Statischen Newsletter erstellen und sichern
    os.makedirs(abs_data_dir, exist_ok=True)
    mail_html = erstelle_mail(df)
    with open(os.path.join(abs_data_dir, f"{today_str}_newsletter.html"), "w", encoding="utf-8") as f:
        f.write(mail_html)
    print("💾 Statisches Mail-HTML im Daten-Archiv gesichert.")

    # 2. Interaktives Dashboard generieren (Vollständige logische Verknüpfung)
    os.makedirs(abs_docs_dir, exist_ok=True)
    dashboard_html = erstelle_dashboard(df)
    with open(os.path.join(abs_docs_dir, "index.html"), "w", encoding="utf-8") as f:
        f.write(dashboard_html)
    print("🖥️ Interaktives Dashboard für GitHub Pages (docs/index.html) erfolgreich generiert!")

    # 3. Assets managen (Logo transferieren)
    os.makedirs(os.path.join(abs_docs_dir, "assets"), exist_ok=True)
    logo_src = os.path.join(root_dir, "assets", "logo.png")
    logo_dst = os.path.join(abs_docs_dir, "assets", "logo.png")
    
    if os.path.exists(logo_src):
        shutil.copy2(logo_src, logo_dst)
        print("🖼️ Logo erfolgreich nach docs/assets/logo.png kopiert.")
    else:
        logo_root_src = os.path.join(root_dir, "logo.png")
        if os.path.exists(logo_root_src):
            shutil.copy2(logo_root_src, logo_dst)
            print("🖼️ Logo aus Root erfolgreich nach docs/assets/logo.png kopiert.")
        else:
            print("⚠️ Warnung: logo.png konnte in den Quellverzeichnissen nicht gefunden werden.")

    print("🏁 Pipeline-Lauf erfolgreich beendet!")
