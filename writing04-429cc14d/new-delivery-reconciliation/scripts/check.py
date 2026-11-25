import json,sys,hashlib,re
x=json.load(open(sys.argv[1],encoding='utf-8')); text=x['manuscript']; cited=[int(n) for n in re.findall(r'\[(\d+)\]',text)]; listed=[int(n) for n in x['bibliography_numbers']]
result={'cited':sorted(set(cited)),'listed':sorted(set(listed)),'missing_from_list':sorted(set(cited)-set(listed)),'uncited_in_list':sorted(set(listed)-set(cited)),'duplicate_list_numbers':sorted({n for n in listed if listed.count(n)>1}),'manuscript_sha256':hashlib.sha256(text.encode()).hexdigest(),'scope':'numeric [n] citations only; inspect ranges, superscripts, captions and fields manually'}
json.dump(result,open(sys.argv[2],'w',encoding='utf-8'),ensure_ascii=False,indent=2)
