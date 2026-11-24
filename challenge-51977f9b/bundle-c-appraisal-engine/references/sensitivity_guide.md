# 敏感性分析协议（sensitivity_guide）

## 1. 目的与判定阈值

质量评价定级之后，必须回答："如果剔除高风险研究，结论还站得住吗？"
sensitivity.py 对每条论断（claim）重算支撑集：

| 判定 | 定义 | 正文处理 |
|---|---|---|
| stable | 支撑集不变（未失去任何被剔除等级的研究） | 正常陈述，标注"剔除高风险研究后结论不变" |
| weakened | 失去部分支撑，但剩余支撑数仍 ≥ min_support | 陈述时降级语气并显式标注"剔除高风险研究后支撑减弱，仅存 N 项研究" |
| unsupported | 支撑清零或剩余 < min_support | **不得作为结论**；改写为更弱表述或移入 uncertainty |

默认 `--min-support 1`；重要论断（主要结局的核心结论）建议提高到 2，
即剔除高风险研究后至少两项独立研究同向支持。

## 2. weakened / unsupported 论断的改写纪律

- **weakened**：保留论断但降语气（"提示""可能"），并在论断后括注
  支撑等级构成，如"（支撑：S1[low]、S3[low]；S5[high] 已剔除）"。
- **unsupported**：两条路，二选一，不许原样留在结论里：
  1. 改写为与剩余证据相符的更弱论断（若支撑清零，则改写为
     "现有低偏倚风险证据无法回答 X"）；
  2. 移入 result.json 的 `uncertainty`，格式见第 3 节。
- 禁止反向操作：为了给 unsupported 论断续命而放宽量表阈值——
  那是修改方法学来迁就结论，属学术不端。

## 3. 写入 uncertainty 的格式

```json
{
  "type": "unsupported_claim_after_sensitivity",
  "claim_id": "C3",
  "original_text": "……原论断……",
  "excluded_studies": ["S5", "S6"],
  "reason": "剔除 high 级研究后支撑清零（min_support=1）。",
  "disposition": "已从结论移除 / 已改写为：……"
}
```

weakened 论断写 `type: "weakened_claim"`，其余字段同上，
`disposition` 写明正文中的降级表述。

## 4. 何时重跑

- 任何判定修订（重判某维度、改 level_id）→ 重跑 appraise.py 与
  sensitivity.py，并比对两版报告差异，记入 change_records。
- 更换剔除等级（`--exclude-grade some_concerns --exclude-grade high`
  的极端保守情形）可作为补充分析，但主分析等级组合必须在方法学部分
  事先声明，避免"挑一个好看的阈值"。
