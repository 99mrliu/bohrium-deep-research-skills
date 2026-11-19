# 最小调用示例（虚构示意，非正式案例结果）

以下内容为演示接口的**示例**，文件、哈希与引文均为虚构，不可当作真实结果。

## 输入

`/input/case.json`（节选）：

```json
{
  "case_id": "demo-case-000",
  "questions": [
    {"id": "Q1", "text": "催化剂 X 在 400 °C 下的转化率是多少？"}
  ],
  "output_contract": {"answers": "每题带来源引用的回答", "sources": "引用清单"}
}
```

`/input/papers/exp_report.txt`（第 12–15 行）：

```
12  实验在固定床反应器中进行。
13  催化剂 X 装填量 0.50 g。
14  在 400 °C、空速 6000 h-1 条件下，
15  CO 转化率稳定为 92.3%。
```

## 调用

```bash
python3 /skills/weekly-skill/scripts/kb_build_index.py --input /input --work /app/work --out /app/output
# stdout: indexed=2 extracted=2 skipped=0

python3 /skills/weekly-skill/scripts/kb_retrieve.py \
    --index /app/output/artifacts/kb_index.json --query "催化剂 X 400 °C 转化率"
# stdout（节选）: file_id F001, sha8 a3f2c1d9, hit L14-L15

python3 /skills/weekly-skill/scripts/kb_verify.py \
    --index /app/output/artifacts/kb_index.json \
    --citations /app/work/citations.jsonl \
    --report /app/output/artifacts/citation_verification.json
# stdout: verify total=1 passed=1 failed=0

python3 /skills/weekly-skill/scripts/kb_finalize.py --case /input/case.json --work /app/work --out /app/output
# stdout: finalized status=completed answers=1 citations=1 unsupported=0
```

其中 `citations.jsonl` 一行：

```json
{"id": "C1", "answer_id": "Q1", "claim": "催化剂 X 在 400 °C 下 CO 转化率为 92.3%", "file_id": "F001", "locator": "L14-L15", "quote": "在 400 °C、空速 6000 h-1 条件下，CO 转化率稳定为 92.3%。"}
```

## 示意输出（示例，非真实运行结果）

`result.json`（节选）：

```json
{
  "case_id": "demo-case-000",
  "status": "completed",
  "answers": [{
    "question_id": "Q1",
    "answer": "催化剂 X 在 400 °C、空速 6000 h-1 下的 CO 转化率为 92.3%。[F001|a3f2c1d9|L14-L15]",
    "claims": [{
      "claim": "催化剂 X 在 400 °C 下 CO 转化率为 92.3%",
      "evidence": [{"file_id": "F001", "locator": "L14-L15", "verification": "passed"}]
    }]
  }],
  "sources": [{"file_id": "F001", "path": "papers/exp_report.txt", "sha8": "a3f2c1d9"}],
  "uncertainty": [],
  "change_log": ["kb_build_index: indexed 2 files, 2 extracted, 0 skipped"]
}
```
