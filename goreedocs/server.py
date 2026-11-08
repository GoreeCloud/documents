"""GoreeCloud Documents: bounded, local-first Markdown document service."""
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
from hashlib import sha256
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import hmac
import json
import os
from pathlib import Path
import re
import secrets
import sqlite3
from threading import Lock
from urllib.parse import parse_qs, unquote, urlsplit
from uuid import uuid4

MAX_BODY = 1024 * 1024
MAX_JSON = MAX_BODY + 4096
DOC_ID = re.compile(r"^[0-9a-f-]{36}$")
SHARE_TOKEN = re.compile(r"^[A-Za-z0-9_-]{20,120}$")
ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "web"


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Problem(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status
        self.message = message


def cleaned(data, creating=False):
    if not isinstance(data, dict):
        raise Problem(400, "Expected a JSON object")
    permitted = {"title", "body", "folder", "format", "favorite"}
    if not set(data).issubset(permitted):
        raise Problem(400, "Unknown document property")
    result = {}
    if creating or "title" in data:
        title = data.get("title")
        if not isinstance(title, str) or not 1 <= len(title.strip()) <= 160 or "\n" in title:
            raise Problem(400, "Title must be 1 to 160 characters")
        result["title"] = title.strip()
    if creating or "body" in data:
        body = data.get("body", "")
        if not isinstance(body, str) or len(body.encode("utf-8")) > MAX_BODY or "\x00" in body:
            raise Problem(413, "Markdown content exceeds 1 MiB or is invalid")
        result["body"] = body
    if creating or "folder" in data:
        folder = data.get("folder", "")
        if not isinstance(folder, str) or len(folder) > 240 or "\x00" in folder or "\\" in folder:
            raise Problem(400, "Invalid folder")
        bits = folder.strip("/").split("/") if folder.strip("/") else []
        if len(bits) > 8 or any(bit in {".", ".."} or not bit or bit != bit.strip() for bit in bits):
            raise Problem(400, "Invalid folder")
        result["folder"] = "/".join(bits)
    if creating or "format" in data:
        fmt = data.get("format", "gcdoc")
        if fmt not in ("gcdoc", "md"):
            raise Problem(400, "Format must be gcdoc or md")
        result["format"] = fmt
    if creating or "favorite" in data:
        fav = data.get("favorite", False)
        if type(fav) is not bool:
            raise Problem(400, "Favorite must be boolean")
        result["favorite"] = fav
    return result


class Store:
    def __init__(self, path):
        target = Path(path).expanduser().resolve()
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if target.parent.stat().st_mode & 0o077:
            raise Problem(403, "Database directory must be owner-private (chmod 700)")
        if target.exists():
            if not target.is_file() or target.stat().st_mode & 0o077:
                raise Problem(403, "Database file must be owner-private (chmod 600)")
        else:
            try:
                fd = os.open(target, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
                os.close(fd)
            except FileExistsError:
                raise Problem(409, "Database path was concurrently created")
        self.path = str(target)
        self.setup()

    @contextmanager
    def db(self):
        c = sqlite3.connect(self.path, timeout=10)
        c.row_factory = sqlite3.Row
        try:
            c.execute("PRAGMA busy_timeout = 10000")
            c.execute("PRAGMA foreign_keys = ON")
            yield c
            c.commit()
        except Exception:
            c.rollback()
            raise
        finally:
            c.close()

    def setup(self):
        with self.db() as c:
            c.execute("PRAGMA journal_mode=WAL")
            c.executescript("""
            CREATE TABLE IF NOT EXISTS documents (
                id TEXT PRIMARY KEY, title TEXT NOT NULL, body TEXT NOT NULL,
                folder TEXT NOT NULL DEFAULT '', version INTEGER NOT NULL,
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL, deleted_at TEXT
            );
            CREATE TABLE IF NOT EXISTS revisions (
                doc_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
                version INTEGER NOT NULL, title TEXT NOT NULL, body TEXT NOT NULL,
                folder TEXT NOT NULL, created_at TEXT NOT NULL,
                PRIMARY KEY(doc_id, version)
            );
            CREATE TABLE IF NOT EXISTS shares (
                token_hash TEXT PRIMARY KEY, doc_id TEXT NOT NULL
                REFERENCES documents(id) ON DELETE CASCADE,
                expires_at TEXT NOT NULL, revoked_at TEXT, created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS documents_folder ON documents(folder);
            CREATE INDEX IF NOT EXISTS shares_doc ON shares(doc_id);
            """)
            columns = {r[1] for r in c.execute("PRAGMA table_info(documents)")}
            if "format" not in columns:
                c.execute("ALTER TABLE documents ADD COLUMN format TEXT NOT NULL DEFAULT 'md'")
            if "favorite" not in columns:
                c.execute("ALTER TABLE documents ADD COLUMN favorite INTEGER NOT NULL DEFAULT 0")


    @staticmethod
    def _summary(row):
        data = {k: row[k] for k in ("id", "title", "folder", "version", "created_at", "updated_at", "deleted_at", "format")}
        data["favorite"] = bool(row["favorite"])
        data["excerpt"] = " ".join(row["body"].split())[:260]
        return data

    def list(self, query="", trash=False):
        if not isinstance(query, str) or len(query) > 200:
            raise Problem(400, "Invalid search query")
        with self.db() as c:
            if query:
                rows = c.execute("""SELECT * FROM documents WHERE deleted_at IS """ +
                    ("NOT NULL" if trash else "NULL") + """ AND
                    (instr(lower(title), lower(?)) > 0 OR
                     instr(lower(body), lower(?)) > 0 OR
                     instr(lower(folder), lower(?)) > 0)
                     ORDER BY updated_at DESC, id DESC LIMIT 200""",
                    (query, query, query)).fetchall()
            else:
                rows = c.execute("SELECT * FROM documents WHERE deleted_at IS " +
                                 ("NOT NULL" if trash else "NULL") +
                                 " ORDER BY updated_at DESC, id DESC LIMIT 200").fetchall()
            return [self._summary(row) for row in rows]

    def search(self, query="", trash=False, folder="", fmt="", favorites=False, recent=False,
               sort="updated", direction="desc", limit=60, offset=0):
        if not isinstance(query,str) or len(query)>200:
            raise Problem(400, "Search query is too long")
        if not isinstance(folder,str) or len(folder)>240:
            raise Problem(400, "Invalid folder filter")
        if fmt not in ("","gcdoc","md"):
            raise Problem(400, "Invalid format filter")
        sort_columns={"updated":"updated_at", "created":"created_at",
                      "title":"title COLLATE NOCASE"}
        if sort not in sort_columns or direction not in ("asc","desc"):
            raise Problem(400, "Invalid sort")
        if type(limit) is not int or type(offset) is not int or not 1<=limit<=100 or not 0<=offset<=1000000:
            raise Problem(400, "Invalid pagination")
        clauses=["deleted_at IS "+("NOT NULL" if trash else "NULL")]
        params=[]
        if query:
            clauses.append("(instr(lower(title), lower(?))>0 OR instr(lower(body), lower(?))>0 OR instr(lower(folder), lower(?))>0)")
            params += [query,query,query]
        if folder:
            # SQLite LIKE treats % and _ in a folder name as wildcards.
            # A literal path prefix followed by "/" preserves hierarchy exactly.
            clauses.append("(folder=? OR instr(folder, ?) = 1)")
            params += [folder, folder+"/"]
        if fmt:
            clauses.append("format=?")
            params.append(fmt)
        if favorites:
            clauses.append("favorite=1")
        if recent:
            from datetime import timedelta
            clauses.append("updated_at>=?")
            params.append((datetime.now(timezone.utc)-timedelta(days=7)).isoformat(timespec="seconds"))
        where=" AND ".join(clauses)
        order=sort_columns[sort]+" "+direction.upper()+", id DESC"
        with self.db() as c:
            total=c.execute("SELECT count(*) FROM documents WHERE "+where, params).fetchone()[0]
            rows=c.execute("SELECT * FROM documents WHERE "+where+" ORDER BY "+order+" LIMIT ? OFFSET ?",
                           params+[limit,offset]).fetchall()
        return {"documents":[self._summary(r) for r in rows],
                "total":total,"offset":offset,"limit":limit,"has_more":offset+len(rows)<total}

    def overview(self):
        with self.db() as c:
            live=c.execute("SELECT count(*) FROM documents WHERE deleted_at IS NULL").fetchone()[0]
            fav=c.execute("SELECT count(*) FROM documents WHERE favorite=1 AND deleted_at IS NULL").fetchone()[0]
            trash=c.execute("SELECT count(*) FROM documents WHERE deleted_at IS NOT NULL").fetchone()[0]
            from datetime import timedelta
            cutoff=(datetime.now(timezone.utc)-timedelta(days=7)).isoformat(timespec="seconds")
            recent=c.execute("SELECT count(*) FROM documents WHERE deleted_at IS NULL AND updated_at>=?",(cutoff,)).fetchone()[0]
            folders=[{"name":r[0], "count":r[1]} for r in c.execute(
                "SELECT folder,count(*) FROM documents WHERE deleted_at IS NULL AND folder<>'' GROUP BY folder ORDER BY folder COLLATE NOCASE LIMIT 200")]
        return {"total":live,"favorites":fav,"trash":trash,"recent":recent,"folders":folders}

    def export(self, doc_id, fmt=None):
        doc=self.get(doc_id)
        fmt=fmt or doc["format"]
        if fmt not in ("gcdoc","md"):
            raise Problem(400,"Unknown export format")
        stem=re.sub(r"[^a-zA-Z0-9._ -]+","",doc["title"]).strip(" .")[:80] or "document"
        if fmt=="md":
            return {"filename":stem+".md", "content":doc["body"],"mime_type":"text/markdown; charset=utf-8"}
        package={"kind":"goreecloud.document", "schema_version":1,"title":doc["title"],
                 "body":doc["body"],"folder":doc["folder"],"format":"gcdoc"}
        content=json.dumps(package,ensure_ascii=False,indent=2)+"\n"
        if len(content.encode("utf-8"))>MAX_JSON:
            raise Problem(413,"GCDOC export exceeds the import size limit; export Markdown (.md) instead")
        return {"filename":stem+".gcdoc","content":content,
                "mime_type":"application/vnd.goreecloud.document+json"}

    def import_file(self, data):
        if not isinstance(data,dict) or set(data)!={"filename","content"}:
            raise Problem(400,"Expected filename and content")
        name,content=data["filename"],data["content"]
        if not isinstance(name,str) or not isinstance(content,str) or len(name)>180 or len(content.encode("utf-8"))>MAX_JSON:
            raise Problem(413,"Invalid import size")
        if "/" in name or "\\" in name or "\x00" in name or name.startswith("."):
            raise Problem(400,"Invalid filename")
        if name.lower().endswith(".gcdoc"):
            try:
                package=json.loads(content)
            except ValueError:
                raise Problem(400,"Invalid GCDOC JSON")
            if not isinstance(package,dict) or package.get("kind")!="goreecloud.document" or type(package.get("schema_version")) is not int or package["schema_version"]!=1:
                raise Problem(400,"Unsupported GCDOC schema")
            if not set(package).issubset({"kind","schema_version","title","body","folder","format"}):
                raise Problem(400,"Unknown GCDOC fields")
            return self.create({"title":package.get("title"),"body":package.get("body"),
                                "folder":package.get("folder",""),"format":"gcdoc"})
        if name.lower().endswith(".md"):
            return self.create({"title":name[:-3],"body":content,"format":"md","folder":""})
        raise Problem(415,"Only .gcdoc and .md imports supported")

    def get(self, doc_id, include_deleted=False):
        if not DOC_ID.fullmatch(doc_id):
            raise Problem(404, "Document not found")
        with self.db() as c:
            row = c.execute("SELECT * FROM documents WHERE id=?", (doc_id,)).fetchone()
            if row is None or (row["deleted_at"] and not include_deleted):
                raise Problem(404, "Document not found")
            return dict(row)

    def create(self, data):
        value = cleaned(data, True)
        stamp = now()
        doc_id = str(uuid4())
        with self.db() as c:
            c.execute("""INSERT INTO documents (id,title,body,folder,version,created_at,updated_at,format,favorite)
                VALUES (?,?,?,?,1,?,?,?,?)""",
                (doc_id, value["title"], value["body"], value["folder"], stamp, stamp,
                 value["format"], int(value["favorite"])))
            c.execute("""INSERT INTO revisions VALUES (?,?,?,?,?,?)""",
                (doc_id, 1, value["title"], value["body"], value["folder"], stamp))
        return self.get(doc_id)

    def update(self, doc_id, data, expected_version):
        changes = cleaned(data)
        if not changes:
            raise Problem(400, "No document changes")
        if type(expected_version) is not int or expected_version < 1:
            raise Problem(428, "A current integer version is required")
        with self.db() as c:
            c.execute("BEGIN IMMEDIATE")
            row = c.execute("SELECT * FROM documents WHERE id=? AND deleted_at IS NULL", (doc_id,)).fetchone()
            if not row:
                raise Problem(404, "Document not found")
            if row["version"] != expected_version:
                raise Problem(409, "Version conflict; reload before saving")
            fields = {k: changes.get(k, row[k]) for k in ("title", "body", "folder", "format", "favorite")}
            stamp, version = now(), expected_version + 1
            c.execute("""UPDATE documents SET title=?,body=?,folder=?,format=?,favorite=?,version=?,updated_at=? WHERE id=?""",
                      (fields["title"], fields["body"], fields["folder"], fields["format"],
                       int(fields["favorite"]),version,stamp,doc_id))
            c.execute("INSERT INTO revisions VALUES (?,?,?,?,?,?)",
                      (doc_id, version, fields["title"], fields["body"], fields["folder"], stamp))
        return self.get(doc_id)

    def change_trash(self, doc_id, deleted):
        with self.db() as c:
            c.execute("BEGIN IMMEDIATE")
            row = c.execute("SELECT * FROM documents WHERE id=?", (doc_id,)).fetchone()
            if not row:
                raise Problem(404, "Document not found")
            if bool(row["deleted_at"]) == deleted:
                raise Problem(409, "Document already in requested state")
            stamp = now()
            c.execute("UPDATE documents SET deleted_at=?,updated_at=? WHERE id=?",
                      (stamp if deleted else None, stamp, doc_id))
            if deleted:
                # A trashed document must not reactivate previously distributed links.
                c.execute("UPDATE shares SET revoked_at=? WHERE doc_id=? AND revoked_at IS NULL",
                          (stamp, doc_id))
        return self.get(doc_id, True)

    def history(self, doc_id):
        self.get(doc_id, True)
        with self.db() as c:
            return [dict(r) for r in c.execute("""SELECT version,title,folder,created_at
                       FROM revisions WHERE doc_id=? ORDER BY version DESC LIMIT 200""", (doc_id,))]

    def version(self, doc_id, version):
        self.get(doc_id, True)
        with self.db() as c:
            r = c.execute("SELECT * FROM revisions WHERE doc_id=? AND version=?", (doc_id, version)).fetchone()
            if not r:
                raise Problem(404, "Revision not found")
            return dict(r)

    def restore_revision(self, doc_id, revision, expected_version):
        source = self.version(doc_id, revision)
        return self.update(doc_id, {k: source[k] for k in ("title", "body", "folder")}, expected_version)

    def share(self, doc_id, hours):
        self.get(doc_id)
        if type(hours) is not int or not 1 <= hours <= 168:
            raise Problem(400, "Share expiry must be 1 to 168 hours")
        from datetime import timedelta
        token = secrets.token_urlsafe(32)
        expires = (datetime.now(timezone.utc) + timedelta(hours=hours)).isoformat(timespec="seconds")
        with self.db() as c:
            c.execute("INSERT INTO shares VALUES (?,?,?,?,?)",
                      (sha256(token.encode()).hexdigest(), doc_id, expires, None, now()))
        return {"token": token, "expires_at": expires}

    def public(self, token):
        if not SHARE_TOKEN.fullmatch(token):
            raise Problem(404, "Share not found")
        with self.db() as c:
            row = c.execute("""SELECT d.title,d.body,d.updated_at,s.expires_at FROM shares s
                  JOIN documents d ON d.id=s.doc_id WHERE s.token_hash=?
                  AND s.revoked_at IS NULL AND s.expires_at > ?
                  AND d.deleted_at IS NULL""", (sha256(token.encode()).hexdigest(), now())).fetchone()
            if row is None:
                raise Problem(404, "Share not found or expired")
            return dict(row)

    def revoke(self, token):
        if not SHARE_TOKEN.fullmatch(token):
            raise Problem(404, "Share not found")
        with self.db() as c:
            result = c.execute("""UPDATE shares SET revoked_at=? WHERE token_hash=?
                           AND revoked_at IS NULL""", (now(), sha256(token.encode()).hexdigest()))
            if result.rowcount == 0:
                raise Problem(404, "Share not found")
        return {"revoked": True}


class Service(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address, store, secret):
        super().__init__(address, Handler)
        self.store = store
        self.secret = secret


class Handler(BaseHTTPRequestHandler):
    server_version = "GoreeDocs/0.1"
    def log_message(self, fmt, *args):
        # Do not log request paths: public share URLs contain bearer-equivalent tokens.
        print("http", self.command, self.path.split("?")[0].split("/")[1:2], args[1:2], flush=True)

    def headers_common(self, mime, length, status):
        self.send_response(status)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(length))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Content-Security-Policy", "default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self'; connect-src 'self'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'")
        self.end_headers()

    def respond(self, data, status=200):
        payload = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.headers_common("application/json; charset=utf-8", len(payload), status)
        self.wfile.write(payload)

    def static(self, name, mime):
        payload = (ASSETS / name).read_bytes()
        self.headers_common(mime, len(payload), 200)
        self.wfile.write(payload)

    def require_auth(self):
        supplied = self.headers.get("Authorization", "")
        correct = "Bearer " + self.server.secret
        if not hmac.compare_digest(supplied.encode("utf-8"), correct.encode("utf-8")):
            raise Problem(401, "Authorization required")

    def body(self):
        content_type = self.headers.get("Content-Type", "").split(";")[0].strip().lower()
        if content_type != "application/json":
            raise Problem(415, "Use application/json")
        try:
            size = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            raise Problem(400, "Invalid Content-Length")
        if size <= 0 or size > MAX_JSON:
            raise Problem(413, "Request size invalid or too large")
        try:
            return json.loads(self.rfile.read(size))
        except (ValueError, UnicodeDecodeError):
            raise Problem(400, "Invalid JSON")

    def dispatch(self, method):
        parsed = urlsplit(self.path)
        path = unquote(parsed.path)
        if method == "GET":
            if path == "/healthz":
                return self.respond({"status": "ok"})
            static_routes = {"/": ("index.html", "text/html; charset=utf-8"),
                             "/app.js": ("app.js", "application/javascript; charset=utf-8"),
                             "/style.css": ("style.css", "text/css; charset=utf-8"),
                             "/share": ("share.html", "text/html; charset=utf-8"),
                             "/share.js": ("share.js", "application/javascript; charset=utf-8")}
            if path in static_routes:
                return self.static(*static_routes[path])
            if path.startswith("/api/public/"):
                return self.respond(self.server.store.public(path.removeprefix("/api/public/")))
        if not path.startswith("/api/"):
            raise Problem(404, "Not found")
        self.require_auth()
        store = self.server.store
        parts = path.strip("/").split("/")
        args = parse_qs(parsed.query)
        if parts == ["api", "overview"] and method == "GET":
            return self.respond(store.overview())
        if parts == ["api", "documents", "import"] and method == "POST":
            return self.respond(store.import_file(self.body()),201)
        if parts == ["api", "documents"]:
            if method == "GET":
                return self.respond(store.search(
                    query=args.get("q",[""])[0], trash=args.get("trash",["0"])[0]=="1",
                    folder=args.get("folder",[""])[0],fmt=args.get("format",[""])[0],
                    favorites=args.get("favorites",["0"])[0]=="1",recent=args.get("recent",["0"])[0]=="1",
                    sort=args.get("sort",["updated"])[0],direction=args.get("direction",["desc"])[0],
                    limit=int(args.get("limit",["60"])[0]),offset=int(args.get("offset",["0"])[0])))
            if method == "POST":
                return self.respond(store.create(self.body()), 201)
        if len(parts) >= 3 and parts[:2] == ["api", "documents"] and DOC_ID.fullmatch(parts[2]):
            doc = parts[2]
            if len(parts) == 3:
                if method == "GET":
                    return self.respond(store.get(doc, args.get("trash", ["0"])[0] == "1"))
                if method == "PATCH":
                    data = self.body()
                    if not isinstance(data, dict):
                        raise Problem(400, "Expected object")
                    version = data.pop("version", None)
                    return self.respond(store.update(doc, data, version))
            if len(parts) == 4:
                action = parts[3]
                if method == "POST" and action in ("trash", "restore"):
                    return self.respond(store.change_trash(doc, action == "trash"))
                if method == "GET" and action == "export":
                    return self.respond(store.export(doc, args.get("format",[None])[0]))
                if method == "GET" and action == "revisions":
                    return self.respond({"revisions": store.history(doc)})
                if method == "POST" and action == "share":
                    data = self.body()
                    if not isinstance(data, dict):
                        raise Problem(400, "Expected object")
                    return self.respond(store.share(doc, data.get("hours", 24)), 201)
            if len(parts) == 5 and parts[3] == "revisions" and parts[4].isdigit():
                revision = int(parts[4])
                if method == "GET":
                    return self.respond(store.version(doc, revision))
                if method == "POST":
                    data = self.body()
                    return self.respond(store.restore_revision(doc, revision, data.get("version") if isinstance(data, dict) else None))
        if len(parts) == 3 and parts[:2] == ["api", "shares"] and method == "DELETE":
            return self.respond(store.revoke(parts[2]))
        raise Problem(404, "Not found")

    def do_GET(self):
        self.run("GET")

    def do_POST(self):
        self.run("POST")

    def do_PATCH(self):
        self.run("PATCH")

    def do_DELETE(self):
        self.run("DELETE")

    def run(self, method):
        try:
            self.dispatch(method)
        except Problem as e:
            self.respond({"error": e.message}, e.status)
        except ValueError:
            self.respond({"error":"Invalid numeric query parameter"},400)
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception:
            self.respond({"error": "Internal server error"}, 500)


def main():
    p = argparse.ArgumentParser(description="GoreeCloud Documents local development server")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8735)
    p.add_argument("--db", default=os.environ.get("GOREEDOCS_DB", "./data/documents.sqlite3"))
    args = p.parse_args()
    token = os.environ.get("GOREEDOCS_TOKEN", "")
    if len(token) < 32 or len(set(token)) < 12:
        p.error("Set GOREEDOCS_TOKEN to a strong random token (at least 32 characters)")
    if args.host not in ("127.0.0.1", "::1", "localhost"):
        p.error("Public binding is disabled in this development preview")
    os.umask(0o077)  # Ensure SQLite WAL/shm and future files remain owner-private.
    server = Service((args.host, args.port), Store(args.db), token)
    print("GoreeCloud Documents: http://%s:%d (local-only)" % server.server_address, flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
