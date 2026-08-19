from __future__ import annotations

import json
import mimetypes
import os
import sqlite3
import sys
import urllib.parse
import secrets
from email.message import Message
from datetime import datetime
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
UPLOAD_DIR = ROOT / "uploads"
DB_PATH = DATA_DIR / "test_assets.db"
HOST = "127.0.0.1"
PORT = int(os.environ.get("ASSET_APP_PORT", "4173"))
SESSIONS: dict[str, str] = {}
ADMIN_USER = "admin"
ADMIN_PASSWORD = "admin"

SEED_ASSETS = [
    ("LB-A100-01", "A100", "LB", "QFN-64 Load Board", "苏州封装厂", 2, "件", "2026-07-10", "使用中", "A100_LB图纸_RevB.pdf", "TESTER-03 / J750", "A100量产测试使用"),
    ("SK-A100-01", "A100", "Socket", "QFN-64 Socket", "苏州封装厂", 1, "件", "2026-07-10", "可用", "A100_Socket.step", "LB-A100-01", "与LB-A100-01配套"),
    ("TESTER-03", "A100", "测试机", "Teradyne J750", "苏州封装厂", 1, "台", "2026-06-20", "使用中", "J750配置说明.pdf", "LB-A100-01", "联系人：王工"),
    ("DC-A100-02", "A100", "DC线", "香蕉头转航空插头", "苏州封装厂", 2, "套", "2026-07-10", "可用", "A100_DC接线图.pdf", "TESTER-03 / J750", "红黑线各1组/套"),
    ("LB-B220-03", "B220", "LB", "BGA-256 Load Board", "上海封装厂", 2, "件", "2026-06-18", "使用中", "B220_LB图纸.pdf", "TESTER-06 / V93K", "B220工程批使用"),
    ("SK-B220-02", "B220", "Socket", "BGA-256 Socket", "我司仓库", 2, "件", "—", "可用", "B220_Socket.pdf", "LB-B220-03", "备用库存"),
    ("TESTER-06", "B220", "测试机", "Advantest V93K", "我司仓库", 1, "台", "—", "可用", "V93K说明书.pdf", "LB-B220-03", "可调拨"),
    ("DC-B220-01", "B220", "DC线", "V93K DC Cable Kit", "上海封装厂", 3, "套", "2026-06-18", "使用中", "B220_DC线序.xlsx", "TESTER-06 / V93K", "编号1-3"),
    ("LB-C310-02", "C310", "LB", "LGA-1200 Load Board", "无锡封装厂", 1, "件", "2026-07-26", "可用", "C310_LB_Gerber.zip", "TESTER-02 / T2000", "试产"),
    ("SK-C310-02", "C310", "Socket", "LGA-1200 Socket", "无锡封装厂", 1, "件", "2026-07-26", "可用", "C310_Socket.pdf", "LB-C310-02", "试产"),
    ("TESTER-08", "D450", "测试机", "Chroma 3380", "深圳封装厂", 1, "台", "2026-05-09", "维护中", "3380维护记录.xlsx", "LB-D450-01", "等待更换电源模块"),
    ("DC-E520-04", "E520", "DC线", "DC Power Harness", "昆山封装厂", 4, "套", "2026-08-02", "可用", "E520接线图.pdf", "TESTER-05 / ETS88", "量产线备用"),
]


def connection() -> sqlite3.Connection:
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    return db


def parse_header(value: str):
    """Parse a MIME-style header without the removed Python cgi module."""
    message = Message()
    message["content-type"] = value
    params = message.get_params(header="content-type", unquote=True) or []
    return (params[0][0] if params else value), dict(params[1:])


def init_db() -> None:
    DATA_DIR.mkdir(exist_ok=True)
    UPLOAD_DIR.mkdir(exist_ok=True)
    with connection() as db:
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS assets (
                id TEXT PRIMARY KEY,
                product TEXT NOT NULL,
                type TEXT NOT NULL CHECK(type IN ('LB','Socket','测试机','DC线')),
                model TEXT NOT NULL,
                location TEXT NOT NULL DEFAULT '我司仓库',
                qty INTEGER NOT NULL DEFAULT 1 CHECK(qty > 0),
                unit TEXT NOT NULL,
                sent_date TEXT NOT NULL DEFAULT '—',
                status TEXT NOT NULL DEFAULT '可用',
                file_name TEXT NOT NULL DEFAULT '暂未上传',
                compatible TEXT NOT NULL DEFAULT '—',
                note TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS shipments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                asset_id TEXT NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
                from_location TEXT NOT NULL,
                to_location TEXT NOT NULL,
                sent_date TEXT NOT NULL,
                tracking_no TEXT NOT NULL DEFAULT '',
                handler TEXT NOT NULL DEFAULT '',
                note TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS files (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                asset_id TEXT NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
                original_name TEXT NOT NULL,
                stored_name TEXT NOT NULL UNIQUE,
                size INTEGER NOT NULL DEFAULT 0,
                content_type TEXT NOT NULL DEFAULT 'application/octet-stream',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS releases (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                version TEXT NOT NULL UNIQUE,
                title TEXT NOT NULL,
                content TEXT NOT NULL,
                released_at TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS idx_assets_product ON assets(product);
            CREATE INDEX IF NOT EXISTS idx_assets_location_type ON assets(location, type);
            CREATE INDEX IF NOT EXISTS idx_shipments_asset_date ON shipments(asset_id, sent_date DESC);
            CREATE INDEX IF NOT EXISTS idx_files_asset ON files(asset_id);
            """
        )
        if db.execute("SELECT COUNT(*) FROM assets").fetchone()[0] == 0:
            db.executemany(
                "INSERT INTO assets(id,product,type,model,location,qty,unit,sent_date,status,file_name,compatible,note) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                SEED_ASSETS,
            )
            for item in SEED_ASSETS:
                if item[7] != "—":
                    db.execute(
                        "INSERT INTO shipments(asset_id,from_location,to_location,sent_date,note) VALUES(?,?,?,?,?)",
                        (item[0], "我司仓库", item[4], item[7], "初始化寄送记录"),
                    )
        if db.execute("SELECT COUNT(*) FROM releases").fetchone()[0] == 0:
            db.execute(
                "INSERT INTO releases(version,title,content,released_at) VALUES(?,?,?,?)",
                ("v0.2.0", "本地数据库与账号版本", "新增 SQLite 本地数据库；新增管理员与临时访问账号；资产、寄送记录和附件可以永久保存；新增版本更新页面。", "2026-08-14"),
            )
            db.execute(
                "INSERT INTO releases(version,title,content,released_at) VALUES(?,?,?,?)",
                ("v0.1.0", "首个可操作原型", "完成 LB、Socket、测试机、DC线的资产总览、封装厂查看、产品配套、寄送记录和图纸资料界面。", "2026-08-06"),
            )
        db.execute(
            "INSERT OR IGNORE INTO releases(version,title,content,released_at) VALUES(?,?,?,?)",
            ("v0.2.1", "本地启动修复", "修复服务停止后网站无法打开的问题；新增一键启动脚本，自动启动本地服务并打开浏览器；兼容新版 Python。", "2026-08-19"),
        )
        db.execute("PRAGMA optimize")


def asset_dict(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"], "product": row["product"], "type": row["type"],
        "model": row["model"], "location": row["location"], "qty": row["qty"],
        "unit": row["unit"], "date": row["sent_date"], "status": row["status"],
        "file": row["file_name"], "fit": row["compatible"], "note": row["note"],
    }


class AppHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def log_message(self, fmt: str, *args) -> None:
        sys.stdout.write("[%s] %s\n" % (self.log_date_time_string(), fmt % args))

    def json_response(self, payload, status=200):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        return json.loads(self.rfile.read(length).decode("utf-8")) if length else {}

    def current_role(self):
        cookie = self.headers.get("Cookie", "")
        values = {}
        for item in cookie.split(";"):
            if "=" in item:
                key, value = item.strip().split("=", 1)
                values[key] = value
        return SESSIONS.get(values.get("asset_session", ""))

    def require_login(self):
        role = self.current_role()
        if not role:
            self.json_response({"error": "请先登录"}, 401)
            return None
        return role

    def require_admin(self):
        role = self.require_login()
        if role and role != "admin":
            self.json_response({"error": "临时访问账号只有查看权限"}, 403)
            return None
        return role

    def read_multipart(self):
        content_type = self.headers.get("Content-Type", "")
        _, params = parse_header(content_type)
        boundary = params.get("boundary")
        if not boundary:
            raise ValueError("缺少上传边界")
        boundary_bytes = ("--" + boundary).encode("utf-8")
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length)
        fields = {}
        uploaded = None
        for part in body.split(boundary_bytes):
            part = part.strip(b"\r\n-")
            if not part or b"\r\n\r\n" not in part:
                continue
            raw_headers, content = part.split(b"\r\n\r\n", 1)
            content = content.rstrip(b"\r\n")
            header_text = raw_headers.decode("utf-8", "replace")
            disposition = next((line for line in header_text.split("\r\n") if line.lower().startswith("content-disposition:")), "")
            _, disp_params = parse_header(disposition.split(":", 1)[1].strip() if ":" in disposition else "")
            name = disp_params.get("name", "")
            filename = disp_params.get("filename")
            if filename is not None:
                content_type_line = next((line for line in header_text.split("\r\n") if line.lower().startswith("content-type:")), "")
                uploaded = {"filename": filename, "content": content, "content_type": content_type_line.split(":", 1)[1].strip() if ":" in content_type_line else "application/octet-stream"}
            elif name:
                fields[name] = content.decode("utf-8", "replace")
        return fields, uploaded

    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path
        if path == "/api/health":
            return self.json_response({"ok": True, "database": str(DB_PATH)})
        if path == "/api/me":
            role = self.current_role()
            if not role:
                return self.json_response({"authenticated": False})
            return self.json_response({"authenticated": True, "role": role, "name": "管理员" if role == "admin" else "临时访问", "can_write": role == "admin"})
        if path.startswith("/api/") and not self.require_login():
            return
        if path == "/api/assets":
            with connection() as db:
                rows = db.execute("SELECT * FROM assets ORDER BY created_at DESC, id").fetchall()
            return self.json_response([asset_dict(row) for row in rows])
        if path == "/api/shipments":
            with connection() as db:
                rows = db.execute("SELECT s.*, a.product, a.type, a.model, a.qty, a.unit, a.status FROM shipments s JOIN assets a ON a.id=s.asset_id ORDER BY s.sent_date DESC, s.id DESC").fetchall()
            return self.json_response([dict(row) for row in rows])
        if path == "/api/files":
            with connection() as db:
                rows = db.execute("SELECT f.*, a.product, a.type FROM files f JOIN assets a ON a.id=f.asset_id ORDER BY f.created_at DESC").fetchall()
            return self.json_response([dict(row) for row in rows])
        if path == "/api/releases":
            with connection() as db:
                rows = db.execute("SELECT * FROM releases ORDER BY released_at DESC, id DESC").fetchall()
            return self.json_response([dict(row) for row in rows])
        if path.startswith("/api/files/"):
            try:
                file_id = int(path.rsplit("/", 1)[1])
            except ValueError:
                return self.json_response({"error": "无效文件编号"}, 400)
            with connection() as db:
                row = db.execute("SELECT * FROM files WHERE id=?", (file_id,)).fetchone()
            if not row:
                return self.json_response({"error": "文件不存在"}, 404)
            file_path = UPLOAD_DIR / row["stored_name"]
            if not file_path.exists():
                return self.json_response({"error": "文件数据不存在"}, 404)
            body = file_path.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", row["content_type"])
            quoted = urllib.parse.quote(row["original_name"])
            self.send_header("Content-Disposition", f"attachment; filename*=UTF-8''{quoted}")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            return self.wfile.write(body)
        return super().do_GET()

    def do_POST(self):
        path = urllib.parse.urlparse(self.path).path
        if path == "/api/login":
            data = self.read_json()
            mode = data.get("mode")
            if mode == "guest":
                role = "guest"
            elif mode == "admin" and data.get("username") == ADMIN_USER and data.get("password") == ADMIN_PASSWORD:
                role = "admin"
            else:
                return self.json_response({"error": "管理员账号或密码错误"}, 401)
            token = secrets.token_urlsafe(32)
            SESSIONS[token] = role
            body = json.dumps({"ok": True, "role": role}, ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Set-Cookie", f"asset_session={token}; Path=/; HttpOnly; SameSite=Strict")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            return self.wfile.write(body)
        if path == "/api/logout":
            cookie = self.headers.get("Cookie", "")
            for item in cookie.split(";"):
                if item.strip().startswith("asset_session="):
                    SESSIONS.pop(item.strip().split("=", 1)[1], None)
            body = b'{"ok":true}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Set-Cookie", "asset_session=; Path=/; Max-Age=0; HttpOnly; SameSite=Strict")
            self.end_headers()
            return self.wfile.write(body)
        if not self.require_admin():
            return
        if path == "/api/assets":
            data = self.read_json()
            required = ["id", "product", "type", "model"]
            if any(not str(data.get(key, "")).strip() for key in required):
                return self.json_response({"error": "请填写完整的资产信息"}, 400)
            unit = {"测试机": "台", "DC线": "套"}.get(data["type"], "件")
            try:
                with connection() as db:
                    db.execute(
                        "INSERT INTO assets(id,product,type,model,location,qty,unit,sent_date,status,file_name,compatible,note) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                        (data["id"], data["product"], data["type"], data["model"], data.get("location", "我司仓库"), int(data.get("qty", 1)), unit, "—", "可用", "暂未上传", data.get("fit", "—"), data.get("note", "新建资产")),
                    )
                    row = db.execute("SELECT * FROM assets WHERE id=?", (data["id"],)).fetchone()
            except sqlite3.IntegrityError:
                return self.json_response({"error": "资产编号已存在"}, 409)
            return self.json_response(asset_dict(row), 201)
        if path == "/api/shipments":
            data = self.read_json()
            with connection() as db:
                asset = db.execute("SELECT * FROM assets WHERE id=?", (data.get("asset_id"),)).fetchone()
                if not asset:
                    return self.json_response({"error": "资产不存在"}, 404)
                db.execute(
                    "INSERT INTO shipments(asset_id,from_location,to_location,sent_date,tracking_no,handler,note) VALUES(?,?,?,?,?,?,?)",
                    (asset["id"], asset["location"], data["location"], data["date"], data.get("tracking_no", ""), data.get("handler", ""), data.get("note", "")),
                )
                db.execute("UPDATE assets SET location=?,sent_date=?,status='使用中',updated_at=CURRENT_TIMESTAMP WHERE id=?", (data["location"], data["date"], asset["id"]))
            return self.json_response({"ok": True}, 201)
        if path == "/api/files":
            fields, uploaded = self.read_multipart()
            asset_id = fields.get("asset_id", "")
            if not asset_id or uploaded is None or not uploaded["filename"]:
                return self.json_response({"error": "请选择资产和文件"}, 400)
            safe_name = Path(uploaded["filename"]).name
            stored_name = f"{datetime.now().strftime('%Y%m%d%H%M%S%f')}_{safe_name}"
            content = uploaded["content"]
            (UPLOAD_DIR / stored_name).write_bytes(content)
            content_type = uploaded["content_type"] or mimetypes.guess_type(safe_name)[0] or "application/octet-stream"
            try:
                with connection() as db:
                    cur = db.execute("INSERT INTO files(asset_id,original_name,stored_name,size,content_type) VALUES(?,?,?,?,?)", (asset_id, safe_name, stored_name, len(content), content_type))
                    db.execute("UPDATE assets SET file_name=?,updated_at=CURRENT_TIMESTAMP WHERE id=?", (safe_name, asset_id))
                    row = db.execute("SELECT * FROM files WHERE id=?", (cur.lastrowid,)).fetchone()
            except sqlite3.IntegrityError:
                (UPLOAD_DIR / stored_name).unlink(missing_ok=True)
                return self.json_response({"error": "关联资产不存在"}, 400)
            return self.json_response(dict(row), 201)
        if path == "/api/releases":
            data = self.read_json()
            if not all(str(data.get(key, "")).strip() for key in ("version", "title", "content", "released_at")):
                return self.json_response({"error": "请填写完整的版本说明"}, 400)
            try:
                with connection() as db:
                    cur = db.execute("INSERT INTO releases(version,title,content,released_at) VALUES(?,?,?,?)", (data["version"], data["title"], data["content"], data["released_at"]))
                    row = db.execute("SELECT * FROM releases WHERE id=?", (cur.lastrowid,)).fetchone()
            except sqlite3.IntegrityError:
                return self.json_response({"error": "版本号已存在"}, 409)
            return self.json_response(dict(row), 201)
        return self.json_response({"error": "接口不存在"}, 404)

    def do_PUT(self):
        path = urllib.parse.urlparse(self.path).path
        if not self.require_admin():
            return
        if not path.startswith("/api/assets/"):
            return self.json_response({"error": "接口不存在"}, 404)
        asset_id = urllib.parse.unquote(path.split("/api/assets/", 1)[1])
        data = self.read_json()
        with connection() as db:
            current = db.execute("SELECT * FROM assets WHERE id=?", (asset_id,)).fetchone()
            if not current:
                return self.json_response({"error": "资产不存在"}, 404)
            fields = {"product": data.get("product", current["product"]), "type": data.get("type", current["type"]), "model": data.get("model", current["model"]), "location": data.get("location", current["location"]), "qty": int(data.get("qty", current["qty"])), "status": data.get("status", current["status"]), "compatible": data.get("fit", current["compatible"]), "note": data.get("note", current["note"])}
            db.execute("UPDATE assets SET product=:product,type=:type,model=:model,location=:location,qty=:qty,status=:status,compatible=:compatible,note=:note,updated_at=CURRENT_TIMESTAMP WHERE id=:id", {**fields, "id": asset_id})
            row = db.execute("SELECT * FROM assets WHERE id=?", (asset_id,)).fetchone()
        return self.json_response(asset_dict(row))

    def do_DELETE(self):
        path = urllib.parse.urlparse(self.path).path
        if not self.require_admin():
            return
        if not path.startswith("/api/assets/"):
            return self.json_response({"error": "接口不存在"}, 404)
        asset_id = urllib.parse.unquote(path.split("/api/assets/", 1)[1])
        with connection() as db:
            files = db.execute("SELECT stored_name FROM files WHERE asset_id=?", (asset_id,)).fetchall()
            cur = db.execute("DELETE FROM assets WHERE id=?", (asset_id,))
        if not cur.rowcount:
            return self.json_response({"error": "资产不存在"}, 404)
        for row in files:
            (UPLOAD_DIR / row["stored_name"]).unlink(missing_ok=True)
        return self.json_response({"ok": True})


if __name__ == "__main__":
    init_db()
    server = ThreadingHTTPServer((HOST, PORT), AppHandler)
    print(f"测试资源管理已启动：http://{HOST}:{PORT}")
    print(f"本地数据库：{DB_PATH}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n服务已停止")
    finally:
        server.server_close()
