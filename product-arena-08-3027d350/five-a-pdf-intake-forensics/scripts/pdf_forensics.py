#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pdf_forensics.py — 纯标准库 PDF 结构取证（bundle A: pdf-intake-forensics）

在任何解析之前回答："这份 PDF 能不能解析、哪部分能、该走哪条路"。
直接读原始字节：正则扫描间接对象、zlib 解压 FlateDecode 流，不依赖任何第三方库。
有 PyMuPDF 时交叉验证页数与每页文本字符数，差异记入 crosscheck 字段。

用法:
    python3 pdf_forensics.py <file.pdf> [-o forensics.json]

退出码: 0=成功(ok) 2=部分(partial，如截尾/加密/解压失败但仍有产出) 3=失败(非 PDF 或完全不可读)
"""
import argparse
import datetime
import json
import os
import re
import sys
import zlib

EXIT_OK = 0
EXIT_PARTIAL = 2
EXIT_FAIL = 3

# ---- 阈值常量（与 SKILL.md「方法要点」保持一致，改动须同步） ----
TAIL_WINDOW = 1024   # 在文件尾此字节窗口内寻找 %%EOF
HEAD_WINDOW = 1024   # 在文件头此字节窗口内寻找 /Linearized

HEADER_RE = re.compile(rb'%PDF-(\d+\.\d+)')
OBJ_RE = re.compile(rb'(\d+)\s+(\d+)\s+obj\b')
STR_RE = rb'\((?:\\.|[^\\()])*\)'          # PDF 字面字符串（含转义）
REF_RE = rb'(\d+)\s+(\d+)\s+R'


# ---------------------------------------------------------------------------
# 底层工具
# ---------------------------------------------------------------------------

def find_objects(data):
    """正则扫描全部间接对象。返回 {num: body_bytes}（同号取首次出现）与出现顺序。"""
    objs = {}
    order = []
    for m in OBJ_RE.finditer(data):
        num = int(m.group(1))
        end = data.find(b'endobj', m.end())
        body = data[m.end():end] if end != -1 else data[m.end():]
        if num not in objs:
            objs[num] = body
            order.append(num)
    return objs, order


def read_balanced_dict(buf, pos):
    """从 buf[pos:pos+2]==b'<<' 起做括号配平，返回整段字典字节（截尾时返回到文件尾）。"""
    depth = 0
    i = pos
    n = len(buf)
    while i < n - 1:
        two = buf[i:i + 2]
        if two == b'<<':
            depth += 1
            i += 2
            continue
        if two == b'>>':
            depth -= 1
            i += 2
            if depth == 0:
                return buf[pos:i]
            continue
        i += 1
    return buf[pos:]


def get_ref(body, key):
    m = re.search(rb'/' + re.escape(key) + rb'\s+' + REF_RE, body)
    return int(m.group(1)) if m else None


def get_ref_array(body, key):
    m = re.search(rb'/' + re.escape(key) + rb'\s*\[([^\]]*)\]', body, re.S)
    if not m:
        single = get_ref(body, key)
        return [single] if single is not None else []
    return [int(x) for x in re.findall(rb'(\d+)\s+\d+\s+R', m.group(1))]


def get_dict_or_ref(body, key, objs):
    """返回 (dict_bytes|referenced_body|None, ref|None)。"""
    m = re.search(rb'/' + re.escape(key) + rb'\s*', body)
    if not m:
        return None, None
    rest = body[m.end():]
    if rest[:2] == b'<<':
        return read_balanced_dict(rest, 0), None
    m2 = re.match(REF_RE, rest)
    if m2:
        ref = int(m2.group(1))
        return objs.get(ref), ref
    return None, None


def get_name(body, key):
    m = re.search(rb'/' + re.escape(key) + rb'\s*/([^\s/<>\[\]()]+)', body)
    return m.group(1).decode('latin-1') if m else None


def get_int(body, key):
    m = re.search(rb'/' + re.escape(key) + rb'\s+(-?\d+)', body)
    return int(m.group(1)) if m else None


def get_box(body, key=b'MediaBox'):
    m = re.search(rb'/' + re.escape(key) + rb'\s*\[([^\]]*)\]', body)
    if not m:
        return None
    try:
        return [float(x) for x in m.group(1).split()][:4]
    except ValueError:
        return None


def unescape_literal(raw):
    out = bytearray()
    i = 0
    while i < len(raw):
        c = raw[i:i + 1]
        if c == b'\\' and i + 1 < len(raw):
            nxt = raw[i + 1:i + 2]
            out += {b'n': b'\n', b'r': b'\r', b't': b'\t',
                    b'(': b'(', b')': b')', b'\\': b'\\'}.get(nxt, nxt)
            i += 2
        else:
            out += c
            i += 1
    return bytes(out)


def get_string(body, key):
    m = re.search(rb'/' + re.escape(key) + rb'\s*\(((?:\\.|[^\\()])*)\)', body, re.S)
    if m:
        return unescape_literal(m.group(1)).decode('latin-1')
    m = re.search(rb'/' + re.escape(key) + rb'\s*<([0-9A-Fa-f\s]+)>', body)
    if m:
        try:
            raw = bytes.fromhex(re.sub(rb'\s+', b'', m.group(1)).decode('ascii'))
            return raw.decode('utf-16-be', errors='replace') if raw.startswith(b'\xfe\xff') \
                else raw.decode('latin-1')
        except ValueError:
            return None
    return None


def extract_stream(body):
    """返回 (raw_stream_bytes, dict_part_bytes)；无 stream 返回 (None, body)。"""
    si = body.find(b'stream')
    if si == -1:
        return None, body
    dstart = si + 6
    if body[dstart:dstart + 2] == b'\r\n':
        dstart += 2
    elif body[dstart:dstart + 1] in (b'\n', b'\r'):
        dstart += 1
    ei = body.find(b'endstream', dstart)
    raw = body[dstart:ei] if ei != -1 else body[dstart:]
    return raw, body[:si]


def decode_stream(raw, dict_part):
    """按 /Filter 链解码。返回 (data, filters, errors)。"""
    filters = []
    m = re.search(rb'/Filter\s*(\[[^\]]*\]|/[A-Za-z0-9]+)', dict_part)
    if m:
        filters = [f for f in re.findall(rb'/([A-Za-z0-9]+)', m.group(1))]
    data = raw
    errors = []
    for f in filters:
        if f in (b'FlateDecode', b'Fl'):
            try:
                data = zlib.decompress(data)
            except zlib.error:
                try:
                    data = zlib.decompress(data.strip())
                except zlib.error as e:
                    errors.append('flate_error: %s' % e)
                    return data, filters, errors
        elif f in (b'ASCIIHexDecode', b'AHx'):
            hexs = re.sub(rb'\s+', b'', data).rstrip(b'>')
            if len(hexs) % 2:
                hexs += b'0'
            try:
                data = bytes.fromhex(hexs.decode('ascii'))
            except (ValueError, UnicodeDecodeError) as e:
                errors.append('asciihex_error: %s' % e)
                return data, filters, errors
        else:
            errors.append('unsupported_filter: %s' % f.decode('latin-1'))
    return data, filters, errors


def count_text_bytes(content):
    """统计内容流中 Tj / TJ 文本绘制操作的字面字符串字节数（ forensic 近似值）。"""
    total = 0
    ops = 0
    for m in re.finditer(rb'(' + STR_RE + rb')\s*Tj', content):
        total += len(m.group(1)) - 2
        ops += 1
    for m in re.finditer(rb'\[(.*?)\]\s*TJ', content, re.S):
        for sm in re.finditer(STR_RE, m.group(1)):
            total += len(sm.group(0)) - 2
        ops += 1
    return total, ops


# ---------------------------------------------------------------------------
# 结构分析
# ---------------------------------------------------------------------------

def check_xref(data):
    tail = data[-TAIL_WINDOW:]
    idx = data.rfind(b'startxref')
    eof_count = data.count(b'%%EOF')
    result = {
        'startxref_found': idx != -1,
        'startxref_offset': None,
        'startxref_points_to_xref': None,
        'trailer_eof_in_tail': b'%%EOF' in tail,
        'eof_marker_count': eof_count,
        'prev_count': len(re.findall(rb'/Prev\s', data)),
        'incremental_update': eof_count > 1 or bool(re.search(rb'/Prev\s', data)),
        'xref_ok': False,
        'truncated': False,
    }
    if idx == -1:
        result['truncated'] = True
        return result
    m = re.match(rb'startxref\s*(\d+)', data[idx:])
    if not m:
        result['truncated'] = True
        return result
    off = int(m.group(1))
    result['startxref_offset'] = off
    points_ok = False
    if off < len(data):
        if data[off:off + 4] == b'xref':
            points_ok = True
        elif re.match(rb'\d+\s+\d+\s+obj', data[off:off + 30]) and b'/XRef' in data[off:off + 400]:
            points_ok = True  # xref 流对象
    result['startxref_points_to_xref'] = points_ok
    result['xref_ok'] = points_ok and result['trailer_eof_in_tail']
    result['truncated'] = not (result['trailer_eof_in_tail'] and idx != -1)
    return result


def find_catalog_ref(data, objs):
    last_trailer = None
    for m in re.finditer(rb'trailer\s*', data):
        rest = data[m.end():]
        if rest[:2] == b'<<':
            last_trailer = read_balanced_dict(rest, 0)
    if last_trailer:
        ref = get_ref(last_trailer, b'Root')
        if ref is not None:
            return ref
    for num, body in objs.items():
        if re.search(rb'/Type\s*/Catalog\b', body):
            return num
    return None


def parse_font(body, objs):
    base = get_name(body, b'BaseFont')
    subtype = get_name(body, b'Subtype')
    has_tounicode = b'/ToUnicode' in body
    embedded = False
    fd = get_ref(body, b'FontDescriptor')
    fd_body = objs.get(fd) if fd is not None else None
    if fd_body:
        embedded = b'/FontFile' in fd_body  # 涵盖 FontFile / FontFile2 / FontFile3
    return {
        'base_font': base,
        'subtype': subtype,
        'has_tounicode': has_tounicode,
        'embedded': embedded,
    }


def parse_resources(res_body, objs):
    fonts, images = [], []
    if not res_body:
        return fonts, images
    font_dict, _ = get_dict_or_ref(res_body, b'Font', objs)
    if font_dict:
        for name, ref in re.findall(rb'/([A-Za-z0-9_.\-]+)\s+(\d+)\s+\d+\s+R', font_dict):
            fbody = objs.get(int(ref))
            if fbody is None:
                fonts.append({'resource_name': name.decode('latin-1'), 'object': int(ref),
                              'error': 'font_object_not_scanned'})
                continue
            info = parse_font(fbody, objs)
            info['resource_name'] = name.decode('latin-1')
            info['object'] = int(ref)
            fonts.append(info)
    xo_dict, _ = get_dict_or_ref(res_body, b'XObject', objs)
    if xo_dict:
        for name, ref in re.findall(rb'/([A-Za-z0-9_.\-]+)\s+(\d+)\s+\d+\s+R', xo_dict):
            xbody = objs.get(int(ref))
            if xbody is None:
                continue
            if re.search(rb'/Subtype\s*/Image\b', xbody):
                images.append({
                    'resource_name': name.decode('latin-1'),
                    'object': int(ref),
                    'width': get_int(xbody, b'Width'),
                    'height': get_int(xbody, b'Height'),
                    'bits_per_component': get_int(xbody, b'BitsPerComponent'),
                    'color_space': get_name(xbody, b'ColorSpace'),
                })
    return fonts, images


def collect_pages(data, objs, order, issues):
    pages = []
    visited = set()
    cat_ref = find_catalog_ref(data, objs)
    root_ref = get_ref(objs.get(cat_ref, b''), b'Pages') if cat_ref is not None else None

    def rec(ref, inh_box, inh_rot, inh_res):
        if ref is None or ref in visited or ref not in objs:
            return
        visited.add(ref)
        body = objs[ref]
        box = get_box(body) or inh_box
        rot = get_int(body, b'Rotate')
        rot = rot if rot is not None else inh_rot
        res_body, res_ref = get_dict_or_ref(body, b'Resources', objs)
        res = res_body if res_body is not None else inh_res
        if re.search(rb'/Type\s*/Pages\b', body):
            for kid in get_ref_array(body, b'Kids'):
                rec(kid, box, rot, res)
        elif re.search(rb'/Type\s*/Page\b', body):
            pages.append({'object': ref, 'mediabox': box, 'rotate': rot or 0,
                          '_res': res, '_body': body})

    if root_ref is not None:
        rec(root_ref, None, None, None)
    if not pages:
        # 回退：按对象号顺序扫描（页序不保证，如实记录）
        for num in order:
            body = objs[num]
            if re.search(rb'/Type\s*/Page\b', body):
                res_body, _ = get_dict_or_ref(body, b'Resources', objs)
                pages.append({'object': num, 'mediabox': get_box(body),
                              'rotate': get_int(body, b'Rotate') or 0,
                              '_res': res_body, '_body': body})
        if pages:
            issues.append('page_order_fallback: kids walk failed, pages listed in object-number order')
    return pages


def analyze_page(p, objs):
    body = p['_body']
    fonts, images = parse_resources(p['_res'], objs)
    content_refs = get_ref_array(body, b'Contents')
    text_bytes = 0
    text_ops = 0
    decompress_errors = []
    filters_seen = []
    for ref in content_refs:
        cbody = objs.get(ref)
        if cbody is None:
            decompress_errors.append('content_object_%d_not_scanned' % ref)
            continue
        raw, dict_part = extract_stream(cbody)
        if raw is None:
            continue
        decoded, filters, errors = decode_stream(raw, dict_part)
        filters_seen.extend(f.decode('latin-1') for f in filters)
        decompress_errors.extend('content_obj_%d: %s' % (ref, e) for e in errors)
        tb, ops = count_text_bytes(decoded)
        text_bytes += tb
        text_ops += ops
    return {
        'object': p['object'],
        'mediabox': p['mediabox'],
        'rotate': p['rotate'],
        'content_objects': content_refs,
        'content_filters': sorted(set(filters_seen)),
        'text_showing_bytes': text_bytes,
        'text_showing_ops': text_ops,
        'decompress_errors': decompress_errors,
        'fonts': fonts,
        'image_count': len(images),
        'images': images,
    }


def parse_metadata(data, objs):
    last_trailer = None
    for m in re.finditer(rb'trailer\s*', data):
        rest = data[m.end():]
        if rest[:2] == b'<<':
            last_trailer = read_balanced_dict(rest, 0)
    if not last_trailer:
        return {}
    info_ref = get_ref(last_trailer, b'Info')
    if info_ref is None or info_ref not in objs:
        return {}
    body = objs[info_ref]
    meta = {}
    for key in (b'Producer', b'Creator', b'CreationDate', b'ModDate', b'Title', b'Author'):
        val = get_string(body, key)
        if val is not None:
            meta[key.decode()] = val
    return meta


def crosscheck(path):
    """有 PyMuPDF 时交叉验证页数与每页文本字符数。"""
    mod = None
    try:
        import pymupdf as mod  # noqa: N811
    except ImportError:
        try:
            import fitz as mod  # noqa: N811
        except ImportError:
            return {'engine': None, 'reason': 'pymupdf_not_installed: 标准库结果为唯一依据'}
    try:
        doc = mod.open(path)
    except Exception as e:  # pymupdf 抛出的异常类型多样，取证场景一律如实记录
        return {'engine': 'pymupdf', 'error': 'open_failed: %s: %s' % (type(e).__name__, e)}
    chars = []
    try:
        for page in doc:
            chars.append(len(page.get_text('text')))
    except Exception as e:
        return {'engine': 'pymupdf', 'error': 'read_failed: %s: %s' % (type(e).__name__, e),
                'page_count': doc.page_count}
    finally:
        doc.close()
    return {'engine': 'pymupdf', 'page_count': len(chars), 'chars_per_page': chars}


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------

def analyze(path):
    """返回 (report_dict, exit_code)。可供 textlayer_probe.py 复用。"""
    issues = []
    with open(path, 'rb') as fh:
        data = fh.read()
    report = {
        'tool': 'pdf_forensics.py',
        'pdf_path': os.path.abspath(path),
        'file_size_bytes': len(data),
        'generated_at': datetime.datetime.now().astimezone().isoformat(timespec='seconds'),
        'issues': issues,
    }
    hm = HEADER_RE.search(data[:HEAD_WINDOW])
    if not hm:
        report.update({'status': 'failed', 'failure_reason': 'not_a_pdf: 头部 %PDF-x.y 签名缺失'})
        return report, EXIT_FAIL
    report['pdf_version'] = hm.group(1).decode('ascii')
    report['encrypted'] = bool(re.search(rb'/Encrypt\b', data))
    report['linearized'] = b'/Linearized' in data[:HEAD_WINDOW]
    report['object_count'] = len(OBJ_RE.findall(data))
    report['objstm_count'] = len(re.findall(rb'/Type\s*/ObjStm', data))
    report['xref_stream'] = bool(re.search(rb'/Type\s*/XRef', data))
    report['xref'] = check_xref(data)

    objs, order = find_objects(data)
    report['metadata'] = parse_metadata(data, objs)
    if report['encrypted']:
        issues.append('encrypted: 存在 /Encrypt，内容流与字符串均不可直接解析')
    if report['xref']['truncated']:
        issues.append('truncated: 文件尾缺少完整 startxref/%%EOF，疑似截尾或写入中断')
    if report['xref']['incremental_update']:
        issues.append('incremental_update: 存在多个 %%EOF 或 /Prev，对象可能被后续修订覆盖')
    if report['objstm_count']:
        issues.append('object_streams: 存在 /ObjStm 压缩对象流，标准库扫描看不到其中的对象，计数可能偏低')

    pages = collect_pages(data, objs, order, issues)
    report['page_count'] = len(pages)
    report['pages'] = [analyze_page(p, objs) for p in pages]
    for pg in report['pages']:
        pg.pop('_res', None)
        pg.pop('_body', None)
    if not pages and not report['encrypted']:
        issues.append('no_pages_found: 未扫描到任何 /Type /Page 对象')

    cc = crosscheck(path)
    diffs = []
    if cc.get('page_count') is not None and cc['page_count'] != report['page_count']:
        diffs.append('page_count: stdlib=%d pymupdf=%d' % (report['page_count'], cc['page_count']))
    if cc.get('chars_per_page') is not None:
        for i, chars in enumerate(cc['chars_per_page']):
            if i < len(report['pages']):
                sb = report['pages'][i]['text_showing_bytes']
                if sb == 0 and chars > 0:
                    diffs.append('page %d: stdlib 文本字节=0 但 pymupdf 字符=%d（可能在对象流/非常规编码中）' % (i + 1, chars))
    cc['diffs'] = diffs
    report['crosscheck'] = cc
    if diffs:
        issues.append('crosscheck_diff: ' + '; '.join(diffs))

    if report['encrypted'] or report['xref']['truncated'] or diffs or \
            any(pg['decompress_errors'] for pg in report['pages']):
        report['status'] = 'partial'
        code = EXIT_PARTIAL
    else:
        report['status'] = 'ok'
        code = EXIT_OK
    if report['page_count'] == 0 and not report['encrypted']:
        report['status'] = 'partial' if pages else report['status']
    return report, code


def main(argv=None):
    ap = argparse.ArgumentParser(description='纯标准库 PDF 结构取证')
    ap.add_argument('pdf')
    ap.add_argument('-o', '--out', help='forensics.json 输出路径（缺省打印到 stdout）')
    args = ap.parse_args(argv)
    if not os.path.isfile(args.pdf):
        sys.stderr.write('ERROR: 文件不存在: %s\n' % args.pdf)
        return EXIT_FAIL
    report, code = analyze(args.pdf)
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.out:
        os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
        with open(args.out, 'w', encoding='utf-8') as fh:
            fh.write(text + '\n')
        sys.stderr.write('forensics.json -> %s (status=%s, exit=%d)\n' % (args.out, report.get('status'), code))
    else:
        print(text)
    return code


if __name__ == '__main__':
    sys.exit(main())
