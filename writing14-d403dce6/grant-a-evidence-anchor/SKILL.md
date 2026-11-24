---
name: grant-a-evidence-anchor
description: 基金申请书章节稿的证据锚定与引用核验。Use when 需要保证申请书中每个数字、术语、引用、关键论断都能锚定到 /input 材料原文逐字 quote，并按"已完成/外部工作/拟开展/待确认"四态区分归属，防止凭印象引用、把原论文成果写成申请人已完成、数字无出处。
---

# grant-a-evidence-anchor：证据锚定与引用核验

## 0. 运行契约

- 启动时读取 `/input/case.json` 与 `/input/task.md`；若存在 `/input/organizer-workorder.json`、`environment/resources.yaml` 一并读取。`output_contract` 字段在运行时从案例自身读取，**不得硬编码**。
- 工作目录 `/app/work`，最终产物与可编辑稿件归 `/app/output`；`/app/output/result.json` 必须含原始 `case_id`、全部 output_contract 字段、诚实的 `status`（success/partial/unable_to_determine/refused）及原因、sources、uncertainty；partial 必须说清界限。
- 材料清单一出来就先落一份诚实的 partial，再就地迭代改进。预算：64 次模型请求 / 900 秒 / 每次响应 16384 tokens（含 reasoning）。
- 只依据**实际读到的材料**写作，绝不按文件名或领域标签补造内容；PDF 无预抽取答案层，必须实际抽取文本。组织方已声明申请人证据缺失时按缺失处理，缺失项列入缺口清单。

## 1. 聚焦问题

**"查得到"**：章节稿中每个数字、术语、引用、关键论断必须能锚定到材料原文的逐字 quote（文件+页/节定位），并以四态标注区分归属。针对基础 Agent 的三类真实失败模式：

1. 凭印象引用（quote 与原文存在改写、数字四舍五入）；
2. 把原论文/既有成果写成申请人"已完成"工作；
3. 数字无出处（尤其是拟开展部分的量化指标随口给出）。

对应处置：证据缺口显式标注【待申请人确认：…】而非编造；引用无法核实标"未核验"。

## 2. 工作流程

1. **盘点材料**：运行 `extract_sources.py --input /input --out /app/work/anchor`，得到 `materials_inventory.json` 与 `src_text/` 纯文本层。逐一检查 `extract.status`：unreadable 的文件按第 4 节异常表处置。
2. **读材料建证据底表**：通读 src_text 中每份文本，为拟写入章节稿的每条关键论断建立 evidence_map 条目（schema 见 `references/evidence_map.schema.json`）：quote 逐字复制原文、填 source.file/loc、按 `references/status_taxonomy.md` 判四态、外部工作附 citation（规则见 `references/citation_rules.md`）。写入 `/app/work/anchor/evidence_map.json`。
3. **锚定核验**：运行 `anchor_audit.py`（参数：`--evidence`、`--src-text /app/work/anchor/src_text`、`--inventory`、`--out`）。退出码非 0 时逐条修复 error（改 quote 为逐字原文，或改正 status/来源类别），warning 记录待办，直至退出码 0 或只剩经人工确认的 warning。
4. **写章节稿**：只使用 evidence_map 中已锚定的事实与数字；每条关键论断后用（证据 Ex）回指；四态谓词分明（"已完成/已"对申请人证据，"已有研究报道"对外部工作，"拟/将"对计划）；材料缺口写【待申请人确认：…】占位符。
5. **无出处数字扫描**：运行 `orphan_scan.py --proposal <章节稿.md> --evidence evidence_map.json [--whitelist 案例年份白名单.json]`。退出码非 0 时，为每个无出处数字二选一：补证据条目（回到第 2 步），或删去/改写该数字。占位符计数写入 result.json 的 uncertainty 与缺口清单。
6. **交付前自查**：对照 `references/reviewer_checklist.md` 逐项打勾；二次运行三个脚本确认输出字节一致；将 evidence_map、两份报告随章节稿一并归入 `/app/output`（具体字段以案例 output_contract 为准）。

## 3. 事实与来源红线

- 四态标注：**已完成**＝申请人已有且材料有证据；**外部工作**＝原论文/既有成果，归外部作者；**拟开展**＝本研究计划将做；**待确认**＝材料缺失需人工确认。判定规则与常见误判见 `references/status_taxonomy.md`。
- 不新增材料之外的任何事实、数字、文献；quote 必须逐字，改写即视为未锚定。
- `已完成` 的来源必须判定为申请人证据类；外部论文即使与申请方向一致也不得记为已完成。
- 引用查不到原文标"未核验"，**不得**补造卷期页码 DOI；材料中完全无踪迹的文献不得进入申请书。

## 4. 异常处理表

| 异常 | 处置 |
|---|---|
| PDF 加密 / 无文本层 | extract_sources 标记 unreadable；尝试渲染+OCR，做不到则声明不可读，相关论断标 待确认，整体落 partial |
| pdftotext / soffice 缺失 | 诚实降级：unreadable 并记录原因，不得假装读过 |
| 材料缺失（组织方声明或盘点发现） | 对应位置放【待申请人确认：…】占位符 + 缺口清单 + result.json uncertainty；不补造 |
| 材料间冲突（两处数字不一致） | 两个 quote 都登记，章节稿采用更直接/更新来源并在 uncertainty 中说明冲突，不擅自取平均 |
| 超长输入 | 先盘点后分文件读取；evidence_map 分批构建分批核验；优先锚定支撑立项依据与已完成工作的论断 |
| 格式冲突（docx 无法转换、乱码） | unreadable 登记原因；尝试替代工具；失败则按材料缺失处理 |
| 七要素清单与默认不同 | 以案例 task.md / organizer-workorder 给定清单为准，不使用默认清单硬套 |
| quote 未命中（anchor_audit 报错） | 按报告 diagnosis 的 source_snippet 对照原文，重新逐字复制；不得"微调 quote 到命中为止"式猜改 |
| 无出处数字（orphan_scan 报错） | 补证据或删数字；禁止把数字塞进白名单搪塞 |

## 5. 脚本与资源清单

| 路径 | 作用 | 调用方式 | 退出码 |
|---|---|---|---|
| `scripts/extract_sources.py` | 盘点 /input：登记路径/大小/md5/角色猜测；PDF 经 pdftotext 抽文本并计页数；md/txt/json 复制；docx 经 soffice 转换；产出 materials_inventory.json | `python3 extract_sources.py --input /input --out /app/work/anchor` | 0 正常（unreadable 如实登记）；2 输入错误；3 写入失败 |
| `scripts/anchor_audit.py` | 核验 evidence_map：quote 经 NFKC+空白折叠后须为来源逐字子串（报告 char_offset，未命中给最接近匹配诊断）；四态合法；已完成必须归属申请人证据类；citation 要件缺件标 warning；产出 anchor_audit_report.json | `python3 anchor_audit.py --evidence evidence_map.json --src-text src_text --inventory materials_inventory.json --out anchor_audit_report.json` | 0 无 error；1 有 error；2 输入错误 |
| `scripts/orphan_scan.py` | 扫描章节稿：抽取阿拉伯数字/百分数/年份，未出现在任何 quote 且不在白名单者列为无出处数字；统计【待确认】/【待申请人确认】占位符；产出 orphan_report.json | `python3 orphan_scan.py --proposal sections.md --evidence evidence_map.json [--whitelist wl.json] --out orphan_report.json` | 0 无无出处数字；1 存在；2 输入错误 |
| `references/evidence_map.schema.json` | 证据底表 JSON schema（id/claim/quote/source{file,loc}/status/source_class/citation） | 建表与人工校验依据 | — |
| `references/status_taxonomy.md` | 四态判定规则、source_class 判定顺序、常见误判（原论文成果 vs 申请人已完成）、quote 摘录规范 | 第 2 步建表时对照 | — |
| `references/citation_rules.md` | 引用核验层级（已核验/未核验）、要件、红线 | 处理 citation 时对照 | — |
| `references/reviewer_checklist.md` | 评审人视角"查得到"自查表（数字/引用/四态/材料完整性/反凭印象抽查） | 交付前逐项过 | — |

三个脚本仅用 Python3 标准库；pdftotext / soffice 为可选外部工具，缺失时诚实降级。全部脚本支持 `--help`，输出确定性（同一输入二次运行字节一致）。

### 最小示例（合成示例，非正式案例结果）

`examples/` 内含虚构材料（外部论文节选、申请人前期记录、工单片段）、含 2 个陷阱的 `evidence_map.json`（外部工作错标已完成；quote 改写未命中原文）、含 1 个无出处数字（42%）的 `proposal_sections.md`，以及修复版输入。真实运行结果：anchor_audit 抓到 2 个陷阱退出码 1，orphan_scan 抓到 1 个无出处数字退出码 1；修复版退出码 0；二次运行输出字节一致。完整命令与真实输出摘录见 `examples/README.md`。

## 6. 版本与维护

- 版本：1.0.0（2026-11）
- 依赖：Python 3.8+ 标准库；pdftotext（poppler）与 soffice（LibreOffice）可选，缺失时对应文件标记 unreadable 并说明原因。
- 适用范围：基金申请书及类似"论断须可溯源"的科技写作场景；针对"查得到"维度。
- 限制：角色/source_class 猜测为启发式，最终以材料内容与人工确认为准；orphan_scan 的数字白名单需按案例配置，内置白名单仅覆盖单位数编号；citation 要件检查为启发式 warning，不替代人工核验；本 bundle 不处理"立得住/说得准/对得上"维度（由其他 bundle 负责）。
