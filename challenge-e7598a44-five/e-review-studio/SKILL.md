---
name: e-review-studio
description: 科研问题驱动检索的"复核工作室"——下游交付物与人工复核渲染工程技能。内置轻量确定性筛查后，把全部结果渲染成一整套人工复核交付物：ledger.csv（UTF-8-SIG 逐条台账，Excel 友好）、report.md（结构化报告）、review.html（自包含零依赖复核台，状态着色+勾选位+一键生成 overrides）、flow.svg（PRISMA 式计数流程图，纯文本生成）、manifest.json（逐件 sha256 防篡改），再由独立核验脚本重新读盘交叉核验（行数/标题/计数/哈希/契约完备），PASS 才交付。适用于有限快照文献筛查的人工复核交付、可核验渲染管线、诚实 partial 状态管理。不适用：全网实时检索、单篇精读、替冲突证据做学术裁决。
---

# e-review-studio — 下游交付物与人工复核渲染工程

**核心立场：检索结果只有被人能复核才算交付；交付物是否可信由独立回读核验决定，不由构建脚本自我声明。**

本技能的重心在**下游渲染与复核工程**：上游筛查刻意保持轻量（计分制、确定性、
可复算），重器放在"把结果变成人能勾核的一整套交付物 + 证明这套交付物内部
自洽、未被篡改"。两条命令完成一个案例，模型判断集中在一处（review.html 里
勾核 borderline 与夹具记录）。

## 运行契约（平台环境）

- 输入：`/input/case.json`（含 `case_id`、`research_question`、`output_contract`）、
  `/input/task.md`、快照导出文件（JSON/JSONL/CSV/TSV，以实际内容为准）。
- 中间产物：`/app/work`（筛查条款、overrides、渲染预览 PNG）；
  最终交付：`/app/output`（五件交付物 + result.json + export-check.json）。
- `result.json` 必含 `case_id` 与 `output_contract` 列出的**每一个**字段
  （动态读取契约，禁止硬编码字段名）；填不了的字段留空容器并在
  `uncertainty`/`field_notes` 说明原因（诚实 partial）。外加 `status`
  （complete/partial/blocked 三值）、`sources`、`uncertainty`。
- 本技能目录记为 `SKILL_DIR`（通常 `/skills/weekly-skill`）；非平台环境换成实际路径。
- 仅 Python 3 标准库（≥3.8），零网络。**预算纪律**：两条命令约 30 秒跑完；
  blocked 时交付物照样生成（空台账 + n=0 流程图），任何中断都有可交付的
  诚实结果。

## 标准流程（两条命令 + 一次可选人工勾核）

```bash
# 1) 构建复核交付物：轻量筛查（年份窗 + 计分制术语命中，逻辑自写从简）
#    → ledger.csv / report.md / review.html / flow.svg / manifest.json / result.json
python3 SKILL_DIR/scripts/build_review.py \
    --case /input/case.json --input-dir /input --work /app/work --out /app/output

# 2) 独立回读交叉核验：不过不交付（PASS exit 0；FAIL exit 1 并逐项指明）
python3 SKILL_DIR/scripts/check_exports.py \
    --case /input/case.json --out /app/output
```

**可选人工勾核（唯一需要判断的环节）**：浏览器打开 `/app/output/review.html`，
逐条目检"待复核"行与夹具行，勾选需翻转的记录，点按钮生成 JSON，保存为
`/app/work/overrides.json`（把 note 改成具体理由），然后带
`--overrides /app/work/overrides.json` 重跑上面两步。详见
`references/review-workflow.md`。判不准就保持 borderline 并写进
uncertainty——**不确定是合法结果，臆造不是**。

## 交付物清单

| 路径 | 内容 |
|-|-|
| `/app/output/ledger.csv` | 逐条台账（UTF-8-SIG）：rid/处置/理由/标题/命中词/来源，人工翻转标 `✓人工` |
| `/app/output/report.md` | 概要/筛查条款/候选/排除理由分布/清单核验/不确定性/交付物哈希 |
| `/app/output/review.html` | 自包含复核台：状态着色、勾选位、overrides 生成器，零外部依赖可离线打开 |
| `/app/output/flow.svg` | PRISMA 式计数流程图（纯文本生成），六 stage 计数均可文本回核 |
| `/app/output/manifest.json` | 5 件交付物的 sha256 与字节数（防篡改锚点） |
| `/app/output/result.json` | 按契约装配（含 deliverables 哈希、status/sources/uncertainty/field_notes） |
| `/app/output/export-check.json` | 核验报告 X1–X6（第三方可复算） |
| `/app/work/` | screening_criteria.json、overrides.json、渲染预览 PNG（如有） |

## 渲染预览（目检渲染产物）

交付物是给人看的，渲染效果必须目检一次：

- **平台环境**：有 browser-automation / office-renderer 工具，把
  `review.html` 与 `flow.svg` 渲染成 PNG 目检（状态着色是否生效、流程图
  计数与布局是否错位），PNG 放 `/app/work`，**不进交付物**。
- **有本机浏览器/rsvg 时**（非平台验证）：

  ```bash
  # macOS Chrome headless（如有）
  "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --headless \
      --disable-gpu --hide-scrollbars --window-size=1280,1800 \
      --screenshot=/app/work/review.png file:///app/output/review.html
  # rsvg-convert（如有）
  rsvg-convert /app/output/flow.svg -o /app/work/flow.png
  ```

- **都没有时**：如实说明"本环境无渲染工具"，以 SVG/HTML 原样交付——二者都是
  文本格式，check_exports.py 的 X4/X5 已做文本级结构核验，目检是加分项
  而非前提。禁止声称"已目检"而未目检。

## 交叉核验项（check_exports.py，详见 references/deliverable-formats.md）

X1 manifest 登记全部 5 件；X2 逐件 sha256/字节回核；X3 CSV 行数 ==
screening_log 条数；X4 HTML 含全部纳入标题；X5 SVG 六 stage 计数与台账
分布一致（identified = duplicates + screened = duplicates + included +
borderline + excluded）；X6 result.json 契约完备、状态诚实。**手工编辑任何
交付物必然触发 X2/X3/X4/X5 之一**——修正永远发生在输入或 overrides 层。

## 异常处理（诚实状态机）

- case.json 缺失/损坏：照常生成全部交付物，`status=blocked`，exit=2，
  uncertainty 指明缺什么。
- 快照零记录：`status=blocked`，exit=2；空台账 + 全零流程图照样交付，不补造文献。
- 某文件解析失败：记入 uncertainty，其余文件继续；不静默丢弃。
- 筛查后零纳入：flow.svg 正确渲染 included n=0，result.json 写明
  "零纳入，不放宽条款、不补造文献"，status=partial。
- 无署名清单：清单核验标 `no_reference_list` 并写入 uncertainty。
- 夹具标记（synthetic_duplicate / conflict_opinion 等）：原样登记进台账
  （HTML 红色"夹具"徽标），冲突意见只登记为争议证据并提示人工，**不做学术裁决**。
- overrides 缺失/损坏：忽略并在 uncertainty 声明，不静默生效。

## 最小调用示例（合成示例，非正式案例结果）

`examples/minimal/` 内含合成的 case.json（9 契约字段）、8 条合成快照记录
（含 1 条夹具合成重复、1 条冲突意见夹具）与 3 篇合成署名清单。实测输出：

```
build_review.py → {"records": 8, "included": 4, "borderline": 1,
                   "excluded": 2, "duplicates": 1, "status": "partial"}   (exit 0)
check_exports.py → {"verdict": "PASS", "failed": []}                     (exit 0)
```

partial 的三项保留（如实写入 uncertainty）：冲突意见夹具 R08 已登记待人工、
清单文献 AP-3 在快照中 missing、1 条 borderline 待勾核。flow.svg 计数
8 → 7 → 4+1+2，review.html 已用 Chrome headless 渲染目检通过。完整产物见
`examples/minimal/expected/`（csv/md/html/svg/json 全是文本，真实运行生成）。

## 复用与维护

- 换领域：build_review.py 顶部 `LEXICON` 是声明式词表，按领域增删即可；
  计分阈值与文献类型排除表在同文件顶部区域，单一事实来源。
- 换契约：无需改代码——契约字段全部从 case.json 动态读取。
- 换版式：review.html / flow.svg 的渲染函数集中在 build_review.py 第 4 节，
  改样式不动筛查逻辑；check_exports.py 只依赖格式约定
  （references/deliverable-formats.md），与渲染细节解耦。
- 版本：v1.0（2026-11，Python ≥3.8，stdlib only）。
