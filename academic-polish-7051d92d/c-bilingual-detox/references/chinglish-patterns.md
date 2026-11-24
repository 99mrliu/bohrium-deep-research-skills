# Chinglish pattern library (中式英语模式库)

Machine-executable in `scripts/detox.py` (pattern ids below match the code).
Categories: **literal-calque** (直译腔) / **cliche** (套话) /
**redundant-nominalization** (冗余名词化) / **connector-abuse** (连接词滥用) /
**vague-subject** (主语悬空) / **word-order** (语序照搬).

A hit is a *review flag*, not a proven error. Zero hits is not proof of
idiomatic English — always finish with a human/LLM read-through.

## literal-calque 直译腔

| id | pattern ( gist ) | ✗ wrong (calque) | ✓ right |
|---|---|---|---|
| LC01 | with the development of …（随着……的发展） | With the development of industry, pollution is serious. | Industrial growth has worsened pollution. |
| LC02 | with the increasingly …（随着日益……） | With the increasingly strict emission standards, … | Stricter emission standards have … |
| LC03 | through the combination of（通过……相结合） | Through the combination of IR and DFT, … | By combining in situ IR with DFT, … |
| LC04 | in the previous research（在前期研究中） | In the previous research, we made X. | In preliminary work, we made X. |
| LC05 | is easy to be …（易……） | The catalyst is easy to be deactivated. | The catalyst deactivates readily. / is prone to deactivation. |
| LC06 | reached more than …（达到……以上） | Conversion reached more than 92%. | Conversion exceeded 92%. |
| LC07 | temperature window of …（温度窗口） | in the temperature window of 150 to 250 °C | across 150–250 °C |
| LC08 | with X structure（具有……结构） | a catalyst with core-shell structure | a core-shell catalyst |
| LC09 | as we all know / it is well known that（众所周知） | It is well known that CeO2 stores oxygen. | CeO2 stores oxygen [3]. |
| LC10 | based on the above（综上所述） | Based on the above, we propose … | Taken together, these results suggest … |
| LC11 | the … mechanism of A on B（……的调控机制） | the regulation mechanism of the interface on NH3 | how the interface regulates NH3 adsorption |
| LC12 | our country（我国） | In our country, diesel trucks … | In China, diesel trucks … |
| LC13 | promote the development of（促进……的发展） | promote the development of catalysis | advance catalysis / catalysis research |
| LC14 | degrees Celsius spelled out | 150 to 250 degrees Celsius | 150–250 °C |

## cliche 套话（说"重要"不如证明重要）

| id | pattern ( gist ) | ✗ wrong | ✓ right |
|---|---|---|---|
| CL01 | play an important role in（发挥重要作用） | Ce plays an important role in SCR. | Ce widens the active temperature window of SCR catalysts. |
| CL02 | has important scientific significance（具有重要的科学意义） | This work has important scientific significance. | The mechanism explains why Mn–Ce interfaces resist sulfur — a long-standing design problem. |
| CL03 | scientific significance and application prospects | …has important scientific significance and application prospects. | …gives refiners a concrete lever: Y doping. |
| CL04 | research hotspot（研究热点） | …has become a research hotspot. | …is now a bottleneck for meeting Euro-VI limits. |
| CL05 | attracted increasing attention（受到广泛关注） | X has attracted increasing attention. | Three groups reported X in 2023 alone [4-6]. |
| CL06 | in the field of（在……领域） | a priority in the field of air pollution control | a priority for air pollution control |
| CL07 | provide theoretical basis and technical support（提供理论依据与技术支撑） | …will provide theoretical basis and technical support for purification. | …will give aftertreatment designers a validated structure–activity rule. |
| CL08 | (broad) application prospects（应用前景） | …with broad application prospects. | …directly transferable to Cu-SSZ-13 systems. |
| CL09 | more and more（越来越） | more and more researchers | a growing number (quantify, or cut) |
| CL10 | it is obvious that / obviously（显然） | Obviously, sulfur poisons the sites. | Sulfur poisons the sites (Fig. 2). |
| CL11 | last but not least | Last but not least, we thank … | (delete) |
| CL12 | a series of（一系列） | a series of experiments | twelve experiments / operando and kinetic experiments |

## redundant-nominalization 冗余名词化

| id | pattern ( gist ) | ✗ wrong | ✓ right |
|---|---|---|---|
| RN01 | the development/improvement/preparation/… of | the development of efficient catalysts is needed | efficient catalysts are needed / we will develop … |
| RN02 | carry out / conduct an analysis of | We carried out an analysis of the spectra. | We analyzed the spectra. |
| RN03 | make an improvement / contribution | make an improvement to the method | improve the method |
| RN04 | conversion/adsorption/removal rate（转化率） | the NOx conversion rate reached 92% | the catalyst converted 92% of NOx |
| RN05 | by means of / by the use of | by means of DFT | with DFT / using DFT |

## connector-abuse 连接词滥用

| id | pattern ( gist ) | ✗ wrong | ✓ right |
|---|---|---|---|
| CA01 | due to the fact that | due to the fact that sulfur poisons sites | because sulfur poisons sites |
| CA02 | in order to | in order to improve stability | to improve stability |
| CA03 | sentence-initial And/But/So | So this project intends to … | We therefore propose … / (merge sentences) |
| CA04 | sentence-initial Moreover/Furthermore/In addition chains | Moreover, … Moreover, … | vary; keep only genuine additions |
| CA05 | Firstly/Secondly/Thirdly | Firstly, we synthesize … | First, we synthesize … |
| CA06 | not only … but also（不仅……而且） | It not only improves activity but also stability. | It improves both activity and stability. |
| CA07 | ", so + subject"（所以） | …is easy to be deactivated, so this project intends to … | …deactivates readily; we therefore … |

## vague-subject 主语悬空 / 无主句硬译

| id | pattern ( gist ) | ✗ wrong | ✓ right |
|---|---|---|---|
| VS01 | this project/paper intends to（本项目/本文拟） | This project intends to construct X. | We will construct X. (grant) / This study constructs X. (paper) |
| VS02 | will be elucidated/studied（将被阐明） | The mechanism will be elucidated. | We will elucidate the mechanism. / The mechanism should emerge from … |
| VS03 | There is/are … opener | There is a catalyst that converts NOx. | One catalyst converts NOx … |
| VS04 | It is important to … opener | It is important to study sulfur resistance. | Sulfur resistance decides whether … |

## word-order 语序 / 信息重心

| id | pattern ( gist ) | ✗ wrong | ✓ right |
|---|---|---|---|
| WO01 | cleft "It is … that …" | It is the interface that controls adsorption. | The interface controls adsorption. |
| WO02 | long preposed adverbial (>50 chars before subject) | Through the combination of in-situ infrared spectroscopy and density functional theory calculation, the mechanism will be elucidated. | We will combine in situ IR with DFT to clarify the mechanism. |
| WO03 | dangling ", which …" tail（流水句尾巴） | …, which has important significance. | …; this result matters because … |

Chinese is topic-prominent: 话题先行、重心在后、无主句常见。English is
subject-prominent: the grammatical subject should carry the information
focus early. Most calques above are really one root cause — keeping the
Chinese information order. See `restructuring-guide.md` for the rewrite side.
