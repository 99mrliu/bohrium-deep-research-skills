# 任务:增量导入治理对账(合成示例)

组织者上一轮(`/input/materials/import_state.json`,方言 a)已从 crossref /
europepmc / publisher 三库导入了一批文献记录,并保存了逐库水印与逐记录
内容哈希。本轮只拿到 crossref 与 europepmc 的离线响应材料
(publisher 响应本次缺席)。请:

1. 对账上一状态与当前响应,把每个标识符分类为 new / unchanged /
   changed(给出 field 级 before→after)/ withdrawn /
   unverifiable_withdrawal / inconsistent_state;
2. 生成本轮水印推进提案 —— **只出提案,绝不写回** import_state.json;
3. 交付 `result.json`(含 output_contract 全部字段)与 `delta_report.md`。

约束:离线,只用本地材料;同输入重跑必须字节一致;无法判定的如实声明。
