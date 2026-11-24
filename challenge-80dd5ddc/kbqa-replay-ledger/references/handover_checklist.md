# 交接自查清单（handover checklist）

目标：换一个评审，只凭 /app/output 与 /input，就能把你的问答完整重走一遍。

## 交付前逐项核对

1. **合同自检**：selfcheck_report.json 的 pass=true（contract 字段齐全、
   case_id 一致、status 合法、引文回验全过）；pass=false 时 result.json
   只能是 partial。
2. **过程审计**：audit_report.json 的 pass=true（哈希链完整、输入全覆盖、
   阶段齐备、已封口）。
3. **重走包**：replay/replay_steps.md 步骤连续可读，replay/manifest.json
   覆盖 /app/output 全部交付物且哈希可重算。
4. **结果诚实**：result.json 的 status 与两份报告一致；uncertainty 与
   日志中的 error/skip 条目数量对得上；没有把 proposed/skip 写成 done。
5. **可定位**：答案中的每个坐标（file_id/行号/哈希前缀）在 manifest 或
   索引中可解析；抽查 2 条人工核对。

## 交接物布局

```
/app/output/
  result.json            # 主结果（case_id + contract 字段 + 诚实状态）
  audit_report.json      # 过程审计结论
  selfcheck_report.json  # 合同自检结论
  replay/
    replay_steps.md      # 人读重走步骤
    manifest.json        # 交付物哈希清单
  （以及任务要求的其他产物：答案、编目、核验报告等）
```

## 常见失败模式（来自实践）

- 日志只在开头记了一笔 scan，之后全靠记忆 → 审计 untouched 爆满。
- 核验失败后改了答案但没重跑核验 → selfcheck 引文回验不过。
- result.json 先写 completed 后补内容，中途被预算截断 → 用
  "先 partial、finalize 时才升级"的纪律避免。
- seal 之后继续改产物 → post_seal 计入 issues；应改完后重新审计并重封
  （在新日志条目上再 seal 一次即可，审计取最后一次 seal）。
