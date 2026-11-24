# Provided bibliography (SYNTHETIC EXAMPLE — all entries invented)

Only these works may be cited. Each entry lists the evidence available to the
writer: a full synthetic abstract unless marked `title-only`.

1. Novak, I., Petersen, L. (2021). TemplateTransfer: ligand binding-site prediction by single-template pocket transplantation. *J. Synth. Comput. Biol.* doi:10.0000/synth.0001
   - Abstract: TemplateTransfer predicts ligand binding sites by transplanting pockets from the single highest-identity template structure. On an invented benchmark of 80 targets it reaches 0.55 top-1 pocket precision when template identity exceeds 40%, but precision drops to 0.41 for targets below 30% identity, because a single template often carries a partially mismatched pocket.
2. Okafor, M., Lindqvist, S., Achebe, T. (2022). SeqPocket: sequence-only binding-site prediction with a residue-attention network. *Synth. Bioinform. Lett.* doi:10.0000/synth.0002
   - Abstract: SeqPocket predicts binding residues directly from sequence using a residue-attention network, requiring no structural template. It matches template-based methods on targets with no usable template but lags them by 0.10 top-1 precision on template-rich targets. The authors note it cannot localize pockets that lack sequence motifs.
3. Vasquez, R. (2023). MultiTempl: naive pocket pooling from multiple templates. *J. Synth. Comput. Biol.* doi:10.0000/synth.0003
   - Abstract: MultiTempl pools predicted pockets from up to 8 template structures and ranks them by pocket frequency. Pooling raises recall by 0.15 over single-template transfer, but precision on low-identity targets stays flat because low-quality templates vote with equal weight.
4. Haugen, P., Weiss, D. (2020). GeoScore: geometry-based ranking of candidate binding pockets. *Proc. Synth. Struct. Biol.* doi:10.0000/synth.0004
   - Abstract: GeoScore ranks candidate pockets by geometric descriptors (depth, enclosure, hydrophobic patch area) without any template. It is fast and template-free, but the abstract reports no comparison against template-based predictors and no low-identity evaluation.
5. Tanaka, Y., Moreau, C. (2024). ConsenSite: consensus scoring of pockets across homologous structures. *Synth. Bioinform. Lett.* doi:10.0000/synth.0005
   - Abstract: ConsenSite scores candidate pockets by unweighted consensus across homologous experimental structures of the same protein. It improves precision by 0.07 over single-structure scoring, but requires multiple experimental structures of the target itself, which are unavailable for most prediction targets; it was not evaluated on template-based transfer.
6. Karlsen, E. (2019). A survey of binding-site prediction methods. *Synth. Rev. Comput. Biol.* doi:10.0000/synth.0006
   - Abstract: This survey groups binding-site predictors into template-based, geometry-based and sequence-based families, and observes that low-identity template transfer remains the weakest setting across all template-based methods surveyed.
