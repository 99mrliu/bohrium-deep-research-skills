# Bundle E — 过程质控与可复核交付工程（feasibility-review-qc-foundry）

面向 Bohrium Playground 挑战「实验方案可行性评估」（challenge-2e2c5820）的 Skill 包。
把可行性审查当作可审计流水线：契约优先脚手架 → 六道质控门 → 可复算 manifest →
stdlib-only 渲染交付。

## 目录结构

```
outputs/
  SKILL.md                      # 技能定义（运行时安装于 /skills/weekly-skill）
  README.md                     # 本文件
  GITHUB_URL.txt                # 仓库地址（首行为规范 URL）
  scripts/
    parse_contract.py           # 步骤0：契约解析 + honest-partial 骨架
    validate_result.py          # 契约符合性校验（exit 2 + 逐项违规）
    lint_review.py              # 审查报告自洽性 lint（R1-R5）
    make_manifest.py            # SHA-256 可复算清单（json+md，含复算命令行）
    render_report.py            # Markdown 子集 → 独立 HTML（徽章/目录/锚点索引）
    selfcheck.py                # G1-G6 聚合质控门 → qc_report.md
  references/
    qc_gates.md                 # 六门定义：判据/严重度/修复建议
    partial_policy.md           # 诚实 partial 状态机 + checkpoint 节奏
  examples/synthetic/           # 合成示例，非正式案例数据
    case.json / task.md
    review_report.md            # 正例（通过全部 lint）
    bad_review_report.md        # 负例（植入 R2/R5 硬违规 + R3/R4 警告）
    run_example.sh              # 端到端演示（正例 exit 0 + 负例如期失败）
    output/                     # run_example.sh 的真实运行产物
```

## 快速开始

```bash
cd examples/synthetic
bash run_example.sh        # 期望 exit 0
```

## 退出码约定

- 全部脚本：误用/文件缺失 → 非零退出 + 中文错误消息。
- `validate_result.py` / `lint_review.py`：违规 → exit 2，逐项打印。
- `selfcheck.py`：任一质控门 FAIL → exit 1；仅 WARN 或全 PASS → exit 0。

## 运行时集成要点

- 平台将本包安装到 `/skills/weekly-skill`，案例输入在 `/input/`，交付写到 `/app/output`。
- 步骤 0 的骨架必须**立即**复制为 `/app/output/result.json`（诚实 partial 从第一分钟起）。
- render_report.py 产出 HTML 后，按平台 office-renderer 能力补 PDF/PNG 预览（G6 认可
  html/pdf/png 任一种）。
- 全部脚本仅依赖 Python 3 标准库，无网络、cwd 无关、绝对路径安全。
