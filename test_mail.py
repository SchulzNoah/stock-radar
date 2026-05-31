import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime

def test_smtp_connection():
    print("=== 🧪 GITHUB ACTIONS SMTP TEST ===")
    
    # 1. Secrets auslesen
    sender = os.environ.get("MAIL_SENDER", "")
    password = os.environ.get("MAIL_PASSWORD", "")
    receiver = os.environ.get("MAIL_RECEIVER", "")
    
    # 2. Harter Check der Variablen (Zwingt GitHub zum Abbruch, falls leer)
    if not sender:
        raise ValueError("❌ 'MAIL_SENDER' ist leer! Überprüfe die GitHub Secrets.")
    if not password:
        raise ValueError("❌ 'MAIL_PASSWORD' ist leer! Überprüfe die GitHub Secrets.")
    if not receiver:
        raise ValueError("❌ 'MAIL_RECEIVER' ist leer! Überprüfe die GitHub Secrets.")
        
    print(f"📡 Versuche Verbindung über: {sender} an {receiver}")
    
    # 3. Einfache Test-Mail aufbauen
    msg = MIMEMultipart()
    msg["Subject"] = f"🧪 GitHub Pipeline Test | {datetime.now().strftime('%H:%M:%S')}"
    msg["From"] = f"Pipeline Tester <{sender}>"
    msg["To"] = receiver
    
    text = "Falls du das liest, funktionieren deine GitHub Secrets und das Google App-Passwort perfekt! 🎉"
    msg.attach(MIMEText(text, "plain"))
    
    # 4. Verbindungsaufbau mit hartem Fehler-Throw
    try:
        print("🔒 Stelle Verbindung zu smtp.gmail.com:465 her...")
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            print("🔑 Logge mit App-Passwort ein...")
            server.login(sender, password)
            
            print("📤 Sende Test-Mail...")
            server.sendmail(sender, receiver, msg.as_string())
            
        print("✅ ERFOLG! Die Mail wurde ohne Fehler an Google übergeben.")
        
    except Exception as e:
        print("❌ KRITISCHER SMTP FEHLER:")
        raise e # GitHub Actions wird rot und zeigt das genaue Problem im Log an

if __name__ == "__main__":
    test_smtp_connection()
