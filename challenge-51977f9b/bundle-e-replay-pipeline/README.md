# slr-replay-pipeline

系统性文献综述的**过程工程** Skill：全流程状态机 + PRISMA 计数对账 + 断点续跑 +
确定性重放与漂移检测。治理两类顽疾——"任务中断后无法定位是哪一步出的错"与
"换人拿着同样输入无法复跑"。

## 签名能力

- **runlog.py**：追加式登记账。每个环节的输入/产物以 SHA-256 + 路径 + 字节数入账；
  `verify` 重算哈希，任何篡改/缺失 exit 3 并**指名步骤与文件**；`status` 给出断点
  续跑的下一个标准环节。
- **reconcile.py**：PRISMA 计数逐账轧平（F1–F5），任何不平衡 exit 3 并输出失衡环节
  与差值（如 `F2: screened=100 但 excluded_ta(85)+fulltext(13)=98, diff=2`）。
- **replay.py**：按 manifest 在干净目录重跑确定性步骤（每步跑两次识别非确定性），
  产物与 runlog 登记哈希逐字节比对；漂移 exit 3 并指名首个漂移步骤。

## 布局

```
SKILL.md             # 本体（工作流程、合同映射、异常处理、自查）
scripts/             # parse_case.py / scaffold_result.py / runlog.py / reconcile.py / replay.py / selfcheck
references/          # pipeline_protocol.md / counts_reconciliation.md / resume_guide.md
examples/            # 合成示例：8 条题录迷你流水线 + 合规/埋雷 flow.json + run/ 真实运行产物
```

## 快速开始

```bash
python3 scripts/selfcheck        # 端到端自检（正例 exit 0，负例 exit 3 指名故障点）
bash examples/run_example.sh     # 合成示例全流程（reconcile/verify/replay 全绿）
```

## 退出码约定

0 = 通过；2 = 输入/材料不足（诚实降级）；3 = 校验失败（违反规则，报错带规则码：
R* 输入类、V* 校验类、F1–F5 轧账类）。

## 限制

- 脚本仅 Python 3 标准库；replay 单步超时 120s；
- 含模型判断的环节（筛选判定、质量评价、综合写作）不可字节级重放，按
  references/resume_guide.md 以"冻结登记"方式纳入账本，replay 覆盖冻结输入之后的
  全部确定性计算；
- examples/ 全部为合成示例数据，不冒充正式案例结果。
