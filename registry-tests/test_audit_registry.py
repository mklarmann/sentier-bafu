import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

spec = importlib.util.spec_from_file_location(
    "audit_registry", Path(__file__).resolve().parents[1] / "scripts/audit_registry.py"
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def seed(root):
    path = root / "registry"
    path.mkdir()
    (root / "manifest.json").write_text(
        json.dumps(
            {
                "counts": {"exchanges": 3, "processes": 1},
                "source": "synthetic",
                "source_version": "test",
                "sources": [],
            }
        )
    )
    pd.DataFrame([{"bw_id": 1}]).to_parquet(path / "processes.parquet")
    pd.DataFrame(
        [
            {
                "bw_id": 2,
                "database": "bio",
                "code": "methane",
                "name": "Methane",
                "categories": "air::urban",
                "unit": "kg",
            }
        ]
    ).to_parquet(path / "biosphere.parquet")
    pd.DataFrame(
        [
            {"process_bw_id": 1, "input_bw_id": 1, "type": "production", "amount": 1.0},
            {
                "process_bw_id": 1,
                "input_bw_id": 1,
                "type": "technosphere",
                "amount": 0.2,
            },
            {"process_bw_id": 1, "input_bw_id": 2, "type": "biosphere", "amount": 1.0},
        ]
    ).to_parquet(path / "exchanges.parquet")
    pd.DataFrame([{"method_id": "ef-3.1:climate-change"}]).to_parquet(path / "methods.parquet")
    pd.DataFrame(
        [{"method_id": "ef-3.1:climate-change", "flow_bw_id": 2, "factor": 0.0}]
    ).to_parquet(path / "characterization-factors.parquet")


class AuditRegistry(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        seed(self.root)

    def tearDown(self):
        self.temp.cleanup()

    def test_explicit_zero_and_non_production_self_loop(self):
        result = module.audit(self.root)
        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["served_counts"]["technosphere"], 1)
        self.assertEqual(result["methods"][0]["explicit_zero_flows"], 1)

    def test_missing_methane_factor_fails(self):
        path = self.root / "registry/characterization-factors.parquet"
        pd.read_parquet(path).iloc[:0].to_parquet(path)
        result = module.audit(self.root)
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["methods"][0]["missing_core_gases"][0]["code"], "methane")

    def test_dangling_target_fails(self):
        path = self.root / "registry/exchanges.parquet"
        df = pd.read_parquet(path)
        df.loc[1, "input_bw_id"] = 999
        df.to_parquet(path)
        self.assertTrue(any("missing target" in e for e in module.audit(self.root)["errors"]))

    def test_duplicate_factor_fails(self):
        path = self.root / "registry/characterization-factors.parquet"
        df = pd.read_parquet(path)
        pd.concat([df, df]).to_parquet(path)
        self.assertTrue(
            any("Duplicate method/flow" in e for e in module.audit(self.root)["errors"])
        )


if __name__ == "__main__":
    unittest.main()
