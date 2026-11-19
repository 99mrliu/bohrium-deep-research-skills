# 最小调用示例（虚构示意，非正式案例结果）

以下内容为演示接口的**示例**，文件与哈希均为虚构。

## 输入

`/input/`：

```
papers/
  report_v1.md        # 初稿，与 v2 相似度 0.72
  report_v2.md        # 修订版（当前）
  report_v2_copy.md   # v2 的字节级副本（哈希相同）
notes/
  version_note.md     # "2022 年实验以 report_v2.md 为准"
case.json, task.md
```

`/input/case.json`（节选）：

```json
{"case_id": "demo-case-001",
 "questions": [{"id": "Q1", "text": "2022 年实验的转化率是多少？"}],
 "output_contract": {"catalog": "六维编目", "answers": "带来源的回答"}}
```

## 调用

```bash
SKILL=/skills/weekly-skill
python3 $SKILL/scripts/lib_inventory.py --input /input --work /app/work --out /app/output
# stdout: inventory files=5 extracted=5 skipped=0
python3 $SKILL/scripts/lib_lineage.py --input /input --work /app/work --out /app/output
# stdout: lineage groups=3 (alias=1 chain=1 unique=1) conflicts=0
python3 $SKILL/scripts/lib_catalog.py --input /input --work /app/work --out /app/output
# stdout: catalog entries=5 groups=3 conflicts=0 skipped=0
python3 $SKILL/scripts/lib_finalize.py --case /input/case.json --work /app/work --out /app/output
# stdout: finalized status=completed answers=1 evidence=1 dropped=0 caveats=0
```

## 示意输出（示例，非真实运行结果）

`artifacts/catalog.json`（节选）：

```json
{"dimensions": {
   "file_types": {".md": 4, ".json": 1},
   "duplicates": [{"group_id": "G01", "kind": "alias",
                   "members": ["E003", "E004"], "kept": "E003",
                   "basis": [{"a": "E003", "b": "E004", "kind": "exact", "score": 1.0}]}],
   "version_diffs": [{"group_id": "G02", "chain": [
     {"entry_id": "E002", "role": "current"},
     {"entry_id": "E001", "role": "historical"}]}]},
 "entries": [{"entry_id": "E002", "path": "papers/report_v2.md",
              "current_version": true, "readable": true}]}
```

`/app/work/answers_draft.json`（节选）：

```json
{"answers": [{"question_id": "Q1",
  "answer": "2022 年实验转化率 92.3%。[E002|7b1d9c04|L30-L31]",
  "evidence": [{"entry_id": "E002", "locator": "L30-L31",
                "quote": "400 °C 下转化率稳定为 92.3%。"}]}]}
```

`result.json`（节选）：

```json
{"case_id": "demo-case-001", "status": "completed",
 "catalog_summary": {"duplicate_groups": 1, "version_chains": 1,
                     "unreadable_skipped": []},
 "answers": [{"question_id": "Q1", "answer": "2022 年实验转化率 92.3%。[E002|7b1d9c04|L30-L31]",
              "evidence": [{"entry_id": "E002", "path": "papers/report_v2.md",
                            "sha8": "7b1d9c04", "locator": "L30-L31"}]}],
 "uncertainty": [], "change_log": ["lib_inventory: 5 files, 5 extracted, 0 skipped"]}
```
