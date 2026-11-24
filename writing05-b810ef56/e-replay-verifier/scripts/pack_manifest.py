#!/usr/bin/env python3
"""核验清单生成器：把 /app/output 的全部可核验承诺固化为一份 manifest。

只依赖标准库。manifest 是"交付方对复核方的承诺表"：产物文件哈希、
逐字摘录、关键数字、参考文献条目、契约键与 case_id。复核方拿到
manifest + 原始来源文本即可用 verify_pack.py 独立重验，不需要
模型参与，也不需要信任交付过程。

用法：
    python3 pack_manifest.py --output-dir OUTPUT_DIR \
        --manifest MANIFEST_JSON [--evidence EVIDENCE_JSON]

EVIDENCE_JSON（可选但强烈建议）结构：
    {"quotes":  [{"id", "source", "quote"}],
     "numbers": [{"id", "source", "value", "context"}],
     "refs":    [{"n", "title", "authors", "year"}]}
source 为来源文本文件名（不含扩展名时的文件名主体）。

退出码：0 = 生成成功；2 = 用法/IO 错误。
"""
import argparse
import hashlib
import json
import os
import sys


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, 'rb') as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--output-dir', required=True)
    ap.add_argument('--manifest', required=True)
    ap.add_argument('--evidence', default=None)
    args = ap.parse_args()

    artifacts = []
    manifest_name = os.path.basename(args.manifest)
    for root, dirs, files in os.walk(args.output_dir):
        dirs.sort()
        for name in sorted(files):
            if name.startswith('.') or name == manifest_name:
                continue
            path = os.path.join(root, name)
            rel = os.path.relpath(path, args.output_dir)
            artifacts.append({'path': rel,
                              'bytes': os.path.getsize(path),
                              'sha256': sha256_of(path)})

    result = {}
    result_path = os.path.join(args.output_dir, 'result.json')
    if os.path.exists(result_path):
        try:
            with open(result_path, encoding='utf-8') as fh:
                result = json.load(fh)
        except (json.JSONDecodeError, UnicodeDecodeError):
            result = {}

    evidence = {'quotes': [], 'numbers': [], 'refs': []}
    if args.evidence:
        with open(args.evidence, encoding='utf-8') as fh:
            loaded = json.load(fh)
        for key in evidence:
            if isinstance(loaded.get(key), list):
                evidence[key] = loaded[key]

    manifest = {
        'manifest_version': '1',
        'case_id': result.get('case_id'),
        'status': result.get('status'),
        'contract_keys': sorted(k for k in result
                                if k not in ('case_id', 'status')),
        'artifacts': artifacts,
        'quotes': evidence['quotes'],
        'numbers': evidence['numbers'],
        'refs': evidence['refs'],
        'note': '本清单由 pack_manifest.py 生成；verify_pack.py 可独立'
                '重验全部条目。哈希覆盖除 manifest 自身外的全部产物。'}
    with open(args.manifest, 'w', encoding='utf-8') as fh:
        json.dump(manifest, fh, ensure_ascii=False, indent=1)
    print(json.dumps({'artifacts': len(artifacts),
                      'quotes': len(evidence['quotes']),
                      'numbers': len(evidence['numbers']),
                      'refs': len(evidence['refs'])},
                     ensure_ascii=False))
    return 0


if __name__ == '__main__':
    sys.exit(main())
