# 合成示例（SYNTHETIC EXAMPLE）

本目录为**合成示例**：case、材料与答案均为演示编造，不含任何隐藏案例预制答案，仅用于本地跑通 process-qc-guard 全流程。

## 运行

```bash
bash run_example.sh /tmp/a1d81ca4-c-demo-out   # 参数为输出目录，默认 ./out
```

## 流程与预期产物（输出目录下）

| 步骤 | 动作 | 预期产物 / 现象 |
|---|---|---|
| 0 | init_run（INPUT_DIR 指向本目录） | `work/run_manifest.json`；`output/result.json` 安全网骨架（status=部分完成，skeleton=true） |
| 1 | 模拟 agent 起草 + checkpoint save | `work/answers.json`（=answers_draft.json）；`work/checkpoints/draft.json` |
| 2 | probe_failures | `work/probes_report.json`、`work/failure_samples.md`；检出 P01（空答案）与 P04（缺证据锚点）两条，退出码=2 |
| 3 | 修复 + checkpoint save + probes | `work/answers.json`（=answers_fixed.json）；probes 0 命中，退出码=0 |
| 4a | rerun_consistency（确定性复制命令） | `work/consistency_report_stable.json/md`，判定 STABLE，退出码=0 |
| 4b | rerun_consistency --inject-drift | `work/consistency_report_drift.json/md`，判定 DRIFT（原因=时间戳），退出码=3 |
| 5 | checkpoint export + status | `output/result.json` 正式版（status=成功，含四契约字段、sources、uncertainty、change_records、qc） |

## 输入文件

- `case.json`：case_id `synthetic-demo-001`，output_contract 四字段（answer_q1/answer_q2/evidence/confidence）。
- `task.md`：T1 问答，两问；第二问答案"未报告"，考察诚实标记。
- `source_excerpt.txt`：编造的合金热处理段落（含 540°C、170°C 等数值；锆含量故意不出现）。
- `answers_draft.json` / `answers_fixed.json`：模拟 agent 工作文件（缺陷版 / 修复版）。
