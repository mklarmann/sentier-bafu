# Findings about the BAFU/UVEK data

<!-- Generated from community/findings/ by `python3 scripts/community.py index`. Do not edit. -->

One line per finding. The full record of a finding is its file in [findings/](findings/), for
example [findings/F3.json](findings/F3.json); the [site](https://sentier-dev.github.io/sentier-bafu/findings.html)
shows every record with its discussion. Dataset values and names are quoted; text from the
LCI reports is never pasted (Terms of Use clause 4).

Numbers are shared with the [lci-bafu-catalog ledger](https://gitlab.com/eos-lci/lci-bafu-catalog/-/blob/main/docs/bafu_findings.md),
so a finding has one number in both places. A number missing here is a finding recorded
there that has no record in this repository yet.

## Status vocabulary

| Status | Meaning |
|---|---|
| **open** | observed and measured; not yet sent to BAFU |
| **upstream-reported** | sent to BAFU (date on the issue) |
| **upstream-fixed** | BAFU corrected it in a named release |
| **informational** | a method or scope difference, not a defect; recorded so nobody derives it again |
| **handled-in-layer** | a layer applies it in a candidate build; the question to BAFU stays open |
| **withdrawn** | did not survive re-measurement on BAFU's own files; kept so nobody finds it again |

## Ledger

| # | Dataset(s) | Observation | Release | Status | Thread here · derivation |
|---|---|---|---|---|---|
| F1 | 188725 (ES), 178351 (CH), 242090 (CH) strawberries, plastic tunnel | Strawberries in plastic tunnel: 126 / 18 / 18 kg of polyethylene disposal per kg of fruit | 2025 v2, 2026 v1 | upstream-reported | [#6](https://github.com/sentier-dev/sentier-bafu/issues/6) · [lci-bafu-catalog #1](https://gitlab.com/eos-lci/lci-bafu-catalog/-/issues/1) |
| F2 | 191385 Refrigerant R134a, at plant (RER) | Refrigerant R134a: HFC, HCFC and CFC emissions exactly 10× the ecoinvent process | 2025 v2, 2026 v1 | open | [#7](https://github.com/sentier-dev/sentier-bafu/issues/7) · [lci-bafu-catalog #2](https://gitlab.com/eos-lci/lci-bafu-catalog/-/issues/2) |
| F3 | hard-coal supply chains + 2 others | 23 supplier links declare location ENTSO (registered as ENTSO-E); two declare CH for GLO/RER suppliers | 2026 v1 | upstream-reported | [#8](https://github.com/sentier-dev/sentier-bafu/issues/8) · [lci-bafu-catalog #3](https://gitlab.com/eos-lci/lci-bafu-catalog/-/issues/3) |
| F4 | whole release | Elementary exchanges absent from the flow list (withdrawn; refined by F31) | — | withdrawn | [lci-bafu-catalog #4](https://gitlab.com/eos-lci/lci-bafu-catalog/-/issues/4) |
| F5 | flow list, all releases | Chloride to water: seven sub-compartments in the files, one entry without sub-compartment in the flow list | 2026 v1 | informational | [lci-bafu-catalog #5](https://gitlab.com/eos-lci/lci-bafu-catalog/-/issues/5) |
| F6 | CH concrete family | Concrete effluent treatment on 4 of 63 CH concrete datasets | 2026 v1 | informational | [lci-bafu-catalog #6](https://gitlab.com/eos-lci/lci-bafu-catalog/-/issues/6) |
| F7 | published LCIA workbook 2026 v1 | LCIA workbook: ecotoxicity total differs from its parts by more than 5 % on 33 rows; 110 datasets score zero | 2026 v1 | open | [lci-bafu-catalog #7](https://gitlab.com/eos-lci/lci-bafu-catalog/-/issues/7) |
| F8 | 102 flagged and 37 structurally aggregated candidates | 102 flagged aggregated datasets and 37 unflagged candidates | 2026 v1 | handled-in-layer | [#3](https://github.com/sentier-dev/sentier-bafu/issues/3) · [lci-bafu-catalog #11](https://gitlab.com/eos-lci/lci-bafu-catalog/-/issues/11) |
| F9 | 286952 CEM II, B-LL cement, at plant (CH) | CEM II B-LL cement: lorry transport 4.3E-4 tkm/kg against 2.0E-2 in the cited report | 2026 v1 | open | [#9](https://github.com/sentier-dev/sentier-bafu/issues/9) · [lci-bafu-catalog #12](https://gitlab.com/eos-lci/lci-bafu-catalog/-/issues/12) |
| F10 | 196588 Disposal, rectangular straw bale | Straw-bale disposal 196588: flagged as cumulative but carries no flows | 2026 v1 | open | [#3](https://github.com/sentier-dev/sentier-bafu/issues/3) · [lci-bafu-catalog #11](https://gitlab.com/eos-lci/lci-bafu-catalog/-/issues/11) |
| F11 | 1,289 datasets named `xx …` / `xxx …` | 1,289 datasets retired by an xx/xxx name prefix; the convention is undocumented | 2026 v1 | upstream-reported | [#4](https://github.com/sentier-dev/sentier-bafu/issues/4) · [lci-bafu-catalog #15](https://gitlab.com/eos-lci/lci-bafu-catalog/-/issues/15) |
| F12 | radionuclide, noise and waste-heat flows | The same elementary flow is declared in two units across datasets (Bq/kBq, m/km, kWh/MJ, Nm3/m3) | 2026 v1 | informational | [#32](https://github.com/sentier-dev/sentier-bafu/issues/32) · [lci-bafu-catalog #28](https://gitlab.com/eos-lci/lci-bafu-catalog/-/issues/28) |
| F13 | 401085 Electricity, natural gas, at power plant (FI) | Electricity from natural gas (FI) labelled MJ but modelled per kWh | 2026 v1 | open | [#28](https://github.com/sentier-dev/sentier-bafu/issues/28) · [lci-bafu-catalog #34](https://gitlab.com/eos-lci/lci-bafu-catalog/-/issues/34) |
| F14 | 584039 Electricity mix, operation storage pumps, ENTSO, 2020 (CH) | Storage-pump electricity mix: wind input declared OCE, supplier exists only as RER | 2026 v1 | open | [#29](https://github.com/sentier-dev/sentier-bafu/issues/29) · [#8](https://github.com/sentier-dev/sentier-bafu/issues/8) |
| F15 | 7 natural-gas supply names | Natural-gas inputs declared in m3 where every provider is Nm3 | 2026 v1 | open | [#30](https://github.com/sentier-dev/sentier-bafu/issues/30) |
| F16 | 10 `Electricity, production mix` inputs (SE 5, IN 2, CH 2, GLO 1) | Ten electricity production-mix inputs carry no location | 2026 v1 | open | [#31](https://github.com/sentier-dev/sentier-bafu/issues/31) · [#8](https://github.com/sentier-dev/sentier-bafu/issues/8) |
| F17 | published LCIA workbook 2026 v1, `Ecotoxicity freshwater (inorganics)` / `(organics)` | LCIA workbook (June file): ecotoxicity inorganics and organics columns swapped | 2026 v1 (June file) | upstream-fixed | [#35](https://github.com/sentier-dev/sentier-bafu/issues/35) |
| F19 | 491975 Asparagus seedling, open field, at production site (GLO, p) | Asparagus seedling 491975: 14 of 20 input amounts sit on the wrong row | 2025 v2, 2026 v1 | open | [#41](https://github.com/sentier-dev/sentier-bafu/issues/41) |
| F21 | 219148 (LU), 491188 (LT), 369980 (RME), 232890 (KR) `Natural gas, burned in power plant or heat plant` (MJ) | Four gas-combustion datasets take 0.5 MJ of gas per MJ burned but emit the CO₂ of 1 MJ | 2025 v2, 2026 v1 | open | [#42](https://github.com/sentier-dev/sentier-bafu/issues/42) · [lci-bafu-catalog #36](https://gitlab.com/eos-lci/lci-bafu-catalog/-/issues/36) |
| F27 | 389238 Production, washing machine, V-ZUG (CH) | Washing-machine production 389238: the 2026 year-to-hour relabel leaves an annual inventory unscaled | 2026 v1 | open | [#47](https://github.com/sentier-dev/sentier-bafu/issues/47) · [lci-bafu-catalog #44](https://gitlab.com/eos-lci/lci-bafu-catalog/-/issues/44) |
| F29 | Ecological Scarcity 2021, `Sulfur dioxide` to air (a method factor, not a dataset) | Ecological Scarcity 2021: sulfur dioxide at 12,000 UBP/kg; the FOEN report gives 8.3 UBP/g | 2026 v1 | open | [#43](https://github.com/sentier-dev/sentier-bafu/issues/43) |
| F30 | `Nitrogen` to water (647 exchanges on 506 datasets) and `Nitrogen, organic bound` to water (413) | Nitrogen to water carries the CAS number of dinitrogen: what does the flow measure? | 2026 v1 | open | [#44](https://github.com/sentier-dev/sentier-bafu/issues/44) |
| F31 | 304227 Polystyrene, expandable, at plant (RER): `Nitrogen dioxide, RAF` to air; seven RER eco-profiles: `Uranium` to water | Eight exchanges on two flows have no row in the 2025 flow list | 2025 v2, 2026 v1 | open | [#45](https://github.com/sentier-dev/sentier-bafu/issues/45) |
