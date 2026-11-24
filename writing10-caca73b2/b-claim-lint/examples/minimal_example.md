# 最小示例：从违规初稿到通过门禁

> 本示例为合成示例：案例、数据与草稿均为完全虚构，仅用于演示 claim-calibration-lint 技能的完整流程，不构成任何真实研究结论。文中所有命令与报告摘录均为真实运行结果（在 `skill/` 目录下以 `python3` 执行，Python 3.9+，仅标准库）。

## 一、示例素材

- `input/case.json`：合成案例 `SYNTH-EXAMPLE-001`，`output_contract` 含 5 个标准键（deliverable、preserved_facts、evidence_map、change_log、status）。
- `input/task.md`：任务说明。
- `input/materials/factsheet.md`：虚构事实底稿——两组盆栽玉米数据（株高、干重、叶片相对含水量、脯氨酸、丙二醛，均含 t 检验 p 值），另附未做趋势检验的剂量梯度。
- `input/draft_v0.md`：故意埋入违规的初稿（违反 R01、R02、R03、R04、R05、R07）。
- `input/draft_v0_sectionless.md`：无分节标题的变体，用于演示 `section_split.py`。

## 二、完整命令序列与真实结果

### 步骤 1：契约骨架

```bash
python3 scripts/result_contract.py init --case examples/input/case.json --out examples/output/result.json
# 退出码 0：已写出骨架（status=partial，占位值无法通过 check，用于尽早落盘诚实部分结果）
```

### 步骤 2：初稿审计（FAIL）

```bash
python3 scripts/claim_lint.py --draft examples/input/draft_v0.md --out examples/output/lint_report_v0
# 退出码 1
```

真实报告头部摘录（`output/lint_report_v0.md`）：

```
- 结论：**FAIL**（退出码 1）
- 未豁免违规：error 3 / warn 4 / info 0；已豁免 0；共 7 条

| 规则 | 名称 | 严重级 | 命中 | 已豁免 |
| R01 | 因果越界 | error | 1 | 0 |
| R02 | 无检验显著 | error | 1 | 0 |
| R03 | 结果段混入解释 | warn | 2 | 0 |
| R04 | 讨论段新数据 | error | 1 | 0 |
| R05 | 幅度夸大 | warn | 1 | 0 |
| R07 | 局限缺失 | warn | 1 | 0 |
```

典型违规条目（真实摘录）：

```
| R02 | error | 7 | 处理组株高为 47.8 cm，显著高于对照组的 42.3 cm（图1、表1）。 | 「显著」表述缺少统计支撑…… | 补入同句检验结果…… |
| R01 | error | 11 | 上述结果证明保水剂 H-2 决定了玉米幼苗的抗旱性。 | 疑似因果越界……因果动词「证明」 | 改写为相关/提示性表述…… |
| R04 | error | 11 | 处理组丙二醛含量降至 12.4 μmol/g…… | 讨论段出现结果段未报告的数据「12.4 μmol」…… | 先在结果段报告…… |
```

机器可读版本同场写出：`output/lint_report_v0.json`（含 `verdict`、`counts`、`per_rule`、逐条 `violations`）。

### 步骤 3：按报告修订初稿

依据行号逐条修复，产出 `output/draft_v1.md`：

- R01：「证明/决定了」→「提示……可能……」（推测级表述）；
- R02：株高句补「t 检验 p=0.032」，干重句写「差异不显著（p=0.41）」；
- R03：两句解释（与既往研究一致、可能是由于）从结果段移至讨论段；
- R04：丙二醛 12.4 μmol/g 先补入结果段，讨论段再引用；
- R05：脯氨酸句补效应量「约 49%」与 p=0.006；
- R07：讨论段末新增局限段落（样本量 n=6、分组未经随机化、单季盆栽外推限制）；
- 剂量梯度句采用边界对冲写法：「呈现剂量依赖趋势，但未进行趋势检验」（R06 合规）。

### 步骤 4：复检（PASS，含一条显式豁免）

修订稿讨论段保留了一句概括承接句「与脯氨酸大幅积累所反映的……相吻合」，触发 R05（warn）。其效应量已在结果段同句报告，属可豁免情形，故显式豁免：

```bash
python3 scripts/claim_lint.py --draft examples/output/draft_v1.md \
  --waive "R05:该句为讨论段的概括性表述，对应效应量（约49%）与检验（p=0.006）已在结果段同句报告，此处不再重复数字" \
  --out examples/output/lint_report_v1
# 退出码 0
```

真实报告头部摘录（`output/lint_report_v1.md`）：

```
- 结论：**PASS**（退出码 0）
- 未豁免违规：error 0 / warn 0 / info 0；已豁免 1；共 1 条

## 已豁免条目
| R05 | 11 | 处理组丙二醛含量（12.4 μmol/g）低于对照组…… | 该句为讨论段的概括性表述，对应效应量（约49%）与检验（p=0.006）已在结果段同句报告，此处不再重复数字 |
```

补充验证（真实运行）：对 draft_v0 仅豁免 R01 时退出码仍为 1（R02、R04 error 未豁免）；同时豁免 R01、R02、R04 后退出码变为 0；豁免不存在的规则号（如 R99）或空理由会被 argparse 拒绝。

### 步骤 5：无分节草稿的预分节演示

```bash
python3 scripts/section_split.py --draft examples/input/draft_v0_sectionless.md \
  --out examples/output/split_skeleton.md --moves examples/output/split_moves.json
# 退出码 0
```

真实归类结果：

```
P1 → 结果（数值词 4 个、统计证据词 0 个、解释标记 0 个（结果分 4，讨论分 0））
P2 → 讨论（数值词 2 个、统计证据词 0 个、解释标记 3 个（结果分 2，讨论分 6））
P3 → 讨论（数值词 0 个、统计证据词 0 个、解释标记 2 个（结果分 0，讨论分 4））
P4 → 待人工判断（数值词 0 个、统计证据词 0 个、解释标记 0 个（结果分 0，讨论分 0））
```

产物：`output/split_skeleton.md`（带 结果/讨论/待人工判断 三个标题的重组骨架）与 `output/split_moves.json`（段落 → 目标节 → 理由，可直接抄入 change_log）。

### 步骤 6：组装 result.json 并校验

按 output_contract 填写 `output/result.json`（deliverable 指向 draft_v1.md，preserved_facts 与底稿数值一致，change_log 记录全部修改与 R05 豁免理由），随后：

```bash
python3 scripts/result_contract.py check --case examples/input/case.json --result examples/output/result.json
```

真实输出：

```
[OK] case_id 一致；output_contract 全部 5 键在位且非空；status=success；sources/uncertainty 在位
PASS
# 退出码 0
```

## 三、产出文件清单（均为真实生成）

| 文件 | 说明 |
| --- | --- |
| `output/lint_report_v0.md` / `.json` | 初稿审计：FAIL，7 条违规（R01×1、R02×1、R03×2、R04×1、R05×1、R07×1） |
| `output/draft_v1.md` | 依据 v0 报告逐条修订的终稿 |
| `output/lint_report_v1.md` / `.json` | 复检：PASS，仅 1 条已豁免 warn（R05，理由在案） |
| `output/split_skeleton.md` / `split_moves.json` | section_split 对无分节变体的真实归类输出 |
| `output/result.json` | 通过 `result_contract.py check` 的契约结果 |
