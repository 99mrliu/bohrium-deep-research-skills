# Enforcement rules — how audit_translation.py judges a translation

The auditor is deliberately simple, deterministic and strict. It checks
**bilingual segment pairs** (`pairs.jsonl`) against the **locked termbase** and
blocks delivery on any blocker-severity violation.

## Source-occurrence matching (when is a term "present" in a source segment?)

A term occurs in a source segment when `term_pattern(source_term)` matches:

1. **Case folding** — matching is case-insensitive (`Perovskite Solar Cell` ≡ `perovskite solar cell`).
2. **Hyphen/space equivalence** — `-`, U+2010, U+2011 and space are the same separator
   (`open-circuit voltage` matches `open circuit voltage` and vice versa).
3. **Plural 's'** — the final token takes an optional trailing `s` unless it already
   ends in `s` (`solar cell` also matches `solar cells`).
4. **Token boundaries** — lookarounds `(?<![a-z0-9]) … (?![a-z0-9])` prevent
   matching inside longer words (`cell` does not match inside `subcellular`).
5. **Acronym acceptance** — for entries with `kind == "acronym"`, the acronym itself
   (word-boundary matched, case-sensitive) also counts as a source occurrence.

## Pass condition (when does a target segment satisfy the term?)

For every entry × segment where the source contains the term:

- **PASS** if the locked `target` string appears verbatim in the target segment.
- **PASS (acronym entries only)** if the acronym appears as a whole word in the target —
  writing `(PSC)` or reusing `PSC` in the Chinese sentence is acceptable.
- Otherwise → violation `term-drift`.

## Section taxonomy

| section | assigned by |
|---|---|
| `title` | first 3 non-empty lines of the source |
| `abstract` | line starting with `Abstract` |
| `body` | default for everything else |
| `caption` | lines starting with `Figure` / `Fig.` / `Table` |
| `introduction` / `conclusion` / `references` | matching heading lines (also markdown `#` headers and short ALL-CAPS lines) |

`pairs.jsonl` segments should carry these same section names so the coverage
matrix lines up with the extractor's.

## Violation codes and severities

| code | severity | meaning | action |
|---|---|---|---|
| `term-drift` | **blocker** | source segment contains the term but target lacks the locked rendering (and the acronym, for acronym entries) | fix the segment, re-audit; exit 1 until clean |
| `forbidden-variant` | **blocker** | target of a term-containing segment uses a listed forbidden variant | replace with locked target, re-audit |
| `uncovered-entry` | warning | a locked entry never occurs in any audited segment (term may live in an unsegmented part, or pairs.jsonl is incomplete) | verify coverage is complete; report stays exit 0 |

Exit code: `1` if any violation (blocker), else `0`. Warnings never change the exit code.

## Worked examples

Locked entry: `{"source_term": "perovskite solar cell", "acronym": "PSC",
"kind": "acronym", "target": "钙钛矿太阳能电池", "forbidden_variants": ["钙钛矿电池"]}`

| # | source | target | verdict | why |
|---|---|---|---|---|
| 1 | `Perovskite solar cells show promise.` | `钙钛矿太阳能电池展现出前景。` | PASS | plural `cells` matched; locked target present |
| 2 | `The PSC is stable.` | `PSC 器件稳定性良好。` | PASS | acronym occurrence; acronym reused in target |
| 3 | `A perovskite solar cell was fabricated.` | `制备了钙钛矿电池器件。` | FAIL ×2 | `term-drift` (no `钙钛矿太阳能电池`) **and** `forbidden-variant` (`钙钛矿电池`) |
| 4 | `Open-circuit voltage reached 1.1 V.` | `开路电压达到 1.1 V。` | PASS | hyphen/space equivalence on `open circuit voltage` |
| 5 | `The open circuit voltage drops.` | `开路电压下降。` | PASS | source used spaces, term has hyphen — equivalent |
| 6 | `The charge transport layer is thin.` | `传输层很薄。` | FAIL | `term-drift`: locked `电荷传输层` missing |

Locked entry: `{"source_term": "power conversion efficiency", "acronym": "PCE",
"kind": "acronym", "target": "光电转换效率", "forbidden_variants": ["能量转换效率"]}`

| # | source | target | verdict |
|---|---|---|---|
| 7 | `PCE exceeded 25%.` | `光电转换效率超过 25%。` | PASS |
| 8 | `Power conversion efficiency (PCE) rose.` | `能量转换效率（PCE）上升。` | FAIL | `forbidden-variant` (+ `term-drift` if `光电转换效率` absent) |
