# Common-field matrix

Every row contains every document. Citations are exact `(source_document_id, paragraph_id)` pairs; unreported and noncomparable values are preserved.

| Field | paper-a | paper-b | paper-c |
|---|---|---|---|
| task | batch adsorption removal<br>Source: `paper-a`, paragraph `a-p1` | batch adsorption removal<br>Source: `paper-b`, paragraph `b-p1` | batch adsorption removal<br>Source: `paper-c`, paragraph `c-p1` |
| material | magnetite-biochar composite vs pristine biochar<br>Source: `paper-a`, paragraph `a-p1` | magnetite-biochar composite vs pristine biochar<br>Source: `paper-b`, paragraph `b-p1` | magnetite-biochar composite vs pristine biochar<br>Source: `paper-c`, paragraph `c-p1` |
| pollutant | methylene blue (dye)<br>Source: `paper-a`, paragraph `a-p1` | methylene blue (dye)<br>Source: `paper-b`, paragraph `b-p1` | methylene blue (dye)<br>Source: `paper-c`, paragraph `c-p1` |
| metric | equilibrium adsorption capacity<br>Source: `paper-a`, paragraph `a-p1` | equilibrium adsorption capacity<br>Source: `paper-b`, paragraph `b-p1` | equilibrium adsorption capacity<br>Source: `paper-c`, paragraph `c-p1` |
| units | mg/g<br>Source: `paper-a`, paragraph `a-p1` | mg/g<br>Source: `paper-b`, paragraph `b-p1` | mg/g<br>Source: `paper-c`, paragraph `c-p1` |
| budget | unreported<br>Source: `paper-a`, paragraph `a-p1` | unreported<br>Source: `paper-b`, paragraph `b-p1` | unreported<br>Source: `paper-c`, paragraph `c-p1` |
| scope | ambient: pH 7; 100 mg/L; 298 K; 120 min; 1 g/L; dataset A<br>Source: `paper-a`, paragraph `a-p2` | acidic extension and ambient attempted replication; no cross-scope pooling<br>Source: `paper-b`, paragraph `b-p2` | direct pH 3/7 x material comparison; other stated conditions fixed<br>Source: `paper-c`, paragraph `c-p2` |

## Quantitative-synthesis gate

Task, material, pollutant, metric, units, budget, scope, and dataset identity must all pass before quantitative synthesis could be considered. This example has unreported budgets and independent datasets and explicitly authorizes no pooling. Reported numbers remain side-by-side; no dye or dataset pooling is performed.
