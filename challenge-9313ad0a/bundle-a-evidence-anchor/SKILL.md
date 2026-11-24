---
name: evidence-anchor
description: 面向科研材料思维导图的证据锚定与材料真实性核验：在需要依据 PDF/TXT/MD 原始材料生成思维导图、并逐字核对引文与页码、筛查杜撰引文与越界页码、产出审计报告与隔离清单时使用。
---

# evidence-anchor：科研材料思维导图的证据锚定与真实性核验

本 Skill 解决的核心问题是**上游材料真实性与证据锚定**：思维导图中的每一个事实性节点必须能够回溯到原始材料的特定文件与页码，且引文必须与原文逐字一致。本工作不提供任何预抽取的答案层；所有核验均在运行时对真实材料现场执行。

## 何时使用

适用场景：

- 依据给定科研材料（论文 PDF、实验记录、笔记等 TXT/MD）构建思维导图，且要求节点附证据定位（文件、页码、章节、逐字引文）。
- 需要对已有思维导图进行真实性审计：筛查杜撰引文（fabricated）、无证据事实（unanchored）、页码错位（mislocated）、越界页码（page_out_of_range）、标签中材料里不存在的数字（number_not_found）。
- 需要产出可复核的审计报告与隔离清单，以支撑 result.json 中的诚实状态与不确定性列表。

不适用场景：

- 无任何原始材料、仅凭模型内部知识生成思维导图的任务（本 Skill 的一切结论都锚定材料，无材料则无从锚定）。
- 需要语义级事实核查（例如判断原文结论本身是否正确）的任务；本工作仅核验"节点陈述是否忠实于所引材料"，不评判材料本身的真伪。
- 扫描件 OCR；本工作不含 OCR 能力，无文本层的 PDF 只能如实记录为不可提取。
- 需要联网检索、补全文献元数据的任务；运行环境无网络。

## 固定运行方式

运行时契约（必须严格遵守）：

1. 首先读取 `/input/case.json` 与 `/input/task.md`，确认 `case_id`、`output_contract` 要求的全部字段以及材料文件清单。
2. 一切中间产物写入 `/app/work`，最终交付物写入 `/app/output`。
3. `/app/output/result.json` 必须包含**原始 case_id** 与 `output_contract` 点名的**每一个字段**，并给出诚实的状态（success / partial / unable_to_determine / refused）、sources/evidence、不确定性列表与变更记录。
4. **尽早保存一份合法可用的 partial 版 result.json**，随后在原文件中迭代改进。
5. 绝不杜撰论文内容、数据或引文；凡无法在材料中逐字锚定的陈述，必须降级、标注或删除。

固定命令序列：

```bash
# 0. 读取任务契约
cat /input/case.json
cat /input/task.md
ls -la /input

# 1. 尽早落盘一份合法 partial 版 result.json（后续就地改进）
mkdir -p /app/work /app/output
python3 - <<'EOF'
import json
case = json.load(open("/input/case.json", encoding="utf-8"))
partial = {
    "case_id": case["case_id"],
    "status": "partial",
    "mindmap": None,
    "sources": [],
    "evidence": [],
    "uncertainties": ["审计尚未完成，当前为早期 partial 结果"],
    "change_records": ["初始化 partial result.json"],
}
with open("/app/output/result.json", "w", encoding="utf-8") as f:
    json.dump(partial, f, ensure_ascii=False, indent=2)
EOF

# 2. 材料入库与分页（/input 下的材料按实际文件名填写）
python3 /skills/weekly-skill/scripts/material_intake.py \
    --out /app/work/material \
    /input/<材料1.pdf> /input/<材料2.txt>

# 3. 构建思维导图草稿（节点附 evidence：file/page/section/quote，引文逐字摘自 pages.jsonl）
#    草稿保存为 /app/work/mindmap.json

# 4. 证据锚定审计
python3 /skills/weekly-skill/scripts/anchor_audit.py \
    --map /app/work/mindmap.json \
    --material /app/work/material/pages.jsonl \
    --report /app/output/anchor_report.json \
    --quarantine /app/output/quarantine.json
# 退出码 1 表示存在 fabricated 或 unanchored 的 fact 节点，必须修正后重跑

# 5. 修正思维导图（修复或删除 quarantine.json 所列节点），重复第 4 步直至通过；
#    随后生成最终思维导图与完整版 /app/output/result.json（含全部 output_contract 字段）
```

## 工作流程

1. **契约确认**：解析 case.json 中的 `case_id` 与 `output_contract`，列出必须交付的字段清单；解析 task.md 明确思维导图的主题与粒度要求。
2. **材料入库**：对 `/input` 下每份材料运行 material_intake.py，得到 `pages.jsonl`（逐页文本与字符偏移）与 `material_index.json`（页数、字符数、SHA-256、提取工具、警告）。核对 `unreadable` 列表并记录于不确定性。
3. **材料通读与节点抽取**：通读 pages.jsonl，按"主题—方法—结果—结论"等层次抽取节点；为每个节点判定 basis 类型（fact / summary / inference，判定规则见 references/claim-typing.md）。
4. **证据锚定**：每个 basis=fact 节点必须携带至少一条 evidence：`file`（与 pages.jsonl 中 file 字段一致的相对路径）、`page`（PDF 页码，非印刷页码）、`section`（章节名，可推断）、`quote`（从该页文本中**逐字复制**的连续子串，不得改写、增删字词或更换标点）。
5. **审计与迭代**：运行 anchor_audit.py；对 quarantine.json 所列节点执行"修正或删除"，对 mislocated 节点更正页码后重跑，直至退出码为 0 或将不可修复项如实写入不确定性。
6. **交付**：输出最终 mindmap（含证据）、anchor_report.json、quarantine.json，以及符合 output_contract 的 result.json（状态诚实、附 sources/evidence/uncertainties/change_records）。

## 输出物说明

| 输出物 | 位置 | 内容 |
|---|---|---|
| pages.jsonl | /app/work/material/pages.jsonl | 逐页文本：`{"file","page","char_start","char_end","text"}`，char_start/char_end 为该页在本文件全部页文本（按页序拼接、不含换页符）中的字符偏移 |
| material_index.json | /app/work/material/material_index.json | `{"materials":[{"file","type","pages","chars","sha256","tool","warnings"}],"unreadable":[{"file","reason"}]}`；SHA-256 为原始文件字节摘要，用于防篡改与重跑比对 |
| mindmap.json | /app/work/mindmap.json（草稿）→ /app/output（最终） | 思维导图节点及其证据锚点 |
| anchor_report.json | /app/output/anchor_report.json | `{"summary":{"nodes","verified","mislocated","fabricated","unanchored","number_not_found","warnings"},"findings":[...]}`，逐条列出每个节点每项核验的结论与依据 |
| quarantine.json | /app/output/quarantine.json | 必须修正或删除的节点 id 清单及隔离规则 |
| result.json | /app/output/result.json | 原始 case_id、output_contract 全部字段、诚实状态、sources/evidence、不确定性列表、变更记录 |

## 异常处理表

| 异常情形 | 检测方式 | 处理策略 | 对 result.json 的影响 |
|---|---|---|---|
| PDF 加密或无文本层 | pdftotext 输出为空或报错；material_index.json 中该材料 pages=0 且 warnings 含"未提取到任何文本" | 如实记录警告；该材料支撑不了任何 fact 节点；不得凭印象补写内容 | 状态降为 partial，uncertainties 注明该材料不可提取 |
| 材料缺失（文件不存在） | material_intake 将其列入 unreadable 并给出原因，进程不崩溃；全部缺失时退出码为 2 | 检查 /input 实际文件名与 case.json 清单是否一致；仍缺失则如实上报 | 无任何可读材料时状态为 unable_to_determine |
| 引文逐字校验失败 | anchor_audit 判定 fabricated（同文件所有页均无此引文） | 回到 pages.jsonl 重新逐字摘录；无法锚定则删除该节点或降级为 inference 并加 note | 修复前该节点进入 quarantine，不得出现在最终导图 |
| 页码错位 | anchor_audit 判定 mislocated 并给出真实页码 | 将 evidence.page 更正为真实页码后重跑审计 | 更正前记录于 uncertainties |
| PDF 页与印刷页不一致 | 材料正文印刷页码与 PDF 物理页码存在固定偏移 | 锚定一律以 **pdf_page**（pages.jsonl 的 page 字段）为准；如需引用印刷页码，在 section 或 note 中另行标注（见 references/locator-spec.md） | 在 uncertainties 中注明页码口径 |
| 同案例重跑 | 两脚本输出均为确定性（无时间戳），同输入必得同输出 | 可安全重跑并覆盖 /app/work 中间产物；result.json 就地更新 | change_records 追加一条重跑记录 |

## 最小合成示例说明

`examples/` 下提供一个**完全虚构的合成示例**（非真实论文、非真实数据，仅用于演示工具行为，目录内另有标注）：

- `examples/synthetic-input/material_alpha.txt`、`material_beta.txt`：两份虚构玩具材料（"材料X""器件Y"及全部为编造的数据），以 `\f` 分页。
- `examples/synthetic-input/mindmap.json`：9 个节点，其中 5 个证据正确、1 个引文为改写（→ fabricated）、1 个引文正确但页码错误（→ mislocated）、1 个标签含材料中不存在的数字（→ number_not_found）、1 个 inference 节点缺少 note（→ warning）。
- `examples/synthetic-output/`：对上述合成输入**真实运行**两个脚本得到的 pages.jsonl、material_index.json、anchor_report.json、quarantine.json，另有 README 标注其为合成示例输出。

复现方式（在 bundle 目录外任意工作目录执行）：

```bash
cd examples/synthetic-input
python3 ../../scripts/material_intake.py --out ./synth-work/material material_alpha.txt material_beta.txt
python3 ../../scripts/anchor_audit.py --map mindmap.json \
    --material ./synth-work/material/pages.jsonl \
    --report ./synth-work/anchor_report.json \
    --quarantine ./synth-work/quarantine.json
# 预期：summary 中 fabricated=1、mislocated=1、number_not_found=1、warnings=1；退出码为 1
```

## 限制

- 仅依赖 Python 3.10+ 标准库与系统 PATH 中的 pdftotext；无网络访问；无 OCR 能力。
- 逐字校验在规范化（压缩空白、统一破折号与引号）后进行，能够容忍排版差异，但**无法识别语义等价的改写**——改写一律按 fabricated 处理，这是刻意保守的设计。
- 数字核验仅为"存在性"核验（标签数字是否出现于材料文本），不校验数字与陈述对象的语义对应关系。
- `pdftotext -layout` 对复杂排版（多栏、表格、公式）的页文本可能出现错行或错位，逐字摘录时应以 pages.jsonl 中的实际文本为准。
- 本工作不评判材料本身的科学真伪，仅保证思维导图节点忠实于所引材料。
