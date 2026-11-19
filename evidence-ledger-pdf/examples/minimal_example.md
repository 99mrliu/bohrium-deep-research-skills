# 最小调用示例（示意，非正式案例结果）

输入（示意）：`/input/case.json`、`/input/task.md`、`/input/paper1.pdf`。

```bash
python3 /skills/weekly-skill/scripts/run_case.py \
  --case /input/case.json --input-dir /input --work /app/work --out /app/output
# {"ok": true, "pdfs": 1, "pages": 12, "tool": "pdftotext", "parse_errors": 0}
#   ← 示例值；同时生成 corpus_index.json、corpus_pages/ 文本快照、partial result.json

python3 /skills/weekly-skill/scripts/ledger.py add \
  --ledger /app/output/evidence_ledger.json --doc paper1.pdf --page 5 \
  --quote "the energy density reached 402 Wh kg-1 at the cell level" \
  --sq SQ-2 --field 效应方向与量级
# {"ok": true, "evidence_id": "EV-0001", "locate": "hit@DOC-1:p5+812"}
#   ← 示例值；定位失败会返回 quote_not_located 并拒绝入库

python3 /skills/weekly-skill/scripts/claims.py add \
  --claims /app/output/claim_register.json \
  --claim "该体系在电芯层面实现了 402 Wh/kg 能量密度" \
  --strength fact --evidence EV-0001
# {"ok": true, "claim_id": "CL-001"}   ← 示例值

python3 /skills/weekly-skill/scripts/verify.py --out /app/output
# {"ok": true, "backlink_rate": 1.0, "claims": 1, "verified": 1, ...}  ← 示例值

python3 /skills/weekly-skill/scripts/finalize.py \
  --case /input/case.json --work /app/work --out /app/output
# {"ok": true, "status": "success", "backlink_rate": 1.0, "claims": 1}  ← 示例值
```

若录入的引用块在原文中不存在，`ledger.py add` 会以退出码 2 拒绝并给出
`quote_not_located`；若结论引用了不存在的证据号，`verify.py` 以退出码 1
报错，finalize 不会写 success。以上输出均为接口示意。
