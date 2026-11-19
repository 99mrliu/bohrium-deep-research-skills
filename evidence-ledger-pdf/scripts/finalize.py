#!/usr/bin/env python3
"""evidence-ledger-pdf: finalization.

Runs the verification gate, requires a clean gate for status=success,
assembles the six-aspect summary and the final result.json. Stdlib only.
"""
import argparse
import io
import contextlib
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import verify as verify_mod


def load(path, default=None):
    if os.path.exists(path):
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    return default


def write_json(path, obj):
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--case', required=True)
    ap.add_argument('--work', required=True)
    ap.add_argument('--out', required=True)
    args = ap.parse_args()

    case = load(args.case, {})
    case_id = case.get('case_id') or case.get('id') or 'unknown-case'
    parse_report = load(os.path.join(args.out, 'parse_report.json'), {})
    ledger = load(os.path.join(args.out, 'evidence_ledger.json'),
                  {'evidence': []})
    claims = load(os.path.join(args.out, 'claim_register.json'),
                  {'claims': []})

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = _run_verify(args.out)
    report = load(os.path.join(args.out, 'backlink_report.json'), {})

    n_ev = len(ledger['evidence'])
    n_cl = len(claims['claims'])
    parse_errors = parse_report.get('parse_errors', [])
    conflict_claims = [c for c in claims['claims']
                       if c.get('section') == '冲突证据']
    gap_claims = [c for c in claims['claims']
                  if c.get('section') == '研究空白']

    ok = (rc == 0 and n_cl > 0 and report.get('counts', {}).get(
        'quote_not_found', 0) == 0 and not parse_errors)
    status = 'success' if ok else (
        'blocked' if not parse_report.get('pages') else 'partial')

    result_path = os.path.join(args.out, 'result.json')
    result = load(result_path, {})
    result.update({
        'case_id': case_id,
        'status': status,
        'research_output': 'synthesis.md',
        'sources': [{'doc_id': d['doc_id'], 'path': d['path'],
                     'pages': len(d.get('pages', [])),
                     'sha256': d.get('sha256')}
                    for d in load(os.path.join(
                        args.out, 'corpus_index.json'), {}).get(
                        'documents', [])],
        'uncertainty': ([e.get('error', 'parse error') + ' @' + e.get(
            'path', '?') for e in parse_errors] +
            ['quote_not_found 结论已强制降级，见 backlink_report.json'] *
            (1 if report.get('counts', {}).get('quote_not_found') else 0) +
            ['超出输入材料范围的判断一律标 unknown（未检索/未提供）']),
        'six_aspects': {
            '问题拆解': 'claim_register.json 中每条结论的 sq/section 绑定；'
                        '证据按 --sq 与子问题对应',
            '检索覆盖': '材料边界=corpus_index.json %d 篇文档 %d 页' % (
                len(result.get('sources', [])), parse_report.get('pages', 0)),
            '证据回链': '回链率 %.2f（%d/%d 条结论 verified，见 '
                        'backlink_report.json）' % (
                report.get('backlink_rate', 0.0),
                report.get('counts', {}).get('verified', 0), n_cl),
            '冲突证据': '%d 条冲突结论（冲突段仅收录引用已核验者）' % len(
                conflict_claims),
            '综合结论': '%d 条结论；synthesis.md 内联 ⟦EV-xxxx⟧ 锚点' % n_cl,
            '研究空白': '%d 条空白判断（每句须附阅读范围依据）' % len(
                gap_claims)},
        'evidence_ledger_summary': {'evidence': n_ev,
                                    'claims': n_cl},
        'finalized_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        'schema_version': 'evledger-b/1.0'})
    oc = case.get('output_contract') or case.get('outputContract') or {}
    keys = oc if isinstance(oc, list) else (
        list(oc.keys()) if isinstance(oc, dict) else [])
    for k in keys:
        result.setdefault(k, result.get(k))
    write_json(result_path, result)
    print(json.dumps({'ok': True, 'status': status,
                      'backlink_rate': report.get('backlink_rate', 0.0),
                      'claims': n_cl}, ensure_ascii=False))


def _run_verify(out):
    """Invoke verify gate programmatically."""
    sys.argv = ['verify.py', '--out', out]
    try:
        return verify_mod.main() or 0
    except SystemExit as e:
        return e.code or 0


if __name__ == '__main__':
    main()
