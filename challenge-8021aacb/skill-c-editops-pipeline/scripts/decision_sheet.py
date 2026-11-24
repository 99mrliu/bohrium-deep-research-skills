#!/usr/bin/env python3
"""decision_sheet.py -- 作者决策表渲染器。

把校验通过的编辑操作渲染成 Markdown 决策表: 每条 op 一行, 含采纳 /
部分采纳 / 驳回三列待作者勾选, 以及指回原文块 ID 的证据列。
这是「说得清」的交付形态: 作者逐条复核后可直接圈定执行范围。

用法:
    python3 decision_sheet.py OPS_JSON CHANGE_LOG_JSON OUT_MD
"""
import json
import sys


def render(ops_path, log_path, out_md):
    with open(ops_path, encoding='utf-8') as f:
        doc = json.load(f)
    ops = doc.get('ops', doc if isinstance(doc, list) else [])
    with open(log_path, encoding='utf-8') as f:
        log = json.load(f)
    status = {e['id']: e['status'] for e in log.get('log', [])}
    reason = {e['id']: e.get('reason', '') for e in log.get('log', [])}

    lines = ['# 结构修改决策表（作者复核用）', '',
             '每条编辑操作对应一处结构诊断；请在「决定」列勾选 采纳 / 部分采纳 / 驳回，',
             '驳回时请在备注写明理由。模拟应用状态来自 change_log.json。', '',
             '| 操作 ID | 类型 | 对象块 | 动作摘要 | 依据（rationale） | 模拟状态 | 决定 | 备注 |',
             '|---|---|---|---|---|---|---|---|']
    for op in ops:
        oid = op.get('id', '?')
        tgt = op.get('target') or op.get('before') or op.get('after') or ''
        summary = _summarize(op).replace('|', '\\|')
        rat = (op.get('rationale') or '').replace('|', '\\|')
        st = status.get(oid, '未模拟')
        if st == 'skipped':
            st += '（%s）' % reason.get(oid, '')
        lines.append('| %s | %s | %s | %s | %s | %s | ☐采纳 ☐部分 ☐驳回 |  |'
                     % (oid, op.get('op'), tgt, summary, rat, st))
    lines += ['', '决策完成后，将勾选项回执给 Agent 以更新 change_record。']
    with open(out_md, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines) + '\n')
    print(json.dumps({'rows': len(ops), 'out': out_md}, ensure_ascii=False))


def _summarize(op):
    k = op.get('op')
    if k == 'move':
        return '移动到 %s 之后' % op.get('after')
    if k == 'merge':
        return '并入 %s' % op.get('into')
    if k == 'split':
        return '从『%s…』处拆分' % (op.get('at_quote', '')[:12])
    if k == 'narrow':
        return '把『%s…』收窄为『%s…』' % (op.get('quote', '')[:12], op.get('replacement', '')[:12])
    if k == 'delete_duplicate':
        return '删除（与 %s 逐字重复）' % op.get('duplicate_of')
    if k == 'insert_transition':
        return '在 %s 前插入过渡句' % op.get('before')
    if k == 'add_limitation':
        return '在 %s 后插入限制说明' % op.get('after')
    if k == 'reorder_section':
        return '整节移动到 %s 之后' % op.get('after')
    return str(op)


if __name__ == '__main__':
    if len(sys.argv) != 4:
        sys.exit('usage: decision_sheet.py OPS_JSON CHANGE_LOG_JSON OUT_MD')
    render(*sys.argv[1:4])
