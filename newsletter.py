import pandas as pd
import numpy as np
import smtplib
import os
import re
from email.mime.multipart import MIMEMultipart
from email.mime.text      import MIMEText
from datetime             import datetime

# ============================================================
# KONFIGURATION
# ============================================================

MAIL_SENDER   = os.environ.get("MAIL_SENDER",   "")
MAIL_PASSWORD = os.environ.get("MAIL_PASSWORD", "")
MAIL_RECEIVER = os.environ.get("MAIL_RECEIVER", "")

today_str = datetime.now().strftime("%Y-%m-%d")
DATA_DIR  = "data"

# ============================================================
# HILFSFUNKTIONEN (identisch zu R-Logik, in Python)
# ============================================================

def pct_zu_num(series):
    """'12.5%' → 12.5"""
    return pd.to_numeric(
        series.astype(str).str.extract(r'(-?[0-9]+\.?[0-9]*)')[0],
        errors='coerce'
    )

def zahl_bereinigen(series):
    """'$32.55', '-' → 32.55, NaN"""
    s = series.astype(str).str.strip()
    s = s.replace(['-', 'NA', 'N/A', '', 'nan'], np.nan)
    return pd.to_numeric(
        s.str.extract(r'(-?[0-9]+\.?[0-9]*)')[0],
        errors='coerce'
    )

def mrd_bereinigen(series):
    """'2.93B' → 2.93, '500M' → 0.5 (in Mrd.)"""
    s = series.astype(str).str.strip()
    wert    = pd.to_numeric(s.str.extract(r'(-?[0-9]+\.?[0-9]*)')[0], errors='coerce')
    einheit = s.str.extract(r'([TBMKtbmk])$')[0]
    
    result = wert.copy()
    result[einheit.isin(['T','t'])] = wert[einheit.isin(['T','t'])] * 1000
    result[einheit.isin(['B','b'])] = wert[einheit.isin(['B','b'])]
    result[einheit.isin(['M','m'])] = wert[einheit.isin(['M','m'])] / 1000
    result[einheit.isin(['K','k'])] = wert[einheit.isin(['K','k'])] / 1_000_000
    return result

def kurs_bereinigen(series):
    """'278.56 -2.21%' → 278.56"""
    return pd.to_numeric(
        series.astype(str).str.extract(r'^(-?[0-9]+\.?[0-9]*)')[0],
        errors='coerce'
    )

def eps_past_split(series, pos=0):
    """'5.91% 21.36%' → 5.91 (pos=0) oder 21.36 (pos=1)"""
    def extract(x):
        zahlen = re.findall(r'-?[0-9]+\.?[0-9]*', str(x))
        return float(zahlen[pos]) if len(zahlen) > pos else np.nan
    return series.apply(extract)

# ============================================================
# DATEN LADEN & AUFBEREITEN
# ============================================================

def lade_und_bereite_auf():
    """Lädt die CSVs und bereitet den Master-DataFrame auf."""
    
    sp_file = f"{DATA_DIR}/{today_str}_SP500_fundamentals.csv"
    ns_file = f"{DATA_DIR}/{today_str}_NASDAQ_fundamentals.csv"
    
    # Fallback: neueste verfügbare Datei laden
    import glob
    if not os.path.exists(sp_file):
        dateien = sorted(glob.glob(f"{DATA_DIR}/*_SP500_fundamentals.csv"))
        sp_file = dateien[-1] if dateien else None
    if not os.path.exists(ns_file):
        dateien = sorted(glob.glob(f"{DATA_DIR}/*_NASDAQ_fundamentals.csv"))
        ns_file = dateien[-1] if dateien else None
    
    if not sp_file or not ns_file:
        raise FileNotFoundError("Keine Datendateien gefunden!")
    
    print(f"📂 Lade: {sp_file}")
    print(f"📂 Lade: {ns_file}")
    
    sp = pd.read_csv(sp_file, dtype=str, low_memory=False)
    ns = pd.read_csv(ns_file, dtype=str, low_memory=False)
    
    # Merge: NASDAQ als Basis, SP500 ergänzen
    sp_only = sp[~sp['Ticker'].isin(ns['Ticker'])]
    df      = pd.concat([ns, sp_only], ignore_index=True)
    
    print(f"✅ Master: {len(df)} Unternehmen")
    
    # --- Umbenennen & Transformieren ---
    df = df.rename(columns={
        'Company':              'Unternehmen',
        'Sector':               'Sektor',
        'Industry':             'Branche',
        'Market Cap':           'Marktkapitalisierung_Mrd',
        'P/E':                  'KGV',
        'Forward P/E':          'KGV_Forward',
        'EPS (ttm)':            'EPS_TTM',
        'EPS this Y':           'EPS_dieses_Jahr_Pct',
        'EPS next Y Percentage':'EPS_naechstes_Jahr_Pct',
        'EPS next 5Y':          'EPS_naechste_5J_Pct',
        'EPS past 3/5Y':        'EPS_vergangene_3_5J',
        'PEG':                  'PEG',
        'Income':               'Gewinn_Mrd',
        'Sales':                'Umsatz_Mrd',
        'Profit Margin':        'Gewinnmarge_Pct',
        'Gross Margin':         'Bruttomarge_Pct',
        'Oper. Margin':         'Operative_Marge_Pct',
        'ROE':                  'ROE_Pct',
        'ROA':                  'ROA_Pct',
        'Perf Week':            'Perf_Woche_Pct',
        'Perf Month':           'Perf_Monat_Pct',
        'Perf Quarter':         'Perf_Quartal_Pct',
        'Perf Half Y':          'Perf_Halbjahr_Pct',
        'Perf Year':            'Perf_Jahr_Pct',
        'Perf YTD':             'Perf_YTD_Pct',
        'Perf 3Y':              'Perf_3J_Pct',
        'Perf 5Y':              'Perf_5J_Pct',
        'Perf 10Y':             'Perf_10J_Pct',
        '52W High':             'Hoch_52W',
        '52W Low':              'Tief_52W',
        'RSI (14)':             'RSI',
        'Recom':                'Analyst_Empfehlung',
        'Target Price':         'Kursziel',
        'Short Float':          'Short_Float_Pct',
        'Price':                'Preis',
        'Beta':                 'Beta',
        'Debt/Eq':              'Verschuldungsgrad',
    })
    
    # Numerisch transformieren
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
    
    # Prozent-Variablen
    pct_cols = [
        'EPS_dieses_Jahr_Pct', 'EPS_naechstes_Jahr_Pct',
        'EPS_naechste_5J_Pct', 'Gewinnmarge_Pct',
        'Bruttomarge_Pct', 'Operative_Marge_Pct',
        'ROE_Pct', 'ROA_Pct', 'Short_Float_Pct',
        'Perf_Woche_Pct', 'Perf_Monat_Pct', 'Perf_Quartal_Pct',
        'Perf_Halbjahr_Pct', 'Perf_Jahr_Pct', 'Perf_YTD_Pct',
        'Perf_3J_Pct', 'Perf_5J_Pct', 'Perf_10J_Pct',
    ]
    for col in pct_cols:
        if col in df.columns:
            df[col] = pct_zu_num(df[col])
    
    # EPS vergangene Jahre aufteilen
    df['EPS_vergangene_3J_Pct'] = eps_past_split(df['EPS_vergangene_3_5J'], pos=0)
    df['EPS_vergangene_5J_Pct'] = eps_past_split(df['EPS_vergangene_3_5J'], pos=1)
    
    # Analyst Upside berechnen
    df['Analyst_Upside_Pct'] = (
        (df['Kursziel'] - df['Preis']) / df['Preis'] * 100
    ).round(2)
    
    # Nur echte Aktien (USA, Preis vorhanden)
    df = df[
        df['Preis'].notna() &
        (df['Preis'] > 0) &
        df['Unternehmen'].notna()
    ].copy()
    
    return df

# ============================================================
# ANALYSE-FUNKTIONEN
# ============================================================

def top_performer(df, n=10):
    """Top N Aktien nach 1-Monats-Performance."""
    return (
        df[df['Perf_Monat_Pct'].notna()]
        .nlargest(n, 'Perf_Monat_Pct')
        [['Ticker','Unternehmen','Sektor','Preis',
          'Perf_Monat_Pct','Perf_Jahr_Pct','KGV_Forward','RSI']]
    )

def flop_performer(df, n=10):
    """Flop N Aktien nach 1-Monats-Performance."""
    return (
        df[df['Perf_Monat_Pct'].notna()]
        .nsmallest(n, 'Perf_Monat_Pct')
        [['Ticker','Unternehmen','Sektor','Preis',
          'Perf_Monat_Pct','Perf_Jahr_Pct','KGV_Forward','RSI']]
    )

def quality_screen(df, n=15):
    """
    Quality + Growth Screen:
    Hohe Gewinnmarge + starkes EPS-Wachstum + faire Bewertung
    """
    return (
        df[
            df['Gewinnmarge_Pct'].notna() &
            df['EPS_naechste_5J_Pct'].notna() &
            df['KGV_Forward'].notna() &
            (df['Gewinnmarge_Pct']    > 10)  &
            (df['EPS_naechste_5J_Pct'] > 10)  &
            (df['KGV_Forward']         > 0)   &
            (df['KGV_Forward']         < 40)  &
            (df['ROE_Pct'].fillna(0)   > 15)
        ]
        .assign(Score = lambda x:
            x['Gewinnmarge_Pct'].rank(pct=True)    * 0.25 +
            x['EPS_naechste_5J_Pct'].rank(pct=True)* 0.30 +
            x['ROE_Pct'].rank(pct=True)             * 0.25 +
            (-x['KGV_Forward']).rank(pct=True)      * 0.20
        )
        .nlargest(n, 'Score')
        [['Ticker','Unternehmen','Sektor','Preis','KGV_Forward',
          'EPS_naechste_5J_Pct','Gewinnmarge_Pct','ROE_Pct','Analyst_Upside_Pct']]
    )

def oversold_screen(df, n=10):
    """Überverkaufte Qualitätsaktien (RSI < 35, positive Fundamentals)."""
    return (
        df[
            df['RSI'].notna() &
            (df['RSI'] < 35) &
            (df['Gewinnmarge_Pct'].fillna(0) > 5) &
            (df['Marktkapitalisierung_Mrd'].fillna(0) > 1)
        ]
        .nsmallest(n, 'RSI')
        [['Ticker','Unternehmen','Sektor','Preis','RSI',
          'Perf_Monat_Pct','KGV_Forward','Analyst_Upside_Pct']]
    )

def sektor_uebersicht(df):
    """Durchschnittliche Performance und Bewertung pro Sektor."""
    return (
        df[df['Sektor'].notna() & (df['Sektor'] != 'nan')]
        .groupby('Sektor')
        .agg(
            Anzahl              = ('Ticker', 'count'),
            Perf_Monat_Avg      = ('Perf_Monat_Pct',   'mean'),
            Perf_Jahr_Avg       = ('Perf_Jahr_Pct',    'mean'),
            KGV_Forward_Median  = ('KGV_Forward',      'median'),
            Gewinnmarge_Avg     = ('Gewinnmarge_Pct',  'mean'),
            ROE_Avg             = ('ROE_Pct',          'mean'),
        )
        .round(2)
        .sort_values('Perf_Monat_Avg', ascending=False)
        .reset_index()
    )

# ============================================================
# HTML-NEWSLETTER ERSTELLEN
# ============================================================

def df_zu_html_tabelle(df, farbe_spalten=None):
    """
    Konvertiert DataFrame zu einer schön formatierten HTML-Tabelle.
    farbe_spalten: Liste von Spalten die grün/rot eingefärbt werden.
    """
    farbe_spalten = farbe_spalten or []
    
    def zelle_formatieren(val, spalte):
        try:
            num = float(val)
            if spalte in farbe_spalten:
                farbe = '#00C896' if num >= 0 else '#FF4444'
                pfeil = '▲' if num >= 0 else '▼'
                return f'<td style="color:{farbe};font-weight:bold">{pfeil} {num:+.2f}%</td>'
            return f'<td>{val}</td>'
        except (ValueError, TypeError):
            return f'<td>{val}</td>'
    
    html = '<table style="width:100%;border-collapse:collapse;font-size:13px;">'
    
    # Header
    html += '<tr>'
    for col in df.columns:
        html += f'<th style="background:#2D2D4E;color:#4A9EFF;padding:8px;text-align:left;border-bottom:2px solid #4A9EFF;">{col}</th>'
    html += '</tr>'
    
    # Zeilen
    for i, (_, row) in enumerate(df.iterrows()):
        bg = '#1E1E2E' if i % 2 == 0 else '#252535'
        html += f'<tr style="background:{bg};">'
        for col in df.columns:
            html += zelle_formatieren(row[col], col)
        html += '</tr>'
    
    html += '</table>'
    return html

def erstelle_newsletter(df):
    """Erstellt den kompletten HTML-Newsletter."""
    
    # Analysen durchführen
    top10       = top_performer(df, n=10)
    flop10      = flop_performer(df, n=10)
    quality     = quality_screen(df, n=15)
    oversold    = oversold_screen(df, n=10)
    sektoren    = sektor_uebersicht(df)
    
    # Markt-Zusammenfassung
    positiv_pct = (df['Perf_Monat_Pct'] > 0).mean() * 100
    avg_perf    = df['Perf_Monat_Pct'].mean()
    n_oversold  = (df['RSI'] < 30).sum()
    n_overbought= (df['RSI'] > 70).sum()
    
    html = f"""
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  body         {{ font-family: 'Segoe UI', Arial, sans-serif;
                 background: #0F0F1A; color: #E0E0E0;
                 margin: 0; padding: 20px; }}
  .header      {{ background: linear-gradient(135deg, #1E1E3F, #2D2D5F);
                 padding: 30px; border-radius: 12px; margin-bottom: 20px; }}
  h1           {{ color: #4A9EFF; margin: 0; font-size: 26px; }}
  .subtitle    {{ color: #888; font-size: 13px; margin-top: 6px; }}
  .section     {{ background: #1E1E2E; border-radius: 10px;
                 padding: 20px; margin: 15px 0;
                 border-left: 4px solid #4A9EFF; }}
  h2           {{ color: #4A9EFF; font-size: 16px; margin-top: 0; }}
  .metric-row  {{ display: flex; gap: 12px; flex-wrap: wrap; margin-bottom: 20px; }}
  .metric      {{ background: #252535; border-radius: 8px;
                 padding: 15px 20px; flex: 1; min-width: 140px; text-align: center; }}
  .metric-val  {{ font-size: 24px; font-weight: bold; color: #4A9EFF; }}
  .metric-lbl  {{ font-size: 11px; color: #888; margin-top: 4px; }}
  .positive    {{ color: #00C896 !important; }}
  .negative    {{ color: #FF4444 !important; }}
  td           {{ padding: 7px 8px; border-bottom: 1px solid #2E2E3E; color: #E0E0E0; }}
  .footer      {{ text-align: center; color: #555;
                 font-size: 11px; margin-top: 30px; padding: 20px; }}
</style>
</head>
<body>

<div class="header">
  <h1>📈 Daily Market Intelligence</h1>
  <div class="subtitle">
    {today_str} | {len(df):,} Aktien analysiert | Generiert um {datetime.now().strftime("%H:%M")} Uhr
  </div>
</div>

<!-- MARKT-ZUSAMMENFASSUNG -->
<div class="section">
  <h2>🌍 Markt-Überblick (1 Monat)</h2>
  <div class="metric-row">
    <div class="metric">
      <div class="metric-val {'positive' if avg_perf >= 0 else 'negative'}" 
           style="color:{'#00C896' if avg_perf >= 0 else '#FF4444'}">
        {avg_perf:+.2f}%
      </div>
      <div class="metric-lbl">Ø Performance (1M)</div>
    </div>
    <div class="metric">
      <div class="metric-val">{positiv_pct:.1f}%</div>
      <div class="metric-lbl">Aktien im Plus (1M)</div>
    </div>
    <div class="metric">
      <div class="metric-val" style="color:#00C896">{n_oversold}</div>
      <div class="metric-lbl">Überverkauft (RSI&lt;30)</div>
    </div>
    <div class="metric">
      <div class="metric-val" style="color:#FF4444">{n_overbought}</div>
      <div class="metric-lbl">Überkauft (RSI&gt;70)</div>
    </div>
    <div class="metric">
      <div class="metric-val">{len(df):,}</div>
      <div class="metric-lbl">Aktien gesamt</div>
    </div>
  </div>
</div>

<!-- SEKTOR-ÜBERSICHT -->
<div class="section">
  <h2>🏭 Sektor-Performance</h2>
  {df_zu_html_tabelle(sektoren, farbe_spalten=['Perf_Monat_Avg','Perf_Jahr_Avg'])}
</div>

<!-- TOP PERFORMER -->
<div class="section">
  <h2>🏆 Top 10 Performer (1 Monat)</h2>
  {df_zu_html_tabelle(top10.round(2), farbe_spalten=['Perf_Monat_Pct','Perf_Jahr_Pct'])}
</div>

<!-- FLOP PERFORMER -->
<div class="section">
  <h2>📉 Flop 10 Performer (1 Monat)</h2>
  {df_zu_html_tabelle(flop10.round(2), farbe_spalten=['Perf_Monat_Pct','Perf_Jahr_Pct'])}
</div>

<!-- QUALITY SCREEN -->
<div class="section">
  <h2>⭐ Quality & Growth Screen</h2>
  <p style="color:#888;font-size:12px;margin-top:0">
    Filter: Gewinnmarge &gt;10% | EPS-Wachstum 5J &gt;10% | KGV Forward &lt;40 | ROE &gt;15%
  </p>
  {df_zu_html_tabelle(quality.round(2), farbe_spalten=['EPS_naechste_5J_Pct','Analyst_Upside_Pct'])}
</div>

<!-- OVERSOLD SCREEN -->
<div class="section">
  <h2>🎯 Überverkaufte Qualitätsaktien (RSI &lt; 35)</h2>
  <p style="color:#888;font-size:12px;margin-top:0">
    Potenzielle Kaufgelegenheiten: technisch überverkauft bei soliden Fundamentals
  </p>
  {df_zu_html_tabelle(oversold.round(2), farbe_spalten=['Perf_Monat_Pct','Analyst_Upside_Pct'])}
</div>

<div class="footer">
  Automatisch generiert durch Finance Pipeline auf GitHub Actions<br>
  ⚠️ Kein Anlageberatung – nur zur persönlichen Information
</div>

</body>
</html>
"""
    return html

# ============================================================
# MAIL VERSENDEN
# ============================================================

def sende_newsletter(html_content):
    """Versendet den Newsletter per Gmail SMTP."""
    
    if not MAIL_SENDER or not MAIL_PASSWORD or not MAIL_RECEIVER:
        print("❌ Mail-Credentials fehlen – Newsletter nicht versendet.")
        print(f"   MAIL_SENDER:   {'✅' if MAIL_SENDER else '❌'}")
        print(f"   MAIL_PASSWORD: {'✅' if MAIL_PASSWORD else '❌'}")
        print(f"   MAIL_RECEIVER: {'✅' if MAIL_RECEIVER else '❌'}")
        return False
    
    msg            = MIMEMultipart("alternative")
    msg["Subject"] = f"📈 Daily Market Intelligence | {today_str}"
    msg["From"]    = MAIL_SENDER
    msg["To"]      = MAIL_RECEIVER
    msg.attach(MIMEText(html_content, "html"))
    
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(MAIL_SENDER, MAIL_PASSWORD)
            server.sendmail(MAIL_SENDER, MAIL_RECEIVER, msg.as_string())
        print(f"✅ Newsletter erfolgreich versendet an {MAIL_RECEIVER}")
        return True
    except Exception as e:
        print(f"❌ Fehler beim Versenden: {e}")
        return False

# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":
    print(f"📧 Starte Newsletter-Generierung: {today_str}")
    
    # 1. Daten laden
    df = lade_und_bereite_auf()
    
    # 2. Newsletter erstellen
    html = erstelle_newsletter(df)
    
    # 3. HTML lokal speichern (zur Kontrolle)
    with open(f"data/{today_str}_newsletter.html", "w", encoding="utf-8") as f:
        f.write(html)
    print(f"💾 HTML gespeichert: data/{today_str}_newsletter.html")
    
    # 4. Mail versenden
    sende_newsletter(html)