# DeepVision.ai — website

FastAPI site with three pages: Home, About, Contact.

No database. The contact form appends each inquiry as one line of JSON to
`data/inquiries.jsonl` on the server's disk — nothing external, nothing to
configure. Swap `save_inquiry()` in `main.py` for a real database call
later if you outgrow the file.

## Run locally

```bash
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --reload
```

Visit http://127.0.0.1:8000

## Structure

```
main.py                  routes: /, /about, /contact (GET + POST)
templates/                Jinja2 HTML (base.html + 3 pages)
static/style.css          all styling
data/inquiries.jsonl      created automatically on first submission
```

## Customizing

- Copy, team members, services: edit the templates directly.
- Colors/fonts: CSS variables at the top of `static/style.css`.
- Contact fields: add a `Form(...)` param in the `/contact` POST route in
  `main.py`, then add the matching `<input>` in `templates/contact.html`.
