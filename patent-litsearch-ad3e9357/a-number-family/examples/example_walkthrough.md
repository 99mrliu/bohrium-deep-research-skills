# 最小调用示例（示例，非正式案例结果）

本示例使用 `examples/fixtures/` 下的**合成玩具语料**（全部虚构，标注 illustrative），仅用于说明接口与完整使用流程。

## 输入

- `examples/fixtures/case.json`：`case_id=EX-ILLUSTRATIVE-001`，`output_contract` 含 candidates/family_scope/status_note 三字段。
- `examples/fixtures/corpus.json`：3 条虚构专利记录（US 授权+公开+申请、WO 公开、CN 公开）。
- `examples/fixtures/facsimile_page1.txt`：模拟 pdftotext 输出的虚构 USPTO 首页（含重复 INID `(72)` 与无国别码申请号 `15/654,321`）。

## 调用

```bash
S=scripts
python3 $S/scaffold_result.py --case examples/fixtures/case.json --out /tmp/ex_out --status partial
python3 $S/scan_corpus.py index --roots examples/fixtures --out /tmp/ex_idx.json
python3 $S/scan_corpus.py query --index /tmp/ex_idx.json --numbers "US 10,293,847 B2"
python3 $S/extract_facsimile.py --text examples/fixtures/facsimile_page1.txt --out /tmp/ex_fx.json
python3 $S/merge_family.py --records examples/fixtures/corpus.json --out /tmp/ex_fam.json
python3 $S/scaffold_result.py --case examples/fixtures/case.json --out /tmp/ex_out --status partial
```

## 示意输出（节选，示例）

- 查询 `US 10,293,847 B2`：`exact_hits` 命中 corpus.json `$.records[0].numbers[0]` 与传真文本 `line 2`，规范键 `US-grant-10293847`。
- 传真抽取：`document_id=US-grant-10293847`、`grant_date.iso=2021-06-15`；`evidence_events` 含 `cc_fallback`（申请号 `15/654,321` 按 US 回退为 `US-app-15654321`）与 `inid_duplicate`（`(72)` 重复）。
- 同族归并：扩展族 `[rec1, rec2]`（共享优先权 `US|15654321`）、`[rec3]`；简单族三者各自独立（优先权集合不同）；`scope_note.limitation` 声明"非完整同族"。
- result.json：`case_id` 已填、三契约字段未填充时列入 `uncertainty`，`status=partial`。

## 负例演示

- `python3 scripts/patent_numbers.py normalize "GARBAGE-123"` → exit 1，`ok=false`，警告"不猜测格式"。
- 空目录建索引 → exit 2，warnings 说明未发现语料。
- `no_inid.txt` 抽取 → `extraction_status=degraded`，记 `no_inid` 事件。

完整断言见 `scripts/selfcheck.py`（25 项）。
