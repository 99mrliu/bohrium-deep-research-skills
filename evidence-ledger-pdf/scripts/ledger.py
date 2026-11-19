#!/usr/bin/env python3
"""Evidence ledger: every evidence item carries a verbatim quote that is
located in the parsed corpus before the item is accepted. Stdlib only."""
import argparse
import json
import os
import sys
import time

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
    sub = ap.add_subparsers(dest='cmd', required=True)
    a = sub.add_parser('add')
    a.add_argument('--ledger', required=True)
    a.add_argument('--corpus', default=None,
                   help='corpus_index.json（默认取 ledger 同目录）')
    a.add_argument('--doc', required=True, help='PDF 相对路径或 doc_id')
    a.add_argument('--page', type=int, default=None, help='期望页码（可选，用于校验）')
    a.add_argument('--quote', required=True, help='逐字引用块')
    a.add_argument('--sq', default=None, help='绑定的子问题编号')
    a.add_argument('--field', default=None, help='提取的可比较字段名')
    a.add_argument('--note', default='')
    l = sub.add_parser('list')
    l.add_argument('--ledger', required=True)
    d = sub.add_parser('get')
    d.add_argument('--ledger', required=True)
    d.add_argument('--id', required=True)
    args = ap.parse_args()

    if args.cmd == 'list':
        led = load(args.ledger)
        for e in led['evidence']:
            print(json.dumps(e, ensure_ascii=False))
        return
    if args.cmd == 'get':
        led = load(args.ledger)
        for e in led['evidence']:
            if e['evidence_id'] == args.id:
                print(json.dumps(e, ensure_ascii=False, indent=2))
                return
        raise SystemExit('evidence not found: ' + args.id)

    ledger_path = args.ledger
    ledger = load(ledger_path)
    corpus_path = args.corpus or os.path.join(os.path.dirname(ledger_path),
                                              'corpus_index.json')
    corpus = load(corpus_path)

    doc = None
    for d_ in corpus['documents']:
        if d_['doc_id'] == args.doc or d_['path'] == args.doc:
            doc = d_
            break
    if doc is None:
        print(json.dumps({'ok': False, 'error': 'document not in corpus',
                          'doc': args.doc}, ensure_ascii=False))
        raise SystemExit(1)

    pages_text = pdfindex.load_pages(doc)
    hit = pdfindex.find_quote(pages_text, args.quote)
    if hit is None:
        # report nearest fragment to help the agent fix the quote
        frag = args.quote[:40]
        near = pdfindex.find_quote(pages_text, frag)
        print(json.dumps({'ok': False, 'error': 'quote_not_located',
                          'hint': '引用块经归一化后未在文档中找到；'
                                  '请复制原文逐字片段',
                          'first40_match': bool(near)}, ensure_ascii=False))
        raise SystemExit(2)
    pno, start, end, snippet = hit
    partial = snippet.startswith('[partial]')
    if args.page is not None and args.page != pno:
        print(json.dumps({'ok': False, 'error': 'page_mismatch',
                          'expected': args.page, 'located': pno},
                         ensure_ascii=False))
        raise SystemExit(3)

    eid = 'EV-%04d' % ledger['next_id']
    ledger['next_id'] += 1
    ledger['evidence'].append({
        'evidence_id': eid, 'doc_id': doc['doc_id'], 'path': doc['path'],
        'page': pno, 'char_start': start, 'char_end': end,
        'quote': args.quote, 'quote_norm_sha16': pdfindex.sha16(
            pdfindex.norm(args.quote).encode()),
        'locate_status': 'partial' if partial else 'hit',
        'sq': args.sq, 'field': args.field, 'note': args.note,
        'entered_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        'method': 'verbatim_quote_located_in_corpus'})
    save(ledger_path, ledger)
    print(json.dumps({'ok': True, 'evidence_id': eid,
                      'locate': '%s@%s:p%d+%d' % (
                          'partial' if partial else 'hit', doc['doc_id'],
                          pno, start)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
