# 写作02｜学术语言润色 (product-arena-02-7051d92d) — 五个独立方向的 Skill bundles

题目：<https://play.bohrium.com/challenge/product-arena-02-7051d92d>

五个 bundle 相互独立、零共享文件，各含完整 `SKILL.md`（合法 YAML frontmatter）、
`scripts/`（Python 3 标准库，无网络依赖）、`references/`、`examples/minimal/`
（合成示例，已本地端到端跑通并目检）。五份的重心刻意错位，不是同一管道的变体：

| Bundle | Skill | 重心 |
|---|---|---|
| [a-termbase-gate](a-termbase-gate/) | `termbase-gated-polish` | 上游术语资产：术语表抽取/锁定 + 改后全篇一致性回扫门 |
| [b-strength-conservator](b-strength-conservator/) | `strength-conserving-polish` | 语义保持机器核验：限定强度五级阶梯 + 四维护栏 + 漂移回退 |
| [c-bilingual-detox](c-bilingual-detox/) | `c2e-detox-polish` | 中英表达质量：直译腔模式库 + 跨语言守恒 + 回译抽检门 |
| [d-register-styler](d-register-styler/) | `genre-register-polish` | 文体语域贴合：文体识别 + 语域体检 + 改前改后评分卡门 |
| [e-audit-ledger](e-audit-ledger/) | `audit-trail-polish` | 下游可复核交付：逐句台账 + 自包含 review.html + 幂等/确定性自检 |

每个 bundle 都遵循 Harbor 运行契约：读 `/input/case.json` 与 `task.md`，在 `/app/work`
工作，交付 `/app/output`（含镜像 `output_contract` 全部字段与 `case_id` 的
`result.json`，诚实标注 success / partial / blocked）。本地复现：

```sh
cd <bundle>/examples/minimal && sh run.sh
```

`examples/` 下的一切输入与产物均为**合成示例**，不是平台正式案例，也不是预置答案。
