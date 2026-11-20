---
name: dual-track-topic-query-strategist
description: >-
  当任务给出一个技术主题/科研问题，需要检索并筛选相关专利与非专利技术文献（论文等），
  且要求输出可解释检索式、专利/NPL 双轨筛选逻辑、逐条排序依据、PRISMA 式筛选留痕与遗漏说明时使用。
  兼容 Harbor 运行时契约（输入 /input/case.json + /input/task.md，材料可能在 /input、/app/work 或当前目录，
  工作目录 /app/work，最终结果与可编辑产物写入 /app/output，result.json 必须含 case_id 并镜像
  output_contract 全部字段）。号码类精确查询与权利要求/法律状态类任务按正文"案例路由"一节降级使用。
---

# 技术主题检索式构造与专利/非专利文献双轨筛选

## 用途与适用条件

把"技术主题检索"做成可解释、可复跑的检索式工程，而不是把主题词丢进通用搜索：

研究问题 → 概念块分解（每个词项带 intent 依据）→ 分面组合（关键词 + IPC/CPC + 申请人 + 年份）
→ 专利轨道与非专利文献（NPL）轨道采用**不同**检索逻辑 → 脚本在本地语料上确定性执行
→ PRISMA 式筛选留痕 + 逐条排序依据 + 遗漏说明。

适用：主题类检索筛选案例。降级适用（见"案例路由"）：号码查询、权利要求摘录、法律状态类案例。

## 运行时契约与预算纪律（评测环境）

- 原始输入：`/input/case.json`（含 case_id、output_contract）与 `/input/task.md`。
- 材料按题目提供，可能在 `/input`、`/app/work` 或当前目录；**PDF 是原始文件（无预抽取答案层），
  必须用 pdftotext/渲染/OCR 读真实内容，不得按文件名标签臆测**。
- 工作目录 `/app/work`；最终结果与可编辑产物放 `/app/output`。`result.json` 必须含 `case_id`
  并镜像 `output_contract` 的全部字段（本 Skill 的 scaffold_result.py 自动镜像），
  `status` 诚实取值 ok/partial/failed，附 sources、uncertainty 与 change_log；部分完成必须说明界限。
- 预算：64 次模型请求 / 900 秒 / 每响应 16384 tokens。**重活全部交给脚本**（发现、匹配、去重、
  计数、打分都是确定性的）；模型只做三件事：概念块判断与 intent 写作、边界案例的纳排判断、
  最终文字写作。先跑通全管线、尽早保存诚实的部分 result.json，再迭代改进检索式。
- 语料特点（本挑战常见情形，规则均已兼容，但**绝不预置任何真实案例答案**）：
  有限专利记录语料 + 传真原件 PDF + 真实对比论文；查询分号码查询与主题查询两类；
  权利要求可能有来源定位版本；当前官方法律状态未知（一律如实标注"未核验"）；
  观察到的链接不构成完整同族（同族合并只信语料内字段）；WO 文献可能 OCR 合并且边界被保留
  （合并 PDF 抽取成 txt 后按边界标记拆分成多条记录再检索，见 rules/dual_track_logic.md）。

## 输入

- `/input/case.json`：case_id、任务描述、output_contract（结果字段契约）。
- `/input/task.md`：任务叙述（主题描述、交付要求）。
- 语料文件：`.json/.jsonl/.csv/.tsv/.txt/.md`；PDF 先用
  `pdftotext -layout input.pdf /app/work/corpus/xxx.txt` 转文本后纳入语料目录。
- 你编写的检索式 spec JSON（概念块 + intent + 分面），格式见 rules/topic_query_construction.md。

## 调用方式（确切命令序列）

以下假设 Skill 安装在 `/skills/weekly-skill`；若路径不同，替换前缀即可。所有脚本仅依赖标准库。

```bash
mkdir -p /app/work/corpus /app/output

# 0) PDF 材料转文本（含传真原件；扫描件先渲染再 OCR），txt 放入语料目录
pdftotext -layout /input/xxx.pdf /app/work/corpus/xxx.txt

# 1) 可选：生成草稿 spec（intent 为空，不会通过校验；真正有价值的概念块分解由你完成）
python3 /skills/weekly-skill/scripts/build_query.py draft \
    --case /input/case.json --task /input/task.md --out /app/work/query_spec_draft.json

# 2) 你按 rules/topic_query_construction.md 写好 /app/work/query_spec.json 后：校验并生成检索式
python3 /skills/weekly-skill/scripts/build_query.py build \
    --spec /app/work/query_spec.json \
    --out /app/work/query.json --expr-out /app/work/query_boolean.txt
#    违反 R1-R9 时 exit 2 并逐条打印违规，修正后重跑。

# 3) 在本地语料上确定性执行检索式（双轨 + 去重 + 定位 + 词项明细）
python3 /skills/weekly-skill/scripts/search_corpus.py \
    --query /app/work/query.json \
    --corpus /input /app/work --out /app/work/hits.json

# 4) PRISMA 式筛选 + 排序 + 遗漏说明（自报计数可用 --expect 比对，不一致 exit 3）
python3 /skills/weekly-skill/scripts/screen_rank.py \
    --query /app/work/query.json --hits /app/work/hits.json \
    --out /app/work/screening.json

# 5) 生成 result.json 骨架（镜像 output_contract 全部字段，status 自动诚实判定）
python3 /skills/weekly-skill/scripts/scaffold_result.py \
    --case /input/case.json --query /app/work/query.json \
    --hits /app/work/hits.json --screening /app/work/screening.json \
    --out /app/output/result.json

# 6) 自查（任何时候都可跑，全绿才交付）
python3 /skills/weekly-skill/scripts/selfcheck.py
```

## 输出字段（/app/output/result.json）

| 字段 | 内容 |
| --- | --- |
| case_id | 取自 case.json |
| status | ok / partial / failed（诚实；语料为空→failed，零命中或有未判定记录→partial） |
| query | 主题、版本、mode、概念块（含每词 intent）、人读布尔表达式 |
| hits | 分轨命中：patent / npl，每条带 file#loc 定位、identifier、命中的块与字段、同族重复条目 |
| screening | PRISMA 计数（identified/duplicates_removed/screened/excluded/included）+ 逐条决定（理由代码+依据）+ 查准阈值 |
| ranking | 每条候选 score 与分解（block_coverage/field_strength/class_overlap/year_proximity） |
| omissions | 零命中概念块、无法判定记录、被跳过文件、来源边界说明 |
| sources | 实际读取的语料文件清单 |
| uncertainty | 未核验项（法律状态、外部库未检索、契约暂缺字段等） |
| change_log | 变更记录 |

字段口径详见 templates/result_fields.md；检索式迭代留痕用 templates/query_log.md。

## 关键方法（规则文件）

- rules/topic_query_construction.md — 概念块方法、intent 纪律、查全/查准迭代协议与停止判据、R1-R9 校验语义。
- rules/dual_track_logic.md — 专利 vs NPL 的检索逻辑差异：分类号优先 vs 关键词优先、族去重 vs DOI 去重、kind code 语义、轨道判定规则、OCR 合并文献处理。
- rules/screening_protocol.md — 纳排理由代码表（E1-E7 / I1-I4）、PRISMA 计数口径、排序特征定义与阈值规则。

## 案例路由（重要）

1. **主题类案例** → 走上方全管线（draft→build→search→screen→scaffold）。
2. **号码类案例** → 降级为单块检索式：spec 中 `"mode": "number_lookup"`，恰好 1 个概念块，
   词项为公开号/申请号（仍需写 intent，例如"按公开号定位文献"）。执行器做规范化精确匹配，
   kind code 有无互相容忍（查 "XX1000002" 可命中 "XX1000002B1"）。
   **必须在 uncertainty 中标注方法局限**：号码查询不做主题相关性判断，不产出排序与筛选语义，
   ranking/screening 仅反映精确命中事实。
3. **权利要求 / 法律状态类案例** → 只做命中事实摘录：用 search_corpus 定位到具体记录与字段
   （file#loc、claims 字段原文片段），逐条引用；法律状态、权利要求有效性、当前权利人
   **一律标注"未核验"**写入 uncertainty，不得给出确定结论。权利要求有来源定位版本时，
   摘录必须保留定位信息（文件 + JSON 路径/行号）。

## 异常处理表

| 异常 | 处理 |
| --- | --- |
| 检索无命中 | 按 rules/topic_query_construction.md 查全协议放宽一次（补同义词/去掉过窄分面），重跑 2-3；仍无命中则 status=partial，在 omissions 写明"语料内零命中"及已尝试的放宽，不得编造命中 |
| 命中过多 | 提高查准阈值 `--min-blocks N`，或收窄 year_range/加申请人分面；把阈值与理由记入 query_log |
| 语料无分类字段 | classification 分面自动失效，仅靠关键词块；在 uncertainty 标注"分类号检索不可用，召回偏关键词轨道" |
| 轨道无法判定 | 记录进 hits.json 的 unclassified 清单并原样列入 omissions；不得强行归入任一轨道 |
| 零结果概念块 | search 输出 zero_hit_blocks；screen 默认阈值自动只统计"语料中至少命中过一次的块"，避免误杀；该块必须在 omissions 与最终文字中说明（查全性受限） |
| PRISMA 自报不一致 | screen_rank exit 3；以脚本重算为准，修正自报数 |
| PDF 无法抽取文本 | 用渲染 + OCR；仍失败则该文件列入 skipped_files 与 omissions，status 至多 partial |
| OCR 合并的 WO 文献 | 按保留的边界标记拆成多个 txt 再入语料；无法拆分则按单条记录处理并在 uncertainty 说明 |

## 自查方法

交付前按顺序确认：
1. `python3 scripts/selfcheck.py` 输出 `SELF-CHECK PASSED`（exit 0）。
2. result.json 含 case_id，output_contract 全部字段存在，`status` 与实际情况一致。
3. 每条命中有 file#loc 定位与匹配词项明细；每条排除有 E 码理由；每条纳入有 I 码依据。
4. omissions 非空且诚实（零命中块、未覆盖来源、语料边界）；uncertainty 含"法律状态未核验"。
5. 全文不含任何预置的真实案例答案；示例均来自 examples/fixtures（虚构）。

## 最小调用示例

```bash
# 用内置虚构夹具演示全链（产物在 /tmp，illustrative only）
cd /tmp && mkdir -p demo/corpus
cp /skills/weekly-skill/examples/fixtures/records_patents.json \
   /skills/weekly-skill/examples/fixtures/records_npl.jsonl \
   /skills/weekly-skill/examples/fixtures/notes_unclassified.txt demo/corpus/
python3 /skills/weekly-skill/scripts/build_query.py build \
    --spec /skills/weekly-skill/examples/fixtures/query_spec_valid.json --out demo/query.json
python3 /skills/weekly-skill/scripts/search_corpus.py --query demo/query.json \
    --corpus demo/corpus --out demo/hits.json
python3 /skills/weekly-skill/scripts/screen_rank.py --query demo/query.json \
    --hits demo/hits.json --out demo/screening.json
python3 /skills/weekly-skill/scripts/scaffold_result.py \
    --case /skills/weekly-skill/examples/fixtures/case_illustrative.json \
    --query demo/query.json --hits demo/hits.json \
    --screening demo/screening.json --out demo/result.json
```

预期：5 条记录 → 轨道 2/2/1 → 同族去重合并 1 条 → 命中 1 专利 + 1 论文 →
查准阶段纳入专利、排除论文（E7）→ result.json status=partial（存在无法判定记录）。
逐步解读见 examples/example_walkthrough.md。
