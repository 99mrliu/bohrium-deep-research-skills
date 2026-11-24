# a-source-fidelity-ledger（事实锚定学术翻译 Skill）

面向 Bohrium Playground 挑战「写作12｜学术翻译与双语写作」（EN↔ZH）的独立 Skill 包。
本包的重心是**上游数据真实性**：对源文做溯源锚定抽取，把源文中每一个数字 / 单位 /
百分数 / 区间 / 年份 / 引用 / 图表参照写入机器可校验的事实台账（`facts.jsonl`），
翻译完成后用确定性脚本审计译文是否保留了台账中的全部事实。术语、对齐、边界等
其他环节仅作一行级配合，不重复造术语库 / 对齐机器。

## 文件地图

```
a-source-fidelity-ledger/
├── SKILL.md                        # Skill 主文件（触发条件、工作流、运行时契约）
├── README.md                       # 本文件
├── GITHUB_URL.txt                  # 仓库地址
├── scripts/                        # 纯 Python 3 标准库（pdftotext 可选，子进程调用）
│   ├── extract_source.py           # PDF/文本 → source.txt + pages.json + extraction_manifest.json
│   ├── build_fact_ledger.py        # source.txt → facts.jsonl（F0001… 稳定编号）
│   └── audit_translation.py        # facts.jsonl + 译文 → audit_report.json（缺失/篡改则退出码非零）
├── references/
│   ├── method.md                   # 抽取与保真规则（舍入/单位/万亿跨locale/判定语义/[待确认]）
│   └── output_contract.md          # 如何诚实填写 /app/output/result.json
└── examples/synthetic/             # 合成示例（虚构数据），含脚本真实输出
    ├── source.txt                  # 虚构英文源文
    ├── translation_zh.md           # 手写中文译文（一处刻意 normalized：2.5 million → 250 万）
    ├── facts.jsonl                 # 实际运行产出（24 条事实）
    ├── audit_report.json           # 实际运行产出（23 preserved / 1 normalized，退出码 0）
    ├── extraction_manifest.json    # 实际运行产出
    └── README.md                   # 示例说明与复现命令
```

## 快速运行示例

```bash
B=/path/to/a-source-fidelity-ledger
W=$(mktemp -d)
python3 "$B/scripts/extract_source.py" "$B/examples/synthetic/source.txt" -o "$W"
python3 "$B/scripts/build_fact_ledger.py" "$W"
python3 "$B/scripts/audit_translation.py" "$W/facts.jsonl" \
    "$B/examples/synthetic/translation_zh.md" -o "$W/audit_report.json"
echo $?   # 0 = 无 missing/altered
```

负例自检：删掉译文中的 `2,004 美元` 再跑审计 → 退出码 1，该事实判为 `missing`；
把 `8.2%` 改成 `8.7%` → 判为 `altered` 并伴随一条 `added` 警告。

## 运行时要点

- 先读 `/input/case.json` 与 `/input/task.md`，记录真实 `case_id` 与 output_contract
  的每个字段；尽早写出 `status: "partial"` 的 `result.json`，之后每阶段原子更新。
- 预算：64 次模型请求 / 900 秒 —— 先跑确定性脚本，再分段翻译、逐段保存。
- 审计退出码非零时必须修译文重审；任何 `normalized`/`added` 都要在映射与
  `change_log.md` 中列明；不可核验内容标 `[待确认]`。
