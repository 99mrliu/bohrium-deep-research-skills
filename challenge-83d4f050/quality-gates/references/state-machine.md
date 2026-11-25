# 状态与规格

正式运行使用 `scripts/run_case.py`，路径为 `/input`、`/app/work`、`/app/output`。状态依次是 observed、specified、rendered、exported、audited、delivered；每个 checkpoint 原子写 manifest。

规格示例结构：

```json
{"title":"Case-specific figure","entities":[{"id":"a","label":"A","x":100,"y":180,"note":"","source":"paper.pdf p.4 Fig.3"}],"edges":[{"id":"ab","source":"a","target":"b","relation":"activates","legend":"activates","kind":"direct","evidence":"paper.pdf p.4"}],"legend":[{"relation":"activates","label":"activation","color":"#2563eb"}]}
```

实际边需 `id,source,target,relation,legend,kind`，kind 为 direct、feedback 或 uncertain；实体含 `id,label,x,y,note,source`，可选 fill/stroke。正式内容必须来自当前案例，不得复用合成节点。result.json 动态保留原始 output_contract 全字段；状态仅 success、partial、failed。机器 audited 后仍 partial，原生 PNG/PDF 目检及哈希绑定后才 success。
