import json,sys
x=json.load(open(sys.argv[1],encoding='utf-8')); refs=x['references']; seen=[]; issues=[]; result=[]
for part in x['parts']:
 marks=[]
 for key in part.get('citations',[]):
  if key not in refs: issues.append({'part':part['id'],'missing_key':key}); marks.append('?'+key); continue
  if key not in seen: seen.append(key)
  marks.append(str(seen.index(key)+1))
 result.append({'id':part['id'],'text':part['text'],'marker':'['+','.join(marks)+']' if marks else ''})
out={'parts':result,'bibliography':[{'number':i+1,'key':k,'record':refs[k]} for i,k in enumerate(seen)],'uncited':[k for k in refs if k not in seen],'issues':issues}
json.dump(out,open(sys.argv[2],'w',encoding='utf-8'),ensure_ascii=False,indent=2)
