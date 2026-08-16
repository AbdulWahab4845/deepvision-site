import os
import requests

RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "")
NOTIFY_TO = os.environ.get("NOTIFY_TO", "")
FROM_EMAIL = os.environ.get("FROM_EMAIL", "onboarding@resend.dev")


def send_notification_email(values: dict) -> None:
    if not RESEND_API_KEY or not NOTIFY_TO:
        print("Email notification skipped: RESEND_API_KEY / NOTIFY_TO not set.")
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

    try:
        response = requests.post(
            "https://api.resend.com/emails",
            headers={
                "Authorization": f"Bearer {RESEND_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "from": FROM_EMAIL,
                "to": [NOTIFY_TO],
                "reply_to": values.get("email", ""),
                "subject": f"New inquiry from {values.get('name') or 'someone'} — DeepVision.ai",
                "text": body,
            },
            timeout=15,
        )
        response.raise_for_status()
        print("Email sent successfully via Resend!")
    except Exception as e:
        print("=== EMAIL FAILURE DETAILED LOG ===")
        print(f"Error: {e}")
        print("==================================")
