# text-fidelity-gate

论文逻辑与论证审查（Bohrium challenge-16d4414d）参赛 Skill —— **上游输入保真**方向。

审查之前先证明审查对象是真的：PDF/文本抽取 → 保真证书（pass/degraded/fail）→ 全文句子锚定（S0001… + 偏移）→ 交付前逐字 quotecheck。截断、扫描件、串栏不再静默漏检，而是变成 result.json 里可核对的"未检查项"。

## 组成

| 文件 | 作用 |
|-|-|
| `SKILL.md` | Skill 本体：触发条件、运行契约、执行协议、异常处理 |
| `scripts/fidelity.py` | 引擎：extract / certificate / anchor / quotecheck 四子命令，纯标准库（Python ≥3.8），确定性，零依赖 |
| `references/fidelity_rubric.md` | 每种告警的含义、误报边界、标准处置 |
| `examples/minimal/` | **合成示例**（非正式案例）：合成截断短文 + 一真一假两条 quote，端到端演示门禁与 quotecheck |
| `GITHUB_URL.txt` | 本作品公开仓库链接 |

## 快速验证（本地）

```sh
sh examples/minimal/run_example.sh
```

预期：certificate 退出码 2（degraded，检出 abrupt_end 截断告警）；anchor 产出 35 句；quotecheck 退出码 4，只拦下伪造的 DEMO-BAD。产物真实生成于 `examples/minimal/outputs/work/`。

## 平台运行契约

输入 `/input/case.json`、`/input/task.md`、论文材料；工作区 `/app/work`；交付 `/app/output/result.json`（含原 `case_id` 与 `output_contract` 全部字段、诚实 status、provenance 含 `paper_sha256`、uncertainty 如实列未检查项）。PDF 无文本层、截断、缺章节各有明确处置，不编造审查结果。

## 限制

不判断论文对错（那是下游审查的事）；章节识别依赖规范标题；串栏需渲染目检仲裁。详见 references/fidelity_rubric.md。

维护：随 challenge-16d4414d 提交版本冻结；问题与复跑方式见上。
