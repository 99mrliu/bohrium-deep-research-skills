# citation-support-auditor

论文逻辑与论证审查（Bohrium challenge-16d4414d）参赛 Skill —— **引用支持核查**方向。

引用核查分两层：文本内对账（引而未列、列而未引、断号、重复）由确定性引擎机判；文本外支持度（被引文献是否真支持那句话）由引擎生成逐条工作单、Agent 取证判断，取不到原文一律待复核——机制上禁止凭空断言"引用不支持"。

## 组成

| 文件 | 作用 |
|-|-|
| `SKILL.md` | Skill 本体：触发条件、运行契约、执行协议、异常处理 |
| `scripts/citescan.py` | 引擎：parse / reconcile / worksheet / verify 四子命令，纯标准库（Python ≥3.8），确定性，零依赖 |
| `references/citation_protocol.md` | 两层模型、功能分类、外部取证流程、严重度映射 |
| `examples/minimal/` | **合成示例**（非正式案例）：植入引而未列、列而未引、强主张躲引用的合成短文 |
| `GITHUB_URL.txt` | 本作品公开仓库链接 |

## 快速验证（本地）

```sh
sh examples/minimal/run_example.sh
```

预期：对账命中全部植入缺陷；worksheet 标出 1 条强主张引用；verify 退出码 4 拦下非逐字 quote。产物真实生成于 `examples/minimal/outputs/work/`。

## 平台运行契约

输入 `/input/case.json`、`/input/task.md`、论文材料；工作区 `/app/work`；交付 `/app/output/result.json`（含原 `case_id` 与 `output_contract` 全部字段、诚实 status、provenance 含引用/文献计数、uncertainty 列待复核引用）。References 缺失时引用齐全性整体待复核，禁止宣称齐全。

## 限制

author-year 匹配按"第一作者姓 + 年"归一，同年同姓多文献需人工分辨；外部取证依赖平台检索工具可用性，不可用时支持度项全部待复核；不查参考文献著录格式（本题排除项）。
