"""Development stdio MCP bridge for GoreeCloud Documents REST.

No model inference is performed here. The MCP host controls confirmations and permissions.
Supports legacy initialize and stateless server/discover openings for local clients.
"""
import json
import sys

from .cli import call

PROTOCOL_MODERN = "2026-07-28"
PROTOCOL_LEGACY = "2025-11-25"


def schema(props, required=()):
    return {"type": "object", "properties": props, "required": list(required), "additionalProperties": False}


STR = {"type": "string"}
INT = {"type": "integer", "minimum": 1}
TOOLS = [
    {"name":"documents_list","title":"Find documents","description":"Search your private Markdown documents by title, folder or contents. Read-only.",
     "inputSchema":schema({"query":STR,"trash":{"type":"boolean"}}),"annotations":{"readOnlyHint":True}},
    {"name":"documents_read","title":"Read document","description":"Read a complete Markdown document by ID. Read-only.",
     "inputSchema":schema({"id":STR}),"annotations":{"readOnlyHint":True}},
    {"name":"documents_create","title":"Create document","description":"Create a Markdown document in the private GoreeCloud library.",
     "inputSchema":schema({"title":STR,"body":STR,"folder":STR},("title","body")),"annotations":{"readOnlyHint":False}},
    {"name":"documents_update","title":"Edit document","description":"Edit using the current version number to avoid overwriting concurrent edits; read document first.",
     "inputSchema":schema({"id":STR,"version":INT,"title":STR,"body":STR,"folder":STR},("id","version")),"annotations":{"readOnlyHint":False}},
    {"name":"documents_history","title":"Document revisions","description":"List a document's revision history.",
     "inputSchema":schema({"id":STR},("id",)),"annotations":{"readOnlyHint":True}},
    {"name":"documents_read_revision","title":"Read prior revision","description":"Get a specific immutable revision of a document.",
     "inputSchema":schema({"id":STR,"revision":INT},("id","revision")),"annotations":{"readOnlyHint":True}},
    {"name":"documents_trash","title":"Move document to trash","description":"Soft-delete a document. This interrupts its share links. Should require user consent.",
     "inputSchema":schema({"id":STR},("id",)),"annotations":{"readOnlyHint":False,"destructiveHint":True}},
    {"name":"documents_restore","title":"Restore trashed document","description":"Restore a soft-deleted document.",
     "inputSchema":schema({"id":STR},("id",)),"annotations":{"readOnlyHint":False}},
]
LOOKUP = {t["name"]:t for t in TOOLS}


def run_tool(name, p):
    if name not in LOOKUP:
        raise KeyError("Unknown tool")
    spec=LOOKUP[name]["inputSchema"]
    if not isinstance(p, dict) or not set(p).issubset(spec["properties"]) or not set(spec["required"]).issubset(p):
        raise ValueError("Missing or unexpected tool arguments")
    for k,v in p.items():
        expected=spec["properties"][k]["type"]
        if expected=="string" and not isinstance(v,str):
            raise ValueError(k+" must be a string")
        if expected=="integer" and (type(v) is not int or v<1):
            raise ValueError(k+" must be a positive integer")
        if expected=="boolean" and type(v) is not bool:
            raise ValueError(k+" must be a boolean")
    from urllib.parse import quote, urlencode
    doc = quote(p.get("id",""), safe="")
    if name=="documents_list":
        return call("/api/documents?"+urlencode({"q":p.get("query",""),"trash":"1" if p.get("trash",False) else "0"}))
    if name=="documents_read":
        return call("/api/documents/"+doc)
    if name=="documents_create":
        return call("/api/documents","POST",{"title":p["title"],"body":p["body"],"folder":p.get("folder","")})
    if name=="documents_update":
        payload={k:v for k,v in p.items() if k!="id"}
        return call("/api/documents/"+doc,"PATCH",payload)
    if name=="documents_history":
        return call("/api/documents/"+doc+"/revisions")
    if name=="documents_read_revision":
        return call("/api/documents/"+doc+"/revisions/"+str(p["revision"]))
    if name=="documents_trash":
        return call("/api/documents/"+doc+"/trash","POST")
    if name=="documents_restore":
        return call("/api/documents/"+doc+"/restore","POST")


def dispatch(request):
    if not isinstance(request,dict) or request.get("jsonrpc")!="2.0" or not isinstance(request.get("method"),str):
        return {"error":{"code":-32600,"message":"Invalid request"}}
    method=request["method"]
    if method=="initialize":
        version=request.get("params",{}).get("protocolVersion",PROTOCOL_LEGACY)
        if version not in (PROTOCOL_LEGACY,"2025-06-18","2025-03-26"):
            version=PROTOCOL_LEGACY
        return {"result":{"protocolVersion":version,"capabilities":{"tools":{"listChanged":False}},"serverInfo":{"name":"goreecloud-documents","version":"0.1.0"}}}
    if method=="server/discover":
        return {"result":{"resultType":"complete","supportedVersions":[PROTOCOL_MODERN],"capabilities":{"tools":{"listChanged":False}},"ttlMs":60000,"cacheScope":"private","_meta":{"io.modelcontextprotocol/serverInfo":{"name":"goreecloud-documents","version":"0.1.0"}}}}
    if method in ("notifications/initialized","notifications/cancelled"):
        return None
    if method=="ping":
        return {"result":{}}
    if method=="tools/list":
        return {"result":{"tools":TOOLS}}
    if method=="tools/call":
        params=request.get("params",{})
        name=params.get("name") if isinstance(params,dict) else None
        if name not in LOOKUP:
            return {"error":{"code":-32602,"message":"Unknown tool"}}
        try:
            result=run_tool(name,params.get("arguments",{}))
            return {"result":{"content":[{"type":"text","text":json.dumps(result,ensure_ascii=False)}],"isError":False}}
        except (ValueError,KeyError,OSError) as e:
            return {"result":{"content":[{"type":"text","text":str(e)}],"isError":True}}
    return {"error":{"code":-32601,"message":"Method not found"}}


def main():
    for raw in sys.stdin.buffer:
        if len(raw)>2*1024*1024:
            print(json.dumps({"jsonrpc":"2.0","id":None,"error":{"code":-32600,"message":"Message too large"}}),flush=True)
            continue
        try:
            req=json.loads(raw)
            response=dispatch(req)
            if response is not None and "id" in req:
                meta=req.get("params",{}).get("_meta",{}) if isinstance(req.get("params",{}),dict) else {}
                modern=(req.get("method")=="server/discover" or meta.get("io.modelcontextprotocol/protocolVersion")==PROTOCOL_MODERN)
                if modern and "result" in response:
                    response["result"].setdefault("resultType","complete")
                    response["result"].setdefault("_meta",{})["io.modelcontextprotocol/serverInfo"]={"name":"goreecloud-documents","version":"0.1.0"}
                print(json.dumps({"jsonrpc":"2.0","id":req["id"],**response},ensure_ascii=False),flush=True)
        except (ValueError,TypeError,AttributeError):
            print(json.dumps({"jsonrpc":"2.0","id":None,"error":{"code":-32700,"message":"Invalid JSON"}}),flush=True)


if __name__=="__main__":
    main()
