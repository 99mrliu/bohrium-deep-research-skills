---
name: placement-surgeon
description: >-
  论断级引用位置外科。当任务要求把参考文献引用"挂对位置"——核查每个引用标记
  是否贴着它真正支撑的那句话（而非段末、邻句或图表注），并执行可回溯的
  移动/插入/移除修复时，必须调用本技能。典型场景：综述或论文稿件的引用位置
  审计、段末漂移与超距覆盖修复、图注误挂归位、未覆盖事实句补挂（含对照文
  献表中的未引用条目）、修复后全稿复审。不适用场景：纯文献著录格式转换
  （GB/T 7714 与 APA 互转但不移动任何标记）、文献内容真伪的事实核查、
  从零为无稿任务选题配文献、对 PDF/DOCX 原文件的直接版面级编辑（本技能只
  处理抽取出的文本层）。
---

# placement-surgeon：论断级引用位置外科

## 核心主张

引用管理的质量首先取决于"挂得对"：每一个引用标记都必须紧贴着它所支撑
的那个命题，而不是飘在段末、错挂在邻句、藏进图表注，或一个标记遥遥覆
盖五句话。位置错了，编号再齐、格式再规范也是误导读者。本技能把稿件切
成论断句，判定哪些句子需要来源支撑，用 P1–P6 六条规则审计现有标记的位
置质量，再把人工裁定后的结论编译成经过校验的"移动/插入/移除"计划，原
子地施加到稿件副本上，全程留下可回溯的变更图。所有插入都以"已有经核
验的来源"为前提——绝不为了填补位置而虚构引用，也绝不为了给引用找位置
而新增无来源论断。

## 运行时契约（必须先读）

在评测/运行环境中，严格遵守下列契约；任何一步违反都视为失败。

1. **逐文件读真实内容**：开工前逐个读取 `/input` 下的全部文件的真实内
   容（case.json、task.md、稿件、文献库导出等），不得凭文件名猜测内容。
   若存在 resources.yaml，先读它再读其余文件。
2. **中间产物与交付分离**：一切中间产物（sentences.jsonl、markers.jsonl、
   审计报告、diff 等）写入 `/app/work`；最终交付物（改后稿件、同步文献
   表、result.json）写入 `/app/output`。
3. **result.json 契约**：`/app/output/result.json` 必须包含逐字照抄的
   `case_id` 以及 `output_contract` 的**全部原始字段**（字段名与取值逐
   字照抄自 case.json，不得改写、增删或"翻译"）。
4. **骨架先行、逐阶段回填**：第一阶段（阶段 0）就写出 result.json 骨
   架——`case_id` 逐字照抄、契约字段先置 `null`、`status` 置
   `"in_progress"`；此后每完成一个阶段回填对应字段，不得等结束时一次
   性补写，以防中断后无据可查。
5. **预算**：全程至多 64 次模型请求、900 秒墙钟时间、单次响应至多
   16384 token。脚本确定性执行、不占模型请求，应尽量把机械工作交给脚
   本。
6. **诚实状态**：`status ∈ {success, partial, failed}`，如实填写；
   `partial` 必须逐条写明缺口（哪些 violation 未修复、原因是什么）。
7. **禁止伪造**：不虚构文献条目；不为给引用找位置而新增无来源论断；
   无对应来源的缺口只在审计报告标注 `[缺来源]`，不写入稿件。

### result.json 骨架示例（阶段 0 即写出）

```json
{
  "case_id": "<逐字照抄 case.json 的 case_id>",
  "status": "in_progress",
  "output_contract": {
    "<契约字段 1>": null,
    "<契约字段 2>": null
  },
  "notes": "骨架于阶段 0 建立，逐阶段回填；partial 时在此逐条写缺口"
}
```

- `case_id` 与 `output_contract` 的字段名逐字照抄，顺序尽量保持一致；
- 契约字段在完成对应交付物后回填真实值，不得留置 `null` 结项（除非
  `status` 为 `partial` 且在 `notes` 中说明原因）；
- 每次回填都重新写整个文件，保证任意时刻 result.json 都是合法 JSON。

## 工作流程（五阶段）

### 阶段 0：盘点与契约骨架

- 读取 `/input` 全部文件（含 resources.yaml，若存在）；确认稿件格式与
  任务边界（是否允许改稿、目标引用体系）。
- 在 `/app/work` 建工作目录；写 `/app/output/result.json` 骨架
  （`case_id` 逐字照抄、契约字段 `null`、`status:"in_progress"`）。
- 若稿件是 PDF/DOCX，先用可用工具抽取文本层到 `/app/work`（见"异常处
  理表"）。

### 阶段 1：论断切分与标记清点

```
python3 /skills/weekly-skill/scripts/claim_scan.py \
    --manuscript /app/work/manuscript.txt --out /app/work/scan
```

- 产出 `sentences.jsonl`（句 id、段落、区、线索、needs_support 初判、
  字符偏移）与 `markers.jsonl`（每个标记的原文、行列、所属句、区）。
- **人工/模型逐句复核分类**：脚本初判只是候选。逐句确认 needs_support
  标记是否恰当（常识句降级、隐性事实句升级），复核结论记入
  `/app/work/review_notes.md`。
- 若任务带来源台账，整理成 `intent.jsonl`（格式见
  `references/placement_plan_format.md`）。

### 阶段 2：位置审计

```
python3 /skills/weekly-skill/scripts/placement_audit.py \
    --sentences /app/work/scan/sentences.jsonl \
    --markers /app/work/scan/markers.jsonl \
    [--intent /app/work/intent.jsonl] --out /app/work/audit
```

- 产出 `placement_report.json/md`，含每条 violation 的规则、位置、证
  据摘录、建议动作（move/insert_mark/remove/split）；有 violation 时
  脚本退出码为 1。
- **逐条人工裁定**：对每条 violation 给出"接受/驳回"；驳回必须写理由
  （如"整段单一来源连续论述""图注自有版权来源说明"）。裁定依据见
  `references/placement_rules.md`。

### 阶段 3：修复计划与施加

- 按 `references/placement_plan_format.md` 编写 `/app/work/plan.json`：
  只包含被裁定接受的修复；每条操作写 `reason` 便于回溯。
- **纪律重申**：insert 的编号必须在文献表中已存在、经来源核验且与论
  断对应（典型情形：补挂文献表中的未引用条目）；否则只在审计报告标
  注 `[缺来源]`，不写入 plan。
- 校验并原子施加：

```
python3 /skills/weekly-skill/scripts/placement_plan.py \
    --manuscript /app/work/manuscript.txt \
    --plan /app/work/plan.json --out /app/work/apply
```

- 校验全部通过才写出 `edited_manuscript.txt` 与 `change_map.json`；任
  一失败整体不写盘（原子），退出码 2，按错误清单修 plan 后重试。

### 阶段 4：全稿复读与收口

- 对 `edited_manuscript.txt` **重跑阶段 1+2**：violation 应清零（退出
  码 0）；未清零说明 plan 不完整，回到阶段 3。
- **目检 `change_map.json` 的 diff**：确认除引用标记的插入/移动/删除外，
  引用跨度外文本零改动。
- 全稿复读一遍改后稿件，确认语句通顺、编号体例一致。
- 同步文献表（如有未引用条目已被补挂、或条目因 remove 变为未引用，如
  实在 result.json 与交付说明中报告）。
- 回填 `/app/output/result.json` 全部契约字段，`status` 如实填写；交
  付物写入 `/app/output`：改后稿件、同步文献表、审计报告与变更图
  （change_map.json）。

### 各阶段产物一览

| 阶段 | 产物（均在 /app/work，除注明外） | 退出码约定 |
|------|----------------------------------|------------|
| 0 | /app/output/result.json（骨架）、格式判定记录 | — |
| 1 | scan/sentences.jsonl、scan/markers.jsonl、review_notes.md | 0 |
| 2 | audit/placement_report.json/md、裁定记录 | 1=有违规，0=干净 |
| 3 | plan.json、apply/edited_manuscript.txt、apply/change_map.json | 0=施加，2=拒绝 |
| 4 | 复审报告（应 0 违规）、/app/output 全部交付物 | 0 |

### 阶段 1 人工复核检查单

脚本的 needs_support 只是初判，逐句复核时按以下清单打勾：

1. 常识句降级：尽人皆知的事实（如"艾滋病由 HIV 引起"在专科稿件中）可
   降级为不需要来源，但须在 review_notes.md 注明依据与目标期刊惯例。
2. 隐性事实句升级：无数字无线索词但含具体实体关系断言（"某酶催化某
   反应"）应升级为 needs_support。
3. 观点句确认：命中 opinion 线索的句子确认其确为作者观点而非转述。
4. 标记归属确认：抽查 markers.jsonl 中每个标记的所属句是否与版式一致
   （标记在句号前者归前句，在句号后者归后句，体例不同的稿件须注意）。
5. 台账整理：若任务提供来源台账或 BibTeX/RIS/CNKI 导出，把"来源→支撑
   论断"的对应关系整理为 intent.jsonl，供 P2 使用。

### 与其他引用管理技能的边界

- 本技能只回答"挂得对不对"（位置），并在修复时维护编号不被破坏；
- 著录格式转换（GB/T 7714—2015 顺序编码上标 ↔ APA 7 著者-年 ↔ 中英
  混排）、编号整体更新、文献去重、来源真伪核验由其他专门技能处理；
- 串联建议：先本技能把位置修对，再做编号更新与格式转换——位置变了，
  顺序编码的编号必然跟着变，顺序不可颠倒；
- 若同一任务同时要求格式转换，在 result.json 中分别报告两类改动，不
  得把格式改动混进 change_map.json 的 diff（本技能的 diff 只应出现标
  记位置的改动）。

## 位置规则 P1–P6 速览

精确定义、正反例与裁定规程见 `references/placement_rules.md`。

- **P1 段末漂移**：段落含 ≥2 个不同事实论断（锚点集不相交）而唯一标
  记挂在段末。修复：split/move，为每个独立论断各挂其源。
- **P2 错挂邻句**：标记所在句与台账（intent.jsonl）声明的支撑句不一
  致。无台账时跳过并注明。
- **P3 图表注误挂**：支撑正文论断的标记出现在图注/表注/脚注内。修复：
  move 回正文，或（图注自有来源时）remove。
- **P4 未覆盖论断**：含事实线索词/具体数字/专有名词结论的句子无任何
  标记，且全段无标记。修复：insert_mark（仅当有已核验来源），否则报
  告标 `[缺来源]`。
- **P5 超距覆盖**：一个标记覆盖 >3 句（标记句之后 ≥3 句无新标记）且
  中间出现新事实。修复：split，为出现新数据的论断句分别补挂。
- **P6 标记先于命题**：标记出现在其支撑命题之前的倒装嫌疑（标记句无
  事实线索而同段下一句是事实句）。minor 级，人工确认后 move。

## 异常处理表

| 异常情形 | 处理规程 |
|----------|----------|
| 稿件为非支持格式（PDF/扫描件等） | 先用可用工具抽取文本层到 /app/work，对文本层完成审计；在 result.json 中如实说明"只能交付审计报告与文本层改稿，无法回写原文件版面" |
| DOCX 稿件 | 提示并优先使用环境中可用的 Office 工具抽取文本；牢记"文本抽取不等于忠实编辑"，批注/修订/域代码会丢失，交付时注明该限制 |
| plan 锚点匹配失败（句 id 不存在、marker 原文找不到、anchor_text 不唯一） | placement_plan.py 拒绝施加、不写任何输出并列出全部错误；按错误修正 plan 重试，禁止绕过校验手工改稿 |
| 任务禁止改动原文 | 只交付审计报告（placement_report.json/md 与人工裁定记录），不运行施加阶段；result.json 注明"仅审计未改稿" |
| 一句多引 | 合法，前提是该句每个编号都支撑同一命题；审计按单个标记处理，plan 用 marker 原文精确串定位 |
| 多句一引 | 仅当这些句子属同一来源连续论述（回指、无新锚点）时合法，标记挂最末句；跨 >3 句仍按 P5 审查 |
| 编号体系不明（既有 [n] 又有 (作者, 年) 混排） | 先按发现的原样登记到 markers.jsonl（kind 字段区分 numeric/author-year），不臆测、不擅自统一；在报告中如实列出两种体系并请示任务要求 |
| 参考文献节识别失败 | claim_scan.py 以"参考文献/References"整行标题识别；识别失败时文献条目会被误当正文，应先用人工方式确认分节再扫描 |

## 常见裁定问答

**问：段末一个标记，整段都在讲同一项研究，报警了怎么办？**
答：按 P1 反例驳回，理由写"整段单一来源连续论述"。若脚本仍报警，说明
段内出现了不相交锚点（如复述中引了第二个年份），此时应逐句人工核对：
确属同源则驳回并在 review_notes.md 记录；否则接受。

**问： violation 建议 insert_mark，但文献表里没有对应条目？**
答：不生成 insert 操作。在审计报告中把该论断标注 `[缺来源]`，并在
result.json 的 notes 里逐条列出缺口；`status` 视缺口数量填 `partial`。

**问：move 之后原位置的句子会不会变成未覆盖论断（P4）？**
答：可能。阶段 4 的复审正是为此设：重跑审计若出现新 P4，回到阶段 3
为该句补挂已核验来源（或标 `[缺来源]`），直到复审清零或如实报 partial。

**问：一句里既有事实又有观点，怎么判？**
答：按事实句处理（needs_support=true）；标记应贴在事实成分之后、句末
之前。若事实与观点难分，按更严格的一侧处理并记录理由。

**问：标记在句号之后（"……。[5]"）体例的稿件？**
答：claim_scan.py 会把该标记归到下一句，可能触发 P6。此时先在
review_notes.md 记录该稿件的体例约定，人工按"标记归前句"解读审计结
果；不要为迁就脚本而改动稿件体例。

## 故障排查

- **claim_scan.py 退出码 2**：稿件路径错误或不是 UTF-8；用
  `file`/`iconv` 确认编码后重试。
- **切句异常（句子被切碎或合并）**：检查是否含未保护的缩写点号或
  "；"长句；必要时在人工复核阶段按语义合并/拆分并在 review_notes.md
  记录，plan 的锚点以记录后的句 id 为准（需重跑扫描刷新）。
- **placement_plan.py 退出码 2**：阅读 stderr 的错误清单，逐条修正
  plan（句 id 打错、marker 原文含不可见字符、操作重叠是最常见的三类）；
  被拒绝时不会产生任何输出文件，可放心重试。
- **复审仍非零**：对照新报告逐条处理；忌讳为"清零"而删除合理标记或
  改动正文，宁可 partial。

## 最小调用示例（合成示例）

`examples/` 内含一篇**全部虚构**的中文小综述（3 节 + 1 图注 + 文献表），
植入了恰好 4 个位置缺陷（P1、P3、P4、P5 各一），另有一段"整段单一来
源连续论述"作为不应报警的对照。完整命令、预期退出码与真实运行产物见
`examples/minimal_example.md` 与 `examples/output/`。本地复现时把脚本
路径换成相对路径 `python3 scripts/xxx.py` 即可。

## 限制与适用范围

- 只处理 UTF-8 文本/Markdown 层；不直接编辑 PDF/DOCX 版面。
- 只解决"位置"问题：不做文献内容真伪核查、不做编号体系换算、不做著录
  格式转换（这些可与其他技能串联）。
- 切句与线索词为启发式，初判必须经过人工/模型复核；P6 仅为提示级。
- 规则阈值（如 P5 的 3 句上限、专有名词 ≥3 词元）定义在脚本顶部，调
  整须在报告中说明依据。
- 插入修复以"文献表中已有对应已核验来源"为硬约束；本技能不会、也不应
  被用来编造来源。

## 文件清单

```
SKILL.md                          本文件
README.md                         一页概述
scripts/claim_scan.py             阶段 1：论断切分与标记清点
scripts/placement_audit.py        阶段 2：P1–P6 位置审计
scripts/placement_plan.py         阶段 3：计划校验与原子施加
references/placement_rules.md     P1–P6 精确定义与裁定规程
references/placement_plan_format.md  plan/change_map/intent 字段级格式
examples/input/manuscript.txt     合成示例稿件（全部虚构）
examples/input/plan.json          合成示例修复计划
examples/minimal_example.md       命令步骤与预期
examples/output/                  真实运行产物
```
