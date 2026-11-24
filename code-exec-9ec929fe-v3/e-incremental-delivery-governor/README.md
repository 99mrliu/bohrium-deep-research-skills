# incremental-delivery-governor

预算治理与诚实交付的过程质量控制：在 900 秒 / 64 次模型请求的硬预算下，
保证任何时刻中断，磁盘上都已存在一个合法的 result.json——要么是 complete，
要么是每个缺失字段都带理由的 partial，绝不出现静默 null。

## 它做什么

- **骨架先行**：`init` 从 case.json 的 output_contract 派生 result.json 骨架，
  在第一个模型请求内落盘；已存在则拒绝覆盖，保护既有进度。
- **证据填充**：`set` 填充契约字段并记录证据路径；未知字段转 `extras{}` 并告警；
  覆盖写留旧值 sha256。
- **命令日志**：`run` 以 shell=False 包裹真实命令，journal.jsonl 记录起止时间、
  时长、退出码、截断输出；非零退出自动记 anomaly，且退出码透明传递。
- **链式校验**：`checkpoint` 对 result.json 做 sha256，并引用前一条校验和形成链。
- **诚实定稿**：`finalize` 校验“非 null 或有理由”，写入 status 与
  delivery_summary.md；exit 0 = complete，4 = partial，1 = invalid（静默 null）。

它不挑选也不改进分析方法，可与任何分析技能组合。详细协议见
`references/delivery_protocol.md`，技能说明见 `SKILL.md`。

## 运行要求

- Python 3.9+，仅标准库（json、hashlib、argparse、pathlib、datetime、
  subprocess、time、sys、os、shlex、csv）。
- 无网络依赖；全部为 UTF-8 文本。

## 文件地图

| 路径 | 作用 |
| --- | --- |
| `SKILL.md` | 技能说明（平台安装入口） |
| `README.md` | 本文件 |
| `GITHUB_URL.txt` | 源码仓库地址 |
| `scripts/stagegate.py` | 治理器全部子命令（init/set/reason/anomaly/run/checkpoint/status/finalize） |
| `references/delivery_protocol.md` | 分阶段交付协议与中断演练准则 |
| `examples/synthetic_case/case.json` | 合成案例契约 |
| `examples/synthetic_case/measurements_syn.csv` | 合成测量数据（40 行，3 个缺失） |
| `examples/toy_analysis.py` | 演示用微型分析脚本（按组求均值） |
| `examples/run_example.sh` | 端到端演练：partial(exit 4) → complete(exit 0) → 阴性测试(exit 1) |

## 快速验证

```bash
bash examples/run_example.sh
```

脚本从任意 cwd 可运行，依次演示：合法 partial（故意失败命令 + 故意留空字段）、
完整交付、以及“静默 null 被拒绝”的阴性测试；全部断言通过时退出 0。
演练产物写在 `examples/demo_out_*` 与 `examples/demo_work_*` 下，可随时删除。
