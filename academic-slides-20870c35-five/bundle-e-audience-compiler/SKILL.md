---
name: audience-spec-compiler
description: 学术汇报内容组织 Skill，重心为中游定量规划——把"听众是谁、讲多久、几页、什么场合"的工作订单编译成可机器校验的 talk_spec.json（背景比例带、结论位置规则、语速模型、每页时间预算），再用确定性门控 S1–S6 校验 storyboard（页数契约、每页单主张、时间模型、叙事角色与顺序、背景比例、图表绑定），让"页数与时长脱节、按论文目录搬运、背景比例与听众错配、结论压尾、结果页裸奔"在建 deck 之前就被拦下。触发词：学术汇报、听众适配、时长规划、页数规划、叙事顺序、storyboard、评审汇报、答辩、组会；academic talk, audience adaptation, time budget, slide planning, narrative spine, storyboard gate, review/defense/group meeting。
---

# audience-spec-compiler：听众-时长-叙事契约编译

## 定位

大多数"学术 PPT 翻车"不是排版事故，而是**规划事故**：页数与时长脱节、按论文
目录逐节搬运、背景比例与听众错配、结论压到最后一页。本 Skill 把规划层机械化：

- `scripts/workorder_compile.py`：把工作订单（case.json + task.md）编译为
  `talk_spec.json`——六字段抽取（缺失即 TO_FILL + 记录默认假设）+ 推导杠杆
  （背景比例带、结论位置规则、语速模型、每页时间预算）。
- `scripts/storyboard_gate.py`：storyboard.json 对照 talk_spec.json 的确定性
  门控 S1–S6，exit 0 通过 / exit 1 违例并打印精确 S 编号 / exit 2 输入或
  schema 错误。**门控不过，不许建 deck。**

两个脚本均为 Python3 标准库实现，确定性输出（同输入同输出，无随机数与时间戳）。

## 环境假设与预算纪律

- 运行时输入：`/input/case.json` 与 `/input/task.md`，以及真实材料（PDF/PPTX，
  无预提取答案层；可能有模板 PPTX、起始 deck、slide-workorder）。**必须读真实
  文件内容，不得从文件名推断。**
- 工作目录 `/app/work`；最终产物与可编辑件放 `/app/output`，含 `result.json`
  （真实 case_id + case 的 `output_contract` 全部根字段**动态读取**，诚实
  status、sources、uncertainty、change records）。`output_contract` 字段名因
  案例而异，禁止硬编码。
- 预算：64 次模型请求 / 900 秒 / 每响应 16384 token。纪律：批处理 shell 命令、
  每阶段结束立即存盘、全量渲染至多两轮、门控失败按 S 编号定点修复而非整体重来。

## 六阶段案例执行协议

### Phase 0：契约 intake（先落盘，再读料）

1. `mkdir -p /app/work /app/output`；递归列出 `/input` 全部文件（类型、大小）。
2. 读真实 `case.json` / `task.md`；写 `/app/work/contract.json`：真实 `case_id`、
   `output_contract` 全部根字段名（原样记录，后续 result.json 严格对齐）、
   mode、页数、听众、时长、语言、模板与起始 deck 路径、要求的导出格式。
3. **立刻**写 `/app/output/result.json` 骨架：case_id 已填、其余字段 PENDING、
   `status: "partial"`——长跑任务任何时刻中断都留下诚实残件。
4. 工具普查：`pdftotext -v`、`pdftoppm -v`、`python3 -c "import pptx"`、
   `soffice --version`、`fc-list | head`，结果记入 contract.json 的 tools 区块；
   缺失工具决定后续降级路径，不得假装存在。
5. 运行编译器，把工作订单落成定量契约：

```bash
python3 /skills/weekly-skill/scripts/workorder_compile.py \
  --case /input/case.json --task /input/task.md \
  --output /app/work/talk_spec.json
```

   stdout 中 `[ACTION REQUIRED]` 列出的 TO_FILL 字段由你结合材料人工确认；
   `[ASSUMPTION]` 行是编译器已记录的默认假设，复核其合理性。talk_spec 的
   语义与默认值依据见 `references/audience-levers.md`。

### Phase 1：源材料索引与主线提取

1. 逐份 PDF 跑 `pdftotext -layout` 得逐页文本；关键图页用 `pdftoppm` 渲染目检
   （工具缺失则记录降级，绝不凭文件名猜图）。
2. 提取主线：`central_question` / `approach` / `results[]`（每条带 strength：
   strong/preliminary/contextual）/ `limitations[]`，每条带 locator
   （file, pdf_page, printed_page, section, exhibit）。
3. **数字连同单位与条件逐字转录**，登记成 source_index；后续 storyboard 的
   exhibit locator 必须能在 source_index 里找到对应条目。

### Phase 2：storyboard——先故事板，后幻灯片

1. 听众分析三问：他们的决策目标是什么、先验知识到哪、最可能质疑什么。
   talk_spec 的 audience/venue 杠杆给出定量边界，本步给出定性内容。
2. 按 `references/narrative-spines.md` 的场合脊柱撰写 `/app/work/storyboard.json`，
   每页五要素：**恰好一个 message**（单句）、**叙事角色**（受控词表）、
   **讲稿 notes**（按 `per_slide_seconds × wpm / 60` 词定量落笔）、
   **转场句**、**exhibit 绑定**（result/comparison 页必须 ≥1 个
   `{file, page, exhibit}` 定位器）。备用页 `backup:true`，单独计数。
3. 过门控，**exit 非 0 不得进入 Phase 3**：

```bash
python3 /skills/weekly-skill/scripts/storyboard_gate.py \
  --storyboard /app/work/storyboard.json --spec /app/work/talk_spec.json
```

   S1 页数契约（备用页不计）/ S2 每页单主张 / S3 时间模型（notes 词数→秒，
   总量在 [0.85,1.15]×时长内、每页备注≥下限）/ S4 角色词表与顺序（主干
   problem<approach<result<conclusion + 场合规则）/ S5 背景比例带 /
   S6 结果页图表绑定。违例按 S 编号定点修改后重跑本命令。

### Phase 3：建 deck——在真实模板内构建

1. `python-pptx` 可用则 `Presentation(template_path)` 在真实模板内逐页构建
   （版式按模板母版选择，不自造文本框堆叠）；不可用时用最小 stdlib OOXML
   兜底并在 result.json 记录降级。
2. Phase 2 的 notes 写入对应页 speaker notes；message 即页标题/核心句；
   每页在 notes 末尾保留 exhibit locator，保证页级证据可追溯。
3. 存在起始 deck 时在其上改写而非另起炉灶；每完成一轮写版本快照到 /app/work。

### Phase 4：渲染 QA——诚实降级，绝不伪造

1. `soffice --headless --convert-to pdf` 导出，再 `pdftoppm -png` 生成逐页预览，
   预览与可编辑件一起放 /app/output。
2. 检查：页数与 storyboard 一致、无空白页、文字不溢出、模板字体未被替换。
   发现问题修 deck 后重渲染，**修复回路至多两轮**，第三轮仍有问题则在
   result.json 如实记录未决项。
3. 无 soffice / 渲染失败：如实记录降级（"未渲染，原因 X"），绝不伪造预览图
   或声称已渲染。

### Phase 5：交付

1. 组装 `/app/output/result.json`：`case_id` 原样写入；`output_contract`
   的全部根字段**按 Phase 0 动态读到的字段名**逐一填充；`status` 诚实
   （completed/partial/blocked，partial 必须写明限制）；`sources` 列出真实
   材料路径；`uncertainty` 区分材料事实/推断/未知；`change_log` 记录每次修改
   （file/what/why）。
2. 交付物齐备：可编辑 deck、渲染 PDF/PNG 预览、storyboard.json、
   talk_spec.json、页级证据映射（exhibit locators ↔ source_index）。
3. 交付前自检：talk_spec 无未处理的 TO_FILL（或已在 uncertainty 声明）、
   storyboard_gate 最终 exit 0、result.json 字段与 output_contract 对齐。

## 编译器核心：workorder_compile.py

```bash
python3 scripts/workorder_compile.py --case case.json --task task.md \
  --output talk_spec.json [--wpm 130] [--cjk-cpm 240] [--min-slide-seconds 20]
```

- 六字段：audience / duration_min / slide_count(或区间) / venue / language /
  goal。case.json 结构化字段优先，task.md 文本正则后备（正则在脚本 docstring
  与 `references/audience-levers.md` §1 逐条文档化），冲突以结构化为准并记录。
- 缺失字段 → 值写 `TO_FILL`，推导照常使用**记录过的默认值**，并在
  `assumptions` 数组留痕——宁可显式假设，绝不静默编造。
- 推导杠杆写入 `derived`：背景比例带（specialist 0.05–0.15 / mixed
  0.15–0.30 / general 0.30–0.45）、结论位置规则（review⇒结论先行、
  defense⇒局限先于结论、group_meeting⇒方法进度为主）、语速模型
  （wpm/cjk_cpm/每页下限）、每页时间预算 = duration/slide_count、
  总时长带 [0.85,1.15]×duration。

## 门控核心：storyboard_gate.py（S1–S6）

| 码 | 语义 | 修复方向 |
|---|---|---|
| S1 | 主故事线页数须在 slide_count 区间（backup 单独计数） | 增删页或调整契约 |
| S2 | 每页恰好一个 message：非空、终止符 ≤2、无列表标记 | 拆页或改写单句 |
| S3 | 总时长 ∈ [0.85,1.15]×duration；每非备用页备注 ≥ 下限 | 增删备注、调页数 |
| S4 | 角色词表合法；problem<approach<result<conclusion；场合规则 | 重排角色序列 |
| S5 | 背景页（hook/problem/gap）比例在听众带内 | 压缩/补充背景页 |
| S6 | 每个 result/comparison 页绑定 ≥1 个 exhibit locator | 补 `{file,page,exhibit}` |

退出码：0 全过；1 任一违例（stdout 逐条 `S<n>: 详情`，并附逐页秒数统计）；
2 IO/schema 错误（slides 缺键、类型错误、talk_spec 缺 derived 等）。

## 场合脊柱速查（详见 references/narrative-spines.md）

- **review（评审）**：结论先行——hook→problem→approach→result(头条)→conclusion
  落在前 1/3，其后用 method/result/comparison/limitation 为已陈述的结论补证据。
- **defense（答辩）**：边界先于结论——limitation 必须在 conclusion 之前，
  创新点落进 approach/method 页的 message。
- **group_meeting（组会）**：方法与进度为主——背景压到带下限，method 与
  进度风险占主体，outlook 写清下一步与求助点。

## 可靠性与边界

- 时间模型是规划估计不是计时器：正式场合前仍需真人试讲一次校准 wpm
  （用 `--wpm` 回填个人语速）。
- S6 只校验 exhibit 定位器**存在且三键非空**；定位内容是否真实指向源材料的
  对应图/表，由 Phase 1 的 source_index 人工核对负责。
- 本 Skill 不管论文精读、学术写作成稿与科研绘图本身；它管从已有材料到
  可讲页面的**定量组织**。
- 完整可运行示例：`bash examples/run_example.sh`（合成埋雷变例证明门控会开火）。
