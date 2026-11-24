#!/usr/bin/env python3
"""论断–证据对齐核验器：逐条核验"证据原文是否说了论断说的话"。

只依赖标准库。四层确定性检查（语义支持关系本身由模型判定，本脚本
负责拦截可机器判定的错位）：

1. 逐字锚定：quote 必须能在来源文本中命中（NFKC+空白折叠规范化），
   命中后回填真实页码（有 pages.json 时）；
2. 数字保真：论断中的每个数字必须在 quote 中逐字出现；
3. 方向一致：论断与 quote 的方向词不得互为反义（升高/降低等）；
4. 否定审视：论断与 quote 的否定词奇偶不一致时标出，交人工裁决。

用法：
    python3 align_check.py CLAIMS_JSON TEXT_DIR OUT_JSON [--report OUT_MD]

CLAIMS_JSON：
    {"claims": [{"id": "C1", "text": "论断",
                 "evidence": [{"source": "paper_a", "quote": "摘录",
                               "relation": "supports"}]}]}
TEXT_DIR    提取文本目录：<source>.txt（可选 <source>.pages.json）

退出码：0 = 全部论断 supported；1 = 存在 unsupported/冲突；
        2 = 用法/IO 错误。
"""
import argparse
import json
import os
import re
import sys
import unicodedata

NUMBER = re.compile(r'\d+(?:\.\d+)?')
NEG_WORDS = ('不', '无', '未', '没有', '并无', 'no ', 'not ', 'non-',
             'without', 'fail')
ANTONYMS = [('升高', '降低'), ('增加', '减少'), ('上升', '下降'),
            ('改善', '恶化'), ('提高', '减低'), ('increase', 'decrease'),
            ('improve', 'worsen'), ('higher', 'lower')]


def normalize(text):
    text = unicodedata.normalize('NFKC', text)
    return ' '.join(text.split())


def neg_parity(text):
    lowered = text.lower()
    return sum(lowered.count(w) for w in NEG_WORDS) % 2


def direction_of(text):
    lowered = text.lower()
    dirs = set()
    for up, down in ANTONYMS:
        if up in lowered:
            dirs.add('up')
        if down in lowered:
            dirs.add('down')
    return dirs


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('claims_json')
    ap.add_argument('text_dir')
    ap.add_argument('out_json')
    ap.add_argument('--report', default=None)
    args = ap.parse_args()

    with open(args.claims_json, encoding='utf-8') as fh:
        data = json.load(fh)

    cache = {}

    def load_source(stem):
        if stem in cache:
            return cache[stem]
        path = os.path.join(args.text_dir, stem + '.txt')
        if not os.path.exists(path):
            cache[stem] = (None, [])
            return cache[stem]
        with open(path, encoding='utf-8', errors='replace') as fh:
            raw = fh.read()
        pages = []
        ppath = os.path.join(args.text_dir, stem + '.pages.json')
        if os.path.exists(ppath):
            with open(ppath, encoding='utf-8') as fh:
                pages = json.load(fh)
        cache[stem] = (raw, pages)
        return cache[stem]

    claim_results = []
    any_bad = False
    for claim in data.get('claims', []):
        ev_results = []
        for idx, ev in enumerate(claim.get('evidence', []), 1):
            eid = ev.get('id', '%s-E%d' % (claim['id'], idx))
            source = ev.get('source', '')
            quote = ev.get('quote', '')
            raw, _pages = load_source(source)
            problems = []
            page = None
            if raw is None:
                problems.append('SOURCE-MISSING')
            else:
                needle = normalize(quote)
                if not needle:
                    problems.append('QUOTE-EMPTY')
                elif needle in normalize(raw.replace('\f', ' ')):
                    for i, chunk in enumerate(raw.split('\f'), 1):
                        if needle in normalize(chunk):
                            page = i
                            break
                else:
                    problems.append('QUOTE-NOT-ANCHORED')
            claim_nums = NUMBER.findall(claim.get('text', ''))
            missing_nums = [n for n in claim_nums
                            if n not in normalize(quote)]
            if missing_nums:
                problems.append('NUMERIC-MISMATCH:%s'
                                % ','.join(missing_nums))
            c_dirs = direction_of(claim.get('text', ''))
            q_dirs = direction_of(quote)
            if 'up' in c_dirs and 'down' in q_dirs and 'up' not in q_dirs:
                problems.append('DIRECTION-CONFLICT:claim=up,quote=down')
            if 'down' in c_dirs and 'up' in q_dirs and 'down' not in q_dirs:
                problems.append('DIRECTION-CONFLICT:claim=down,quote=up')
            if neg_parity(claim.get('text', '')) != neg_parity(quote):
                problems.append('NEGATION-REVIEW')
            hard = [p for p in problems
                    if not p.startswith('NEGATION-REVIEW')]
            verdict = ('anchored' if not problems else
                       'review' if not hard else 'failed')
            if hard:
                any_bad = True
            ev_results.append({'id': eid, 'source': source, 'page': page,
                               'verdict': verdict, 'problems': problems})
        ok = [e for e in ev_results if e['verdict'] == 'anchored']
        if not ev_results:
            c_verdict = 'unsupported'
            any_bad = True
        elif ok and len(ok) == len(ev_results):
            c_verdict = 'supported'
        elif ok:
            c_verdict = 'partial'
        else:
            c_verdict = 'unsupported'
            any_bad = True
        if c_verdict == 'partial':
            any_bad = True
        claim_results.append({'id': claim['id'], 'verdict': c_verdict,
                              'evidence': ev_results})

    out = {'claims': claim_results,
           'summary': {
               'total': len(claim_results),
               'supported': sum(1 for c in claim_results
                                if c['verdict'] == 'supported'),
               'partial': sum(1 for c in claim_results
                              if c['verdict'] == 'partial'),
               'unsupported': sum(1 for c in claim_results
                                  if c['verdict'] == 'unsupported')}}
    with open(args.out_json, 'w', encoding='utf-8') as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1)

    if args.report:
        lines = ['# 论断–证据对齐核验报告', '',
                 '| 论断 | 结论 | 证据 | 锚定 | 页 | 问题 |',
                 '|---|---|---|---|---|---|']
        for c in claim_results:
            for e in c['evidence']:
                lines.append('| %s | %s | %s | %s | %s | %s |' % (
                    c['id'], c['verdict'], e['id'], e['verdict'],
                    e['page'] or '-',
                    '; '.join(e['problems']).replace('|', '/') or '-'))
        with open(args.report, 'w', encoding='utf-8') as fh:
            fh.write('\n'.join(lines) + '\n')

    print(json.dumps(out['summary'], ensure_ascii=False))
    return 1 if any_bad else 0


if __name__ == '__main__':
    sys.exit(main())
