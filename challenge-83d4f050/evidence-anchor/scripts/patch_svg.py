#!/usr/bin/env python3
"""Conservative ID-addressed SVG edits with before/after evidence; never overwrite input."""
import argparse, hashlib, json, sys
from pathlib import Path
from xml.etree import ElementTree as ET

def h(b): return hashlib.sha256(b).hexdigest()
def main():
 p=argparse.ArgumentParser(); p.add_argument('--input',required=True); p.add_argument('--operations',required=True); p.add_argument('--output',required=True); p.add_argument('--record',required=True); a=p.parse_args()
 src=Path(a.input); dst=Path(a.output)
 if src.resolve()==dst.resolve(): raise SystemExit('refusing to overwrite original')
 raw=src.read_bytes(); root=ET.fromstring(raw); ops=json.loads(Path(a.operations).read_text(encoding='utf-8')); records=[]
 for i,op in enumerate(ops):
  target=op['id']; matches=root.findall(f".//*[@id='{target}']")+([root] if root.get('id')==target else [])
  if len(matches)!=1: raise ValueError(f'operation {i}: expected one id {target}, found {len(matches)}')
  node=matches[0]; before=ET.tostring(node,encoding='unicode')
  if op['op']=='set_text': node.text=op['value']
  elif op['op']=='set_attribute': node.set(op['name'],str(op['value']))
  elif op['op']=='remove_element':
   parent=next((q for q in root.iter() if node in list(q)),None)
   if parent is None: raise ValueError('cannot remove root')
   parent.remove(node)
  else: raise ValueError('unsupported op '+op['op'])
  records.append({'index':i,'id':target,'operation':op,'before':before,'after':ET.tostring(node,encoding='unicode') if op['op']!='remove_element' else None})
 dst.parent.mkdir(parents=True,exist_ok=True); ET.ElementTree(root).write(dst,encoding='utf-8',xml_declaration=True)
 report={'source_sha256':h(raw),'edited_sha256':h(dst.read_bytes()),'source_preserved':src.exists() and h(src.read_bytes())==h(raw),'records':records}
 Path(a.record).write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 print(json.dumps({'operations':len(records),'source_preserved':report['source_preserved'],'output':str(dst)}))
if __name__=='__main__':
 try: main()
 except Exception as e: print('ERROR:',e,file=sys.stderr); sys.exit(2)
