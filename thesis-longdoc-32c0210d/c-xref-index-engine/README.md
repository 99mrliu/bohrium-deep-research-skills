# xref-index-engine — 跨章节一致性索引引擎

面向玻尔 Playground 竞赛题 challenge-32c0210d（学位论文与长文档写作）的 Skill bundle。
重心：把整部分章节 Markdown 工作稿建成**机器可查的注册表**，确定性检查
悬空图表引用、重复题注编号、标题编号断裂、引文/条目失配、缩略语重复定义、
术语漂移，并在编辑前做**级联影响分析**（改一处，找全所有受影响段落）。

## 结构

```
SKILL.md                       # 可直接照做的命令序列工作流（/skills/weekly-skill 路径）
GITHUB_URL.txt
scripts/
  build_index.py               # 章节目录 -> index.json（headings/floats/refs/citations/abbr/terms）
  check_consistency.py         # index.json -> consistency_report.json（error/warn 分级，有 error 退出码 1）
  impact.py                    # --anchor/--term/--section + --renumber 模拟 -> impact_report.json
  make_result.py               # 运行时读 case.json output_contract.fields 逐字段填充，原子写 result.json
references/
  consistency_rules.md         # 每条规则的触发条件、级别、修复建议
  index_schema.md              # index.json 结构与扫描口径（含全角/连字符归一化）
examples/synthetic/
  input/                       # 合成 case.json + 工单 + 3 个短章节（钙钛矿太阳能电池封装）
  run_example.sh               # 一键端到端：首检捕获预埋问题 -> 修复 -> impact -> 复检 PASS -> result.json
  expected/                    # 真实运行固化的预期产物（含 *_before_fix 首检报告）
```

## 快速验证（macOS /bin/bash + 系统 python3，纯标准库）

```bash
bash examples/synthetic/run_example.sh
for f in consistency_report_before_fix.json consistency_report.json impact_report.json result.json; do
  diff examples/synthetic/expected/$f examples/synthetic/runtime/output/$f   # 应全部一致
done
```

## 合成示例声明

`examples/synthetic/` 下所有输入与产物均为**合成示例**（主题自造，与任何真实论文无关），
文件内含 `"note": "SYNTHETIC EXAMPLE — 合成示例，非正式案例结果"` 标注。
预埋问题：一个 dangling 图表引用、一个重复题注编号、一个跨章重复定义、一个术语两写法；
工单 2 条（修 dangling 引用、术语统一）。

## 已知边界

结构性检查不判断科学正误；作者-年份引用仅 `[n]` 数字引文参与核对；题注识别基于
行首浮动体 token 约定。详见 SKILL.md §7。
