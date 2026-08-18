import random
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from fastapi import BackgroundTasks, Depends, FastAPI, Form, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import desc
from sqlalchemy.orm import Session
from database import Base, engine, get_db
from models import Inquiry, OtpCode
from notify import send_notification_email, send_otp_email

OTP_EXPIRY_MINUTES = 10
OTP_MAX_ATTEMPTS = 5

BASE_DIR = Path(__file__).resolve().parent
Base.metadata.create_all(bind=engine)

app = FastAPI(title="DeepVision.ai")

app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
PHONE_RE = re.compile(r"^[0-9+\-().\s]{7,20}$")


def nav_context(active: str) -> dict:
    return {
        "nav_items": [
            {"href": "/", "label": "Home", "key": "home"},
            {"href": "/about", "label": "About", "key": "about"},
            {"href": "/contact", "label": "Contact", "key": "contact"},
        ],
        "active": active,
    }


@app.get("/")
async def home(request: Request):
    return templates.TemplateResponse(request, "index.html", {**nav_context("home")})


@app.get("/about")
async def about(request: Request):
    return templates.TemplateResponse(request, "about.html", {**nav_context("about")})


@app.get("/contact")
async def contact_get(request: Request):
    return templates.TemplateResponse(
        request, "contact.html", {**nav_context("contact"), "errors": {}, "values": {}}
    )


@app.post("/contact/send-otp")
async def send_otp(email: str = Form(""), db: Session = Depends(get_db)):
    email = email.strip()
    if not email or not EMAIL_RE.match(email):
        return JSONResponse({"ok": False, "error": "Please enter a valid email address first."}, status_code=422)

    code = f"{random.randint(0, 999999):06d}"
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=OTP_EXPIRY_MINUTES)

    otp = OtpCode(email=email, code=code, expires_at=expires_at)
    db.add(otp)
    db.commit()

    sent = send_otp_email(email, code)
    if not sent:
        return JSONResponse(
            {"ok": False, "error": "Couldn't send the verification email. Please try again in a moment."},
            status_code=502,
        )

    return JSONResponse({"ok": True, "message": f"Code sent to {email}. It expires in {OTP_EXPIRY_MINUTES} minutes."})


@app.post("/contact")
async def contact_post(
    request: Request,
    background_tasks: BackgroundTasks,
    name: str = Form(""),
    email: str = Form(""),
    phone: str = Form(""),
    company: str = Form(""),
    interest: str = Form(""),
    message: str = Form(""),
    otp: str = Form(""),
    db: Session = Depends(get_db),
):
    values = {
        "name": name.strip(),
        "email": email.strip(),
        "phone": phone.strip(),
        "company": company.strip(),
        "interest": interest.strip(),
        "message": message.strip(),
    }
    otp = otp.strip()
    errors = {}
    if not values["name"]:
        errors["name"] = "Please tell us your name."
    if not values["email"]:
        errors["email"] = "Please add an email so we can reply."
    elif not EMAIL_RE.match(values["email"]):
        errors["email"] = "That email address doesn't look right."
    if values["phone"] and not PHONE_RE.match(values["phone"]):
        errors["phone"] = "That phone number doesn't look right."
    if not values["message"]:
        errors["message"] = "Let us know a little about your project."

    otp_record = None
    if not errors.get("email"):
        if not otp:
            errors["otp"] = "Please verify your email with the code we sent."
        else:
            otp_record = (
                db.query(OtpCode)
                .filter(OtpCode.email == values["email"], OtpCode.verified == False)  # noqa: E712
                .order_by(desc(OtpCode.created_at))
                .first()
            )
            if not otp_record:
                errors["otp"] = "Please request a verification code first."
            elif otp_record.attempts >= OTP_MAX_ATTEMPTS:
                errors["otp"] = "Too many attempts. Please request a new code."
            elif otp_record.expires_at < datetime.now(timezone.utc):
                errors["otp"] = "That code expired. Please request a new one."
            elif otp_record.code != otp:
                otp_record.attempts += 1
                db.commit()
                errors["otp"] = "That code doesn't match. Please check and try again."

    if errors:
        return templates.TemplateResponse(
            request,
            "contact.html",
            {**nav_context("contact"), "errors": errors, "values": values},
            status_code=422,
        )

    inquiry = Inquiry(**values)
    db.add(inquiry)

    if otp_record:
        otp_record.verified = True

    db.commit()

    # Offload email sending to background task
    background_tasks.add_task(send_notification_email, values)

    return templates.TemplateResponse(
        request,
        "contact.html",
        {
            **nav_context("contact"),
            "errors": {},
            "values": {},
            "success": True,
            "sent_name": values["name"],
        },
    )


@app.get("/admin/inquiries")
async def admin_inquiries(request: Request, db: Session = Depends(get_db)):
    inquiries = db.query(Inquiry).order_by(desc(Inquiry.received_at)).all()
    return templates.TemplateResponse(
        request,
        "admin_inquiries.html",
        {**nav_context(""), "inquiries": inquiries},
    )
