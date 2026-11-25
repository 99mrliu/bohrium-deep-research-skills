# v2-a-source-veracity-gate

面向 Playground 竞赛题 challenge-60a8202d「引文追踪与关联文献发现」的 Skill
bundle，工程重心是**上游数据真实性与溯源门控**：先审计、后扩展。

加载本 Skill 后，Agent 用三条确定性命令完成一个案例：

```bash
# 1) 来源审计：递归扫描语料根，登记来源注册表，损坏文件登记而非中断
python3 scripts/source_audit.py --workdir /app/work

# 2) 构建结果：种子解析 → 去重合并 → 引用图 → 1–2 层扩展 → locator 门禁
python3 scripts/build_result.py --case /input/case.json --task /input/task.md \
    --out /app/output --workdir /app/work

# 3) 交付自查：contract 镜像完整性、locator 完整性、status 一致性
python3 scripts/selfcheck.py --out /app/output --case /input/case.json
```

核心机制：

- **全语料来源注册表**：每个语料文件登记相对路径、sha1、字节数、判定格式
  （crossref / europepmc / openalex / edge-list / node-table / generic /
  unknown）、解析记录数与失败原因；解析失败的文件进入注册表而不是中断管线。
- **冲突台账**：自动检出"同 DOI 不同标题""同标题不同 DOI"两类线索，
  写入 `audit_report.md` 与 `source_registry.json`。
- **locator 强制门禁**：每条规范化记录、每条引用边都带 `{file, pointer}`
  来源定位；任何没有 locator 的记录不得进入 candidates。
- **方向语义**：reference 边 = citing→cited；citation 边 = cited→citing；
  只给参考文献列表的数据源用全语料反向索引恢复前向边，边上标
  `direction_restored: true`。
- **契约镜像**：`result.json` 逐字段镜像 `case.json` 的 `output_contract`；
  未知语义的字段给诚实空值并在 `uncertainty` 注明。

## 目录结构

```
v2-a-source-veracity-gate/
├── SKILL.md                  # Skill 说明（frontmatter + 运行契约 + 异常处理表）
├── README.md                 # 本文件
├── GITHUB_URL.txt            # GitHub 公开链接
├── scripts/
│   ├── source_audit.py       # 阶段一：来源审计与 records_norm.jsonl
│   ├── build_result.py       # 阶段二：引用扩展、门禁与 result.json
│   └── selfcheck.py          # 阶段三：交付自查门禁
├── references/
│   ├── veracity_policy.md    # 溯源与门控规则
│   └── corpus_formats.md     # 支持的语料格式与判定逻辑
└── examples/                 # 合成示例（SYNTHETIC，非真实文献）
    ├── corpus/               # 迷你语料：2×Crossref 风格 + 1×EuropePMC 风格 + 1 个损坏文件
    ├── case.json             # 含 output_contract 的合成案例
    ├── task.md               # 合成任务说明
    ├── walkthrough.md        # 运行说明与预期输出要点
    └── run_out/              # 合成示例的真实运行产物（示意输出）
```

## 依赖与约束

- Python 3，仅标准库；脚本位置无关（pathlib）；默认离线，无网络调用。
- 全部 UTF-8 文本文件，无符号链接。

## 合成示例声明

`examples/` 下所有文献均为虚构（DOI 形如 `10.0000/synth.*`），仅用于演示
审计与门控能力；`run_out/` 是这些合成输入的真实运行产物，**不是正式案例结果**。

## 在本地跑合成示例

```bash
cd v2-a-source-veracity-gate
python3 scripts/source_audit.py \
    --roots examples/corpus --workdir examples/run_out/work
python3 scripts/build_result.py \
    --case examples/case.json --task examples/task.md \
    --out examples/run_out --workdir examples/run_out/work
python3 scripts/selfcheck.py \
    --out examples/run_out --case examples/case.json
```

预期：损坏文件被登记（status=failed）而非中断；同 DOI 不同标题冲突被检出；
全部候选与边带 locator；`result.json` 镜像 `output_contract` 全字段；
selfcheck 打印 `ok=true`，退出码 0。
