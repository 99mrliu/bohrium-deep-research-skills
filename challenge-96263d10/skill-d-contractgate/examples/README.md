# 最小调用示例（合成示例，非正式案件结果）

`run_demo.sh` 一键演示契约门禁正路与反路。**全部输入现场合成；
expected/ 下为合成示例的真实运行产物，仅示意接口。**

## 运行

```bash
bash examples/run_demo.sh
```

## 本示例实测结果（2026-11-24 真实运行）

- probe：盘点 3 个输入（magic 嗅探 + sha256 固证），宽容解析 case.json，
  识别契约字段 adapted_file/summary，立即落 partial 骨架 result.json。
- checkpoint：登记交付物 adapted.md（sha256 入 result.json artifacts），
  阶段事件进 journal.jsonl。
- 正路 seal：S1–S8 全 PASS → **SEALED**（注意此时 status 诚实保持 partial，
  S4 认可"partial + 0 未了事项"——人工目检尚未做，不虚报 complete）。
- 反路 seal：人为清空 summary 字段并谎报 complete（同时 uncertainties 里
  还挂着未确认项）→ **SEAL REFUSED**，S3 点名缺失字段、S4 点名状态撒谎，
  退出码 1。

expected/ 内容：seal_positive.json / seal_negative.json（两份独立裁决报告）、
journal.jsonl、run_state.json、正路最终 result.json。
