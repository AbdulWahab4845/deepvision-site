import os
import requests

RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "")
NOTIFY_TO = os.environ.get("NOTIFY_TO", "")
FROM_EMAIL = os.environ.get("FROM_EMAIL", "onboarding@resend.dev")

BREVO_API_KEY = os.environ.get("BREVO_API_KEY", "")
BREVO_SENDER_EMAIL = os.environ.get("BREVO_SENDER_EMAIL", "")
BREVO_SENDER_NAME = os.environ.get("BREVO_SENDER_NAME", "DeepVision.ai")


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


def send_otp_email(to_email: str, code: str) -> bool:
    """Send a 6-digit verification code to a site visitor via Brevo.

    Returns True on success, False on failure (never raises).
    """
    if not BREVO_API_KEY or not BREVO_SENDER_EMAIL:
        print("OTP email skipped: BREVO_API_KEY / BREVO_SENDER_EMAIL not set.")
        return False

    body = (
        f"Your DeepVision.ai verification code is: {code}\n\n"
        "This code expires in 10 minutes. If you didn't request this, "
        "you can safely ignore this email."
    )

    try:
        response = requests.post(
            "https://api.brevo.com/v3/smtp/email",
            headers={
                "api-key": BREVO_API_KEY,
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            json={
                "sender": {"email": BREVO_SENDER_EMAIL, "name": BREVO_SENDER_NAME},
                "to": [{"email": to_email}],
                "subject": "Your DeepVision.ai verification code",
                "textContent": body,
            },
            timeout=15,
        )
        response.raise_for_status()
        print(f"OTP email sent successfully via Brevo to {to_email}!")
        return True
    except Exception as e:
        print("=== OTP EMAIL FAILURE DETAILED LOG ===")
        print(f"Error: {e}")
        print("==================================")
        return False
