# Findings about the BAFU/UVEK data — the open ledger

A **finding** is a measured observation about a BAFU dataset or release: an amount
that cannot be right, a supplier declared with a location that is not registered,
a flow the published flow list does not carry, a dataset flagged as cumulative
that carries no flows. It is not a contribution layer (those are
[contribution records](contributions/)); a finding may *lead* to a layer, or to a
recommendation, or to nothing but a note that saves the next person a day.

Every row below was re-measured on BAFU's own release files (the ecoSpold v1
archive, the LCIA results workbook, the change log) before it was written up;
two earlier write-ups elsewhere were wrong because they measured a local
import instead. The derivations, scripts and discussion threads live on the
linked issues. Dataset values and names are quoted freely; text from the LCI
*reports* is never pasted (Terms of Use clause 4, author copyright).

## Status vocabulary

| Status | Meaning |
|---|---|
| **open** | observed and measured; not yet sent to BAFU |
| **upstream-reported** | sent to lca@bafu.admin.ch (date on the issue) |
| **upstream-fixed** | BAFU corrected it in a named release |
| **informational** | a method or scope difference, not a defect; recorded so nobody re-derives it |
| **handled-in-layer** | a contribution layer applies it in a candidate build; the upstream question stays open |
| **withdrawn** | did not survive re-measurement against BAFU's own files; kept so nobody re-finds it |

## Ledger (seeded 2026-10-07 from the lci-bafu-catalog ledger, BAFU:2025 v2 and BAFU:2026 v1)

| # | Dataset(s) | Observation | Release | Status | Thread here · derivation |
|---|---|---|---|---|---|
| F1 | 188725 (ES), 178351 (CH), 242090 (CH) strawberries, plastic tunnel | 126.22 / 18.085 / 18.079 kg `Disposal, polyethylene, 0.4% water, to municipal incineration` per kg fruit, against 0.0096 / 0.042 / 0.036 kg of polyethylene granulate entering; the tunnel film is already disposed of in the tunnel dataset (per m²·a). The LCIA workbook scores them at 383 / 55 / 55 kg CO₂-eq per kg; the heated greenhouse in the same group scores 2.6. Identical in both releases; not in the 2026 change log. BAFU confirmed the error by email on 12 October 2026 and announced a correction for its next release; community-fixes [patch 0001](https://github.com/sentier-dev/bafu-community-fixes/blob/053c799a4d3e129747f47d6775ea88647c0bec78/src/bafu_community_fixes/patches/p0001_strawberry_polyethylene_disposal.py) applies the corrected amounts until then. | 2025 v2, 2026 v1 | upstream-reported | [#6](https://github.com/sentier-dev/sentier-bafu/issues/6) · [lci-bafu-catalog #1](https://gitlab.com/eos-lci/lci-bafu-catalog/-/issues/1) |
| F2 | 191385 Refrigerant R134a, at plant (RER) | HFC-134a 0.019, HCFC-124 0.010, CFC-113 0.010 kg per kg — each exactly 10× the corresponding ecoinvent 3.6 dataset (0.0019 / 0.001 / 0.001); GWP100 108.6 against roughly 19. A documented process difference or a unit slip? | 2025 v2, 2026 v1 | open | [#7](https://github.com/sentier-dev/sentier-bafu/issues/7) · [#2](https://gitlab.com/eos-lci/lci-bafu-catalog/-/issues/2) |
| F3 | hard-coal supply chains + 2 others | 23 exchanges declare the supplier location `ENTSO`; no dataset is registered as ENTSO, 25 as ENTSO-E, and every one of the 23 suppliers exists as ENTSO-E. Two more exchanges declare `CH` for suppliers that exist only as GLO / RER (`Disposal, concrete, 5% water, to inert material landfill`; `Direct air capture system, sorbent-based, 100ktCO2`). An importer linking by name + location drops all 25 silently; one linking by dataset number does not. BAFU confirmed this by email on 12 October 2026 and announced a correction for its next release; community-fixes [patch 0002](https://github.com/sentier-dev/bafu-community-fixes/blob/053c799a4d3e129747f47d6775ea88647c0bec78/src/bafu_community_fixes/patches/p0002_supplier_locations.py) uses the suppliers' locations until then. | 2026 v1 | upstream-reported | [#8](https://github.com/sentier-dev/sentier-bafu/issues/8) · [#3](https://gitlab.com/eos-lci/lci-bafu-catalog/-/issues/3) |
| F4 | whole release | **Withdrawn.** The claim that ~7.6 % of elementary exchanges were absent from the flow list was an artefact of an earlier donor-seeded import; re-measured, one flow name is absent. Counted by name and compartment instead, 8 exchanges have no row in the 2025 flow list: see F31. | — | withdrawn | [#4](https://gitlab.com/eos-lci/lci-bafu-catalog/-/issues/4) |
| F5 | flow list, all releases | The XML declares chloride to water with seven sub-compartments (ocean, river, groundwater …); the published flow list carries one `Chloride` without sub-compartment. A structure question, not a value defect. | 2026 v1 | informational | [#5](https://gitlab.com/eos-lci/lci-bafu-catalog/-/issues/5) |
| F6 | CH concrete family | `Treatment, concrete production effluent` (0.0143 m³/m³) is carried by 4 of the 63 CH concrete datasets and by none of the civil-engineering concretes. Inconsistent modelling or a scope choice? | 2026 v1 | informational | [#6](https://gitlab.com/eos-lci/lci-bafu-catalog/-/issues/6) |
| F7 | published LCIA workbook 2026 v1 | 33 rows where the ecotoxicity total differs from inorganics + organics by more than 5 % (worst 23.4 %); 110 datasets score zero in every category. | 2026 v1 | open | [#7](https://gitlab.com/eos-lci/lci-bafu-catalog/-/issues/7) |
| F8 | 102 flagged and 37 structurally aggregated candidates | 102 datasets are cumulative LCIs flagged ecoSpold `dataSetInformation@type=2` (no supplier links); 37 more PlasticsEurope-era eco-profiles are aggregated by structure (no supply input, > 50 elementary flows) but not flagged. Matters for every disaggregation or copied-process layer. Community-fixes [patch 0011](https://github.com/sentier-dev/bafu-community-fixes/pull/5) flags 40 datasets `type=2`: the 37, plus one more eco-profile and two inventories without inputs ([below](#f8-the-list-behind-the-37-unflagged-candidates)). | 2026 v1 | handled-in-layer | [#3](https://github.com/sentier-dev/sentier-bafu/issues/3) · [#11](https://gitlab.com/eos-lci/lci-bafu-catalog/-/issues/11) |
| F9 | 286952 CEM II, B-LL cement, at plant (CH) | lorry transport 4.345E-4 tkm/kg in the dataset; the cited 2020 cement/concrete report's table prints 2.00E-2 tkm for CEM II/B-LL (rail 1.50E-4 in both). Found by comparing the dataset with its report. | 2026 v1 | open | [#9](https://github.com/sentier-dev/sentier-bafu/issues/9) · [#12](https://gitlab.com/eos-lci/lci-bafu-catalog/-/issues/12) |
| F10 | 196588 Disposal, rectangular straw bale | flagged type=2 but carries only its production exchange — a cumulative LCI with no flows; the two straw-bale siblings carry 1,656 flows each. | 2026 v1 | open | [#3](https://github.com/sentier-dev/sentier-bafu/issues/3) · [#11](https://gitlab.com/eos-lci/lci-bafu-catalog/-/issues/11) |
| F11 | 1,289 datasets named `xx …` / `xxx …` | retired by name prefix and/or category words (`obsolete`: 803, `notMaintained`: 441, current category: 45; 57 `obsolete` datasets carry no prefix). The convention is undocumented; consumers that match by name anchor on retired datasets unknowingly. BAFU explained by email on 12 October 2026 that these datasets should be avoided and will move to a "not maintained" category in its next release; community-fixes [patch 0003](https://github.com/sentier-dev/bafu-community-fixes/blob/053c799a4d3e129747f47d6775ea88647c0bec78/src/bafu_community_fixes/patches/p0003_flag_not_maintained.py) flags the prefixed ones (not the 57 without a prefix). | 2026 v1 | upstream-reported | [#4](https://github.com/sentier-dev/sentier-bafu/issues/4) · [#15](https://gitlab.com/eos-lci/lci-bafu-catalog/-/issues/15) |
| F12 | radionuclide, noise and waste-heat flows | The same flow is declared in two units in different datasets. Counted by name and compartment, 112 flows: 107 radionuclides in Bq (3,171 exchanges on 20 cumulative datasets) and kBq, 2 road-noise flows in m (43 exchanges) and km, `Heat, waste` in kWh (3) and MJ, and 2 gas resources in Nm3 (127 exchanges) and m3; the first count listed three unit pairs. The flow list (`SetupDatabase_file.CSV` of the BAFU:2025 SimaPro import guide; the 2026 download has no such file) carries one unit per flow and gives the factors (kBq = 1000 Bq, km = 1000 m, kWh = 3.6 MJ, Nm3 = 1 m3); whether 1 Nm3 = 1 m3 holds for those 127 exchanges is open. An importer that compares unit labels only either writes Bq amounts against kBq flows (EF 3.1 ionising radiation ×1,000; GWP unaffected) or drops the exchanges. Not a value error; every importer must convert explicitly. The lci-bafu-catalog layer converts Bq, m and kWh and records it per exchange; its Nm3 route is a label mapping that records nothing. | 2026 v1 | informational | [#32](https://github.com/sentier-dev/sentier-bafu/issues/32) · [#28](https://gitlab.com/eos-lci/lci-bafu-catalog/-/issues/28) |
| F13 | 401085 Electricity, natural gas, at power plant (FI) | Reference unit MJ; its 29 sibling regions and its only consumer (`Electricity, from natural gas`, FI, 0.0156738 kWh) use kWh. The dataset is modelled per kWh (14.07 MJ gas per unit against a sibling median of 7.17 MJ/kWh; 3.6 / 14.07 = its stated 25.6 % efficiency): a label error, no rescale. BAFU's own `LCIA-Results.xlsx` applies ×3.6 on that edge, overstating FI gas electricity by about 9 % and the FI production mix by about 2 %. The same error affects 316743 `Electricity, hard coal, at power plant, merged` (IN, labelled MJ, about 0.76 kg coal per unit, no consumer). | 2026 v1 | open | [#28](https://github.com/sentier-dev/sentier-bafu/issues/28) · [#34](https://gitlab.com/eos-lci/lci-bafu-catalog/-/issues/34) |
| F14 | 584039 Electricity mix, operation storage pumps, ENTSO, 2020 (CH) | One wind input (0.0058202 kWh/kWh, comment `Wind Offshore / DE`) declares location OCE with supplier number 535960, the only wind-farm provider (onshore, RER). OCE exists as a geography, but the only wind dataset there is retired (`xx Electricity, at wind power plant 2MW, offshore`, 539240); current offshore wind farms exist at RER (402599, 396070, 555490). Relabelling as RER links the edge but keeps an onshore stand-in for offshore wind. | 2026 v1 | open | [#29](https://github.com/sentier-dev/sentier-bafu/issues/29) · [#8](https://github.com/sentier-dev/sentier-bafu/issues/8) |
| F15 | 7 natural-gas supply names | 40 consumer exchanges declare `m3` where every provider of the name declares `Nm3` (DZ/NG/QA/US at production, NO/NL/GB offshore, DE/RU/NL onshore, three RER pipelines, LNG DZ to FR). Amounts are consistent with Nm3 (≈36 MJ per m3); relabel, no rescale. | 2026 v1 | open | [#30](https://github.com/sentier-dev/sentier-bafu/issues/30) |
| F16 | 10 `Electricity, production mix` inputs (SE 5, IN 2, CH 2, GLO 1) | No location attribute; the supplier number on all ten is 744613, the ENTSO-E production mix. They are part of 1,399 location-less technosphere exchanges whose supplier numbers all point to ENTSO-E datasets, so the absent location reads as ENTSO-E, not the consumer's geography. Three consumers are retired (`xx`, F11). | 2026 v1 | open | [#31](https://github.com/sentier-dev/sentier-bafu/issues/31) · [#8](https://github.com/sentier-dev/sentier-bafu/issues/8) |
| F17 | published LCIA workbook 2026 v1, `Ecotoxicity freshwater (inorganics)` / `(organics)` | In the June 2026 file (sha256 `a213ab5a…`) the two sub-indicator columns carry each other's header: `Copper, primary, at refinery` (GLO) shows 0.60 inorganics against 170 organics CTUe/kg, and organics is larger in 11,600 of 11,947 rows. BAFU's corrected file of 15 July 2026 (`BAFU-2026 v1 LCIA Results_corrected.xlsx`, sha256 `7e9f1c9f…`) exchanges the two header labels. Compared cell by cell, only the date cell and those two headers differ, and every value is identical. We measured the June file, so this row was filed after BAFU had corrected it. A tool that reads the columns by position keeps the swap on either file, and both files say `BAFU:2026 v1`: only the date cell or the sha256 tells them apart. The total is unaffected. | 2026 v1 (June file) | upstream-fixed | [#35](https://github.com/sentier-dev/sentier-bafu/issues/35) |
| F19 | 491975 Asparagus seedling, open field, at production site (GLO, p) | 14 of its 20 technosphere and land rows carry the amount, with its pedigree comment, of a different row of the report's Figure 6 (*Life cycle assessment of strawberry and asparagus production*, Kägi et al., 2022). `Pesticide unspecified` reads 0.04 kg per seedling against the figure's 3.35E-06 kg. That one row is 89 % of the seedling's GWP100 in the workbook (0.392 kg CO₂-eq/p; about 0.024 with the figure's assignment) and 22–37 % of its three consumers, `Asparagus, conventional` 435703 (CH), 378451 (PE) and 202096 (MX). | 2025 v2, 2026 v1 | open | [#41](https://github.com/sentier-dev/sentier-bafu/issues/41) |
| F21 | 219148 (LU), 491188 (LT), 369980 (RME), 232890 (KR) `Natural gas, burned in power plant or heat plant` (MJ) | One gas input of 0.5 MJ per MJ burned. The other 34 datasets of this name take 1.0 MJ, and all 38 emit 0.0561 kg fossil CO₂, the CO₂ of 1 MJ. The workbook scores the four 11.3 % (LU, LT, RME) and 15.4 % (KR) below their same-supplier siblings, which is the missing half of the supply chain. Eleven datasets consume them directly. | 2025 v2, 2026 v1 | open | [#42](https://github.com/sentier-dev/sentier-bafu/issues/42) · [lci-bafu-catalog #36](https://gitlab.com/eos-lci/lci-bafu-catalog/-/issues/36) |
| F29 | Ecological Scarcity 2021, `Sulfur dioxide` to air (a method factor, not a dataset) | The method in the release's openLCA package scores SO₂ at 12,000 UBP/kg in all four air compartments. The FOEN report (*Swiss Eco-Factors 2021 according to the Ecological Scarcity Method*) gives 8.3 UBP/g, and the method carries the report's values for the acids it scales from SO₂ by acidification potential (HCl 7,300, H₂S 16,000 UBP/kg). The workbook applies 12,000: of the 101 cumulative datasets with SO₂, 87 reproduce within 0.01 % at 12,000 and none at 8,300. Effect ×1.45 on SO₂. On the 87 cumulative datasets with SO₂ and no technosphere input, the difference is a median 3.3 % of `Main air pollutants and PM` (largest 10.9 %, `Anthraquinone, at plant`); on the 68 of them with unit kg, a median 3.4 % of that column and 0.2 % of `Total`. Is there an official factor list that says 12? | 2026 v1 | open | [#43](https://github.com/sentier-dev/sentier-bafu/issues/43) |
| F30 | `Nitrogen` to water (647 exchanges on 506 datasets) and `Nitrogen, organic bound` to water (413) | Both carry CAS 7727-37-9, molecular nitrogen (N₂). The flow list (`SetupDatabase_file.CSV` of the BAFU:2025 SimaPro import guide; the 2026 download has no such file) writes `Formula: N` under Waterborne and `Formula: N2` under Airborne with that number, and the release's openLCA package gives `Nitrogen` to water the formula N2; probably an inherited convention. A question, not a value defect: what does `Nitrogen` to water measure (202 exchanges call it a sum parameter), and where it is total N, do nitrate and ammonium on the same dataset count twice? Of the 104 unit processes that report it next to those species, it is smaller than their nitrogen in 70, so there it cannot be their sum; a double count could occur in the other 34, and none has been shown. | 2026 v1 | open | [#44](https://github.com/sentier-dev/sentier-bafu/issues/44) |
| F31 | 304227 Polystyrene, expandable, at plant (RER): `Nitrogen dioxide, RAF` to air; seven RER eco-profiles: `Uranium` to water | Counted by name and compartment, 8 of 293,747 elementary exchanges have no row in the flow list (`SetupDatabase_file.CSV` of the BAFU:2025 SimaPro import guide; the 2026 download has no such file): it has no `Nitrogen dioxide, RAF` and lists waterborne uranium only by isotope. For 2026 the uranium gap is in that 2025 file, not in the release: the release's openLCA package has `Uranium` to water in kg with all seven amounts. Only the RAF name is a real difference, and the package carries that row as `Nitrogen dioxide`. 304227 has no `Nitrogen oxides` row while 13 of the 14 datasets from its generator do, so the row looks like its NOx under a name nothing else uses, and the published `Main air pollutants and PM` appears not to count it. Refines F4, which counted by name. | 2025 v2, 2026 v1 | open | [#45](https://github.com/sentier-dev/sentier-bafu/issues/45) |

Numbers follow the [lci-bafu-catalog ledger](https://gitlab.com/eos-lci/lci-bafu-catalog/-/blob/main/docs/bafu_findings.md), so a finding has one number in both places. This ledger lists only the findings filed here: F18, F20 and F22–F28 are recorded there and have no issue in this tracker yet.

## F8: the list behind the 37 unflagged candidates

The hackathon's [extended dataset list](https://github.com/LouisFreboeuf/brightcon-hacktlon_reverse-engineering-bafu/blob/f4784965c12b82f2731e7cdcd696c11afaf434a6/results/system_terminated_extended.csv)
contains **37 distinct dataset UUIDs with `detected_by=structure`**. Each row
provides its name, location, unit, input count and elementary-flow count. This
subset includes four names prefixed `xx`; excluding those gives 33, not 22.

The [detection script](https://github.com/LouisFreboeuf/brightcon-hacktlon_reverse-engineering-bafu/blob/f4784965c12b82f2731e7cdcd696c11afaf434a6/scripts/find_system_processes.py)
selects datasets outside the flagged list with more than 50 elementary exchanges
and no production-supply inputs after excluding waste-treatment services and
infrastructure inputs measured in `unit`. It also excludes emission-only,
disposal, discharge, provision and resource-correction activities by name.
These are structural candidates; the rule and source generation matter when
comparing another search.

Community-fixes [patch 0011](https://github.com/sentier-dev/bafu-community-fixes/pull/5)
(merged 15 October 2026) sets `type=2` on 40 datasets, matched by number: the
37 structural candidates; `xxx Acrylonitrile, at plant`, which has the same
structure but which the hackathon's rule missed because one of its disposal
inputs starts with `xxx`; `Iridium production` (GLO), whose comment calls it an
aggregated inventory; and `Cabinet panel` (CH), which has no inputs but 17 kg
fossil CO₂ per m² of panel. After the patch, 142 datasets are `type=2`. The patch
records this as a community convention, not schema compliance, and the
question to BAFU stays open.

The table contains 101 flagged rows plus these 37 structural rows, for 138 total.
The separate 102nd flagged dataset, `196588 Disposal, rectangular straw bale`,
is omitted from that survey because it has no elementary-flow vector (F10).

The hackathon's [rebuild documentation](https://github.com/LouisFreboeuf/brightcon-hacktlon_reverse-engineering-bafu/blob/f4784965c12b82f2731e7cdcd696c11afaf434a6/exports/README.md#L415)
reports **22 of the 37 rebuilt**, with 15 remaining. That 22 describes rebuild
coverage. An independently identified set of 22 still needs a UUID comparison;
equal counts do not establish that they are the same subset.

Count provenance checked on 13 October 2026 against the published table at
commit `f4784965c12b82f2731e7cdcd696c11afaf434a6`. This check verifies the list
behind the reported count; it is not a new census of raw ecoSpold files, a
validation of the reconstructed inventories, or an acceptance threshold for a
current import. Continue the source comparison in
[#3](https://github.com/sentier-dev/sentier-bafu/issues/3).

## Mapping import work with Chris

[Mapping integration status](mutel-mapping-review.md) links the concrete importer
fixes from this shared work. [#14](https://github.com/sentier-dev/sentier-bafu/issues/14)
tracks conversion factors and unit compatibility;
[#15](https://github.com/sentier-dev/sentier-bafu/issues/15) tracks CF fallback
instructions the current consumer cannot apply.
[C002](contributions/C002.json) keeps the candidate method integration and
reproduction requirements. Importer issues are distinct from the raw-source
findings above; code fixes do not establish a new method's score parity.

## Reconciliation with the community patches

[reconciliation.json](reconciliation.json) keeps, for every finding and
contribution, the community patch, its authorisation, the provider response as
recorded in public patch metadata, whether a provider release has shipped the
correction, the next action with its review role, and the asks and earlier
interpretations a status change must not erase.
`python3 scripts/community.py check` fails if a status here and there disagree,
if a ledger link is missing there, or if a finding is marked `upstream-fixed`
without a named release. The [receipt](reconciliation.md) lists what the
reconciliation of 21 October 2026 preserved, updated and left unresolved.

## How a finding moves

1. **Open an issue** with the *BAFU data finding* template: dataset code, release,
   what you measured and how, why it cannot be right, exposure if known. It gets
   `bafu-finding` + `needs-triage`.
2. **A second person re-measures** on the release files (never on an import) and
   drops `needs-triage`, or sets `withdrawn` with the reason — a withdrawn finding
   stays in the table.
3. **A row is added here** with the status and the issue link.
4. **Batches go to BAFU** (lca@bafu.admin.ch) through the recommendations tracker;
   the issue gets `upstream-reported` and the date, then `upstream-fixed` with the
   release that fixed it.

A finding that a contribution layer works around gets `handled-in-layer`; the
upstream question stays open until BAFU answers it.
