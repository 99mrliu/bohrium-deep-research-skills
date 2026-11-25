# 物理版面与证据恢复规则

本文件只处理 PDF 上游物理版面到可复核文本证据的过程，不处理通用 lint、来源指纹、论文质量评价或语义 entailment。

## 1. 输入与事实分层

1. 先读取 `/input/task.md`，其中实际 `output_contract` 决定最终 `/app/output/result.json` 的字段名、类型和必需字段；不要套用想象中的固定合同。再读取 `/input/case.json`，原样保留 `case_id`。资源与预算见 `environment/resources.yaml`。
2. 原始 PDF、提取文本、物理块、角色判定、定位结果是不同层次。每层的来源都写入 `sources`；不得把推测的阅读顺序写成 PDF 已证实事实。
3. `scripts/layout_evidence.py` 接受 JSON 物理块或 TXT/MD，**不直接解析 PDF**。Agent 可在环境已有工具时，用 `pdftotext -bbox` / `pdftotext -bbox-layout` 或 PyMuPDF 生成物理文本块，再转换为 JSON。脚本不要求、不自动安装这些依赖。
4. 坐标默认沿提取器页面坐标系保留为 `[x0,y0,x1,y1]`。记录提取器及其原点/单位（若已知）；不知道就写 `null` 和 uncertainty，不能猜。
5. 所有页面为一基页码。TXT/MD 的页面也按一基页码。没有物理页序依据时，不可把文件数组次序包装成已验证顺序。

## 2. 双栏与跨栏顺序

1. JSON 每页用 `block_order` 显式列出**所有**块 ID，且每个恰好一次。正文检索只从其中筛选 `body`（可选 `figure_text`），所以页眉、页脚的列出位置不会改变正文流。
2. 对常规双栏，只有视觉证据支持时才采用“左栏自上而下，再右栏自上而下”的连续顺序。不要按所有块的 `y0` 全局排序，因为那会把左右栏逐行交错。
3. 跨栏标题、通栏段落、脚注、侧栏和插入框不能被强行塞入栏序。若连续关系不清楚，保留候选顺序并报告 `ORDER_NOT_DECLARED` 或自定义未决项；不可凭阅读“更通顺”来伪造确定性。
4. 缺 `block_order` 且有多个正文块时，脚本仅为产生诚实 partial 而采用输入数组次序，并发 `ORDER_NOT_DECLARED`。这不是顺序恢复成功。
5. `column` 是物理栏标签，不是排序指令。脚本不会自动推断“正确”栏序。正确性需由坐标、提取输出和页面检查共同支持。
6. 跨块、跨页引文可以匹配，结果以 `spans_blocks` / `spans_pages` 明示。跨页匹配的根级 `page_char_start/end` 为 `null`，逐段 offsets 仍保留。

## 3. 页眉、页脚、图内文字和正文

1. 每块给定 `role`：`body`、`header`、`footer`、`figure_text` 或其他自定义角色。只有 `body` 默认进入阅读流。
2. 重复出现在页面顶部/底部是页眉页脚线索，不是充分条件。重复术语也可能是正文；角色判定应结合位置、字体或页面图像。没把握就加 uncertainty。
3. 页眉、页脚和图中文字仍保存在索引的块列表中，`included: false` 且全局 offsets 为 `null`。因此排除是可审计的，不是静默删除。
4. 图中文字默认隔离，避免 `FIGURE 1 ...` 与正文拼成虚假引文。只有查询图内证据或任务明确要求时，使用 `--include-figure-text` 建立单独索引；报告中必须记录此选择，不能把该流冒充纯正文。
5. 对 OCR 图中文字、旋转文字或叠印，保留原块与坐标，并报告畸变。本工具不旋转图像、不去噪、不进行 OCR。

## 4. 换行、断词与保真引文

1. `exact` 模式只在规范化 LF 的阅读流中寻找逐字子串；大小写、空白、连字符差异都会导致不匹配。若查询含 `\n`，可验证原始断词形式。
2. `fidelity` 模式只做确定性折叠，并为每个行尾 ASCII 连字符保留两个候选投影：
   - 投影 `hyphen_removed` 移除 `-\n` 及换行后的水平空格，适合 `dehyphen-` + `ation` → `dehyphenation`；
   - 投影 `hyphen_retained` 保留连字符但移除其换行，适合 `cross-` + `column` → `cross-column`；
   - 两个投影都把连续 Unicode 空白折叠为一个空格。匹配映射回同一 raw range 时去重，实际投影写入 `fidelity_variant`，不会仅因双投影而制造歧义。
3. `fidelity` 不做大小写折叠、词形还原、同义词替换、Unicode NFKC、标点替换或 semantic entailment。因此 `cross-column` 不等于 `cross column`，`Evidence` 不等于 `evidence`。普通词内连字符也不会被随意删除；删除仅发生于原阅读流的行尾断词候选。
4. 每次匹配保存原阅读流 `[document_char_start, document_char_end)`、`source_excerpt` 和逐原行 segments。折叠只用于搜索，不能覆盖原文。
5. 连字符可能是真实复合词而非软断词。若断词类型或拼合结果有争议，同时保存 exact 未找到、候选 fidelity 匹配与 unresolved 说明，不宣称单词恢复已证实。
6. 对不可见连字符、软连字符、 ligature、全角字符或编码错乱，当前脚本不自动矫正；记录 `UNRESOLVED_DISTORTION` 等未决项。

## 5. TXT/MD 分页与行索引

1. 输入必须是严格 UTF-8（无 BOM）。CRLF/CR 先变为 LF，所有全局 offset 都针对这个**规范化 LF 流**，不是磁盘字节 offset。
2. TXT 用 form-feed (`\f`) 分页；MD 同时支持 form-feed 和独占一行的 `<!-- page: N -->`。起始 `page: 1` 是标签，其他标记产生换页；页标记不是正文，不可被检索。
3. 非顺序页标记产生 `PAGE_NUMBER_MISMATCH`。空文本页不可被解释为无文本层扫描页；只有显式 `extraction_status: no_text_layer` 才触发扫描阻断。
4. 每个 TXT/MD 页生成一个 `pN-b1` body 块。它没有坐标，不表示物理单栏已获证明。
5. 行号是一基；行内字符 offsets 是零基、Unicode code point、半开区间 `[start,end)`。它不是 UTF-8 字节数，也不是 PDF 字形 ID。

## 6. 扫描无文本层与失败策略

1. 扫描页无文本层时用 `extraction_status: no_text_layer`、空块及未决项。命令仍写索引/定位报告，但退出码为 2，状态为 `needs_review` / `unresolved`。
2. 在无 OCR 文本页中未找到引文，不能推出“不含引文”。最终字段用 `null`、空结果及明确 uncertainty 表示未知。
3. 如果实际执行 OCR，记录工具、版本、页码和来源，把页面标成 `ocr`。未逐字核对时保留 `OCR_UNVERIFIED`，定位只表示 OCR 文本匹配，不表示原扫描内容已准确恢复。
4. 工具不可用时立即保存诚实 partial，不安装重依赖、不假装 PDF/OCR 成功。一个页或一个字段失败，不清空其他页已经取得的有效定位。
5. 重复短语有多处匹配时状态为 `ambiguous`，列出全部物理位置；不得擅自选择最像答案的一个作为唯一证据。零匹配是 `not_found`，空查询是 `invalid`，两者都不等于语义假。

## 7. 时间与请求预算下保存 partial

1. 总上限为 64 requests / 900 秒。一开始就记录计数和单调时钟；给结果整理保留余量，不在最后一刻才序列化。
2. 启动后先按实际 `output_contract` 创建 `/app/output/result.json` partial：原 `case_id`、全部必需字段的 `null`/空容器、`sources`、`uncertainty`、`change_records` 和明确的 partial 状态。字段 placeholder 不得伪装成找到的事实。
3. 每完成提取、索引、定位的阶段性工作就原子更新；中间索引和报告放 `/app/work`。最后只把合同要求的最终结果放 `/app/output`。
4. 超时/请求达到上限时停止新请求，保存已完成证据和未决原因。partial 优先于超时且无文件。
