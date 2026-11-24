#!/usr/bin/env python3
"""alignment_check.py -- 七要素对齐裁定庭。

读对齐矩阵 JSON（schema 见 references/alignment_schema.md），按合取式纳入条件
逐条裁定，输出逐项 pass/fail 裁定报告与覆盖率统计。任一 fail 即 gate 不过。

裁定规则：
  RQ-NUM      研究问题数须在 1..3
  RQ-CRIT     每个 RQ 含非空判断标准 decision_criterion
  RQ-COVER    每个 RQ 被 >=1 个 OBJ 引用
  OBJ-FIELDS  每个 OBJ 恰有 metric/threshold/threshold_basis/time_point（缺项即 fail）
  STEP-SERVE  每个 STEP 的 serves 引用 >=1 个 OBJ（孤儿步骤 fail）
  VAL-FIELDS  每条 VAL 含 control 与 statistical_criterion
  OUT-FIELDS  每个 OUT 含 acceptance_criterion
  OBJ-COVER   每个 OBJ >=1 条 VAL 且 >=1 个 OUT（覆盖门）
  RSK-FIELDS  每个 RSK 含 trigger_signal/fallback/decision_point（缺字段 fail）
  REF-INT     悬空引用与重复 id 检测

用法：
  python3 alignment_check.py MATRIX_JSON REPORT_JSON
退出码：全部通过 0；存在 fail 1（CI 可阻断交付）。
"""
import argparse
import json
import sys

OBJ_REQUIRED = ['metric', 'threshold', 'threshold_basis', 'time_point']
VAL_REQUIRED = ['control', 'statistical_criterion']
OUT_REQUIRED = ['acceptance_criterion']
RSK_REQUIRED = ['trigger_signal', 'fallback', 'decision_point']


def present(v):
    """字段值视为「非空」：非 None、非空白串、非空列表/字典。"""
    if v is None:
        return False
    if isinstance(v, str):
        return bool(v.strip())
    if isinstance(v, (list, dict)):
        return bool(v)
    return True


def check(matrix, matrix_path):
    verdicts = []

    def say(rule, target, ok, detail):
        verdicts.append({'rule': rule, 'target': target,
                         'verdict': 'pass' if ok else 'fail', 'detail': detail})

    rqs = matrix.get('research_questions') or []
    objs = matrix.get('objectives') or []
    steps = matrix.get('steps') or []
    vals = matrix.get('validations') or []
    outs = matrix.get('outcomes') or []
    rsks = matrix.get('risks') or []

    rq_ids = {r.get('id') for r in rqs}
    obj_ids = {o.get('id') for o in objs}
    step_ids = {s.get('id') for s in steps}
    all_ids = [e.get('id') for e in rqs + objs + steps + vals + outs + rsks]

    # REF-INT: 重复 id
    dupes = sorted({x for x in all_ids if x and all_ids.count(x) > 1})
    say('REF-INT', '(matrix)', not dupes,
        '无重复 id' if not dupes else '重复 id: %s' % ', '.join(dupes))

    # RQ-NUM
    say('RQ-NUM', '(matrix)', 1 <= len(rqs) <= 3,
        '研究问题 %d 个（要求 1–3）' % len(rqs))

    # 逐 RQ：判断标准 + 目标覆盖
    for rq in rqs:
        rid = rq.get('id', '?')
        say('RQ-CRIT', rid, present(rq.get('decision_criterion')),
            '含判断标准' if present(rq.get('decision_criterion'))
            else '缺 decision_criterion，RQ 不可证伪')
        n = sum(1 for o in objs if o.get('rq_id') == rid)
        say('RQ-COVER', rid, n >= 1,
            '挂有 %d 个 OBJ' % n if n else '没有任何 OBJ 回答该问题')

    # 逐 OBJ：必填四字段 + 引用完整性
    for o in objs:
        oid = o.get('id', '?')
        missing = [k for k in OBJ_REQUIRED if not present(o.get(k))]
        say('OBJ-FIELDS', oid, not missing,
            'metric/threshold/threshold_basis/time_point 齐全' if not missing
            else '缺必填字段: %s' % ', '.join(missing))
        rq_ref = o.get('rq_id')
        say('REF-INT', oid, rq_ref in rq_ids,
            'rq_id -> %s' % rq_ref if rq_ref in rq_ids
            else 'rq_id %r 指向不存在的 RQ' % rq_ref)

    # 逐 STEP：孤儿检测 + 依赖引用
    for s in steps:
        sid = s.get('id', '?')
        serves = s.get('serves') or []
        say('STEP-SERVE', sid, len(serves) >= 1,
            '服务 %d 个 OBJ: %s' % (len(serves), ', '.join(serves)) if serves
            else '孤儿步骤：不服务任何 OBJ（做了无人考核的工作）')
        bad = [x for x in serves if x not in obj_ids]
        bad += [x for x in (s.get('depends_on') or []) if x not in step_ids]
        say('REF-INT', sid, not bad,
            'serves/depends_on 引用均可解析' if not bad
            else '悬空引用: %s' % ', '.join(bad))

    # 逐 VAL：必填字段 + 引用
    for v in vals:
        vid = v.get('id', '?')
        missing = [k for k in VAL_REQUIRED if not present(v.get(k))]
        say('VAL-FIELDS', vid, not missing,
            '对照与统计判据齐全' if not missing
            else '缺必填字段: %s' % ', '.join(missing))
        say('REF-INT', vid, v.get('obj_id') in obj_ids,
            'obj_id -> %s' % v.get('obj_id') if v.get('obj_id') in obj_ids
            else 'obj_id %r 指向不存在的 OBJ' % v.get('obj_id'))

    # 逐 OUT：必填字段 + 引用
    for o in outs:
        oid = o.get('id', '?')
        missing = [k for k in OUT_REQUIRED if not present(o.get(k))]
        say('OUT-FIELDS', oid, not missing,
            '含验收判据' if not missing
            else '缺必填字段: %s（成果无法考核）' % ', '.join(missing))
        say('REF-INT', oid, o.get('obj_id') in obj_ids,
            'obj_id -> %s' % o.get('obj_id') if o.get('obj_id') in obj_ids
            else 'obj_id %r 指向不存在的 OBJ' % o.get('obj_id'))

    # OBJ-COVER 覆盖门：每个 OBJ >=1 VAL 且 >=1 OUT
    for o in objs:
        oid = o.get('id', '?')
        nv = sum(1 for v in vals if v.get('obj_id') == oid)
        no = sum(1 for u in outs if u.get('obj_id') == oid)
        say('OBJ-COVER', oid, nv >= 1 and no >= 1,
            'VAL %d 条, OUT %d 个' % (nv, no) if (nv >= 1 and no >= 1)
            else '覆盖门未过: VAL %d 条, OUT %d 个（各需 >=1）' % (nv, no))

    # 逐 RSK：三连字段 + 引用
    for r in rsks:
        rid = r.get('id', '?')
        missing = [k for k in RSK_REQUIRED if not present(r.get(k))]
        say('RSK-FIELDS', rid, not missing,
            '触发信号/备选方案/决策时点齐全' if not missing
            else '缺必填字段: %s' % ', '.join(missing))
        targets = r.get('affects') or []
        bad = [x for x in targets if x not in step_ids and x not in obj_ids]
        say('REF-INT', rid, bool(targets) and not bad,
            'affects 引用均可解析' if (targets and not bad)
            else ('affects 为空或含悬空引用: %s' % ', '.join(bad) if bad
                  else 'affects 为空，风险未挂到任何 STEP/OBJ'))

    fails = [v for v in verdicts if v['verdict'] == 'fail']

    def ratio(a, b):
        return round(a / b, 3) if b else None

    stats = {
        'rq_total': len(rqs),
        'rq_covered': sum(1 for r in rqs
                          if any(o.get('rq_id') == r.get('id') for o in objs)),
        'obj_total': len(objs),
        'obj_fields_complete': sum(
            1 for o in objs
            if all(present(o.get(k)) for k in OBJ_REQUIRED)),
        'obj_with_val': len({v.get('obj_id') for v in vals if v.get('obj_id') in obj_ids}),
        'obj_with_out': len({u.get('obj_id') for u in outs if u.get('obj_id') in obj_ids}),
        'step_total': len(steps),
        'step_orphans': sum(1 for s in steps if not (s.get('serves') or [])),
        'val_total': len(vals), 'out_total': len(outs),
        'rsk_total': len(rsks),
        'rsk_complete': sum(
            1 for r in rsks if all(present(r.get(k)) for k in RSK_REQUIRED)),
        'verdict_pass': sum(1 for v in verdicts if v['verdict'] == 'pass'),
        'verdict_fail': len(fails),
    }
    stats['obj_val_coverage'] = ratio(stats['obj_with_val'], stats['obj_total'])
    stats['obj_out_coverage'] = ratio(stats['obj_with_out'], stats['obj_total'])
    stats['step_orphan_rate'] = ratio(stats['step_orphans'], stats['step_total'])

    report = {'matrix': matrix_path,
              'gate_pass': not fails,
              'fail_count': len(fails),
              'stats': stats,
              'verdicts': verdicts,
              'fails': fails}
    return report


def main():
    ap = argparse.ArgumentParser(description='七要素对齐裁定庭：对齐矩阵合取式校验')
    ap.add_argument('matrix', help='对齐矩阵 JSON 路径')
    ap.add_argument('report', help='裁定报告输出 JSON 路径')
    args = ap.parse_args()

    with open(args.matrix, encoding='utf-8') as f:
        matrix = json.load(f)
    report = check(matrix, args.matrix)
    with open(args.report, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(json.dumps({'gate_pass': report['gate_pass'],
                      'fail_count': report['fail_count'],
                      'failed_rules': sorted({v['rule'] for v in report['fails']}),
                      'failed_targets': [v['target'] for v in report['fails']]},
                     ensure_ascii=False))
    return 0 if report['gate_pass'] else 1


if __name__ == '__main__':
    sys.exit(main())
