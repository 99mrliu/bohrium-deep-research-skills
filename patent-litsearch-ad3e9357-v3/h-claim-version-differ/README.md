# claim-version-structural-differ

权利要求文本的**版本结构化比对**技能包（skill bundle），面向"专利与技术文献检索"场景中来源可定位的权利要求版本（公开版 vs 授权版、不同观察到的同族成员、跨越 WO 合并 OCR 边界的文本）。

仓库地址：<https://github.com/99mrliu/bohrium-deep-research-skills/tree/main/patent-litsearch-ad3e9357-v3/h-claim-version-differ>

## 功能一览

| 脚本 | 功能 |
|---|---|
| `scripts/claim_segment.py` | 权利要求编号单元切分、独立/从属判定、前序/过渡语/要素切分；全部边界以字符 span + 逐字 quote 锚定原文；无法切分区域原样保留并降级标记；检测已声明的 OCR 合并边界 |
| `scripts/claim_align.py` | 两版本要素级对齐（difflib 贪婪最优相似度，阈值可声明）；分类 unchanged/modified/added/removed/reordered；低于阈值只列候选；统计由脚本重算；单侧版本产出 partial 清单 |
| `scripts/scope_note.py` | 由对应表渲染中文比对说明（含固定诚实性页脚）；`--gate` 模式拦截违禁结论性措辞（退出码 1 + 行号） |
| `scripts/selfcheck.py` | 合成夹具自查，7 项断言，退出码 0 表示通过 |

运行环境：Python 3（仅标准库）。退出码约定：`0` 正常（含 partial/degraded），`1` 违规（闸门检出），`2` 用法/输入错误。

## 快速开始

```bash
python3 scripts/selfcheck.py   # 先自查

# 对合成夹具跑完整流水线
python3 scripts/claim_segment.py --input examples/fixtures/claims_pub_HX1001.txt   --output /tmp/seg_pub.json
python3 scripts/claim_segment.py --input examples/fixtures/claims_grant_HX1001.txt --output /tmp/seg_grant.json
python3 scripts/claim_align.py  --a /tmp/seg_pub.json --b /tmp/seg_grant.json --output /tmp/corr.json
python3 scripts/scope_note.py  --table /tmp/corr.json --case-id HX-SYNTH-0001 --output /tmp/note.md
python3 scripts/scope_note.py  --gate /tmp/note.md                       # 应通过
python3 scripts/scope_note.py  --gate examples/fixtures/note_bad.md      # 应退出 1
```

完整演示（含单侧清单与 OCR 边界情形）见 `examples/example_walkthrough.md`。

## 目录结构

```
skill/
├── SKILL.md                  # 技能说明（用途/运行时契约/调用方式/异常处理/限制/自查）
├── README.md
├── GITHUB_URL.txt
├── scripts/                  # 仅 Python 标准库
│   ├── claim_segment.py
│   ├── claim_align.py
│   ├── scope_note.py
│   └── selfcheck.py
├── references/
│   ├── claim_grammar.md      # 切分语法、边界情形、OCR 边界处理
│   ├── wording_gate.md       # 违禁/允许措辞及理由
│   └── alignment_method.md   # 相似度度量、阈值与候选策略
└── examples/
    ├── example_walkthrough.md
    └── fixtures/             # 全部为合成数据，内容虚构
        ├── case_fixture.json
        ├── claims_pub_HX1001.txt
        ├── claims_grant_HX1001.txt
        ├── claims_wo_boundary_HX1002.txt
        └── note_bad.md
```

## 诚实性立场

本技能只报告**文本层面**的差异：不假定两版本权利要求保护范围是否一致，不做任何法律等价性（doctrine of equivalents 等）判断，不做侵权/FTO 结论。缺失版本、切分降级、OCR 边界交叉均以 `partial` 状态与 `limits` 明确定位。详见 `SKILL.md` 与 `references/wording_gate.md`。
