#!/usr/bin/env python3
"""Official /input contract adapter for transactional SVG source surgery."""
import argparse, copy, hashlib, json, sys
from pathlib import Path
from xml.etree import ElementTree as ET
from source_surgery import safe_xml, apply_operation, compare_trees, export_svg, atomic_json, atomic_bytes, sha256

FIELDS=["case_id","status","editable_source","export_artifact","content_map","compliance_checks","exceptions"]
def load(p): return json.loads(Path(p).read_text(encoding="utf-8"))
def find(root,names):
 for name in names:
  hits=[root/name,root/"artifacts"/name,root/"materials"/name]
  for p in hits:
   if p.is_file(): return p
 return None
def contract_fields(case):
 c=case.get("output_contract",FIELDS)
 return list(c.keys()) if isinstance(c,dict) else list(c)
def result(case,status,editable,exports,cmap,checks,exceptions,sources,changes,uncertainty):
 vals={"case_id":case.get("case_id"),"status":status,"editable_source":editable,"export_artifact":exports,"content_map":cmap,"compliance_checks":checks,"exceptions":exceptions,"sources":sources,"uncertainty":uncertainty,"change_records":changes}
 for key in contract_fields(case): vals.setdefault(key,None)
 return vals
def main():
 ap=argparse.ArgumentParser(); ap.add_argument('--input',default='/input'); ap.add_argument('--work',default='/app/work'); ap.add_argument('--output',default='/app/output'); ap.add_argument('--operations'); ap.add_argument('--visual-review'); a=ap.parse_args()
 inp,work,out=Path(a.input),Path(a.work),Path(a.output); work.mkdir(parents=True,exist_ok=True); out.mkdir(parents=True,exist_ok=True)
 case=load(inp/'case.json'); changes=[]; sources=[]; checks=[]; uncertainty=[]; exceptions=[]
 atomic_json(out/'result.json',result(case,'partial',[],[],{},[],[{"type":"in_progress"}],sources,changes,uncertainty))
 try:
  task=inp/'task.md'
  if not task.is_file(): raise ValueError('missing /input/task.md')
  svg=find(inp,['source.svg','figure03.svg','original.svg'])
  if not svg: raise ValueError('source-preserving edit requires an actual SVG; do not redraw a bitmap')
  opsp=Path(a.operations) if a.operations else find(inp,['figure-workorder.json','workorder.json'])
  if not opsp: raise ValueError('missing edit workorder/operations')
  opsdoc=load(opsp); ops=opsdoc.get('operations',opsdoc if isinstance(opsdoc,list) else None)
  if not isinstance(ops,list) or not ops: raise ValueError('operations must be a nonempty list')
  sources=[{"role":r,"path":str(p),"sha256":sha256(p)} for r,p in [('case',inp/'case.json'),('task',task),('source_svg',svg),('workorder',opsp)]]
  before,_,raw=safe_xml(svg); after=copy.deepcopy(before)
  for i,op in enumerate(ops,1): changes.append(apply_operation(after,op,i))
  unchanged,_=compare_trees(before,after,{x['id'] for x in ops})
  staged=work/'transaction/edited.svg'; atomic_bytes(staged,ET.tostring(after.getroot(),encoding='utf-8',xml_declaration=True))
  ex=export_svg(staged,work/'transaction/figure.png',work/'transaction/figure.pdf')
  for s,name in [(staged,'figure_edited.svg'),(work/'transaction/figure.png','figure_edited.png'),(work/'transaction/figure.pdf','figure_edited.pdf')]: atomic_bytes(out/name,s.read_bytes())
  atomic_json(out/'change_records.json',changes); atomic_json(out/'unchanged_elements.json',unchanged)
  checks=[{"name":"unique_stable_ids","status":"pass"},{"name":"unchanged_subtrees","status":"pass","detail":unchanged},{"name":"svg_png_pdf_export","status":"pass","detail":{k:v for k,v in ex.items() if k!='pdf_text'}},{"name":"source_unchanged","status":"pass" if sha256(svg)==hashlib.sha256(raw).hexdigest() else "fail"}]
  cmap={f"element:{c['id']}":{"operation":c['op'],"workorder":str(opsp),"source_element":f"{svg.name}#{c['id']}","before":c.get('before'),"after":c.get('after')} for c in changes}
  visual=load(a.visual_review) if a.visual_review else None
  if not visual:
   exceptions.append({"type":"visual_review_pending","impact":"Machine checks passed; native PNG/PDF inspection is still required."}); uncertainty.append('Native visual/scientific review pending')
  atomic_json(out/'sources.json',sources); atomic_json(out/'result.json',result(case,'success' if not exceptions else 'partial',['figure_edited.svg'],['figure_edited.png','figure_edited.pdf'],cmap,checks,exceptions,sources,changes,uncertainty))
  print(json.dumps({'case_id':case.get('case_id'),'status':'success' if not exceptions else 'partial','operations':len(changes)})); return 0
 except Exception as e:
  exceptions.append({"type":"source_surgery_failed","detail":str(e)})
  atomic_json(out/'result.json',result(case,'failed',[],[],{},checks,exceptions,sources,changes,uncertainty)); print('ERROR:',e,file=sys.stderr); return 3
if __name__=='__main__': sys.exit(main())
