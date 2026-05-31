# index.py
# -------------------------------------------------------
# FastAPI app — Vercel entry point & local dev server
# Run locally: uvicorn index:app --reload --port 8000
# -------------------------------------------------------

import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi             import FastAPI, Form, Request, Header
from fastapi.responses   import HTMLResponse, JSONResponse
from fastapi.templating  import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from dotenv              import load_dotenv

from email_service import send_email
from scheduler     import process_scheduled_emails
from logger        import load_history, save_record

load_dotenv()

CRON_SECRET = os.getenv("CRON_SECRET", "")

# ----------------------------------------------------------
# Build absolute paths — critical for Windows compatibility
# Path(__file__).resolve() gives the FULL absolute path to
# index.py regardless of where uvicorn is launched from.
# ----------------------------------------------------------
BASE_DIR      = Path(__file__).resolve().parent
TEMPLATES_DIR = BASE_DIR / "templates"
PUBLIC_DIR    = BASE_DIR / "public"

# ----------------------------------------------------------
# Startup diagnostics — printed once when server starts.
# Check your terminal to confirm these paths exist.
# ----------------------------------------------------------
print("=" * 60)
print(f"[STARTUP] BASE_DIR      = {BASE_DIR}")
print(f"[STARTUP] TEMPLATES_DIR = {TEMPLATES_DIR} | exists={TEMPLATES_DIR.exists()}")
print(f"[STARTUP] PUBLIC_DIR    = {PUBLIC_DIR}    | exists={PUBLIC_DIR.exists()}")
index_html = TEMPLATES_DIR / "index.html"
style_css  = PUBLIC_DIR / "style.css"
print(f"[STARTUP] index.html    = {index_html} | exists={index_html.exists()}")
print(f"[STARTUP] style.css     = {style_css}  | exists={style_css.exists()}")
print("=" * 60)

# ----------------------------------------------------------
# Validate directories exist before app starts
# ----------------------------------------------------------
if not TEMPLATES_DIR.exists():
    raise RuntimeError(
        f"\n\n[ERROR] templates/ folder NOT FOUND at: {TEMPLATES_DIR}\n"
        f"Make sure you have: {BASE_DIR}/templates/index.html\n"
    )

if not index_html.exists():
    raise RuntimeError(
        f"\n\n[ERROR] index.html NOT FOUND at: {index_html}\n"
        f"Make sure templates/index.html exists inside your project folder.\n"
    )

# ----------------------------------------------------------
# FastAPI app instance
# ----------------------------------------------------------
app = FastAPI(
    title="Email Automation System",
    description="Schedule and send emails automatically.",
    version="1.0.0",
)

# ----------------------------------------------------------
# Mount /public as static files directory.
# Your CSS will be served at: http://127.0.0.1:8000/public/style.css
# ----------------------------------------------------------
if PUBLIC_DIR.exists():
    app.mount("/public", StaticFiles(directory=str(PUBLIC_DIR)), name="public")
    print(f"[STARTUP] ✅ Static files mounted from: {PUBLIC_DIR}")
else:
    print(f"[STARTUP] ⚠️  public/ folder missing — CSS will not load from /public/style.css")

# ----------------------------------------------------------
# Jinja2 template engine
# ----------------------------------------------------------
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
print(f"[STARTUP] ✅ Jinja2 templates loaded from: {TEMPLATES_DIR}")


# ----------------------------------------------------------
# ROUTE 1 — Home page (GET /)
# ----------------------------------------------------------
@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    print("[ROUTE] GET / — rendering index.html")

    history = load_history()
    history_sorted = sorted(
        history,
        key=lambda x: x.get("created_at", ""),
        reverse=True,
    )

    context = {
        "request": request,           # required by Jinja2
        "history": history_sorted,
        "total":   len(history),
        "sent":    sum(1 for e in history if e.get("status") == "sent"),
        "pending": sum(1 for e in history if e.get("status") == "scheduled"),
        "failed":  sum(1 for e in history if e.get("status") == "failed"),
        "debug_base_dir": str(BASE_DIR),
    }

    print(f"[ROUTE] Rendering with context: total={context['total']}, "
          f"sent={context['sent']}, pending={context['pending']}, failed={context['failed']}")

    response = templates.TemplateResponse("index.html", context)
    print(f"[ROUTE] TemplateResponse created — status={response.status_code}")
    return response


# ----------------------------------------------------------
# ROUTE 2 — Schedule an email (POST /schedule)
# ----------------------------------------------------------
@app.post("/schedule")
async def schedule_email(
    to:           str = Form(...),
    subject:      str = Form(...),
    body:         str = Form(...),
    scheduled_at: str = Form(...),
):
    print(f"[ROUTE] POST /schedule — to={to}, scheduled_at={scheduled_at}")

    try:
        scheduled_dt = datetime.fromisoformat(scheduled_at)
    except ValueError:
        return JSONResponse(
            content={"success": False, "message": "Invalid date/time format."},
            status_code=400,
        )

    now = datetime.now(timezone.utc)
    if scheduled_dt.tzinfo is None:
        scheduled_dt = scheduled_dt.replace(tzinfo=timezone.utc)

    if scheduled_dt <= now:
        return JSONResponse(
            content={"success": False, "message": "Scheduled time must be in the future."},
            status_code=400,
        )

    record = {
        "id":           str(uuid.uuid4()),
        "to":           to.strip(),
        "subject":      subject.strip(),
        "body":         body.strip(),
        "status":       "scheduled",
        "scheduled_at": scheduled_dt.isoformat(),
        "created_at":   now.isoformat(),
        "sent_at":      None,
        "note":         "",
    }

    save_record(record)
    print(f"[ROUTE] ✅ Scheduled email ID={record['id']}")

    return JSONResponse(content={
        "success": True,
        "message": f"Email scheduled for {scheduled_dt.strftime('%b %d, %Y at %I:%M %p')}",
        "id":      record["id"],
    })


# ----------------------------------------------------------
# ROUTE 3 — Send immediately (POST /send-now)
# ----------------------------------------------------------
@app.post("/send-now")
async def send_now(
    to:      str = Form(...),
    subject: str = Form(...),
    body:    str = Form(...),
):
    print(f"[ROUTE] POST /send-now — to={to}")

    success, message = send_email(
        to=to.strip(),
        subject=subject.strip(),
        body=body.strip(),
    )

    now = datetime.now(timezone.utc).isoformat()

    record = {
        "id":           str(uuid.uuid4()),
        "to":           to.strip(),
        "subject":      subject.strip(),
        "body":         body.strip(),
        "status":       "sent" if success else "failed",
        "scheduled_at": None,
        "created_at":   now,
        "sent_at":      now if success else None,
        "note":         message,
    }

    save_record(record)
    print(f"[ROUTE] send-now result: success={success}, message={message}")

    return JSONResponse(content={"success": success, "message": message})


# ----------------------------------------------------------
# ROUTE 4 — Email history JSON (GET /history)
# ----------------------------------------------------------
@app.get("/history")
async def get_history():
    print("[ROUTE] GET /history")
    history = load_history()
    history_sorted = sorted(
        history,
        key=lambda x: x.get("created_at", ""),
        reverse=True,
    )
    return JSONResponse(content={
        "total":   len(history),
        "emails":  history_sorted,
        "sent":    sum(1 for e in history if e.get("status") == "sent"),
        "pending": sum(1 for e in history if e.get("status") == "scheduled"),
        "failed":  sum(1 for e in history if e.get("status") == "failed"),
    })


# ----------------------------------------------------------
# ROUTE 5 — Cron endpoint (GET /cron/send-scheduled)
# Called by Vercel every minute per vercel.json schedule.
# ----------------------------------------------------------
@app.get("/cron/send-scheduled")
async def cron_send_scheduled(authorization: str = Header(default="")):
    if CRON_SECRET:
        if authorization != f"Bearer {CRON_SECRET}":
            return JSONResponse(content={"error": "Unauthorized"}, status_code=401)

    print("[CRON] ⏰ Triggered — checking for due emails...")
    result = process_scheduled_emails()
    print(f"[CRON] Done — {result['sent']} sent, {result['failed']} failed")

    return JSONResponse(content={
        "success": True,
        "result":  result,
        "message": f"{result['sent']} sent, {result['failed']} failed.",
    })


# ----------------------------------------------------------
# ROUTE 6 — Debug route (GET /debug)
# Visit http://127.0.0.1:8000/debug to confirm everything works.
# DELETE this route before going to production if you want.
# ----------------------------------------------------------
@app.get("/debug")
async def debug():
    return JSONResponse(content={
        "status":        "ok",
        "base_dir":      str(BASE_DIR),
        "templates_dir": str(TEMPLATES_DIR),
        "templates_ok":  TEMPLATES_DIR.exists(),
        "index_html_ok": (TEMPLATES_DIR / "index.html").exists(),
        "public_dir":    str(PUBLIC_DIR),
        "public_ok":     PUBLIC_DIR.exists(),
        "style_css_ok":  (PUBLIC_DIR / "style.css").exists(),
        "history_file":  str(BASE_DIR / "email_history.json"),
        "history_ok":    (BASE_DIR / "email_history.json").exists(),
        "os_name":       os.name,
        "python_cwd":    os.getcwd(),
    })