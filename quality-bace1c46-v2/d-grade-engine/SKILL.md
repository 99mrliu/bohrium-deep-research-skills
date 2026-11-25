---
name: grade-derivation-engine
description: 文献研究质量评估的等级推导与校准引擎。当任务要求对文献/研究进行质量分级、偏倚风险评估、GRADE 式评级、多人独立评定一致性（Cohen's kappa）比对，或要求"每个等级都可追溯推导链、禁止拍脑袋给等级"时使用。触发词：质量分级、等级推导、偏倚风险、GRADE、methodological quality、risk of bias、双人评定、kappa、abstain/弃权传播、grading scale、derivation chain。
---

# 等级推导引擎（GRADE Derivation & Calibration Engine）

## 1. 解决什么问题

把**维度级判定**转化为**域级与总评等级**的过程完全规则化、版本化、可复现：

- **绝不输出孤立等级标签**。每个等级都由 `references/thresholds.json`（版本化机器可读量表）中的显式阈值规则派生，并携带 `derivation_chain`（命中规则 id + 输入计数）。
- **弃权传播**：`insufficient_evidence` 是弃权而非中性分，沿 维度→域→总评 向上传播，绝不参与平均、绝不被其他维度的"低担忧"抵消。
- **双人复现包**：两份独立判定文件按 (doc_id, dimension) 对齐，输出一致率、Cohen's kappa 与分歧裁决清单，让第二个人能独立复现并比较结论。
- **模型与脚本职责分离**：模型只产出维度判定 + 证据引用；**所有聚合由脚本完成，模型绝不允许自行发明阈值或"综合判断"总评等级**。

## 2. 适用条件

- 安装路径 `/skills/weekly-skill`（本 bundle 的脚本内默认按"相对脚本文件位置"解析量表，因此安装后开箱即用）。
- 输入 `/input/case.json` 与 `/input/task.md`；全部材料离线提供，**禁止任何实时网络访问**。
- 运行环境：Python 3（仅标准库）；脚本退出码约定 `0=正常 / 1=运行期错误 / 2=用法或输入文件错误`。
- 资源预算：**模型请求 ≤64 次、总时长 ≤900 秒**。
- 交付目录 `/app/output`，工作目录 `/app/work`。

## 3. 输入契约

- `/input/task.md`：任务说明（先读，确定文献范围与任何附加要求）。
- `/input/case.json`：案例数据。**防御性递归搜索**以下键（可能嵌套在任意层级）：
  - `case_id`（退化：`id`）→ 案例标识；
  - `documents` / `docs` / `papers` / `items` / `studies`（列表，元素含 `doc_id`/`id`）→ 期望评估的文献集；
  - `output_contract` / `contract` / `output_fields` / `required_fields` → 输出契约，必须**原样镜像**进 result.json。
- 离线文献材料：从 case.json 中引用的本地路径/内嵌文本读取；找不到的材料按"证据不足"处理，不得联网补全。

## 4. 运行方式

```bash
S=/skills/weekly-skill        # 安装后的 bundle 根目录
W=/app/work;  O=/app/output
mkdir -p "$W" "$O"

# ① 聚合：维度判定 → 域级 + 总评（--scale 可省略，默认取 $S/references/thresholds.json）
python3 "$S/scripts/derive.py" --verdicts "$W/verdicts.jsonl" --workdir "$W"

# ②（可选，有第二评定者时）双人比对
python3 "$S/scripts/second_rater.py" --rater-a "$W/verdicts.jsonl" \
        --rater-b "$W/verdicts_b.jsonl" --workdir "$W"

# ③ 组装交付
python3 "$S/scripts/build_result.py" --workdir "$W" --output-dir "$O" --case /input/case.json
```

`verdicts.jsonl` 每行一个 JSON 对象：

```json
{"doc_id": "DOC-1", "dimension": "design_adequacy", "level": "some_concern", "evidence_ref": "材料路径#段落", "note": "判定理由"}
```

- `dimension` 必须属于量表 5 维：`design_adequacy / sample_sampling / measurement_outcomes / statistical_analysis / reporting_completeness`；
- `level` 必须属于 4 级：`low_concern / some_concern / high_concern / insufficient_evidence`（进入条件见 `references/grading_scale.md`）；
- `evidence_ref`、`note` 可选但强烈建议填写；判 `insufficient_evidence` 时 `note` 必须写明缺什么。

## 5. 工作流

1. **读任务与契约**（task.md → case.json 递归提取 case_id / 文献清单 / output_contract）。
2. **先写骨架 result.json**：进入实质工作前，向 `/app/output/result.json` 写出 `status="partial"`、字段齐全（值可为 null/空）的诚实骨架，确保任何中途失败都留下可用的部分结果。
3. **逐篇逐维判定**：对每篇文献的 5 个维度，基于离线材料给出判定 + `evidence_ref`；信息不足即判 `insufficient_evidence`（诚实弃权优于猜测）。判定流式追加写入 `/app/work/verdicts.jsonl`，防止超时丢进度。
4. **脚本聚合**：运行 `derive.py`（模型在此环节零介入，不得手改 grades.json）。
5. **双人比对**（若任务提供或可构造第二评定）：运行 `second_rater.py`，分歧清单写入交付物供裁决。
6. **组装交付**：运行 `build_result.py`，覆盖骨架为最终 result.json + grade_report.md。
7. **自检**：确认 status 合理、推导链齐全、不确定性如实列出。

## 6. 预算分配（≤64 请求 / ≤900 s）

| 阶段 | 请求预算 | 说明 |
|---|---|---|
| 读 task.md / case.json / 契约解析 | ≤2 | 一次读完，避免反复 |
| 维度判定（核心开销） | ≤44 | ≈每篇 5 维；文献多时对每维只请求一次，禁止逐段闲聊式提问 |
| 中途骨架/进度写入 | ≤4 | 脚本完成，不占模型请求 |
| 双人比对复核（如有） | ≤6 | 第二评定视角复判 |
| 组装与自检 | ≤4 | 校验 result.json 完整性 |
| 机动/重试 | ≥4 | 保留余量，超支即降级为 partial 并说明 |

脚本（derive/second_rater/build_result）不消耗模型请求。接近 900 s 或请求上限时：立即停止新判定，用已有 verdicts.jsonl 跑完三个脚本，交付 partial 结果并在 uncertainties 中说明覆盖范围。

## 7. 异常处理

- **未知维度 id**：`derive.py` 将该行写入 `workdir/rejected_verdicts.jsonl`（reason=`unknown_dimension`），**运行继续**，合法行照常聚合。模型若发现量表未覆盖所需维度，不得自创维度——选最近似维度判定并在 `note`/`uncertainties` 中说明。
- **未知等级**：同上，reason=`unknown_level`，拒绝并继续。模型只允许输出量表 4 级。
- **弃权传播**：由量表规则自动执行——维度弃权 → 域弃权（R-DOM-02）；弃权维度 ≥3/5（R-OV-01）或两核心域均弃权（R-OV-02）→ 总评 `insufficient_evidence`；未达阈值时经 R-OV-06 降为 `moderate` 并把弃权信号写入 uncertainties。模型**不得**为"凑出"一个等级而把弃权改成 some_concern。
- **双人比对分歧**：`second_rater.py` 输出全部分歧（双方等级并列）与未配对判定（仅一方给出者，绝不静默丢弃）。分歧不自动抹平：列入 result.json 与报告，交由裁决（adjudication）；裁决后重跑 derive.py 更新等级。
- **缺失维度判定**：某篇文献缺维度时，相关域走兜底规则（R-DOM-FB→弃权），缺失清单写入 uncertainties，status 视覆盖情况为 success/partial。
- **脚本异常**：退出码 2 = 输入文件缺失/量表损坏（修正后重跑）；退出码 1 = 未预期错误（build_result 会尽量写出 failed 骨架）。保留 workdir 供排查。

## 8. result.json 契约

`/app/output/result.json` 顶层字段：

| 字段 | 内容 |
|---|---|
| `case_id` | 递归提取自 case.json |
| `skill` / `scale_version` | 技能名 / 量表版本（如 `1.0.0`） |
| `status` | `success`（全部文献完成推导）/ `partial`（部分缺判定——列出是哪些；或零判定——附解释）/ `failed`（兜底骨架） |
| `status_reason` | status 的人类可读理由 |
| `output_contract_mirror` | case.json 中 output_contract/contract/output_fields/required_fields 的原样镜像；契约声明但无法填充的字段以 null 置于顶层并记入 uncertainties |
| `grades` | 每篇文献：维度判定、缺失维度、域级等级、总评、**完整 derivation_chain（规则 id + 输入计数）**、scale_version、rejected_count |
| `reliability` | （如有双人比对）配对数、一致率、Cohen's kappa 及解释、分歧数、未配对数 |
| `uncertainties` | 缺失维度、被拒绝判定行、未配对判定、null 占位字段等全部如实列出 |
| `change_records` | 各脚本关键动作的时间戳日志（derive → second_rater → build_result） |

另交付 `/app/output/grade_report.md`（人类可读分级报告）。workdir 中保留 `grades.json / derivation_report.md / reliability.json / reliability_report.md / rejected_verdicts.jsonl / change_records.jsonl` 作为可复现证据。
