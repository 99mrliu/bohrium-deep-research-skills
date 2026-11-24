# 材料取证报告

| 文件 | 大小(B) | 格式 | 处置 | 页数 | 字符数 | 说明 |
|---|---|---|---|---|---|---|
| case.json | 321 | json | OK | - | - |  |
| task.md | 118 | md | OK | - | - |  |
| sources/paper_a.txt | 496 | txt | OK | 1 | 199 |  |
| sources/paper_b.txt | 298 | txt | OK | 1 | 107 |  |
| sources/paper_c_corrupt.txt | 987 | txt | DEGRADED | 1 | 331 | 文本含异常字符，疑似编码损坏 |

## 结论

- 可用来源（OK）：2；降级（DEGRADED）：1；不可用（UNUSABLE）：0。
- DEGRADED 来源只能支撑带〔材料质量受限〕标注的表述；UNUSABLE 来源不得支撑任何事实句。
- case.json 中声明的线索见 sources_registry.json 的 declared_hints；声明而缺失、存在而未声明都应在 result.json 的 limits 中说明。
