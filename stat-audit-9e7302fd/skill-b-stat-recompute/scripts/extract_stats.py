#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""extract_stats.py — 从论文纯文本中抽取所有可核对的统计量（纯标准库）。

输入: 由 pdftotext -layout 或 pdf-text-tool 得到的 .txt 纯文本。
输出: stats.jsonl，每条记录一个统计量:
  {kind, line, raw, <fields...>, context}
  kind ∈ {t, F, chi2, z, r, p_only, ratio, mean_sd, percent, ci_mean, power}
  context 为命中位置前后各 120 字符。

设计原则:
  - 先做全角数字/标点归一化，再匹配；
  - 任何正则异常、字段缺失都不导致崩溃，最差结果是少抽（WARNING），
    绝不多造；抽取为空只输出 WARNING，退出码仍为 0；
  - 硬失败（输入文件不存在/不可读/非 UTF-8）退出码非零。

用法: python3 extract_stats.py INPUT.txt [-o stats.jsonl]
"""

import argparse
import json
import re
import sys

CONTEXT = 120          # context 前后字符数
P_WINDOW_AFTER = 120   # 统计量之后寻找 p 值的窗口
P_WINDOW_BEFORE = 40   # 统计量之前寻找 p 值的窗口

# ------------------------------------------------------------ 全角归一化 ---
_NORM_TABLE = {}
for _c in range(0xFF01, 0xFF5F):   # 全角 ASCII（含 ０-９ Ａ-Ｚ ａ-ｚ 与标点）
    _NORM_TABLE[_c] = chr(_c - 0xFEE0)
for _c, _r in {
    '．': '.', '，': ',', '：': ':', '；': ';', '（': '(', '）': ')',
    '［': '[', '］': ']', '％': '%', '＝': '=', '﹤': '<', '﹥': '>',
    '＜': '<', '＞': '>', '－': '-', '﹣': '-', '−': '-', '±': '±',
    '＋': '+', '～': '~', '﹪': '%', '﹑': ',', '≈': '=', '≒': '=',
    '≤': '≤', '≥': '≥', 'Χ': 'χ', 'ⅹ': 'x', '²': '²',
}.items():
    _NORM_TABLE[ord(_c)] = _r


def normalize(text):
    return text.translate(_NORM_TABLE)


# ---------------------------------------------------------------- 模式 -----
NUM = r'(-?\d+(?:\.\d+)?|\.\d+)'
P_RE = re.compile(
    r'(?<![A-Za-z])[pP]\s*(≤|>=?|<|>|=|≦|≧|\bNS\b)?\s*'
    r'(0?\.\d+|1\.0+|\d+\.\d+|\.\d+)')
# 上式中 \bNS\b 捕获不到时忽略；单独处理 p = NS
P_NS_RE = re.compile(r'(?<![A-Za-z])[pP]\s*(?:=|>|≥)\s*(?:NS|ns|不显著)')

STAT_PATTERNS = [
    # (kind, regex, 优先级(同起点时小者先))
    ('ratio', re.compile(
        r'(?<![A-Za-z])(OR|HR|RR|odds ratio|hazard ratio|risk ratio|relative risk)'
        r'\s*[=为]?\s*' + NUM +
        r'\s*[,，]?\s*(?:95\s*%\s*)?CI\s*[\[(:：]?\s*' + NUM +
        r'\s*[-–—~,，]\s*' + NUM + r'\s*[\])]?', re.I), 0),
    ('F', re.compile(
        r'(?<![A-Za-z])F\s*\(\s*(\d+)\s*[,，]\s*(\d+)\s*\)\s*=\s*' + NUM), 1),
    ('t', re.compile(
        r'(?<![A-Za-z])t\s*\(\s*(\d+)\s*\)\s*=\s*' + NUM), 1),
    ('chi2', re.compile(
        r'χ[²2]?\s*(?:\(\s*(\d+)\s*\))?\s*=\s*' + NUM), 1),
    ('z', re.compile(
        r'(?<![A-Za-z])[zZ]\s*=\s*' + NUM), 2),
    ('r', re.compile(
        r'(?<![A-Za-z])r\s*(?:\(\s*(\d+)\s*\))?\s*=\s*' + NUM), 2),
    ('mean_sd', re.compile(
        r'(?<![\d.])' + NUM + r'\s*±\s*' + NUM), 3),
    ('mean_sd', re.compile(
        r'(?<![A-Za-z])M\s*=\s*' + NUM + r'\s*[,，]\s*(?:SD|SEM|SE)\s*=\s*' + NUM), 3),
    ('percent', re.compile(
        r'(\d+)\s*/\s*(\d+)\s*\(\s*' + NUM + r'\s*%\s*\)'), 3),
    ('percent', re.compile(
        NUM + r'\s*%\s*\(\s*(\d+)\s*/\s*(\d+)\s*\)'), 3),
    ('ci_mean', re.compile(
        r'(?<![\d.])' + NUM + r'\s*[,，]?\s*\(?\s*95\s*%\s*CI'
        r'\s*[\[(:：]?\s*' + NUM + r'\s*[-–—~,，]\s*' + NUM + r'\s*[\])]?', re.I), 4),
]

POWER_KEY_RE = re.compile(
    r'(?i)(statistical power|检验效能|把握度|power\s*[=为]|样本量估计|'
    r'sample size (?:calculation|estimation))')
POWER_WIN = 180


def _f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _line_of(line_starts, pos):
    import bisect
    return bisect.bisect_right(line_starts, pos)


def _context(text, start, end):
    lo = max(0, start - CONTEXT)
    hi = min(len(text), end + CONTEXT)
    return text[lo:hi].replace('\n', ' ').strip()


def _sentence_bounds(text, start, end):
    """p 值搜索窗口：统计量前后 P_WINDOW_BEFORE/AFTER 字符，
    但不跨越句号或换行（防止把下一句的 p 错挂到本统计量上）。"""
    lo = max(0, start - P_WINDOW_BEFORE)
    hi = min(len(text), end + P_WINDOW_AFTER)
    for i in range(start - 1, lo - 1, -1):
        if text[i] in '。\n':
            lo = i + 1
            break
    for i in range(end, hi):
        if text[i] in '。\n':
            hi = i
            break
    return lo, hi


def _attach_p(text, start, end, used_p):
    """在统计量同一句内寻找 p 值，返回 (p_rec, span) 或 (None, None)。"""
    lo, hi = _sentence_bounds(text, start, end)
    best = None
    for m in P_RE.finditer(text, lo, hi):
        if m.span() in used_p:
            continue
        # 距离 = p 与统计量的间隔
        dist = min(abs(m.start() - end), abs(start - m.end()))
        if m.start() >= end:
            dist = m.start() - end
        elif m.end() <= start:
            dist = start - m.end() + 1000  # 前置 p 降权
        if best is None or dist < best[0]:
            best = (dist, m)
    if best is None:
        if P_NS_RE.search(text, lo, hi):
            return ({'p_op': '>', 'p': 0.05, 'p_raw': 'NS'}, None)
        return None, None
    m = best[1]
    op = m.group(1) or '='
    op = {'=<': '≤', '=<': '≤', '≦': '≤', '≧': '≥', 'NS': '>'}.get(op, op)
    if op not in ('<', '≤', '>', '≥', '='):
        op = '='
    return {'p_op': op, 'p': _f(m.group(2)), 'p_raw': m.group(2)}, m.span()


def _parse_power_window(win):
    """从把握度/样本量窗口中解析 α、power、d、n（缺失为 None）。"""
    alpha = power = d = n = None
    m = re.search(r'[αa]\s*=\s*(0?\.\d+)', win)
    if m:
        alpha = _f(m.group(1))
    m = re.search(r'(?i)(?:power|检验效能|把握度)\s*[=为of]*\s*(0?\.\d+|\d{1,3}(?:\.\d+)?)\s*%?',
                  win)
    if m:
        v = _f(m.group(1))
        if v is not None:
            power = v / 100.0 if v > 1.0 else v
    m = re.search(r"(?i)(?:Cohen'?s?\s*)?d\s*=\s*(0?\.\d+|\d\.\d+)", win)
    if m:
        d = _f(m.group(1))
    m = re.search(r'(?<![A-Za-z])[nN]\s*=\s*(\d+)', win)
    if m:
        n = int(m.group(1))
    else:
        m = re.search(r'(\d+)\s*(?:例|名|人|participants|subjects)', win)
        if m:
            n = int(m.group(1))
    return alpha, power, d, n


def extract(text):
    """返回记录列表。任何单点失败只跳过该条，不中断整体。"""
    text = normalize(text)
    line_starts = [0]
    for m in re.finditer('\n', text):
        line_starts.append(m.end())

    # 1) 收集所有候选匹配，按 (起点, 优先级) 排序后去重叠
    cands = []
    for prio, (kind, pat, pri) in enumerate(STAT_PATTERNS):
        try:
            for m in pat.finditer(text):
                cands.append((m.start(), pri, prio, m, kind))
        except Exception:  # noqa: BLE001 —— 单条正则失败不致命
            continue
    cands.sort(key=lambda c: (c[0], c[1]))
    accepted = []
    spans = []
    for start, pri, prio, m, kind in cands:
        s, e = m.span()
        if any(s < oe and os < e for os, oe in spans):
            continue
        spans.append((s, e))
        accepted.append((m, kind))

    records = []
    used_p = set()
    for m, kind in accepted:
        s, e = m.span()
        g = m.groups()
        line = _line_of(line_starts, s)
        ctx = _context(text, s, e)
        raw = m.group(0).strip()
        rec = {'kind': kind, 'line': line, 'raw': raw}
        try:
            if kind == 't':
                rec.update(df=int(g[0]), stat=_f(g[1]), stat_raw=g[1])
            elif kind == 'F':
                rec.update(df1=int(g[0]), df2=int(g[1]), stat=_f(g[2]), stat_raw=g[2])
            elif kind == 'chi2':
                rec.update(df=int(g[0]) if g[0] else None,
                           stat=_f(g[1]), stat_raw=g[1])
            elif kind == 'z':
                rec.update(stat=_f(g[0]), stat_raw=g[0])
            elif kind == 'r':
                rec.update(df=int(g[0]) if g[0] else None,
                           stat=_f(g[1]), stat_raw=g[1])
            elif kind == 'ratio':
                rec.update(ratio_type=g[0].upper() if len(g[0]) <= 2 else
                           {'ODDS': 'OR', 'HAZARD': 'HR', 'RISK': 'RR',
                            'RELATIVE': 'RR'}.get(g[0].split()[0].upper(), 'OR'),
                           est=_f(g[1]), est_raw=g[1],
                           ci_lo=_f(g[2]), ci_lo_raw=g[2],
                           ci_hi=_f(g[3]), ci_hi_raw=g[3])
            elif kind == 'mean_sd':
                rec.update(mean=_f(g[0]), mean_raw=g[0],
                           spread=_f(g[1]), spread_raw=g[1])
                win = text[max(0, s - 60):min(len(text), e + 60)]
                rec['label'] = ('SEM' if re.search(r'(?i)\bSEM?\b|标准误', win)
                                else 'SD')
                mn = re.search(r'(?<![A-Za-z])[nN]\s*=\s*(\d+)', win)
                rec['n'] = int(mn.group(1)) if mn else None
            elif kind == 'percent':
                if '/' in raw.split('%')[0]:
                    # 23/45 (45.0%) 形式
                    rec.update(n=int(g[0]), N=int(g[1]),
                               pct=_f(g[2]), pct_raw=g[2])
                else:  # 45.0% (23/45) 形式
                    rec.update(pct=_f(g[0]), pct_raw=g[0],
                               n=int(g[1]), N=int(g[2]))
            elif kind == 'ci_mean':
                rec.update(est=_f(g[0]), est_raw=g[0],
                           ci_lo=_f(g[1]), ci_lo_raw=g[1],
                           ci_hi=_f(g[2]), ci_hi_raw=g[2])
        except (ValueError, IndexError, TypeError):
            continue  # 字段解析失败: 跳过该条, 不中断

        if kind in ('t', 'F', 'chi2', 'z', 'r', 'ratio'):
            p_rec, p_span = _attach_p(text, s, e, used_p)
            if p_rec is not None:
                rec.update(p_rec)
                if p_span is not None:
                    used_p.add(p_span)
        rec['context'] = ctx
        records.append(rec)

    # 2) 未被吸收的孤立 p 值
    for m in P_RE.finditer(text):
        if m.span() in used_p:
            continue
        if any(abs(m.start() - r.get('_pos', -10**9)) < 5 for r in records):
            continue
        # 若 p 落在已接受统计量跨距内则跳过
        if any(os <= m.start() < oe for os, oe in spans):
            continue
        op = m.group(1) or '='
        op = {'≦': '≤', '≧': '≥'}.get(op, op)
        if op not in ('<', '≤', '>', '≥', '='):
            op = '='
        records.append({'kind': 'p_only', 'line': _line_of(line_starts, m.start()),
                        'raw': m.group(0).strip(), 'p_op': op,
                        'p': _f(m.group(2)), 'p_raw': m.group(2),
                        'context': _context(text, *m.span())})

    # 3) 把握度/样本量窗口
    for m in POWER_KEY_RE.finditer(text):
        s = m.start()
        e = min(len(text), s + POWER_WIN)
        win = text[s:e]
        stop = win.find('。')
        if 0 < stop < len(win):
            win = win[:stop + 1]
        alpha, power, d, n = _parse_power_window(win)
        fields = [x for x in (alpha, power, d, n) if x is not None]
        if len(fields) < 2:
            continue  # 信息不足, 不产生记录
        records.append({'kind': 'power', 'line': _line_of(line_starts, s),
                        'raw': win.strip(), 'alpha': alpha, 'power': power,
                        'd': d, 'n': n,
                        'context': _context(text, s, e)})

    records.sort(key=lambda r: (r['line'], r['kind']))
    for r in records:
        r.pop('_pos', None)
    return records


def main(argv=None):
    ap = argparse.ArgumentParser(
        description='从论文纯文本抽取统计量 → stats.jsonl（纯标准库）。'
                    ' 空抽取仅告警，不视为失败。')
    ap.add_argument('input', help='输入纯文本文件（pdftotext -layout 产物）')
    ap.add_argument('-o', '--output', default='stats.jsonl',
                    help='输出 JSONL 路径（默认 stats.jsonl）')
    args = ap.parse_args(argv)

    try:
        with open(args.input, 'r', encoding='utf-8') as fh:
            text = fh.read()
    except (OSError, UnicodeDecodeError) as exc:
        print('ERROR: 无法读取输入文件 %s: %s' % (args.input, exc),
              file=sys.stderr)
        return 2

    records = extract(text)
    try:
        with open(args.output, 'w', encoding='utf-8') as fh:
            for rec in records:
                fh.write(json.dumps(rec, ensure_ascii=False) + '\n')
    except OSError as exc:
        print('ERROR: 无法写入输出文件 %s: %s' % (args.output, exc),
              file=sys.stderr)
        return 2

    if not records:
        print('WARNING: 未抽取到任何统计量（空抽取，非错误）', file=sys.stderr)
    else:
        print('INFO: 共抽取 %d 条统计量记录 → %s' % (len(records), args.output),
              file=sys.stderr)
    return 0


if __name__ == '__main__':
    sys.exit(main())
