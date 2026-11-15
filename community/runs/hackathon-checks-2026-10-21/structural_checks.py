"""Claims b/c/d + units-and-mass-balance check.

Usage: python -I structural_checks.py <pr_src_dir> <pinned_root> <main_root> <demo_values_parquet> <out_json>
"""
import json
import sys

import numpy as np
import pandas as pd

SRC, PINNED, MAIN, DEMO_VALUES, OUT = sys.argv[1:6]
sys.path.insert(0, SRC)
import model  # noqa: E402
from classify import classify  # noqa: E402
from forecast_superstructure import _homogeneous_unit_inputs, MASS_BALANCE_TOL  # noqa: E402

res = {}

# ---------- b: main -- what the 21 extra families are ----------
Pm, Em = model.load(MAIN)
res["main_columns_processes"] = list(Pm.columns)
sector_col = "sector" if "sector" in Pm.columns else None
fam_main = classify(MAIN)
res["main_families"] = int(len(fam_main))
# P from load() has 'sector' overwritten by folder name; read raw to get the real sector column
raw = pd.read_parquet(f"{MAIN}/data/bafu-2026-v1/processes.parquet")
res["main_raw_sector_values"] = sorted(map(str, raw["sector"].unique())) if "sector" in raw.columns else None
if "sector" in raw.columns:
    obs = raw[raw["sector"].astype(str).str.contains("obsolete", case=False)]
    res["main_obsolete_processes"] = int(len(obs))
    nonobs = raw[~raw.index.isin(obs.index)]
    lc = nonobs.groupby("reference_product")["location"].nunique()
    res["main_families_excluding_obsolete_sector"] = int((lc > 1).sum())

# ---------- pinned ----------
P, E = model.load(PINNED)
fam = classify(PINNED)
res["pinned_families"] = int(len(fam))

dup_rows = dup_fams = 0
dup_examples = []
tiny_nonzero = 0
exact_mismatch_rows = 0
exact_mismatch_fams = 0
total_rows = 0
u1_fail, u2_fail = [], []
mb_fams = 0
mb_member_total = mb_member_fail = 0
mb_fail_examples = []
mb_fail_fams = set()
mb_by_family = {}
mutation = None

for rp in fam["reference_product"]:
    s, v, pm = model.build_family(P, E, rp)
    procs, orig = model._family_slice(P, E, rp)
    orig = orig.drop(columns=["sector"]).reset_index(drop=True)
    total_rows += len(orig)
    # c: primary key (process_id, slot_id)
    d = v.duplicated(["process_id", "slot_id"], keep=False)
    if d.any():
        dup_fams += 1
        dup_rows += int(d.sum())
        if len(dup_examples) < 3:
            ex = v[d].iloc[0]
            dup_examples.append({"family": rp, "process_location": ex["location"],
                                 "flow_name": s.set_index("slot_id").loc[ex["slot_id"], "flow_name"],
                                 "rows_sharing_key": int(((v.process_id == ex.process_id) & (v.slot_id == ex.slot_id)).sum())})
    # d: tiny amounts, exact round-trip
    a = orig["amount"].astype(float).values
    tiny_nonzero += int(((a != 0) & (np.abs(a) < 1e-8)).sum())
    rebuilt = model.reconstruct(s, v, pm, rp)
    key = ["process_id", "flow_name", "direction", "flow"]
    o = orig.sort_values(key).reset_index(drop=True)
    r = rebuilt.sort_values(key).reset_index(drop=True)
    bad = np.zeros(len(o), bool)
    for c in model._EXACT_COLS:
        bad |= ~((o[c].astype(str).values == r[c].astype(str).values) | (o[c].isna().values & r[c].isna().values))
    for c in model._NUMERIC_COLS:
        x, y = o[c].astype(float).values, r[c].astype(float).values
        bad |= ~((x == y) | (np.isnan(x) & np.isnan(y)))
    exact_mismatch_rows += int(bad.sum())
    exact_mismatch_fams += int(bad.any())
    # mutation test: zero the first tiny non-zero amount in the rebuilt copy
    if mutation is None:
        idx = np.where((r["amount"].astype(float).values != 0) & (np.abs(r["amount"].astype(float).values) < 1e-8))[0]
        if len(idx):
            r2 = r.copy()
            old = float(r2.loc[idx[0], "amount"])
            r2.loc[idx[0], "amount"] = 0.0
            mutation = {"family": rp, "original_amount": old, "set_to": 0.0,
                        "compare_rows_still_ok": bool(model.compare_rows(o, r2, verbose=False))}
    # U1: one unit per (flow_name, direction, flow_type)
    nu = s.groupby(["flow_name", "direction", "flow_type"])["unit"].nunique()
    if (nu > 1).any():
        k = nu[nu > 1].index[0]
        u1_fail.append({"family": rp, "flows_with_multiple_units": int((nu > 1).sum()),
                        "example": {"flow_name": k[0], "direction": k[1], "flow_type": k[2],
                                    "units": sorted(s[(s.flow_name == k[0]) & (s.direction == k[1]) & (s.flow_type == k[2])].unit.astype(str))}})
    # U2: production exchange unit == reference_unit, one reference_unit per family
    prod = orig[orig["flow_type"] == "production"].merge(procs[["process_id", "reference_unit"]], on="process_id")
    bad_u2 = int((prod["unit"].astype(str) != prod["reference_unit"].astype(str)).sum())
    n_ref_units = procs["reference_unit"].nunique()
    if bad_u2 or n_ref_units > 1:
        u2_fail.append({"family": rp, "production_unit_ne_reference_unit": bad_u2,
                        "distinct_reference_units": sorted(procs["reference_unit"].astype(str).unique())})
    # MB: families where the forecaster would apply sum-to-one
    if _homogeneous_unit_inputs(s):
        mb_fams += 1
        inp = v[v.slot_id.isin(s[s.direction == "input"].slot_id)]
        sums = inp.groupby("process_id")["amount"].sum().reindex(pm["process_id"], fill_value=0.0)
        locs = dict(zip(pm.process_id, pm.location))
        fails = sums[(sums - 1).abs() > MASS_BALANCE_TOL]
        mb_member_total += len(sums)
        mb_member_fail += len(fails)
        mb_by_family[rp] = {"members": int(len(sums)), "fail": int(len(fails)),
                            "input_unit": (s[s.direction == "input"].unit.dropna().unique().tolist() or [None])[0]}
        if len(fails):
            mb_fail_fams.add(rp)
            if len(mb_fail_examples) < 6:
                pid = fails.index[0]
                mb_fail_examples.append({"family": rp, "location": locs[pid], "input_sum": round(float(fails.iloc[0]), 6),
                                         "input_unit": mb_by_family[rp]["input_unit"]})

res.update({
    "pinned_exchange_rows_in_families": int(total_rows),
    "c_pk_violation_rows": dup_rows, "c_pk_violation_families": dup_fams, "c_examples": dup_examples,
    "d_tiny_nonzero_amounts_lt_1e-8": tiny_nonzero,
    "d_exact_mismatch_rows": exact_mismatch_rows, "d_exact_mismatch_families": exact_mismatch_fams,
    "d_mutation": mutation,
    "U1_fail_families": len(u1_fail), "U1_examples": u1_fail[:5],
    "U2_fail_families": len(u2_fail), "U2_examples": u2_fail[:5],
    "MB_families_with_constraint": mb_fams, "MB_families_failing": len(mb_fail_fams),
    "MB_members_checked": mb_member_total, "MB_members_failing": mb_member_fail,
    "MB_examples": mb_fail_examples,
    "MB_forecast_family": mb_by_family.get("Electricity, production mix"),
})
# MB families: how many have zero passing members (constraint never holds)
res["MB_families_no_member_passes"] = sum(1 for f in mb_by_family.values() if f["fail"] == f["members"])
res["MB_input_units_of_constrained_families"] = pd.Series([f["input_unit"] for f in mb_by_family.values()]).astype(str).value_counts().head(10).to_dict()

# c on the generated demo values.parquet
dv = pd.read_parquet(DEMO_VALUES)
dd = dv.duplicated(["process_id", "slot_id"], keep=False)
res["c_demo_values_rows"] = int(len(dv))
res["c_demo_values_pk_violation_rows"] = int(dd.sum())
res["c_demo_values_pk_violation_rows_with_family_id_key"] = int(dv.duplicated(["family_id", "process_id", "slot_id"], keep=False).sum())
res["c_demo_values_unique_with_flow"] = bool(not dv.duplicated(["process_id", "slot_id", "flow"], keep=False).any())
res["c_demo_values_dups_with_flow_rows"] = int(dv.duplicated(["process_id", "slot_id", "flow"], keep=False).sum())

json.dump(res, open(OUT, "w"), indent=1, default=str)
print(json.dumps(res, indent=1, default=str))
