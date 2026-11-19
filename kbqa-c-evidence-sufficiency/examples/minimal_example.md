# 最小调用示例（虚构示意，非正式案例结果）

以下内容为演示接口的**示例**，文件、哈希与数据均为虚构。

## 输入

`/input/docs/exp_a.md`（第 2 行）：

```
反应温度 400 °C 下，CO 转化率为 88.1%。
```

`/input/docs/exp_b.md`（第 2 行）：

```
修订后：400 °C 下 CO 转化率为 92.3%。
```

`/input/raw/results_2022.csv`：存在但无读权限。

`/input/case.json`（节选）：

```json
{"case_id": "demo-case-002",
 "questions": [{"id": "Q1", "text": "CO 转化率是多少？"},
               {"id": "Q2", "text": "results_2022.csv 中的平均粒径是多少？"}],
 "output_contract": {"answers": "带裁决的回答"}}
```

## 调用

```bash
SKILL=/skills/weekly-skill
python3 $SKILL/scripts/suff_index.py --input /input --work /app/work --out /app/output
# stdout: index docs=4 extracted=3 inaccessible=1

# 模型从 case.json 提取 questions.json 后：
python3 $SKILL/scripts/suff_matrix.py --work /app/work --out /app/output
# stdout: matrix questions=2 grades={'SUPPORTED': 1, 'PARTIAL': 0, 'UNSUPPORTED': 0, 'INACCESSIBLE': 1}

python3 $SKILL/scripts/suff_conflict.py --work /app/work --out /app/output
# stdout: conflict facts=2 clear_conflicts=1

python3 $SKILL/scripts/suff_verdict.py --case /input/case.json --work /app/work --out /app/output
# stdout: verdict status=completed answers=2 grades={'SUPPORTED': 0, 'PARTIAL': 0, 'CONFLICTED': 1, 'UNSUPPORTED': 0, 'INACCESSIBLE': 1}
```

`/app/work/answers.json`（节选）：

```json
{"answers": [
  {"question_id": "Q1", "verdict": "SUPPORTED",
   "answer": "400 °C 下 CO 转化率为 88.1%。",
   "evidence": [{"doc_id": "D001", "locator": "L2-L2",
                 "quote": "CO 转化率为 88.1%。"}]},
  {"question_id": "Q2", "verdict": "INACCESSIBLE",
   "answer": "库中无依据：raw_data 仅有结果表而无对应说明文档。",
   "missing": "results_2022.csv 无读权限，需要组织方提权后方可读取平均粒径字段。"}]}
```

（注意：Q1 模型声明 SUPPORTED，但 conflicts.json 检出 `转化率` 88.1 vs 92.3 的 clear_conflict，suff_verdict.py 将其降级为 CONFLICTED 并记入 change_log——这正是判据不可被措辞绕过的演示。）

## 示意输出（示例，非真实运行结果）

`result.json`（节选）：

```json
{"case_id": "demo-case-002", "status": "completed",
 "answers": [
  {"question_id": "Q1", "verdict": "CONFLICTED", "declared_verdict": "SUPPORTED",
   "answer": "库内证据相互冲突：exp_a.md 给出 88.1%，exp_b.md（修订版）给出 92.3%；任务未指定权威版本，本工作不作取舍。",
   "evidence": [{"doc_id": "D001", "path": "docs/exp_a.md", "sha8": "1a2b3c4d", "locator": "L2-L2"}]},
  {"question_id": "Q2", "verdict": "INACCESSIBLE",
   "answer": "库中无依据：raw_data 仅有结果表而无对应说明文档。",
   "missing": "results_2022.csv 无读权限，需要组织方提权后方可读取平均粒径字段。"}],
 "grade_summary": {"SUPPORTED": 0, "PARTIAL": 0, "CONFLICTED": 1, "UNSUPPORTED": 0, "INACCESSIBLE": 1},
 "change_log": ["question Q1: 涉及未决冲突 转化率，降级 CONFLICTED"],
 "uncertainty": ["问题 Q1（CONFLICTED）：存在未决证据冲突（转化率），已并列双方坐标，未裁决。",
                 "问题 Q2（INACCESSIBLE）：results_2022.csv 无读权限，需要组织方提权后方可读取平均粒径字段。"]}
```
