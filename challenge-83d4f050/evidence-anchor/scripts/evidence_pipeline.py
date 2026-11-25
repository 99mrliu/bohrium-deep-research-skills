#!/usr/bin/env python3
"""Evidence-anchored biological figure builder; no scientific extraction is automated."""
import argparse, hashlib, html, json, os, re, sys, tempfile, math
from pathlib import Path
from xml.etree import ElementTree as ET

KIND = {"activates":"activation", "inhibits":"inhibition", "binds":"binding", "phosphorylates":"phosphorylation", "ubiquitinates":"ubiquitination", "transports":"transport", "recruits":"recruitment", "uncertain":"uncertain"}

def read_json(path):
    with open(path, encoding="utf-8") as f: return json.load(f)

def dump_json(path, obj):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=path.name+".", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f: json.dump(obj, f, ensure_ascii=False, indent=2); f.write("\n")
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp): os.unlink(tmp)

def sha256(path):
    h=hashlib.sha256()
    with open(path,"rb") as f:
        for b in iter(lambda:f.read(65536),b""): h.update(b)
    return h.hexdigest()

def norm(s): return re.sub(r"\s+", " ", s or "").strip()

def validate_claims(c, root):
    checks=[]; exceptions=[]
    def check(name, ok, detail): checks.append({"name":name,"status":"pass" if ok else "fail","detail":detail})
    ev=c.get("evidence",[]); ids=[e.get("id") for e in ev]
    check("evidence_ids_unique",len(ids)==len(set(ids)),f"{len(ids)} evidence records")
    emap={e.get("id"):e for e in ev}; source_manifest=[]
    for e in ev:
        p=root/e.get("file",""); quote=e.get("quote","")
        item={"evidence_id":e.get("id"),"file":e.get("file"),"locator":e.get("locator"),"quote":quote}
        if not p.is_file():
            item["status"]="unavailable"; exceptions.append({"type":"missing_source","evidence_id":e.get("id"),"file":e.get("file")})
        else:
            item["sha256"]=sha256(p)
            if p.suffix.lower() in {".txt",".md",".csv",".tsv",".json"}:
                found=norm(quote) in norm(p.read_text(encoding="utf-8",errors="replace"))
                item["quote_match"]=found
                if not found: exceptions.append({"type":"quote_mismatch","evidence_id":e.get("id")})
            else: item["quote_match"]="manual_pdf_page_check_required"
        source_manifest.append(item)
    used=[]
    for kind, items in (("entity",c.get("entities",[])),("edge",c.get("edges",[])),("encoding",c.get("encodings",[]))):
        for x in items:
            refs=x.get("evidence_ids",[]); used.extend(refs)
            check(f"{kind}_source:{x.get('id')}",bool(refs) and all(r in emap for r in refs),f"{x.get('id')} -> {refs or 'NO EVIDENCE'}")
            for r in refs:
                if r not in emap: exceptions.append({"type":"orphan_evidence_ref","element":x.get("id"),"evidence_id":r})
    for e in c.get("edges",[]):
        check(f"edge_semantics:{e.get('id')}",e.get("kind") in KIND,f"kind={e.get('kind')}")
    check("all_evidence_used",set(ids).issubset(set(used)),f"unused={sorted(set(ids)-set(used))}")
    return checks, exceptions, source_manifest

def esc(s): return html.escape(str(s),quote=True)

def marker_defs():
    return '''<defs><marker id="arrow" markerWidth="10" markerHeight="8" refX="9" refY="4" orient="auto"><path d="M0,0 L10,4 L0,8 z" fill="#276fbf"/></marker><marker id="open" markerWidth="10" markerHeight="8" refX="9" refY="4" orient="auto"><path d="M0,0 L10,4 L0,8" fill="white" stroke="#276fbf"/></marker></defs>'''

def render_svg(c, path):
    W=int(c.get("width",1100)); H=int(c.get("height",700)); entities=c.get("entities",[]); by={e["id"]:e for e in entities}
    out=[f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">',marker_defs(),'<rect width="100%" height="100%" fill="white"/>']
    title=c.get("title","Biological mechanism")
    if c.get("synthetic"): title="SYNTHETIC EXAMPLE — "+title
    out += [f'<g id="layer-title"><text x="36" y="42" font-family="Arial,sans-serif" font-size="24" font-weight="700">{esc(title)}</text></g>','<g id="layer-compartments">']
    for z in c.get("compartments",[]):
        out += [f'<rect id="compartment:{esc(z["id"])}" x="{z.get("x",30)}" y="{z.get("y",80)}" width="{z.get("w",W-60)}" height="{z.get("h",100)}" fill="{z.get("fill","#f6f8fa")}" stroke="#b8c2cc"/>',f'<text x="{z.get("x",30)+12}" y="{z.get("y",80)+22}" font-family="Arial" font-size="14" fill="#586575">{esc(z.get("label",z["id"]))}</text>']
    out.append('</g><g id="layer-edges">')
    for ed in c.get("edges",[]):
        a=by.get(ed.get("from"),{}); b=by.get(ed.get("to"),{}); x1,y1=a.get("x",0),a.get("y",0); x2,y2=b.get("x",0),b.get("y",0)
        kind=ed.get("kind","uncertain"); dash=' stroke-dasharray="8 5"' if kind in {"transports","uncertain"} else ''
        marker=' marker-end="url(#open)"' if kind in {"binds","transports"} else ' marker-end="url(#arrow)"'
        col="#6b7280" if kind=="uncertain" else "#276fbf"
        out.append(f'<g id="edge:{esc(ed["id"])}" data-kind="{esc(kind)}" data-evidence="{esc(",".join(ed.get("evidence_ids",[])))}"><line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{col}" stroke-width="2.5"{dash}{"" if kind=="inhibits" else marker}/>')
        if kind=="inhibits":
            length=math.hypot(x2-x1,y2-y1) or 1.0; tx=x2-70*(x2-x1)/length; ty=y2-70*(y2-y1)/length
            out.append(f'<line x1="{tx}" y1="{ty-11}" x2="{tx}" y2="{ty+11}" stroke="#b23a48" stroke-width="4"/>')
        else:
            length=math.hypot(x2-x1,y2-y1) or 1.0; ux,uy=(x2-x1)/length,(y2-y1)/length; tx,ty=x2-70*ux,y2-70*uy; bx,base_y=tx-13*ux,ty-13*uy; px,py=-6*uy,6*ux
            fill="white" if kind in {"binds","transports"} else col
            out.append(f'<polygon points="{tx},{ty} {bx+px},{base_y+py} {bx-px},{base_y-py}" fill="{fill}" stroke="{col}" stroke-width="2" data-terminal="direction"/>')
        label=ed.get("label",{"phosphorylates":"P","ubiquitinates":"Ub","uncertain":"?"}.get(kind,kind))
        out.append(f'<text x="{(x1+x2)/2}" y="{(y1+y2)/2-8}" text-anchor="middle" font-family="Arial" font-size="13" fill="{col}">{esc(label)} [{esc(",".join(ed.get("evidence_ids",[])))}]</text></g>')
    out.append('</g><g id="layer-entities">')
    for e in entities:
        x,y=e.get("x",0),e.get("y",0); fill=e.get("fill","#dceeff"); stroke=e.get("stroke","#24557a")
        out.append(f'<g id="entity:{esc(e["id"])}" data-kind="{esc(e.get("kind","other"))}" data-evidence="{esc(",".join(e.get("evidence_ids",[])))}"><rect x="{x-65}" y="{y-27}" width="130" height="54" rx="12" fill="{fill}" stroke="{stroke}" stroke-width="2"/><text x="{x}" y="{y+5}" text-anchor="middle" font-family="Arial" font-size="17" font-style="{"italic" if e.get("kind")=="gene" else "normal"}">{esc(e.get("label",e["id"]))}</text><text x="{x+68}" y="{y-17}" font-family="Arial" font-size="11" fill="#59636e">{esc(",".join(e.get("evidence_ids",[])))}</text></g>')
    out += ['</g>','<g id="layer-legend"><rect x="36" y="%d" width="1028" height="76" fill="#fff" stroke="#ccd3da"/>'%(H-95),f'<text x="52" y="{H-67}" font-family="Arial" font-size="14">arrow = directed regulation; bar = inhibition; dashed = transport/uncertain; [E#] = ledger evidence</text>',f'<text x="52" y="{H-42}" font-family="Arial" font-size="12" fill="#59636e">Scientific claims are not inferred by this script; every depicted claim must cite the current input evidence ledger.</text></g>',f'<metadata>{esc(json.dumps(c,ensure_ascii=False))}</metadata></svg>']
    Path(path).parent.mkdir(parents=True,exist_ok=True); Path(path).write_text("\n".join(out),encoding="utf-8")

def export(svg, png, pdf):
    try:
        import pymupdf
        doc=pymupdf.open(stream=Path(svg).read_bytes(),filetype="svg"); pdfbytes=doc.convert_to_pdf()
        Path(pdf).write_bytes(pdfbytes); pdoc=pymupdf.open(stream=pdfbytes,filetype="pdf"); pix=pdoc[0].get_pixmap(matrix=pymupdf.Matrix(2,2),alpha=False); pix.save(str(png))
        return {"status":"pass","renderer":"PyMuPDF","pdf_pages":len(pdoc),"pixels":[pix.width,pix.height],"bytes":{"pdf":len(pdfbytes),"png":Path(png).stat().st_size}}
    except Exception as e:
        return {"status":"fail","renderer":"PyMuPDF","error":str(e)}

def content_map(c, source_manifest):
    emap={e["evidence_id"]:e for e in source_manifest}; out={}
    for kind, items in (("entity",c.get("entities",[])),("edge",c.get("edges",[])),("encoding",c.get("encodings",[]))):
        for x in items:
            out[f"{kind}:{x['id']}"]={"label":x.get("label",x.get("kind")),"evidence":[emap.get(r,{"evidence_id":r,"status":"missing"}) for r in x.get("evidence_ids",[])]}
    return out

def result_object(case,c,sources,checks,exceptions,exports):
    status="success" if not exceptions and all(x["status"]=="pass" for x in checks) and exports["status"]=="pass" else "partial"
    fields=case.get("output_contract",["case_id","status","editable_source","export_artifact","content_map","compliance_checks","exceptions"])
    vals={"case_id":case.get("case_id"),"status":status,"editable_source":["figure.svg","claims.json"],"export_artifact":["figure.png","figure.pdf"],"content_map":content_map(c,sources),"compliance_checks":checks+[{"name":"render_export",**exports}],"exceptions":exceptions,"sources":sources,"uncertainty":[e for e in exceptions if e.get("type") in {"quote_mismatch","missing_source"}],"change_records":[],"synthetic_example":bool(c.get("synthetic"))}
    return {k:vals[k] for k in fields if k in vals} | {k:v for k,v in vals.items() if k not in fields}

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--input",required=True); ap.add_argument("--work",required=True); ap.add_argument("--output",required=True); ap.add_argument("--claims"); ap.add_argument("--case"); a=ap.parse_args()
    inp=Path(a.input); work=Path(a.work); out=Path(a.output); work.mkdir(parents=True,exist_ok=True); out.mkdir(parents=True,exist_ok=True)
    case=read_json(a.case or inp/"case.json"); c=read_json(a.claims or (work/"claims.json" if (work/"claims.json").exists() else inp/"claims.json"))
    checks,exceptions,sources=validate_claims(c,inp)
    cpath=out/"claims.json"; dump_json(cpath,c); render_svg(c,out/"figure.svg")
    exports=export(out/"figure.svg",out/"figure.png",out/"figure.pdf")
    if exports["status"]!="pass": exceptions.append({"type":"render_export","detail":exports.get("error")})
    try: ET.parse(out/"figure.svg"); checks.append({"name":"svg_xml_parse","status":"pass","detail":"SVG and element ids are editable"})
    except Exception as e: checks.append({"name":"svg_xml_parse","status":"fail","detail":str(e)}); exceptions.append({"type":"invalid_svg","detail":str(e)})
    dump_json(out/"source_manifest.json",sources); dump_json(out/"result.json",result_object(case,c,sources,checks,exceptions,exports))
    print(json.dumps({"case_id":case.get("case_id"),"output":str(out),"status":read_json(out/"result.json")["status"],"checks":len(checks),"exceptions":len(exceptions)},ensure_ascii=False))
    return 0 if read_json(out/"result.json")["status"]=="success" else 2
if __name__=="__main__": sys.exit(main())
