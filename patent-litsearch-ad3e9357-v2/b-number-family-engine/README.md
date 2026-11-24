# patent-number-family-engine

Bohrium Playground 挑战"专利与技术文献检索"（challenge-ad3e9357）的
Skill bundle B：**确定性专利号码规范化与同族合并引擎**。

所有号码解析、语料匹配、族合并由 `scripts/` 下的确定性 Python 脚本完成
（仅标准库，Python 3）；歧义显式呈现、绝不静默裁决；无法解析的内容原文
保留。证据台账、检索策略、法律状态与许可分级**不属于**本 bundle。

## 目录结构

```
SKILL.md                        # Skill 定义（用途/运行时契约/流水线/路由/异常/自查）
README.md
GITHUB_URL.txt
scripts/
  patent_numbers.py             # 号码规范化库 + CLI（normalize / split）
  corpus_scan.py                # 语料索引与种类容忍查询（index / query）
  family_merge.py               # simple + extended 双口径族合并
  scaffold_result.py            # result.json 骨架先行 + 深合并填充
  selfcheck.py                  # 端到端自查（45 项断言）
references/
  number_formats.md             # 各国号码格式表与边界
  family_scope.md               # 双口径定义与措辞模板
  ocr_boundary.md               # OCR 粘连唯一边界规则
examples/
  example_walkthrough.md        # 真实命令 + 示意输出（合成示例）
  fixtures/
    case_fixture.json           # 合成号码查询案例（SYNTH-EXAMPLE-002）
    corpus/rec_EX1001.txt       # 虚构专利记录（族成员 1）
    corpus/rec_EX1002.txt       # 虚构专利记录（族成员 2）
    corpus/rec_EX1003.txt       # 虚构专利记录（族成员 3）
    corpus/rec_EX2001.txt       # 虚构非专利论文（演示非专利分离）
```

## 快速开始（真实命令，输出为示意输出（合成示例））

```
$ cd skill
$ python3 scripts/patent_numbers.py normalize "US 10,293,847 B2"
```
```json
[{"input": "US 10,293,847 B2", "ok": true, "normalized": "US10293847B2",
  "kind": "grant", "country": "US", "number": "10293847", "kind_code": "B2",
  "warnings": [], "alternatives": []}]
```

```
$ python3 scripts/corpus_scan.py index --roots examples/fixtures/corpus --out /tmp/index.json
索引完成：4 文件，16 号码条目，0 不可用
$ python3 scripts/corpus_scan.py query --index /tmp/index.json --numbers "XX1000001B2" --out /tmp/hits.json
查询完成：1 号码，2 精确命中
```

## 验证

```
$ python3 scripts/selfcheck.py
```

真实输出（示意输出（合成示例）环境实测）：

```
== 1. 合法号码规范化电池 ==
[PASS] normalize 'US 10,293,847 B2' — got US10293847B2/grant/US ok=True
[PASS] normalize 'US2019/0123456 A1' — got US20190123456A1/publication/US ok=True
...（共 17 项合法格式，含 EP/CN/JP/KR/XX）...
== 2. 歧义号码 ==
[PASS] 裸 8 位号歧义 — alternatives=1
[PASS] 裸 8 位号主解读为 US 授权号 — US16123456
[PASS] JP 无种类代码歧义（公开号 vs 申请号） — alternatives=1
== 3. 非法号码 ==
[PASS] 拒绝 'NOT_A_NUMBER' / 'US12345' / '' / '##'
== 4. OCR 粘连切分 ==
[PASS] 唯一边界切分成功 — boundary=13
[PASS] 多解粘连保持原文 — boundaries=[7, 8]
[PASS] 无解粘连保持原文
== 5. 语料索引与查询 ==
[PASS] 索引含 4 个可用文本文件 / 授权号精确命中 EX1001 与 EX2001 /
       related_hits 含同号公开号 XX1000001A1 / 关键词召回 ≥2 条 ...
== 6. 双口径族合并 ==
[PASS] simple 族 = 3 / extended 族 = 1 / 无优先权记录单列并带警示 ...
== 7. scaffold 骨架 ==
[PASS] 骨架镜像 output_contract 全部字段 / 深合并填充生效 ...
== 8. CLI 冒烟测试 ==
[PASS] patent_numbers.py normalize CLI / 缺参数退出码 2
== 汇总 ==
SELF-CHECK PASSED: 全部断言通过   （exit 0）
```

逐步演示见 `examples/example_walkthrough.md`。

## 约束

- 仅 Python 3 标准库；退出码：0 正常 / 1 自查断言失败 / 2 用法或输入错误。
- PDF 依赖外部 `pdftotext -layout`（可选）；缺失时跳过 PDF 并标记
  unavailable，不中断。
- 全部文件为 UTF-8 文本，无符号链接，无二进制，总量 < 2MB。
- fixture 全部为虚构合成数据（合成测试国别码 XX），不对应任何真实专利。
