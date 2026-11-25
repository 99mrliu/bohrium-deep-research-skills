# patent-chronology-semantics-engine

专利与技术文献检索中的**日期口径与时间轴工程**技能。唯一焦点是时间：异构日期解析归一化、日期口径严格区分（优先权/申请/公开/授权）、带日期事件抽取、时间轴构建与顺序冲突检测、观测同族优先权一致性核查、带硬性护栏的法定参考日期估算（仅估算，永不输出法律状态结论）。

- 仅 Python 3 标准库，无第三方依赖；退出码约定：0 正常 / 1 检查未通过或护栏触发 / 2 用法错误。
- 详细契约与纪律见 [SKILL.md](SKILL.md)；格式与口径语义见 [references/](references/)。
- 仓库地址：<https://github.com/99mrliu/bohrium-deep-research-skills/tree/main/patent-litsearch-ad3e9357-v3/g-chronology-engine>

## 快速开始

```bash
cd skill/

# 1) 解析单个日期（含歧义与 OCR 情形）
python3 scripts/date_norm.py "Jun. 5, 2018"
python3 scripts/date_norm.py "03/04/2018"                                  # 两种解释 + 歧义警告
python3 scripts/date_norm.py "2O18-06-05" --ocr-policy fix-digit-confusion # 声明式 OCR 修复

# 2) 在合成 fixtures 上跑完整流水线
T=$(mktemp -d)
python3 scripts/event_extract.py examples/fixtures/rec_GX1001.txt -o $T/gx1001.json
python3 scripts/event_extract.py examples/fixtures/rec_GX1002.txt -o $T/gx1002.json
python3 scripts/event_extract.py examples/fixtures/rec_GX1003.txt -o $T/gx1003.json
python3 scripts/timeline_build.py --events $T/gx1001.json $T/gx1002.json -o $T/timelines.json
python3 scripts/timeline_build.py --events $T/gx1001.json $T/gx1003.json --family -o $T/family.json
python3 scripts/term_estimate.py --request examples/fixtures/estimate_request.json -o $T/estimate.json

# 3) 端到端自检（应输出 27/27 checks passed，退出码 0）
python3 scripts/selfcheck.py
```

完整带标注的演示（合成示例/示意输出）见 [examples/example_walkthrough.md](examples/example_walkthrough.md)。
所有 fixtures 均为合成数据，不对应任何真实专利。
