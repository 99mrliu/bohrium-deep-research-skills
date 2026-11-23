---
name: bilingual-align-render
description: >
  面向长文献翻译的「分段 + 双语段落对照」工程化流程:对 PDF/TXT 源文做确定性分段(页码追踪、断词修复、页眉页脚剔除),
  为每个源段落分配稳定 seg_id,再将译文段落与源段落逐一锚定对齐(锚点 = 数字/引用/图表标记),
  渲染左右对照的双语 HTML/Markdown,保证译文段落 100% 可回溯到源段落及其页码。
  Use this skill when you must translate a long document and prove that no paragraph was lost, duplicated, or reordered.
---

# bilingual-align-render:长文分段与双语段落对照渲染

## 目的(Purpose)

翻译长文献(论文、报告)时,最常见的失败不是译错,而是**段落丢失、重复或错位**——尤其跨页、跨栏时。
本技能把「翻译」拆成可审计的工程管线:确定性分段 → 稳定段落 ID → 锚点对齐 → 双语对照渲染,
使每一段译文都能指回源段落(seg_id + 页码),任何缺口都被显式登记而不是静默跳过。

## 何时使用 / 不适用

**适用**:长文(数页以上)的翻译交付;需要逐段审校、回查原文;译文必须证明完整性(无丢段/重段/乱序)。

**不适用**:单段短文本(直接翻译即可);纯公式/纯图片文档(无文本层);不需要回溯关系的自由改写任务。

## Runtime contract

- 本技能安装在 `/skills/weekly-skill`(脚本位于 `/skills/weekly-skill/scripts/`,规则文档位于 `/skills/weekly-skill/references/`)。
- 输入:`/input/case.json`(含 `case_id` 与 `output_contract`)与 `/input/task.md`,以及随案材料——**真实论文 PDF,无预抽取答案层**;
  文本层须用 `pdftotext -layout` 自行提取(`scripts/segment_text.py` 已封装)。
- 在 `/app/work` 下工作(中间文件:提取文本、paragraphs.jsonl、译文草稿等)。
- 最终产物写入 `/app/output`,其中 **`result.json` 必须包含原始 `case_id` 以及 `output_contract` 声明的每一个字段**。
- 预算约 **64 次模型请求 / 900 秒**:请**先用 `scripts/write_result.py` 写一份部分(占位)result.json**,再就地逐步改进。
- 状态必须诚实:`success` / `partial` / `unable_to_determine` / `refused` 四选一;**绝不编造缺失内容**。

## Workflow

1. **锁定部分结果**:运行 `scripts/write_result.py --case /input/case.json --out /app/output/result.json --status partial`,
   确保即使中途超时也有一份合法 result.json 可交。
2. **提取文本并分段**:`scripts/segment_text.py --src <论文.pdf 或 .txt> --out /app/work/paragraphs.jsonl --report /app/work/seg_report.json`。
   产出每段的稳定 seg_id(P0001…)、page_start/page_end、char_count、text;报告记录断词修复、被剔除的页眉页脚与页码行。
3. **逐段翻译**:agent 按 paragraphs.jsonl 逐段翻译,**保留 seg_id 对应关系**。产出 `/app/work/target_zh.txt`:
   段落块之间空行分隔,每块对应一个源段落,**建议每块首行写 `[[P0001]]` 标签**(可选但强烈推荐——有标签即硬对齐,无歧义)。
4. **对齐校验**:`scripts/align_bilingual.py --src /app/work/paragraphs.jsonl --tgt /app/work/target_zh.txt --out /app/work/alignment.json --report /app/work/align_report.json`。
   **源段覆盖率必须为 100%,否则每个缺口都要在 coverage.missing 中显式登记**(脚本以退出码 1 阻断)。
5. **渲染对照**:`scripts/render_side_by_side.py --alignment /app/work/alignment.json --src /app/work/paragraphs.jsonl --tgt /app/work/target_zh.txt --out /app/output/bilingual.html --md /app/output/bilingual.md`,
   生成带 seg_id 锚点、状态配色、顶部导航索引的对照页,供人工检查。
6. **交付**:`/app/output` 至少包含 `result.json`、`paragraphs.jsonl`、`alignment.json`、`bilingual.html`(及 `bilingual.md`);
   用 `write_result.py` 把 status 改为 `success`(或诚实的 `partial`)并登记各产物路径。

## 产物清单(Artifacts)

| 路径 | 内容 |
| --- | --- |
| `/app/output/result.json` | case_id + output_contract 全部字段 + change_record |
| `/app/output/paragraphs.jsonl` | 源文分段(seg_id / page_start / page_end / char_count / text) |
| `/app/output/alignment.json` | 段落级对齐 + coverage 登记(见 `references/alignment_format.md`) |
| `/app/output/bilingual.html` | 双语对照表(seg_id 锚点 + 状态配色 + 顶部导航) |
| `/app/output/bilingual.md` | 同内容的两栏 Markdown 预览(前 80 字符) |

中间产物(`/app/work`):提取的纯文本、`seg_report.json`、`align_report.json`、译文草稿 `target_zh.txt`。

## 预算建议(Budget guidance)

- 分段、对齐、渲染均由脚本确定性完成,**不消耗模型请求**;
- 64 次请求中,约 80% 留给逐段翻译(每段一次或数段合并一次),其余留给:
  1 次启动(读 case/task + 写占位 result.json)、若干次缺口补译、
  1 次终检(对照 alignment.json 的 coverage 与 bilingual.html 的状态行)。
- 若预算告急:优先保证 `coverage.missing` 为空(补译缺口),
  `anchor-mismatch` / `order-swap` 可如实登记后以 `partial` 交付。

## 输出要求(Output requirements)

- 每个译文段落**必须可回溯**到源 seg_id 与页码(alignment.json 中 `tgt_ids` ↔ `src_id` 一一可查)。
- 缺失(missing-translation)/ 多余(extra-translation)/ 乱序(order-swap)/ 锚点不符(anchor-mismatch)
  **必须显式列出,绝不静默修补**。合并(merged-in-target)与拆分(split-in-target)也需标注状态。
- bilingual.html 中每个状态有独立 CSS class,人工一眼可定位问题行。

## 异常处理(Exception handling)

| 异常 | 处理 |
| --- | --- |
| 无文本层 / 扫描版 PDF | `pdftotext` 产出为空 → segment_text.py 报警告;需先 OCR(超出本技能范围),状态记 `unable_to_determine` 并说明 |
| 双栏布局串行错乱 | 使用 `pdftotext -layout` 缓解;若块序仍错,在 seg_report.json warnings 与 result.json 中显式说明,人工核对块序 |
| 公式/图表为图片 | 保留占位段(如"[Figure image]"),绝不编造公式内容;在对照页中如实呈现 |
| 参考文献段 | 正常分段与对齐,但可整段保留原文不译——仍需在 alignment 中登记,不得整段丢弃 |
| pdftotext 不存在 | segment_text.py 明确报错(诚实失败),改用 .txt 输入或安装 poppler |

## 自检清单(Self-check)

- [ ] result.json 含原始 case_id 与 output_contract 全部字段
- [ ] paragraphs.jsonl 每行 JSON 合法,seg_id 连续无跳号(P0001…PN)
- [ ] alignment.json coverage.source_paragraphs == aligned + len(missing)
- [ ] align 退出码为 0,或 missing 列表已在 result.json note 中如实说明
- [ ] bilingual.html 可离线打开,含 `id="P0001"` 锚点与状态配色
- [ ] 无任何「静默修复」:所有缺口/多余/乱序均已显式登记
