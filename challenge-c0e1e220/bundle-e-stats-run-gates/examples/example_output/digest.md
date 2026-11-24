# digest — 待确认裁决（stats-run-gates）

以下裁决由 pipeline 自动/按参数作出。[PENDING] 项须确认或覆盖后 finalize（G7 门检）。
确认：python3 scripts/pipeline_e.py decide --work <work> --confirm-all
覆盖：python3 scripts/pipeline_e.py decide --work <work> --set groups=28,90（随后 finalize）

- [CONFIRMED] DEC-001 分组列 = group（来源 auto）
- [CONFIRMED] DEC-002 结局变量 = ['yield_rate']（来源 auto）
- [CONFIRMED] DEC-005 测量单位 = %（来源 auto）

全部裁决已确认，无待办。
