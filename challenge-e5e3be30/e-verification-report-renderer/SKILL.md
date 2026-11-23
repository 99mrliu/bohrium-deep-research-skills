---
name: verification-report-renderer
description: 文献证据溯源与事实核验任务的下游交付工程工具链。当任务要求对论断做四级判定（supported/partially_supported/contradicted/insufficient_evidence）并交付 result.json、证据卡片、核验报告及真实渲染预览（PDF/HTML）时使用；提供契约装配（骨架-增量合并-完工校验）、证据卡片渲染、报告渲染降级链与提交前总闸门。不用于论断本身的检索与推理判断，也不用于无结构化交付契约的开放式写作。
---

# 核验报告交付工程：契约装配、证据卡片与渲染预览

核验链条"论断→证据→定位→判定→理由"能否被评审一分钟复核，取决于交付形态。
本 Skill 把交付链做成确定性工具，Agent 把推理预算留给核验本身。

## 何时用 / 何时不用

**用**：
- 输入含 `case.json`（带 `output_contract`）、`claims-to-verify.json`、论文 PDF，
  要求交付 `/app/output/result.json` 及配套报告；
- 需要把判定结果渲染成统一版式证据卡片与核验报告，并附**真实渲染**的
  PDF/HTML 预览；
- 预算受限（64 请求 / 900s / 16k tokens），需要"先存后改"的增量交付纪律。

**不用**：
- 论断的检索、阅读、推理判定本身（那是模型的工作，本 Skill 只约束交付格式）；
- 无 output_contract 的开放式综述写作；
- 需要 Office 复杂排版（本链产物为 Markdown + PDF/HTML 预览）。

## 评测运行契约（必须遵守）

1. Skill 安装到 `/skills/weekly-skill`；下文 `<skill>` 即该根目录。
2. 输入在 `/input/`：`case.json`（含 `case_id` 与 `output_contract`）、`task.md`、
   `claims-to-verify.json`（论断是**待核验的问题**，不是权威事实）、论文 PDF、
   `environment/resources.yaml`（若有，列 latex-compiler / office-renderer /
   pdf-render-tool 等可用工具）。
3. 工作目录 `/app/work`；最终成果 `/app/output`，必须有 `result.json`：
   `case_id` + `output_contract` **全部字段** + 诚实 `status`
   （success/partial/cannot_determine/refused）+ `sources` + `uncertainty`
   + `change_records`。
4. 四级判定纪律：`supported` / `partially_supported` / `contradicted` /
   `insufficient_evidence`；**主题相关 ≠ 支持；未报告 ≠ 反驳；证据冲突时
   并列双方原话**，不替作者取舍。
5. 平台要求可编辑交付物附**真实渲染**的 PDF/PNG 预览；渲染降级必须声明，
   **绝不伪造渲染产物**。

## 工具一览

| 工具 | 作用 | 退出码 |
| --- | --- | --- |
| `<skill>/scripts/contract_assemble.py` | output_contract 发现、骨架生成、增量合并、完工校验 | 0/1/2 |
| `<skill>/scripts/cards_render.py` | 判定 JSON → schema 校验 → 证据卡片 Markdown | 0/1/2 |
| `<skill>/scripts/report_render.py` | 卡片集 → 报告 Markdown → PDF/HTML 真实渲染（降级链） | 0/1/2 |
| `<skill>/scripts/gate.py` | 提交前总闸门：契约 + 逐字回查 + 一致性 | 0/1/2 |

参考文档：`references/report-schema.md`（result.json 与判定对象 schema）、
`references/card-template.md`（卡片版式与机读锚点）、
`references/preview-policy.md`（渲染降级链与诚实声明规则）。
可运行示例：`examples/run_example.sh`（合成示例，端到端演示）。

## 标准流水线

### 第 0 步：输入盘点（1–2 个请求内完成）

- 读 `/input/case.json`：记下 `case_id`、`output_contract` 字段清单；
- 读 `task.md` 与 `claims-to-verify.json`：统计论断条数；
- 检查 `environment/resources.yaml` 是否提供 latex/pandoc/pdf 工具；
- 列出论文 PDF，规划分页文本抽取。

### 第 1 步：先写骨架（先存后改的地基）

```bash
python3 <skill>/scripts/contract_assemble.py skeleton \
    --case /input/case.json --out /app/output/result.json
```

骨架立即落盘：`case_id` 填好、`status=partial`、全部契约字段 null 占位、
`missing_items` 列出全部契约字段。**此后即使预算耗尽，/app/output 里也有
一份合法的 partial 结果**——这是增量保存纪律的核心。

### 第 2 步：分页文本抽取

用平台 pdf-render-tool 或 `pdftotext -layout` 把论文 PDF 抽成
`/app/work/pages.jsonl`（每行 `{"page": int, "text": str}`）。gate 以此回查
每条 quote，页码必须与 PDF 物理页一致。纯文本示例见 `examples/run_example.sh`
第 0 步（按 `\f` 分页）。

### 第 3 步：核验论断（模型推理，规则从简）

对每条论断：定位相关段落 → 摘逐字 quote（含页码）→ 按四级枚举判定 →
写 rationale（为何是该判定而非相邻判定）→ 有冲突填 `conflicts` 双方原话 →
有疑点填 `uncertainty`。判定对象 schema 见 `references/report-schema.md`。

**每完成一批（甚至一条）论断就增量合并落盘**：

```bash
python3 <skill>/scripts/contract_assemble.py merge \
    --base /app/output/result.json --new /app/work/batch-N.json \
    --out /app/output/result.json --case /input/case.json
```

merge 深度合并：空值（null/""/[]/{}）绝不覆盖已有非空字段，列表去重追加，
并自动重算 `missing_items`、追加 `change_records`。这支撑"先存后改"：
任何时候中断，result.json 都是自洽的 partial。

### 第 4 步：证据卡片

```bash
python3 <skill>/scripts/cards_render.py \
    --verdicts /app/work/verdicts.json --out /app/output/evidence-cards.md
```

每条判定先过内嵌 schema（必填字段、verdict 枚举、quote 非空、page 正整数），
不过则 exit 1 并列出全部错误——**先修数据再渲染**，不让格式漂移进入交付物。

### 第 5 步：报告渲染（含真实预览）

```bash
python3 <skill>/scripts/report_render.py \
    --cards /app/output/evidence-cards.md --case /input/case.json \
    --result /app/output/result.json --outdir /app/output
```

产物：`verification-report.md`（封面：case_id、日期、论断统计表、四级判定
分布、不确定性汇总 + 卡片全文 + 渲染链说明）、真实渲染预览、`render-info.json`。

渲染链按优先级真实探测、真实执行：**xelatex → pdflatex → pandoc → 自包含
HTML**。每步成功的标准是返回码 0 且产物非空；失败如实降级。报告尾部固定写入
"渲染链实际路径与降级说明"——**诚实声明是硬性义务**（规则全文见
`references/preview-policy.md`）：
- 不许把 Markdown 改名 PDF；不许声称渲染成功而产物不存在；
- 未走 xelatex 链必须附降级声明；
- 预览必须与报告同源同时，报告更新后必须重渲。

### 第 6 步：回写契约字段并完工校验

把 `render-info.json` 的 `chain` / `preview_path` / `report_markdown_path`
与卡片路径 merge 回 result.json，置最终 `status`，然后：

```bash
python3 <skill>/scripts/contract_assemble.py validate \
    --case /input/case.json --result /app/output/result.json
```

validate 检查：字段完整性、`case_id` 一致、`status` 自洽（partial 必须给出
覆盖全部空契约字段的 `missing_items`；success 不得有空契约字段）。
不过 exit 1，**修复后再往下走**。

### 第 7 步：提交前总闸门（不过不得提交）

```bash
python3 <skill>/scripts/gate.py \
    --case /input/case.json --result /app/output/result.json \
    --pages /app/work/pages.jsonl --cards /app/output/evidence-cards.md
```

三道检查：契约校验（复用 validate）+ 每条 quote 归一化回查分页文本
（NFKC、弯引号→直引号、连字符归一、空白折叠）+ 卡片与 result.json 的
claim_id/verdict 一一对账。**GATE: PASS（exit 0）才允许结束任务**；
FAIL 时按 ERROR 清单逐条修复后重跑。

## 预算与增量保存纪律

- 第 1 步骨架必须在前 2 个请求内落盘；之后每完成一条论断立即 merge；
- merge 幂等可重入，中断恢复后直接继续 merge 下一批；
- 报告渲染（第 5–6 步）留在核验基本完成之后；预算紧张时宁可报告走 HTML
  链，也要保证 result.json 字段齐全、gate 通过；
- `change_records` 由工具自动追加，不要手工伪造时间线。

## 异常处理表

| 异常 | 处理 |
| --- | --- |
| case.json 无 output_contract | skeleton exit 2；人工读 task.md 推断交付字段，在 uncertainty 中声明偏差 |
| 某条论断找不到任何相关段落 | verdict=insufficient_evidence，quotes 引用最接近段落并说明，uncertainty 注明 |
| 证据相互冲突 | verdict=partially_supported（或 insufficient_evidence），conflicts 并列双方原话 |
| cards_render schema exit 1 | 按错误清单修 verdicts 数据；不许绕过校验手改卡片 |
| 无 latex/pandoc | 正常走 HTML 链，报告附降级声明；**不扣分，伪造才扣分** |
| latex 编译失败（如 CJK 字体） | 工具自动降级并在 attempts 中记录失败原因 |
| gate quote 回查失败 | 回到原文重摘逐字 quote（允许弯直引号/空白差异，不允许改写） |
| gate 卡片-结果不一致 | 以 result.json 为准重跑 cards_render + report_render + gate |
| 预算将尽 | 保持 status=partial 与 missing_items 诚实，validate 通过后即可收尾 |

## 输出契约自查清单（提交前逐项打勾）

- [ ] `/app/output/result.json` 存在，JSON 合法，UTF-8；
- [ ] `case_id` 与 `/input/case.json` 完全一致；
- [ ] `output_contract` 全部字段存在且（success 时）非空；
- [ ] `status` 与内容自洽；partial 时 `missing_items` 覆盖全部空缺字段；
- [ ] 每条判定：claim 原文照录、verdict 四级枚举、quote 逐字可回查、页码正确、rationale 非空；
- [ ] 冲突条目已并列双方原话；
- [ ] `sources` / `uncertainty` / `change_records` 存在；
- [ ] evidence-cards.md、verification-report.md、真实预览（PDF 或 HTML）在 /app/output；
- [ ] 报告尾部含渲染链实际路径说明；降级已声明；
- [ ] `gate.py` 输出 `GATE: PASS`（exit 0）。
