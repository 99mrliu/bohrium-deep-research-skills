# challenge-da62e8d4「论文复现与方法验证」— 五方向独立 Skill 提交

本目录包含 5 份相互独立、零共享文件的 Skill bundle。五份的重心按流水线位置彻底错位，不是同一管道的变体：

| bundle | 重心 | 一句话 |
|-|-|-|
| `provenance-gate/` | 上游证据真实性 | 论文目标值必须带逐字引文，脚本与真实 PDF 文本层机械比对，不过门即隔离，不进入比较 |
| `rng-determinism-lab/` | 运行环境与随机性取证 | 比较之前先证"同机重跑得到同一个数"：AST 未播种审计 + 受控重放 identical/stable/unstable + 环境快照 |
| `tolerance-court/` | 事前容差与统计判定 | 容差先注册后运行（防事后篡改），按论文书写位数推半单位容差，多种子分解随机波动 vs 系统偏差 |
| `report-compiler/` | 下游渲染与可核验报告 | 报告是编译产物：所有数字来自台账，审计器逐格对账、查孤儿数字，自动生成论文值+容差带对比图 |
| `run-supervisor/` | 过程质量控制 | 状态机+检查点，任意时刻磁盘上的 result.json 都是合法诚实部分结果，失败/超时是证据不中断，finalize 重算不信任记忆 |

每份 bundle：`SKILL.md`（合法 YAML frontmatter，含 /input、/app/work、/app/output 运行契约）、`scripts/`（仅 Python3 标准库）、`references/`、`examples/`（合成示例，非正式案例结果）、`GITHUB_URL.txt`。
