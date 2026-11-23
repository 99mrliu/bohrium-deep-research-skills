# 多文档比较与整合（challenge-95061011）— 五方向独立 Skill 集

围绕"多文档比较与整合"的五个截然不同重心的独立 Skill bundle，相互零共享文件，
各自含完整 SKILL.md（合法 YAML frontmatter）、scripts/、references/、可运行的合成最小示例
（examples/，全部合成数据，非正式案例结果）。

| Bundle | Skill name | 重心 |
|---|---|---|
| [A-corpus-forensics](A-corpus-forensics/) | corpus-forensics-registry | 上游数据真实性：语料取证、重复/多版本检测、哈希锚定段落注册表 |
| [B-obligation-ledger](B-obligation-ledger/) | obligation-ledger-coverage | 需求侧完整性：工单编译为回答义务台账，逐条闭环与覆盖度门禁 |
| [C-measurement-forge](C-measurement-forge/) | measurement-forge | 抽取工程：数值-单位-口径同源绑定，量纲代数与 quantity-kind 登记 |
| [D-comparability-court](D-comparability-court/) | comparability-court | 判定逻辑：可比性裁定记录 + 定量合成守门（无 permit 不合成） |
| [E-replay-delivery](E-replay-delivery/) | replay-delivery-contract | 下游渲染与过程质量控制：确定性渲染、契约 lint、字节级复跑 |

每份 bundle 遵循平台运行契约：读 /input/comparison-workorder.json 与语料，
构建带 exact source_document_id + paragraph_id 的共同字段比较矩阵，在定量合成前检验
task/metric/units/material/pollutant/budget 六个维度可比性，result.json 含 case_id 与
output_contract 全部字段，诚实 partial。运行示例：`cd <bundle>/examples && bash run_example.sh`。
