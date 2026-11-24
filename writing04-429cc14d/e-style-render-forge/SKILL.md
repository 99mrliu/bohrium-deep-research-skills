---
name: style-render-forge
description: >-
  参考文献格式转换与确定性渲染技能（方向 E：格式转换与下游渲染工程）。
  适用：BibTeX / RIS（含 CNKI RefWorks 风味）/ CNKI 文本导出文献库的解析、
  字段 lint、向 GB/T 7714—2015（顺序编码制与著者-出版年制）与 APA 7 的确定性渲染、
  缺失字段占位符标注、CSL-JSON/RIS/BibTeX 导出与往返稳定性核验、参考文献表草稿生成。
  不适用：规范符合性的最终背书（渲染器是草稿而非规范验证器，结果必须逐条目检）；
  凭记忆或联网补全缺失字段（本技能明确禁止，缺字段一律渲染可见占位符）；
  来源真实性核验（DOI 是否真实存在需人工或外部工具核实，本技能只做语法检查）；
  正文引用的语义判断（如某处是否该引某文献）。
---

# style-render-forge：格式转换与确定性渲染

## 核心主张

格式转换的敌人是「静默丢字段」和「凭印象补字段」。本技能把任何来源格式
（BibTeX、RIS 及其 CNKI RefWorks 风味、CNKI 文本导出）解析进一个**规范化记录
模型**：raw 字段逐字保留、未识别标签登记进 `unmapped_fields` 绝不丢弃、BibTeX
`@string` 宏延迟到读取时解析且原样留痕；再由**类型化模板**确定性渲染到目标规范
（GB/T 7714—2015 顺序编码制 / 著者-出版年制、APA 7）。**缺失字段渲染为可见占位符
（如 `[缺: 页码]`），绝不杜撰**；往返（import→export→import）必须做到字段级 diff
为零或全部可解释。渲染器是草稿而非规范验证器——最终逐条目检是人的工作，本技能的
职责是让每一处缺失都**看得见**，而不是藏起来。

## 运行时契约（必须先读）

1. **逐文件读真实内容**：`/input` 下的 `case.json`、`task.md`、稿件、文献库
   （BibTeX/RIS/EndNote/CNKI 导出）、可能的快照，必须逐一打开读取，不得凭文件名
   猜测内容。`resources.yaml`（若存在）先于一切业务动作读取。
2. **目录约定**：中间产物写 `/app/work`（导入的 records.json、lint 报告、各样式
   渲染稿、往返产物），最终交付写 `/app/output`（改后稿、渲染好的文献表、
   result.json）。
3. **result.json 契约**：**逐字**包含 `case_id` 与 `output_contract` 的**全部
   原始字段**，一个字段都不能少、不能改写键名。第一阶段就先写骨架
   （`status: "in_progress"`，含全部契约字段的占位结构），随后逐阶段回填；**骨架
   与回填都不可省略**。
4. **预算**：64 次工具调用 / 900 秒 / 16384 token 输出。任何阶段发现预算吃紧，
   立即把已完成部分如实回填并收尾，不得静默截断。
5. **status 诚实**：完成就是 `"completed"`，部分完成就是 `"partial"` 并说明哪部分
   未完成及原因；不确定就是不确定，不得写成确定。
6. **禁止伪造**：
   - 缺页码 / 年份 / DOI / 出版者等字段 → 渲染 `[缺: X]` 占位符，**绝不凭记忆
     或"常识"补齐**；
   - 不盲目大小写化科学缩写、软件名、专名（APA 题名句首大写只抬升首字母，
     其余字符原样）；
   - 书章、学位论文、会议论文、电子资源用各自类型字段与标识（[A]/[D]/[C]/
     [EB/OL]），**不得把非期刊文献伪造成期刊引用**；
   - 引用日期不杜撰：电子资源渲染 `[引用日期: 待补]`，除非 task.md 明确给出
     引用日期；
   - 渲染器不支持的构造 → 如实报告"不支持"，而非静默跳过或硬套期刊模板。

## 工作流程（五阶段）

### 阶段 0：盘点与契约骨架

- 列出 `/input` 全部文件，逐个读取；确认 `task.md` 指定的**目标规范与版本**：
  GB/T 7714—2015 顺序编码制还是著者-出版年制？APA 7？是否有期刊自定义覆盖
  （house style）？覆盖优先级：task.md 明示 > 期刊覆盖 > 默认 GB/T 7714—2015
  顺序编码制。
- 写 `/app/output/result.json` 骨架：`status: "in_progress"` + `case_id` +
  `output_contract` 全部原始字段（值先占位，结构先完整）。
- 统计文献库规模，规划预算分配（导入→lint→渲染→往返→目检）。

### 阶段 1：导入（import_records.py）

```
python3 /skills/weekly-skill/scripts/import_records.py --file /input/xxx.bib \
    [--file /input/yyy.ris] [--format bibtex|ris|cnki-text] --out /app/work
```

- BibTeX：条目级解析；`@string` 宏在**读取时**解析出 resolved 值，raw 源文本与
  `@string`/`@preamble`/注释逐字保留；`#` 连接按段解析；**重复键与未解析宏逐条
  报告**（重复键加 `#dupN` 后缀双保留，未解析宏保留原样不手改）。
- RIS：`TY` 起始、`ER` 结束；自动识别 CNKI RefWorks 风味（命中 A1/Y1/JF/K1 等
  提示标签）并声明判定依据；**未映射标签 verbatim 进 `unmapped_fields`**。
- CNKI 文本导出：`键: 值` 行式、空行分记录；未识别键 verbatim 保留；类型默认
  期刊论文并显式警告。
- 统一产出 `records.json`（schema `style-render-forge/records/v1`）；**每条解析
  警告都必须逐条处理**：能映射的补映射，不能的保留并在报告中说明。

### 阶段 2：字段 lint（field_lint.py）

```
python3 /skills/weekly-skill/scripts/field_lint.py --records /app/work/records.json \
    --out /app/work [--roundtrip /app/work/rt/records.json]
```

规则 L1–L8：L1 按类型查必备字段（期刊：作者/题名/刊名/年 + 页码或文章号）；
L2 DOI 语法 `10.\d{4,9}/`；L3 页码范围格式；L4 作者姓名可疑形式（全小写姓等，
**只报告不改写**）；L5 类型标识与类型匹配；L6 年份 4 位合理区间；L7 中英混排
标点（中文条目 CJK 紧邻半角标点、西文条目夹全角句读，只报告不改写）；L8 往返
字段级 diff。有 error 级发现退出码为 1——**error 不消灭就不进入交付**。

### 阶段 3：渲染（style_render.py）

```
python3 /skills/weekly-skill/scripts/style_render.py --records /app/work/records.json \
    --style gbt7714-numeric|gbt7714-author-year|apa7 --out /app/work/refs.txt
```

- 类型化模板：[J] 期刊、[M] 专著、[A]//或[C]// 论文集析出、[D] 学位论文、
  [EB/OL] 电子资源（url 存在时渲染 `(更新年)[引用日期: 待补]`）、[R]/[N]/[Z]。
- 缺字段 → `[缺: X]` 占位符，逐条登记进 `<输出名>.render_notes.json`。
- GB/T 作者 >3 名：中文条目"等"、西文条目"et al."（按记录 language 判定）。
- APA 7：作者 ≤20 全列（>20 列前 19 + … + 末位）；题名句首大写（保守策略，
  仅抬升首字母）；刊名与卷号斜体以 `*…*` 标记（纯文本约定，见 references）。
- `--style ris|bibtex|csljson` 为**导出模式**：即使视觉样式省略，也把 DOI、URL、
  卷期页、文章号、类型标识、语言等元数据完整写入导出文件。

### 阶段 4：往返与目检

```
python3 /skills/weekly-skill/scripts/style_render.py --records /app/work/records.json \
    --style ris --out /app/work/roundtrip.ris
python3 /skills/weekly-skill/scripts/import_records.py --file /app/work/roundtrip.ris \
    --out /app/work/rt
python3 /skills/weekly-skill/scripts/field_lint.py --records /app/work/records.json \
    --roundtrip /app/work/rt/records.json --out /app/work/rt
```

- 字段级 diff 必须**为零或全部可解释**（如 BibTeX citation key 字符集对 id 的
  合法改写——见 references/import_export_formats.md 的往返规程）。
- **完整渲染结果逐条目检**：每条对照 records.json 核字段、核占位符、核类型
  标识；占位符逐条决定处置（回源补齐 / 保留占位并在 result.json 声明）。
- 回填 result.json：把交付物、假设、未决占位符清单、lint 摘要如实写入，
  status 按实际情况填。

## 阶段—脚本—产物对照表

| 阶段 | 脚本 | 输入 | 产物（写 /app/work） | 失败信号 |
| --- | --- | --- | --- | --- |
| 0 盘点 | （人工读文件） | /input 全部 | result.json 骨架（/app/output） | 契约字段缺失 |
| 1 导入 | import_records.py | 各来源文献库 | records.json（含 warnings） | 解析警告未逐条处理 |
| 2 lint | field_lint.py | records.json | lint_report.json / lint_report.md | 退出码 1（有 error） |
| 3 渲染 | style_render.py | records.json | refs 文本 + *.render_notes.json | 占位符未登记 |
| 4 往返 | 三脚本串联 | records.json | roundtrip.ris、rt/records.json、rt/lint_report.* | L8 diff 非零且不可解释 |

## 占位符字典（渲染层可见占位符）

| 占位符 | 触发条件 | 处置建议 |
| --- | --- | --- |
| `[缺: 作者]` | authors 为空 | 回源查库；确认为机构/佚名再按规范特判 |
| `[缺: 题名]` | title 缺失 | 回源；不得凭刊名+年份臆造题名 |
| `[缺: 刊名]` / `[缺: 论文集题名]` | venue 缺失 | 回源或按宿主文献补 |
| `[缺: 年份]` | year 缺失 | 回源；GB/T 与 APA 均不用 n.d. 代替该占位 |
| `[缺: 页码]` | pages 与 article_number 均缺 | 查原文；若实为文章号，补 article_number 后重渲 |
| `[缺: 出版地]` / `[缺: 出版者]` / `[缺: 培养单位]` | address / publisher 缺失 | 回源；不用 [S.l.] / [s.n.] 代替占位 |
| `[缺: 网址]` | 电子资源 url 缺失 | 该条不宜按 [EB/OL]，回源或改类型 |
| `[引用日期: 待补]` | [EB/OL] 且 url 存在 | task.md 给日期则用 `--citedate` 传入；不给则保留"待补" |

## 目检清单（阶段 4 必做）

1. 逐条对照 records.json 与渲染行：作者人数与省略（等 / et al.）是否正确。
2. 类型标识 [J]/[M]/[C]/[A]/[D]/[EB/OL] 与记录 type 一一对应，无张冠李戴。
3. 每个 `[缺: X]` 都能在 render_notes.json 中找到登记，且处置结论写入 result.json。
4. DOI 原样出现（未被截断、未加多余空格）；GB/T 行尾 `DOI: xxx.` 的句点为
   模板句读而非 DOI 一部分。
5. 中文条目用全角句读处的模板标点正确；题名内部的标点保持原文（L7 只报告）。
6. 缩写、软件名、专名大小写与 records.json 中原文一致（渲染器不做盲目改写）。
7. 著者-出版年制排序为（首作者, 年, id）；顺序编码制序号与 records 顺序一致。
8. result.json 逐字段对照 case.json 的 output_contract：键名逐字、无增无减。

## result.json 回填要点

- 骨架先行：阶段 0 写出含 `case_id`、`status: "in_progress"` 与 output_contract
  全部字段的骨架；此后每完成一个阶段就地回填对应字段，不另起新文件。
- 假设显式化：目标规范默认值、引用日期"待补"、未决占位符清单、lint 摘要
  （error/warning/info 计数）、往返 diff 结论，都写进契约允许的字段里。
- status 取值的唯一依据是事实：全部契约产物完成且 lint error 为零 →
  `"completed"`；有未决占位符但已如实声明 → 按契约约定填并附说明。

## 异常处理表

| 异常情形 | 处置 |
| --- | --- |
| 未知文献类型（如 `@weirdtype`、RIS `TY - XXXX`） | 按最近类型（misc → [Z]）渲染，lint 与渲染注记中显式标注，**不伪造成期刊条目** |
| BibTeX 宏无法解析（未定义 `@string`） | 保留原样（含宏名）并警告，**不手改**；resolved 值即宏名本身 |
| CNKI 导出缺字段（缺年、缺页、缺卷期） | 导入置空 → lint 登记 error/warning → 渲染 `[缺: X]` 占位符，链路全程留痕 |
| 目标规范未在 task.md 指明 | 按 GB/T 7714—2015 顺序编码制渲染，并在 result.json 中显式声明该假设 |
| 双语题名 / 双语元数据 | 都保留（`title` + `title_alt`），按任务要求选择主显，另一个不丢 |
| 渲染器不支持的构造（如报纸版次、专利号细化） | 如实报告"不支持/按简化模板渲染"，**不静默跳过、不硬套期刊模板** |
| 重复 citation key / 重复记录 id | 双保留并加后缀（`#dupN` / `~N`），警告登记，由人决定去重 |
| 中英混排标点冲突 | L7 只报告不改写；是否全角化由人按目标规范决定 |

## 最小调用示例（合成示例）

`examples/` 内为**全虚构合成数据**（刊名、出版社、DOI、人名均为虚构），演示完整
链路：导入（警告登记）→ lint（报出缺页码/缺年/标点混用，退出码 1）→ 渲染
GB/T 7714 顺序编码制与 APA 7（占位符可见）→ RIS 往返 diff 为零 → 修复库后
lint 通过（退出码 0）。详见 `examples/minimal_example.md`，运行产物在
`examples/output/` 与 `examples/output_fixed/`。

本地复现（相对路径；评测环境中用绝对路径 `/skills/weekly-skill/scripts/xxx.py`）：

```
python3 scripts/import_records.py --file examples/input/library.bib \
    --file examples/input/cnki_export.ris --file examples/input/cnki_text.txt \
    --out examples/output
python3 scripts/field_lint.py --records examples/output/records.json --out examples/output
python3 scripts/style_render.py --records examples/output/records.json \
    --style gbt7714-numeric --out examples/output/gbt7714.txt
python3 scripts/style_render.py --records examples/output/records.json \
    --style apa7 --out examples/output/apa7.txt
```

## 来源格式识别与保真细节

- **BibTeX**：`@string` 宏表逐字存于 `meta.bibtex_strings_raw`；字段同时给出
  resolved（宏已展开、保护花括号已去除——花括号在纯文本渲染目标下只起大小写
  保护作用，该行为已文档化）与 raw（`raw_fields` 中的原表达式，如
  `journal = jscis`）。宏重复定义保留首定义并登记。
- **RIS**：两位大写标签体系；`SP`/`EP` 合并为 `pages`（`55-62`）；`Y1` 中取首个
  4 位年份；`ID` 标签用于往返时还原记录 id；`M3` 承载 GB/T 类型标识；`M1`
  承载文章号。风味判定（standard-ris vs cnki-refworks）只影响报告，不影响映射。
- **CNKI 文本导出**：`题名/作者/来源/年/卷/期/页码/DOI/链接` 等键映射；
  `关键词/摘要/作者单位` 等未映射键 verbatim 进 `unmapped_fields`；因该格式不
  携带类型信息，一律默认期刊论文并挂警告，由人工按实际情况改 type/type_tag。
- **语言判定**：按题名/刊名粗判 zh/en/mixed/unknown，仅用于"等/et al."选择与
  L7 标点规则选择，不改写任何字段。

## 导出模式与视觉样式的关系

视觉样式（GB/T 与 APA 的参考文献表行）允许省略 DOI、URL、文章号、语言等元
数据；但 `--style ris|bibtex|csljson` 导出的数据文件**必须完整携带**这些内容，
以便下游工具（Zotero、EndNote、CSL 处理器）无损接收。"视觉上省略"绝不等于
"数据上丢弃"，这是本技能保真承诺的另一半。

## 预算内的执行策略

- 文献库条目较多时，lint 与渲染是对全库一次性批量执行的（脚本本身 O(n)），
  不会随条目数消耗额外工具调用；预算主要花在**读输入、写骨架、逐条目检与
  回填**上。
- 目检抽样策略：条目 ≤30 全检；>30 先全检含占位符与含警告的条目，再按类型
  各抽 2 条复检；把抽样范围写进 result.json。
- 每阶段结束立即落盘中件产物（records.json / lint_report / 渲染稿），即使后续
  阶段因预算中断，已落盘产物仍可支撑 `status: "partial"` 的诚实交付。

## 限制与适用范围

- 渲染器是**草稿生成器**，不是 GB/T 7714—2015 / APA 7 的规范验证器；输出必须
  逐条目检后方可交付。
- 不联网：DOI 只做语法检查（L2），不核验其真实存在性与元数据一致性；来源核验
  的实质判断超出本技能范围。
- BibTeX 解析为条目级自实现解析器：假设括号配对良好；引号值内出现不配对花括号、
  圆括号定界条目内嵌不平衡花括号等极端构造会降级为警告 + 截断，而非崩溃。
- 作者姓名结构按保守约定解析：有逗号按"姓, 名"；无逗号的拉丁多词姓名 GB/T 按
  "首词为姓"、APA 按"末词为姓"，均在 render_notes 中登记。复姓、贵族前缀
  （van/de/von）、机构作者需人工复核。
- APA 题名句首大写是保守策略（仅抬升首字母）；完整的 APA 大小写规范（冒号后
  首词、专名等）需人工微调。
- 报纸 [N]、专利 [P]、标准 [S]、档案等类型只有简化模板或按 [Z] 处理并标注。
- BibTeX 往返不承诺记录 id 逐字还原（citation key 字符集限制）；**官方往返规程
  使用 RIS（ID 标签保 id）或 CSL-JSON**，可做到核心字段级 diff 为零，详见
  `references/import_export_formats.md`。
- 仅标准库、无网络、输出确定性（排序固定、JSON 键序固定），同输入必同输出。
