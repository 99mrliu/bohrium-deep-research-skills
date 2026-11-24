#!/usr/bin/env python3
"""证据强度标定与措辞校准器：证据等级决定允许使用的措辞强度。

只依赖标准库。两步：
1. 定级：按研究设计、样本量、一致性把每条论断的证据定为 A–D 级
   （口径见 references/strength_rubric.md，规则集中在 LEVEL_RULES）；
2. 校准：扫描成稿中带〔C#〕标记的句子，其措辞强度不得超过该论断
   的等级上限（等级-措辞映射见 ALLOWED / FORBIDDEN 常量）。

用法：
    python3 strength_map.py --meta CLAIMS_META_JSON \
        --draft DRAFT_MD --out VERDICTS_JSON [--report OUT_MD]

CLAIMS_META_JSON：
    {"claims": [{"id": "C1",
                 "studies": [{"design": "rct", "n": 120,
                              "consistent": true}]}]}
design 枚举：meta / guideline / rct / cohort / case-control /
cross-sectional / case-series / preprint / in-vitro / animal / expert

退出码：0 = 无越级措辞；1 = 存在 OVERSTATED；2 = 用法/IO 错误。
"""
import argparse
import json
import re
import sys

BASE_LEVEL = {'meta': 'A', 'guideline': 'A', 'rct': 'B', 'cohort': 'C',
              'case-control': 'C', 'cross-sectional': 'C',
              'case-series': 'D', 'preprint': 'D', 'in-vitro': 'D',
              'animal': 'D', 'expert': 'D'}
LEVEL_ORDER = ['A', 'B', 'C', 'D']

# 各等级禁止使用的措辞（即更高等级才允许的表述）
FORBIDDEN = {
    'A': [],
    'B': ['证据一致表明', '已获证实', '指南推荐'],
    'C': ['证据表明', '研究表明', '已证实', '证明了', '指南推荐',
          '证据一致表明'],
    'D': ['证据表明', '研究表明', '研究显示', '已证实', '证明了',
          '指南推荐', '证据一致表明', '临床有效'],
}
# 各等级建议措辞（写入报告供写作参考）
ALLOWED = {
    'A': ['证据一致表明', '指南推荐'],
    'B': ['研究显示', '随机对照试验提示'],
    'C': ['一项观察性研究提示', '初步显示'],
    'D': ['临床前证据提示', '尚待研究验证', '个案报告提示'],
}

SENT_SPLIT = re.compile(r'(?<=[。！？；!?;])\s*|(?<=\.)\s+')
CLAIM_MARK = re.compile(r'〔(C\d+)〕')


def level_of(studies):
    if not studies:
        return 'D', '无登记研究，按最低等级处理'
    levels = [BASE_LEVEL.get(s.get('design', ''), 'D') for s in studies]
    best = min(levels, key=LEVEL_ORDER.index)
    rank = LEVEL_ORDER.index(best)
    reasons = ['基础等级 %s（%s）' % (best, studies[0].get('design'))]
    if len(studies) >= 2 and all(s.get('consistent') for s in studies):
        if rank > 0:
            rank -= 1
            reasons.append('≥2 项一致证据，上调一级')
    for s in studies:
        n = s.get('n')
        if isinstance(n, int) and 0 < n < 30:
            rank = min(rank + 1, 3)
            reasons.append('存在 n<30 的研究，下调一级')
            break
    return LEVEL_ORDER[rank], '；'.join(reasons)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--meta', required=True)
    ap.add_argument('--draft', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--report', default=None)
    args = ap.parse_args()

    with open(args.meta, encoding='utf-8') as fh:
        meta = json.load(fh)
    with open(args.draft, encoding='utf-8') as fh:
        draft = fh.read()

    verdicts = {}
    for claim in meta.get('claims', []):
        level, reason = level_of(claim.get('studies', []))
        verdicts[claim['id']] = {'level': level, 'reason': reason,
                                 'allowed': ALLOWED[level],
                                 'violations': []}

    for line in draft.splitlines():
        for sent in SENT_SPLIT.split(line):
            marks = CLAIM_MARK.findall(sent)
            for cid in marks:
                if cid not in verdicts:
                    continue
                level = verdicts[cid]['level']
                for phrase in FORBIDDEN[level]:
                    if phrase in sent:
                        verdicts[cid]['violations'].append({
                            'phrase': phrase,
                            'sentence': sent.strip()[:160]})
    overstated = {cid: v for cid, v in verdicts.items() if v['violations']}

    with open(args.out, 'w', encoding='utf-8') as fh:
        json.dump({'verdicts': verdicts,
                   'overstated_claims': sorted(overstated)},
                  fh, ensure_ascii=False, indent=1)

    if args.report:
        lines = ['# 证据强度标定与措辞校准报告', '',
                 '| 论断 | 等级 | 定级理由 | 允许措辞 | 越级命中 |',
                 '|---|---|---|---|---|']
        for cid, v in verdicts.items():
            hits = '; '.join(x['phrase'] for x in v['violations']) or '-'
            lines.append('| %s | %s | %s | %s | %s |' % (
                cid, v['level'], v['reason'],
                '、'.join(v['allowed']), hits))
        lines += ['', '结论：%s。' % (
            '存在越级措辞：' + '、'.join(sorted(overstated))
            if overstated else '全部论断措辞与证据等级相称')]
        with open(args.report, 'w', encoding='utf-8') as fh:
            fh.write('\n'.join(lines) + '\n')

    print(json.dumps({'levels': {c: v['level']
                                 for c, v in verdicts.items()},
                      'overstated': sorted(overstated)},
                     ensure_ascii=False))
    return 1 if overstated else 0


if __name__ == '__main__':
    sys.exit(main())
