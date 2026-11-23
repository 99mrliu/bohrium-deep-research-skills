#!/usr/bin/env python3
"""freeze_data.py — snapshot source data files into the output tree with
sha256 provenance, so the figure is always traceable to an exact data version
(stdlib only).

Usage:
  python3 freeze_data.py --inputs file1.csv file2.tsv --outdir DIR
Writes DIR/<basename> copies and DIR/data_provenance.json.
"""
import argparse
import hashlib
import json
import os
import shutil
import sys


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--inputs', nargs='+', required=True)
    ap.add_argument('--outdir', required=True)
    args = ap.parse_args()

    os.makedirs(args.outdir, exist_ok=True)
    records, failures = [], []
    for src in args.inputs:
        if not os.path.isfile(src):
            failures.append({'input': src, 'error': 'file not found'})
            continue
        base = os.path.basename(src)
        dst = os.path.join(args.outdir, base)
        if os.path.abspath(src) != os.path.abspath(dst):
            shutil.copyfile(src, dst)
        records.append({'source_path': os.path.abspath(src),
                        'snapshot_file': base,
                        'sha256': sha256_of(dst),
                        'bytes': os.path.getsize(dst)})
    prov = {'status': 'ok' if records and not failures else
            ('partial' if records else 'failed'),
            'files': records, 'failures': failures}
    with open(os.path.join(args.outdir, 'data_provenance.json'), 'w',
              encoding='utf-8') as f:
        json.dump(prov, f, ensure_ascii=False, indent=2)
    print(json.dumps(prov, ensure_ascii=False))
    sys.exit(0 if records else 1)


if __name__ == '__main__':
    main()
