#!/usr/bin/env python3
"""草稿静态检查器（draft lint）：对成稿做 CI 式逐句检查。

只依赖标准库。不调用模型，全部检查确定性可复跑。检查规则见
references/lint_rules.md；每条命中给出规则编号、严重度、行号、
上下文与修复建议。

用法：
    python3 draft_lint.py --draft DRAFT_MD --registry EVIDENCE_JSON \
        --out LINT_JSON [--report LINT_MD]

DRAFT_MD       成稿（论断标注约定：句内用 〔C编号〕 标记论断，
               引文用 [n] 标记参考文献）
EVIDENCE_JSON  证据登记，结构：
               {"claims":[{"id","text","evidence_ids"[]}],
                "evidence":[{"id","source","quote","strength"}],
                "refs":[{"n","title","authors","year"}],
                "number_allowlist":[{"value","reason"}]}

退出码：0 = 无 error 级命中；1 = 存在 error 级命中；2 = 用法/IO 错误。
"""
import argparse
import json
import re
import sys

NUMBER = re.compile(r'(?<![\w.])\d+(?:\.\d+)?(?![\w.])')
CITATION = re.compile(r'\[(\d{1,3})\]')
CLAIM_MARK = re.compile(r'〔(C\d+)〕')
PLACEHOLDER = re.compile(
    r'TODO|TBD|XXX|FIXME|待补充|待补全|待填写|【待|此处省略|（略）',
    re.IGNORECASE)
OVERCLAIM = re.compile(r'已证实|证明了|确凿|结论性证据|彻底|根治')
CAUSAL = re.compile(r'导致|引起|治愈|消除病因|可以预防')
CORRELATIONAL = re.compile(r'相关|关联|associated|correlat', re.IGNORECASE)
SENT_SPLIT = re.compile(r'(?<=[。！？；!?;])\s*|(?<=\.)\s+')

STRENGTH_RANK = {'high': 3, 'moderate': 2, 'low': 1}


def sentences_with_line(text):
    """按行切句并保留行号（markdown 行内多句也拆开）。"""
    for lineno, line in enumerate(text.splitlines(), 1):
        for sent in SENT_SPLIT.split(line):
            sent = sent.strip()
            if sent:
                yield lineno, sent


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--draft', required=True)
    ap.add_argument('--registry', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--report', default=None)
    args = ap.parse_args()

    with open(args.draft, encoding='utf-8') as fh:
        draft = fh.read()
    with open(args.registry, encoding='utf-8') as fh:
        reg = json.load(fh)

    claims = {c['id']: c for c in reg.get('claims', [])}
    evidence = {e['id']: e for e in reg.get('evidence', [])}
    refs = {int(r['n']): r for r in reg.get('refs', [])}
    allowlist = {str(a['value']) for a in reg.get('number_allowlist', [])}
    quote_blob = ' '.join(e.get('quote', '') for e in evidence.values())

    findings = []

    def add(rule, severity, lineno, context, advice):
        findings.append({'rule': rule, 'severity': severity,
                         'line': lineno,
                         'context': context[:160], 'advice': advice})

    # --- 全文级检查 ---
    for lineno, line in enumerate(draft.splitlines(), 1):
        m = PLACEHOLDER.search(line)
        if m:
            add('PLACEHOLDER', 'error', lineno, line,
                '删除占位符或补入真实内容；无法补入时在 limits 说明。')

    cited = set()
    for lineno, sent in sentences_with_line(draft):
        for m in CITATION.finditer(sent):
            n = int(m.group(1))
            cited.add(n)
            if n not in refs:
                add('CITE-ORPHAN', 'error', lineno, sent,
                    '引文 [%d] 在参考文献登记表中不存在；补登或删除。' % n)

        # 数字溯源：跳过引文标记与四位年份
        scrubbed = CITATION.sub('', sent)
        for m in NUMBER.finditer(scrubbed):
            token = m.group(0)
            if re.fullmatch(r'(19|20)\d{2}', token) or token in allowlist:
                continue
            if token not in quote_blob:
                add('NUM-UNTRACE', 'error', lineno, sent,
                    '数字 %s 未在任何已登记证据的原文摘录中出现；'
                    '回到原文核对，或修正数字，或删除。' % token)

        marks = CLAIM_MARK.findall(sent)
        claim_strengths = []
        claim_quotes = []
        for cid in marks:
            claim = claims.get(cid)
            if not claim:
                add('CLAIM-UNKNOWN', 'error', lineno, sent,
                    '论断标记〔%s〕未在登记表中定义。' % cid)
                continue
            for eid in claim.get('evidence_ids', []):
                ev = evidence.get(eid)
                if ev:
                    claim_strengths.append(
                        STRENGTH_RANK.get(ev.get('strength', 'low'), 1))
                    claim_quotes.append(ev.get('quote', ''))
        if OVERCLAIM.search(sent):
            if not marks:
                add('OVERCLAIM-NOMARK', 'warning', lineno, sent,
                    '强结论措辞但无论断标记，无法核验证据强度；'
                    '补〔C#〕或改弱措辞。')
            elif claim_strengths and max(claim_strengths) < 3:
                add('OVERCLAIM', 'error', lineno, sent,
                    '措辞强度超过证据等级（最高 non-high）；'
                    '改用与证据相称的表述。')
        if CAUSAL.search(sent) and claim_quotes and any(
                CORRELATIONAL.search(q) for q in claim_quotes):
            add('CAUSAL-SLIP', 'error', lineno, sent,
                '证据原文为相关性表述，成稿写成了因果；改回相关性措辞。')
        if NUMBER.search(scrubbed) and not marks:
            add('UNMARKED-FACT', 'warning', lineno, sent,
                '含数字的事实句无论断标记；补〔C#〕以便回溯。')

    for n in sorted(refs):
        if n not in cited:
            add('REF-UNUSED', 'warning', 0,
                '参考文献 [%d] %s' % (n, refs[n].get('title', '')[:60]),
                '成稿中从未引用；删除或在正文引用。')

    errors = sum(1 for f in findings if f['severity'] == 'error')
    warnings = sum(1 for f in findings if f['severity'] == 'warning')
    out = {'draft': args.draft, 'errors': errors, 'warnings': warnings,
           'findings': findings}
    with open(args.out, 'w', encoding='utf-8') as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1)

    if args.report:
        lines = ['# 草稿静态检查报告', '',
                 'error：%d；warning：%d。' % (errors, warnings), '',
                 '| 规则 | 严重度 | 行 | 上下文 | 建议 |',
                 '|---|---|---|---|---|']
        for f in findings:
            lines.append('| %s | %s | %s | %s | %s |' % (
                f['rule'], f['severity'], f['line'] or '-',
                f['context'].replace('|', '/'),
                f['advice'].replace('|', '/')))
        with open(args.report, 'w', encoding='utf-8') as fh:
            fh.write('\n'.join(lines) + '\n')

    print(json.dumps({'errors': errors, 'warnings': warnings,
                      'rules_hit': sorted({f['rule']
                                           for f in findings})},
                     ensure_ascii=False))
    return 1 if errors else 0


if __name__ == '__main__':
    sys.exit(main())
