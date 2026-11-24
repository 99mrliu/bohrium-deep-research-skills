---
name: gap-tribunal
description: 以缺口审计与冲突裁决为核心的"方法与实验章节"写作技能：六要素证据审计、多源参数冲突矩阵、套话与静默填平检查，保证章节可信、缺口说得住。
---

# gap-tribunal：缺口追问与冲突裁决

## 1. 用途

在材料不完整、取值互相矛盾的真实科研写作场景中，"方法与实验章节"的可信度有两大杀手：

1. **材料缺口被静默填平**——作者（或模型）用"典型值""一般认为"补齐没有来源的
   步骤、参数、数据集信息；
2. **冲突被悄悄选边**——同一参数在配置、日志、草稿、论文中取值不同，正文只写
   其中一个，不留任何裁决痕迹。

本 Skill 把缺口与冲突提升为一等公民，提供三件确定性工具（纯标准库、无网络）：

- `scripts/gap_audit.py`：按六要素清单扫描全部材料，给出每要素的证据状态
  （sufficient / thin / missing）与命中证据的 file:line 定位，并为每个非充足要素
  生成编号追问项（G001、G002……）；
- `scripts/conflict_matrix.py`：从多源文本中抽取"键=值"型参数，按键归组，
  跨来源取值不一致时输出冲突记录与裁决建议；同文件同键的值序列（训练曲线等）
  只记为观测，不误报为冲突；
- `scripts/hedge_scan.py`：完稿后扫描章节，检查空泛限制套话、无来源数值
  （静默填平嫌疑）、缺口是否全部被"待作者确认"段点名，FAIL 时退出码非零。

适用对象：依据 `/input/case.json` 与 `/input/task.md` 及随附材料撰写
"方法与实验章节"的智能体；亦适用于任何需要"说得住"的实验文档写作。

## 2. 运行时契约（必须遵守）

1. **读实际内容，不凭标签猜**：动手前必须通读 `/input/case.json` 与
   `/input/task.md` 的实际字段与正文，以及材料目录中的配置、日志、代码、
   草稿、PDF 提取文本。文件名与标签仅作索引，不作为内容依据。
2. **目录约定**：工作文件写入 `/app/work`（中间产物 gaps.json、conflicts.json、
   章节草稿等）；最终产物写入 `/app/output`；`/app/output/result.json` 必须包含
   `case_id` 与 `output_contract` 要求的全部字段，字段名与类型以
   `/input/case.json` 的 `output_contract` 实际定义为准。
3. **诚实状态**：材料缺失、无法判断、运行失败三类情况必须分别说明，不得混同；
   只能部分完成时状态记为 partial，并逐条标明局限；任何情况下不编造数值、
   版本、引用或来源定位。
4. **尽早保存部分产物**：每完成一个阶段（审计、冲突矩阵、草稿、检查、装配）
   立即落盘到 `/app/work` 或 `/app/output`，防止预算耗尽时颗粒无收。
5. **产物四要件**：最终章节产物须包含来源定位（file:line）、修改记录、
   不确定性说明、人工确认项（"待作者确认"段，逐条引用 G 编号）。
6. **六要素覆盖**：章节必须覆盖步骤、实验设置、参数与来源、数据集与划分、
   对照、复现与限制六个要素；证据不足的要素不得省略，改写为缺口陈述。

## 3. 调用步骤

设材料目录为 `$MAT`（通常由 /input 下材料整理到 /app/work/materials），
工作目录为 `/app/work`，输出目录为 `/app/output`。

### ① 缺口审计

```bash
python3 scripts/gap_audit.py --materials "$MAT" \
    [--draft /app/work/draft.md] --out-dir /app/work
```

阅读 `/app/work/gaps.json` 与 `gaps.md`：

- `elements[*].evidence_status`：每要素 sufficient / thin / missing；
- `elements[*].hits`：命中证据的 file:line 与片段，写作时的来源定位据此填写；
- `gaps[*]`：编号缺口清单（G001…），含追问措辞建议，原样或改写后进入
  "待作者确认"段。

### ② 冲突矩阵

```bash
python3 scripts/conflict_matrix.py --materials "$MAT" --out-dir /app/work
```

阅读 `/app/work/conflicts.json`：

- `conflicts[*]`：参数名、各来源取值（file:line）、建议裁决规则、是否阻断；
- `observations[*]`：同文件同键多值的时间序列，**不是冲突**，写作时不得当作
  冲突处理；
- 裁决规则与双值并陈条件见 `references/adjudication_rules.md`；
  缺口分类与追问措辞模板见 `references/gap_taxonomy.md`。

### ③ 模型写作

依据 gaps.json 与 conflicts.json 撰写章节（草稿先存 `/app/work/chapter_draft.md`）：

- 六要素齐备；证据充足处正常成文，数值后标注来源（如 `train.log:1`）；
- 冲突参数：满足双值并陈条件时，正文同时写出各来源取值，再给裁决结论与依据；
  未决的阻断性冲突相应小节标 partial；
- 缺口：不设法定夺处写"待作者确认（G00x）"，汇总为文末"待作者确认"段，
  逐条引用 G 编号，措辞可参照 `references/gap_taxonomy.md` 第 3 节模板；
- 限制段：每条限制必须指向具体失效场景（何种数据、何种条件、何种度量下失效、
  失效表现），禁止空泛套话。

### ④ 套话与静默填平检查

```bash
python3 scripts/hedge_scan.py --md /app/work/chapter_draft.md \
    --materials "$MAT" --gaps /app/work/gaps.json --out-dir /app/work
```

- 退出码 0（PASS）方可进入装配；
- 退出码 2（FAIL）：按 `hedge_report.json` 逐项修复——套话改写为具体失效场景，
  无来源数值补来源或改写为"待作者确认"，未点名的 G 编号补入"待作者确认"段，
  然后重新运行本步。

### ⑤ 装配 result.json

将最终章节写入 `/app/output`（文件名按 output_contract 要求），并装配
`/app/output/result.json`：

- `case_id`：照抄 `/input/case.json`；
- `output_contract` 全部字段：逐一核对，不缺键、不改型；
- `uncertainty`（或契约规定的等价字段）：如实列出全部缺口（G 编号、要素、
  状态）与全部冲突（参数、各来源值、裁决结论、是否阻断、确认状态）；
- 修改记录：列出对草稿的每处实质性修改及其依据；
- 状态字段：complete / partial / failed，与实际完成情况一致；
  partial 时逐条说明局限。

## 4. 工具输出规格

### 4.1 gaps.json（gap_audit）

| 字段 | 含义 |
| --- | --- |
| `files_scanned` | 实际纳入证据池的文件清单（相对路径，确定性排序） |
| `elements[*].key / label` | 要素键（steps/setup/params/dataset/baselines/repro）与中文名 |
| `elements[*].evidence_status` | `sufficient` / `thin` / `missing` |
| `elements[*].hits` | 命中证据：`file`、`line`、`probe`（命中的探针名）、`snippet` |
| `elements[*].must_satisfied` | 该要素关键面向（如数据集"版本与获取"）是否命中 |
| `gaps[*]` | 编号缺口：`id`（G001…）、`element`、`status`、`question`（追问措辞） |
| `summary` | 缺口总数与三档状态的要素清单 |

判定阈值（与 `references/gap_taxonomy.md` 第 1 节一致）：0 命中 = missing；
≥3 命中且覆盖 ≥2 类探针且 must 面向满足 = sufficient；其余 = thin。

### 4.2 conflicts.json（conflict_matrix）

| 字段 | 含义 |
| --- | --- |
| `pairs_extracted` | 抽取到的"键=值"对总数 |
| `conflicts[*].parameter` | 归一化后的参数名（epoch/epochs/num_epochs 等归并为 epochs） |
| `conflicts[*].blocking` | 是否关键参数（epochs、lr、batch_size、seed、划分比例等） |
| `conflicts[*].sources` | 各来源取值：`file`、`line`、`value_raw`、`source_type` |
| `conflicts[*].suggested_rule` / `recommended_value` | 裁决建议与建议取值 |
| `observations[*]` | 同文件同键多值的时间序列，附"非冲突"说明 |

### 4.3 hedge_report.json（hedge_scan）

| 字段 | 含义 |
| --- | --- |
| `verdict` | `PASS` / `FAIL`（FAIL 时进程退出码为 2） |
| `hedge_hits` | 套话命中：行号、模式编号（ZH01…/EN01…）、片段、修改建议 |
| `unsourced_numbers` | 无来源数值：行号、数值、片段 |
| `gap_coverage` | G 编号点名核对：`ok_ids` / `missing_ids` |

## 5. 写作检查清单（六要素 × 工具产出对照）

落笔前逐行核对，任一答案为"否"即存在待确认项：

- 步骤：每一步是否有命令行或编号步骤证据（gaps.json 中 steps 为 sufficient）？
- 实验设置：硬件、框架版本、随机种子是否各有 file:line 来源（setup 探针三组）？
- 参数与来源：每个写进正文的数值是否都能指到 config/log/脚本（params +
  conflicts.json 无未决冲突）？
- 数据集与划分：名称、划分比例、样本数之外，**版本与获取方式**是否有证据
  （dataset 的 must 面向）？
- 对照：基线名称、来源、配置是否齐备（baselines 非 thin/missing）？
- 复现与限制：运行命令、依赖、数据获取途径是否可复现；限制是否逐条指向
  具体失效场景（hedge_scan 套话项为零）？

## 6. 预算分配建议（64 请求 / 900 秒）

1. 读 case.json、task.md 与材料清单：约 2–4 请求；
2. 步骤①②（脚本运行与结果阅读）：约 2–3 请求；
3. 步骤③（写作，含六要素与待确认段）：约 3–6 请求，每写一节落盘一次；
4. 步骤④（扫描—修复—复扫，通常 1–3 轮）：约 2–6 请求；
5. 步骤⑤（装配与核对 result.json）：约 1–2 请求；
6. 预留 ≥2 请求处理异常与最终自检。

## 7. 异常处理

| 异常 | 处理 |
| --- | --- |
| 材料目录不存在或为空 | gap_audit 全部要素判 missing；章节只写"材料缺失"陈述与待确认段；result.json 状态 partial 或 failed，并说明 |
| 材料格式不可解析（PDF 提取失败、二进制损坏） | 记为"权限不足/不可读"类缺口（见 gap_taxonomy 第 2 节），不猜测内容 |
| gap_audit / conflict_matrix 非零退出 | 记录 stderr 到修改记录；降级为人工阅读材料，手工填写缺口与冲突；状态标 partial |
| hedge_scan 反复 FAIL 且预算紧张 | 优先修"无来源数值"与"未点名 G 编号"（影响诚实性），套话次之；每轮修复后先落盘再重扫 |
| 冲突双方优先级相同且无法互证 | 双值并陈，不裁决，记为"无法判断"类缺口，写入待确认段 |
| gaps.json 缺失时运行 hedge_scan | 工具跳过 G 编号核对并告警；不得因此声称缺口已覆盖 |
| 预算（64 请求 / 900 秒）不足 | 立即将当前 gaps.json、conflicts.json、最佳草稿、部分 result.json 落盘 /app/output，状态 partial |

## 8. 最小合成示例

`examples/` 内置合成示例（**非正式案例结果**）：

- `examples/case/config.yaml`：`epochs: 300`，且只有数据集名（cifar10）无版本；
- `examples/case/train.log`：首行 `epochs=500`（与配置冲突），含逐 epoch 的
  `loss=` 序列（应判为观测而非冲突）；
- `examples/case/draft.md`：含空泛限制句"在某些情况下可能不适用"与一个
  无来源数值（基线准确率 91.7%）。

一键运行：

```bash
bash examples/run_example.sh
```

产物写入 `examples/expected/`。预期：gap_audit 判 dataset 为 thin（缺"版本与获取"
面向）并生成 G 编号；conflict_matrix 抓到 epochs 冲突（建议取日志值 500，
blocking=true）且 loss 序列列为 observation；hedge_scan 抓出套话、91.7 无来源、
G 编号未点名，退出码 2（FAIL，演示预期行为）。详见 `examples/README.md`。

## 9. 边界

- 三个脚本为**确定性启发式**：关键词/模式探针可能漏检（表述冷僻时）或误检
  （如同名不同义）；工具输出是审计起点，不替代对材料本身的通读与判断。
- `conflict_matrix.py` 只抽取**数值型**取值；非数值参数（模型名、数据路径）
  的冲突需人工比对。
- "同文件同键多值 = 观测"的规则可能掩盖同一文件内的真实配置变更
  （如同一日志里两次不同 run）；此时应人工拆分来源后再运行。
- `hedge_scan.py` 的无来源数值检查以"词边界精确匹配"判来源，单位换算
  （0.8 vs 80%）或改写（300 vs 三百）会被判为无来源——这是刻意的保守取向，
  命中后由写作者补来源或改写，而非放宽检查。
- 套话模式表可按领域扩展（编辑 `HEDGE_PATTERNS`），但删除内置模式会削弱
  检查强度，须在修改记录中说明。
- 本 Skill 不提供文献检索与事实核查；涉及外部知识的主张仍需作者确认。
