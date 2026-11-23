---
name: evidence-anchor
description: 面向科研阅读的证据绑定与原文锚定技能。先把源材料建成页/行/偏移三级索引，再让每条断言的逐字引文通过机器复定位，锚点由脚本算出而非手写，漂移、歧义、找不到即拦截。适用于 Nanopublication 的证据绑定、引文核验、页码图表定位。不适用：无原文材料的纯知识问答、图像像素测量。
---

# evidence-anchor — 证据锚定工程：引文必须机器复定位

**核心立场：锚点是算出来的，不是写出来的。任何一条证据都要能被第三方按记录回到原文。**

本技能的重心在**证据绑定**环节：断言内容（拆解、关系、限定）按通用契约完成，但每条
断言的交付以引文复定位成功为前提。全部脚本仅用 Python 3.9+ 标准库；PDF 解析调用
环境已有的 `pdftotext` 或 PyMuPDF，不安装新依赖。

## 运行契约（平台评测环境）

1. 先读 `/input/case.json`、`/input/task.md` 与 `environment/resources.yaml`（如存在），
   记录 `case_id`、任务边界、`output_contract` 字段。**任务 schema 优先于本技能示例**。
2. 工作区 `/app/work`，交付区 `/app/output`。`result.json` 含原 `case_id` 与
   `output_contract` 全部字段；断言、证据（引文+位置）、来源、置信度依据、状态、
   不确定项逐一落齐。
3. 预算 64 次模型请求 / 900 秒：**先建索引并写 result.json 草稿（诚实 partial），
   再逐条补断言**；锚定脚本不耗模型请求。
4. 本技能目录记为 `SKILL_DIR`（通常 `/skills/weekly-skill`）；脚本用
   `python3 SKILL_DIR/scripts/...` 调用，全部使用绝对路径。

## 工作流（Agent 逐步执行）

### 第 1 步：把源材料建成可复定位的索引

```
python3 SKILL_DIR/scripts/index_source.py \
  --input /input/<真实材料文件> --source-id SRC1 --out /app/work/src1-index.json
```

- PDF：`pdftotext -layout` 逐页提取（缺页/失败时回退 PyMuPDF）；扫描件无文本层按
  「异常处理」处理。TXT/MD 直接索引，`\f` 分页。
- 索引记录 `sha256`、页数、每页每行的原文与字符偏移；**原文不改写**，匹配时才归一化。
- 多文件/多版本各自建索引、各自 source-id；文件名相同也必须区分。

### 第 2 步：读材料并起草断言

按 task.md 覆盖所需区域（全文级任务覆盖结果/方法/结论/局限）。断言拆解为可独立判真
的原子句，保留条件与模态限定；主体解析代词。每条断言带 `evidence.quote`：从索引中
**复制**（不是复述）的最小充分原文片段，原语言、含数值与限定。

### 第 3 步：锚点复定位（交付门禁）

```
python3 SKILL_DIR/scripts/verify_anchors.py \
  --source /app/work/src1-index.json \
  --claims /app/work/claims.jsonl \
  --out /app/work/anchor-report.json
```

脚本对每条引文重新定位，输出物理页、行区间、字符偏移与多候选歧义；跨行连字符
（`inher-\nently`）自动做去连字符匹配并在 `change_records` 留痕。判定：

- `verified`：唯一匹配 → 锚点写回断言（以脚本输出为准，覆盖手写位置）；
- `ambiguous`：多处匹配 → 用更长引文窗口或加 `--page` 限定后重跑，不得取第一个凑数；
- `not_found`：引文并非逐字（改写/翻译/拼接）→ 修复引文或删除断言；
  引文不存在却声称存在是交付级错误。

证据定位规则（最小充分、表格/图、直接 vs 间接）见
[references/evidence-rules.md](references/evidence-rules.md)；索引与报告 JSON 结构见
[references/anchor-format.md](references/anchor-format.md)。

### 第 4 步：交付与状态

- 把 verified 锚点并入 `/app/output/result.json` 各断言的 evidence 字段（按契约命名）。
- `anchor-report.json` 复制到 `/app/output/`（或按契约并入 result.json），作为可复核记录。
- 状态：全部请求区域覆盖且全部断言 verified → `success`；存在 ambiguous/not_found 未决、
  部分区域无文本层、材料冲突未裁定 → `partial` 并指明缺口；材料不可得 → `blocked`。

## 异常处理

| 情形 | 处置 |
|-|-|
| 扫描件无文本层 | 尝试环境 OCR；仍失败则标明受阻页码区间，交付已索引部分，状态 `partial` |
| 双栏交错/乱序 | 换 PyMuPDF 按块提取或渲染该页目检；引用保持忠实片段，不拼接修复 |
| 引文跨页 | 拆为同页两个片段并各自锚定，evidence.fragments 记录顺序 |
| 表格证据 | 转录单元格+行列表头+脚注为 faithful transcription，锚到表所在页 |
| 图证据 | 只写图号+图注定位；读不出的数值记入不确定项 |
| 断言找不到支撑 | 不作为事实交付；记入未决项并写明检索范围 |

## 本地最小示例（合成）

`examples/minimal/`：合成文本 → 索引 → 3 条断言锚定（含 1 条歧义演示）。
`examples/twenty_claims/`：同一合成来源的 20 条断言批量锚定。**均为合成示例，非正式
案例结果。** 运行方式见各目录 README 与 `expected/`（本机真实运行产物）。

## 边界与限制

- 复定位证明「引文逐字且位置正确」，不证明「引文支持断言」；语义忠实仍须对照原文，
  歧义与漂移记录全部保留供复核。
- 连字符修复只用于定位，交付的引文仍保留原文形态，修复行为写入 change_records。
- 本技能不做断言粒度判定与跨来源去重；关系/字段语义按任务契约适配。
