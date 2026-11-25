# Numeric ledger audit

Records: **17**. Offsets are half-open Unicode-codepoint spans within each paragraph's exact `text`.
Compound expressions retain component offsets; no numeric or unit conversion has occurred.

| Token | Source / paragraph / page | Kind | Exact raw | Scalar | Units | Statistic | Statement span |
|---|---|---|---|---|---|---|---|
| N000001 | synthetic-main / p-control / 1 | scalar | `25 °C` | 25 | °C | — | 0–61 |
  - Context 0–61: Under 25 °C, the control response was 3.2 ± 0.2 mV (Table 1).
| N000002 | synthetic-main / p-control / 1 | uncertainty | `3.2 ± 0.2 mV` | 3.2 ± 0.2 | mV | — | 0–61 |
  - Context 0–61: Under 25 °C, the control response was 3.2 ± 0.2 mV (Table 1).
| N000003 | synthetic-main / p-control / 1 | table_reference | `Table 1` | — | — | — | 0–61 |
  - Context 0–61: Under 25 °C, the control response was 3.2 ± 0.2 mV (Table 1).
| N000004 | synthetic-main / p-treatment / 1 | scalar | `37 °C` | 37 | °C | — | 0–51 |
  - Context 0–71: Under 37 °C, the treated response was 4.8 ± 0.3 mV; the range was 2–4 m
| N000005 | synthetic-main / p-treatment / 1 | uncertainty | `4.8 ± 0.3 mV` | 4.8 ± 0.3 | mV | — | 0–51 |
  - Context 0–104: Under 37 °C, the treated response was 4.8 ± 0.3 mV; the range was 2–4 ms, with p<0.01 and n=18 (Fig. 2).
| N000006 | synthetic-main / p-treatment / 1 | range | `2–4 ms` | 2–4 | ms | — | 52–104 |
  - Context 6–104: 37 °C, the treated response was 4.8 ± 0.3 mV; the range was 2–4 ms, with p<0.01 and n=18 (Fig. 2).
| N000007 | synthetic-main / p-treatment / 1 | p_statistic | `p<0.01` | 0.01 | — | p<0.01 | 52–104 |
  - Context 19–104: eated response was 4.8 ± 0.3 mV; the range was 2–4 ms, with p<0.01 and n=18 (Fig. 2).
| N000008 | synthetic-main / p-treatment / 1 | n_statistic | `n=18` | 18 | — | n=18 | 52–104 |
  - Context 30–104: nse was 4.8 ± 0.3 mV; the range was 2–4 ms, with p<0.01 and n=18 (Fig. 2).
| N000009 | synthetic-main / p-treatment / 1 | figure_reference | `Fig. 2` | — | — | — | 52–104 |
  - Context 36–104: s 4.8 ± 0.3 mV; the range was 2–4 ms, with p<0.01 and n=18 (Fig. 2).
| N000010 | synthetic-main / p-typography / 2 | scalar | `5 × 10⁻³ mol·L⁻¹` | 5 × 10⁻³ | mol·L⁻¹ | — | 0–122 |
  - Context 0–79: At 5 × 10⁻³ mol·L⁻¹, the treated response reached 8% (95% CI 0.4–1.1), an incre
| N000011 | synthetic-main / p-typography / 2 | percent | `8%` | 8 | % | — | 0–122 |
  - Context 0–112: At 5 × 10⁻³ mol·L⁻¹, the treated response reached 8% (95% CI 0.4–1.1), an increase of 0.6 percentage points from
| N000012 | synthetic-main / p-typography / 2 | confidence_interval | `(95% CI 0.4–1.1)` | 0.4–1.1 | — | (95% CI 0.4–1.1) | 0–122 |
  - Context 0–122: At 5 × 10⁻³ mol·L⁻¹, the treated response reached 8% (95% CI 0.4–1.1), an increase of 0.6 percentage points from baseline.
| N000013 | synthetic-main / p-typography / 2 | percentage_point | `0.6 percentage points` | 0.6 | percentage points | — | 0–122 |
  - Context 26–122: reated response reached 8% (95% CI 0.4–1.1), an increase of 0.6 percentage points from baseline.
| N000014 | synthetic-main / p-inequality / 2 | inequality | `<0.2 °C` | 0.2 | °C | — | 0–40 |
  - Context 0–40: The assay temperature drift was <0.2 °C.
| N000015 | synthetic-replication / r-treatment / 4 | scalar | `37 °C` | 37 | °C | — | 0–61 |
  - Context 0–61: Under 37 °C, the treated response was 5.0 ± 0.4 mV (Table 2).
| N000016 | synthetic-replication / r-treatment / 4 | uncertainty | `5.0 ± 0.4 mV` | 5.0 ± 0.4 | mV | — | 0–61 |
  - Context 0–61: Under 37 °C, the treated response was 5.0 ± 0.4 mV (Table 2).
| N000017 | synthetic-replication / r-treatment / 4 | table_reference | `Table 2` | — | — | — | 0–61 |
  - Context 0–61: Under 37 °C, the treated response was 5.0 ± 0.4 mV (Table 2).
