import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv

load_dotenv()

GMAIL_USER = os.getenv("GMAIL_USER")
GMAIL_PASSWORD = os.getenv("GMAIL_PASSWORD")

if not GMAIL_USER or not GMAIL_PASSWORD:
    raise RuntimeError("GMAIL_USER yoki GMAIL_PASSWORD topilmadi. .env faylini tekshiring.")


def send_verify_email(to_email: str, code: str):
    try:
        msg = MIMEMultipart()
        msg["From"] = GMAIL_USER
        msg["To"] = to_email
        msg["Subject"] = "Remote Control - Tasdiqlash kodi"
        body = f"""
        <h2>Salom!</h2>
        <p>Tasdiqlash kodingiz: <strong style='font-size:24px; color:#1B8EF8'>{code}</strong></p>
        <p>Kod 10 daqiqa davomida amal qiladi.</p>
        """
        msg.attach(MIMEText(body, "html"))
        server = smtplib.SMTP("smtp.gmail.com", 587)
        server.starttls()
        server.login(GMAIL_USER, GMAIL_PASSWORD)
        server.sendmail(GMAIL_USER, to_email, msg.as_string())
        server.quit()
        return True
    except Exception as e:
        print(f"Email xatosi: {e}")
        return False