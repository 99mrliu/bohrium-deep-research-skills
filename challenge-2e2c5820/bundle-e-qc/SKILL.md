---
name: feasibility-review-qc-foundry
description: 实验方案可行性评估的"过程质控与可复核交付"技能。当需要让审查结论能进入真实流程、事后可复核、结论与内容一致、交付契约不缺字段时使用。核心机制：契约优先脚手架（parse_contract 第一分钟即落地 honest-partial 骨架）+ 六道质控门 G1-G6（selfcheck 聚合，FAIL 必须修复或降级）+ 审查意见机器自检（lint_review 五条规则）+ 全输入输出 SHA-256 可复算 manifest（含复算命令行）+ stdlib-only 渲染独立 HTML 审查报告并按平台能力补 PDF/PNG 预览。
---

# 实验方案可行性评估 · 过程质控与可复核交付工程

## 解决什么问题

把"可行性审查"本身当作一条可审计流水线来管，专治四类失效：

1. **审查意见无法进入真实流程** —— 交付缺契约字段，下游系统拒收（→ G1/G6）。
2. **事后无法复核/复算** —— 结论无证据锚点、文件被改过无记录（→ G4/G5 + manifest）。
3. **结论与内容不一致** —— 「有条件可行」没有条件、同一方案两个结论（→ G3 lint）。
4. **状态粉饰** —— 没做完却写 complete，或 partial 不说缺什么（→ G2 + partial_policy）。

## 输入输出契约

- 运行时输入：`/input/case.json`（字段名不固定，**先读实际文件**；用 parse_contract 定位
  output_contract，兼容 list / dict / JSON-Schema properties 三种形态）与 `/input/task.md`。
- 运行时输出（`/app/output/`）：
  - `result.json`：case_id + output_contract 全部字段 + status（complete/partial/failed）
    + sources + uncertainty + change_record；
  - `review_report.md`：人读审查报告，结论带定位锚点（`[L12]`、`（第X节）`）；
  - `review_report.html`（及平台能力下的 PDF/PNG 预览）；
  - `manifest.json` / `manifest.md`：全部输入输出 SHA-256 + 复算命令行；
  - `qc_report.md`：六道质控门结果。
- 规则细节：`references/qc_gates.md`（门禁判据）、`references/partial_policy.md`（诚实
  部分交付状态机与 checkpoint 节奏）。运行时路径以 `/skills/weekly-skill/` 为根。

## 严格按序工作流

**步骤 0（第 0 分钟，最先做）**：契约解析 + 骨架落地。

```bash
python3 /skills/weekly-skill/scripts/parse_contract.py /input/case.json /app/output
cp /app/output/result.skeleton.json /app/output/result.json   # 立即落地 honest partial
```

先打印的字段清单就是后续所有工作的 checklist；骨架让 result.json 自第一分钟起就是
一份合法交付（status=partial，uncertainty 非空）。

**步骤 1-3**：按 task.md 完成七类约束审查（科学合理性/资源/预算/排期/安全合规/参数域/
可复现）。预算机时必须真实算术；**每完成一类，立即把中间结论 merge 进
/app/output/result.json** 并在 change_record 追加一条（谁、何时、改了什么）。

**步骤 4**：写 `/app/output/review_report.md`。要求：每个结论词后附条件/理由；「有条件
可行」必带编号条件清单；关键结论带证据锚点；「建议进一步确认」只能出现在编号条目内。

**步骤 5（修复循环）**：

```bash
python3 /skills/weekly-skill/scripts/lint_review.py /app/output/review_report.md --strict
python3 /skills/weekly-skill/scripts/validate_result.py /input/case.json /app/output/result.json
```

任一不通过：回到步骤 1-4 修复，再跑，直到两者 exit 0。

**步骤 6**：渲染交付。

```bash
python3 /skills/weekly-skill/scripts/render_report.py \
  /app/output/review_report.md /app/output/result.json /app/output/review_report.html
```

随后按平台能力用 office-renderer 把 HTML/MD 再导出 PDF/PNG 预览，放入 /app/output。

**步骤 7**：可复算清单。先写 `commands.txt`（本流程实际执行的命令行，每行一条），再：

```bash
python3 /skills/weekly-skill/scripts/make_manifest.py \
  /input/case.json /input/task.md /app/output \
  -o /app/output --commands /app/output/commands.txt
```

**步骤 8（总闸）**：

```bash
python3 /skills/weekly-skill/scripts/selfcheck.py /app/output /input/case.json
```

exit 非 0（存在 FAIL）：**必须修复后重跑**；确属材料/时间所限无法修复的，把
result.json 降级为 `status=partial` 并在 uncertainty 写清缺口，再跑到 exit 0 为止。

## 异常处理

- **缺材料**：对应契约字段保持 null、status 保持 partial，uncertainty 逐条点名缺什么；
  绝不编造数字或把"待确认"写成事实（禁写清单见 partial_policy.md）。
- **case.json 结构异常**（找不到契约/JSON 损坏）：result.json 保持骨架，status=partial，
  uncertainty 说明解析失败原因，并在 change_record 记录。
- **时间不够**：立即停止新分析，保证当前 skeleton + 已完成部分能通过 selfcheck；
  未审完的约束类别写进 uncertainty。

## 预算意识（~64 请求 / 900 秒）

- 先存 partial 再优化：checkpoint 节奏 = 0 min 骨架 → 每完成一类约束 merge 一次 →
  ~600 s 跑一次 lint+validate → ~750 s 冻结分析、渲染 + manifest → 最后 selfcheck。
- lint/validate/manifest/selfcheck 都是本地 stdlib 脚本，**不消耗模型请求**，可随意多跑。
- 任何时刻被打断，/app/output 里的最新 result.json 都必须是一份诚实交付。
