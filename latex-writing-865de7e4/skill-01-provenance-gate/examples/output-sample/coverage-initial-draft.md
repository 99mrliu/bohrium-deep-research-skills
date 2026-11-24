# 事实覆盖审计报告（coverage）

> 合成示例（synthetic example），非正式案例结果。本文件为示例运行真实产物的留档副本。

稿件：`/Users/liuhengshen/Desktop/bhr_product/4/arena07/bundles/skill-01-provenance-gate/examples/input/draft.tex`
事实库：`/Users/liuhengshen/Desktop/bhr_product/4/arena07/bundles/skill-01-provenance-gate/examples/_run/work/facts/facts.jsonl`（7 条）

> 本报告由 texaudit.py 生成，只报告不改稿；弱匹配候选仅供人工复核，不得当作已证实。

## 汇总

- matched: 2
- unmatched: 2
- conflict: 1
- 材料间口径冲突（预警）: 1

## conflict（口径冲突，需 Agent 裁定）

| 稿件位置 | 类型 | 稿件值 | 材料锚点 | 说明 |
| --- | --- | --- | --- | --- |
| draft.tex:7 | percent | 93.7% | data.csv:3; notes.md:5 | 材料同上下文中记载的数值不同: 92.4%（notes.md:5）; 94.1（data.csv:3） |

## unmatched（材料外内容，需 Agent 显式处置）

| 稿件位置 | 类型 | 稿件值 | 最接近候选（弱匹配） | 说明 |
| --- | --- | --- | --- | --- |
| draft.tex:8 | num_unit | 9 h | 12 h @ notes.md:7 [弱匹配]; 92.4% @ notes.md:5 [弱匹配]; 94.1 @ data.csv:3 [弱匹配] | 材料中未找到该数值；候选为弱匹配，仅供人工复核 |
| draft.tex:9 | cite_key | zhang2023unknown | wang2021cnn @ refs.bib:2 [弱匹配] | 引用键未出现在任何材料 .bib 中；候选为弱匹配，仅供人工复核 |

## matched（已回溯到材料）

| 稿件位置 | 类型 | 值 | 材料锚点 |
| --- | --- | --- | --- |
| draft.tex:6 | percent | 92.4% | notes.md:5 |
| draft.tex:6 | cite_key | wang2021cnn | refs.bib:2 |

## 材料间口径冲突（预警，与稿件是否引用无关）

| 材料 A | 材料 B | 共享上下文 |
| --- | --- | --- |
| notes.md:5 = 92.4% | data.csv:3 = 94.1 | accuracy |

## 运行备注

- 已排除来自被审计稿件自身的 3 条事实（draft.tex），避免自我匹配
