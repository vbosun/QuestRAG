from datetime import date
from pathlib import Path

from fastapi import FastAPI, Form
from fastapi.responses import HTMLResponse

app = FastAPI(title="Mock HRSS Business System", version="0.1.0")
HTML_PATH = Path(__file__).with_name("employment_registration.html")


@app.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
    return HTMLResponse("<h1>模拟人社业务系统</h1><p>请从就业登记业务入口进入。</p>")


@app.get("/employment-registration/apply", response_class=HTMLResponse)
def employment_registration_page() -> HTMLResponse:
    return HTMLResponse(HTML_PATH.read_text(encoding="utf-8"))


@app.post("/api/employment-registration/submit")
def submit_employment_registration(
    full_name: str = Form(...), phone: str = Form(...), employment_type: str = Form(...),
    employer_name: str = Form(...), occupation: str = Form(...), employment_start_date: str = Form(...),
    current_address: str = Form(...),
) -> dict:
    return {
        "status": "SUBMITTED",
        "application_no": f"MOCK-{date.today().strftime('%Y%m%d')}-0001",
        "message": "模拟业务系统已收到提交，进入审批流程。",
        "data": {"full_name": full_name, "phone": phone, "employment_type": employment_type,
                 "employer_name": employer_name, "occupation": occupation,
                 "employment_start_date": employment_start_date, "current_address": current_address},
    }
