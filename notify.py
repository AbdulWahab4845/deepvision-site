import os
import smtplib
import socket
import traceback
from email.mime.text import MIMEText

SMTP_EMAIL = os.environ.get("SMTP_EMAIL", "")
SMTP_APP_PASSWORD = os.environ.get("SMTP_APP_PASSWORD", "")
NOTIFY_TO = os.environ.get("NOTIFY_TO", SMTP_EMAIL)


def send_notification_email(values: dict) -> None:
    if not SMTP_EMAIL or not SMTP_APP_PASSWORD:
        print("Email notification skipped: SMTP_EMAIL / SMTP_APP_PASSWORD not set.")
        return

    body = (
        "New inquiry from the DeepVision.ai website\n\n"
        f"Name: {values.get('name', '')}\n"
        f"Email: {values.get('email', '')}\n"
        f"Phone: {values.get('phone') or '-'}\n"
        f"Company: {values.get('company') or '-'}\n"
        f"Interest: {values.get('interest') or '-'}\n\n"
        "Message:\n"
        f"{values.get('message', '')}\n\n"
        "---\n"
        "Just hit Reply to answer them directly."
    )
    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = f"New inquiry from {values.get('name') or 'someone'} — DeepVision.ai"
    msg["From"] = SMTP_EMAIL
    msg["To"] = NOTIFY_TO
    if values.get("email"):
        msg["Reply-To"] = values["email"]

    try:
        # Force IPv4, use port 465 with SSL directly (no STARTTLS handshake)
        addr_info = socket.getaddrinfo("smtp.gmail.com", 465, socket.AF_INET)
        ipv4_address = addr_info[0][4][0]
        server = smtplib.SMTP_SSL(ipv4_address, 465, timeout=15)
        server.ehlo("gmail.com")
        server.login(SMTP_EMAIL, SMTP_APP_PASSWORD)
        server.sendmail(SMTP_EMAIL, [NOTIFY_TO], msg.as_string())
        server.quit()
        print("Email sent successfully via port 465 SSL!")
    except Exception as e:
        print("=== EMAIL FAILURE DETAILED LOG ===")
        print(f"Error: {e}")
        traceback.print_exc()
        print("==================================")
