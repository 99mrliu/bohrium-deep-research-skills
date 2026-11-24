# termbase-forge — 术语资产工程技能包

面向 Bohrium Playground 挑战「写作12｜学术翻译与双语写作」（EN↔ZH）的独立
Skill bundle。核心重心是**术语资产工程**：从真实源文本抽取术语候选、
人工策划带学科消歧的锁定双语术语表（一词一译 / 术语锁定），并用纯标准库
脚本在摘要、正文、图注、附录全范围内确定性强制一致性。数字核对、句对齐、
边界记录由案例其他机制负责，本包只各提一句、不重复建设。

## 文件地图

```
SKILL.md                      技能说明（用途/触发/工作流/调用/输入输出/异常/运行时契约）
README.md                     本文件
GITHUB_URL.txt                仓库地址
scripts/
  extract_terms.py            源文本 → terms_draft.json（首字母缩写、首字母大写复合词、
                              连字符复合词、停用词过滤的 2-4 词高频 n-gram；含频次、
                              章节直方图、例句）
  lint_glossary.py            校验 glossary.json 模式与冲突（必填字段、重复冲突译名、
                              空译名、译名夹带未翻译源词、forbidden_variants 自相矛盾）；
                              出错退出码非零，支持 --json
  check_consistency.py        glossary + 源文 + 译文 → glossary_check.json；逐章节强制
                              锁定译名、forbidden_variant 报错（带行号）、untranslated_leak
                              报错、首现形式缺失警告；出错退出码非零
references/
  method.md                   术语规则：一词一译锁定、学科消歧（cell=电池/细胞、
                              bond=化学键/债券…）、首现约定「中文全称（English full name, ABBR）」、
                              源文本不一致时用 [待确认] 记录、图注/附录继承锁定
  output_contract.md          如何填写 /app/output/result.json（读取真实 case_id 与
                              output_contract 的每个字段，诚实状态，来源/不确定项/变更记录）
examples/synthetic/           小型全合成工作示例（合成示例 / synthetic example）：
                              source.txt、glossary.json、translation_zh.md，以及实际
                              生成的 terms_draft.json、lint_output.txt、glossary_check.json
```

脚本仅依赖 Python 3 标准库（无 pip、无网络）。

## 运行示例

```bash
cd examples/synthetic
python3 ../../scripts/extract_terms.py source.txt -o terms_draft.json   # 抽取候选术语
python3 ../../scripts/lint_glossary.py glossary.json                    # 退出码 0 = 通过
python3 ../../scripts/check_consistency.py glossary.json source.txt translation_zh.md -o glossary_check.json
# 7 个术语全部 locked_ok，退出码 0
```

详见 `examples/synthetic/README.md`。
