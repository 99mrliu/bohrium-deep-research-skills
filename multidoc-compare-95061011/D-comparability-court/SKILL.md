---
name: comparability-court
description: 多文档比较与整合的"可比性裁定法庭"：把六维度（task/metric/units/material/pollutant/budget）可比性做成确定性裁定记录，任何定量合成必须先申请 permit，否则物理阻断。当输入含 comparison-workorder.json / case.json 与多篇论文语料时使用。
---

# comparability-court：可比性裁定与定量合成守门

## 设计立场

多文档比较最致命的错误是**"比了不该比的"**——把不同污染物、不同指标口径、不同实验条件下的数值放进同一列求平均。本 Skill 把可比性从"读后感"变成**裁定记录**：

1. 每一对论文 × 每个工单维度，由**确定性规则引擎**（脚本，无模型参与）产出一条可检查的 decision 记录（verdict ∈ comparable / convertible / subset_only / blocked / undecidable，附 blocking_dimensions 与双方取值证据）；
2. 任何定量合成（求均值、排名、"优于"断言）必须先向守门脚本申请 **permit**——permit 只发给全链路 comparable/convertible 的集合，否则**物理阻断**并给出阻断理由（维度、双方取值、双方 quote 定位）；
3. 叙述层（报告里的每个比较句）必须引用 `[DEC-…]` 或 `[PERMIT-…]`，**不得手写新的比较结论**。

**诚实性铁律**：裁定由脚本产出，agent 不得改写 verdict，只能补充证据（quote / paragraph_id）。宁可交"blocked + 定性对照"的诚实 partial，也不交一个漂亮但非法的平均值。

## 第 0 步：输入识别

评测环境约定：

- 输入：`/input/case.json`、`/input/task.md`、`/input/comparison-workorder.json`（组织方 v2 接口）以及语料文档。
- 中间产物放 `/app/work`，最终交付放 `/app/output`。
- 语料可能是**真实 PDF，无预提取答案层**：先 `pdftotext -layout in.pdf out.txt`；若输出为空/乱码，再 `pdftoppm -r 200 -png in.pdf page` 渲染后 OCR。
- 将每篇论文的全文写成一个文本文件：`/app/work/corpus/<DOC-ID>.md`（或 .txt），**文件名主干必须等于工单中的 document_id**；段落之间用空行分隔（脚本按空行自动编号 P1、P2、…）。

## 工作流程（分阶段，含确切命令行）

设 `SKILL_DIR` 为本 Skill 根目录，`WORK=/app/work`，`OUT=/app/output`。

### 阶段 1：条件档案（agent 填写 + 机检落地）

对每篇论文填写轻量 condition profile：六维度 task / metric / units / material / pollutant / budget（可自由扩展键），**每个取值附 paragraph_id + 逐字 quote**。某维度论文确实没写，就**不填该条**（脚本按"未报告"处理），严禁编造。

写入 `$WORK/profiles.jsonl`，每行一条：

```json
{"doc_id": "DOC-01", "dimension": "pollutant", "value": "RhB", "paragraph_id": "P2", "quote": "目标污染物为罗丹明 B（RhB）"}
```

校验并规范化（quote 逐字落地机检，失败即报错退出）：

```bash
python3 "$SKILL_DIR/scripts/build_profiles.py" \
    --corpus "$WORK/corpus" --profiles "$WORK/profiles.jsonl" --out "$WORK/profiles.json"
```

### 阶段 2：裁定引擎（全对 × 全维度）

```bash
python3 "$SKILL_DIR/scripts/decide.py" \
    --profiles "$WORK/profiles.json" \
    --rules "$SKILL_DIR/references/comparability-rules.json" \
    --out "$WORK/decisions.jsonl"
```

产出 decisions.jsonl：每条含 `decision_id`、`doc_pair`、`dimension`、`verdict`、`blocking_detail{value_a, value_b, paragraph_id, quote}`；每对论文另有一条 `__overall__` 任务级总裁定（= 六维度裁定之最严者，severity：blocked > undecidable > subset_only > convertible > comparable）。规则表见 `references/comparability-rules.json`，语义见 `references/verdict-taxonomy.md`。

### 阶段 3：合成守门（permit 先行）

agent 提交合成请求 `$WORK/synthesis_request.json`：

```json
{"request_id": "REQ-01", "docs": ["DOC-01", "DOC-02"],
 "field": "degradation_rate_eta", "claim_type": "quantitative",
 "required_dimensions": ["task","metric","units","material","pollutant","budget"],
 "claim_text": "想做的断言"}
```

```bash
python3 "$SKILL_DIR/scripts/pool.py" \
    --decisions "$WORK/decisions.jsonl" \
    --request "$WORK/synthesis_request.json" \
    --rules "$SKILL_DIR/references/comparability-rules.json" \
    --out "$WORK/pool_<request_id>.json"
```

- `quantitative`：所有相关 decision 全为 comparable/convertible 才发 permit（附归一化说明）；
- `qualitative`：额外放行 subset_only（附口径警告，报告必须复述）；
- 否则 **block**：输出阻断维度、双方取值、双方 quote 定位。**无 permit 的断言不得出现在报告中。**
- 每个想做的合成一个请求文件，分别跑一次。

### 阶段 4：渲染 + 叙述绑定 lint

```bash
python3 "$SKILL_DIR/scripts/render_court.py" \
    --decisions "$WORK/decisions.jsonl" --profiles "$WORK/profiles.json" \
    --workorder /input/comparison-workorder.json --case /input/case.json \
    --permits "$WORK"/pool_*.json --outdir "$OUT"
```

产物：`decision-matrix.md`（论文对 × 六维度 ✓/○/△/?/✗ 网格 + 阻断明细表）、`comparison-matrix.md`（许可内字段视图）、`verdict-report.md`（报告模板，比较句已带 `[DEC-…]`/`[PERMIT-…]`）、`result.json`、`lint.json`。

agent 可扩写 verdict-report.md 的叙述，但每个比较句必须引用真实存在的 id；改完复检：

```bash
python3 "$SKILL_DIR/scripts/render_court.py" \
    --decisions "$WORK/decisions.jsonl" --profiles "$WORK/profiles.json" \
    --permits "$WORK"/pool_*.json --outdir "$OUT" --lint "$OUT/verdict-report.md"
```

### 阶段 5：交付契约

`/app/output/result.json` 必须包含：

- `case_id`：从 case.json **原样复制**；
- case.json `output_contract` 的**全部字段，字段名原样照搬**（render_court.py 对已知字段自动填充，未知字段置 null 并记入 uncertainty）；
- `status` ∈ {success, partial, failed}：存在 blocked/undecidable/subset_only 总裁定或有契约字段缺失 → `partial`，**必须在 uncertainty 写明缺失边界**；
- `sources`、`uncertainty`。

若 case.json 无 `output_contract`，退化为 `{case_id, status, 主结果, sources, uncertainty}`。

## 异常处理

| 情形 | 处置 |
|---|---|
| 某维度论文未报告 | 不填该条 profile → 该维度对涉及它的每一对均为 `undecidable`；定量/定性合成都被守门阻断，补齐档案后重跑 decide + pool |
| 单位可换算（如 min⁻¹ vs h⁻¹、g/L vs mg/mL） | `convertible`；permit 附归一化说明，报告中数值必须统一到一个口径 |
| 单位不可换算（% vs min⁻¹，分属不同指标） | `subset_only`；仅允许定性对照，数值合并被阻断 |
| 指标不同（η vs k） | `subset_only`；禁止均值/排名/"优于"，只允许定性对照句并注明口径 |
| 污染物或任务不同（RhB vs MB） | `blocked`；任何形式的合并比较都被物理阻断 |
| 材料/投加量不同 | `subset_only`；定性对照可许可，报告必须复述口径警告 |
| 同一论文多版本 | 视为不同 doc_id 分别建档，对它们先跑一轮裁定；task/material 等一致则 comparable，再决定去重策略并在 uncertainty 中说明 |
| 全部论文对都 blocked | 诚实 partial：只交定性对照与裁定矩阵，`status=partial`，uncertainty 写明"无可比集合，未做任何定量合成" |
| profile 校验失败（quote 未落地） | build_profiles.py 报错退出；修正 quote/paragraph_id 后重跑，严禁绕过机检 |
| 请求只含 1 篇论文 | pool.py 直接 block：单篇摘要不构成多文档比较 |

## 预算与节奏

预算 64 次模型请求 / 900 秒。推荐节奏：**先交条件档案 + 全对裁定**（机制产物，确定可交付），再挑 1–2 个最可能全链路 comparable 的子集申请 permit 做少量许可内合成；其余如实 block。**随时可诚实 partial**——裁定矩阵本身就是高价值交付。

## 最小调用示例

见 `examples/`（**合成示例**，虚构论文与工单，case_id `SYNTH-EXAMPLE-001`）：

```bash
bash "$SKILL_DIR/examples/run_example.sh"
```

端到端演示：DOC-01×DOC-02 在 pollutant 维度 blocked、DOC-01×DOC-03 在 metric 维度 subset_only 且 budget 缺失 undecidable；"对 DOC-01、DOC-02 的降解率求均值"被守门物理阻断，"DOC-01×DOC-03 同污染物定性对照"获得 permit。预期结果详见 `examples/README.md`。
