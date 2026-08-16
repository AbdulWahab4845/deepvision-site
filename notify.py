import os
import smtplib
from email.mime.text import MIMEText

# These come from Railway's Variables tab - never hardcode credentials in code.
SMTP_EMAIL = os.environ.get("SMTP_EMAIL", "")
SMTP_APP_PASSWORD = os.environ.get("SMTP_APP_PASSWORD", "")
NOTIFY_TO = os.environ.get("NOTIFY_TO", SMTP_EMAIL)


def send_notification_email(values: dict) -> None:
    """
    Send an email to the studio inbox whenever the contact form is submitted.

    Reply-To is set to the visitor's own email address, so replying to this
    notification in Gmail (or any mail app) goes straight back to them -
    no separate reply system on the website is needed.
    """
    if not SMTP_EMAIL or not SMTP_APP_PASSWORD:
        # Not configured yet - don't break the form, just skip silently.
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
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=10) as server:
            server.login(SMTP_EMAIL, SMTP_APP_PASSWORD)
            server.sendmail(SMTP_EMAIL, [NOTIFY_TO], msg.as_string())
    except Exception as e:
        # Never let an email failure break the contact form submission.
        print(f"Email notification failed: {e}")
