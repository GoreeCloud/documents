"""Integration and regression checks for document storage, REST, and AI bridge."""
import json
from http.client import HTTPConnection
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from goreedocs.server import MAX_JSON, Problem, Service, Store
from goreedocs import cli, mcp


class DocumentsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = Store(Path(self.tmp.name) / "docs.sqlite3")
        self.secret = "0123456789abcdefghijklmnopqrstuvwxyz_SAFE"
        self.srv = Service(("127.0.0.1", 0), self.store, self.secret)
        self.addCleanup(self.srv.server_close)
        thread = threading.Thread(target=self.srv.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(self.srv.shutdown)
        self.url = "http://127.0.0.1:%d" % self.srv.server_address[1]

    def req(self, path, method="GET", data=None, key=True):
        headers = {"Authorization": "Bearer " + (self.secret if key else "wrong")}
        if data is not None:
            headers["Content-Type"] = "application/json"
        req = Request(self.url+path, method=method, headers=headers,
                      data=None if data is None else json.dumps(data).encode())
        try:
            with urlopen(req, timeout=5) as res:
                return res.status, json.load(res)
        except HTTPError as e:
            return e.code, json.loads(e.read())

    def test_auth_and_create(self):
        self.assertEqual(self.req("/api/documents", key=False)[0], 401)
        code, doc = self.req("/api/documents", "POST", {"title":"Policy","body":"# Private","folder":"GoreeCloud/Policies"})
        self.assertEqual(code, 201)
        self.assertEqual(doc["version"], 1)
        self.assertEqual(self.req("/api/documents/"+doc["id"])[1]["body"], "# Private")
        self.assertEqual(len(self.req("/api/documents?q=polic")[1]["documents"]),1)
        self.assertEqual(len(self.req("/api/documents?q=%25")[1]["documents"]),0)
        self.assertEqual(self.req("/api/documents", "POST", {"title":"a","body":"","folder":"../secret"})[0], 400)
        self.assertEqual(self.req("/api/documents", "POST", {"title":"a","body":"x"*(1024*1024+1)})[0], 413)

    def test_import_nested_json_transport_uses_strict_file_limits(self):
        escaped = chr(92) * 400_000
        status, original = self.req("/api/documents", "POST",
                                    {"title": "Synthetic", "body": escaped, "format": "gcdoc"})
        self.assertEqual(status, 201)
        status, native = self.req("/api/documents/" + original["id"] + "/export")
        self.assertEqual(status, 200)
        self.assertLessEqual(len(native["content"].encode("utf-8")), MAX_JSON)
        wrapped = {"filename": native["filename"], "content": native["content"]}
        self.assertGreater(len(json.dumps(wrapped).encode("utf-8")), MAX_JSON)
        status, imported = self.req("/api/documents/import", "POST", wrapped)
        self.assertEqual(status, 201, imported)
        self.assertEqual(imported["body"], escaped)
        self.assertNotEqual(imported["id"], original["id"])

        markdown = {"filename": "sample.md", "content": chr(92) * 600_000}
        self.assertGreater(len(json.dumps(markdown).encode("utf-8")), MAX_JSON)
        status, imported_md = self.req("/api/documents/import", "POST", markdown)
        self.assertEqual(status, 201, imported_md)
        self.assertEqual(imported_md["body"], markdown["content"])

        status, _ = self.req("/api/documents/import", "POST",
                             {"filename": "oversized.md", "content": "x" * (MAX_JSON + 1)})
        self.assertEqual(status, 413)
        # Send only the oversized length header. A server may close the
        # connection before a client finishes streaming a rejected large body.
        connection = HTTPConnection("127.0.0.1", self.srv.server_address[1], timeout=5)
        try:
            connection.putrequest("POST", "/api/documents")
            connection.putheader("Authorization", "Bearer " + self.secret)
            connection.putheader("Content-Type", "application/json")
            connection.putheader("Content-Length", str(MAX_JSON + 1))
            connection.endheaders()
            response = connection.getresponse()
            self.assertEqual(response.status, 413)
            response.read()
        finally:
            connection.close()

    def test_rest_folder_search_uses_literal_names_and_descendants(self):
        names = [
            ("Finance%", "literal"),
            ("Finance%/2026", "child"),
            ("FinanceX", "unrelated"),
            ("Team_2026", "underscore"),
            ("Team_2026/Private", "nested"),
            ("TeamX2026", "not an underscore"),
        ]
        for folder, title in names:
            status, created = self.req(
                "/api/documents", "POST", {"title": title, "body": "text", "folder": folder}
            )
            self.assertEqual(status, 201, created)

        for encoded, expected in (
            ("Finance%25", {"literal", "child"}),
            ("Team_2026", {"underscore", "nested"}),
            ("FinanceX", {"unrelated"}),
            ("TeamX2026", {"not an underscore"}),
        ):
            with self.subTest(folder=encoded):
                code, result = self.req("/api/documents?folder=" + encoded)
                self.assertEqual(code, 200)
                self.assertEqual(result["total"], len(expected))
                self.assertEqual(
                    {doc["title"] for doc in result["documents"]}, expected
                )

    def test_version_history_conflict_and_restore_revision(self):
        d=self.req("/api/documents","POST",{"title":"First","body":"a"})[1]
        path="/api/documents/"+d["id"]
        self.assertEqual(self.req(path,"PATCH",{"version":5,"body":"bad"})[0],409)
        self.assertEqual(self.req(path,"PATCH",{"version":1,"body":"b"})[1]["version"],2)
        self.assertEqual(self.req(path,"PATCH",{"version":1,"body":"overwrite"})[0],409)
        self.assertEqual(self.req(path)[1]["body"],"b")
        self.assertEqual(len(self.req(path+"/revisions")[1]["revisions"]),2)
        self.assertEqual(self.req(path+"/revisions/1")[1]["body"],"a")
        self.assertEqual(self.req(path+"/revisions/1","POST",{"version":2})[1]["version"],3)
        self.assertEqual(self.req(path)[1]["body"],"a")

    def test_share_revocation_and_trash(self):
        d=self.req("/api/documents","POST",{"title":"Share","body":"Safe"})[1]
        path="/api/documents/"+d["id"]
        code, link=self.req(path+"/share","POST",{"hours":1})
        self.assertEqual(code,201)
        share="/api/public/"+link["token"]
        self.assertEqual(self.req(share,key=False)[1]["body"],"Safe")
        self.assertEqual(self.req("/api/shares/"+link["token"],"DELETE")[0],200)
        self.assertEqual(self.req(share,key=False)[0],404)
        link=self.req(path+"/share","POST",{"hours":1})[1]
        self.assertEqual(self.req(path+"/trash","POST")[0],200)
        self.assertEqual(self.req(path)[0],404)
        self.assertEqual(len(self.req("/api/documents?trash=1")[1]["documents"]),1)
        self.assertEqual(self.req("/api/public/"+link["token"],key=False)[0],404)
        self.assertEqual(self.req(path+"/restore","POST")[0],200)
        self.assertEqual(self.req("/api/public/"+link["token"],key=False)[0],404,
                         "Trash must permanently revoke existing capability links")

    def test_cli_and_mcp(self):
        previous=os.environ.copy()
        self.addCleanup(lambda: (os.environ.clear(),os.environ.update(previous)))
        os.environ["GOREEDOCS_URL"]=self.url
        os.environ["GOREEDOCS_TOKEN"]=self.secret
        created=mcp.run_tool("documents_create",{"title":"AI note","body":"Hello","folder":"Notes"})
        self.assertEqual(mcp.run_tool("documents_read",{"id":created["id"]})["body"],"Hello")
        self.assertEqual(cli.call("/api/documents?q=AI")["documents"][0]["id"],created["id"])
        result=mcp.dispatch({"jsonrpc":"2.0","method":"tools/call","params":{"name":"documents_update","arguments":{"id":created["id"],"version":1,"body":"Updated"}}})
        self.assertFalse(result["result"]["isError"])
        self.assertEqual(self.req("/api/documents/"+created["id"])[1]["body"],"Updated")
        self.assertIn("tools",mcp.dispatch({"jsonrpc":"2.0","method":"tools/list"})["result"])
        self.assertIn("capabilities",mcp.dispatch({"jsonrpc":"2.0","method":"initialize","params":{"protocolVersion":"2025-11-25"}})["result"])

    def test_static_security_headers(self):
        req=Request(self.url+"/")
        with urlopen(req) as r:
            self.assertEqual(r.status,200)
            self.assertIn("default-src 'none'",r.headers["Content-Security-Policy"])
            self.assertEqual(r.headers["X-Content-Type-Options"],"nosniff")


if __name__=="__main__":
    unittest.main()
