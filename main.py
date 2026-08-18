import os
import random
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from fastapi import BackgroundTasks, Depends, FastAPI, Form, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from sqlalchemy import desc
from sqlalchemy.orm import Session
from database import Base, engine, get_db
from models import Inquiry, OtpCode, User
from notify import send_notification_email, send_otp_email
from auth import (
    hash_password,
    verify_password,
    generate_totp_secret,
    get_totp_uri,
    verify_totp_code,
    qr_code_data_uri,
    get_user_by_email,
)

OTP_EXPIRY_MINUTES = 10
OTP_MAX_ATTEMPTS = 5

# Comma-separated list of emails that automatically get admin access
# (able to view /admin/inquiries). Set this in Railway Variables.
ADMIN_EMAILS = {
    e.strip().lower() for e in os.environ.get("ADMIN_EMAILS", "").split(",") if e.strip()
}

BASE_DIR = Path(__file__).resolve().parent
Base.metadata.create_all(bind=engine)

app = FastAPI(title="DeepVision.ai")
app.add_middleware(SessionMiddleware, secret_key=os.environ.get("SESSION_SECRET", "change-me-in-production"))

app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
PHONE_RE = re.compile(r"^[0-9+\-().\s]{7,20}$")


def as_aware_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def nav_context(active: str, request: Request = None) -> dict:
    items = [
        {"href": "/", "label": "Home", "key": "home"},
        {"href": "/about", "label": "About", "key": "about"},
        {"href": "/contact", "label": "Contact", "key": "contact"},
    ]
    if request is not None and request.session.get("user_id"):
        items.append({"href": "/logout", "label": "Logout", "key": "logout"})
    return {"nav_items": items, "active": active}


def require_login(request: Request):
    """Returns a redirect to /login if not logged in, otherwise None."""
    if not request.session.get("user_id"):
        return RedirectResponse(url="/login", status_code=303)
    return None


# ---- Pages that require login first ----

@app.get("/")
async def home(request: Request):
    redirect = require_login(request)
    if redirect:
        return redirect
    return templates.TemplateResponse(request, "index.html", {**nav_context("home", request)})


@app.get("/about")
async def about(request: Request):
    redirect = require_login(request)
    if redirect:
        return redirect
    return templates.TemplateResponse(request, "about.html", {**nav_context("about", request)})


@app.get("/contact")
async def contact_get(request: Request):
    redirect = require_login(request)
    if redirect:
        return redirect
    return templates.TemplateResponse(
        request, "contact.html", {**nav_context("contact", request), "errors": {}, "values": {}}
    )


@app.post("/contact/send-otp")
async def send_otp(request: Request, email: str = Form(""), db: Session = Depends(get_db)):
    redirect = require_login(request)
    if redirect:
        return JSONResponse({"ok": False, "error": "Please log in first."}, status_code=401)

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
    redirect = require_login(request)
    if redirect:
        return redirect

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
            elif as_aware_utc(otp_record.expires_at) < datetime.now(timezone.utc):
                errors["otp"] = "That code expired. Please request a new one."
            elif otp_record.code != otp:
                otp_record.attempts += 1
                db.commit()
                errors["otp"] = "That code doesn't match. Please check and try again."

    if errors:
        return templates.TemplateResponse(
            request,
            "contact.html",
            {**nav_context("contact", request), "errors": errors, "values": values},
            status_code=422,
        )

    inquiry = Inquiry(**values)
    db.add(inquiry)

    if otp_record:
        otp_record.verified = True

    db.commit()

    background_tasks.add_task(send_notification_email, values)

    return templates.TemplateResponse(
        request,
        "contact.html",
        {
            **nav_context("contact", request),
            "errors": {},
            "values": {},
            "success": True,
            "sent_name": values["name"],
        },
    )


# ---- Signup (open to the public) ----

@app.get("/signup")
async def signup_get(request: Request):
    if request.session.get("user_id"):
        return RedirectResponse(url="/", status_code=303)
    return templates.TemplateResponse(
        request, "signup.html", {**nav_context("signup", request), "errors": {}, "values": {}}
    )


@app.post("/signup")
async def signup_post(
    request: Request,
    name: str = Form(""),
    email: str = Form(""),
    password: str = Form(""),
    confirm_password: str = Form(""),
    db: Session = Depends(get_db),
):
    values = {"name": name.strip(), "email": email.strip().lower()}
    errors = {}

    if not values["name"]:
        errors["name"] = "Please enter your name."
    if not values["email"] or not EMAIL_RE.match(values["email"]):
        errors["email"] = "Please enter a valid email."
    elif get_user_by_email(db, values["email"]):
        errors["email"] = "An account with this email already exists."
    if len(password) < 8:
        errors["password"] = "Password must be at least 8 characters."
    elif password != confirm_password:
        errors["password"] = "Passwords don't match."

    if errors:
        return templates.TemplateResponse(
            request, "signup.html",
            {**nav_context("signup", request), "errors": errors, "values": values},
            status_code=422,
        )

    secret = generate_totp_secret()
    user = User(
        name=values["name"],
        email=values["email"],
        password_hash=hash_password(password),
        totp_secret=secret,
        totp_confirmed=False,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    request.session["pending_setup_user_id"] = user.id
    return RedirectResponse(url="/totp-setup", status_code=303)


@app.get("/totp-setup")
async def totp_setup_get(request: Request, db: Session = Depends(get_db)):
    user_id = request.session.get("pending_setup_user_id")
    if not user_id:
        return RedirectResponse(url="/signup", status_code=303)
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return RedirectResponse(url="/signup", status_code=303)

    uri = get_totp_uri(user.totp_secret, user.email)
    return templates.TemplateResponse(
        request, "totp_setup.html",
        {**nav_context("", request), "qr_data_uri": qr_code_data_uri(uri), "secret": user.totp_secret, "error": None},
    )


@app.post("/totp-setup")
async def totp_setup_post(request: Request, code: str = Form(""), db: Session = Depends(get_db)):
    user_id = request.session.get("pending_setup_user_id")
    if not user_id:
        return RedirectResponse(url="/signup", status_code=303)
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return RedirectResponse(url="/signup", status_code=303)

    if not verify_totp_code(user.totp_secret, code):
        uri = get_totp_uri(user.totp_secret, user.email)
        return templates.TemplateResponse(
            request, "totp_setup.html",
            {
                **nav_context("", request),
                "qr_data_uri": qr_code_data_uri(uri),
                "secret": user.totp_secret,
                "error": "That code didn't match. Try the current code from your app.",
            },
            status_code=422,
        )

    user.totp_confirmed = True
    if user.email in ADMIN_EMAILS:
        user.is_admin = True
    db.commit()

    was_admin_setup = request.session.get("pending_setup_was_admin", False)
    request.session.pop("pending_setup_user_id", None)
    request.session.pop("pending_setup_was_admin", None)
    request.session["user_id"] = user.id
    request.session["is_admin"] = user.is_admin

    if was_admin_setup and user.is_admin:
        return RedirectResponse(url="/admin/inquiries", status_code=303)
    return RedirectResponse(url="/", status_code=303)


# ---- Login (for normal users) ----

@app.get("/login")
async def login_get(request: Request):
    if request.session.get("user_id"):
        return RedirectResponse(url="/", status_code=303)
    return templates.TemplateResponse(request, "login.html", {**nav_context("login", request), "errors": {}, "values": {}})


@app.post("/login")
async def login_post(
    request: Request,
    email: str = Form(""),
    password: str = Form(""),
    db: Session = Depends(get_db),
):
    values = {"email": email.strip().lower()}
    user = get_user_by_email(db, values["email"])
    if not user or not verify_password(password, user.password_hash):
        return templates.TemplateResponse(
            request, "login.html",
            {**nav_context("login", request), "errors": {"form": "Wrong email or password."}, "values": values},
            status_code=422,
        )

    if not user.totp_confirmed:
        request.session["pending_setup_user_id"] = user.id
        return RedirectResponse(url="/totp-setup", status_code=303)

    request.session["pending_login_user_id"] = user.id
    return RedirectResponse(url="/login-totp", status_code=303)


@app.get("/login-totp")
async def login_totp_get(request: Request):
    if not request.session.get("pending_login_user_id"):
        return RedirectResponse(url="/login", status_code=303)
    return templates.TemplateResponse(request, "login_totp.html", {**nav_context("login", request), "error": None})


@app.post("/login-totp")
async def login_totp_post(request: Request, code: str = Form(""), db: Session = Depends(get_db)):
    user_id = request.session.get("pending_login_user_id")
    if not user_id:
        return RedirectResponse(url="/login", status_code=303)
    user = db.query(User).filter(User.id == user_id).first()
    if not user or not verify_totp_code(user.totp_secret, code):
        return templates.TemplateResponse(
            request, "login_totp.html",
            {**nav_context("login", request), "error": "That code didn't match. Try the current code from your app."},
            status_code=422,
        )

    request.session.pop("pending_login_user_id", None)

    if user.email in ADMIN_EMAILS and not user.is_admin:
        user.is_admin = True
        db.commit()

    request.session["user_id"] = user.id
    request.session["is_admin"] = user.is_admin
    return RedirectResponse(url="/", status_code=303)


# ---- Admin login (separate entry point, hidden from normal users) ----

@app.get("/admin/login")
async def admin_login_get(request: Request):
    if request.session.get("user_id") and request.session.get("is_admin"):
        return RedirectResponse(url="/admin/inquiries", status_code=303)
    return templates.TemplateResponse(
        request, "admin_login.html", {**nav_context("", request), "errors": {}, "values": {}}
    )


@app.post("/admin/login")
async def admin_login_post(
    request: Request,
    email: str = Form(""),
    password: str = Form(""),
    db: Session = Depends(get_db),
):
    values = {"email": email.strip().lower()}
    user = get_user_by_email(db, values["email"])

    if not user or not verify_password(password, user.password_hash):
        return templates.TemplateResponse(
            request, "admin_login.html",
            {**nav_context("", request), "errors": {"form": "Wrong email or password."}, "values": values},
            status_code=422,
        )

    if user.email not in ADMIN_EMAILS and not user.is_admin:
        return templates.TemplateResponse(
            request, "admin_login.html",
            {**nav_context("", request), "errors": {"form": "This account doesn't have admin access."}, "values": values},
            status_code=403,
        )

    if not user.totp_confirmed:
        request.session["pending_setup_user_id"] = user.id
        request.session["pending_setup_was_admin"] = True
        return RedirectResponse(url="/totp-setup", status_code=303)

    request.session["pending_admin_login_user_id"] = user.id
    return RedirectResponse(url="/admin/login-totp", status_code=303)


@app.get("/admin/login-totp")
async def admin_login_totp_get(request: Request):
    if not request.session.get("pending_admin_login_user_id"):
        return RedirectResponse(url="/admin/login", status_code=303)
    return templates.TemplateResponse(request, "admin_login_totp.html", {**nav_context("", request), "error": None})


@app.post("/admin/login-totp")
async def admin_login_totp_post(request: Request, code: str = Form(""), db: Session = Depends(get_db)):
    user_id = request.session.get("pending_admin_login_user_id")
    if not user_id:
        return RedirectResponse(url="/admin/login", status_code=303)
    user = db.query(User).filter(User.id == user_id).first()
    if not user or not verify_totp_code(user.totp_secret, code):
        return templates.TemplateResponse(
            request, "admin_login_totp.html",
            {**nav_context("", request), "error": "That code didn't match. Try the current code from your app."},
            status_code=422,
        )

    request.session.pop("pending_admin_login_user_id", None)
    if user.email in ADMIN_EMAILS and not user.is_admin:
        user.is_admin = True
        db.commit()

    request.session["user_id"] = user.id
    request.session["is_admin"] = user.is_admin
    return RedirectResponse(url="/admin/inquiries", status_code=303)


@app.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login", status_code=303)


# ---- Admin (must be logged in AND be an admin account) ----

@app.get("/admin/inquiries")
async def admin_inquiries(request: Request, db: Session = Depends(get_db)):
    if not request.session.get("user_id"):
        return RedirectResponse(url="/admin/login", status_code=303)
    if not request.session.get("is_admin"):
        return templates.TemplateResponse(
            request, "forbidden.html", {**nav_context("", request)}, status_code=403
        )

    inquiries = db.query(Inquiry).order_by(desc(Inquiry.received_at)).all()
    return templates.TemplateResponse(
        request,
        "admin_inquiries.html",
        {**nav_context("", request), "inquiries": inquiries},
    )
