#!/usr/bin/env python3
"""gain_compare.py -- 同稿双程对照: 量化 Skill 管线相对机械基线的增益。

指标 (同一稿件、同一 finding schema):
  1. 可核验率   有逐字 quote + 位置的 finding 占比
  2. 可执行率   action 含操作动词 (移动/合并/拆分/收窄/删除/插入/前置/后移) 的占比
  3. 维度有效覆盖  有 finding 或带 how_checked clearance 的维数
  4. 严重度分级率  severity ∈ {high,medium,low} 的占比

输出 gain_report.md, 含「基线为内部机械消融, 不代表平台基础 Agent」的硬性声明。

用法:
    python3 gain_compare.py BASE_JSON SKILL_JSON GAIN_REPORT_MD
"""
import json
import sys

ACTION_VERBS = ['移动', '合并', '拆分', '收窄', '删除', '插入', '前置', '后移',
                '补', '改写为', 'move', 'merge', 'split', 'narrow', 'delete', 'insert']
DIMS = ['研究问题', '章节结构', '论证链', '段落关系', '重复内容', '结论边界']
SEV = {'high', 'medium', 'low'}


def metrics(doc):
    fs = doc.get('findings', [])
    n = len(fs) or 1
    ver = sum(1 for x in fs if x.get('quote') and (x.get('location') or x.get('anchor')))
    act = sum(1 for x in fs
              if any(v in (x.get('action') or '') for v in ACTION_VERBS))
    sev = sum(1 for x in fs if x.get('severity') in SEV)
    cov = {x.get('dimension') for x in fs if x.get('dimension') in DIMS}
    cl = doc.get('dimension_clearance', {}) or {}
    cov |= {d for d, c in cl.items() if isinstance(c, dict) and c.get('how_checked')}
    return {'findings': len(fs),
            'verifiable_rate': round(ver / n, 3),
            'actionable_rate': round(act / n, 3),
            'severity_rated': round(sev / n, 3),
            'dimension_coverage': len(cov & set(DIMS))}


def compare(base_path, skill_path, out_md):
    with open(base_path, encoding='utf-8') as f:
        b = metrics(json.load(f))
    with open(skill_path, encoding='utf-8') as f:
        s = metrics(json.load(f))

    rows = []
    for k in ('findings', 'verifiable_rate', 'actionable_rate',
              'severity_rated', 'dimension_coverage'):
        delta = s[k] - b[k]
        rows.append('| %s | %s | %s | %+.3g |' % (k, b[k], s[k], delta))
    md = '\n'.join([
        '# 同稿双程对照报告（内部消融）', '',
        '> **声明**：基线是 `base_pass.py` 生成的机械消融（无锚定、无判据、无操作化），',
        '> 用于量化本 Skill 管线的自身增量；它**不代表平台的基础 Agent**，',
        '> 平台的官方对照由组织方运行，本报告不替代之。', '',
        '| 指标 | 机械基线 | Skill 管线 | 增量 |', '|---|---|---|---|'] + rows + [
        '', '## 读法', '',
        '- 可核验率：finding 带逐字引文与位置，评审可独立复核的比例；',
        '- 可执行率：action 为操作动词 + 对象，可直接执行的比例；',
        '- 维度有效覆盖：六维中有 finding 或有 how_checked clearance 的维数（满分 6）。', ''])
    with open(out_md, 'w', encoding='utf-8') as f:
        f.write(md + '\n')
    print(json.dumps({'base': b, 'skill': s}, ensure_ascii=False))


if __name__ == '__main__':
    if len(sys.argv) != 4:
        sys.exit('usage: gain_compare.py BASE_JSON SKILL_JSON GAIN_REPORT_MD')
    compare(*sys.argv[1:4])
