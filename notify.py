import os
import smtplib
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
        # Port 587 with starttls is much more reliable on cloud platforms like Railway
        server = smtplib.SMTP("smtp.gmail.com", 587, timeout=15)
        server.starttls()
        server.login(SMTP_EMAIL, SMTP_APP_PASSWORD)
        server.sendmail(SMTP_EMAIL, [NOTIFY_TO], msg.as_string())
        server.quit()
        print("Email sent successfully!")
    except Exception as e:
        print("=== EMAIL FAILURE DETAILED LOG ===")
        print(f"Error: {e}")
        traceback.print_exc()
        print("==================================")
