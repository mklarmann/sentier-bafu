"""Independent re-scoring of the PR's leave-one-out forecast.

Usage: python -I eval_forecast.py <pr_src_dir> <inventory_root> <out_json>
Imports the PR's own build_family/solve_member (read beforehand) and rescores.
"""
import json
import sys

import numpy as np
import pandas as pd

SRC, ROOT, OUT = sys.argv[1:4]
sys.path.insert(0, SRC)
from model import load, build_family  # noqa: E402
import forecast_superstructure as fs  # noqa: E402

FAMILY = "Electricity, production mix"
ACT = 1e-6


def is_country(loc):
    return isinstance(loc, str) and len(loc) == 2 and loc.isalpha() and loc.isupper()


def score(real_by_slot, solved, candidate_slots, output_slots):
    """Mirror solve_member's metric code exactly; return also honest F1."""
    rows = [{"slot_id": s, "real": real_by_slot.get(s, 0.0), "solved": solved[s]} for s in candidate_slots]
    unseen = sorted(set(real_by_slot) - set(candidate_slots) - set(output_slots))
    rows += [{"slot_id": s, "real": real_by_slot.get(s, 0.0), "solved": np.nan} for s in unseen]
    c = pd.DataFrame(rows)
    c["err"] = (c["real"] - c["solved"]).abs()
    mae = c["err"].dropna().mean()
    ra = set(c[c.real > ACT].slot_id)
    sa = set(c[c.solved.fillna(0) > ACT].slot_id)
    tp = len(ra & sa)
    p = tp / len(sa) if sa else np.nan
    r = tp / len(ra) if ra else np.nan
    f1 = (2 * p * r / (p + r)) if (p and r) else np.nan
    return mae, p, r, f1


def baseline_predict(train, candidate_slots):
    members = train["process_id"].unique()
    n = len(members)
    # per-member per-slot amount (sum duplicates within a member)
    piv = train[train.slot_id.isin(candidate_slots)].groupby(["process_id", "slot_id"])["amount"].sum().unstack(fill_value=0.0)
    piv = piv.reindex(index=members, columns=candidate_slots, fill_value=0.0)
    freq = (piv > ACT).sum(axis=0) / n
    mean = piv.mean(axis=0)
    chosen = [s for s in candidate_slots if freq[s] >= 0.5]
    tot = sum(mean[s] for s in chosen)
    return {s: (float(mean[s] / tot) if (s in chosen and tot > 0) else 0.0) for s in candidate_slots}


def main():
    P, E = load(ROOT)
    structure, values, proc_meta = build_family(P, E, FAMILY)
    output_slots = structure[structure.direction == "output"].slot_id.tolist()
    input_slots = structure[structure.direction == "input"].slot_id.tolist()
    locs = proc_meta["location"].tolist()

    per = []
    for loc in locs:
        rec = {"location": loc, "country": is_country(loc)}
        for anchor in ("global", "regional"):
            r = fs.solve_member(structure, values, proc_meta, loc, anchor=anchor)
            rec[anchor] = {"status": r["status"], "mae": r["mae"], "p": r["precision"], "r": r["recall"], "f1": r["f1"]}
        # baseline, same training set / candidate set as solve_member
        train = values[values.location != loc]
        real = values[values.location == loc]
        cand = [s for s in input_slots if (train.slot_id == s).any()]
        real_by_slot_pr = dict(zip(real.slot_id, real.amount))          # PR's (last row wins)
        real_by_slot_sum = real.groupby("slot_id").amount.sum().to_dict()  # summed duplicates
        pred = baseline_predict(train, cand)
        b = score(real_by_slot_pr, pred, cand, output_slots)
        rec["baseline"] = dict(zip(["mae", "p", "r", "f1"], b))
        rec["dup_slot_rows"] = int((real.groupby("slot_id").size() > 1).sum())
        rec["slot15_pr_vs_sum"] = [float(real_by_slot_pr.get(15, 0.0)), float(real_by_slot_sum.get(15, 0.0))]
        # sensitivity: retrain without aggregates (countries only)
        if is_country(loc):
            v_c = values[values.location.map(is_country)]
            pm_c = proc_meta[proc_meta.location.map(is_country)]
            for anchor in ("global", "regional"):
                r = fs.solve_member(structure, v_c, pm_c, loc, anchor=anchor)
                rec[anchor + "_noagg_train"] = {"mae": r["mae"], "f1": r["f1"]}
            tr = v_c[v_c.location != loc]
            cand_c = [s for s in input_slots if (tr.slot_id == s).any()]
            pred = baseline_predict(tr, cand_c)
            b = score(real_by_slot_pr, pred, cand_c, output_slots)
            rec["baseline_noagg_train"] = {"mae": b[0], "f1": b[3]}
        per.append(rec)

    def agg(key, subset, nan_as_zero, sub=None):
        rows = [x[key] for x in per if subset(x) and key in x]
        f1 = np.array([np.nan if r["f1"] is None else r["f1"] for r in rows], dtype=float)
        mae = np.array([r["mae"] for r in rows], dtype=float)
        out = {"n": len(rows), "mae": float(np.nanmean(mae)), "f1": float(np.nan_to_num(f1).mean() if nan_as_zero else np.nanmean(f1)),
               "f1_undefined": int(np.isnan(f1).sum())}
        if "p" in rows[0]:
            p = np.array([r["p"] for r in rows], dtype=float); rc = np.array([r["r"] for r in rows], dtype=float)
            out["precision"] = float(np.nan_to_num(p).mean() if nan_as_zero else np.nanmean(p))
            out["recall"] = float(np.nan_to_num(rc).mean() if nan_as_zero else np.nanmean(rc))
        return out

    allm = lambda x: True
    ctry = lambda x: x["country"]
    summary = {}
    for k in ("global", "regional", "baseline"):
        summary[k] = {
            "as_shipped_scoring_all_81": agg(k, allm, False),
            "nan_as_zero_all_81": agg(k, allm, True),
            "honest_countries_nan_as_zero": agg(k, ctry, True),
        }
    for k in ("global_noagg_train", "regional_noagg_train", "baseline_noagg_train"):
        summary[k] = {"honest_countries_nan_as_zero": agg(k, ctry, True)}
    summary["aggregates"] = sorted(x["location"] for x in per if not x["country"])
    summary["aggregate_slot15_pr_vs_sum"] = {x["location"]: x["slot15_pr_vs_sum"] for x in per if not x["country"]}
    summary["undefined_f1_members"] = {k: sorted(x["location"] for x in per if np.isnan(x[k]["f1"] if x[k]["f1"] is not None else np.nan)) for k in ("global", "regional", "baseline")}
    json.dump({"summary": summary, "per_member": per}, open(OUT, "w"), indent=1, default=float)
    print(json.dumps(summary, indent=1, default=float))


if __name__ == "__main__":
    main()
