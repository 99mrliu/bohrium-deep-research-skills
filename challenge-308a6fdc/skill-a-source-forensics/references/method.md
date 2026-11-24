# 方法细节与限制

## 1. 管线总览

```
/input ──► forensic_intake.py ──► /app/work/manifest.json      （哈希+类型+状态基线）
                                  /app/work/receipts/Mx.json   （抽取回执）
                                  /app/work/extracted/Mx.*     （抽取文本副本）
                                  /app/work/anchor_index.json  （行/页锚索引）
                                            │
        写作（模型，带锚 [Mx:Ly]/[Mx:py]）   │
                                            ▼
/app/output/deliverable.md ──► anchor_audit.py ──► /app/output/audit_report.md
                                                    /app/output/result.json
```

两个脚本均为纯 Python3 标准库、确定性、秒级；唯一可选外部依赖是 `pdftotext`（`shutil.which` 检测，缺失即降级）。

## 2. 取证细节

- **类型嗅探（magic bytes，不信扩展名）**：`%PDF`→pdf；`PK\x03\x04/05/07`→zip（docx/xlsx 容器）；`\x89PNG\r\n\x1a\n`→png；`\xFF\xD8\xFF`→jpeg；`GIF87a/89a`→gif；可整体 UTF-8 解码→text；其余→binary。
- **哈希**：SHA-256 流式计算（1 MiB 分块），大文件不占内存。
- **材料编号**：全部常规文件按相对路径字典序编为 M1、M2…，跳过符号链接；同一输入编号恒定。
- **PDF 抽取**：`pdftotext -layout <file> -`，stdout 按 `\f` 分页；记录页数与每页字符数。返回非零→`extractor_error`；零页文本→`no_text_layer`；工具缺失→`extractor_unavailable`。
- **完整性证明**：audit 时对 manifest 中每份材料 re-hash 并比对；任一缺失或哈希变化 → `integrity_check: fail` 并进入 uncertainty。这证明"写作期间输入未被改动"，不证明材料本身内容真实。

## 3. 锚核验算法

1. 交付稿切句前剔除：代码块、标题行（`#`）、引用行（`>`）、表格行（`|`）、含 `audit-skip` 的行；随后按中英文句末标点切句，纯锚碎片并回上一句。
2. 事实句判定：含 `\d`，或含线索词（表明/显示/证明/证实/指出/提升/提高/下降/降低/达到/占比/约为/超过）。
3. 关键 token：数字（`\d+(\.\d+)?%?`）、≥4 字符英文词（转小写）、中文连续段落的 4 字滑窗（≥4 字段落整体也算）。
4. 共振判定：任一 token 出现于锚位原文（行锚 ±2 行上下文，页锚首页前 200 字符）即通过；论断无关键 token 时不做共振判定（非事实句）。
5. 结论 PASS ⇔ 异常锚 = 0 且无锚事实句 = 0；`【待确认】` 句豁免但公示。

## 4. result.json 装配

- 先以 `output_contract` 的全部键占位 `"PENDING"`，再逐项填实——契约字段永不缺失。
- `case_id` 从 case.json 原样照抄；`evidence_map` 为"锚 → {材料, 状态, 论断, 原文摘录}"；`preserved_facts` 为通过核验的带锚事实句；`sources` 为 manifest 材料全量（含 SHA-256）；`status = complete` 当且仅当审计 PASS 且完整性 pass，否则 `partial`。

## 5. 限制（务必知情）

- **不验证语义真假**：共振只保证"论断与锚位原文有字面交集"，不保证锚位原文真的支持该论断。它抓得住"没读材料/锚错位/无锚"，抓不住"读对了但曲解"。人工抽查仍必要。
- **中文分词启发式**：4 字滑窗在极端同义改写时可能误报（见 anchoring-protocol.md §5），也可能被"埋字"绕过——故红线禁止埋字。
- **PDF 依赖外部工具**：无 `pdftotext` 时 PDF 完全不可锚定（如实记缺口）。docx 等 zip 容器不做解包，记 `non_text_material`。
- **图片/OCR 超出范围**：图片材料只记缺口，不读图；正文引用图片内容须人工核对并在 uncertainty 声明。
- **完整性是快照比对**：只能发现"intake 之后输入被改动"，不能防止 intake 之前材料已被污染；基线哈希即信任锚点。
- **单交付稿**：audit 每次核验一份 Markdown 交付稿；多产物需分别跑。
