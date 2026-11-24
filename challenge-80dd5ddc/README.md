# 科研知识库问答（challenge-80dd5ddc）— 五个独立方向 Skill

本目录为 challenge-80dd5ddc（科研知识库问答：科研资料管理——整理文件，也保留
版本关系）的参赛交付。五个 bundle 相互独立、零共享文件，重心互不重叠：

| Bundle | 重心 | 核心机制 |
|-|-|-|
| [kbqa-ingest-forensics](kbqa-ingest-forensics/) | 上游数据真实性 | 取证级哈希编目 + 独立重算复核 + 行政备注优先的版本谱系 + 修复台账 |
| [kbqa-answer-forge](kbqa-answer-forge/) | 带来源引用的问答生产线 | 问题分解 → BM25-lite 检索（阴性留痕）→ 逐字引文机器核验闸门 → 硬性收尾 |
| [kbqa-abstention-court](kbqa-abstention-court/) | 不确定性分级与拒答 | 证据面覆盖矩阵 + 冲突登记 + 五级机器裁决 + 越级申报强制回降 |
| [kbqa-replay-ledger](kbqa-replay-ledger/) | 过程质量控制 | 哈希链操作日志 + 输入覆盖审计 + output_contract 自检 + 第三方重走包 |
| [kbqa-kb-renderer](kbqa-kb-renderer/) | 下游渲染与交接工程 | 可导航交接包（知识库地图/catalog.csv/答案卡）+ 断链/哈希/引文三类机检 |

每个 bundle 含：SKILL.md（YAML frontmatter、运行时合同、异常处置、自查清单）、
scripts/（stdlib-only 确定性脚本，exit 0 纪律）、references/（契约与判据）、
examples/（**合成示例**：make_fixture.py + run_example.sh，可本地端到端复跑，
输出为虚构数据）、GITHUB_URL.txt。

运行时合同：技能安装于 /skills/weekly-skill；输入 /input/case.json + task.md +
真实资料库；工作区 /app/work；交付 /app/output（result.json 含 case_id 与
output_contract 全部字段、诚实 status/sources/uncertainty/change_log）；
第一步即落保底 partial result.json，脚本失败只进产物记录不崩溃。
