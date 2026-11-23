# 报告契约（report_contract.md）—— report-compiler

本文件定义六个台账的字段级 schema、结论分级机械汇总规则、孤儿数字白名单规则、
渲染降级链与交付前目检清单。编译器只做 schema 校验与代数复核，**不做科学判断**；
科学判断（指标怎么抽、容差怎么定、差异怎么归因）由上游流程与 agent 完成并写入台账。

---

## 1. 六个台账的字段级 schema

所有台账为 UTF-8 JSON，顶层均为对象，含 `schema` 版本串。`_note` 等额外字段允许存在。

### 1.1 inventory.json（材料清单，`schema: "inventory/v1"`）

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| materials | array | 是 | 每份材料一条记录 |
| materials[].id | string | 是 | 材料唯一标识 |
| materials[].kind | string | 是 | 如 paper_pdf / candidate_code / dataset / author_repository |
| materials[].status | string | 是 | 仅 `present` 或 `missing`；**缺失材料必须显式登记 missing** |
| materials[].locator | string\|null | 否 | 路径或来源描述；missing 时为 null |
| materials[].note | string | 否 | 备注（缺失原因、预期情况等） |

### 1.2 targets.json（指标目标，`schema: "targets/v1"`）

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| metrics | array | 是 | 指标 id 不得重复 |
| metrics[].id | string | 是 | 指标唯一标识，被 runs/comparison 引用 |
| metrics[].name | string | 是 | 显示名 |
| metrics[].paper_value | number | 是 | 论文报告值；论文未报告则不立此指标（不得编造） |
| metrics[].unit | string | 是 | 单位 |
| metrics[].tolerance.type | string | 是 | `abs` 或 `rel` |
| metrics[].tolerance.value | number | 是 | 容差值 |
| metrics[].source_locator | string | 是 | 论文内定位（表号/页码） |

### 1.3 runs.json（运行记录，`schema: "runs/v1"`）

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| runs | array | 是 | 每个（方法 × 指标）一条 |
| runs[].run_id | string | 是 | 运行唯一标识 |
| runs[].method | string | 是 | 候选方法名 |
| runs[].metric_id | string | 是 | 引用 targets 的指标 id |
| runs[].seeds | array | 否 | 种子列表 |
| runs[].values | array(number) | 是 | 非空逐种子观测值 |
| runs[].env | string | 否 | 环境描述 |
| runs[].command | string | 否 | 实际执行命令 |
| runs[].status | string | 是 | 如 ok / failed |

### 1.4 comparison.json（比较，`schema: "comparison/v1"`）

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| entries | array | 是 | 每行一个（指标 × 方法）；metric_id 必须存在于 targets |
| entries[].metric_id / .method | string | 是 | 比较键 |
| entries[].paper_value | number | 是 | 论文值快照（与 targets 一致） |
| entries[].reproduced_value | number | 是 | 复现聚合值（上游流程计算） |
| entries[].abs_diff / .rel_diff | number | 是 | 差异（上游流程计算） |
| entries[].within | bool | 是 | 上游判定；编译器按 targets 容差**机械重算**，不一致时采用重算值并告警 |

### 1.5 attributions.json（差异归因，`schema: "attributions/v1"`）

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| attributions | array | 是 | 可为空数组；但有超差项时应有对应归因 |
| attributions[].metric_id / .method | string | 是 | 指向比较项 |
| attributions[].cause | string | 是 | 差异原因假设 |
| attributions[].evidence | string | 是 | 证据指针（台账路径/日志路径） |
| attributions[].confidence | string | 否 | low / medium / high |

### 1.6 result.json（最终契约底账，`schema: "result/v1"`）

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| case_id | string | 是 | 与 /input/case.json 一致 |
| status | string | 是 | 仅 `success` / `partial` / `unable` / `refused`，须诚实 |
| output_contract | object | 是 | 键 = case.json 的 output_contract 字段清单，值 = 对应交付内容，**字段一个不能少、值不能为空** |
| sources | array | 是 | 每项结论的来源定位 |
| uncertainties | array | 是 | 不确定性逐条列出 |
| changelog | array | 是 | 变更记录（time + change） |

---

## 2. 结论分级机械汇总规则

分级**只能**由 comparison 判定机械汇总，编译器与审计器各自独立按同一规则重算：

| 条件 | 分级 |
| --- | --- |
| comparison 无有效条目 | `unable` |
| 全部条目在容差内 | `reproducible` |
| 存在超差条目，且**每条**超差都有 attributions 归因记录 | `partially_reproducible` |
| 存在超差条目且无归因记录 | `not_reproducible` |

判定 within 的代数以 targets 容差重算为准：`abs` 型 |复现−论文| ≤ tol；`rel` 型
|复现−论文| / |论文| ≤ tol（含 1e-12 相对数值保护）。

## 3. 孤儿数字白名单规则

结论段（`## 复现结论`）中出现的每个数字（正则 `-?\d+(\.\d+)?([eE][+-]?\d+)?` 抽取）
必须落在以下并集内，否则审计 FAIL（孤儿数字）：

1. 六个台账 JSON 递归出现的全部数字；
2. report_map.json `entries` 登记的全部值（含计数类派生值）；
3. report_map.json `number_whitelist` 显式白名单（页码/年份/种子号等确需出现在
   结论中的数字，须人工显式登记，缺省为空）。

结论段还会被核对分级串与重算分级一致（防手改结论）。

## 4. 渲染降级链

1. 默认尝试 matplotlib → `figures/comparison_<指标>.png`，report.html 内嵌 base64；
2. 无 matplotlib 或指定 `--svg` → 纯 Python 标准库手写 SVG
   （坐标映射、刻度、容差带、散点全部由 compile_report.py 自行计算），
   report.html 内联 SVG 文本；
3. 报告头部与 report_map.json `renderer` 字段都注明实际渲染器；
4. 两链产物图内容一致：论文值点、各方法复现聚合点、逐种子散点（若有）、容差带。

## 5. 目检清单（交付前人工过目）

- [ ] 每张图：有坐标轴与刻度、容差带位置正确、论文值与各方法点齐全、单位正确；
- [ ] 指标比较表每行数字与 comparison.json 一致（审计已机检，人工抽查一行）；
- [ ] 缺失材料节显式列出全部 missing 项；
- [ ] 不确定性节非空且措辞诚实（合成数据结论未外推为论文数值复现）；
- [ ] 变更记录节完整；
- [ ] audit.json overall=PASS；若 PARTIAL 报告，缺口清单与预期一致；
- [ ] report.html 用浏览器打开可自包含渲染（无外部资源）。
