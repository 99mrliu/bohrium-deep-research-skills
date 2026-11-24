#!/usr/bin/env python3
"""term_cohorts.py — build the term-cohort matrix from canon.jsonl.

Usage:
    python3 term_cohorts.py --work DIR [--synonyms FILE]

Term extraction (documented in references/term_normalization.md):
  * text = title + abstract + keywords, lowercased
  * English: tokens [a-z0-9]+; bigrams formed only within punctuation-
    delimited segments (hyphens/spaces act as intra-segment separators)
  * unigrams kept when len>=3 and not a stopword; bigrams kept when both
    parts are non-stopword and len>=2
  * Chinese (when present): keyword strings containing CJK are kept whole,
    plus CJK character bigrams
  * document-frequency filter: a term must occur in >= min_df (default 2)
    distinct documents; falls back to df>=1 with a warning on tiny corpora
  * --synonyms FILE is a JSON object {variant: canonical}; matching terms
    are merged into the canonical form BEFORE counting (this is the
    term-drift defense: renamed vocabulary stays one cohort)

Outputs in DIR (all deterministic, sorted keys):
  term_year_matrix.json  {term: {year: doc_count}}
  year_vectors.json      {year: {term: doc_count}}   (input for phase_segment)
  record_terms.json      {record_id: [terms]}        (input for representative_select)
  top_terms.csv          term,total_df,first_year,last_year
"""
import argparse
import csv
import json
import os
import re
import sys
from collections import defaultdict

STOPWORDS = set("""
a an the and or but if then else when at by for with about against between
into through during before after above below to from up down in out on off
over under again further once here there all any both each few more most
other some such no nor not only own same so than too very can will just
should now is am are was were be been being have has had having do does did
doing would could shall may might must of it its this that these those i you
he she we they them his her their our your my me him us as which who whom
what where why how also using use used via based within across per et al
however while whereas thus therefore hence moreover furthermore additionally
respectively etc novel new propose proposed present presented introduce
introduced paper study work approach technique system framework algorithm
results result show shows shown demonstrate demonstrates experiment
experiments experimental evaluation evaluated performance achieve achieves
achieved state art significantly compared comparison baseline baselines
dataset datasets data task tasks problem problems domain domains various
several many much well often first second one two three among without given
existing previous prior recent real large small high low improve improves
improved improvement effective effectiveness efficient accuracy accurate
better best outperform outperforms sota significant significance different
important key main general specific common wide widely typically usually
particular especially including include includes included provide provides
provided allow allows enable enables make makes made take takes end held out
""".split())

TOKEN_RE = re.compile(r"[a-z0-9]+|[一-鿿]+")
CJK_RE = re.compile(r"[一-鿿]")
SEGMENT_SPLIT = re.compile(r"[.!?;:\n\r\t()\[\]\"“”'‘’、，。；：…—|/\\<>*_`~@#$%^&=+{}\u3000]")


def load_synonyms(path):
    if not path:
        return {}
    with open(path, "r", encoding="utf-8") as fh:
        raw = json.load(fh)
    if not isinstance(raw, dict):
        raise ValueError("synonyms file must be a JSON object {variant: canonical}")
    return {str(k).strip().lower(): str(v).strip().lower()
            for k, v in raw.items() if not str(k).startswith("_")}


def doc_text(rec):
    """The lowercase raw text of a record (used for extraction AND for
    literal synonym-phrase matching)."""
    title = (rec.get("title") or "").lower()
    abstract = (rec.get("abstract") or "").lower()
    kws = [(k or "").strip().lower() for k in (rec.get("keywords") or [])]
    return title + " . " + abstract + " . " + " ; ".join(kws)


def extract_terms(text, kws):
    """Return the raw (pre-synonym) term set from one record's text."""
    terms = set()
    for seg in SEGMENT_SPLIT.split(text):
        toks = TOKEN_RE.findall(seg)
        for t in toks:
            if CJK_RE.search(t):
                continue
            if len(t) >= 3 and t not in STOPWORDS:
                terms.add(t)
        for a, b in zip(toks, toks[1:]):
            if CJK_RE.search(a) or CJK_RE.search(b):
                continue
            if a in STOPWORDS or b in STOPWORDS:
                continue
            if len(a) >= 2 and len(b) >= 2:
                terms.add(a + " " + b)
    for kw in kws:
        if CJK_RE.search(kw) and len(kw) >= 2:
            terms.add(kw)
            for run in re.findall(r"[一-鿿]+", kw):
                terms.update(run[i:i + 2] for i in range(len(run) - 1))
    return terms


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", required=True)
    ap.add_argument("--synonyms", default=None)
    ap.add_argument("--min-df", type=int, default=2)
    args = ap.parse_args()

    canon_path = os.path.join(args.work, "canon.jsonl")
    if not os.path.isfile(canon_path):
        print("ERROR: %s not found; run build_corpus.py first" % canon_path,
              file=sys.stderr)
        return 2
    records = [json.loads(l) for l in open(canon_path, encoding="utf-8") if l.strip()]
    syn = load_synonyms(args.synonyms)

    # per-record canonical term sets (synonym merge happens here). Besides
    # n-gram extraction, every phrase that appears in the synonyms map
    # (variant OR canonical, any length, e.g. the trigram "pretrained
    # language model") is matched LITERALLY against the raw text so that
    # multi-word canonical cohorts are counted even when the tokenizer
    # only emits unigrams+bigrams.
    phrase_probes = {}
    for variant, canonical in syn.items():
        phrase_probes[variant] = canonical
        phrase_probes.setdefault(canonical, canonical)
    rec_terms = {}
    for rec in records:
        text = doc_text(rec)
        kws = [(k or "").strip().lower() for k in (rec.get("keywords") or [])]
        raw = extract_terms(text, kws)
        for phrase in phrase_probes:
            if phrase and phrase in text:
                raw.add(phrase)
        rec_terms[rec["id"]] = {syn.get(t, t) for t in raw}

    # global document frequency
    df = defaultdict(int)
    for terms in rec_terms.values():
        for t in terms:
            df[t] += 1
    keep = {t for t, c in df.items() if c >= args.min_df}
    if not keep and records:
        print("WARN: no term passes min_df=%d; falling back to df>=1"
              % args.min_df, file=sys.stderr)
        keep = set(df)

    term_year = defaultdict(lambda: defaultdict(int))
    year_vec = defaultdict(lambda: defaultdict(int))
    rec_terms_out = {}
    for rec in records:
        terms = sorted(t for t in rec_terms[rec["id"]] if t in keep)
        rec_terms_out[rec["id"]] = terms
        y = rec.get("year")
        if y is None:
            continue
        ys = str(y)
        for t in terms:
            term_year[t][ys] += 1
            year_vec[ys][t] += 1

    def dump(name, obj):
        p = os.path.join(args.work, name)
        with open(p, "w", encoding="utf-8") as fh:
            json.dump(obj, fh, ensure_ascii=False, sort_keys=True, indent=1)
        return p

    dump("term_year_matrix.json", {t: dict(sorted(v.items()))
                                   for t, v in sorted(term_year.items())})
    dump("year_vectors.json", {y: dict(sorted(v.items()))
                               for y, v in sorted(year_vec.items())})
    dump("record_terms.json", dict(sorted(rec_terms_out.items())))

    rows = []
    for t in sorted(keep):
        ys = sorted(int(y) for y in term_year.get(t, {}))
        rows.append((t, df[t], ys[0] if ys else "", ys[-1] if ys else ""))
    rows.sort(key=lambda r: (-r[1], r[0]))
    with open(os.path.join(args.work, "top_terms.csv"), "w",
              encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["term", "total_df", "first_year", "last_year"])
        w.writerows(rows)

    print("term_cohorts: %d records, %d terms kept (df>=%d), %d synonym mappings"
          % (len(records), len(keep), args.min_df, len(syn)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
