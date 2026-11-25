# 复核交付报告 — synth-review-001

- 研究问题: 2019 至 2024 年间发表的关于钠离子电池层状氧化物正极材料循环稳定性提升的实验研究文献检索与筛选
- 生成时间: 2026-11-25T17:07:02+0800
- 结果状态: **partial**（三值诚实状态：complete/partial/blocked）

## 一、概要

| 环节 | 数量 |
|-|-|
| 识别记录 | 8 |
| 重复移除 | 1 |
| 去重后筛查 | 7 |
| 纳入候选 | 4 |
| 待人工复核 | 1 |
| 排除 | 2 |

## 二、筛查条款（轻量、确定性、可复算）

- 年份窗: [2019, 2024]
- 决策规则: score=2*标题命中术语数+1*仅摘要命中术语数; >=4 纳入, 1-3 待复核, 0 排除
- 硬性排除: 文献类型 ∈ {review, editorial, news, perspective}
- 跨语扩展: 钠离子→sodium-ion/sodium/na-ion; 电池→battery/batteries; 层状氧化物→layered oxide; 正极→cathode; 循环→cycling/cycle; 稳定性→stability/stable
- 术语数: 52（完整清单见 result.json criteria.terms）

## 三、候选清单（纳入 4 条）

| rid | 标题 | 年份 | 理由 |
|-|-|-|-|
| R01 | Cycling stability of layered oxide cathodes for sodium-ion batteries via Mg doping | 2021 | term_score:15>=4 |
| R02 | Suppressing phase transitions in O3-type layered oxide cathode for Na-ion batteries | 2023 | term_score:12>=4 |
| R07 | Cr doping improves layered oxide cathode stability in sodium-ion batteries | 2024 | term_score:14>=4 |
| R08 | Opinion: layered oxide cathodes show no practical stability gain for sodium-ion batteries | 2023 | term_score:13>=4 |

## 四、排除理由分布（排除 2 条）

| 理由码 | 条数 |
|-|-|
| doctype_excluded | 1 |
| year_out_of_window | 1 |

## 五、署名清单核验

| ref_id | 标题 | 状态 | 对应记录 | 已纳入 |
|-|-|-|-|-|
| AP-1 | Cycling stability of layered oxide cathodes for sodium-ion batteries via Mg doping | matched | R01 | 是 |
| AP-2 | Suppressing phase transitions in O3-type layered oxide cathode for Na-ion batteries | matched | R02 | 是 |
| AP-3 | A phantom sodium cathode study absent from the snapshot | missing | — | 否 |

## 六、不确定性与保留项

- 冲突意见夹具记录 R08 已登记为争议证据，本技能不做学术裁决
- 清单文献 AP-3 在快照中未找到匹配记录
- 1 条记录为 borderline，需在 review.html 中人工勾核

## 七、交付物清单与哈希（防篡改，供 check_exports.py 回核）

| 文件 | sha256（前 16 位） | 字节数 |
|-|-|-|
| flow.svg | `f3f447c93fe84f2e…` | 2934 |
| ledger.csv | `f59db1985ebdd788…` | 2260 |
| review.html | `9df7f107a7d72428…` | 6165 |
| report.md | （本文件，哈希见 manifest.json） | — |
| result.json | （哈希见 manifest.json） | — |

---
本报告由 build_review.py 自动生成；人工复核请使用 review.html，勾核结果回写 overrides.json 后重跑本脚本。
