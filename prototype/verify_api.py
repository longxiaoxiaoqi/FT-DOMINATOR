import json
import urllib.request

BASE = "http://127.0.0.1:4173"
TEST_ID = "LOCAL-DB-VERIFY-001"


def request(path, method="GET", payload=None):
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(BASE + path, data=body, method=method)
    if body is not None:
        req.add_header("Content-Type", "application/json; charset=utf-8")
    with urllib.request.urlopen(req) as response:
        return json.loads(response.read().decode("utf-8"))


cookie_jar = urllib.request.HTTPCookieProcessor()
opener = urllib.request.build_opener(cookie_jar)


def authed_request(path, method="GET", payload=None):
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(BASE + path, data=body, method=method)
    if body is not None:
        req.add_header("Content-Type", "application/json; charset=utf-8")
    with opener.open(req) as response:
        return json.loads(response.read().decode("utf-8"))


authed_request("/api/login", "POST", {"mode": "admin", "username": "admin", "password": "admin"})


try:
    authed_request("/api/assets/" + TEST_ID, "DELETE")
except Exception:
    pass

created = authed_request("/api/assets", "POST", {
    "id": TEST_ID,
    "product": "验证产品",
    "type": "DC线",
    "model": "本地数据库验证线",
    "qty": 1,
    "fit": "TESTER-VERIFY",
    "note": "接口自动测试",
})
assert created["id"] == TEST_ID

edited = authed_request("/api/assets/" + TEST_ID, "PUT", {
    "qty": 2,
    "location": "我司仓库",
    "status": "可用",
    "note": "编辑验证成功",
})
assert edited["qty"] == 2

authed_request("/api/shipments", "POST", {
    "asset_id": TEST_ID,
    "location": "苏州封装厂",
    "date": "2026-08-14",
    "tracking_no": "VERIFY001",
    "handler": "自动测试",
    "note": "寄送验证",
})

persisted = next(asset for asset in authed_request("/api/assets") if asset["id"] == TEST_ID)
assert persisted["location"] == "苏州封装厂"
assert persisted["date"] == "2026-08-14"

authed_request("/api/assets/" + TEST_ID, "DELETE")
assert not any(asset["id"] == TEST_ID for asset in authed_request("/api/assets"))
print("api_create_edit_ship_delete=ok")
