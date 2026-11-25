# Reference-style cheat sheet

Annotated examples of what the regexes in `refs_parse.py` capture. All
strings below are synthetic.

## Numbered-bracket style

```
[1] A. Turing, B. Lovelace. On Computable Widgets. Journal of Synthetic Machinery 12, 34–56 (1936).
│   │                     │                       │                              │   │      │
│   │                     │                       │                              │   │      └─ TAIL_BRACKET (?P<year>)
│   │                     │                       │                              │   └─ (?P<pages>)  "34–56"
│   │                     │                       │                              └─ (?P<volume>) "12"
│   │                     │                       └─ (?P<venue>) lazy up to " <vol>,"
│   │                     └─ title: text up to first ". " after authors
│   └─ AUTHORS_RE group 1: initials-first list "A. Turing, B. Lovelace"
└─ BRACKET_START → label = 1

[3] D. Knuth. The Art of Frobnication. Addison-Wesley (1968).
                                            └──────── TAIL_BRACKET_PLAIN: venue + year,
                                                      volume/pages stay null → parsed, confidence 0.75
```

## Author-year style

```
Hopper, G. & Kleene, S. (1952). Recursive widget theory. Annals of Synthetic Mathematics, 54(3), 101-118. https://doi.org/10.1234/synth.1952.54
│                     │       │                        │                              │  │   │
│                     │       │                        │                              │  │   └─ TAIL_AY (?P<pages>)
│                     │       │                        │                              │  └─ (?P<issue>)
│                     │       │                        │                              └─ (?P<volume>)
│                     │       │                        └─ (?P<venue>) lazy up to ", <vol>"
│                     │       └─ leading "(year)." consumed right after authors
│                     └─ surname-first list via AU alternation "Hopper, G." & "Kleene, S."
└─ DOI_RE strips "10.1234/synth.1952.54" (prefix optional) before venue parsing
```

## DOI-only and minimal entries

```
[7] E. Noether. Invariante Variationsprobleme. https://doi.org/10.9999/synth.1918.x
    → authors + title + doi, no year/venue → parse_status: partial (title may be
      absent if no ". " boundary → raw if <2 core fields)
```

## Deliberately unparseable

```
%%% BROKEN ENTRY ||| no year no authors ~~~ !!! ??? ~~~ garbage text ...
    → AUTHORS_RE fails, no (19xx|20xx), no DOI, no digits for volume/pages
    → parse_status: raw, all fields null, raw string kept verbatim
```

Entry-splitting hints (mixed lists): a new entry starts at `^\[\d+\]`, or at a
surname-first line containing a `(year)` when the previous entry looks
complete, or at a non-alphanumeric starter (corrupted entries) after a
complete-looking entry. Wrapped continuation lines are re-joined with spaces.
