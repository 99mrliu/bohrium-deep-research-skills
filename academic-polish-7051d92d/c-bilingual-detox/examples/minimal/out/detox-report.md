# Detox report (Chinglish pattern lint)

> Synthetic minimal example output of `detox.py lint` (c2e-detox-polish).

- Input: `.work/en-draft.txt`
- Sentences scanned: 6
- Pattern library size: 45
- Total hits: 23

## Hits by category

| Category | Hits |
|---|---|
| literal-calque | 9 |
| cliche | 6 |
| redundant-nominalization | 2 |
| connector-abuse | 1 |
| vague-subject | 3 |
| word-order | 2 |

## Detailed hits

### s0001 @ LC02 (literal-calque / with-increasingly)

- Matched: `With the increasingly` (chars 0-21)
- Sentence: With the increasingly strict emission standards of industrial exhaust gas, the development of highly efficient and stable low-temperature denitration catalysts has become a research hotspot in the field of air pollution control.
- Suggestion: '随着日益……' calque. Front the real driver, e.g. 'Stricter emission standards have ...'.

### s0001 @ WO02 (word-order / long-preposed-adverbial)

- Matched: `With the increasingly strict emission standards of industrial exhaust gas,` (chars 0-74)
- Sentence: With the increasingly strict emission standards of industrial exhaust gas, the development of highly efficient and stable low-temperature denitration catalysts has become a research hotspot in the field of air pollution control.
- Suggestion: Chinese stacks long adverbials before the subject; English wants the subject early. Front the subject, move the adverbial later or split.

### s0001 @ RN01 (redundant-nominalization / the-nominalization-of)

- Matched: `the development of` (chars 75-93)
- Sentence: With the increasingly strict emission standards of industrial exhaust gas, the development of highly efficient and stable low-temperature denitration catalysts has become a research hotspot in the field of air pollution control.
- Suggestion: Nominalization where a verb exists ('the development of X' -> 'developing X' / 'X development' only if technical term). Prefer the verb.

### s0001 @ CL04 (cliche / research-hotspot)

- Matched: `research hotspot` (chars 173-189)
- Sentence: With the increasingly strict emission standards of industrial exhaust gas, the development of highly efficient and stable low-temperature denitration catalysts has become a research hotspot in the field of air pollution control.
- Suggestion: '研究热点' boilerplate. Say why the problem matters now, not that it is popular.

### s0001 @ CL06 (cliche / in-the-field-of)

- Matched: `in the field of` (chars 190-205)
- Sentence: With the increasingly strict emission standards of industrial exhaust gas, the development of highly efficient and stable low-temperature denitration catalysts has become a research hotspot in the field of air pollution control.
- Suggestion: '在……领域' padding. Usually deletable: 'a priority in air pollution control' not 'in the field of'.

### s0002 @ VS01 (vague-subject / this-project-intends)

- Matched: `This project intends to` (chars 229-252)
- Sentence: This project intends to use nano titanium dioxide as the carrier, loading manganese-cerium composite oxide, to construct a low-temperature selective catalytic reduction (SCR) catalyst with core-shell structure.
- Suggestion: Projects/papers cannot intend ('本项目拟'). Grant: 'We will / We aim to'. Paper: 'This study investigates X' (verb, not intention) or 'we'.

### s0002 @ LC08 (literal-calque / with-x-structure)

- Matched: `with core-shell structure` (chars 413-438)
- Sentence: This project intends to use nano titanium dioxide as the carrier, loading manganese-cerium composite oxide, to construct a low-temperature selective catalytic reduction (SCR) catalyst with core-shell structure.
- Suggestion: '具有……结构' calque ('a catalyst with core-shell structure'). Use a compound modifier: 'a core-shell catalyst'.

### s0003 @ LC03 (literal-calque / through-the-combination-of)

- Matched: `Through the combination of` (chars 440-466)
- Sentence: Through the combination of in-situ infrared spectroscopy and density functional theory calculation, the regulation mechanism of manganese-cerium interface synergy on NH3 adsorption activation will be elucidated.
- Suggestion: '通过……相结合' calque. Use 'by combining A with B'.

### s0003 @ WO02 (word-order / long-preposed-adverbial)

- Matched: `Through the combination of in-situ infrared spectroscopy and density functional theory calculation,` (chars 440-539)
- Sentence: Through the combination of in-situ infrared spectroscopy and density functional theory calculation, the regulation mechanism of manganese-cerium interface synergy on NH3 adsorption activation will be elucidated.
- Suggestion: Chinese stacks long adverbials before the subject; English wants the subject early. Front the subject, move the adverbial later or split.

### s0003 @ LC11 (literal-calque / the-mechanism-of)

- Matched: `the regulation mechanism of` (chars 540-567)
- Sentence: Through the combination of in-situ infrared spectroscopy and density functional theory calculation, the regulation mechanism of manganese-cerium interface synergy on NH3 adsorption activation will be elucidated.
- Suggestion: '……的调控机制' nominal calque. Prefer a verb clause: 'how A regulates B'.

### s0003 @ VS02 (vague-subject / will-be-elucidated)

- Matched: `will be elucidated` (chars 632-650)
- Sentence: Through the combination of in-situ infrared spectroscopy and density functional theory calculation, the regulation mechanism of manganese-cerium interface synergy on NH3 adsorption activation will be elucidated.
- Suggestion: Agent-less future passive hides who does the work ('将被阐明'). Grant: 'we will elucidate'; or reorder to make the phenomenon the subject.

### s0004 @ LC04 (literal-calque / in-the-previous-research)

- Matched: `In the previous research` (chars 652-676)
- Sentence: In the previous research, MnOx-CeO2/TiO2 catalyst has been prepared, and the NOx conversion rate has reached more than 92% in the temperature window of 150 to 250 degrees Celsius [1].
- Suggestion: '在前期研究中' calque. Use 'In preliminary work', 'Previously', or 'In our earlier study'.

### s0004 @ RN04 (redundant-nominalization / x-rate)

- Matched: `conversion rate` (chars 733-748)
- Sentence: In the previous research, MnOx-CeO2/TiO2 catalyst has been prepared, and the NOx conversion rate has reached more than 92% in the temperature window of 150 to 250 degrees Celsius [1].
- Suggestion: '转化率' nominalization. Often better as a verb: 'converted 92% of NOx' beats 'the NOx conversion rate reached 92%'.

### s0004 @ LC06 (literal-calque / reached-more-than)

- Matched: `reached more than` (chars 753-770)
- Sentence: In the previous research, MnOx-CeO2/TiO2 catalyst has been prepared, and the NOx conversion rate has reached more than 92% in the temperature window of 150 to 250 degrees Celsius [1].
- Suggestion: '达到……以上' calque. Use 'exceeded X'.

### s0004 @ LC07 (literal-calque / temperature-window-of)

- Matched: `temperature window of` (chars 782-803)
- Sentence: In the previous research, MnOx-CeO2/TiO2 catalyst has been prepared, and the NOx conversion rate has reached more than 92% in the temperature window of 150 to 250 degrees Celsius [1].
- Suggestion: '在……温度窗口内' calque. Use 'across 150-250 °C' or 'between 150 and 250 °C'.

### s0004 @ LC14 (literal-calque / degrees-celsius-spelled-out)

- Matched: `degrees Celsius` (chars 815-830)
- Sentence: In the previous research, MnOx-CeO2/TiO2 catalyst has been prepared, and the NOx conversion rate has reached more than 92% in the temperature window of 150 to 250 degrees Celsius [1].
- Suggestion: Word-by-word rendering of 摄氏度. Use the unit symbol: '250 °C'.

### s0005 @ LC05 (literal-calque / is-easy-to-be)

- Matched: `is easy to be` (chars 888-901)
- Sentence: The similar system reported in reference [2] (2020) is easy to be deactivated in sulfur-containing atmosphere, so this project intends to introduce yttrium doping to improve the sulfur resistance.
- Suggestion: '易……' calque ('is easy to be deactivated'). Use 'deactivates readily', 'is prone to deactivation'.

### s0005 @ CA07 (connector-abuse / comma-so)

- Matched: `, so this` (chars 945-954)
- Sentence: The similar system reported in reference [2] (2020) is easy to be deactivated in sulfur-containing atmosphere, so this project intends to introduce yttrium doping to improve the sulfur resistance.
- Suggestion: Chinese '所以' joins clauses freely; English prefers a full stop, a semicolon, or a 'because'-inversion. Split or restructure.

### s0005 @ VS01 (vague-subject / this-project-intends)

- Matched: `this project intends to` (chars 950-973)
- Sentence: The similar system reported in reference [2] (2020) is easy to be deactivated in sulfur-containing atmosphere, so this project intends to introduce yttrium doping to improve the sulfur resistance.
- Suggestion: Projects/papers cannot intend ('本项目拟'). Grant: 'We will / We aim to'. Paper: 'This study investigates X' (verb, not intention) or 'we'.

### s0006 @ CL07 (cliche / provide-theoretical-basis)

- Matched: `provide theoretical basis` (chars 1059-1084)
- Sentence: The expected results will provide theoretical basis and technical support for diesel vehicle exhaust purification, and have important scientific significance and application prospects.
- Suggestion: '提供理论依据与技术支撑' boilerplate. State the concrete deliverable instead.

### s0006 @ CL02 (cliche / has-important-significance)

- Matched: `have important scientific significance` (chars 1152-1190)
- Sentence: The expected results will provide theoretical basis and technical support for diesel vehicle exhaust purification, and have important scientific significance and application prospects.
- Suggestion: '具有重要的科学意义' boilerplate. Show the significance instead: say who can now do what.

### s0006 @ CL03 (cliche / significance-and-prospects)

- Matched: `scientific significance and application prospects` (chars 1167-1216)
- Sentence: The expected results will provide theoretical basis and technical support for diesel vehicle exhaust purification, and have important scientific significance and application prospects.
- Suggestion: '科学意义和应用前景' stacked boilerplate. Replace with one concrete expected consequence.

### s0006 @ CL08 (cliche / application-prospects)

- Matched: `application prospects` (chars 1195-1216)
- Sentence: The expected results will provide theoretical basis and technical support for diesel vehicle exhaust purification, and have important scientific significance and application prospects.
- Suggestion: '应用前景' boilerplate. Replace with the actual use case and user.

---

Boundary note: Pattern hits are heuristic flags for review, not proven errors; zero hits does not prove idiomatic English.
