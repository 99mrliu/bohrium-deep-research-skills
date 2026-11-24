#!/usr/bin/env python3
"""verify_quotes.py -- 逐字引文核验器。

诊断 JSON 中的每条 quote 必须逐字命中锚点库中对应 anchor 的段落文本;
这是「说得清」的机器保证: 评审可独立重跑本脚本复核每一条来源定位。

用法:
    python3 verify_quotes.py ANCHOR_MAP_JSONL DIAGNOSIS_JSON OUT_JSON

DIAGNOSIS_JSON 两种形态均可:
  1) {"findings": [{"id","anchor","quote", ...}, ...]}
  2) 直接是 finding 列表
finding 缺 anchor 或 quote 字段记为 unverifiable (不静默放过)。
"""
import json
import sys


def load_anchors(path):
    anchors = {}
    with open(path, encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line:
                r = json.loads(line)
                anchors[r['anchor']] = r['text']
    return anchors


def normalize(s):
    """比对前只做空白归一, 不改字: 换行/多空格视为同一文本。"""
    return ' '.join(s.split())


def verify(anchor_path, diag_path, out_path):
    anchors = load_anchors(anchor_path)
    with open(diag_path, encoding='utf-8') as f:
        diag = json.load(f)
    findings = diag.get('findings', diag) if isinstance(diag, dict) else diag

    results = []
    n_ok = n_fail = n_unver = 0
    for i, fnd in enumerate(findings):
        fid = fnd.get('id', 'F%03d' % (i + 1))
        anchor = fnd.get('anchor')
        quote = fnd.get('quote')
        if not anchor or not quote:
            results.append({'id': fid, 'status': 'unverifiable',
                            'reason': 'missing anchor or quote field'})
            n_unver += 1
            continue
        text = anchors.get(anchor)
        if text is None:
            results.append({'id': fid, 'anchor': anchor, 'status': 'fail',
                            'reason': 'anchor not in anchor_map'})
            n_fail += 1
        elif normalize(quote) in normalize(text):
            results.append({'id': fid, 'anchor': anchor, 'status': 'ok'})
            n_ok += 1
        else:
            results.append({'id': fid, 'anchor': anchor, 'status': 'fail',
                            'reason': 'quote not verbatim in anchor text',
                            'quote_head': quote[:80]})
            n_fail += 1

    report = {'diagnosis': diag_path, 'anchor_map': anchor_path,
              'total': len(findings), 'ok': n_ok, 'fail': n_fail,
              'unverifiable': n_unver,
              'all_verified': n_fail == 0 and n_unver == 0 and n_ok > 0,
              'results': results}
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(json.dumps({k: report[k] for k in
                      ('total', 'ok', 'fail', 'unverifiable', 'all_verified')},
                     ensure_ascii=False))
    return report


if __name__ == '__main__':
    if len(sys.argv) != 4:
        sys.exit('usage: verify_quotes.py ANCHOR_MAP_JSONL DIAGNOSIS_JSON OUT_JSON')
    verify(*sys.argv[1:4])
