"""Independent, persistent demo submissions and single-step human review."""
import hashlib
import hmac
import json
import os
import re
import secrets
import sqlite3
import time
from contextlib import asynccontextmanager, contextmanager
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import quote

from argon2 import PasswordHasher
from argon2.exceptions import VerificationError
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from pydantic import BaseModel, Field
from starlette.datastructures import UploadFile

ROOT = Path(__file__).parent
MAX_FILE = 5 * 1024 * 1024
COOKIE = "mock_business_session"
PASSWORDS = PasswordHasher()
BUSINESSES = {
    "employment-registration": {
        "name": "就业登记", "proof": "employment_proof", "date": "employment_start_date",
        "fields": {"full_name": "姓名", "phone": "联系电话", "employment_type": "就业类型", "employer_name": "用人单位或经营主体名称", "occupation": "岗位或从事职业", "employment_start_date": "就业起始日期", "current_address": "现居住地址"},
        "options": {"employment_type": {"employer": "单位就业", "flexible": "灵活就业", "self_employed": "自主创业"}},
    },
    "unemployment-registration": {
        "name": "失业登记", "proof": "unemployment_proof", "date": "unemployment_date",
        "fields": {"full_name": "姓名", "phone": "联系电话", "unemployment_date": "失业日期", "unemployment_reason": "失业原因", "last_employer": "上次工作单位", "current_address": "现居住地址"},
        "options": {"unemployment_reason": {"contract_ended": "劳动合同终止", "layoff": "单位裁员", "resignation": "主动离职", "other": "其他"}},
    },
}


def db_path():
    return Path(os.environ.get("MOCK_BUSINESS_DB", "data/mock-business/business.sqlite3"))


@contextmanager
def database():
    conn = sqlite3.connect(db_path(), timeout=15)
    conn.row_factory = sqlite3.Row
    try:
        with conn:
            yield conn
    finally:
        conn.close()


def initialize():
    db_path().parent.mkdir(parents=True, exist_ok=True)
    with database() as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS administrators (name TEXT PRIMARY KEY, password_hash TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS sessions (digest TEXT PRIMARY KEY, name TEXT NOT NULL, expires REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS login_attempts (at REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS submissions (
            number TEXT PRIMARY KEY, request_id TEXT UNIQUE NOT NULL, fingerprint TEXT NOT NULL,
            query_token TEXT NOT NULL, case_id TEXT, business TEXT NOT NULL, fields TEXT NOT NULL,
            applicant TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'PENDING', created_at TEXT NOT NULL,
            reviewed_at TEXT, reviewer TEXT, comment TEXT,
            file_name TEXT NOT NULL, file_type TEXT NOT NULL, file_content BLOB NOT NULL
        );
        CREATE INDEX IF NOT EXISTS submissions_status_created ON submissions(status, created_at);
        """)
        columns = {row[1] for row in conn.execute("PRAGMA table_info(submissions)")}
        if "link_hash" not in columns:
            conn.execute("ALTER TABLE submissions ADD COLUMN link_hash TEXT")
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS submissions_case_link ON submissions(case_id,link_hash) WHERE link_hash IS NOT NULL")
        if not conn.execute("SELECT 1 FROM administrators LIMIT 1").fetchone():
            password = os.environ.get("MOCK_ADMIN_PASSWORD") or secrets.token_urlsafe(18)
            if len(password) < 12:
                raise RuntimeError("MOCK_ADMIN_PASSWORD must contain at least 12 characters")
            name = os.environ.get("MOCK_ADMIN_USER", "admin")
            fd = os.open(db_path().parent / "initial-admin.txt", os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                stream.write(f"审批账号：{name}\n初始密码：{password}\n登录后请修改密码。\n")
            conn.execute("INSERT INTO administrators VALUES (?, ?)", (name, PASSWORDS.hash(password)))


@asynccontextmanager
async def lifespan(app):
    initialize()
    yield


app = FastAPI(title="模拟人社业务系统", version="0.2.0", lifespan=lifespan, docs_url=None, redoc_url=None)


@app.middleware("http")
async def response_headers(request, call_next):
    response = await call_next(request)
    response.headers.update({"X-Content-Type-Options": "nosniff", "Referrer-Policy": "no-referrer", "Cache-Control": "no-store"})
    return response


@app.get("/")
@app.get("/business/")
@app.get("/business/admin")
@app.get("/business/query")
def portal():
    return FileResponse(ROOT / "portal.html")


@app.get("/business/portal.css")
def stylesheet():
    return FileResponse(ROOT / "portal.css")


@app.get("/business/portal.js")
def javascript():
    return FileResponse(ROOT / "portal.js")


@app.get("/form-bridge.js")
def form_bridge():
    return FileResponse(ROOT / "form_bridge.js")


@app.get("/business/submission.js")
def submission_script():
    return FileResponse(ROOT / "submission.js")


@app.get("/business/submission.css")
def submission_styles():
    return FileResponse(ROOT / "submission.css")


@app.get("/employment-registration/apply")
def employment_registration_page():
    return FileResponse(ROOT / "employment_registration.html")


@app.get("/unemployment-registration/apply")
def unemployment_registration_page():
    return FileResponse(ROOT / "unemployment_registration.html")


@app.get("/business/api/health")
def health():
    with database() as conn:
        conn.execute("SELECT 1 FROM submissions LIMIT 1")
    return {"status": "ok"}


def require_ajax(request: Request):
    # Cross-origin forms cannot supply this header; no CORS origins are enabled.
    if request.headers.get("X-Business-Request") != "1":
        raise HTTPException(403, "请从业务系统页面操作")


def admin(request: Request):
    digest = hashlib.sha256(request.cookies.get(COOKIE, "").encode()).hexdigest()
    with database() as conn:
        session = conn.execute("SELECT name FROM sessions WHERE digest=? AND expires>?", (digest, time.time())).fetchone()
    if not session:
        raise HTTPException(401, "请先登录审批工作台")
    return session["name"]


class Login(BaseModel):
    username: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=1, max_length=200)


@app.post("/business/api/login", dependencies=[Depends(require_ajax)])
def login(body: Login):
    with database() as conn:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("DELETE FROM login_attempts WHERE at<?", (time.time() - 60,))
        if conn.execute("SELECT count(*) FROM login_attempts").fetchone()[0] >= 15:
            raise HTTPException(429, "登录尝试过于频繁，请一分钟后再试")
        conn.execute("INSERT INTO login_attempts VALUES (?)", (time.time(),))
        row = conn.execute("SELECT password_hash FROM administrators WHERE name=?", (body.username,)).fetchone()
    try:
        valid = bool(row) and PASSWORDS.verify(row["password_hash"], body.password)
    except VerificationError:
        valid = False
    if not valid:
        raise HTTPException(401, "账号或密码错误")
    token = secrets.token_urlsafe(32)
    with database() as conn:
        conn.execute("DELETE FROM sessions WHERE expires<?", (time.time(),))
        conn.execute("INSERT INTO sessions VALUES (?, ?, ?)", (hashlib.sha256(token.encode()).hexdigest(), body.username, time.time() + 8 * 3600))
    response = JSONResponse({"name": body.username})
    response.set_cookie(COOKIE, token, httponly=True, samesite="strict", path="/business", max_age=8 * 3600, secure=os.environ.get("MOCK_COOKIE_SECURE") == "true")
    return response


@app.get("/business/api/me")
def me(name=Depends(admin)):
    return {"name": name}


@app.post("/business/api/logout", dependencies=[Depends(require_ajax)])
def logout(request: Request):
    with database() as conn:
        conn.execute("DELETE FROM sessions WHERE digest=?", (hashlib.sha256(request.cookies.get(COOKIE, "").encode()).hexdigest(),))
    response = JSONResponse({"ok": True})
    response.delete_cookie(COOKIE, path="/business")
    return response


class PasswordChange(BaseModel):
    current_password: str = Field(max_length=200)
    new_password: str = Field(min_length=12, max_length=200)


@app.post("/business/api/password", dependencies=[Depends(require_ajax)])
def change_password(body: PasswordChange, name=Depends(admin)):
    with database() as conn:
        row = conn.execute("SELECT password_hash FROM administrators WHERE name=?", (name,)).fetchone()
        try:
            PASSWORDS.verify(row["password_hash"], body.current_password)
        except VerificationError:
            raise HTTPException(400, "当前密码错误")
        conn.execute("UPDATE administrators SET password_hash=? WHERE name=?", (PASSWORDS.hash(body.new_password), name))
        conn.execute("DELETE FROM sessions WHERE name=?", (name,))
    (db_path().parent / "initial-admin.txt").unlink(missing_ok=True)
    return {"ok": True}


def receipt(row):
    return {"status": "SUBMITTED", "application_no": row["number"], "query_code": row["query_token"], "message": "申请已提交，等待审批。", "progress": progress_row(row)}


def progress_row(row):
    result = {key: row[key] for key in ('number', 'business', 'status', 'created_at', 'reviewed_at', 'comment')}
    spec = BUSINESSES[row['business']]
    result['business_name'] = spec['name']
    size = row['file_size'] if 'file_size' in row.keys() else len(row['file_content'])
    result['materials'] = [{'key': spec['proof'], 'name': row['file_name'], 'size_bytes': size,
                            'status': 'received', 'received_at': row['created_at']}]
    return result


@app.post("/api/{business}/submit")
async def submit(business: str, request: Request):
    spec = BUSINESSES.get(business)
    if not spec:
        raise HTTPException(404, "业务不存在")
    async with request.form(max_files=1, max_fields=15, max_part_size=8192) as form:
        fields = {}
        for key, label in spec["fields"].items():
            value = form.get(key)
            if not isinstance(value, str) or not value.strip() or len(value) > 2000:
                raise HTTPException(422, f"请正确填写{label}")
            fields[key] = value.strip()
        if not re.fullmatch(r"1[3-9]\d{9}", fields["phone"]):
            raise HTTPException(422, "请输入正确的11位手机号码")
        try:
            date.fromisoformat(fields[spec["date"]])
        except ValueError:
            raise HTTPException(422, "日期格式不正确")
        for key, options in spec["options"].items():
            if fields[key] not in options:
                raise HTTPException(422, f"请正确选择{spec['fields'][key]}")
        request_id, case_id = form.get("submission_id", ""), form.get("case_id", "")
        link_token = form.get("link_token", "")
        if not isinstance(link_token, str) or (link_token and not re.fullmatch(r"[a-zA-Z0-9_-]{43}", link_token)):
            raise HTTPException(422, "请重新打开申请页面以关联进度查询，再提交申请")
        link_hash = hashlib.sha256(link_token.encode()).hexdigest() if case_id and link_token else None
        if not isinstance(request_id, str) or not re.fullmatch(r"[a-zA-Z0-9_-]{20,100}", request_id):
            raise HTTPException(422, "提交标识无效，请刷新页面")
        if not isinstance(case_id, str) or len(case_id) > 100:
            raise HTTPException(422, "申请关联无效")
        file = form.get(spec["proof"])
        if not isinstance(file, UploadFile) or not file.filename:
            raise HTTPException(422, "请上传证明材料")
        content = await file.read(MAX_FILE + 1)
        if not content or len(content) > MAX_FILE:
            raise HTTPException(422, "材料不能为空，且不能超过5MB")
        filename = file.filename.replace("\\", "/").split("/")[-1][:200]
        payload = json.dumps(fields, ensure_ascii=False, sort_keys=True)
        fingerprint = hashlib.sha256(json.dumps([business, case_id, payload, filename, hashlib.sha256(content).hexdigest()]).encode()).hexdigest()
        with database() as conn:
            conn.execute("BEGIN IMMEDIATE")
            existing = conn.execute("SELECT * FROM submissions WHERE request_id=?", (request_id,)).fetchone()
            if not existing and link_hash:
                existing = conn.execute("SELECT * FROM submissions WHERE case_id=? AND link_hash=?", (case_id, link_hash)).fetchone()
            if existing:
                if existing["fingerprint"] != fingerprint or existing["link_hash"] != link_hash:
                    raise HTTPException(409, "此申请已提交，内容不可覆盖；请从业务首页新建申请")
                return receipt(existing)
            number = f"MOCK-{date.today():%Y%m%d}-{secrets.token_hex(6).upper()}"
            conn.execute("""INSERT INTO submissions
                (number, request_id, fingerprint, query_token, case_id, business, fields, applicant, created_at, file_name, file_type, file_content, link_hash)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (number, request_id, fingerprint, secrets.token_urlsafe(18), case_id, business, payload, fields["full_name"], datetime.now(timezone.utc).isoformat(), filename, file.content_type or "application/octet-stream", content, link_hash))
            return receipt(conn.execute("SELECT * FROM submissions WHERE number=?", (number,)).fetchone())


SUMMARY_COLUMNS = "number,business,applicant,status,created_at,reviewed_at,reviewer,comment,file_name,length(file_content) AS file_size"


def public_row(row, detail=False):
    result = dict(row)
    result["business_name"] = BUSINESSES[row["business"]]["name"]
    if detail:
        values = json.loads(result.pop("fields"))
        spec = BUSINESSES[row["business"]]
        result["fields"] = [{"label": label, "value": spec["options"].get(key, {}).get(values[key], values[key])} for key, label in spec["fields"].items()]
    return result


@app.get("/business/api/applications")
def list_applications(status: str = "PENDING", business: str = "", q: str = "", page: int = 1, name=Depends(admin)):
    if status not in {"", "PENDING", "APPROVED", "REJECTED"} or business not in {"", *BUSINESSES} or page < 1 or len(q) > 100:
        raise HTTPException(422, "筛选条件无效")
    where, params = ["1=1"], []
    for column, value in [("status", status), ("business", business)]:
        if value:
            where.append(f"{column}=?")
            params.append(value)
    if q.strip():
        where.append("(instr(applicant, ?) > 0 OR instr(number, ?) > 0)")
        params.extend([q.strip(), q.strip()])
    clause = " AND ".join(where)
    with database() as conn:
        total = conn.execute(f"SELECT count(*) FROM submissions WHERE {clause}", params).fetchone()[0]
        rows = conn.execute(f"SELECT {SUMMARY_COLUMNS} FROM submissions WHERE {clause} ORDER BY created_at DESC LIMIT 20 OFFSET ?", [*params, (page - 1) * 20]).fetchall()
        counts = {row[0]: row[1] for row in conn.execute("SELECT status,count(*) FROM submissions GROUP BY status")}
    return {"items": [public_row(row) for row in rows], "total": total, "counts": counts}


@app.get("/business/api/applications/{number}")
def application_detail(number: str, name=Depends(admin)):
    with database() as conn:
        row = conn.execute(f"SELECT {SUMMARY_COLUMNS},fields FROM submissions WHERE number=?", (number,)).fetchone()
    if not row:
        raise HTTPException(404, "申请不存在")
    return public_row(row, True)


@app.get("/business/api/applications/{number}/material")
def material(number: str, name=Depends(admin)):
    with database() as conn:
        row = conn.execute("SELECT file_name,file_content FROM submissions WHERE number=?", (number,)).fetchone()
    if not row:
        raise HTTPException(404, "材料不存在")
    return Response(bytes(row["file_content"]), media_type="application/octet-stream", headers={"Content-Disposition": "attachment; filename*=UTF-8''" + quote(row["file_name"], safe="")})


class Decision(BaseModel):
    action: str
    comment: str = Field(default="", max_length=1000)


@app.post("/business/api/applications/{number}/decision", dependencies=[Depends(require_ajax)])
def decide(number: str, body: Decision, name=Depends(admin)):
    if body.action not in {"approve", "reject"}:
        raise HTTPException(422, "审批操作无效")
    if body.action == "reject" and not body.comment.strip():
        raise HTTPException(422, "驳回时请填写原因")
    with database() as conn:
        changed = conn.execute("UPDATE submissions SET status=?,reviewed_at=?,reviewer=?,comment=? WHERE number=? AND status='PENDING'",
            ("APPROVED" if body.action == "approve" else "REJECTED", datetime.now(timezone.utc).isoformat(), name, body.comment.strip(), number)).rowcount
        if not changed:
            raise HTTPException(409, "申请已被处理或不存在，请刷新列表")
    return application_detail(number, name)


class Query(BaseModel):
    number: str = Field(min_length=1, max_length=100)
    code: str = Field(min_length=1, max_length=100)


class CaseQuery(BaseModel):
    case_id: str = Field(min_length=1, max_length=100)
    token: str = Field(pattern=r"^[a-zA-Z0-9_-]{43}$")


@app.post("/business/api/case-status", dependencies=[Depends(require_ajax)])
def case_status(body: CaseQuery):
    digest = hashlib.sha256(body.token.encode()).hexdigest()
    with database() as conn:
        row = conn.execute("SELECT number,case_id,business,status,created_at,reviewed_at,comment,file_name,length(file_content) AS file_size FROM submissions WHERE case_id=? AND link_hash=?",
                           (body.case_id, digest)).fetchone()
    if not row:
        raise HTTPException(404, "未找到关联的业务回执")
    result = progress_row(row)
    result['case_id'] = row['case_id']
    return result


@app.post("/business/api/query", dependencies=[Depends(require_ajax)])
def query(body: Query):
    with database() as conn:
        row = conn.execute("SELECT number,business,status,created_at,reviewed_at,comment,query_token,file_name,length(file_content) AS file_size FROM submissions WHERE number=?", (body.number.strip(),)).fetchone()
    if not row or not hmac.compare_digest(row["query_token"].encode(), body.code.strip().encode()):
        raise HTTPException(404, "申请编号或查询码不正确")
    return progress_row(row)
