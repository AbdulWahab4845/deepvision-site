import re
from pathlib import Path
from fastapi import Depends, FastAPI, Form, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import desc
from sqlalchemy.orm import Session
from database import Base, engine, get_db
from models import Inquiry
from notify import send_notification_email

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
@app.post("/contact")
async def contact_post(
    request: Request,
    name: str = Form(""),
    email: str = Form(""),
    phone: str = Form(""),
    company: str = Form(""),
    interest: str = Form(""),
    message: str = Form(""),
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
    if errors:
        return templates.TemplateResponse(
            request, "contact.html",
            {**nav_context("contact"), "errors": errors, "values": values},
            status_code=422,
        )
    inquiry = Inquiry(**values)
    db.add(inquiry)
    db.commit()

    send_notification_email(values)

    return templates.TemplateResponse(
        request, "contact.html",
        {**nav_context("contact"), "errors": {}, "values": {}, "success": True, "sent_name": values["name"]},
    )
@app.get("/admin/inquiries")
async def admin_inquiries(request: Request, db: Session = Depends(get_db)):
    inquiries = db.query(Inquiry).order_by(desc(Inquiry.received_at)).all()
    return templates.TemplateResponse(
        request,
        "admin_inquiries.html",
        {**nav_context(""), "inquiries": inquiries},
    )
