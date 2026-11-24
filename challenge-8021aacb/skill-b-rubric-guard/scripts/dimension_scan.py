#!/usr/bin/env python3
"""dimension_scan.py -- 六维线索扫描器。

按 references/cue_lexicon.json 的六维线索词扫描稿件文本, 产出「候选证据位点」:
每个命中给出维度、线索词、行号与上下文窗口。扫描结果只是候选, 是否构成缺陷
必须经 references/taxonomy_six.md 的纳入/排除判据裁定——本脚本不做裁定。

用法:
    python3 dimension_scan.py MANUSCRIPT_TEXT LEXICON_JSON OUT_JSON
"""
import json
import sys

CONTEXT = 80


def scan(text_path, lexicon_path, out_path):
    with open(text_path, encoding='utf-8') as f:
        text = f.read()
    with open(lexicon_path, encoding='utf-8') as f:
        lexicon = json.load(f)

    hits = []
    for dim, cues in lexicon['dimensions'].items():
        for cue in cues:
            start = 0
            while True:
                i = text.find(cue, start)
                if i < 0:
                    break
                line_no = text.count('\n', 0, i) + 1
                hits.append({
                    'dimension': dim,
                    'cue': cue,
                    'line': line_no,
                    'char': i,
                    'context': text[max(0, i - CONTEXT):i + len(cue) + CONTEXT].replace('\n', ' '),
                })
                start = i + len(cue)

    by_dim = {}
    for h in hits:
        by_dim.setdefault(h['dimension'], []).append(h)
    summary = {d: len(v) for d, v in sorted(by_dim.items())}
    report = {'manuscript': text_path, 'total_hits': len(hits),
              'hits_by_dimension': summary,
              'note': '候选位点非诊断结论; 须按 taxonomy_six.md 纳入/排除判据逐条裁定',
              'hits': hits}
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(json.dumps({'total_hits': len(hits), 'by_dimension': summary}, ensure_ascii=False))


if __name__ == '__main__':
    if len(sys.argv) != 4:
        sys.exit('usage: dimension_scan.py MANUSCRIPT_TEXT LEXICON_JSON OUT_JSON')
    scan(*sys.argv[1:4])
