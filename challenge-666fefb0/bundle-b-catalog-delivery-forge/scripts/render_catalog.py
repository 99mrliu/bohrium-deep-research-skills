#!/usr/bin/env python3
"""render_catalog.py — render the four reviewable deliverables.

catalog.md (human) / catalog.csv (machine) / tree_diff.md (before-after) /
verify_report.md (hash re-check). All four are generated from the same ops
journal so they can never disagree with each other or with result.json.
"""
import csv
import datetime
import json
import os

from inventory import read_json, write_json

COLUMNS = ['fid', 'status', 'doc_type', 'category', 'subcategory', 'new_name',
           'original_path', 'archived_path', 'sha256', 'size_bytes', 'year',
           'doi', 'disposition', 'note']


def short(h):
    return (h or '')[:12]


def load_jsonl(path):
    rows = []
    if os.path.isfile(path):
        with open(path, encoding='utf-8') as f:
            for line in f:
                if line.strip():
                    rows.append(json.loads(line))
    return rows


def tree_lines(root):
    lines = []
    if not os.path.isdir(root):
        return ['(missing)']
    for r, dirs, files in os.walk(root):
        dirs.sort()
        depth = os.path.relpath(r, root).count(os.sep) + (0 if os.path.samefile(r, root) else 1)
        if not os.path.samefile(r, root):
            lines.append('  ' * (depth - 1) + os.path.basename(r) + '/')
        for fn in sorted(files):
            lines.append('  ' * depth + fn)
    return lines


def render_all(work_dir, out_dir):
    case = read_json(os.path.join(work_dir, 'case_meta.json'))
    files = {r['fid']: r for r in load_jsonl(os.path.join(work_dir, 'files.jsonl'))}
    ops = load_jsonl(os.path.join(out_dir, 'operations.jsonl'))
    skipped = read_json(os.path.join(work_dir, 'skipped.json')) if os.path.isfile(os.path.join(work_dir, 'skipped.json')) else []
    merged = read_json(os.path.join(work_dir, 'merged_plan.json'))
    verify = read_json(os.path.join(out_dir, 'verify_report.json'))
    relations = merged.get('version_relations') or []
    rel_by_fid = {}
    for g in relations:
        for fid in g.get('group', []):
            rel_by_fid[fid] = f"{g.get('relation', '')} (canonical: {g.get('canonical')})"

    op_by_fid = {o['fid']: o for o in ops}
    rows = []
    for fid, rec in sorted(files.items()):
        a = next((x for x in merged['assignments'] if x['fid'] == fid), None)
        op = op_by_fid.get(fid)
        sk = next((s for s in skipped if s['fid'] == fid), None)
        meta = (a or {}).get('metadata') or {}
        rows.append({
            'fid': fid,
            'status': 'archived' if op else ('skipped: ' + sk['reason'] if sk else 'skipped'),
            'doc_type': (a or {}).get('doc_type', ''),
            'category': (a or {}).get('category', ''),
            'subcategory': (a or {}).get('subcategory', ''),
            'new_name': (a or {}).get('new_name', ''),
            'original_path': rec['rel'],
            'archived_path': op['dst_rel'] if op else '',
            'sha256': rec.get('sha256') or '',
            'size_bytes': rec.get('size') or 0,
            'year': (meta.get('year') or {}).get('value', 'unknown'),
            'doi': (meta.get('doi') or {}).get('value', 'unknown'),
            'disposition': (a or {}).get('disposition', ''),
            'note': (sk or {}).get('reason', ''),
        })

    lib_out = os.path.join(out_dir, 'library')
    with open(os.path.join(out_dir, 'catalog.csv'), 'w', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS)
        w.writeheader()
        for row in rows:
            w.writerow(row)

    md = ['# 资料库整理总目录（catalog）', '',
          f"case_id: {case.get('case_id')}",
          f"生成时间: {datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='seconds')}",
          f"输入文件 {len(files)}；已归档 {sum(1 for r in rows if r['status'] == 'archived')}；"
          f"跳过 {sum(1 for r in rows if r['status'] != 'archived')}",
          '', '## 已归档', '']
    current = None
    for row in rows:
        if row['status'] != 'archived':
            continue
        group = f"{row['category']}/{row['subcategory']}"
        if group != current:
            current = group
            md += ['', f"### {group}", '']
        rel_note = f" — 版本关系: {rel_by_fid[row['fid']]}" if row['fid'] in rel_by_fid else ''
        conf = next((x.get('confidence') for x in merged['assignments'] if x['fid'] == row['fid']), None)
        conf_note = ' （置信度:低）' if conf == 'low' else ''
        md.append(f"- **{row['new_name']}** (`{row['fid']}`){conf_note}")
        md.append(f"  - 原始路径: `{row['original_path']}` → 归档: `library/{row['archived_path']}`")
        md.append(f"  - SHA-256: `{short(row['sha256'])}…` | 年份: {row['year']} | DOI: {row['doi']}{rel_note}")
    md += ['', '## 未归档（skipped）', '']
    for row in rows:
        if row['status'] == 'archived':
            continue
        md.append(f"- `{row['original_path']}` (`{row['fid']}`) — {row['status']}; 恢复建议: {row['note'] or '见 skipped'}")
    if relations:
        md += ['', '## 版本关系', '']
        for g in relations:
            md.append(f"- {g.get('group')}: {g.get('relation')} — canonical: {g.get('canonical')}; 证据: {g.get('evidence', '')}")
    with open(os.path.join(out_dir, 'catalog.md'), 'w', encoding='utf-8') as f:
        f.write('\n'.join(md) + '\n')

    before = tree_lines(case['library_dir'])
    after = tree_lines(lib_out)
    width = max((len(l) for l in before), default=20) + 4
    diff = ['# 整理前后目录树对照（tree diff）', '',
            f"{'整理前（' + case['library_dir'] + ')':<{width}}整理后（library/）",
            f"{'=' * min(width, 60)}  {'=' * 40}"]
    for i in range(max(len(before), len(after))):
        b = before[i] if i < len(before) else ''
        a = after[i] if i < len(after) else ''
        diff.append(f'{b:<{width}}{a}')
    diff += ['', '## 逐文件移动对照', '']
    for row in rows:
        if row['status'] == 'archived':
            diff.append(f"- `{row['original_path']}` → `library/{row['archived_path']}` ({row['disposition']})")
        else:
            diff.append(f"- `{row['original_path']}` — 未移动（{row['status']}）")
    with open(os.path.join(out_dir, 'tree_diff.md'), 'w', encoding='utf-8') as f:
        f.write('\n'.join(diff) + '\n')

    vr = ['# 哈希复核报告（verify report）', '',
          f"复核时间: {verify.get('ts')}",
          f"结论: {'全部一致 ✓' if verify.get('ok') else '存在不一致 ✗（见下）'}", '',
          '| 操作 | 源 SHA-256 | 目标 SHA-256 | 结论 |', '|---|---|---|---|']
    for o in ops:
        ok = o.get('src_sha256') == o.get('dst_sha256') and o.get('dst_present')
        vr.append(f"| {o['op_id']} | `{short(o.get('src_sha256'))}…` | `{short(o.get('dst_sha256'))}…` | {'一致 ✓' if ok else '不一致 ✗'} |")
    if verify.get('problems'):
        vr += ['', '## 不一致明细', ''] + [f"- {p}" for p in verify['problems']]
    with open(os.path.join(out_dir, 'verify_report.md'), 'w', encoding='utf-8') as f:
        f.write('\n'.join(vr) + '\n')
    return {'catalog_rows': len(rows),
            'archived': sum(1 for r in rows if r['status'] == 'archived')}
