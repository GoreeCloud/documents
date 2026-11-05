"""GoreeCloud Documents CLI. Calls the same versioned REST API as the browser."""
import argparse
import json
import os
from pathlib import Path
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen


def call(path, method="GET", payload=None):
    endpoint = os.environ.get("GOREEDOCS_URL", "http://127.0.0.1:8735").rstrip("/")
    if not (endpoint.startswith("http://127.0.0.1:") or
            endpoint.startswith("http://localhost:") or
            endpoint.startswith("https://")):
        raise ValueError("Only loopback HTTP or HTTPS document endpoints are allowed")
    token = os.environ.get("GOREEDOCS_TOKEN", "")
    if not token:
        raise ValueError("Set GOREEDOCS_TOKEN before using the CLI")
    headers = {"Authorization": "Bearer " + token, "Accept": "application/json"}
    data = None
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = Request(endpoint + path, method=method, data=data, headers=headers)
    try:
        with urlopen(request, timeout=20) as response:
            return json.load(response)
    except HTTPError as e:
        try:
            detail = json.loads(e.read()).get("error", str(e))
        except (ValueError, UnicodeDecodeError):
            detail = "HTTP " + str(e.code)
        raise ValueError(detail) from None
    except URLError as e:
        raise ValueError("Cannot reach document server: " + str(e.reason)) from None


def execute(args):
    doc = quote(getattr(args, "id", ""), safe="")
    if args.action == "list":
        return call("/api/documents?" + urlencode({"q": args.search, "trash": "1" if args.trash else "0"}))
    if args.action == "get":
        return call("/api/documents/" + doc + ("?trash=1" if args.trash else ""))
    if args.action == "create":
        body = sys.stdin.read() if args.file == "-" else Path(args.file).read_text(encoding="utf-8")
        return call("/api/documents", "POST", {"title":args.title,"folder":args.folder,"body":body,"format":args.format})
    if args.action == "update":
        payload = {"version":args.version}
        if args.file is not None:
            payload["body"] = sys.stdin.read() if args.file == "-" else Path(args.file).read_text(encoding="utf-8")
        if args.title is not None:
            payload["title"] = args.title
        if args.folder is not None:
            payload["folder"] = args.folder
        if args.format is not None:
            payload["format"] = args.format
        if args.favorite is not None:
            payload["favorite"] = args.favorite == "yes"
        return call("/api/documents/" + doc, "PATCH", payload)
    if args.action == "import":
        source = Path(args.file)
        return call("/api/documents/import", "POST", {"filename":source.name,"content":source.read_text(encoding="utf-8")})
    if args.action == "export":
        result=call("/api/documents/" + doc + "/export?" + urlencode({"format":args.format}))
        target=Path(args.file) if args.file else Path(result["filename"])
        with target.open("x", encoding="utf-8") as output:
            output.write(result["content"])
        return {"saved":str(target),"format":args.format,"filename":result["filename"]}
    if args.action == "trash":
        return call("/api/documents/" + doc + "/trash", "POST")
    if args.action == "restore":
        return call("/api/documents/" + doc + "/restore", "POST")
    if args.action == "history":
        return call("/api/documents/" + doc + "/revisions")
    if args.action == "revision":
        return call("/api/documents/" + doc + "/revisions/" + str(args.number))
    if args.action == "revert":
        return call("/api/documents/" + doc + "/revisions/" + str(args.number), "POST", {"version":args.version})
    if args.action == "share":
        return call("/api/documents/" + doc + "/share", "POST", {"hours":args.hours})
    if args.action == "revoke":
        return call("/api/shares/" + quote(args.token, safe=""), "DELETE")
    raise ValueError("Unknown command")


def parser():
    p = argparse.ArgumentParser(prog="goreedocs", description="GoreeCloud Documents CLI")
    sub = p.add_subparsers(dest="action", required=True)
    listing = sub.add_parser("list"); listing.add_argument("--search", default=""); listing.add_argument("--trash", action="store_true")
    get = sub.add_parser("get"); get.add_argument("id"); get.add_argument("--trash", action="store_true")
    create = sub.add_parser("create"); create.add_argument("--title", required=True); create.add_argument("--folder", default=""); create.add_argument("--format", choices=["gcdoc","md"],default="gcdoc"); create.add_argument("--file", default="-", help="UTF-8 Markdown source path, or - for stdin")
    update = sub.add_parser("update"); update.add_argument("id"); update.add_argument("--version", required=True, type=int); update.add_argument("--title"); update.add_argument("--folder"); update.add_argument("--file"); update.add_argument("--format", choices=["gcdoc","md"]); update.add_argument("--favorite", choices=["yes","no"])
    imp = sub.add_parser("import"); imp.add_argument("file", help="Source .gcdoc or .md file")
    exp = sub.add_parser("export"); exp.add_argument("id"); exp.add_argument("--format", choices=["gcdoc","md"],default="gcdoc"); exp.add_argument("--file", help="New destination file (must not exist)")
    for name in ("trash", "restore", "history", "share"):
        sub.add_parser(name).add_argument("id")
    sub.choices["share"].add_argument("--hours", type=int, default=24)
    for name in ("revision", "revert"):
        cmd = sub.add_parser(name); cmd.add_argument("id"); cmd.add_argument("number", type=int)
        if name == "revert":
            cmd.add_argument("--version", type=int, required=True)
    sub.add_parser("revoke").add_argument("token")
    return p


def main():
    try:
        result = execute(parser().parse_args())
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except (ValueError, OSError) as e:
        print("goreedocs: " + str(e), file=sys.stderr)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
