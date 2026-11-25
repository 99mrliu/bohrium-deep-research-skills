import json,sys,unicodedata
x=json.load(open(sys.argv[1],encoding='utf-8'))
def norm(s): return ''.join(c for c in unicodedata.normalize('NFKC',str(s)).casefold() if c.isalnum())
out=[]
for r in x['records']:
 s=r.get('source_record'); conflicts=[]
 if s:
  for k in ('title','year','doi'):
   if r.get(k) and s.get(k) and norm(r[k])!=norm(s[k]): conflicts.append(k)
 out.append({'id':r['id'],'identity':'conflict' if conflicts else 'matched' if s else 'unverified','conflicts':conflicts,'locator':r.get('locator'),'support':'requires reading source; identity alone does not establish support'})
json.dump(out,open(sys.argv[2],'w',encoding='utf-8'),ensure_ascii=False,indent=2)
