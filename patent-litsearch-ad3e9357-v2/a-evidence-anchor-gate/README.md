# verbatim-anchor-evidence-gate

**上游数据真实性（反编造证据锚定）门控技能**，面向 Bohrium Playground 挑战
"专利与技术文献检索"（challenge-ad3e9357）。核心主张：凡写入 `result.json` 的
字段级事实必须携带逐字引用锚点（quote + 源文件 sha256），确定性审计脚本阻断
任何在登记源文件中找不到出处的引用——审计不过宁可 `partial`。

## 目录结构

```
SKILL.md                              # 技能说明（YAML frontmatter + 运行时契约）
README.md                             # 本文件
GITHUB_URL.txt                        # 源码仓库地址
scripts/
  source_register.py                  # 源登记：path/sha256/size/解码说明，PDF 抽文本，OCR 容差预声明
  quote_audit.py                      # 确定性审计：逐字子串校验 + 声明式容差裁决
  scaffold_result.py                  # 诚实 partial 骨架：镜像 output_contract 全字段
  selfcheck.py                        # 端到端自测（fixtures 正例 + 两个反例 + 骨架校验）
references/
  anchoring_protocol.md               # 锚定协议：锚定范围、locator 格式、归一化规则
  tolerance_declaration.md            # OCR 容差声明规则
examples/
  example_walkthrough.md              # 可复现的最小调用示例（真实命令 + 真实输出）
  fixtures/                           # 全部为明确标注的合成虚构数据
    case_fixture.json
    src_patent_EX1001.txt             # 虚构专利记录（合成示例）
    src_paper_EX2001.txt              # 虚构论文摘要（合成示例）
    result_ok.json                    # 正例：全部 quote 逐字命中
    result_bad_forged.json            # 反例：一条 quote 系编造
    result_bad_tolerant_undeclared.json # 反例：OCR 噪声近似匹配但未声明容差
```

## 快速开始

```bash
cd <本技能目录>

# 0) 自测（应 5/5 PASS，exit 0）
python3 scripts/selfcheck.py

# 1) 骨架先行
python3 scripts/scaffold_result.py --case /input/case.json --out /app/output --status partial

# 2) 登记源文件
python3 scripts/source_register.py --roots /input --out /app/work/registry.json --workdir /app/work

# 3) 填充 result.json（每个事实带逐字 quote 锚点）后审计
python3 scripts/quote_audit.py --result /app/output/result.json --registry /app/work/registry.json
```

退出码约定：`0` 成功 / 审计通过，`1` 审计失败，`2` 用法或输入错误。
所有脚本仅依赖 Python 3 标准库；PDF 文本抽取在系统提供 `pdftotext` 时自动启用，
缺失时降级为 `unavailable` 并继续。

更多细节：`SKILL.md`（运行时契约）、`references/anchoring_protocol.md`、
`references/tolerance_declaration.md`、`examples/example_walkthrough.md`。
