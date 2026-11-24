---
name: slide-qa-rehearsal
description: 面向"学术汇报内容组织"任务的问答预演工程 Skill：当需要把论文或研究材料组织成可上台的汇报（组会/答辩/评审场景，尤其听众会尖锐追问时）时调用。它在完成主线提取、页级 storyboard、模板建 deck、渲染 QA 与交付的完整流程之外，把"被追问时毫无准备"这一失败模式做成机器可核验的硬门控——用 stdlib 确定性脚本从 claim card 与听众质疑自动播种追问题库（机制/数据/对照/局限四类），再以 G1–G5 门控校验类别覆盖、回答要点与正页/备用页引用完整性、数字口径与 anchor 的逐字一致性、弱证据措辞纪律、听众质疑覆盖率，确保交付的每一场汇报都自带口径一致、可定位到页面的答辩预案。
---

# slide-qa-rehearsal —— 学术汇报问答预演工程

## 定位与重心

学术汇报最常见的翻车不在页面上，而在页面之后：评委追问机制、追问数据
稳健性、追问对照是否公平、追问结论边界时，讲者没有任何准备，或临时
编出一个与页面数字对不上的口径。本 Skill 的重心就是**答辩韧性工程**：
把问答准备从"临场发挥"变成"交付前必须过的机器门"。

完整的六阶段案例执行协议（Phase 0–5）保证从真实输入到合规交付不走样；
其中 **Phase Q（问答预演）是本 Skill 的机器核验重心**，由两个仅依赖
Python3 标准库的确定性脚本驱动：

- `scripts/qa_seed.py`：从 claim card 与听众质疑自动播种题库骨架；
- `scripts/qa_gate.py`：对题库执行 G1–G5 门控，exit 0 通过 / exit 1
  逐行报码 / exit 2 用法或 IO 错误。

模型只做判断类工作（读材料、写 claim、拟回答），机械可判定的检查全部
下沉到脚本，跑不过门就不许交付。

## 安装布局

```
/skills/weekly-skill/
├── SKILL.md                  本手册
├── scripts/
│   ├── qa_seed.py            题库播种（limitations / preliminary / objections）
│   └── qa_gate.py            题库门控 G1–G5
├── references/
│   ├── qa-taxonomy.md        四类追问分类学 + 三段式答题结构 + 备用页策略
│   └── bank-schema.md        claims / audience / deck_plan / qa_bank 字段契约
└── examples/                 合成示例（标注 SYNTHETIC EXAMPLE，可一键跑通，含埋雷变例）
```

下文统一记：

```bash
SKILL_DIR=/skills/weekly-skill
```

## Phase 0：契约 intake（先落盘，后思考）

1. 递归检查 `/input`，读**真实的** `case.json` 与 `task.md`，以及全部
   真实材料（PDF/PPTX/模板/起始 deck/slide-workorder）。材料没有预提取
   答案层，必须读真实文件内容，**不得从文件名推断内容**。
2. 在 `/app/work/contract.json` 记录：真实 `case_id`、`output_contract`
   的**全部根字段**（逐字段动态读出，禁止硬编码字段名）、mode、页数、
   听众、时长、语言、模板与起始 deck 路径、导出格式要求。
3. **立刻**在 `/app/output/result.json` 写入诚实 `partial` 骨架：`case_id`
   照抄 contract；每个 output_contract 根字段先占位；`status="partial"`；
   `sources` / `uncertainty` / `change_log` 置空待填；`limitations` 写明
   "交付进行中，各字段待回填"。此后每完成一个阶段就增量更新它——早存盘
   是预算纪律的一部分。
4. 工具普查：`pdftotext` / `pdftoppm` / `python3` / `python-pptx` /
   `soffice` / 可用字体，逐一实测（如 `command -v`），结果写进
   `contract.json`。缺失工具不假设、不伪造，降级路径见 Phase 3/4。
5. 预算纪律：总计 64 次模型请求 / 900 秒 / 每响应 16384 token。批处理
   shell 命令（一次响应内完成多步文件操作）、每阶段结束立即存盘、
   全量渲染至多两轮。问答预演的脚本调用很便宜，门控循环不占多少预算，
   真正的预算风险在渲染回修，要给它预留余量。

## Phase 1：源材料索引与主线提取（claims.json 的诞生地）

1. 对每份 PDF 用 `pdftotext -layout` 逐页抽文本；关键图页用 `pdftoppm`
   渲染成 PNG 目检（坐标、单位、图注是否被文本层丢失）。纯文本材料直接读。
2. 提取主线：`central_question` / `approach` / `results` / `limitations`。
   每条结果带 `strength`（established / preliminary / contextual）与
   `locator`（file / pdf_page / printed_page / section / exhibit）。
3. **数字连同单位与条件逐字转录**，不得凭记忆改写：它们成为 claim card
   的 `anchor`，是 Phase Q 里 G3 口径检查的比较基准。
4. 把主线落成 `/app/work/claims.json`（claim card：statement / kind /
   strength / locator / anchor / limitations / slide，契约见
   references/bank-schema.md）。每张卡的 `limitations` 数组要如实登记——
   它们是 qa_seed.py 的播种原料，藏着不报等于主动拆掉自己的 G1。

## Phase 2：听众与页级 storyboard（audience.json + deck_plan.json）

1. 听众分析落 `/app/work/audience.json`：决策目标、先验知识，以及——
   本 Skill 的关键动作——**预期质疑 objections**：站在听众立场，把
   "最可能被发难的点"逐条登记成带 id 的 objection（机制/数据/对照/
   局限各想几条）。刻意回避的质疑恰是答辩死穴，G5 会强制它们被覆盖。
2. 页级 storyboard 落 `/app/work/deck_plan.json`：每页恰好一个 message、
   叙事角色、时间片、转场句、图表绑定（exhibit locator）。正片页数服从
   契约；**备用页单独编目并显式标 `backup:true`**，不计入正片页数——
   备用页是答辩动线的一部分（"若被追问，切到 S-B1"），不是废稿。

## Phase 3：在真实模板内建 deck

1. 若提供了模板 PPTX 且 `python-pptx` 可用：`Presentation(template_path)`
   在真实母版/版式内逐页构建；不可用则用 bundle 外临时编写的 stdlib
   OOXML 兜底（zipfile + 手写 XML），并在 result.json 记录降级。
2. 每页讲稿备注写入 notes（讲稿 ≠ 页面复读，要写转场与口径提示）；
   每页保留证据 locator；高风险页在 notes 里注明对应备用页编号。
3. 每完成一轮构建做版本快照（复制带序号的中间件到 `/app/work`），
   改坏可回退。

## Phase Q：问答预演（本 Skill 的机器核验重心）

在 deck 成形、渲染之前，把答辩预案做成可过门的结构化题库。

### Q.1 播种（脚本驱动）

```bash
python3 "$SKILL_DIR/scripts/qa_seed.py" \
  --claims /app/work/claims.json \
  --audience /app/work/audience.json \
  --out /app/work/qa_bank_seed.json
```

播种规则（确定性）：每张 claim 的**每条 limitation 必生一题**（类别
limitation）；每张 **strength=preliminary 的 claim 必生一题**（类别
data，数据稳健性）；audience.json 的**每个 objection 落一题**并回填
`objection_ref`。种子题的 answer_points 是三段式占位（重述主张→证据
定位→边界声明，见 references/qa-taxonomy.md），**不可直接交付**。

### Q.2 扩写（模型判断）

把种子题扩成正式题库 `/app/work/qa_bank.json`，并补齐种子覆盖不到的
类别（G1 要求 mechanism/data/comparison/limitation 各 ≥1 题；若 claims
里缺少机制或对照素材，必须主动补题）。每题按三段式写 ≥2 条
answer_points；数字逐字照抄 anchor；弱强度 claim 用弱措辞；每道高风险
题指定 `primary_slide` 与 ≥1 张 `backup_slides`（必须指向 deck_plan 中
`backup:true` 的页）；`objection_ref` 逐条核对 audience.json。

### Q.3 门控（脚本驱动，循环至通过）

```bash
python3 "$SKILL_DIR/scripts/qa_gate.py" \
  --bank /app/work/qa_bank.json \
  --deck /app/work/deck_plan.json \
  --claims /app/work/claims.json \
  --audience /app/work/audience.json
```

- exit 0：打印 `GATE: PASS`，题库冻结，进入渲染 QA；
- exit 1：stdout 逐行打印 `G编号: 具体细节`，逐条修复后重跑；
- exit 2：用法/IO/schema 错误，检查路径与 JSON 合法性（schema 契约见
  references/bank-schema.md）。

**门控不过，不进入 Phase 4**：带着口径矛盾的答案去渲染，返工成本更高。

### 门控规则 G1–G5

- **G1 类别覆盖**：mechanism / data / comparison / limitation 每类 ≥1 题。
- **G2 引用完整**：每题 answer_points ≥2 条非空；`primary_slide` 存在于
  deck_plan；`backup_slides` 每条存在且该页 `backup:true`；`claim_ids`
  存在于 claims.json。
- **G3 口径一致**：回答文本中的"数字+单位"，若与所链 claim 的 anchor
  同单位，必须与其中某一个数值完全一致（NFKC + 空白归一，数值容差
  1e-9 相对误差）；同单位但谁都不等即判矛盾（如回答写 12.5% 而
  anchor 是 12.7%）。无单位数字不参与判定。
- **G4 强度纪律**：所链 claim 为 preliminary / contextual 时，回答文本
  不得含过强词 prove / proves / conclusive / definitively（英文词边界、
  大小写不敏感）/ 证实 / 确立了（中文子串）。
- **G5 质疑覆盖**：audience.json 每个 objection 被 ≥1 题的
  `objection_ref` 覆盖。

### 退出码约定（全部脚本一致）

| 退出码 | 含义 | 处置 |
|---|---|---|
| 0 | 播种成功 / 门控通过 | 进入下一步 |
| 1 | 门控违例（仅 qa_gate） | 读 stdout 逐行 `G编号: 细节`，修复重跑 |
| 2 | 用法 / IO / schema 错误 | 检查参数、路径、JSON 合法性 |

## Phase 4：渲染 QA（诚实降级，绝不伪造）

1. 有 `soffice`：导出 PDF，再 `pdftoppm` 出 PNG 预览逐页目检——页数与
   契约一致、无空白页、文字不溢出边界、字体无缺字方块、图未被裁切。
2. 无 `soffice`：如实把"无法本地渲染预览"写入 result.json 的
   `limitations` 与 `uncertainty`，保留可编辑源文件等待下游渲染；
   **绝不伪造渲染产物或谎称已渲染**。
3. 发现问题回 Phase 3 修复，**修复回路至多两轮**（预算纪律），超支则以
   诚实 partial 交付并写明残留缺陷。

## Phase 5：交付

补全 `/app/output/result.json`：真实 `case_id` + `output_contract` 全部
根字段（按 contract.json 的动态字段清单逐项核对）+ 诚实 `status`
（completed / partial / blocked；partial 必须逐字段写明限制）+
`sources` + `uncertainty` + `change_log`（file/what/why）。交付物齐备：

- 可编辑演示文件（含 notes 与备用页）+ 真实渲染的 PDF/PNG 预览；
- 页级证据映射（deck_plan.json 的 exhibits + 每页 locator）；
- 问答预演全套：claims.json、audience.json、qa_bank.json（已过 G1–G5）、
  门控日志。这套东西本身就是"答辩韧性"的可复核证据。

## 预算纪律

先跑脚本骨架再思考；一次响应多做事（intake + 工具普查 + result.json
骨架同一响应完成）；claims/audience/deck_plan 一次成形后再迭代；
渲染至多两轮；超支前按"砍渲染轮次 → 砍备用页美化 → 保题库过门"的
顺序收缩，最终以诚实 partial 兜底。门控循环（Q.3）每次只花一次 shell
调用，不要在两次门控之间做无关的重读材料。

## 确定性说明

`qa_seed.py` 与 `qa_gate.py` 无随机数、无时间戳、无网络访问，同一输入
重复运行输出逐字节一致（examples/run_example.sh 内含确定性复跑断言）。

## 异常与限制

- **门控管口径，不管真理**：G3 只保证回答数字与登记的 anchor 一致；
  anchor 本身抄错（Phase 1 转录失误）门控发现不了——转录纪律靠人。
- **G3 只判"数字+单位"token**：无单位数字（"Figure 2""3 台设备"）不参与
  判定；单位写法差异经 NFKC + casefold 归一，但 `ml/min` 与 `mL/min`
  之外的异体单位（如 `cc/min`）视为不同单位，不判冲突也不判一致。
- **G4 是词表法**：词表外的过强措辞（"毫无疑问""首次"）拦不住；
  反向误报也可能发生（如引用别人观点时出现 prove），需人工甄别。
- **G5 只查引用存在**：回答是否真正化解了质疑，门控不评判。
- **播种依赖诚实的输入**：claims 的 limitations 隐瞒不报、audience 的
  objections 敷衍登记，种子就会缺料——脚本只放大输入的诚实度。
- **环境限制**：脚本仅依赖 Python3 标准库（不 import 任何第三方包）；
  pdftotext/pdftoppm/soffice/python-pptx 的缺失按 Phase 3/4 的降级
  路径处理并如实记录；脚本不读不写 `/input` 与 `/app/output` 之外
  的路径假设，所有路径经命令行参数传入。
- **不适用场景**：无需问答环节的纯文档排版任务；源材料本身不可信或
  涉密无法登记 anchor 的场景；非学术汇报领域的追问分类需自行扩展
  references/qa-taxonomy.md 后再用。

## 自检

bundle 自带全合成示例（所有夹具标注 SYNTHETIC EXAMPLE），一键跑通
播种与门控，并证明 G1–G5 真的会开火：

```bash
bash "$SKILL_DIR/examples/run_example.sh"
```

预期：`qa_seed.py` 播种 8 题且覆盖 limitations / preliminary(C-04) /
objections(OB-1..3)，确定性复跑逐字节一致；`qa_gate.py` 对 good 题库
exit 0；对 bad 埋雷题库 exit 1 且输出精确含 G1（缺 limitation 类）、
G2（primary_slide S-99 不存在）、G3（12.5% 对 anchor 12.7%）、
G4（preliminary claim 配 proves）、G5（OB-2 未覆盖）；输入缺失 exit 2；
末尾打印 `ALL EXPECTATIONS MET`。
