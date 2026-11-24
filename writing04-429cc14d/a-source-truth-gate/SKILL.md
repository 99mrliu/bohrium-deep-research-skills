---
name: source-truth-gate
description: >-
  上游数据真实性核验关。当 /input 中存在 case.json、task.md、稿件与文献库
  （BibTeX/RIS/EndNote/CNKI 导出、DOI 快照、PDF/DOCX 等），且任务要求对参考文献做
  核验去伪、元数据比对、论断-引用锚定、去重、编号更新或格式整理（GB/T 7714—2015
  顺序编码上标、APA 7 著者-年、中英混排），并向 /app/output 交付改后稿、同步文献表
  与 result.json 时调用本技能。本技能先核验再放行：任何文献条目、任何论断-引用
  对应关系，未过核验关不得进入成品。不适用场景：与参考文献无关的纯写作润色；
  要求凭模型记忆"补全"或"猜测"文献元数据的任务；要求删除证据不足条目但无任务
  明确授权的情形；无 /input 材料、凭空生成文献综述的请求。
---

# source-truth-gate：上游数据真实性核验关

## 核心主张

任何文献条目、任何论断-引用对应关系，在进入改后稿之前必须先过核验关。核验不过的
条目不删除而是隔离登记；核验不过的论断-来源对应必须修复或降级标注为证据不足。宁可
让输出变保守（条目被隔离、论断被标注、结论写明覆盖边界），也绝不让伪造文献、错误
元数据、错配引用流入成品。核验的唯一依据是输入材料本身（可信快照与来源文本），
而不是模型记忆：DOI 解析失败不等于伪造，Crossref 404 不等于删除理由，快照查不到
不等于条目不存在。本技能把机械性保证集中在核验层（三个确定性脚本），其余阶段为
程序性指引。

## 运行时契约（必须先读）

以下条款不可协商，优先级高于一切"让结果更好看"的倾向：

1. **逐文件读真实内容。** 对 /input 中的每个文件，必须打开并阅读其真实内容，
   不得凭文件名、扩展名或"看起来像"猜测内容。先执行 `ls -laR /input` 建立完整
   清单，再逐一读取；遇到无法解析的格式，换工具重试一次，仍失败则登记为
   unreadable，绝不可用想象填补。
2. **若存在 /input/environment/resources.yaml，先读它。** 其中声明的资源路径、
   快照位置、工具约束构成后续核验的事实基础。
3. **目录纪律。** 中间产物（清单、登记册、核验报告、台账、草稿）一律写入
   /app/work；最终交付物（改后稿、同步文献表、result.json、可复核附件）写入
   /app/output。不得把中间产物当作交付物。
4. **result.json 契约字段逐字一致。** result.json 必须包含与 case.json 中
   case_id 逐字一致的值，以及 output_contract 声明的全部原始字段——字段名逐字
   照抄，不增、不删、不改、不翻译、不改大小写。output_contract 声明了哪些字段，
   result.json 就 exactly 出现哪些字段。
5. **第一阶段就写 result.json 骨架。** 在阶段 0 即创建 /app/output/result.json，
   契约字段先全部置 null，status 置 "in_progress"；此后每个阶段结束时回填已确认
   的字段。这样即使运行中断，/app/output 中始终存在一份合法的半成品 result.json，
   而不是一无所出。
6. **预算。** 总模型请求 ≤ 64 次、总时长 ≤ 900 秒、单次响应 ≤ 16384 token。
   据此规划：核验层用脚本完成（不占模型请求），模型请求只花在阅读理解、台账
   构造与稿件改写上；避免逐条目单独请求，批量构造 entries.jsonl 与 claims.jsonl
   后一次性交给脚本。
7. **status 诚实。** result.json 的 status 只能取 success / partial / failed，
   且必须与事实相符：存在隔离条目、降级论断或未完成任务要求时不得写 success；
   写 partial 必须同时写明缺什么（哪些条目被隔离、哪些论断被降级、哪些要求未完成
   及原因）；failed 仅用于完全无法产出合法交付物的情形。
8. **禁止伪造。** 文献不存在就写不存在；核验不过的条目不得被引用；不得凭领域
   标签、"常见格式"或模型记忆补造 DOI、页码、年份、卷期、作者或任何元数据；
   不得在报告或 result.json 中写"已联网核实"等与实际执行不符的陈述。本技能
   全部脚本均无网络访问，核验依据只能是输入快照与来源文本。

## 核验状态速查表

下表为状态机的速查版；完整定义、转移条件与处置规程见
references/verification_policy.md。

| 状态 | 含义 | 可否进入成品文献表 | 可否作为关键论断支撑 |
| --- | --- | --- | --- |
| verified_identity | 身份确认（by DOI 或 by_title） | 可以 | 可以 |
| metadata_conflict | DOI 命中但字段与快照冲突 | 否，隔离登记；按快照修正后可重验 | 否 |
| not_found_in_snapshot | DOI 合法但快照未覆盖 | 否，除非任务明确豁免且标注 | 否（默认） |
| not_checked | 无 DOI 且标题无法确认 | 否；任何位置不得写"已核实" | 否 |
| suspected_fabricated | DOI 语法非法或张冠李戴 | 禁止；隔离登记 | 禁止 |
| invalid_input | 条目本身不是合法输入 | 否，先修正输入再重验 | 否 |

锚点审计的状态更简单：PASS 可用；FAIL 必须修复或降级；ERROR 先回到阶段 0
查明来源真伪，查不清则论断降级为证据不足。

## result.json 骨架示例

阶段 0 写出的骨架形如（字段名以 case.json 的 output_contract 为准，此处仅为
示意，实际字段名必须逐字照抄 output_contract，一个都不许改）：

```json
{
  "case_id": "<逐字照抄 case.json 的 case_id>",
  "status": "in_progress",
  "<output_contract 字段 1>": null,
  "<output_contract 字段 2>": null,
  "<output_contract 字段 N>": null
}
```

回填纪律：每个阶段结束立刻回填该阶段能确定的字段；不允许把回填拖到最后
一次请求——那样一旦中断，交付目录里就什么都没有。

## 工作流程（五阶段）

### 阶段 0：盘点与契约骨架

1. `ls -laR /input`，逐文件读取真实内容，登记到 /app/work/inventory.md：每个文件
   一行，含路径、字节数、格式判断、角色判断（稿件/文献库/快照/来源正文/契约）。
2. 读取 case.json，把 case_id 与 output_contract 的全部原始字段名逐字抄出，
   立即写出 /app/output/result.json 骨架（字段置 null，status: "in_progress"）。
3. 收集来源文本：把稿件正文、文献全文或可抽取文本整理到 /app/work/sources/
   （纯文本，UTF-8）；把文献库（BibTeX/RIS/EndNote/CNKI 导出）转换为或抽取为
   统一条目集，存 /app/work/library/。组织方提供的 DOI/元数据快照原样复制到
   /app/work/library/snapshot.json。
4. 运行登记册脚本，固化输入指纹，防止"来源到底是什么"事后扯皮：

   ```bash
   python3 /skills/weekly-skill/scripts/source_registry.py \
     --sources /app/work/sources --out /app/work/registry.json
   ```

   （本地复现时把 `/skills/weekly-skill/scripts/` 替换为本 bundle 的 `scripts/`
   相对路径，下文同。）

### 阶段 1：条目身份与元数据核验

1. 将文献库中的每条条目规整为一行 JSON，批量写入 /app/work/entries.jsonl
   （字段格式见 references/ledger_formats.md：id, title, authors, year, venue,
   doi 可选, pmid 可选, type 可选）。抽取原则：只抄录文献库中真实存在的字段，
   缺的字段就缺着，绝不凭记忆补 DOI、页码、年份、卷期。
2. 运行核验脚本：

   ```bash
   python3 /skills/weekly-skill/scripts/verify_entries.py \
     --entries /app/work/entries.jsonl \
     --snapshot /app/work/library/snapshot.json \
     --out /app/work/verify
   ```

3. 按状态机处置（完整定义与处置规程见 references/verification_policy.md）：
   - **verified_identity**：身份确认，可进入候选文献集。无 DOI 但按标题命中的，
     报告带 note: by_title，使用时在不确定性说明中注明核验路径。
   - **metadata_conflict**：DOI 命中但 title/year/first_author 与快照冲突。
     隔离登记；以快照为准修正元数据后可重验，修正动作必须记录 old/new/field。
   - **not_found_in_snapshot**：DOI 语法合法但快照无记录。这是快照覆盖不全的
     信号，不等于伪造：隔离登记并标注"未经快照确认"，除非任务明确豁免，不得
     作为关键论断的支撑文献。
   - **not_checked**：无 DOI 且按标题无法确认。不得在任何地方写"已核实"。
   - **suspected_fabricated**：DOI 语法非法，或条目其余元数据在快照中匹配到的
     记录 DOI 不同。隔离登记，禁止引用，禁止"修一修接着用"——除非能在输入材料
     中找到该条目真实存在的独立证据（而非模型记忆）。
4. 脚本退出码为 1 表示存在必须隔离/修复的条目，这是正常工作流程的一部分，
   不是脚本故障；阅读 verification_report.json 逐条处置即可。

### 阶段 2：论断-来源锚点审计

1. 从改后稿（或其草稿）中抽出每个承载关键论断的句子，构造 claim ledger
   /app/work/claims.jsonl，每行一条：id、claim（论断）、source（来源文件名，
   指向 /app/work/sources/ 内的文件）、quote（从来源正文中**逐字复制**的引文，
   不得凭记忆复述）、locator（可选，页码/节号等定位符）。
2. 运行锚点审计：

   ```bash
   python3 /skills/weekly-skill/scripts/claim_anchor_audit.py \
     --sources /app/work/sources \
     --ledger /app/work/claims.jsonl \
     --out /app/work/anchor
   ```

3. 处置：
   - **PASS**：引文逐字锚定于来源（报告附 char_offset），该论断-引用关系可用。
   - **FAIL**：脚本给出诊断（paraphrase_or_minor_alteration 转述冒充引文 /
     cross_segment_splice 跨段拼接 / source_mismatch 记错出处）。必须三选一修复：
     (a) 把 quote 改为来源中的逐字文本；(b) 把稿件中该处改写为明确的转述表述
     （去掉引号、改用"研究报道……"类措辞）并确认论断本身被来源支撑；
     (c) 无法修复时，将该论断在稿件中降级标注为证据不足（如"此说尚缺直接
     文献支持"），并在不确定性说明中登记。
   - **ERROR**（来源缺失/不可读）：回到阶段 0 检查 inventory，确认来源是否
     真实存在；不存在的来源对应的论断一律按证据不足降级。

### 阶段 3：在核验通过的条目集合上完成其余案例动作

只有在阶段 1 通过（verified_identity，或任务明确豁免的 not_found_in_snapshot）
的条目集合上，才执行 task.md 要求的其余动作：引用插入与定位、编号更新、文献
去重（按归一化标题+第一作者+年份判重，合并时保留核验状态更高者）、格式转换与
渲染（严格按 task.md 指定的规范：GB/T 7714—2015 顺序编码制上标引用、APA 7
著者-年制、或中英混排规则；规范未明确处参照 task.md 原文而非惯例）。本阶段为
程序性指引，不提供额外脚本：去重、编号、渲染的正确性依赖模型按 task.md 执行，
而"哪些条目有资格进入这些操作"这一机械保证集中在阶段 1–2 的核验层。阶段 3
结束时回填 result.json 相应字段，并将阶段 1–2 中所有隔离/降级处置汇总写入
不确定性说明。

### 阶段 3.5（目录结构约定）

此时 /app/work 应形如：

```text
/app/work/
  inventory.md            # 阶段 0：输入清单
  sources/                # 阶段 0：纯文本来源（UTF-8）
  library/                # 阶段 0：条目集与 snapshot.json
  registry.json           # 阶段 0：SHA-256 登记册
  entries.jsonl           # 阶段 1：条目台账
  verify/                 # 阶段 1：verification_report.json/.md
  claims.jsonl            # 阶段 2：论断台账
  anchor/                 # 阶段 2：anchor_report.json/.md
```

/app/output 中除稿件与文献表外，始终有 result.json（骨架起步、逐阶段回填）。

### 阶段 4：收口

1. 回填 /app/output/result.json 全部契约字段：case_id 逐字照抄；status 按事实
   取 success/partial/failed；partial 时写明缺什么。
2. 把可复核附件复制到 /app/output：registry.json（输入指纹）、
   verification_report.json/.md（条目核验报告）、anchor_report.json/.md
   （锚点审计报告）、不确定性说明（隔离条目清单、降级论断清单、覆盖边界）。
3. 终检：逐条检查成品中每一条与文献相关的陈述（每处引用标记、每条文献表
   条目、每个论断-引用对应），确认都能回溯到一条 PASS 记录或 verified_identity
   条目；任何无法回溯的，当场移除或降级，不得"先交付再说"。
4. 最后通读 result.json，确认字段名与 output_contract 逐字一致、status 与事实
   相符。

## 异常处理表

| 异常情形 | 处置规程 |
| --- | --- |
| 条目核验 FAIL 且修不好（如 suspected_fabricated 无独立证据） | 隔离登记进不确定性说明（条目 id、状态、证据），成品中不引用、不删除，result.json 的 status 据实取 partial 并说明 |
| 来源文件不可解析（编码损坏、加密 PDF 等） | 换工具/换编码重试一次；仍失败则在 inventory 与 registry 中登记 unreadable，依赖该来源的论断全部降级为证据不足 |
| 可信快照缺失（/input 未提供 snapshot） | 全库条目标记 not_checked，不得在任何位置写"已核实"；在 result.json 与不确定性说明中写明核验覆盖边界 |
| DOI 格式合法但快照显示其指向另一篇文献 | 判 metadata_conflict（若 DOI 命中快照记录但字段不符）或 suspected_fabricated（若标题匹配到 DOI 不同的记录），隔离登记，禁止引用 |
| task.md 要求删除某条目但证据不足 | 不删除；保留条目并书面说明证据状态与保留理由，把分歧显式交给评测方裁决 |
| 网络不可用（本技能脚本本来就不联网） | 只使用输入快照与来源文本完成核验；所有结论注明"依据输入快照/来源文本，未联网核实"，并写明覆盖边界 |
| claim ledger 中 quote 无法逐字锚定且无法修复 | 该论断降级标注为证据不足，登记进不确定性说明；不得保留原引用标记 |
| 预算耗尽风险（请求数/时长逼近上限） | 立即跳到阶段 4：按当前已核验状态回填 result.json（status: partial，写明未完成项），保证交付半成品合法 |

## 最小调用示例（合成示例）

见 examples/ 目录与 examples/minimal_example.md。**其中全部论文、作者、DOI、
数据、快照均为虚构合成数据，不对应任何真实文献**，仅用于演示三个脚本的调用
方式、状态机判定与退出码语义。示例包含故意埋入的缺陷（booby trap）：一条
DOI 语法非法的条目、一条年份与快照冲突的条目、一条转述冒充引文的论断，
脚本会精确捕获并以退出码 1 报告。

## 设计决策说明（为什么是"隔离"而不是"删除"）

1. **可逆性。** 删除是不可逆操作，而核验失败经常源于快照覆盖不全或输入噪声，
   并非条目必然为假。隔离登记保留了证据链，允许后续用更全的快照重验。
2. **可审计性。** 评测方需要看到"哪条被拦下、依据什么"，而不是面对一个被
   悄悄清理过的文献表。不确定性说明是本技能交付物的一部分，不是附属品。
3. **诚实优先于完备。** 一个变保守的输出（条目被隔离、论断被标注、status
   为 partial）在竞赛评分中应当优于一个表面完整但混入伪造条目的输出；本
   技能的全部默认动作都按这个偏好排序。
4. **机械保证集中在核验层。** 三个脚本是确定性的：同输入同输出、无网络、
   无随机数、无时间依赖（时间戳可由 SOURCE_DATE_EPOCH 固定）。模型只负责
   构造台账与执行处置，判定本身不经过模型，避免了"模型自己给自己打分"。

## 限制与适用范围

- 核验依据仅限输入材料：快照未覆盖的真实文献会被判 not_found_in_snapshot，
  这是保守设计（宁错拦、不错放），需要任务方提供更全的快照来解除。
- 脚本不做格式渲染：GB/T 7714、APA 7 的具体排版由模型在阶段 3 按 task.md
  执行，本技能只保证进入渲染的条目已通过身份核验。
- 锚点审计只支持纯文本来源；PDF/DOCX 需先在阶段 0 抽取为文本，抽取失败的
  按 unreadable 处理。
- 标题归一化（NFKC+大小写折叠+去标点）对极端排版差异（如译名不一致）可能
  漏配，漏配结果是 not_checked 而非误判通过，方向仍然是保守的。
- 本技能不联网；DOI 传输层失败、Crossref 404 等在线情形只作为政策知识写进
  references/verification_policy.md 的分类学，运行时不会发生。
- 本技能不改变"是否删除条目"的裁决权归属：证据不足时一律保留并说明。
