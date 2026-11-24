#!/usr/bin/env python3
"""make_fixture.py — generate the SYNTHETIC example fixture (16 files, 8 anomaly classes).

合成示例：所有文件与元数据均为演示数据，非正式案例、非真实文献。
"""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
FIX = os.path.join(HERE, 'fixture')
LIB = os.path.join(FIX, 'input', 'library')


def esc(s):
    return s.replace('\\', '\\\\').replace('(', '\\(').replace(')', '\\)')


def write_pdf(path, objs, trailer_extra=''):
    header = '%PDF-1.4\n'
    body, offsets, pos = '', [], len(header.encode('latin-1'))
    for i, o in enumerate(objs, 1):
        s = f'{i} 0 obj\n{o}\nendobj\n'
        offsets.append(pos)
        pos += len(s.encode('latin-1'))
        body += s
    xref = f'xref\n0 {len(objs)+1}\n0000000000 65535 f \n' + \
        ''.join(f'{o:010d} 00000 n \n' for o in offsets)
    trailer = (f'trailer\n<< /Size {len(objs)+1} /Root 1 0 R{trailer_extra} >>\n'
               f'startxref\n{pos}\n%%EOF\n')
    with open(path, 'wb') as f:
        f.write((header + body + xref + trailer).encode('latin-1'))


def make_pdf(path, lines, text=True, encrypt=False):
    if text:
        content = 'BT /F1 12 Tf 72 760 Td 16 TL\n' + '\n'.join(
            f'({esc(l)}) Tj T*' for l in lines) + '\nET'
    else:
        content = '0.2 0.5 0.8 rg 72 700 300 60 re f'
    objs = [
        '<< /Type /Catalog /Pages 2 0 R >>',
        '<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
        '<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] '
        '/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>',
        '<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>',
        f'<< /Length {len(content.encode("latin-1"))} >>\nstream\n{content}\nendstream',
    ]
    extra = ''
    if encrypt:
        objs.append('<< /Filter /Standard /V 1 /R 3 /Length 40 /P -4 '
                    '/O (AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA) /U (BBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB) >>')
        extra = ' /Encrypt 6 0 R /ID [(aa)(bb)]'
    write_pdf(path, objs, extra)


def main():
    os.makedirs(LIB, exist_ok=True)
    preprint = ['GNN Screening of Perovskite Catalysts', 'Smith, J., Lee, K., Wang, M.',
                'arXiv:2201.00001 preprint, 2021', 'We screen perovskite catalysts with GNNs.']
    published = ['GNN Screening of Perovskite Catalysts', 'Smith, J., Lee, K., Wang, M.',
                 'Nature Energy, 2022. DOI 10.1038/s41560-022-0001-x',
                 'Published version of the arXiv preprint 2201.00001.']
    review = ['Advances in Quantum Dot Photovoltaics', 'Chen, L., Garcia, P.',
              'Chemical Reviews, 2020. DOI 10.1021/acs.chemrev.00002', 'A review.']
    thesis = ['Solid-State Battery Interface Engineering', 'Zhang, W.',
              'PhD Thesis, Tsinghua University, 2023', 'Interface engineering.']

    make_pdf(os.path.join(LIB, 'arxiv_2201.00001.pdf'), preprint)
    make_pdf(os.path.join(LIB, 'Nature-Energy-2022-GNN-perovskite.pdf'), published)
    make_pdf(os.path.join(LIB, 'SI-GNN-perovskite.pdf'),
             ['Supplementary Information for GNN Screening of Perovskite Catalysts',
              'Smith, J., Lee, K., Wang, M.', 'Nature Energy, 2022'])
    make_pdf(os.path.join(LIB, '01-quantum-dots-review.pdf'), review)
    make_pdf(os.path.join(LIB, 'quantum dots review final.pdf'), review)      # duplicate
    make_pdf(os.path.join(LIB, 'thesis-final-v3.pdf'), thesis)
    make_pdf(os.path.join(LIB, 'thesis-copy-again.pdf'), thesis)              # duplicate
    with open(os.path.join(LIB, 'corrupt-scan.pdf'), 'wb') as f:              # corrupt_pdf
        f.write(b'%PDF-1.4\n1 0 obj <<truncated garbage without trailer')
    make_pdf(os.path.join(LIB, 'encrypted-report.pdf'),                       # encrypted_pdf
             ['Secret Report', 'Doe, J.', 'Internal, 2019'], encrypt=True)
    make_pdf(os.path.join(LIB, 'old-scanned-article.pdf'), [], text=False)    # no_text_layer
    make_pdf(os.path.join(LIB, 'no-permission.pdf'),                          # permission_denied
             ['Locked Away Report', 'Doe, J.', 'Internal preprint, 2019'])
    os.chmod(os.path.join(LIB, 'no-permission.pdf'), 0)
    with open(os.path.join(LIB, 'empty-download.pdf'), 'wb') as f:            # empty_file
        pass
    with open(os.path.join(LIB, 'legacy-gbk-notes.txt'), 'wb') as f:          # garbled_encoding
        f.write('文献整理记录：量子点综述需要更新版本，预印本与正式版要区分。\n'.encode('gbk') * 5)
    with open(os.path.join(LIB, 'data-perovskite-bandgaps.csv'), 'w', encoding='utf-8') as f:
        f.write('material,bandgap_ev\nMAPbI3,1.55\nFAPbI3,1.48\n')
    with open(os.path.join(LIB, 'meta.csv'), 'w', encoding='utf-8') as f:
        f.write('file,title,year,doi\n'
                'Nature-Energy-2022-GNN-perovskite.pdf,GNN Screening of Perovskite Catalysts,2022,10.1038/s41560-022-0001-x\n')
    with open(os.path.join(LIB, 'notes-版本说明.md'), 'w', encoding='utf-8') as f:
        f.write('# 管理员版本说明\n\n'
                '- arxiv_2201.00001.pdf 是预印本；Nature-Energy-2022-GNN-perovskite.pdf 是正式版，正式版为准。\n'
                '- quantum dots review final.pdf 与 01-quantum-dots-review.pdf 是重复下载。\n'
                '- thesis-copy-again.pdf 是 thesis-final-v3.pdf 的重复下载。\n'
                '- encrypted-report.pdf 有密码；old-scanned-article.pdf 需 OCR；legacy-gbk-notes.txt 是 GBK 编码。\n')

    case = {
        'case_id': 'case-synthetic-demo-e',
        'task': '整理资料库：清点全部文件，识别异常与重复，健康文件按 类型/年份 归档，异常文件隔离保留，回答检索问题，输出清单与操作记录。',
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
                '要求：1. 全部文件分诊并逐一说明状态；2. 健康文件归档，异常文件隔离保留；\n'
                '3. 识别重复下载；4. 回答检索问题；5. 交付清单、分诊报告与 result.json。\n')
    print(f'fixture written to {FIX}/input ({len(os.listdir(LIB))} library files)')


if __name__ == '__main__':
    main()
