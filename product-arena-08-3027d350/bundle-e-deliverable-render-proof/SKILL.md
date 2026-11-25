---
name: deliverable-render-proof
description: >-
  在任何 PDF 解析步骤产出"带锚点的类型化块"（page/column/bbox/kind: heading|body|caption|
  equation|reference|header|footer|unresolved）之后触发。本 Skill 负责把解析结果工程化为可
  人工检查的交付物：带内联锚点标签的阅读版 Markdown、完全自包含（内联 CSS、零外部资源、零 JS
  依赖）的 standalone HTML 预览（页面导航侧栏、逐块源锚点、页眉页脚置灰、未解析块红框高亮、公式/
  图注专属样式）、anchor_map.json 锚点回溯表，以及 render-QC 对账（块数进==块数出、每个输入锚点
  在交付物中恰好出现一次、零静默丢失，任何丢失都使 status 变为 failed/partial，绝不静默通过）。
  超出范围：PDF 抽取本身、OCR、版面分析、科学内容解读。
---

# deliverable-render-proof — 解析后交付物渲染与对账

## 总览

```
上游解析步骤 (/app/work/blocks.jsonl)
        │  类型化+锚定块: id/page/column/bbox/kind/text
        ▼
┌──────────────────┐   anchor_map.json（锚点→page/bbox/kind，schema 错误即退出码 3）
│ scripts/         │
│ anchor_map.py    │
└────────┬─────────┘
         ▼
┌──────────────────┐   deliverable.md（每块 [[pX-bY]] 锚点，页眉页脚入附录）
│ scripts/         │   preview.html（单文件自包含：侧栏导航、data-anchor、
│ render_preview.py│    页眉页脚置灰、unresolved 红框、公式等宽、图注斜体）
└────────┬─────────┘
         ▼
┌──────────────────┐   render_qc.json（pass|fail：缺失/多余/重复锚点清单）
│ scripts/         │   result.json（case_id 回传 + output_contract 全字段 +
│ render_qc.py     │    status success|partial|failed，失败附 handoff，绝不静默）
└──────────────────┘
```

核心理念：**人打开来检查解析质量的那份东西，本身必须是被工程化并对账过的**。渲染即回归测试——
如果解析进来 N 个块，交付物里必须能数出 N 个锚点，多一个少一个都算失败。

## 运行契约

- 输入：`/input/case.json`（含 `case_id` 与 `output_contract` 字段清单）+ `/input/task.md`；
  上游解析产物 `blocks.jsonl` 位于 `/app/work`（schema 见 `references/block-schema.md`）。
- 输出：全部交付物写入 `/app/output`。
- `result.json` **必须**包含原始 `case_id` 以及 `output_contract` 中的**每一个**字段；
  某字段对应产物不存在时，填 `{"value": null, "explanation": "..."}`，绝不编造路径。
- 诚实状态：QC 对账失败 ⇒ `status: "failed"` 并附 `handoff` 说明；有警告（如 bbox=null
  仍渲染）⇒ 警告写入 `uncertainty` 字段；绝不把丢失静默成 success。
- 预算：64 次请求 / 900 秒。**脚本优先**——三个脚本一条管道跑完，不要逐块手工渲染。
- 仅使用 Python 3 标准库；输出确定性（无时间戳、无随机数），同输入必得同输出。

## 操作步骤

```bash
# 1. 校验 schema 并分配稳定锚点 p{page}-b{seq}；schema 非法时退出码 3 并给出逐行原因
python3 scripts/anchor_map.py --blocks /app/work/blocks.jsonl \
    --out /app/output/anchor_map.json

# 2. 渲染阅读版 Markdown 与自包含 HTML 预览
python3 scripts/render_preview.py --blocks /app/work/blocks.jsonl \
    --anchor-map /app/output/anchor_map.json \
    --out-md /app/output/deliverable.md --out-html /app/output/preview.html

# 3. 对账门：把两份交付物"解析回来"，与输入逐锚点核对，产出 render_qc.json 与 result.json
python3 scripts/render_qc.py --blocks /app/work/blocks.jsonl \
    --anchor-map /app/output/anchor_map.json \
    --md /app/output/deliverable.md --html /app/output/preview.html \
    --case /input/case.json \
    --out-qc /app/output/render_qc.json --out-result /app/output/result.json \
    --outdir /app/output
```

退出码：`0` 正常；`2` IO/用法错误；`3` schema 非法（anchor_map）或 QC 失败（render_qc）。
第 3 步返回 3 时，检查 `render_qc.json.problems`，修复上游或渲染输入后重跑，**不要**手工
编辑交付物凑通过。

## 输出物说明

| 文件 | 内容 | 保证 |
|---|---|---|
| `deliverable.md` | 阅读版 Markdown；每块前缀 `[[pX-bY]]` 锚点 + kind/page/col/bbox 元信息行；页眉页脚移入文末附录（仍带锚点）；unresolved 块保留并显式标注原因 | 每个输入块恰好出现一次 |
| `preview.html` | 单文件自包含预览：UTF-8 meta、仅内联 CSS、无 `<script>`、无任何外部 URL/字体；左侧页面导航栏；每块带 `data-anchor` 与 `title`（page/bbox/kind）；页眉页脚透明度 0.45 置灰；unresolved 红框红标；公式等宽字体；图注斜体 | 每个锚点恰好出现一次，可离线双击打开 |
| `anchor_map.json` | 锚点 → block_id/page/column/bbox/kind/字符数；附 schema_valid 与逐行 schema_errors | 覆盖全部输入块 |
| `render_qc.json` | status pass\|fail；四类计数（blocks_in / map / md / html）；每份交付物的 missing/duplicated/extra 锚点清单；warnings（bbox=null、unresolved 等）；fail 时附 handoff | 丢失必失败，绝不静默 |
| `result.json` | case_id、status、output_contract 全字段、sources、uncertainty、change_record | 契约字段一个不少 |

## 方法要点

- **为什么自包含 HTML**：审阅者必须在离线环境（无网络、无外网字体 CDN）双击即可打开；
  任何外部 `<link>`/`<script src>`/webfont 都会让"检查解析"这件事依赖不可控环境，故一律内联。
- **锚点即回归测试**：渲染管线把交付物再用正则解析回来（`[[pX-bY]]` 与 `data-anchor="..."`），
  与 anchor_map 做集合对账。这把"渲染丢块"从肉眼抽查变成确定性断言：计数不等、锚点缺失、
  锚点重复、出现未知锚点，任一成立即 fail。
- **页眉页脚不丢弃，只降级**：header/footer 移入附录并置灰，锚点保留——对账仍要求它们出现，
  避免"顺手丢了页眉"成为静默丢失的灰色地带。
- **稳定锚点命名**：`p{page}-b{seq}`，seq 为该页内按输入顺序的序号；与文件位置无关、
  重跑结果一致，便于跨轮 diff。
- 详见 `references/method.md`（渲染契约与对账逻辑）与 `references/block-schema.md`（输入 schema）。

## 异常与限制

| 情况 | 行为 |
|---|---|
| 块缺 `bbox`（null） | 照常渲染，meta/title 显示 `bbox: n/a` 并加黄色徽标；QC 记入 warnings，**不**崩溃、**不**丢弃 |
| 块缺 `column` | 容忍，按 0 处理 |
| 超大文档（数千块） | HTML 为单文件线性流；建议按章节/页分批渲染多个 preview 文件，再逐文件跑 render_qc，最后汇总计数 |
| `unresolved` 块 | 一律保留：Markdown 斜体标注原因，HTML 红框高亮；**禁止**删除或"留空跳过" |
| 输入非 UTF-8 | anchor_map.py 拒绝处理，退出码 3 |
| schema 非法（缺 id/page/kind 错误等） | anchor_map.py 逐行列出原因，退出码 3；anchor_map.json 中 schema_valid=false |
| QC 失败 | result.json status=failed，附 handoff；存在但未通过的产物标注"do not consume" |
| 文本含 HTML 特殊字符 | preview.html 全部转义；Markdown 原样保留 |

## 最小示例（合成数据）

`examples/minimal/` 内含一份**完全合成**的两页"论文"块（20 个块，覆盖全部 8 种 kind，
含 2 个 unresolved、1 个 bbox=null 的 body 块）以及真实跑出的全部输出。

```bash
cd examples/minimal
python3 ../../scripts/anchor_map.py   --blocks inputs/blocks.jsonl --out outputs/anchor_map.json
python3 ../../scripts/render_preview.py --blocks inputs/blocks.jsonl --anchor-map outputs/anchor_map.json \
    --out-md outputs/deliverable.md --out-html outputs/preview.html
python3 ../../scripts/render_qc.py --blocks inputs/blocks.jsonl --anchor-map outputs/anchor_map.json \
    --md outputs/deliverable.md --html outputs/preview.html --case inputs/case.json \
    --out-qc outputs/render_qc.json --out-result outputs/result.json --outdir .
```

预期：QC `pass`，20 blocks in == 20 anchors out（md 与 html 各 20），warnings 含
"p1-b6 bbox=null" 与 2 个 unresolved 块提示。用浏览器打开 `outputs/preview.html` 检查
侧栏、置灰页眉页脚、红框 unresolved 与等宽公式。

> 声明：示例中所有文本、作者、期刊、引用均为编造，仅用于演示管线，不对应任何真实文献。

另见 `examples/qc-fail/`：同一份输入，但 deliverable.md 被故意删掉一个锚点（模拟静默丢块），
真实运行 `render_qc.py` 得到 `status=fail`、退出码 3、`result.json.status=failed` 且附 handoff
——用于核对"对账失败绝不静默通过"的行为。
