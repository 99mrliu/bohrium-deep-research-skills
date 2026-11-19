# 冲突裁定与证据分级规则

## 冲突对（conflict pair）

- 定义：同一 (topic, outcome) 下 direction 互斥（positive vs negative，或与 none 相对且双方都声称做了有效检验）。
- 呈现：并置双方研究行（含 design/n/magnitude/limits/source），不删任何一方。
- 裁定（adjudication）必填，三选一写法：
  1. `supports:A/B` + 依据（设计层级更高、样本量更大、方向与多数一致等）；
  2. `unresolved` + 缺什么证据（如"缺长期随访数据，无法裁定"）；
  3. `mixed`：效应依赖调节变量时，写明调节变量与双方适用边界。
- 禁止输出"双方都有道理""尚存争议"这类不含信息的裁定。

## 证据等级

| 等级 | 判据 |
|-|-|
| A | ≥2 项原始数据研究（rct/cohort）且方向一致 |
| B | 1 项原始数据研究；或仅综述但 ≥2 篇方向一致 |
| C | 仅综述/观点；或单项小样本（n<30）；或方向不一致的非原始证据 |
| D | 无法确定：材料未覆盖或检索未执行 |

## 空白分类

- searched_but_absent：该方向执行过检索（topics.json searched=true）但矩阵无研究行——高置信缺口。
- partially_covered：仅 1 篇或证据等级 ≤C——需更多证据。
- not_searched：未执行检索——不下任何结论。

## 结论句模板

`[事实|推断|无法确定] 结论句（等级 X；矩阵行 r1,r2）`
