---
name: auditgate-process-qc
description: >-
  过程质量控制 / 独立审计门。当科研成果的改写稿、翻译稿或文体转换稿
  （如论文→科普、中文→英文、长文→摘要）写完后，需要逐段逐句与源文对照、
  生成双向映射（稿→源支撑、源→稿覆盖）、校验改动清单（每处删改有动作
  类型与理由、每处删减可追溯）、汇总待确认问题供原作者复核、并执行
  「不过门不交付」的发布前审计时，触发本技能。适用于科研成果转化写作
  流程的复核阶段，不负责改写本身。
---

# AuditGate：科研成果转化写作的独立审计门

## 一、重心与边界

本技能只做**过程质量控制（process QC）**，不做写作：

- **独立性**：审计门独立于写作过程，在改写稿/翻译稿/文体转换稿**完成之后**运行，属于事后复核（post-hoc audit），不介入、不修改稿件本身。
- **双向映射**：正向——每句稿映射到最相似源句并给出支撑判定；反向——含数字/图表引用/强度词的**关键源句**是否被稿件覆盖。
- **改动清单合法性**：每处删改必须有合法 `action` 与非空 `reason`；每处关键删减必须可追溯（有 `omit`/`condense` 记录）；拿不准的地方以「待确认问题」形式交原作者，而不是替原作者拍板。
- **不过门不交付**：gate 判 FAIL 时，`result.json` 必须如实记录失败检查项，稿件不得标记为完成。
- **边界**：不验证科学结论真伪、不查重、不做语言润色；数字锚点只做字面核对，不判断单位换算是否等价。详细协议见 `references/audit_protocol.md`。

## 二、运行契约

- 输入只读：`/input/case.json` 与 `/input/task.md`。从 `case.json` 中定位源文、改写稿、改动清单（字段名以各案例 schema 为准，找不到的字段写入 `missing_fields`）。
- 中间产物写入 `/app/work`，最终产物写入 `/app/output`。
- `result.json` 契约：必须含 `case_id` 与 case 自带 `output_contract` 要求的全部字段；写不出的字段给 `null`/`[]` 并在 `notes` 说明（**诚实 partial**）；不得预制答案、不得把合成示例的内容写进正式结果。
- 建议 `result.json` 至少含：`case_id`、`gate_verdict`（PASS/FAIL/MANUAL_REVIEW）、`checks`、`alignment_path`、`editlog_report_path`、`pending_questions`、`missing_fields`、`notes`。
- 脚本仅用 Python 3 标准库，同一输入输出确定；所有脚本**只读输入文件**，只写 `--outdir` 指定目录。

### 退出码（各脚本）

| 脚本 | 0 | 非 0 |
|---|---|---|
| `align_map.py` | 正常完成（含 degraded） | 2=输入错误；1=内部错误 |
| `editlog_check.py` | PASS | 4=FAIL（非法条目/删减无记录）；2=输入错误；1=内部错误 |
| `audit_gate.py` | PASS（可交付） | 5=FAIL（不过门）；6=MANUAL_REVIEW（降级人工复核）；2=输入错误；1=内部错误 |

## 三、标准流程

```bash
# 技能路径；评测机上即 /skills/weekly-skill
SK=/skills/weekly-skill
# fallback 定位：找不到时全局搜索 align_map.py
if [ ! -f "$SK/scripts/align_map.py" ]; then
  P=$(find / -maxdepth 6 -name align_map.py 2>/dev/null | head -n 1)
  SK=$(dirname "$(dirname "$P")")
fi

mkdir -p /app/work /app/output
# 从 case.json 提取三份材料（字段名以案例 schema 为准，此处为示意）
python3 - <<'EOF'
import json
case = json.load(open('/input/case.json', encoding='utf-8'))
open('/app/work/source.md', 'w', encoding='utf-8').write(case.get('source_text', ''))
open('/app/work/draft.md',  'w', encoding='utf-8').write(case.get('rewritten_text', ''))
log = case.get('edit_log') or []
with open('/app/work/edit_log.jsonl', 'w', encoding='utf-8') as f:
    for e in log:
        f.write(json.dumps(e, ensure_ascii=False) + '\n')
print(case.get('case_id'))
EOF

# 第 1 步：句级双向对齐（源文、改写稿只读）
python3 "$SK/scripts/align_map.py" /app/work/source.md /app/work/draft.md \
    -o /app/work
# 第 2 步：改动清单合法性校验（退出码 4 = FAIL，属正常业务结果）
python3 "$SK/scripts/editlog_check.py" /app/work/edit_log.jsonl \
    --alignment /app/work/alignment.json -o /app/work || true
# 第 3 步：审计门汇总（0=PASS / 5=FAIL / 6=MANUAL_REVIEW）
python3 "$SK/scripts/audit_gate.py" \
    --alignment /app/work/alignment.json \
    --editlog-report /app/work/editlog_report.json \
    --source /app/work/source.md --draft /app/work/draft.md \
    -o /app/output || true
# 汇总 result.json（含 case_id 与 output_contract 全部字段）
python3 - <<'EOF'
import json
case = json.load(open('/input/case.json', encoding='utf-8'))
gate = json.load(open('/app/output/gate_verdict.json', encoding='utf-8'))
result = {
    'case_id': case.get('case_id'),
    'gate_verdict': gate['verdict'],
    'checks': {c['name']: c['verdict'] for c in gate['checks']},
    'alignment_path': '/app/work/alignment.json',
    'editlog_report_path': '/app/work/editlog_report.json',
    'pending_questions': gate.get('pending_questions', []),
    'missing_fields': [k for k in ('source_text', 'rewritten_text', 'edit_log')
                       if k not in case],
    'notes': 'auditgate 独立事后复核；FAIL 表示不过门不交付，非写作失败。',
}
for k in (case.get('output_contract') or {}):
    result.setdefault(k, None)
json.dump(result, open('/app/output/result.json', 'w', encoding='utf-8'),
          ensure_ascii=False, indent=2)
EOF
```

## 四、异常处理

- **源文极短（<3 句）或稿件极短（<2 句）**：`align_map.py` 仍以退出码 0 完成，但输出 `meta.mode="degraded"` 并写明原因；`audit_gate.py` 据此判 `MANUAL_REVIEW`（退出码 6）——**降级为人工复核清单，而非误判 FAIL**。
- **对齐分数普遍偏低**（稿句平均最佳分 < supported 阈值）：标记 `low_global_confidence` 并同样降级为 `MANUAL_REVIEW`。低分通常意味着大幅意译或阈值不适配，此时应调阈值重跑或交人工，**不得直接把全稿判 FAIL**。
- **硬错误优先**：若降级的同时仍存在硬错误（删减无记录、edit_log 非法、稿件数字在源文中找不到），仍判 FAIL（退出码 5）——降级只豁免「对齐统计不可靠」，不豁免已查实的违规。
- **edit_log 为空文件**：合法输入；此时任何删减都会因无 `omit` 记录而 FAIL，提示「改写必有改动，空清单本身即可疑」。
- **输入文件缺失/为空**：退出码 2，`result.json` 记 `missing_fields`，按诚实 partial 交付。

## 五、最小合成示例

`examples/` 下是**虚构**的「某锂电池回收研究」：`source.md`（9 句源文）、
`draft.md`（7 句改写稿，删去浸出渣残留率与图 2 引用两处关键信息）、
`edit_log_bad.jsonl`（含 1 条空 reason、1 处删减无记录）与
`edit_log_good.jsonl`（全合法、删减均有 `omit` 记录、2 条待确认）。
真实运行命令与结果见 `examples/README.md`，输出原件存于 `examples/expected/`：
bad → 退出码 4 → gate FAIL（退出码 5）；good → 退出码 0 → gate PASS（退出码 0）。

## 六、局限

- 相似度为字符 3-gram Jaccard，对**同义改写/跨语言翻译**敏感不足：大幅意译会落到 weak 甚至 unsupported，跨语言场景几乎必然低分，此时应依赖 edit_log 与人工复核而非对齐分数（阈值可用 `--supported/--weak` 调整，调整须记录）。
- 数字锚点只做**字面**子串核对：「96.5%」改写为「百分之九十六点五」会被误判缺失；「2」这类单数字易误命中。
- 句级对齐不理解篇章结构（段落移动 `move` 的合理性只能人工判断）。
- Markdown 标题行不参与句级对齐（标题通常刻意改写）。
- 审计门判断「是否可追溯、是否需复核」，不判断「科学上是否正确」。
