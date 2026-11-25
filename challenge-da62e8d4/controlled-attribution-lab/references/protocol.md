# 受控归因与复现报告协议

## 一、材料账本

建立带路径和 SHA256 的账本：case/task、真实 PDF、两个候选脚本、合成数据、环境描述。每个数值目标注明 PDF 页码、图/表/方程、单位和抽取方式。区分：

| 来源 | 可写内容 |
| --- | --- |
| 论文明确报告 | 带页码/图表定位的事实 |
| 任务材料给出 | 标明组织方合成或任务文件提供 |
| 本实验自行设定 | 未由论文报告的步长、seed、容差等，附理由 |

组织方合成数据不是作者原代码或全量 PMLB。未找到原始数据仓库时，明确检查 `/input` 后写“未提供原始数据仓库”，不能用“完整复现作者仓库”措辞。

## 二、事前假设卡

每张假设卡必须能失败。例如：

- statement：在材料、实现、数据、环境和 seed 固定时，仅把 `parameter.steps` 从 4 增至 40，会使 `absolute_error` 降低。
- predicted signatures：误差下降超过 baseline pairwise noise floor；估计值向论文目标移动；其他输出结构不变。
- falsification：误差上升或下降不超过 noise floor；后者判 inconclusive，不宣称支持。
- attribution boundary：仅对该材料、该实现、测试区间和 seeds 内有效。

在看到变体结果前封存所有卡、目标、容差、运行列表和 output contract。事后新想法必须作为新 plan、新 ID 另行注册，并标记 exploratory，不可覆盖旧计划。

## 三、执行与对照

1. 同候选至少 3 次 baseline；变化仅由事前指定的 baseline seeds/重复条件引起。估计 noise floor，不追求完全相同。
2. A 的任何运行失败后继续 A 剩余项和 B 的全部项；退出码、超时与 JSON 解析失败均入证据。
3. 改变体时维持 cwd、环境、输入和候选，除声明路径外不变。数据变体记录数据哈希，实现变体记录代码 diff，环境变体记录包/平台，seed 变体记录 seed 列表。
4. 不把 baseline 重跑次数当变体，不以不同容差函数、舍入或可视化配方当科学干预。
5. 若同时改两个字段，执行前拒绝；若事后发现未声明共变，标 `confounded`，最多描述相关观察，不得强因果措辞。

## 四、效应与判定

设 baseline 值为 b，variant 值为 v：

```text
baseline_center = median(b)
variant_center = median(v)
effect = variant_center - baseline_center
noise_floor = noise_epsilon + max(abs(b[i] - b[j])) for i < j
```

方向判定必须在数值表中同时给原值、中心、effect 和 noise floor。`increase/decrease` 只在效应越过噪声且同向时 supported，反向越噪为 falsified。效应未越噪一律 inconclusive。`unresolved` 表示事前未承诺方向：越噪只可 supported “可检测变化”，未越噪 inconclusive；均不证明唯一机制。

失败或无指标使相应假设 inconclusive，并令 overall partial。不得只挑有利重复；所有计划运行进入审计表。

## 五、复现结论层次

最终分四层写：

1. **目标复现**：A/B 对论文目标的事前容差比较，以及图表关键点、趋势、误差与单位对照。
2. **干预证据**：每个预注册假设的 supported/falsified/inconclusive、统计量和 signatures 是否出现。
3. **归因范围**：统一写“受控证据支持/未支持；attributable only within tested conditions”。不要写“已证明根因”“排除了所有其他因素”。
4. **不确定性和缺失**：原仓库、合成范围、PDF 抽取、未测 factor、重复次数、失败运行、自设参数与剩余图表差异。

顶层 `result.status` 只能为 `success/partial/unable/refused`：全部运行且证据、artifact、case 回答字段完整交付为 `success`；任何运行/指标/artifact/回答缺失为 `partial`；预检失败且未运行为 `unable`。执行器细节另记 `execution_status=complete/partial/rejected`。成功仍不等于论文完全复现，科学结论、交付状态和执行状态必须分开保留。

## 六、最终清单

- [ ] `/input` 未修改，中间与最终文件分目录。
- [ ] A 和 B 都实际运行，失败未中断。
- [ ] 论文目标、容差和图表对照事前固定。
- [ ] hash 通过，factor 合法，每 variant 仅一个 changed path。
- [ ] noise floor 来自多次 baseline，小效应不硬判。
- [ ] 所有 stdout/stderr/env/cwd/argv/exit/timeout/metric 可审计。
- [ ] result 从真实 case_file 读取 case_id/output_contract，含全部合同回答字段及 status/execution_status/sources/uncertainty/change_records；实质值或结构化 unavailable 平铺顶层。
- [ ] case.output_contract（回答）与 plan.artifact_contract（路径）未混用；标准字段允许声明，未知回答字段未只填 artifact 路径。
- [ ] 自设参数不冒充论文事实，partial 诚实，结论不越过测试条件。
