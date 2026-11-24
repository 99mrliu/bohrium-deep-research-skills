# 最小示例运行记录（合成示例）

> 本示例的计数、协议与判定摘要均为**合成数据**，不对应真实筛选结果。

## 输入

- `counts.json`：200 identified − 23 duplicates = 177 screened
  = 160 excluded + 12 included + 5 needs_human；理由分解 80+50+30=160（闭合）；
- `protocol_meta.json`：两库合成检索协议元数据；
- `decisions_summary.json`：理由分解 + agreement（177 判定、170 一致）。

## 实际执行与结果（2026-11-24，Python 3，macOS arm64）

```text
[1] RENDER PASS: flow.svg (3418 bytes) + flow.md        rc=0
[2] 篡改 excluded=159 → RENDER BLOCKED，R2/R3 FAIL       rc=3（预期）
[3] REPORT -> screening_report.md (gaps=0)               rc=0
[4] REPORT（仅 counts）-> partial/screening_report.md (gaps=3)  rc=0
EXAMPLE PASS
```

退出码 0；flow.md 与 render_check.json 重跑逐字节一致。

## 产物目检结论（output/）

- **flow.svg（运行时产物，未随包保留）**：经 qlmanage 转 PNG 目检——
  Identification/Screening/Included 纵列 + Excluded 侧盒、三条箭头连贯、
  数字与 counts.json 一致、"Awaiting human confirmation (n=5)"单列；
  render_check.json 记录 well-formed=true、svg_bytes=3418。
  复现命令：`python3 scripts/run_example.py`（生成于 output/flow.svg）。
  不随包附带的原因：保持包内全部为平台允许的文本资源类型，
  且 SVG 可由一条命令确定性重建。
- `flow.md`：Mermaid 流程图 + 计数表，与 SVG 同源。
- `screening_report.md`：六节齐备（检索范围/流程计数/流程图/排除理由/
  一致性 96.0%/待人工确认），无缺失清单。
- `partial/screening_report.md`：仅 counts 输入的降级版，缺失清单恰为
  检索范围、流程图、一致性统计 3 项。
- `render_check.json`：R1–R4 全 PASS。
