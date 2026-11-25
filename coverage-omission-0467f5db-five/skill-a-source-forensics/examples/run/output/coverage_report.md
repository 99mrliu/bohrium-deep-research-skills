# 覆盖率与遗漏分析报告（参考集取证管线）

- case_id: `synthetic-demo-forensics-001`
- 分母来源：冻结参考集 v1.0.0，10 条（content_sha256 `7a298535a453`）
- 命中 6 / 漏检 4，覆盖率 0.6000
- 材料监管链：authenticity_manifest.json（3 份材料，manifest_sha256 `f44988c5992e`）
- 撤稿排除 1 条；核验不足记录以 flag_keep_unverified 保留并列入 uncertainty

## 逐条命中状态

| ref_id | status | match_level | 证据 |
|---|---|---|---|
| R001 | hit | L1_identifier | Q1/Crossref |
| R002 | hit | L1_identifier | Q1/Crossref |
| R003 | excluded | - | - |
| R004 | hit | L1_identifier | Q2/EuropePMC |
| R005 | hit | L1_identifier | Q2/EuropePMC |
| R006 | hit | L1_identifier | Q3/Crossref |
| R007 | hit | L2_title_year | Q3/Crossref |
| R008 | miss | - | - |
| R009 | miss | - | - |
| R010 | miss | - | - |
| R011 | miss | - | - |

## 漏检归因

- `R008` Ion migration hysteresis under damp heat — query_term_missing, source_not_covered_check
- `R009` Early study of moisture ingress in films — query_term_missing, source_not_covered_check, time_window_cutoff
- `R010` Grain boundary chemistry of halide films — query_term_missing, source_not_covered_check
- `R011` Bibliographic entry without any identifier — identifier_anomaly, query_term_missing, source_not_covered_check

## 局限
- 未在本地留存响应中命中的记录标记为 unverified，不作真实性断言。
- 补检为建议级产物；实际新增命中需以案例检索接口执行后复跑本管线。
