"""Checks for the Supabase additions (no network, no pytest):  python tests/supabase.py

- connection options chosen for each kind of DATABASE_URL
- Supabase Storage upload/delete against a local stub server
"""
import io
import os
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.mkdtemp()}/t.db"
os.environ.pop("VERCEL", None)

from werkzeug.datastructures import FileStorage  # noqa: E402

from laicq import _opcoes_postgres, create_app, storage  # noqa: E402

ok = 0


def check(cond, msg):
    global ok
    assert cond, "FAILED: " + msg
    ok += 1
    print("  ok -", msg)


# ------------------------------------------------------------------ connection options
print("Connection options")
pooler = "postgresql://postgres.ref:pw@aws-0-sa-east-1.pooler.supabase.com:6543/postgres"
session = "postgresql://postgres.ref:pw@aws-0-sa-east-1.pooler.supabase.com:5432/postgres"
check(_opcoes_postgres(pooler) == {"connect_args": {"sslmode": "require", "prepare_threshold": None}},
      "transaction pooler: SSL required, prepared statements off")
check(_opcoes_postgres(session) == {"connect_args": {"sslmode": "require"}},
      "session pooler: SSL required, prepared statements kept")
check(_opcoes_postgres(pooler + "?sslmode=verify-full")["connect_args"] == {"prepare_threshold": None},
      "an explicit sslmode is respected")
check(_opcoes_postgres("postgresql://u:p@localhost/db") == {}, "localhost: no extra options")
check(_opcoes_postgres("postgresql://u:p@/db?host=/tmp/sock") == {}, "unix socket: no extra options")
check(_opcoes_postgres("sqlite:///x.db") == {}, "sqlite: no extra options")

# ------------------------------------------------------------------ storage against a stub
calls = []


class Stub(BaseHTTPRequestHandler):
    def _record(self):
        body = self.rfile.read(int(self.headers.get("content-length") or 0))
        calls.append((self.command, self.path, {k.lower(): v for k, v in self.headers.items()}, body))
        self.send_response(200)
        self.send_header("content-type", "application/json")
        self.end_headers()
        self.wfile.write(b"{}")

    do_POST = do_DELETE = _record

    def log_message(self, *a):
        pass


server = HTTPServer(("127.0.0.1", 0), Stub)
threading.Thread(target=server.serve_forever, daemon=True).start()
base = f"http://127.0.0.1:{server.server_port}"

app = create_app({"TESTING": True})
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32


def upload(name="foto.png", data=PNG):
    return storage.salvar(FileStorage(io.BytesIO(data), filename=name))


print("Supabase Storage")
with app.app_context():
    os.environ.update(SUPABASE_URL=base + "/", SUPABASE_SECRET_KEY="sb_secret_abc", SUPABASE_BUCKET="laicq")
    url = upload()
    method, path, headers, body = calls[-1]
    check(method == "POST" and path.startswith("/storage/v1/object/laicq/") and path.endswith(".png"),
          "upload goes to /storage/v1/object/<bucket>/<name>")
    check(url == f"{base}/storage/v1/object/public/laicq/{path.rsplit('/', 1)[-1]}", "returns the public URL")
    check(headers.get("apikey") == "sb_secret_abc" and "authorization" not in headers,
          "new-format key: apikey header only")
    check(headers.get("content-type") == "image/png" and body == PNG, "content type and bytes are sent")

    storage.remover(url)
    method, path, headers, _ = calls[-1]
    check(method == "DELETE" and path == f"/storage/v1/object/laicq/{url.rsplit('/', 1)[-1]}", "delete uses the object path")

    n = len(calls)
    storage.remover("https://elsewhere.example/img.png")
    check(len(calls) == n, "foreign URLs are never deleted")

    os.environ["SUPABASE_SECRET_KEY"] = "eyJlegacy.jwt.key"
    upload()
    headers = calls[-1][2]
    check(headers.get("authorization") == "Bearer eyJlegacy.jwt.key" and headers.get("apikey") == "eyJlegacy.jwt.key",
          "legacy JWT key: apikey and Authorization")

    for bad, label in (("x.exe", "unsupported extension"), ("x.png", "fake image")):
        n = len(calls)
        try:
            upload(bad, b"MZ not an image")
            check(False, label + " must be rejected")
        except ValueError:
            check(len(calls) == n, label + " rejected before any request")

    # no Supabase variables: falls back to the local folder (development)
    for k in ("SUPABASE_URL", "SUPABASE_SECRET_KEY", "SUPABASE_BUCKET"):
        os.environ.pop(k)
    n = len(calls)
    check(upload().startswith("/uploads/") and len(calls) == n, "without variables: local folder, no requests")

print(f"\n{ok} checks passed.")
