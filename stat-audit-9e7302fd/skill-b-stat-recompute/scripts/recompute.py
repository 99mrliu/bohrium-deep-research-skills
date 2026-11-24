#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""recompute.py — 确定性数值重算内核（纯标准库）。

读取 extract_stats.py 生成的 stats.jsonl，对每条可算记录:
  1) 由统计量 + 自由度重算 p 值；
  2) 用区间算术容纳报告值的舍入误差（statcheck 式抗误报）:
     报告统计量视作落在其舍入区间内 → 重算 p 区间；
     报告 p 值同样视作舍入区间；两区间无交集才判定不一致；
  3) 不一致时区分「显著性翻转」(critical) 与「数值偏差」(major)；
  4) 比率量 (OR/HR/RR): CI↔p 方向矛盾、对数尺度 CI 不对称；
  5) 百分比↔计数自洽；不可能值 (|r|>1, p∉[0,1], SD<0, n>N 等)；
  6) mean±SD 的 SEM 混用提示；样本量/把握度粗反算 (>20% 偏差才报)。

无法重算的记录只计入「待复核」汇总计数，绝不臆造数值。
输出 findings.jsonl: {line, kind, category, severity, message,
                     reported, recomputed, context}

用法: python3 recompute.py stats.jsonl [-o findings.jsonl] [--alpha 0.05]
规则与常量的权威说明见 references/recheck_rules.md，两者必须一致。
"""

import argparse
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    import statmath
except ImportError as exc:
    print('ERROR: 无法导入 statmath.py: %s' % exc, file=sys.stderr)
    sys.exit(2)

# ---- 规则常量（与 references/recheck_rules.md 保持一致，改动须同步） ----
DEFAULT_ALPHA = 0.05   # 显著性阈值，可用 --alpha 覆盖
ASYM_TOL = 0.15        # CI 不对称容忍度（对数/算术半宽的相对偏差）
POWER_TOL = 0.20       # 样本量反算相对偏差容忍度


# ---------------------------------------------------------------- 工具 -----
def dec_places(raw):
    """报告值字符串的小数位数，用于确定舍入半宽。"""
    if raw is None:
        return 2
    s = str(raw).strip().lstrip('+-')
    if '.' in s:
        return len(s.split('.', 1)[1])
    return 0


def half_unit(raw):
    return 0.5 * (10.0 ** -dec_places(raw))


def stat_interval(value, raw, nonnegative=False):
    """报告统计量的舍入区间 [lo, hi]。"""
    h = half_unit(raw)
    lo, hi = value - h, value + h
    if nonnegative:
        lo = max(0.0, lo)
    return lo, hi


def p_interval_from_stat(kind, rec):
    """由统计量舍入区间重算 p 值区间 (p_lo, p_hi)。不可算返回 None。"""
    try:
        if kind == 't':
            df = rec.get('df')
            if df is None:
                return None
            lo, hi = stat_interval(abs(rec['stat']), rec.get('stat_raw'))
            return (statmath.t_two_sided_p(hi, df),
                    statmath.t_two_sided_p(lo, df))
        if kind == 'F':
            df1, df2 = rec.get('df1'), rec.get('df2')
            if df1 is None or df2 is None:
                return None
            lo, hi = stat_interval(rec['stat'], rec.get('stat_raw'), True)
            return (statmath.f_sf(hi, df1, df2), statmath.f_sf(lo, df1, df2))
        if kind == 'chi2':
            df = rec.get('df')
            if df is None:
                return None
            lo, hi = stat_interval(rec['stat'], rec.get('stat_raw'), True)
            return (statmath.chi2_sf(hi, df), statmath.chi2_sf(lo, df))
        if kind == 'z':
            lo, hi = stat_interval(abs(rec['stat']), rec.get('stat_raw'))
            return (statmath.norm_two_sided_p(hi), statmath.norm_two_sided_p(lo))
        if kind == 'r':
            df = rec.get('df')
            if df is None:
                return None
            lo, hi = stat_interval(abs(rec['stat']), rec.get('stat_raw'))
            hi = min(hi, 0.999999)
            return (statmath.r_two_sided_p(hi, df),
                    statmath.r_two_sided_p(lo, df))
    except (ValueError, KeyError, TypeError, OverflowError):
        return None
    return None


def fmt_interval(pl, ph):
    return '[%.5f, %.5f]' % (pl, ph)


# ------------------------------------------------------------ 主比较逻辑 ---
class Auditor:
    def __init__(self, alpha):
        self.alpha = alpha
        self.findings = []
        self.pending = {}   # (kind, reason) -> count
        self.ok_count = 0

    def add(self, rec, category, severity, message, reported, recomputed):
        self.findings.append({
            'line': rec.get('line'),
            'kind': rec.get('kind'),
            'category': category,
            'severity': severity,
            'message': message,
            'reported': reported,
            'recomputed': recomputed,
            'context': rec.get('context', ''),
        })

    def pend(self, kind, reason):
        self.pending[(kind, reason)] = self.pending.get((kind, reason), 0) + 1

    # -- p 值比较: 返回 True 表示已处理（含发现），False 表示无法比较 ----
    def compare_p(self, rec, pl, ph, stat_desc):
        p = rec.get('p')
        p_op = rec.get('p_op', '=')
        p_raw = rec.get('p_raw')
        if p is None:
            self.add(rec, '规范问题', 'minor',
                     '%s 未报告 p 值，显著性无法核对' % stat_desc,
                     '无 p 值', fmt_interval(pl, ph))
            self.pend(rec['kind'], '缺p值')
            return True
        if not (0.0 <= p <= 1.0):
            self.add(rec, '事实错误', 'critical',
                     '不可能值: 报告的 p 值超出 [0,1]',
                     'p=%s' % p_raw, 'p∈[0,1]')
            return True
        a = self.alpha
        if p_op in ('<', '≤', '>', '≥'):
            thr = p
            if p_op in ('<', '≤'):
                # 声称 p<thr；若重算区间整体 ≥ thr 则显著性翻转
                if pl >= thr:
                    self.add(rec, '事实错误', 'critical',
                             '显著性翻转: 报告 p%s%s 但重算 p 区间整体≥%s'
                             % (p_op, p_raw, p_raw),
                             'p%s%s' % (p_op, p_raw), fmt_interval(pl, ph))
                    return True
            else:
                if ph <= thr:
                    self.add(rec, '事实错误', 'critical',
                             '显著性翻转: 报告 p%s%s 但重算 p 区间整体<%s'
                             % (p_op, p_raw, p_raw),
                             'p%s%s' % (p_op, p_raw), fmt_interval(pl, ph))
                    return True
            self.add(rec, '规范问题', 'minor',
                     '%s 以不等式报告 p 值（缺精确 p），建议补报精确值'
                     % stat_desc,
                     'p%s%s' % (p_op, p_raw), fmt_interval(pl, ph))
            self.ok_count += 1
            return True
        # 精确 p: 报告 p 的舍入区间与重算区间求交集
        hp = half_unit(p_raw)
        r_lo, r_hi = max(0.0, p - hp), min(1.0, p + hp)
        if r_lo <= ph and pl <= r_hi:
            self.ok_count += 1
            return True
        # 无交集 → 判定翻转还是偏差（约定 p=α 视为显著侧）
        rep_side = p <= a
        if rep_side and pl >= a:
            flip = True
        elif (not rep_side) and ph < a:
            flip = True
        else:
            flip = False
        if flip:
            self.add(rec, '事实错误', 'critical',
                     '显著性翻转: 报告 p 与重算 p 区间分居 α=%g 两侧'
                     % a,
                     'p=%s' % p_raw, fmt_interval(pl, ph))
        else:
            self.add(rec, '事实错误', 'major',
                     '数值偏差: 报告 p 落在重算区间之外，但未改变显著性结论',
                     'p=%s' % p_raw, fmt_interval(pl, ph))
        return True

    # ------------------------------------------------------------ 各类 ----
    def check_test_stat(self, rec):
        kind = rec['kind']
        desc = {'t': 't 检验', 'F': 'F 检验', 'chi2': 'χ² 检验',
                'z': 'z 检验', 'r': '相关 r'}.get(kind, kind)
        # 不可能值
        if kind == 'r' and rec.get('stat') is not None and abs(rec['stat']) > 1.0:
            self.add(rec, '事实错误', 'critical',
                     '不可能值: |r|>1', 'r=%s' % rec.get('stat_raw'), '|r|≤1')
            return
        missing_df = ((kind in ('t', 'chi2', 'r') and rec.get('df') is None) or
                      (kind == 'F' and (rec.get('df1') is None or
                                        rec.get('df2') is None)))
        if missing_df:
            self.add(rec, '规范问题', 'minor',
                     '%s 缺自由度，无法重算（待复核）' % desc,
                     rec.get('raw', ''), '—')
            self.pend(kind, '缺df')
            return
        iv = p_interval_from_stat(kind, rec)
        if iv is None:
            self.pend(kind, '重算失败')
            return
        self.compare_p(rec, iv[0], iv[1], desc)

    def check_p_only(self, rec):
        p = rec.get('p')
        if p is not None and not (0.0 <= p <= 1.0):
            self.add(rec, '事实错误', 'critical',
                     '不可能值: 报告的 p 值超出 [0,1]',
                     'p=%s' % rec.get('p_raw'), 'p∈[0,1]')
            return
        if rec.get('p_op') in ('<', '≤', '>', '≥'):
            msg = '孤立 p 值以不等式报告（缺精确 p），且无所属统计量，无法核对'
        else:
            msg = '孤立 p 值，未找到所属统计量与自由度，无法核对'
        self.add(rec, '规范问题', 'minor', msg,
                 rec.get('raw', ''), '—')
        self.pend('p_only', '无所属统计量')

    def check_ratio(self, rec):
        est, lo, hi = rec.get('est'), rec.get('ci_lo'), rec.get('ci_hi')
        rt = rec.get('ratio_type', 'OR')
        if est is None or lo is None or hi is None:
            self.pend('ratio', '字段缺失')
            return
        if lo > hi:
            self.add(rec, '事实错误', 'critical',
                     '不可能值: %s 的 CI 下界大于上界' % rt,
                     rec.get('raw', ''), 'CI 下界≤上界')
            return
        if est <= 0 or lo <= 0 or hi <= 0:
            self.add(rec, '事实错误', 'critical',
                     '不可能值: %s 或其 CI 含非正数（比率量必须为正）' % rt,
                     rec.get('raw', ''), '>0')
            return
        if not (lo <= est <= hi):
            self.add(rec, '事实错误', 'critical',
                     '不可能值: %s 点估计落在自身 95%%CI 之外' % rt,
                     'est=%s CI[%s, %s]' % (rec.get('est_raw'),
                                            rec.get('ci_lo_raw'),
                                            rec.get('ci_hi_raw')),
                     'est∈CI')
            return
        # 对数尺度对称性
        center = (math.log(lo) + math.log(hi)) / 2.0
        halfwidth = (math.log(hi) - math.log(lo)) / 2.0
        if halfwidth > 0:
            asym = abs(math.log(est) - center) / halfwidth
            if asym > ASYM_TOL:
                self.add(rec, '规范问题', 'major',
                         '%s 点估计明显偏离 CI 对数几何中心'
                         '（不对称度 %.2f > %g），疑转录或取整错误'
                         % (rt, asym, ASYM_TOL),
                         'est=%s CI[%s, %s]' % (rec.get('est_raw'),
                                                rec.get('ci_lo_raw'),
                                                rec.get('ci_hi_raw')),
                         '几何中心=%.4f' % math.exp(center))
        # CI↔p 方向矛盾
        crosses = lo <= 1.0 <= hi
        p, p_op = rec.get('p'), rec.get('p_op', '=')
        if p is None:
            self.add(rec, '规范问题', 'minor',
                     '%s 报告了 CI 但未报告 p 值' % rt,
                     rec.get('raw', ''), '—')
            self.pend('ratio', '缺p值')
            return
        if not (0.0 <= p <= 1.0):
            self.add(rec, '事实错误', 'critical',
                     '不可能值: 报告的 p 值超出 [0,1]',
                     'p=%s' % rec.get('p_raw'), 'p∈[0,1]')
            return
        sig = (p < self.alpha) if p_op == '=' else (p_op in ('<', '≤'))
        if crosses and sig:
            self.add(rec, '事实错误', 'critical',
                     'CI↔p 矛盾: %s 的 95%%CI 跨越 1（不显著）'
                     '但报告 p%s%s（显著）' % (rt, p_op, rec.get('p_raw')),
                     'CI[%s, %s], p%s%s' % (rec.get('ci_lo_raw'),
                                            rec.get('ci_hi_raw'), p_op,
                                            rec.get('p_raw')),
                     'CI 跨 1 ⇒ p 应≥%g' % self.alpha)
        elif (not crosses) and not sig:
            self.add(rec, '事实错误', 'critical',
                     'CI↔p 矛盾: %s 的 95%%CI 完全不跨 1（显著）'
                     '但报告 p%s%s（不显著）' % (rt, p_op, rec.get('p_raw')),
                     'CI[%s, %s], p%s%s' % (rec.get('ci_lo_raw'),
                                            rec.get('ci_hi_raw'), p_op,
                                            rec.get('p_raw')),
                     'CI 不跨 1 ⇒ p 应<%g' % self.alpha)
        else:
            self.ok_count += 1

    def check_percent(self, rec):
        n, N, pct = rec.get('n'), rec.get('N'), rec.get('pct')
        if n is None or N is None or pct is None:
            self.pend('percent', '字段缺失')
            return
        if N <= 0:
            self.add(rec, '事实错误', 'critical',
                     '不可能值: 分母 N≤0', rec.get('raw', ''), 'N>0')
            return
        if n > N:
            self.add(rec, '事实错误', 'critical',
                     '不可能值: 分子 n=%d 大于分母 N=%d' % (n, N),
                     rec.get('raw', ''), 'n≤N')
            return
        if not (0.0 <= pct <= 100.0):
            self.add(rec, '事实错误', 'critical',
                     '不可能值: 百分比超出 [0,100]',
                     'pct=%s' % rec.get('pct_raw'), '0–100')
            return
        computed = 100.0 * n / N
        hp = half_unit(rec.get('pct_raw'))
        if abs(computed - pct) > hp + 1e-9:
            self.add(rec, '事实错误', 'major',
                     '百分比不自洽: %d/%d=%.2f%% 与报告 %s%% 不符'
                     % (n, N, computed, rec.get('pct_raw')),
                     '%s%%' % rec.get('pct_raw'),
                     '%.2f%%' % computed)
        else:
            self.ok_count += 1

    def check_mean_sd(self, rec):
        mean, spread = rec.get('mean'), rec.get('spread')
        label = rec.get('label', 'SD')
        if mean is None or spread is None:
            self.pend('mean_sd', '字段缺失')
            return
        if spread < 0:
            self.add(rec, '事实错误', 'critical',
                     '不可能值: %s 为负' % label,
                     rec.get('raw', ''), '≥0')
            return
        if label == 'SEM':
            n = rec.get('n')
            hint = ('SEM×√n≈%.3f 应约等于 SD，' % (spread * math.sqrt(n))
                    if n else '')
            self.add(rec, '待复核', '待复核',
                     '该处以 SEM（标准误）报告离散度；%s'
                     '请核对是否误用 SEM 代替 SD' % hint,
                     rec.get('raw', ''), '—')
            self.pend('mean_sd', 'SEM待复核')
        else:
            self.ok_count += 1

    def check_ci_mean(self, rec):
        est, lo, hi = rec.get('est'), rec.get('ci_lo'), rec.get('ci_hi')
        if est is None or lo is None or hi is None:
            self.pend('ci_mean', '字段缺失')
            return
        if lo > hi:
            self.add(rec, '事实错误', 'critical',
                     '不可能值: CI 下界大于上界', rec.get('raw', ''),
                     'CI 下界≤上界')
            return
        if not (lo <= est <= hi):
            self.add(rec, '事实错误', 'critical',
                     '不可能值: 点估计落在自身 95%CI 之外',
                     'est=%s CI[%s, %s]' % (rec.get('est_raw'),
                                            rec.get('ci_lo_raw'),
                                            rec.get('ci_hi_raw')),
                     'est∈CI')
            return
        halfwidth = (hi - lo) / 2.0
        if halfwidth > 0:
            asym = abs(est - (lo + hi) / 2.0) / halfwidth
            if asym > ASYM_TOL:
                self.add(rec, '规范问题', 'major',
                         'CI 不关于点估计对称（不对称度 %.2f > %g），'
                         '疑转录错误' % (asym, ASYM_TOL),
                         'est=%s CI[%s, %s]' % (rec.get('est_raw'),
                                                rec.get('ci_lo_raw'),
                                                rec.get('ci_hi_raw')),
                         '中心=%.4f' % ((lo + hi) / 2.0))
                return
        self.ok_count += 1

    def check_power(self, rec):
        alpha, power, d, n = (rec.get('alpha'), rec.get('power'),
                              rec.get('d'), rec.get('n'))
        if None in (alpha, power, d, n) or d == 0:
            self.pend('power', '字段不全(α/power/d/n)')
            return
        try:
            z_a = statmath.inv_norm(1.0 - alpha / 2.0)
            z_b = statmath.inv_norm(power)
        except ValueError:
            self.pend('power', '参数越界')
            return
        n_per_group = 2.0 * ((z_a + z_b) / d) ** 2   # 两组 t 检验每组 n
        implied_total = 2.0 * n_per_group
        rel_pg = abs(n_per_group - n) / max(n, 1)
        rel_tot = abs(implied_total - n) / max(n, 1)
        if min(rel_pg, rel_tot) > POWER_TOL:
            which = '每组约 %.0f（总约 %.0f）' % (n_per_group, implied_total)
            self.add(rec, '规范问题', 'major',
                     '样本量反算不符: 由 α=%g, power=%g, d=%g 反推 %s，'
                     '与报告 n=%d 相对偏差 %.0f%% > %g%%'
                     % (alpha, power, d, which, n,
                        min(rel_pg, rel_tot) * 100, POWER_TOL * 100),
                     'n=%d' % n, which)
        else:
            self.ok_count += 1

    def run(self, records):
        for rec in records:
            try:
                kind = rec.get('kind')
                if kind in ('t', 'F', 'chi2', 'z', 'r'):
                    self.check_test_stat(rec)
                elif kind == 'p_only':
                    self.check_p_only(rec)
                elif kind == 'ratio':
                    self.check_ratio(rec)
                elif kind == 'percent':
                    self.check_percent(rec)
                elif kind == 'mean_sd':
                    self.check_mean_sd(rec)
                elif kind == 'ci_mean':
                    self.check_ci_mean(rec)
                elif kind == 'power':
                    self.check_power(rec)
                else:
                    self.pend(str(kind), '未知kind')
            except Exception:  # noqa: BLE001 —— 单条记录绝不允许崩溃
                self.pend(str(rec.get('kind')), '处理异常')


def main(argv=None):
    ap = argparse.ArgumentParser(
        description='对 stats.jsonl 做确定性数值重算 → findings.jsonl。'
                    ' 不可算记录计入待复核汇总，绝不臆造。')
    ap.add_argument('input', help='extract_stats.py 生成的 stats.jsonl')
    ap.add_argument('-o', '--output', default='findings.jsonl',
                    help='输出 JSONL 路径（默认 findings.jsonl）')
    ap.add_argument('--alpha', type=float, default=DEFAULT_ALPHA,
                    help='显著性阈值（默认 %.2f）' % DEFAULT_ALPHA)
    args = ap.parse_args(argv)

    if not (0.0 < args.alpha < 1.0):
        print('ERROR: --alpha 必须在 (0,1) 内', file=sys.stderr)
        return 2
    try:
        records = []
        with open(args.input, 'r', encoding='utf-8') as fh:
            for ln, line in enumerate(fh, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    print('WARNING: 第 %d 行 JSON 解析失败，已跳过' % ln,
                          file=sys.stderr)
    except (OSError, UnicodeDecodeError) as exc:
        print('ERROR: 无法读取输入文件 %s: %s' % (args.input, exc),
              file=sys.stderr)
        return 2

    auditor = Auditor(args.alpha)
    auditor.run(records)

    try:
        with open(args.output, 'w', encoding='utf-8') as fh:
            for f in auditor.findings:
                fh.write(json.dumps(f, ensure_ascii=False) + '\n')
    except OSError as exc:
        print('ERROR: 无法写入输出文件 %s: %s' % (args.output, exc),
              file=sys.stderr)
        return 2

    # ---- 汇总 ----
    sev_count = {}
    for f in auditor.findings:
        sev_count[f['severity']] = sev_count.get(f['severity'], 0) + 1
    print('== 重算汇总 ==')
    print('记录总数: %d' % len(records))
    print('核对一致: %d' % auditor.ok_count)
    for sev in ('critical', 'major', 'minor', '待复核'):
        if sev in sev_count:
            print('发现 %s: %d' % (sev, sev_count[sev]))
    pend_total = sum(auditor.pending.values())
    print('待复核（无法重算）合计: %d' % pend_total)
    for (kind, reason), c in sorted(auditor.pending.items()):
        print('  - kind=%s 原因=%s: %d' % (kind, reason, c))
    if not records:
        print('WARNING: 输入为空（无记录可算）', file=sys.stderr)
    return 0


if __name__ == '__main__':
    sys.exit(main())
