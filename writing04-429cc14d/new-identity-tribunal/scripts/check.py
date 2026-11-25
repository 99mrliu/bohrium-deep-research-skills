import json,sys,re,unicodedata
x=json.load(open(sys.argv[1],encoding='utf-8'))
def norm(s): return ''.join(c for c in unicodedata.normalize('NFKC',str(s)).casefold() if c.isalnum())
def doi(s): return re.sub(r'^(https?://(dx\.)?doi\.org/|doi:\s*)','',str(s).strip().lower())
out=[]
for i,a in enumerate(x):
 for b in x[i+1:]:
  da,db=doi(a.get('doi','')),doi(b.get('doi','')); ta,tb=norm(a.get('title','')),norm(b.get('title',''))
  if da and db and da==db: decision='same_identifier_review_metadata'; reason='same DOI'
  elif ta and ta==tb and a.get('year')==b.get('year') and a.get('year'): decision='candidate_review'; reason='same normalized title and year'
  else: continue
  out.append({'ids':[a['id'],b['id']],'decision':decision,'reason':reason,'auto_merge':False})
json.dump(out,open(sys.argv[2],'w',encoding='utf-8'),ensure_ascii=False,indent=2)
