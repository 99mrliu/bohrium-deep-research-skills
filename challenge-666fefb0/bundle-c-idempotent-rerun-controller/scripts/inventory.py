#!/usr/bin/env python3
"""inventory.py — read-only inventory + field-level metadata candidate extraction.

Every candidate metadata value carries (layer, evidence) so the model never has
to invent: it confirms, corrects with verbatim evidence, or marks unknown.
Stdlib only; uses pdftotext when available, degrades honestly otherwise.
"""
import csv
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys

DOI_RE = re.compile(r'10\.\d{4,9}/[^\s"\'<>)\]]+')
YEAR_RE = re.compile(r'\b(19|20)\d{2}\b')
SIDECAR_EXT = {'.md', '.txt', '.csv', '.json', '.bib', '.ris', '.yml', '.yaml'}
TEXT_EXT = SIDECAR_EXT | {'.log', '.xml', '.tsv', '.html', '.htm'}
MAX_EXTRACT = 20000

CASE_ID_KEYS = ['case_id', 'caseId', 'id', 'name']
LIB_KEYS = ['library_dir', 'library', 'input_dir', 'data_dir', 'corpus_dir', 'root', 'materials_dir']
CONTRACT_KEYS = ['output_contract', 'contract', 'output_fields', 'required_fields', 'outputs']
QUESTION_KEYS = ['questions', 'queries', 'search_questions', 'retrieval_questions']
NAMING_KEYS = ['naming_template', 'naming', 'filename_template']
STRUCT_KEYS = ['target_structure', 'directory_structure', 'structure']


def read_json(path):
    with open(path, encoding='utf-8', errors='replace') as f:
        return json.load(f)


def write_json(path, obj):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def sha256_of(path, block=1 << 20):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(block), b''):
            h.update(chunk)
    return h.hexdigest()


def first_key(d, keys):
    if not isinstance(d, dict):
        return None
    for k in keys:
        if k in d and d[k] not in (None, ''):
            return d[k]
    return None


def parse_case(input_dir):
    """Defensive case.json/task.md parsing. Never assume field names."""
    case_path = os.path.join(input_dir, 'case.json')
    case = {}
    parse_notes = []
    if os.path.isfile(case_path):
        try:
            case = read_json(case_path)
        except Exception as e:  # noqa: BLE001
            parse_notes.append(f'case.json parse error: {e}')
    else:
        candidates = [p for p in os.listdir(input_dir) if p.endswith('.json')] if os.path.isdir(input_dir) else []
        if candidates:
            case_path = os.path.join(input_dir, sorted(candidates)[0])
            try:
                case = read_json(case_path)
                parse_notes.append(f'case.json not found; used {os.path.basename(case_path)}')
            except Exception as e:  # noqa: BLE001
                parse_notes.append(f'fallback case parse error: {e}')
        else:
            parse_notes.append('no case.json found')
    task_path = os.path.join(input_dir, 'task.md')
    task_text = ''
    if os.path.isfile(task_path):
        with open(task_path, encoding='utf-8', errors='replace') as f:
            task_text = f.read()
    case_id = first_key(case, CASE_ID_KEYS) or os.path.splitext(os.path.basename(case_path))[0]
    lib = first_key(case, LIB_KEYS)
    if isinstance(lib, str) and not os.path.isabs(lib):
        lib = os.path.join(input_dir, lib)
    if not (isinstance(lib, str) and os.path.isdir(lib)):
        for guess in ('library', 'materials', 'files', 'data'):
            g = os.path.join(input_dir, guess)
            if os.path.isdir(g):
                lib = g
                parse_notes.append(f'library dir guessed: {guess}/')
                break
        else:
            lib = input_dir
            parse_notes.append('library dir fallback: whole /input')
    contract = first_key(case, CONTRACT_KEYS)
    if isinstance(contract, dict):
        contract = list(contract.keys())
    if not isinstance(contract, list):
        contract = []
    contract = [str(x) for x in contract]
    questions = first_key(case, QUESTION_KEYS) or []
    norm_q = []
    for i, q in enumerate(questions):
        if isinstance(q, dict):
            norm_q.append({'qid': str(q.get('qid') or q.get('id') or f'Q{i+1}'),
                           'text': str(q.get('text') or q.get('question') or q.get('q') or '')})
        else:
            norm_q.append({'qid': f'Q{i+1}', 'text': str(q)})
    return {
        'case_id': str(case_id), 'library_dir': lib, 'output_contract': contract,
        'questions': norm_q, 'task_text': task_text,
        'naming_template': str(first_key(case, NAMING_KEYS) or '{authors}-{year}-{title}'),
        'target_structure': str(first_key(case, STRUCT_KEYS) or 'type/year two-level'),
        'parse_notes': parse_notes, 'raw_case_path': case_path,
    }


def sniff_kind(path, head):
    if head.startswith(b'%PDF'):
        return 'pdf'
    if head.startswith(b'PK\x03\x04'):
        return 'zip-container'
    ext = os.path.splitext(path)[1].lower()
    if ext in TEXT_EXT:
        return 'text'
    try:
        head.decode('utf-8')
        return 'text'
    except UnicodeDecodeError:
        return 'binary'


def pdf_text(path, max_pages=3):
    """Return (text, status). status: ok | no_text_layer | extract_error | extract_unavailable"""
    tool = shutil.which('pdftotext')
    if not tool:
        return '', 'extract_unavailable'
    try:
        p = subprocess.run([tool, '-f', '1', '-l', str(max_pages), '-layout', path, '-'],
                           capture_output=True, timeout=60)
        if p.returncode != 0:
            return '', 'extract_error'
        text = p.stdout.decode('utf-8', errors='replace')
        if len(text.strip()) < 20:
            return text, 'no_text_layer'
        return text, 'ok'
    except Exception:  # noqa: BLE001
        return '', 'extract_error'


def field(value, layer, evidence):
    return {'value': value, 'layer': layer, 'evidence': evidence}


def candidates_from_text(text):
    """Heuristic candidates from extracted text; each with verbatim evidence line."""
    out = {'title': None, 'authors': None, 'year': None, 'venue': None, 'doi': None}
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if lines:
        out['title'] = field(lines[0][:200], 'pdf_text', lines[0][:200])
    if len(lines) > 1 and re.search(r'[A-Za-z]', lines[1]) and (',' in lines[1] or ' and ' in lines[1].lower()):
        out['authors'] = field(lines[1][:200], 'pdf_text', lines[1][:200])
    m = DOI_RE.search(text)
    if m:
        val = m.group(0).rstrip('.,;')
        ln = next((l.strip() for l in lines if val in l), val)
        out['doi'] = field(val, 'pdf_text', ln[:200])
    m = YEAR_RE.search(text)
    if m:
        ln = next((l.strip() for l in lines if m.group(0) in l), m.group(0))
        out['year'] = field(m.group(0), 'pdf_text', ln[:200])
    for ln in lines[1:6]:
        if re.search(r'(journal|proceedings|transactions|review|letters|science|nature|conference|preprint|arxiv)', ln, re.I):
            out['venue'] = field(ln[:200], 'pdf_text', ln[:200])
            break
    return out


def candidates_from_filename(rel):
    stem = os.path.splitext(os.path.basename(rel))[0]
    out = {'title': None, 'authors': None, 'year': None, 'venue': None, 'doi': None}
    m = YEAR_RE.search(stem)
    if m:
        out['year'] = field(m.group(0), 'filename', stem)
    cleaned = re.sub(r'[-_]+', ' ', stem).strip()
    if cleaned:
        out['title'] = field(cleaned[:200], 'filename', stem)
    m = DOI_RE.search(stem)
    if m:
        out['doi'] = field(m.group(0), 'filename', stem)
    return out


def merge_candidates(primary, fallback):
    merged = {}
    for k in ('title', 'authors', 'year', 'venue', 'doi'):
        merged[k] = primary.get(k) or fallback.get(k) or {'value': 'unknown', 'layer': None, 'evidence': None}
    return merged


def run_inventory(input_dir, work_dir, out_dir):
    case = parse_case(input_dir)
    os.makedirs(work_dir, exist_ok=True)
    os.makedirs(os.path.join(work_dir, 'extracted'), exist_ok=True)
    os.makedirs(out_dir, exist_ok=True)
    write_json(os.path.join(work_dir, 'case_meta.json'), case)

    records, sidecars = [], []
    lib = case['library_dir']
    all_paths = []
    for root, dirs, files in os.walk(lib):
        dirs.sort()
        for fn in sorted(files):
            all_paths.append(os.path.join(root, fn))
    for i, path in enumerate(all_paths):
        rel = os.path.relpath(path, lib)
        fid = f'F{i+1:03d}'
        rec = {'fid': fid, 'rel': rel, 'size': None, 'sha256': None, 'readable': True,
               'kind': None, 'extract_status': None, 'err': None}
        try:
            rec['size'] = os.path.getsize(path)
            rec['sha256'] = sha256_of(path)
            with open(path, 'rb') as f:
                head = f.read(4096)
        except PermissionError as e:
            rec.update(readable=False, kind='unknown', extract_status='permission_denied', err=str(e))
            records.append(rec)
            continue
        except OSError as e:
            rec.update(readable=False, kind='unknown', extract_status='read_error', err=str(e))
            records.append(rec)
            continue
        rec['kind'] = sniff_kind(path, head)
        ext = os.path.splitext(path)[1].lower()
        if ext in SIDECAR_EXT:
            try:
                with open(path, encoding='utf-8', errors='replace') as f:
                    content = f.read(MAX_EXTRACT)
                rec['extract_status'] = 'ok'
                rows = None
                if ext == '.csv':
                    try:
                        rows = list(csv.DictReader(io.StringIO(content)))
                    except Exception:  # noqa: BLE001
                        rows = None
                sidecars.append({'fid': fid, 'rel': rel, 'content_excerpt': content[:2000],
                                 'csv_rows': rows})
            except OSError as e:
                rec['extract_status'] = 'read_error'
                rec['err'] = str(e)
        elif rec['kind'] == 'pdf':
            text, status = pdf_text(path)
            rec['extract_status'] = status
            if text:
                with open(os.path.join(work_dir, 'extracted', f'{fid}.txt'), 'w', encoding='utf-8') as f:
                    f.write(text[:MAX_EXTRACT])
                rec['head_text'] = text[:1500]
        elif rec['kind'] == 'text':
            try:
                with open(path, encoding='utf-8', errors='replace') as f:
                    text = f.read(MAX_EXTRACT)
                rec['extract_status'] = 'ok'
                with open(os.path.join(work_dir, 'extracted', f'{fid}.txt'), 'w', encoding='utf-8') as f:
                    f.write(text[:MAX_EXTRACT])
                rec['head_text'] = text[:1500]
            except OSError as e:
                rec['extract_status'] = 'read_error'
                rec['err'] = str(e)
        else:
            rec['extract_status'] = 'binary_no_extract'
        records.append(rec)

    with open(os.path.join(work_dir, 'files.jsonl'), 'w', encoding='utf-8') as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + '\n')
    write_json(os.path.join(work_dir, 'sidecars.json'), sidecars)

    groups = {}
    for rec in records:
        if rec.get('sha256'):
            groups.setdefault(rec['sha256'], []).append(rec['fid'])
    aliases = [{'sha256': k, 'fids': v, 'note': 'byte-identical duplicate downloads'}
               for k, v in groups.items() if len(v) > 1]
    write_json(os.path.join(work_dir, 'aliases.json'), aliases)

    meta_cand = {}
    for rec in records:
        text_cand = {'title': None, 'authors': None, 'year': None, 'venue': None, 'doi': None}
        ext_path = os.path.join(work_dir, 'extracted', f"{rec['fid']}.txt")
        if os.path.isfile(ext_path):
            with open(ext_path, encoding='utf-8', errors='replace') as f:
                text_cand = candidates_from_text(f.read())
        meta_cand[rec['fid']] = merge_candidates(text_cand, candidates_from_filename(rec['rel']))
    write_json(os.path.join(work_dir, 'meta_candidates.json'), meta_cand)

    lines = ['# Decision digest (auto-generated, verify against extracted/*.txt)', '',
             f"case_id: {case['case_id']}", f"library: {lib} ({len(records)} files)",
             f"target_structure: {case['target_structure']}",
             f"naming_template: {case['naming_template']}", '',
             '| fid | rel | size | sha256[:12] | kind | extract | title candidate |', '|---|---|---|---|---|---|---|']
    for rec in records:
        t = meta_cand[rec['fid']]['title']['value']
        lines.append('| {} | {} | {} | {} | {} | {} | {} |'.format(
            rec['fid'], rec['rel'], rec['size'], (rec['sha256'] or '')[:12],
            rec['kind'], rec['extract_status'], str(t)[:60]))
    if aliases:
        lines += ['', '## Byte-identical duplicate groups'] + [str(a['fids']) for a in aliases]
    if sidecars:
        lines += ['', '## Sidecar files (READ THEM — may contain admin version notes)'] + \
                 [f"- {s['rel']} (fid {s['fid']})" for s in sidecars]
    if case['questions']:
        lines += ['', '## Retrieval questions'] + [f"- {q['qid']}: {q['text']}" for q in case['questions']]
    with open(os.path.join(work_dir, 'decision_digest.md'), 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines) + '\n')
    return case, records, aliases


if __name__ == '__main__':
    inp, work, out = sys.argv[1], sys.argv[2], sys.argv[3]
    case, records, aliases = run_inventory(inp, work, out)
    print(json.dumps({'case_id': case['case_id'], 'files': len(records),
                      'alias_groups': len(aliases)}, ensure_ascii=False))
