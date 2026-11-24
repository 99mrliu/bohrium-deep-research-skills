# audit-process-qc

论文逻辑与论证审查（Bohrium challenge-16d4414d）参赛 Skill —— **过程质量控制**方向。

不替你审论文，而是让审查过程本身可复核：原子检查点（任何中断留下诚实半成品）、覆盖台账（没做和做了没问题分得清）、预算安全网（40/56 阈值）、复跑一致性（STABLE/DRIFT）、finalize 诚实门禁（有未检查项禁止 success）。

## 组成

| 文件 | 作用 |
|-|-|
| `SKILL.md` | Skill 本体：触发条件、运行契约、执行协议、异常处理 |
| `scripts/runqc.py` | 引擎：init / checkpoint / coverage / budget / reruncheck / finalize 六子命令，纯标准库（Python ≥3.8），零依赖 |
| `references/runbook.md` | 900 秒时间盒、检查点节奏、DRIFT 处置、门禁逻辑 |
| `examples/minimal/` | **合成示例**（非正式案例）：合成 case.json + 模拟审查会话 + DRIFT 复跑 + 蓄意 dishonest 负面对照 |
| `GITHUB_URL.txt` | 本作品公开仓库链接 |

## 快速验证（本地）

```sh
sh examples/minimal/run_example.sh
```

预期：骨架从合成 case.json 正确提取 5 个契约字段；budget 在 41/64 告警；reruncheck 报 DRIFT×3；finalize 对 partial 放行、对蓄意 success 拒收（exit=5）。产物真实生成于 `examples/minimal/outputs/`。

## 平台运行契约

输入 `/input/case.json`、`/input/task.md`、论文材料；工作区 `/app/work`；交付 `/app/output/result.json`（init 时即含原 `case_id` 与 `output_contract` 全部字段）。partial 是合法最终状态；门禁 exit=5 时禁止交付。

## 限制

不做任何论文内容判断；预算计数依赖 Agent 自报（平台 token 计量为准，本工具是安全网不是计量器）；复跑一致性需要两次运行的 findings 文件。
