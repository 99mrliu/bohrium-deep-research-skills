---
name: structure-argument-map
description: 论文结构完整性与论证链制图审查——当需要检查稿件 IMRaD 小节齐备性、摘要↔结论对应、引言问题是否被结论回答、因果/相关混淆、结论外推或无据结论时使用；不做事实真伪核验、文献逐条验证、统计方法学深查与查重（仅按最低检查点轮查登记）。
---

# structure-argument-map：结构完整性与论证链制图审查

## 核心思想

先把稿件制成**两张机器可核对的图**，再在图上定位问题，而不是直接写评语：

1. **结构图**（`scripts/doc_map.py`）：标题层级树 + IMRaD 要素齐备性矩阵
   （present/absent/ambiguous）+ 摘要↔结论句子级对齐表 + 引言问题↔结论回答配对。
2. **论证链**（`scripts/chain_lint.py`）：研究问题→假设→方法→结果→结论→外推边界
   六环逐环登记（每环必须有原文引用+定位），并对因果混淆/无据结论/答非所问做
   机械候选扫描。

所有 finding 必须引用**两侧原文**（如方法节设计句 + 结论节主张句）并给定位
（`角色#s序号`）。机械扫描结果一律 `candidate=true`，由 Agent 对照
`references/argument_rubric.md` 逐条转正或驳回，防误报。

## 适用边界

- 深查面：**整体质量 / 结构完整性与论证链**。
- 事实核验、引用支持、方法设计、统计报告、学术规范五个分面只按
  `references/facet_coverage.md` 的最低检查点轮查登记，不展开深查。
- 不适用：数据真伪鉴定、文献真实性/DOI 验证、统计检验方法学复核、查重、
  英文以外的多语种混排稿件（启发式按中英文设计，其他语言降级为 partial）。

## 运行时契约

- 评测安装路径 `/skills/weekly-skill`；脚本以
  `python3 /skills/weekly-skill/scripts/<脚本>` 调用，仅依赖 Python 3 标准库；
  PDF 抽取尝试 `pdftotext`（`shutil.which` 检测，没有则在 result.json 如实记录
  extract_error 并降级 partial）。
- 输入 `/input/case.json` 与 `/input/task.md`，稿件在 `/input` 下
  （PDF/DOCX/MD/TXT/TeX）。case.json schema 宽容处理：output_contract 为字段名
  列表或 dict 均可，缺失回退默认字段集
  `["case_id","status","review_report","findings","sources","uncertainty","change_log"]`
  并在 uncertainty 说明。
- 工作目录 `/app/work`；最终成果 `/app/output/result.json` +
  `/app/output/review_report.md`。
- **第一次脚本调用（doc_map.py）即落盘保底 partial result.json**，之后增量改进；
  所有产出原子写（临时文件 + os.replace）。
- 文本统一 `utf-8, errors=replace`；禁止编造文献、页码、DOI、结论、分数；
  未确认条目一律 `pending_review`。

## 分步工作流

```bash
# 第 1 步：结构制图（同时先落盘保底 partial result.json）
python3 /skills/weekly-skill/scripts/doc_map.py \
  --input /input --work /app/work --output /app/output
# 产物：/app/work/doc_map.json、/app/work/manuscript.txt、/app/output/result.json(保底)

# 第 2 步：生成论证链登记模板（只跑一次；重复运行会覆盖已填写内容）
python3 /skills/weekly-skill/scripts/chain_lint.py scaffold --work /app/work
# 产物：/app/work/chain_register.json（6 环 + 5 条链边，初始全部 pending_review）

# 第 3 步（Agent 手工）：读 doc_map.json 与 manuscript.txt，
# 逐环填写 chain_register.json 的 claim/quote/locator：
#   status=confirmed（稿件中确有该环）或 broken（该环在稿件中缺失，quote 留空）；
# 同时核对 5 条链边 consistent: true/false/null + note。
# 判据见 references/argument_rubric.md 第 1、4 节。

# 第 4 步：机械候选扫描（可重复运行，候选编号确定性稳定）
python3 /skills/weekly-skill/scripts/chain_lint.py lint --work /app/work
# 产物：/app/work/lint_candidates.json（C1/C2 因果混淆、X1 无据数值、Q1 未答问题）

# 第 5 步（Agent 手工）：逐条核对候选（对照 references/argument_rubric.md 的
# 防误报条款），写 /app/work/lint_dispositions.json：
# {"dispositions":[{"candidate_id":"CAND-001","verdict":"confirmed|rejected","note":"核对两侧原文……"}]}

# 第 6 步：汇总产出（可重复运行，finding 编号幂等稳定）
python3 /skills/weekly-skill/scripts/build_result.py \
  --input /input --work /app/work --output /app/output
# 产物：/app/output/result.json + /app/output/review_report.md
```

## 输出 schema

`result.json` 必含 output_contract 全部字段（默认七字段），另附：

- `findings[]`：`{id(SR-结构/AC-论证链), severity(major/minor), facet, type, title,
  description, evidence{quote_a,locator_a,quote_b,locator_b}, status(confirmed/pending_review)}`
- `sources[]`：稿件文件 + SHA-256 + 抽取方式/错误
- `facet_coverage`：六分面状态（checked_clean/issues_found/partially_checked/unable_to_check）
- `counts`：total/confirmed/pending_review
- `status`：completed（三件套齐全且抽取成功）/ partial（任一缺失，uncertainty 说明限度）

## 异常处置

| 异常 | 行为 |
|---|---|
| /input 无稿件 | doc_map.py 退出码 2，保底 result.json 记 uncertainty |
| PDF 无 pdftotext | 退出码 3，extract_error 如实记录，状态 partial |
| 缺 chain_register.json 或 lint_candidates.json | build_result 仍产出，status=partial，对应分面降级 |
| 候选未处置 | 保持 pending_review 进 findings，uncertainty 提示待复核，不凭空下结论 |
| 无标题纯文本稿件 | role_matrix 全 absent，uncertainty 标 unable_to_check，不臆判结构完整 |

## 文件清单

- `scripts/doc_map.py`：文本抽取 + 标题解析 + 角色矩阵 + 对齐表（保底 result.json）
- `scripts/chain_lint.py`：`scaffold` 链登记模板 / `lint` 机械候选扫描
- `scripts/build_result.py`：汇总 result.json + review_report.md（原子写、幂等编号）
- `references/structure_rubric.md`：结构齐备判据与"看着完整但关键缺位"情形
- `references/argument_rubric.md`：因果/外推/缺环判据与防误报、处置格式
- `references/facet_coverage.md`：六分面最低检查点与状态值
- `examples/`：合成示例（植入 4 处已知问题）及真实跑出的输出拷贝
