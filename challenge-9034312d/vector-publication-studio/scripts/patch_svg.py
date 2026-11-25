#!/usr/bin/env python3
"""Patch addressed SVG IDs as UTF-8 byte spans; never rebuild/reserialize the document.

Operations: set_text (simple text elements only), set_attr, remove_attr.
All bytes outside the exact addressed text/attribute/start-tag span survive unchanged.
"""
from __future__ import annotations
import argparse, hashlib, json, re, sys
from pathlib import Path
from xml.parsers import expat
from xml.sax.saxutils import escape, quoteattr

class PatchError(Exception): pass

def tag_end(data, start):
    quote=None; i=start
    while i<len(data):
        c=data[i]
        if quote:
            if c==quote: quote=None
        elif c in (34,39): quote=c
        elif c==62: return i+1
        i+=1
    raise PatchError(f"Unclosed XML tag at byte {start}")

def locate(data, target_id):
    found=[]; stack=[]
    parser=expat.ParserCreate(namespace_separator=None)
    def start(name,attrs):
        rec={"name":name,"start":parser.CurrentByteIndex,"open_end":None,"children":0}
        rec["open_end"]=tag_end(data,rec["start"])
        if stack: stack[-1]["children"]+=1
        stack.append(rec)
        if attrs.get("id")==target_id: found.append(rec)
    def end(name):
        if not stack: raise PatchError("Malformed element stack")
        rec=stack.pop(); rec["end_start"]=parser.CurrentByteIndex
        raw=data[rec["start"]:rec["open_end"]]
        if raw.rstrip().endswith(b"/>"):
            rec["empty"]=True; rec["end_start"]=rec["open_end"]; rec["close_end"]=rec["open_end"]
        else:
            rec["empty"]=False
            if not data[rec["end_start"]:].startswith(b"</"): raise PatchError(f"Cannot locate closing tag for {target_id}")
            rec["close_end"]=tag_end(data,rec["end_start"])
    parser.StartElementHandler=start; parser.EndElementHandler=end
    try: parser.Parse(data,True)
    except expat.ExpatError as e: raise PatchError(f"Malformed XML: {e}")
    if len(found)!=1: raise PatchError(f"Addressed id {target_id!r} occurs {len(found)} times; exactly one is required")
    return found[0]

def apply_one(data, edit):
    if not isinstance(edit,dict) or not edit.get("id"): raise PatchError("Every edit requires an id")
    op=edit.get("op"); rec=locate(data,edit["id"])
    if op=="set_text":
        if "text" not in edit: raise PatchError("set_text requires text")
        if rec["empty"] or rec["children"]: raise PatchError(f"set_text for {edit['id']!r} requires a nonempty element with no child elements; target an individual text/tspan node")
        inner=data[rec["open_end"]:rec["end_start"]]
        if b"<" in inner: raise PatchError("set_text refuses mixed content")
        replacement=escape(str(edit["text"]),{">":"&gt;"}).encode("utf-8")
        a,b=rec["open_end"],rec["end_start"]; kind="text-content"
    elif op in ("set_attr","remove_attr"):
        name=edit.get("name")
        if not name or name=="id": raise PatchError("Attribute name is required; id cannot be edited")
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.:-]*",name): raise PatchError("Unsafe/invalid attribute name")
        a0,b0=rec["start"],rec["open_end"]; raw=data[a0:b0]
        # Match an XML attribute in the opening tag, never element text. UTF-8 names are intentionally rejected.
        pattern=re.compile(rb"(?<![^\s<])"+re.escape(name.encode("ascii"))+rb"\s*=\s*([\"'])(.*?)\1",re.DOTALL)
        match=pattern.search(raw)
        if op=="remove_attr":
            if not match: raise PatchError(f"Attribute {name!r} not found on {edit['id']!r}")
            a,b=a0+match.start(),a0+match.end(); replacement=b""; kind="attribute-removal"
        else:
            if "value" not in edit: raise PatchError("set_attr requires value")
            quoted=quoteattr(str(edit["value"])).encode("utf-8")
            if match:
                # Replace only the quoted value, retaining original attribute-name whitespace.
                a,b=a0+match.start(2)-1,a0+match.end(2)+1; replacement=quoted; kind="attribute-value"
            else:
                close=raw.rfind(b"/>")
                if close<0: close=raw.rfind(b">")
                a=b=a0+close; replacement=b" "+name.encode("ascii")+b"="+quoted; kind="attribute-insertion"
    else: raise PatchError(f"Unsupported operation {op!r}; use set_text, set_attr or remove_attr")
    return data[:a]+replacement+data[b:], {"op":op,"id":edit["id"],"addressed":kind,"byte_span":[a,b],"replacement_bytes":len(replacement)}

def patch(data, edits):
    if not isinstance(edits,list) or not edits: raise PatchError("Edits must be a nonempty JSON list")
    original=data; records=[]
    for index,edit in enumerate(edits):
        data,record=apply_one(data,edit); record["edit_index"]=index; records.append(record)
    # Reparse final bytes, proving well-formedness without emitting a serializer's formatting.
    p=expat.ParserCreate(); p.Parse(data,True)
    return data,{"engine":"expat-byte-span","document_reserialized":False,"edits":records,"before_sha256":hashlib.sha256(original).hexdigest(),"after_sha256":hashlib.sha256(data).hexdigest(),"preservation_rule":"Only byte spans reported above were replaced; markup, comments, whitespace, namespace declarations and all non-addressed nodes retain their original bytes."}

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__); p.add_argument("--input",required=True); p.add_argument("--output",required=True); p.add_argument("--edits",required=True); p.add_argument("--report",required=True)
    a=p.parse_args(argv)
    try:
        source=Path(a.input).read_bytes(); edits=json.loads(Path(a.edits).read_text(encoding="utf-8"))
        result,report=patch(source,edits)
        output=Path(a.output); output.parent.mkdir(parents=True,exist_ok=True)
        output.write_bytes(result); Path(a.report).write_text(json.dumps(report,ensure_ascii=False,indent=2,sort_keys=True)+"\n",encoding="utf-8")
        print(json.dumps({"status":"ok","output":str(output),"edits":len(report["edits"]),"document_reserialized":False}))
        return 0
    except (OSError,PatchError,json.JSONDecodeError,expat.ExpatError) as e:
        print(f"ERROR: {e}",file=sys.stderr); return 2
if __name__=="__main__": raise SystemExit(main())
