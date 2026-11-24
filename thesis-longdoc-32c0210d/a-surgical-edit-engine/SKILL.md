---
name: surgical-edit-engine
description: 学位论文/长文档分章节工作稿的手术式编辑执行引擎。把 organizer-edit-workorder 编译为确定性操作 DSL（term_unify / float_ref_fix / replace / delete / format_normalize），由脚本事务式落改、自动验收、按 output_contract 装配 result.json；模型只处理编译器标记为 manual 的非机械改写。当 /input 提供 organizer-edit-workorder.json 与分章节 Markdown 工作稿、要求按工单编辑并产出 result.json 时使用。
---

# surgical-edit-engine — 工单 → 操作 DSL → 脚本直接落改

## 1. 用途与触发条件

输入是**分章节可编辑工作稿**（若干 Markdown 章节文件）+ `organizer-edit-workorder.json`（编辑工单）+ `case.json`（含 `output_contract.fields`）。本 Skill 的内核是**编辑执行引擎**：凡是机械可判定的编辑（术语统一、图表引用纠错、明确新旧文的替换/删除、数字-单位空格规范化）一律由脚本确定性完成并留下 hunk 级变更记录；模型只处理编译器识别不了、标记为 `manual` 的条目。

## 2. 输入契约（/input 布局）

```
/input/case.json                      # {"case_id","task","output_contract":{"fields":[...]}}
/input/organizer-edit-workorder.json  # {"schema":"organizer-edit-workorder/v1","items":[{id,title,action,target,acceptance}]}
/input/chapters/*.md                  # 分章节工作稿（位置可能不同，先 find 确认）
```

- `output_contract.fields` **运行时读取**，不得假设固定字段集合。
- 若只提供 PDF：先 `pdftotext -layout /input/xxx.pdf /app/work/src.txt`（pdftotext 不可用则如实记录到 uncertainty），按 `# 第X章` 切成 `/app/work/chapters/chNN.md` 再走下方流程。
- 工作目录 `/app/work`，最终产物 `/app/output`，`/app/output/result.json` 为必交付物。

## 3. 工作流（按序执行；标注【脚本】/【模型】）

设 `S=/skills/weekly-skill`（本 Skill 安装目录）。

**步骤 0【脚本】准备目录并定位章节：**

```bash
mkdir -p /app/work /app/output
ls -R /input
# 找到章节 .md 目录，记为 CH（如 /input/chapters）
```

**步骤 1【脚本】编译工单为 ops.json：**

```bash
python3 $S/scripts/compile_workorder.py \
  --workorder /input/organizer-edit-workorder.json \
  --case /input/case.json \
  --chapters <CH> \
  --out /app/work/ops.json
```

**步骤 2【模型】检查 ops.json：** 读 `/app/work/ops.json`。对每个 `type="manual"` 的 op 记下其 `action` 与 `reason`；对 `warning`（如 target 回退）确认可接受。不要手改 ops.json 里的确定性 op。

**步骤 3【脚本】先 dry-run 预览，再正式落改：**

```bash
python3 $S/scripts/apply_ops.py --ops /app/work/ops.json --src <CH> \
  --work /app/work/chapters --change-log /app/work/change_log.json --dry-run
python3 $S/scripts/apply_ops.py --ops /app/work/ops.json --src <CH> \
  --work /app/work/chapters --change-log /app/work/change_log.json
```

锚点找不到的 op 会记入 `problems` 并跳过，其余继续——脚本绝不静默失败。如需撤销：`--rollback` 恢复最近快照。

**步骤 4【脚本】立刻存一份可用 partial（预算铁律：先存再改进）：**

```bash
python3 $S/scripts/make_result.py --case /input/case.json \
  --work /app/work --chapters /app/work/chapters --out /app/output
```

**步骤 5【模型】处理 manual op：** 按 ops.json 中 `manual_ops` 的 `action`，直接编辑 `/app/work/chapters/` 下对应章节文件（只改必要处，保留原有 Markdown 结构）。模型只允许做这一步的非机械改写；机械改写已被步骤 3 完成。

**步骤 6【脚本】验收；FAIL 则回到步骤 5 修复后重验：**

```bash
python3 $S/scripts/verify_acceptance.py \
  --workorder /input/organizer-edit-workorder.json \
  --ops /app/work/ops.json \
  --chapters /app/work/chapters \
  --out /app/work/acceptance_report.json
# 退出码非零 = 有 FAIL，读报告逐项修
```

**步骤 7【脚本】重新装配最终 result.json（幂等，覆盖步骤 4 的 partial）：**

```bash
python3 $S/scripts/make_result.py --case /input/case.json \
  --work /app/work --chapters /app/work/chapters --out /app/output
```

## 4. 输出契约（result.json）

由 `make_result.py` 保证：含 `case_id`、`status`、`sources`、`problems`、`uncertainty`、`contract_fields`，以及 `output_contract.fields` 声明的**每一个字段**（运行时逐字段填充）：

| 字段 | 填充规则 |
|---|---|
| `edited_chapters` | 编辑后章节复制到 `/app/output/chapters/`，值为相对路径列表 |
| `change_record` | change_log 全文（同时另存 `/app/output/change_record.json`） |
| `consistency_report` | 图表引用完整性 + 术语缺失断言结果 |
| `acceptance_report` / `verification` | 逐项 PASS/FAIL/SKIP 验收报告 |
| `uncertainty` | manual 项、锚点未命中、候选不唯一等不确定来源列表 |
| 未知字段 | `null` + problems 记录，绝不编造 |

`status`：`complete`（无 problem/manual/FAIL）/ `partial`（有问题但产物可用，必须在 uncertainty 写明限制）/ `failed`（关键输入缺失）。**诚实 partial 优于伪造 complete。**

## 5. 异常矩阵

| 异常 | 降级路径 |
|---|---|
| 章节材料缺失/目录为空 | compile 直接报错退出；make_result 仍写 status=failed 的 result.json，problems 说明缺失 |
| workorder item 无法识别 | 编译为 `manual` op（保留 action 原文 + reason），步骤 5 由模型处理 |
| 锚点找不到（术语/旧文/引用不存在） | 该 op 记 problem 跳过，其余 op 继续；进入 uncertainty，status 降 partial |
| 图表引用候选题注不唯一 | 记 `unresolved`，verify 标 SKIP，由模型判断后手动改章节 |
| target 章节匹配失败 | 回退全部章节并在 op 上标 `warning` |
| 落改出错想撤销 | `apply_ops.py --rollback` 恢复最近快照 |
| pdftotext 不可用 | 在 uncertainty 记录“PDF 未抽取”，仅基于已有 Markdown 工作 |
| 时间/预算不足 | 步骤 4 已存 partial；后续步骤能跑多少跑多少，最后重跑 make_result 刷新 status |
| acceptance FAIL 无法消除 | 保留 FAIL 于报告，status=partial，uncertainty 逐条说明，不得改报告充 PASS |

## 6. 依赖与文件清单

- 依赖：python3（仅标准库）；可选外部依赖 `pdftotext`（仅当输入为 PDF 时）。
- `scripts/compile_workorder.py` — 工单 → ops.json（替模型省：类型识别、目标解析、图表引用悬空扫描）
- `scripts/apply_ops.py` — ops → 事务式落改 + hunk 级 change_log + 快照/回滚（替模型省：机械替换与留痕）
- `scripts/verify_acceptance.py` — acceptance → 可执行断言，逐项 PASS/FAIL，非零退出（替模型省：全文复查）
- `scripts/make_result.py` — output_contract 装配 + 原子写 result.json（替模型省：契约对齐与交付）
- `references/ops_dsl.md` — 操作 DSL 字段与语义；`references/editing_policy.md` — 脚本/模型分工与异常矩阵
- `examples/synthetic/` — 合成示例（非正式案例），`run_example.sh` 一键端到端

## 7. 已知边界

- 只处理 Markdown 章节；docx/图片内文字不编辑。
- term_unify 是字面替换，不做语义消歧（同形异义需走 manual）。
- float_ref_fix 仅在“同章同类型题注唯一”或“全文同类型题注唯一”时自动改号；其余交给模型。
- format_normalize 仅内置 `number_unit_space` 一条规则；其它格式规范编译为 manual。
- 题注识别约定：行首（可带 `**`）的 `图x-y`/`表x-y`；其它题注风格需在 ops.json 生成后人工核对。
- 示例 `examples/synthetic/` 为合成数据，仅用于验证流程，不代表真实案例结果。
