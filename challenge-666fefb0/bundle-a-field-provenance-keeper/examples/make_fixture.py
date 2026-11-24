#!/usr/bin/env python3
"""make_fixture.py — generate the SYNTHETIC example fixture.

合成示例：以下所有文件、元数据与决策均为演示数据，非正式案例、非真实文献。
PDF 由内置的最小 PDF 写出器生成（Helvetica 文本层，pdftotext 可抽取）。
"""
import os
import stat
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
FIX = os.path.join(HERE, 'fixture')
LIB = os.path.join(FIX, 'input', 'library')


def esc(s):
    return s.replace('\\', '\\\\').replace('(', '\\(').replace(')', '\\)')


def make_pdf(path, lines, text=True):
    if text:
        content = 'BT /F1 12 Tf 72 760 Td 16 TL\n' + '\n'.join(
            f'({esc(l)}) Tj T*' for l in lines) + '\nET'
    else:  # valid PDF with no text layer (a drawn rectangle only)
        content = '0.2 0.5 0.8 rg 72 700 300 60 re f'
    objs = [
        '<< /Type /Catalog /Pages 2 0 R >>',
        '<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
        '<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] '
        '/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>',
        '<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>',
        f'<< /Length {len(content.encode("latin-1"))} >>\nstream\n{content}\nendstream',
    ]
    header = '%PDF-1.4\n'
    body, offsets, pos = '', [], len(header.encode('latin-1'))
    for i, o in enumerate(objs, 1):
        s = f'{i} 0 obj\n{o}\nendobj\n'
        offsets.append(pos)
        pos += len(s.encode('latin-1'))
        body += s
    xref = f'xref\n0 {len(objs)+1}\n0000000000 65535 f \n' + \
        ''.join(f'{o:010d} 00000 n \n' for o in offsets)
    trailer = (f'trailer\n<< /Size {len(objs)+1} /Root 1 0 R >>\n'
               f'startxref\n{pos}\n%%EOF\n')
    with open(path, 'wb') as f:
        f.write((header + body + xref + trailer).encode('latin-1'))


def main():
    os.makedirs(LIB, exist_ok=True)
    preprint = ['GNN Screening of Perovskite Catalysts',
                'Smith, J., Lee, K., Wang, M.',
                'arXiv:2201.00001 preprint, 2021',
                'We screen perovskite catalysts with graph neural networks.']
    published = ['GNN Screening of Perovskite Catalysts',
                 'Smith, J., Lee, K., Wang, M.',
                 'Nature Energy, 2022. DOI 10.1038/s41560-022-0001-x',
                 'Published version of the arXiv preprint 2201.00001.']
    si = ['Supplementary Information for GNN Screening of Perovskite Catalysts',
          'Smith, J., Lee, K., Wang, M.',
          'Nature Energy, 2022', 'Additional tables and figures.']
    review = ['Advances in Quantum Dot Photovoltaics',
              'Chen, L., Garcia, P.',
              'Chemical Reviews, 2020. DOI 10.1021/acs.chemrev.00002',
              'A review of quantum dot solar cells.']
    thesis = ['Solid-State Battery Interface Engineering',
              'Zhang, W.',
              'PhD Thesis, Tsinghua University, 2023',
              'Interface engineering for solid-state batteries.']

    make_pdf(os.path.join(LIB, 'arxiv_2201.00001.pdf'), preprint)
    make_pdf(os.path.join(LIB, 'Nature-Energy-2022-GNN-perovskite.pdf'), published)
    make_pdf(os.path.join(LIB, 'SI-GNN-perovskite.pdf'), si)
    make_pdf(os.path.join(LIB, '01-quantum-dots-review.pdf'), review)
    make_pdf(os.path.join(LIB, 'quantum dots review final.pdf'), review)  # byte-identical duplicate
    make_pdf(os.path.join(LIB, 'thesis-final-v3.pdf'), thesis)
    make_pdf(os.path.join(LIB, 'thesis-copy-again.pdf'), thesis)  # byte-identical duplicate
    with open(os.path.join(LIB, 'corrupt-scan.pdf'), 'wb') as f:
        f.write(b'%PDF-1.4\n1 0 obj <<truncated garbage without trailer')
    make_pdf(os.path.join(LIB, 'old-scanned-article.pdf'), [], text=False)
    make_pdf(os.path.join(LIB, 'no-permission.pdf'),
             ['Locked Away Report', 'Doe, J.', 'Internal preprint, 2019'])
    os.chmod(os.path.join(LIB, 'no-permission.pdf'), 0)

    with open(os.path.join(LIB, 'data-perovskite-bandgaps.csv'), 'w', encoding='utf-8') as f:
        f.write('material,bandgap_ev\nMAPbI3,1.55\nFAPbI3,1.48\nCsPbI3,1.73\n')
    with open(os.path.join(LIB, 'meta.csv'), 'w', encoding='utf-8') as f:
        f.write('file,title,year,doi\n'
                'Nature-Energy-2022-GNN-perovskite.pdf,GNN Screening of Perovskite Catalysts,2022,10.1038/s41560-022-0001-x\n'
                '01-quantum-dots-review.pdf,Advances in Quantum Dot Photovoltaics,2020,10.1021/acs.chemrev.00002\n')
    with open(os.path.join(LIB, 'notes-版本说明.md'), 'w', encoding='utf-8') as f:
        f.write('# 管理员版本说明\n\n'
                '- arxiv_2201.00001.pdf 是预印本；Nature-Energy-2022-GNN-perovskite.pdf 是同一工作的正式版，'
                '正式版为准（canonical）。\n'
                '- SI-GNN-perovskite.pdf 是正式版的补充材料。\n'
                '- quantum dots review final.pdf 与 01-quantum-dots-review.pdf 是重复下载，保留前者路径下的任意一份即可。\n'
                '- thesis-copy-again.pdf 是 thesis-final-v3.pdf 的重复下载。\n'
                '- old-scanned-article.pdf 无文本层，需要 OCR；corrupt-scan.pdf 已损坏。\n')

    import json
    case = {
        'case_id': 'case-synthetic-demo-a',
        'task': '整理资料库：清点全部文件，识别重复与版本关系，按 类型/年份 目录归档，按 作者-年份-标题 规则重命名，回答检索问题，输出清单与操作记录。',
        'library_dir': 'library',
        'target_structure': '按 文献类型/年份 两级目录组织',
        'naming_template': '{authors}-{year}-{title}',
        'questions': [
            {'qid': 'Q1', 'text': 'GNN 钙钛矿筛选论文的正式版是哪一份文件？'},
            {'qid': 'Q2', 'text': '资料库中哪几份文件是重复下载？'},
            {'qid': 'Q3', 'text': '无法解析或无权限的文件有哪些？'}],
        'output_contract': ['case_id', 'status', 'library_index', 'operations_log',
                            'version_relations', 'skipped', 'answers', 'sources',
                            'uncertainties', 'change_log'],
    }
    with open(os.path.join(FIX, 'input', 'case.json'), 'w', encoding='utf-8') as f:
        json.dump(case, f, ensure_ascii=False, indent=2)
    with open(os.path.join(FIX, 'input', 'task.md'), 'w', encoding='utf-8') as f:
        f.write('### 案例：科研资料库整理（合成示例）\n\n'
                '要求：1. 清点全部文件并逐一说明状态；2. 识别重复下载与版本关系，不删除任何文件；\n'
                '3. 按 文献类型/年份 归档到 library，文件名 {authors}-{year}-{title}；\n'
                '4. 回答 case.json 中的检索问题；5. 交付清单、操作日志与 result.json。\n')
    print(f'fixture written to {FIX}/input ({len(os.listdir(LIB))} library files)')


if __name__ == '__main__':
    main()
