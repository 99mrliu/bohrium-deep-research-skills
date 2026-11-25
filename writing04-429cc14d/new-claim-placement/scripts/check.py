import json,sys
x=json.load(open(sys.argv[1],encoding='utf-8')); out=[]
for c in x:
 evidence=c.get('evidence',[]); missing=[e.get('source_id') for e in evidence if not e.get('locator') or not e.get('quote')]
 out.append({'claim_id':c['id'],'claim':c['claim'],'proposed_citations':[e.get('source_id') for e in evidence], 'state':'needs_evidence' if not evidence or missing else 'semantic_review_required','incomplete_anchors':missing,'instruction':'Place only after checking that the quoted source supports this specific claim; keep source locator.'})
json.dump(out,open(sys.argv[2],'w',encoding='utf-8'),ensure_ascii=False,indent=2)
