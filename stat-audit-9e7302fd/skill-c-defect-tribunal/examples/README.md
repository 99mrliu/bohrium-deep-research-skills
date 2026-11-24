# examples/ — 合成示例（非真实文献）

**本目录全部内容为合成示例**：所涉"论文"（《"清压操"社区干预对中老年高血压患者收缩压
的影响》，虚构）、全部数据、引用与结论均为演示而编造，不对应任何真实文献，不得照抄
或引用。

## 文件说明

- `candidate_findings.jsonl` — 宽进阶段的 6 条候选发现（指控），每条带 quote + location
  与提议的类别/严重度。
- `adjudication_log.jsonl` — 裁决庭对 6 条候选的完整裁决日志，**通过**校验脚本：
  - F-001：真·事实错误/critical（结论与自身表2相反），裁决 维持；
  - F-002：原指控"误用 t 检验"，辩护证明仅为"未报告"，改类 规范问题 并降级 minor
    （未报告 ≠ 做错）；
  - F-003：指控"未报告随机化"，辩护 q2 证明方法节已报告，驳回（留痕）；
  - F-004：power 声称无法复算，转待复核（写明 missing_material）；
  - F-005：原指控 证据不足/major，辩护证明不确定度正文已给出，改类 建议 + 降级
    editorial；
  - F-006：干净的 规范问题/minor，维持。
- `run_example.sh` — 一键演示：有效日志应通过（exit 0），破坏日志应被拒（exit≠0）。
- `expected_output/` — 实际运行产物：
  - `validation_summary.txt`：对 `adjudication_log.jsonl` 运行的真实输出（汇总表 + 通过）；
  - `broken_log.jsonl`：蓄意破坏的日志变体（每条埋一类违规）；
  - `broken_validation_output.txt`：对破坏日志运行的真实输出（违规逐条列出 + 退出码），
    证明校验门是真实有效的。

## 运行

```bash
bash examples/run_example.sh
```
