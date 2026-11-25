#!/usr/bin/env python3
"""Generic quality-gated /input runner with atomic checkpoints and standard result.json."""
import argparse, hashlib, json, subprocess, sys
from pathlib import Path
from runner import atomic_json, atomic_bytes, sha256, audit_svg, audit_png, audit_pdf

FIELDS=["case_id","status","editable_source","export_artifact","content_map","compliance_checks","exceptions"]
STAGES=["observed","specified","rendered","exported","audited","delivered"]
def load(p): return json.loads(Path(p).read_text(encoding="utf-8"))
def fields(case):
 c=case.get('output_contract',FIELDS); return list(c) if isinstance(c,list) else list(c.keys())
def make_result(case,status,checks,exceptions,cmap,sources,uncertainty,changes):
 vals={"case_id":case.get('case_id'),"status":status,"editable_source":["figure.svg"] if (checks or status!='partial') else [],"export_artifact":["figure.png","figure.pdf"] if any(c.get('name')=='exports' and c.get('status')=='pass' for c in checks) else [],"content_map":cmap,"compliance_checks":checks,"exceptions":exceptions,"sources":sources,"uncertainty":uncertainty,"change_records":changes}
 for k in fields(case): vals.setdefault(k,None)
 return vals
def main():
 ap=argparse.ArgumentParser(); ap.add_argument('--input',default='/input'); ap.add_argument('--work',default='/app/work'); ap.add_argument('--output',default='/app/output'); ap.add_argument('--spec'); ap.add_argument('--visual-review'); ap.add_argument('--resume',action='store_true'); a=ap.parse_args()
 inp,work,out=Path(a.input),Path(a.work),Path(a.output); work.mkdir(parents=True,exist_ok=True); out.mkdir(parents=True,exist_ok=True)
 case=load(inp/'case.json'); checks=[]; exceptions=[]; sources=[]; uncertainty=[]; changes=[]; cmap={}
 atomic_json(out/'result.json',make_result(case,'partial',checks,[{"type":"in_progress"}],cmap,sources,uncertainty,changes))
 manifest={"case_id":case.get('case_id'),"current_stage":"observed","completed_stages":[],"checkpoints":{}}
 def checkpoint(stage,evidence):
  manifest['current_stage']=stage
  if stage not in manifest['completed_stages']: manifest['completed_stages'].append(stage)
  manifest['checkpoints'][stage]=evidence; atomic_json(work/'run_manifest.json',manifest); atomic_json(out/'run_manifest.json',manifest)
 try:
  task=inp/'task.md'
  if not task.is_file(): raise ValueError('missing task.md')
  specp=Path(a.spec) if a.spec else work/'specification.json'
  if not specp.is_file(): specp=inp/'specification.json'
  spec=load(specp)
  sources=[{"role":r,"path":str(p),"sha256":sha256(p)} for r,p in [('case',inp/'case.json'),('task',task),('specification',specp)]]
  checkpoint('observed',{"input_hashes":sources})
  checkpoint('specified',{"specification_sha256":sha256(specp),"entities":len(spec['entities']),"edges":len(spec['edges'])})
  staged=work/'figure.svg'
  if staged.exists(): staged.unlink()
  subprocess.run([sys.executable,str(Path(__file__).with_name('simple_renderer.py')),'--spec',str(specp),'--output',str(staged)],check=True,capture_output=True,text=True)
  atomic_bytes(out/'figure.svg',staged.read_bytes()); checkpoint('rendered',{"svg_sha256":sha256(staged)})
  import pymupdf
  doc=pymupdf.open(stream=staged.read_bytes(),filetype='svg'); pdf=doc.convert_to_pdf(); atomic_bytes(out/'figure.pdf',pdf)
  pd=pymupdf.open(stream=pdf,filetype='pdf'); pix=pd[0].get_pixmap(matrix=pymupdf.Matrix(2,2),alpha=False); atomic_bytes(out/'figure.png',pix.tobytes('png'))
  checks=[{"name":"exports","status":"pass","detail":{"png":[pix.width,pix.height],"pdf_pages":len(pd)}}]; checkpoint('exported',checks[-1]['detail'])
  svg_audit=audit_svg(out/'figure.svg',spec); png_audit=audit_png(out/'figure.png'); pdf_audit=audit_pdf(out/'figure.pdf',spec)
  checks += [{"name":"svg_readback","status":"pass","detail":{k:v for k,v in svg_audit.items() if k!='text'}},{"name":"png_pixels","status":"pass","detail":png_audit},{"name":"pdf_text","status":"pass","detail":pdf_audit}]
  cmap={**{f"entity:{e['id']}":e.get('source') for e in spec['entities']},**{f"edge:{e['id']}":e.get('evidence','Agent specification; verify against source') for e in spec['edges']}}
  checkpoint('audited',{"checks":checks})
  review=load(a.visual_review) if a.visual_review else None
  if review:
   if review.get('png_sha256')!=sha256(out/'figure.png') or review.get('pdf_sha256')!=sha256(out/'figure.pdf') or not review.get('observations'): raise ValueError('visual review must bind current PNG/PDF hashes and concrete observations')
   checkpoint('delivered',{"visual_review":review})
  else:
   exceptions.append({"type":"visual_review_pending","impact":"All machine gates passed; native PNG/PDF inspection is still required."}); uncertainty.append('Native visual/scientific confirmation pending')
  atomic_json(out/'sources.json',sources); atomic_json(out/'content_map.json',cmap); atomic_json(out/'audit.json',checks)
  atomic_json(out/'result.json',make_result(case,'success' if not exceptions else 'partial',checks,exceptions,cmap,sources,uncertainty,changes))
  print(json.dumps({'case_id':case.get('case_id'),'status':'success' if not exceptions else 'partial','stage':manifest['current_stage']})); return 0
 except Exception as e:
  exceptions.append({"type":"quality_gate_failed","detail":str(e),"stage":manifest['current_stage']})
  atomic_json(work/'run_manifest.json',manifest); atomic_json(out/'run_manifest.json',manifest)
  atomic_json(out/'result.json',make_result(case,'failed',checks,exceptions,cmap,sources,uncertainty,changes)); print('ERROR:',e,file=sys.stderr); return 3
if __name__=='__main__': sys.exit(main())
