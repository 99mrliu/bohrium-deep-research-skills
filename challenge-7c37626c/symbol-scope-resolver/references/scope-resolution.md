# Scope resolution and ledger semantics

## Evidence units

The extractor assigns stable IDs in XML document order. A section pointer locates
an XML `sec`/`section`/`chapter`; paragraph and sentence pointers retain their
parent section. Sentence text and offsets refer to the whitespace-normalized
paragraph text stored in `ledger.json`. Candidate quotes are exact substrings,
not paraphrases. Paragraphs outside explicit sections use an explicit document
root scope rather than being merged into the first section.

Scope is determined from the article's discourse structure. The default binding
scope is one publisher section within one document. Subsections receive their own
scope. Repeated occurrences of the same complete identity within one local scope
can share a binding only after the agent checks that the source does not redefine
the symbol. If it does, retain the conflict in that scope; do not export its
meaning into a neighboring section. Paragraph and sentence locators provide the
finer evidence needed for that review.

## Occurrence, identity, and binding

Keep three levels distinct:

1. **Formula occurrence** — one `math` element or non-MathML formula container,
   with `formula_id`, source pointer, section, paragraph context, and MathML.
2. **Symbol occurrence** — one full symbol inside that formula. Script wrappers
   (`msub`, `msup`, `msubsup`, under/over variants, and `mmultiscripts`) retain
   all script content. Annotation branches are excluded to avoid duplicate
   TeX/rendering tokens.
3. **Scoped symbol instance** — repeated occurrences grouped by document,
   section, base glyph, canonical full symbol, and complete script structure.

Consequently, `r`, `r_{1}`, and `r_{2}` are not aliases merely because their base
is `r`. A plain `r` in section A and plain `r` in section B are separate scoped
instances even though their canonical MathML text is identical. No one-variable,
one-definition table is acceptable across such scopes.

The canonical field is an audit key, not a typographic reconstruction target.
Use `base_glyph` and `scripts` for identity decisions and use source MathML when
the exact formula matters.

## Candidate review

English cues include `where`, `denote(s)`, `is/are defined as`, `represent(s)`,
`representing`, and `stands for`. Chinese cues include `取值`, `表示`, and
`定义为`. Unit cues cover explicit unit language and common printed unit tokens;
range cues cover from/between, numeric interval notation, inequalities, and
Chinese range expressions. Cue matches only prioritize reading. They do not
establish which symbol a clause modifies, whether a statement is hypothetical,
or whether a negated unit statement reports a value.

Read the complete paragraph and formula context. A direct definition candidate
may be rejected, another candidate selected, an inference labeled, a not-reported
state retained, or a conflict preserved. Never let extraction order or a global
lexicon approve a definition automatically.

## Formula coverage

Coverage is occurrence-by-occurrence, not a claim about a unique equation. A
covered MathML occurrence must list every `symbol_instance_id` attached to that
formula. An exclusion must set `excluded: true` and give an actual reason (for
example, formula is decorative markup and contains no scientific symbol). A
missing entry, `covered: null`, or a generic unreviewed template fails validation.
Non-MathML containers remain visible as `xml_text_only`; their text is not parsed
into guessed symbol identities.

When no formula representation exists, formula coverage is empty because there
are no extracted occurrences—not because the target formula has value zero. The
absence itself must drive partial/insufficient-evidence status and limitations.
