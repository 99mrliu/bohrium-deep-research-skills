#!/usr/bin/env python3
"""base_pass.py -- 机械基线诊断 (消融对照的 "无技能" 一程)。

刻意模拟不做锚定、不做判据、不做操作化的朴素诊断:
对每维按线索命中数写一条笼统结论, 无逐字引文、无可执行动作。
这是内部消融基线, 用于量化 Skill 管线的增益;
**不代表平台的基础 Agent**, 报告中必须如此标注 (见 two_pass_protocol.md)。

用法:
    python3 base_pass.py MANUSCRIPT_MD BASE_DIAG_JSON
"""
import json
import re
import sys

DIM_CUES = {
    '研究问题': ['旨在', '提出', 'aims', 'propose'],
    '章节结构': ['引言', '方法', '结果', '结论', 'introduction', 'conclusion'],
    '论证链': ['表明', '证明', '因此', 'shows', 'therefore'],
    '段落关系': ['然而', '此外', 'however', 'moreover'],
    '重复内容': ['如前所述', '再次', 'as mentioned'],
    '结论边界': ['最优', '所有', '完全', 'best', 'all', 'completely'],
}
GENERIC = {
    '研究问题': '研究问题的提出与回收情况建议作者通读检查。',
    '章节结构': '章节安排建议参考领域惯例进一步推敲。',
    '论证链': '部分论断的支撑力度建议加强。',
    '段落关系': '段落衔接建议更加连贯。',
    '重复内容': '建议检查是否存在重复表述。',
    '结论边界': '结论表述建议更加严谨。',
}


def base(ms_path, out_path):
    with open(ms_path, encoding='utf-8') as f:
        text = f.read()
    findings = []
    for dim, cues in DIM_CUES.items():
        hits = sum(text.count(c) for c in cues)
        findings.append({
            'id': 'B-%s' % dim, 'dimension': dim,
            'location': None, 'quote': None,
            'defect_class': '笼统印象（基线）',
            'action': GENERIC[dim],
            'severity': 'unknown',
            'cue_hits': hits,
            'verifiable': False,
        })
    doc = {'pass': 'base (mechanical, un-anchored)',
           'note': '内部消融基线, 不代表平台基础 Agent; 见 two_pass_protocol.md',
           'findings': findings}
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(doc, f, ensure_ascii=False, indent=2)
    print(json.dumps({'base_findings': len(findings)}, ensure_ascii=False))


if __name__ == '__main__':
    if len(sys.argv) != 3:
        sys.exit('usage: base_pass.py MANUSCRIPT_MD BASE_DIAG_JSON')
    base(*sys.argv[1:3])
