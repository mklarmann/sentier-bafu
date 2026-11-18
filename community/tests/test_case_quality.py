"""A case remains a native patch input. Quality measurements track the exact export."""

import hashlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
import sys
import zipfile
from xml.etree.ElementTree import Element

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from sitebuild import cases

try:
    from release_build.inventory_quality import assess, declares_spread
except ImportError:
    assess = None


@unittest.skipUnless(importlib.util.find_spec("markdown"), "the site build needs Markdown")
class CaseRecords(unittest.TestCase):
    def test_sources_cases_and_registered_patches_agree(self):
        import build_site
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            site = build_site.Site(out, offline=True)
            site.build()
            rid = "F1"
            native = json.loads((ROOT / "community/findings/0/F1.json").read_text())
            self.assertEqual(json.loads((out / "api/v1/cases/F1.json").read_text()), native)
            record = next(r for r in json.loads((out / "api/v1/cases.json").read_text())["cases"] if r["id"] == rid)
            self.assertIn("0001-strawberry-polyethylene-disposal", record["patches"])
            self.assertTrue({"report-F1", "answer-F1", "release-2026-v1", "inventory-188725"} <= set(record["sources"]))
            self.assertIn(rid, cases.sources(site)["answer-F1"]["cases"])
            self.assertEqual(cases.sources(site)["C001"]["cases"], [])
            self.assertIn("No matching inventory archive", (out / "quality.html").read_text())


@unittest.skipIf(assess is None, "the inventory measurement dependencies are installed by Pages")
class InventoryQuality(unittest.TestCase):
    def test_uncertainty_needs_a_nonzero_spread(self):
        for kind, key, constant, spread in [("1", "standardDeviation95", "1", "1.1"),
                                            ("2", "standardDeviation95", "0", "0.1"),
                                            ("3", "maxValue", "2", "3"), ("4", "maxValue", "2", "3")]:
            row = Element("exchange", uncertaintyType=kind, minValue="2")
            row.set(key, constant)
            self.assertFalse(declares_spread(row))
            row.set(key, spread)
            self.assertTrue(declares_spread(row))

    def test_real_xml_roles_score_and_missing_evidence_stays_visible(self):
        def xml(code, other):
            return f'''<ecoSpold><dataset number="{code}"><metaInformation><processInformation>
                <referenceFunction name="Product" unit="kg" amount="1"/>
                <timePeriod><endYear>2020</endYear></timePeriod></processInformation></metaInformation>
                <flowData><exchange number="{code}" name="Product" meanValue="1" unit="kg">
                <outputGroup>0</outputGroup></exchange>{other}</flowData></dataset></ecoSpold>'''
        row = '<exchange number="9" meanValue="-1" unit="kg" uncertaintyType="0"><inputGroup>5</inputGroup></exchange>'
        with tempfile.TemporaryDirectory() as tmp:
            archive = Path(tmp) / "export.zip"
            with zipfile.ZipFile(archive, "w") as z:
                z.writestr("process_1.xml", xml("1", row))
                z.writestr("process_2.xml", xml("2", ""))
            digest = hashlib.sha256(archive.read_bytes()).hexdigest()
            rules = ROOT / "quality/criteria.json"
            with self.assertRaisesRegex(ValueError, "checksum"):
                assess(archive, rules, expected_digest="0" * 64, year=2026)
            report = assess(archive, rules, expected_digest=digest, year=2026, case_codes={"1", "2"})
            self.assertEqual(report["datasets"], 2)
            self.assertEqual(report["criteria"]["reference"], {"pass": 2})
            self.assertEqual(report["criteria"]["suppliers"], {"fail": 1, "not_applicable": 1})
            self.assertEqual(report["criteria"]["signs"], {"warn": 1, "absent": 1})
            self.assertEqual(report["case_datasets"]["1"]["band"], "poor")
            self.assertEqual(report["periods"]["past_end_year"], 2)
            self.assertEqual(report["supplier_geography"].get("ef_connection_rated", 0), 0)
