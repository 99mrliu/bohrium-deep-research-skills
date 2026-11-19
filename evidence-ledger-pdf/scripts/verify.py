#!/usr/bin/env python3
"""Quote verification gate: re-locate every evidence quote in the corpus,
recompute each claim's quote_check, and emit a backlink report.

Gate semantics:
- evidence quote no longer locatable  -> quote_check=quote_not_found
- all evidence located                -> verified
- some located (incl. partial)        -> partial
- claim references missing evidence   -> error (finalize refuses success)
Claims with quote_not_found are demoted: the gate rewrites their strength
to 'unknown' and section to '无法确定' unless --no-demote is given.
Stdlib only.
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pdfindex


def load(path):
    with open(path, encoding='utf-8') as f:
        return json.load(f)


def save(path, obj):
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', required=True)
    ap.add_argument('--no-demote', action='store_true',
                    help='只报告不降级（默认降级 quote_not_found 结论）')
    args = ap.parse_args()

    corpus = load(os.path.join(args.out, 'corpus_index.json'))
    ledger = load(os.path.join(args.out, 'evidence_ledger.json'))
    claims = load(os.path.join(args.out, 'claim_register.json'))
    pages_cache = {}
    ev_status = {}
    ev_detail = []

    for e in ledger['evidence']:
        doc = next((d for d in corpus['documents']
                    if d['doc_id'] == e['doc_id']), None)
        if doc is None:
            ev_status[e['evidence_id']] = 'doc_missing'
            ev_detail.append({'evidence_id': e['evidence_id'],
                              'status': 'doc_missing'})
            continue
        if doc['doc_id'] not in pages_cache:
            pages_cache[doc['doc_id']] = pdfindex.load_pages(doc)
        pages = pages_cache[doc['doc_id']]
        hit = pdfindex.find_quote(
            [pages[e['page'] - 1]] if 0 < e['page'] <= len(pages) else pages,
            e['quote'])
        if hit is None:
            status = 'quote_not_found'
        elif hit[0] != e['page']:
            status = 'moved_to_page_%d' % hit[0]
        else:
            status = 'verified'
        ev_status[e['evidence_id']] = status
        ev_detail.append({'evidence_id': e['evidence_id'], 'status': status,
                          'doc_id': e['doc_id'], 'page': e['page'],
                          'sq': e.get('sq')})

    errors, demoted = [], []
    for c in claims['claims']:
        missing = [i for i in c['evidence_ids'] if i not in ev_status]
        if missing:
            c['quote_check'] = 'error_missing_evidence'
            errors.append({'claim_id': c['claim_id'], 'missing': missing})
            continue
        sts = [ev_status[i] for i in c['evidence_ids']]
        if all(s == 'verified' for s in sts):
            c['quote_check'] = 'verified'
        elif any(s == 'quote_not_found' or s == 'doc_missing' for s in sts):
            c['quote_check'] = 'quote_not_found'
        else:
            c['quote_check'] = 'partial'
        if c['quote_check'] == 'quote_not_found' and not args.no_demote:
            c['strength'], c['section'] = 'unknown', '无法确定'
            demoted.append(c['claim_id'])

    total = len(claims['claims'])
    verified = sum(1 for c in claims['claims']
                   if c['quote_check'] == 'verified')
    partial = sum(1 for c in claims['claims']
                  if c['quote_check'] == 'partial')
    rate = round(verified / total, 4) if total else 0.0
    save(os.path.join(args.out, 'claim_register.json'), claims)

    report = {'case_id': claims['case_id'],
              'backlink_rate': rate,
              'counts': {'claims': total, 'verified': verified,
                         'partial': partial,
                         'quote_not_found': sum(
                             1 for c in claims['claims']
                             if c['quote_check'] == 'quote_not_found'),
                         'errors': len(errors)},
              'demoted_claims': demoted,
              'evidence_detail': ev_detail,
              'errors': errors,
              'rule': '回链率=verified/结论总数；quote_not_found 的结论'
                      '强制降级为无法确定，不得留在结论区'}
    save(os.path.join(args.out, 'backlink_report.json'), report)
    print(json.dumps({'ok': not errors, 'backlink_rate': rate,
                      **report['counts']}, ensure_ascii=False))
    return 0 if not errors else 1


if __name__ == '__main__':
    raise SystemExit(main())
