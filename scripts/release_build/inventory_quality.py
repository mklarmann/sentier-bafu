"""Assess a built ecoSpold archive. The output holds only counts and quality judgements."""

import hashlib
import math
import re
import zipfile
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from sentier_diagnostics.quality.contract import Absence, Observation, Result, Verdict
from sentier_diagnostics.quality.ef import representativeness
from sentier_diagnostics.quality.engine import combine, read_rules

from release_build import adapter


def finite(value):
    if value is None:
        return None
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except ValueError:
        return None


def declares_spread(row):
    kind = row.get("uncertaintyType")
    spread = finite(row.get("standardDeviation95"))
    if kind in {"1", "2"}:
        return spread is not None and spread > (1 if kind == "1" else 0)
    low, high = finite(row.get("minValue")), finite(row.get("maxValue"))
    return kind in {"3", "4"} and low is not None and high is not None and low < high


@dataclass
class Inventory:
    number: str
    unit: str
    reference_ok: bool
    other: int
    spreads: int
    negative: int
    amounts: int
    location: str | None
    inputs: list[tuple[str | None, str | None, str | None]]
    end_year: int | None


def read(dataset):
    ref = dataset.find("metaInformation/processInformation/referenceFunction")
    unit = ref.get("unit", "") if ref is not None else ""
    rows = dataset.findall("flowData/exchange")
    production = [r for r in rows if adapter._kind(r) == "production"]
    other = [r for r in rows if adapter._kind(r) != "production"]
    amounts = [v for r in other if (v := finite(r.get("meanValue"))) is not None]
    reference_ok = bool(
        len(production) == 1
        and unit
        and production[0].get("unit") == unit
        and ref.get("name") == production[0].get("name")
        and finite(ref.get("amount")) not in (None, 0)
        and finite(production[0].get("meanValue")) == finite(ref.get("amount"))
    )
    geography = dataset.find("metaInformation/processInformation/geography")
    inputs = [
        (r.get("number"), r.get("unit"), r.get("location"))
        for r in other
        if adapter._kind(r) == "technosphere"
    ]
    period = dataset.find("metaInformation/processInformation/timePeriod")
    year = None
    if period is not None:
        for tag in ("endDate", "endYearMonth", "endYear"):
            value = period.findtext(tag, "")
            if re.fullmatch(r"[1-9][0-9]{3}(?:-.*)?", value):
                year = int(value[:4])
                break
    return Inventory(
        dataset.get("number"),
        unit,
        reference_ok,
        len(other),
        sum(map(declares_spread, other)),
        sum(n < 0 for n in amounts),
        len(amounts),
        geography.get("location") if geography is not None else None,
        inputs,
        year,
    )


def check(key, numerator, denominator, method, *, warn=False):
    if denominator == 0:
        return Result.absent(key, Absence.NO_EVIDENCE, "No eligible exchanges to evaluate.")
    full = numerator == denominator
    verdict = Verdict.PASS if full else Verdict.WARN if warn else Verdict.FAIL
    value = 1 if full else 0.5 if warn else 0
    return Result.measured(
        key,
        verdict,
        value,
        "{met} of {total} meet the criterion.",
        [
            Observation("met", numerator, how=method),
            Observation("total", denominator, how="Eligible observations in this dataset"),
        ],
        evaluated=denominator,
    )


def criteria(item, units):
    resolved = sum(bool(unit) and units.get(code) == unit for code, unit, _ in item.inputs)
    return [
        check(
            "reference",
            int(item.reference_ok),
            1,
            "One reference output matching the product name, amount and unit",
        ),
        check(
            "suppliers",
            resolved,
            len(item.inputs),
            "Supplier number resolves to a unique dataset in the declared unit",
        )
        if item.inputs
        else Result.not_applicable("suppliers", "No technosphere exchanges."),
        check(
            "exchanges",
            int(item.other > 0),
            1,
            "Dataset includes at least one exchange besides production",
        ),
        check(
            "uncertainty",
            item.spreads,
            item.other,
            "Exchange has a recognised uncertainty type and spread",
        ),
        check(
            "signs",
            item.amounts - item.negative,
            item.other,
            "Exchange has a finite, non-negative amount",
            warn=True,
        ),
    ]


def assess(archive, rules_file, *, expected_digest, year, case_codes=()):
    with Path(archive).open("rb") as stream:
        if hashlib.file_digest(stream, "sha256").hexdigest() != expected_digest:
            raise ValueError("Inventory archive checksum differs from the build record")
    inventories = []
    with zipfile.ZipFile(archive) as z:
        for name in z.namelist():
            if not name.lower().endswith(".xml"):
                continue
            root, _ = adapter._parse(z.read(name), name)
            for dataset in root.findall("dataset"):
                adapter._restore_numbers(dataset, name, adapter.Receipt())
                inventories.append(read(dataset))
    if not inventories:
        raise ValueError("Inventory archive contains no datasets")
    rules = read_rules(rules_file, shown="quality/criteria.json")
    counts = Counter(i.number for i in inventories)
    units = {i.number: i.unit for i in inventories if counts[i.number] == 1}
    bands, checks, dated = Counter(), {key: Counter() for key in rules.weights}, Counter()
    total, graded, examples = 0.0, 0, {}
    locations = {i.number: i.location for i in inventories if counts[i.number] == 1}
    geography = Counter()
    for item in inventories:
        results = criteria(item, units)
        standing = combine(results, rules)
        if standing.band is not None:
            graded += 1
            total += standing.mean
        bands[standing.said] += 1
        for r in results:
            checks[r.criterion][r.said] += 1
        if item.end_year:
            expired = max(0, year - item.end_year)
            dated["dated"] += 1
            dated["past_end_year"] += int(expired > 0)
        for code, _, place in item.inputs:
            geography["inputs"] += 1
            known = locations.get(code)
            if place and known:
                geography["comparable"] += 1
                same = place == known
                geography["match"] += same
                # A mismatch by itself does not establish the degree of geographical deviation.
                rating = representativeness(geography=0 if same else None)
                geography["ef_connection_rated"] += int(rating is not None)
        if item.number in case_codes and counts[item.number] == 1:
            examples[item.number] = {
                "score": standing.mean if standing.band else None,
                "band": standing.said,
                "criteria": {r.criterion: r.said for r in results},
            }
    return {
        "format": "bafu/inventory-quality/1",
        "archive_sha256": expected_digest,
        "rules_sha256": rules.sha256,
        "year": year,
        "datasets": len(inventories),
        "graded": graded,
        "mean": round(total / graded, 6) if graded else None,
        "bands": dict(bands),
        "criteria": {k: dict(v) for k, v in checks.items()},
        "periods": dict(dated),
        "supplier_geography": dict(geography),
        "case_datasets": examples,
    }
