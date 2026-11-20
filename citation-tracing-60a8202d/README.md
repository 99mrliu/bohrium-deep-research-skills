# 引文追踪与关联文献发现（challenge-60a8202d）：三个独立方向的 Skill

本目录是 Bohrium Playground 赛题 [challenge-60a8202d 引文追踪与关联文献发现](https://play.bohrium.com/challenge/challenge-60a8202d) 的参赛作品。三个方向在方法、代码与文档上完全解耦，各自为可独立安装、独立运行的 Skill bundle：

| 目录 | Skill | 对应题目方向 | 核心方法 |
|-|-|-|-|
| [a-snowball-tracer](a-snowball-tracer/) | `dir-aware-snowball-tracer` | 方向 1：前向/后向追踪 | 方向感知多跳雪球扩展；反向索引恢复前向边（解决"只给参考文献不给方向"）；分支剪枝＋停止判据全日志；逐边数据源定位 |
| [b-cocitation-discovery](b-cocitation-discovery/) | `cocitation-parallel-discovery` | 方向 2：关联文献发现 | 共被引（Ochiai 归一）＋文献耦合（Jaccard）；直接邻居按定义排除；高被引噪声抑制；逐候选双定位关联证据 |
| [c-identity-merge](c-identity-merge/) | `crossdb-identity-merge` | 方向 5：去重与身份合并 | 五路分块＋三级决策（自动合并/人工待审/分离）；预印本/会议/期刊版本对齐；合并证据账簿与字段冲突留痕 |

## 共同设计

- Harbor 运行契约：读 `/input/case.json`＋本地语料（自动发现 Crossref/EuropePMC/OpenAlex/Semantic Scholar 等异构格式），写 `/app/output/result.json`（含 `case_id`、`status`、`sources`、`uncertainty`，镜像 `output_contract` 全字段）。
- Python ≥ 3.8 仅标准库，无网络依赖（A 提供可选 `--allow-net` best-effort 核对并记录 URL）。
- 每条记录/每条边带 `{file, pointer}` 数据源定位，可独立复核；解析不出的引用目标保留为 stub，不补造元数据；空结果与部分完成如实标注。
- 每个 bundle 附独立自查脚本（verify_*.py）与合成数据最小示例（标注为示意，非正式案例结果）。

各 bundle 详细用法见各自目录的 `SKILL.md` 与 `README.md`。
