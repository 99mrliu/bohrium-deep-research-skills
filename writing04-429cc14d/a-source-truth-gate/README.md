# source-truth-gate

上游数据真实性核验关：面向「参考文献与引用管理」类写作任务的 skill。任何文献
条目、任何论断-引用对应关系，必须先过核验关才能进入改后稿；核验不过的条目
隔离登记（不删除），核验不过的论断-来源对应修复或降级标注。宁可输出变保守，
不让假文献、错元数据、错配引用流入成品。

## 文件清单

```text
SKILL.md                        技能主文档（运行时契约、五阶段流程、异常处理表）
README.md                       本文件
scripts/
  source_registry.py            来源目录 SHA-256 登记册（确定性、仅标准库）
  verify_entries.py             条目身份与元数据核验（对照可信快照的状态机）
  claim_anchor_audit.py         论断-来源锚点审计（逐字引文子串核验+FAIL 诊断）
references/
  verification_policy.md        状态机定义、处置规程、DOI 失败分类学、修复手册
  ledger_formats.md             entries/snapshot/claims 及各报告 JSON 的字段级格式
examples/
  minimal_example.md            逐步命令与预期结果（合成示例）
  input/sources/                三篇虚构论文文本（合成数据，不对应真实文献）
  input/entries.jsonl           6 条虚构条目（含 2 条埋雷）
  input/snapshot.json           虚构可信快照
  input/claims.jsonl            5 条虚构论断台账（含 1 条埋雷）
  output/                       上述脚本的真实运行产物
```

## 安装

无依赖：Python 3.10+ 标准库即可，无第三方包、无网络访问。评测环境中脚本
位于 `/skills/weekly-skill/scripts/`；本地使用时直接以 `scripts/` 相对路径调用。

## 快速开始

```bash
# 1. 登记来源指纹
python3 scripts/source_registry.py --sources examples/input/sources \
  --out /tmp/registry.json

# 2. 条目核验（示例含埋雷，预期退出码 1）
python3 scripts/verify_entries.py --entries examples/input/entries.jsonl \
  --snapshot examples/input/snapshot.json --out /tmp/verify

# 3. 论断锚点审计（示例含埋雷，预期退出码 1）
python3 scripts/claim_anchor_audit.py --sources examples/input/sources \
  --ledger examples/input/claims.jsonl --out /tmp/anchor
```

退出码语义：核验类脚本检出必须隔离/修复的缺陷时退出码为 1，全部通过为 0；
这是工作流程信号，不是脚本故障。详见 examples/minimal_example.md。

## 限制

- 核验依据仅为输入快照与来源文本；脚本不联网，不做在线 DOI 解析。
- 快照未覆盖不等于伪造（not_found_in_snapshot 是保守拦截，不是判决）。
- 锚点审计只支持纯文本来源；PDF/DOCX 需先抽取为文本。
- 去重、编号、GB/T 7714 / APA 7 渲染为程序性指引，由模型按 task.md 执行，
  本 skill 的机械保证集中在身份核验与引文锚定两层。
