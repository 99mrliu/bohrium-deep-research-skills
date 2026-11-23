---
name: measurement-forge
description: >-
  多文档比较与整合的"抽取工程/数值-单位-口径同源绑定"技能：把每个定量单元格铸成测量记录
  (value+unit 解析为 SI 量纲向量与换算因子+quantity_kind 受控登记+metric_definition 口径随值走
  +condition_context 条件窗+逐字 quote+doc/paragraph)，机检强制口径随值走、quantity_kind 不同
  直接判不可比、单位可换算时给换算值但保留原值原文。当输入含 comparison-workorder.json /
  case.json 与多篇论文语料时使用。
---

# measurement-forge — 数值-单位-口径同源绑定的多文档比较

## 设计立场

多文档比较的错误大头是**数值格**：单位丢了、口径（公式/仪器/数据集版本）没随值走、把降解率 % 和速率常数 k 当成一个量比较。本 Skill 的立场是：**每个定量单元格都必须铸成一条测量记录**，口径随值走由机检强制，而不是靠 agent 自觉。

一条测量记录 =

```
value + unit(解析成 SI 量纲向量与换算因子) + quantity_kind(受控登记)
+ metric_definition(公式或仪器口径) + condition_context(同句/同段条件窗)
+ 逐字 quote + source_document_id + paragraph_id
```

核心规则（全部由 `scripts/validate_measurements.py` 机检强制）：

1. **口径随值走**：`status="reported"` 的记录没有 `metric_definition` 不得进入比较（机检直接报错退出）。
2. **quantity_kind 不同 → 不可比**：机检直接判不可比，不进入同一比较组。降解效率 % 与速率常数 k (min⁻¹) 是两个量，即使在同一篇论文里也不可互换。
3. **单位可换算 → 给换算值但保留原值原文**：换算值一律标 `derived`；量纲不同 → 不可换算，保留原值不合并。
4. **先机器提候选、后 agent 判读**：`extract_candidates.py` 在段落索引上自动提出候选测量记录（value/unit/所在句/条件词提示），agent 的职责是逐条确认、补口径、标 status，减少漏抽。
5. **诚实性**：数值只能来自原文；quote 必须逐字落地（机检查 quote 是否逐字出现在对应段落）；值串出现在他篇则告警（防跨论文誊抄）。

## 第 0 步：输入识别

评测时的平台运行契约（本 Skill 按此编写）：

- 输入在 `/input`：`case.json`、`task.md`、`comparison-workorder.json`（组织方 v2 接口）以及语料文档。
- 语料可能是**真实 PDF，无预提取答案层**：
  - 先 `pdftotext /input/<file>.pdf /app/work/<file>.txt`；
  - 失败（扫描件）再 `pdftoppm -r 300 -png` 渲染 + OCR（如 `tesseract`）；
  - 表格区可用 `pdftotext -layout` 辅助保留列结构。
- **中间产物放 `/app/work`，最终交付放 `/app/output`**。
- 预算：**64 次模型请求、900 秒**。先交候选抽取 + 骨架台账，再逐条确认；随时可诚实 `partial`。
- 本 bundle 不含任何官方正式案例答案；`examples/` 是合成示例。

识别顺序：

1. `ls /input` 看有哪些文件；读 `case.json`（取 `case_id` 与 `output_contract`）、`task.md`、`comparison-workorder.json`（取比较任务、目标文档、维度要求）。
2. 语料是 PDF → 按上文转文本；是 txt/md → 直接用。
3. 决定产物路径：`/app/work/measurements.jsonl`（工作台账）、`/app/output/`（最终交付）。

## 工作流程

### 阶段 1：建段落索引

语料必须带 `paragraph_id`，所有 quote 核验都依赖它。

```bash
mkdir -p /app/work /app/output
# 若已是 jsonl 段落索引则跳过; 否则由裸文本/markdown 建索引(空行分段):
python3 scripts/extract_candidates.py --corpus /app/work/DOC-*.txt --doc-prefix "" \
    -o /app/work/_discard.jsonl   # 仅为建索引时也可直接用 --corpus; 推荐先显式建索引:
# 显式索引(自行写一个 5 行 python 或用 jq):
python3 - <<'EOF'
import json, glob, re, os
out = open('/app/work/paras-index.jsonl', 'w', encoding='utf-8')
for path in sorted(glob.glob('/app/work/DOC-*.txt')):
    doc = os.path.splitext(os.path.basename(path))[0]
    for i, blk in enumerate(re.split(r'\n\s*\n', open(path, encoding='utf-8').read()), 1):
        blk = re.sub(r'\s*\n\s*', ' ', blk.strip())
        if blk:
            out.write(json.dumps({"document_id": doc, "paragraph_id": f"P{i:03d}", "text": blk}, ensure_ascii=False) + '\n')
EOF
```

### 阶段 2：机器提候选（不判读）

```bash
python3 scripts/extract_candidates.py --paras /app/work/paras-index.jsonl \
    -o /app/work/candidates.jsonl
```

输出每行一条候选：`candidate_id / document_id / paragraph_id / quote(所在句逐字) / value_raw / value / unit / unit_status(parsed|unparsed|none) / window(整段) / condition_hints / status="proposed"`。

### 阶段 3：agent 逐条确认（你的核心工作）

对每条候选：

1. **取舍**：噪声（年份、图号、仪器型号数字）标 `status="excluded"`；真正的测量值保留。
2. **绑定 quantity_kind**：从 `references/quantity-kinds.json` 选恰好一个量类（≥8 类已登记：degradation_efficiency / rate_constant / concentration / catalyst_dosage / irradiation_time / light_source_power / wavelength / specific_surface_area / band_gap / temperature）。登记表里没有的量类不要硬凑——保留记录并在 note 说明。
3. **补 metric_definition（口径随值走）**：公式（如 η=(C0−Ct)/C0）或仪器口径（测定波长、仪器型号、拟合模型与区间）。没有口径的 reported 记录**机检不过**。
4. **补 condition_context 与 conditions**：同句/同段条件窗；`conditions` 对象给出四个维度的取值：`task / material / pollutant / budget`（缺失维留空，机检在矩阵里标 `unreported`）。
5. **核对 quote 逐字**：quote 必须逐字出现在 `(document_id, paragraph_id)` 的段落文本里；value_raw 必须出现在 quote 里。
6. 写入 `/app/work/measurements.jsonl`（每行一条，字段见 `scripts/validate_measurements.py` 头注释）。

### 阶段 4：机检

```bash
python3 scripts/validate_measurements.py /app/work/measurements.jsonl \
    --paras /app/work/paras-index.jsonl
```

机检项（违反即非零退出）：必填字段、quote 逐字落地、value_raw 在 quote 中且与 value 一致、unit 可解析（或显式 `unregistered_unit_accepted`）、quantity_kind 合法、reported 必带 metric_definition。告警项：跨论文值串（疑似誊抄）、condition_context 为空。**机检不过就不进比较。**

### 阶段 5：渲染台账 / 矩阵 / result 骨架

```bash
python3 scripts/render_ledger.py /app/work/measurements.jsonl \
    --case /input/case.json --workorder /input/comparison-workorder.json \
    --outdir /app/output
```

产物：

- `measurement-ledger.md`：按 quantity_kind 分组，列 = 原值 | SI换算(derived) | 单位 | 口径 | 条件窗 | doc | paragraph | quote。
- `comparison-matrix.md`：按 quantity_kind 分组的数值视图（原值列保留原文，"换算到规范单位"列标 derived），每组附**六维度可比性判定**：`task / metric / units / material / pollutant / budget`——其中 **units 与 metric 两维由单位代数与口径串自动判定**，其余四维由 agent 填的 `conditions` 比对；quantity_kind 不同的组之间直接列出"不可比"。
- `result.json` 骨架：`case_id` 原样复制；`case.json` 的 `output_contract` **全部字段名原样照搬**（值由你填写）；`status / sources / uncertainty / comparability` 预填机器可判部分。

### 阶段 6：完成 result.json（v2 强制要求）

- `result.json` 必须含：`case_id`（原样复制）、`case.json` 的 `output_contract` 全部字段（字段名原样照搬）、`status ∈ {success, partial, failed}`、`sources`、`uncertainty`。**partial 必须写明缺失边界**（哪些文档/哪些量类没抽完、为什么）。若 case.json 无 `output_contract`，退化为 `{case_id, status, 主结果, sources, uncertainty}`。
- **覆盖全部语料论文的共同字段比较矩阵**，每格带 exact `source_document_id` 与 `paragraph_id`。
- **在任何定量合成之前检验六个维度的可比性**（task/metric/units/material/pollutant/budget）；units 与 metric 已由机器判，其余四维以 `conditions` 为准。
- **不得合并不同数据集或不同染料**；保留不可比与未报告项（不删除、不估算）。
- 单篇摘要不满足多文档比较——结论必须基于矩阵中 ≥2 篇的可比格。

## 异常处理

| 异常 | 处置 |
|---|---|
| 单位无法解析（未登记写法，如 `mL/min/cm²`、`quanta`） | 记录保留**原单位原文**，置 `"unregistered_unit_accepted": true`，**不换算**；台账 SI 列显示 `unregistered(不换算)`；机检 WARNING，agent 在 note 里说明并建议登记 |
| 表格跨页 | 用 `pdftotext -layout` 分段重提；跨页表头在 condition_context 里补全；quote 取数值实际所在页的那一行，paragraph_id 指向该行所在段 |
| 图文不一致（正文数字与图中读数冲突） | 以**正文 quote** 为准入台账；图读数若要收录必须单开记录、metric_definition 注明 "read from Figure X (digitized)" 且标 `derived`；两者不一致写进 uncertainty |
| 候选抽取误提（年份/型号/R² 等） | 标 `status="excluded"` 留在 jsonl 里（不删），机检只查 reported/derived |
| 数值与他篇雷同 | 机检 W1 告警；逐字核对两篇 quote，确认各自落地后保留，告警写入 uncertainty |
| 预算不足（64 请求/900 秒将尽） | 立即冻结当前 `measurements.jsonl`，跑 validate + render 交骨架；`result.json` 的 `status="partial"` 并在缺失边界中列明"已确认 X/Y 条候选，未确认清单见 /app/work/candidates.jsonl" |

## 最小调用示例

`examples/` 是**完整可运行的最小合成示例**（三篇虚构 g-C3N4/RhB 光催化"论文"，非真实文献）：

```bash
bash examples/run_example.sh
```

管线：语料 jsonl → 段落索引 → `extract_candidates`（26 条候选）→ `validate_measurements`（7 条 agent 确认记录过检）→ `render_ledger`（台账 + 矩阵 + result 骨架到 `examples/output/`）。预期看点：

- DOC-01 报 "degraded 96% within 90 min"（degradation_efficiency）↔ DOC-02 只报 "k = 0.031 min⁻¹"（rate_constant）：**quantity_kind 不同，机检直接判不可比**；
- DOC-03 报 "removal 0.92"（fraction）：矩阵换算列给出 **92 % (derived)**，原值 0.92 fraction 保留；
- DOC-03 投加量 500 mg/L ↔ DOC-01 的 0.5 g/L：单位换算列显示 **0.5 g/L (derived)**，演示 mg/L↔g/L 混用归一。

详见 `examples/README.md`。
