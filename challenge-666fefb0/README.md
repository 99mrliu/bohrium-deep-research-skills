# challenge-666fefb0 文献与资料自动分类：五个独立 Skill 作品

题目：科研资料管理——整理文件，也保留版本关系（文献分类、标签生成、自动命名、
去重与版本区分、批量整理）。

本目录包含五个**相互独立、零共享文件**的 Skill bundle，每个解决同一任务但重心
截然不同，各自含完整 `SKILL.md`、`scripts/`、`references/` 与可一键运行的
合成示例（`examples/`，`make_fixture.py` 生成夹具，`run_example.sh` 端到端跑通）。

| Bundle | 重心 | 核心机制 |
|---|---|---|
| [bundle-a-field-provenance-keeper](bundle-a-field-provenance-keeper/) | 上游数据真实性 | 字段级 provenance 台账（layer+逐字证据）+ 锚定 lint 机械复验，锚不住一律降级 unknown 并记冲突 |
| [bundle-b-catalog-delivery-forge](bundle-b-catalog-delivery-forge/) | 下游交付渲染工程 | 脚本先出确定性提案、模型只写覆盖项；四件套交付物（catalog.md/catalog.csv/tree_diff.md/verify_report.md）同源渲染、fid 交叉链接 |
| [bundle-c-idempotent-rerun-controller](bundle-c-idempotent-rerun-controller/) | 过程质量控制 | plan(plan_hash)→apply(journaling+断点续跑)→verify→certify(输出树指纹幂等证书)→undo(可回滚) |
| [bundle-d-version-relation-graph](bundle-d-version-relation-graph/) | 版本关系语义图谱 | 六类信号 typed-edge 有向图（duplicate_of/same_work/version_of/supplement_of），canonical 显式打分裁决、证据不足诚实为 null |
| [bundle-e-anomaly-triage-guardian](bundle-e-anomaly-triage-guardian/) | 异常分诊与诚实降级 | 12+1 类分诊 taxonomy，异常文件 `_quarantine/<类别>/` 原样隔离，单文件异常永不阻塞，状态诚实状态机 |

共同运行契约：输入 `/input/case.json`+`task.md`（防御式解析，不假设字段名），
工作目录 `/app/work`，交付 `/app/output/result.json`（含原 case_id 与
output_contract 全部字段、诚实 status）、整理后 `library/`、操作日志与复核证据。
Python 3 标准库；pdftotext 缺失时降级登记。每个 bundle 根部的 `GITHUB_URL.txt`
第一行即本作品公开链接。

所有示例均为**合成示例**（演示数据），非平台正式案例结果。
