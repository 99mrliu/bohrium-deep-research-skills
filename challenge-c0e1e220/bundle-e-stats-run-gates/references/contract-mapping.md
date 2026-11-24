# 契约字段填充规则与诚实降级（contract-mapping）

result.json 必须包含 case.json `output_contract.required_fields` 的 9 个字段。
本文件给出每个字段的填充规则、来源阶段、降级行为。骨架先行：流水线第一步把
全部字段以空容器 + status=partial 写入交付位，随后逐阶段填数。

| 字段 | 填充规则 | 来源 | 降级（诚实 partial） |
|---|---|---|---|
| case_id | 原样复制 case.json.case_id | case.json | 缺失则 "UNKNOWN" + exception |
| status | 无 exception→`complete`；有→`partial`；崩溃→骨架保留 `partial` | 组装 | 枚举仅 complete/partial/failed |
| cleaning | rows_raw/kept/dropped + 闭合律 + 规则账本（缺失/重复/离群，各记影响行数）+ db_consistency | stage_02 | SQLite 不可读→checked=false + limitation，不中断 |
| descriptive | 每结局 × 每组 n/mean/sd/median/q1/q3/min/max/skewness + unit | stage_03 | 组有效 n=0→该组 null 并记 exception |
| hypothesis_test | 方法名+reason_code+统计量+df+p+alpha+significant+assumptions+post_hoc(Holm)+reference | stage_04 | 可用组<2→OUTCOME_SKIPPED exception，该结局降级为描述 |
| effect_size | 两组 hedges_g（+bootstrap CI）；k 组 eta2/omega2（KW 路线 eps2）+幅度分级 | stage_04 | 方差为 0→value=null + exception |
| confidence_interval | 效应量 bootstrap CI（B=2000,seed=20240501）；位置差：参数路线 Welch CI、非参 Hodges-Lehmann | stage_04 | 有效重抽样<一半→ci95=[null,null] + uncertainty 注明 |
| interpretation | 每结局一段中文：方法+判定+效应量+方向+单位+证据引用 [HT/ES/CI:id]；区分统计显著与实际意义，禁用"证明" | 组装 | 骨架态为空串（SKELETON_SHIPPED 会被 lint 拦截） |
| limitations | 离群点计数、小 n 组、单位缺失、DB 未核对、观察性数据因果限制；**必须非空** | 组装 | 永远非空（G4 强制） |

## 附加字段（非契约但必须）
- `sources`：每个输入文件 sha256+bytes（G0 登记一致性的依据）。
- `reproducibility`：seed/bootstrap_B/python/platform/timestamp_utc（**唯一易变字段**）。
- `uncertainty`：bootstrap 蒙特卡洛误差、秩检验近似、边界正态性等；**必须非空**（G4）。
- `exceptions`：[{code,message,detail?}]；partial 时非空（G5/lint 强制）。
- `decisions`：DEC-001..005 裁决与状态（pending→confirmed/overridden）。
- `evidence_index`：全部可引用 id（HT:/ES:/CI:/SRC:/STAGE:/DEC-），lint 据此查悬空引用。
- `analysis_plan`：最终生效的分组列/结局/子集/单位/alpha。

## 清洗口径（默认值，constraints 可覆盖）
- 缺失：report_and_exclude——分组变量缺失整行剔除；结局变量按逐变量有效 n，不零填不插补。
- 完全重复：默认 **flag_and_report**（只标记报告不删除；基准快照中的完全重复可能是
  真实重测记录，一位小数测量下重合并非不可能）；constraints.duplicate_policy=
  "dedupe_exact_keep_first" 时删至首行。无论哪条路线，重复行数都写入账本。
  （设计说明：本默认比"默认即删"保守，删除数据必须有显式授权。）
- 异常值：1.5×IQR 栅栏**只标记不删除**，按变量报告格数与行数。
- 单位：--unit > plan 文件 > task.md"单位 X"嗅探 > "unspecified"（DEC-005 待确认）。

## 路线与经典结果冲突时
门控路线（如正态不齐→Welch ANOVA、非正态→Mann-Whitney）永远是主结论；
经典 ANOVA F / Welch t 以 `hypothesis_test.<结局>.reference` 一并报告并注明
"仅作可比性参考"。这既遵守假设门控，又保留与教科书/基线数字对账的能力。
