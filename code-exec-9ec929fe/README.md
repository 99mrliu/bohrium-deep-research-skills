# 科研代码生成与执行：科研数据分析（challenge-9ec929fe）

挑战 [科研代码生成与执行：科研数据分析：给出结果，也保留计算依据](https://play.bohrium.com/challenge/challenge-9ec929fe) 的五个相互独立参赛作品。每个目录是一个自足的可加载 Skill（SKILL.md + scripts + references + examples），五方向重心错位、零共享文件，全部面向平台固定案例形态（/input 的 case.json 含 case_id 与 output_contract、task.md、数据字典、CSV 快照与 SQLite 数据库 → /app/output 的可复核 result.json）：

| 目录 | Skill | 方向重心 |
|-|-|-|
| [a-semalign-contract](a-semalign-contract/) | 上游契约与字段语义对齐门禁 | 上游数据真实性：output_contract 编译为机检契约、数据字典↔实际列名归一化对齐（歧义强制人工裁决）、先落盘诚实 result.json 骨架、交付前契约门（case_id/字段齐全/图文件存在/provenance） |
| [b-envport-core](b-envport-core/) | 零依赖可移植执行核心 | 环境配置：纯标准库实现清洗/统计（Welch t、Pearson、OLS）/SQLite 只读查询/绘图，任何 Python≥3.8 免安装逐字节复现；matplotlib 缺失显式降级；env 快照 + run_log + finalize |
| [c-silenterror-auditor](c-silenterror-auditor/) | 静默错误猎手 | 结果验证：scan 计算前挖出缺失当 0/重复行/哨兵值/NULL 口径等陷阱并试算影响；audit 把每个结论数字登记为 claim 并从原始输入独立重算，MISMATCH 即 exit 1 阻断 success |
| [d-run-forensics](d-run-forensics/) | 运行取证与重放 | 过程质量控制：runcap exec 命令级台账（退出码/stdout/stderr/输入哈希/失败自动分类）、重试链、replay.sh 生成与真实重放、seal 强制诚实 partial |
| [e-figure-fidelity](e-figure-fidelity/) | 图表保真与渲染证据链 | 下游渲染工程：PNG + .data.csv + .receipt.json 三件套；lint 机检列名/PNG 哈希/值域/单位-字典/轴标签一致性；无 matplotlib 诚实降级 |

五者互不依赖，可分别安装到 `/skills/weekly-skill` 使用；各目录 examples/ 内为**合成示例**（人工合成数据，非正式案例结果），`bash examples/run_example.sh` 可端到端复跑：脚本真实执行、产物真实生成。统计实现已交叉核对（envport 的 Welch t 与 Pearson r/p 对 scipy 差异 <1e-10）。详见各目录 SKILL.md。
