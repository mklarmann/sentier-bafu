"""The audit of an installed Brightway database.

The helpers are tested on plain data. The audit itself runs on a two-dataset project that
the test writes into a temporary Brightway folder, in a subprocess, so that no existing
Brightway project is opened. Those tests are skipped where bw2data isn't installed.
"""

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from collections import Counter
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY / "scripts"))

from release_build import audit_brightway as audit  # noqa: E402

HAS_SCIPY = importlib.util.find_spec("scipy") is not None
HAS_BRIGHTWAY = all(importlib.util.find_spec(name) for name in ("bw2data", "bw2calc"))
SCRIPT = REPOSITORY / "scripts" / "release_build" / "audit_brightway.py"

INVENTORY, RESIDUAL = "bafu-2026", "bafu-2026-residual"


class Helpers(unittest.TestCase):
    def test_range_flag(self):
        self.assertIsNone(audit.range_flag(1.0, [0.5, 2.0]))
        self.assertIsNone(audit.range_flag(1e9, None))
        self.assertIn("above", audit.range_flag(3.0, [0.5, 2.0]))
        self.assertIn("below", audit.range_flag(0.1, [0.5, 2.0]))
        self.assertIn("finite", audit.range_flag(float("nan"), None))

    def test_exchange_accounting_counts_kinds_and_targets(self):
        nodes = {(INVENTORY, "a"), (INVENTORY, "b"), (audit.BIOSPHERE_DB, "co2"), (RESIDUAL, "r")}
        rows = [
            (INVENTORY, "a", "production"),
            (INVENTORY, "b", "production"),
            (INVENTORY, "a", "technosphere"),
            (audit.BIOSPHERE_DB, "co2", "biosphere"),
            (RESIDUAL, "r", "biosphere"),
        ]
        result = audit.exchange_accounting(rows, nodes, INVENTORY, RESIDUAL)
        self.assertEqual(
            result["exchanges"],
            {"biosphere": 2, "production": 2, "technosphere": 1, "total": 5, "other_kinds": 0},
        )
        self.assertEqual(set(result["unlinked"].values()), {0})
        self.assertEqual(
            result["biosphere_targets"],
            {"ef_3_1": 1, "no_ef_3_1_flow": 1, "other_databases": {}},
        )

    def test_exchange_accounting_finds_what_is_not_linked(self):
        nodes = {(INVENTORY, "a")}
        rows = [
            (INVENTORY, "a", "production"),
            (INVENTORY, "gone", "technosphere"),
            ("elsewhere", "x", "technosphere"),
            (audit.BIOSPHERE_DB, "gone", "biosphere"),
            ("biosphere3", "y", "biosphere"),
            (INVENTORY, "a", "substitution"),
        ]
        result = audit.exchange_accounting(rows, nodes, INVENTORY, RESIDUAL)
        self.assertEqual(result["unlinked"]["technosphere"], 2)
        self.assertEqual(result["unlinked"]["biosphere"], 2)
        self.assertEqual(
            result["unlinked"]["technosphere_or_production_outside_inventory_database"], 1
        )
        self.assertEqual(result["biosphere_targets"]["other_databases"], {"biosphere3": 1})
        self.assertEqual(result["exchanges"]["other_kinds"], 1)

    def test_a_zero_factor_counts_as_a_factor(self):
        emitted = Counter(
            {(audit.BIOSPHERE_DB, "co2"): 4, (audit.BIOSPHERE_DB, "bio"): 2, (RESIDUAL, "r"): 3}
        )
        factors = {
            (audit.BIOSPHERE_DB, "co2"): 1.0,
            (audit.BIOSPHERE_DB, "bio"): 0.0,
            (audit.BIOSPHERE_DB, "unused"): 5.0,
        }
        result = audit.method_coverage(emitted, factors, RESIDUAL)
        self.assertEqual(result["factors"], 3)
        self.assertEqual(result["flows_used"], 3)
        self.assertEqual(result["flows_with_factor"], 2)
        self.assertEqual(result["flows_with_zero_factor"], 1)
        self.assertEqual(result["flows_without_factor"], 1)
        self.assertEqual(result["flows_without_factor_no_ef_3_1_flow"], 1)
        self.assertEqual(result["exchanges_with_factor"], 6)
        self.assertEqual(result["exchanges_without_factor"], 3)

    def test_the_committed_sample_is_valid(self):
        sample = audit.load_sample(SCRIPT.with_name("score_sample.json"))
        self.assertGreaterEqual(len(sample), 20)
        for item in sample:
            self.assertRegex(item["code"], r"^[0-9a-f]{8}-[0-9a-f]{4}-")
            self.assertTrue(item["name"] and item["location"] and item["why"])

    def test_sample_with_a_repeated_code_or_bad_range_is_refused(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "sample.json"
            path.write_text(json.dumps({"datasets": [{"code": "a"}, {"code": "a"}]}))
            with self.assertRaisesRegex(audit.AuditError, "repeat"):
                audit.load_sample(path)
            path.write_text(json.dumps({"datasets": [{"code": "a", "plausible_range": [2, 1]}]}))
            with self.assertRaisesRegex(audit.AuditError, "plausible_range"):
                audit.load_sample(path)


@unittest.skipUnless(HAS_SCIPY, "scipy is not installed here")
class Solves(unittest.TestCase):
    def setUp(self):
        import numpy as np
        import scipy.sparse as sp

        rng = np.random.default_rng(1)
        dense = np.eye(40) + 0.1 * rng.random((40, 40)) * (rng.random((40, 40)) < 0.1)
        # Columns of different size, as in an inventory with mixed units
        self.dense = dense * np.logspace(-3, 3, 40)
        self.lu = audit.Factorised(sp.csc_matrix(self.dense))
        self.rhs = rng.random((40, 3))

    def test_solve_and_transposed_solve_match_a_dense_solve(self):
        import numpy as np

        np.testing.assert_allclose(
            self.lu.solve(self.rhs), np.linalg.solve(self.dense, self.rhs), rtol=1e-6
        )
        np.testing.assert_allclose(
            self.lu.solve_transposed(self.rhs), np.linalg.solve(self.dense.T, self.rhs), rtol=1e-6
        )
        self.assertLessEqual(self.lu.worst_residual, audit.RESIDUAL_TOLERANCE)

    def test_a_solution_that_misses_the_tolerance_is_refused(self):
        import numpy as np

        def wrong(values):
            return np.zeros_like(values)

        with self.assertRaisesRegex(audit.AuditError, "relative residual"):
            self.lu._refined(self.lu.matrix, self.rhs, wrong, "solve")

    def test_refinement_repairs_an_inexact_solver(self):
        import numpy as np

        exact = self.lu._lu.solve

        def inexact(values):
            return exact(values) * (1 + 1e-4)

        solution = self.lu._refined(self.lu.matrix, self.rhs, inexact, "solve")
        np.testing.assert_allclose(solution, np.linalg.solve(self.dense, self.rhs), rtol=1e-6)
        self.assertGreater(self.lu.refinements, 0)

    def test_a_singular_matrix_is_refused(self):
        import numpy as np
        import scipy.sparse as sp

        with self.assertRaises(audit.AuditError):
            audit.Factorised(sp.csc_matrix(np.zeros((3, 3))))


PROJECT = textwrap.dedent(
    """
    import sys
    import bw2data as bd

    bd.projects.set_current("mini")
    bio, residual, inventory = "ef-3.1-biosphere", "bafu-2026-residual", "bafu-2026"

    def flow(name):
        return {"name": name, "type": "emission", "unit": "kilogram", "categories": ("air",),
                "exchanges": []}

    bd.Database(bio).write({(bio, code): flow(code) for code in ("co2", "ch4", "unused")})
    bd.Database(residual).write({(residual, "r1"): flow("No EF flow")})

    def process(code, name, exchanges):
        return {"name": name, "reference product": name, "unit": "kilogram", "location": "CH",
                "type": "process", "production amount": 1.0,
                "exchanges": [{"input": (inventory, code), "type": "production", "amount": 1.0},
                              *exchanges]}

    bd.Database(inventory).write({
        (inventory, "a"): process("a", "Product A", [
            {"input": (bio, "co2"), "type": "biosphere", "amount": 2.0},
            {"input": (residual, "r1"), "type": "biosphere", "amount": 5.0}]),
        (inventory, "b"): process("b", "Product B", [
            {"input": (inventory, "a"), "type": "technosphere", "amount": 0.5},
            {"input": (bio, "ch4"), "type": "biosphere", "amount": 0.1}]),
    })
    method = bd.Method(("sentier", "EF v3.1", "Climate change"))
    method.register(unit="kg CO2 eq", sentier_method_id="ef-3.1:climate-change")
    method.write([((bio, "co2"), 1.0), ((bio, "ch4"), 30.0), ((bio, "unused"), 7.0)])
    if "dangling" in sys.argv:
        from bw2data.backends import ExchangeDataset
        ExchangeDataset.create(
            input_database=inventory, input_code="gone", output_database=inventory,
            output_code="b", type="technosphere",
            data={"input": (inventory, "gone"), "output": (inventory, "b"),
                  "type": "technosphere", "amount": 1.0})
    """
)
SAMPLE = {
    "datasets": [
        {
            "code": "a",
            "name": "Product A",
            "location": "CH",
            "plausible_range": [1.0, 3.0],
            "documented_score": {"value": 2.0, "source": "by hand"},
        },
        {"code": "b", "name": "Product B", "location": "CH", "plausible_range": [0.1, 1.0]},
    ]
}


@unittest.skipUnless(HAS_BRIGHTWAY, "bw2data and bw2calc are not installed here")
class AuditOfAProject(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.env = {**os.environ, "BRIGHTWAY2_DIR": str(self.root / "brightway")}
        (self.root / "brightway").mkdir()
        (self.root / "sample.json").write_text(json.dumps(SAMPLE))

    def tearDown(self):
        self.temp.cleanup()

    def write_project(self, *arguments):
        subprocess.run(
            [sys.executable, "-c", PROJECT, *arguments],
            env=self.env,
            check=True,
            capture_output=True,
        )

    def run_audit(self, *arguments, env=None):
        command = [
            *(sys.executable, str(SCRIPT), "--project", "mini"),
            *("--sample", str(self.root / "sample.json"), "--out", str(self.root / "audit")),
            *arguments,
        ]
        return subprocess.run(command, env=env or self.env, capture_output=True, text=True)

    def test_counts_coverage_and_scores(self):
        self.write_project()
        done = self.run_audit("--label", "fixture")
        self.assertEqual(done.returncode, 0, done.stderr)
        result = json.loads((self.root / "audit" / "audit.json").read_text())
        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["label"], "fixture")
        self.assertEqual(result["datasets"], 2)
        self.assertEqual(
            result["exchanges"],
            {"biosphere": 3, "production": 2, "technosphere": 1, "total": 6, "other_kinds": 0},
        )
        self.assertEqual(set(result["unlinked"].values()), {0})
        self.assertEqual(result["biosphere_targets"]["ef_3_1"], 2)
        self.assertEqual(result["biosphere_targets"]["no_ef_3_1_flow"], 1)
        flows = result["elementary_flows"]
        self.assertEqual((flows["used"], flows["on_ef_3_1"], flows["no_ef_3_1_flow"]), (3, 2, 1))
        self.assertEqual(flows["no_ef_3_1_flow_names"], ["No EF flow"])
        (method,) = result["methods"]
        self.assertEqual(method["id"], "ef-3.1:climate-change")
        self.assertEqual((method["factors"], method["flows_with_factor"]), (3, 2))
        self.assertEqual(method["flows_without_factor"], 1)
        self.assertEqual(
            (method["exchanges_with_factor"], method["exchanges_without_factor"]), (2, 1)
        )
        scores = {entry["code"]: entry for entry in result["scores"]["sample"]}
        # Brightway stores amounts and factors as 32-bit floats: 0.1 is not exact
        self.assertAlmostEqual(scores["a"]["score"], 2.0, places=6)
        self.assertAlmostEqual(scores["b"]["score"], 0.5 * 2.0 + 0.1 * 30.0, places=6)
        self.assertTrue(scores["a"]["documented_score"]["agrees"])
        self.assertIsNone(scores["a"]["flag"])
        self.assertIn("above", scores["b"]["flag"])
        self.assertEqual(len(result["scores"]["range_flags"]), 1)
        self.assertEqual(result["scores"]["checks"]["recomputed_with_bw2calc"], ["a", "b"])
        lines = (self.root / "audit" / "scores.csv").read_text().splitlines()
        self.assertEqual(lines[0], "code,ef-3.1:climate-change")
        self.assertEqual([line.split(",")[0] for line in lines[1:]], ["a", "b"])

    def test_a_score_outside_its_range_fails_only_when_asked(self):
        self.write_project()
        self.assertEqual(self.run_audit().returncode, 0)
        self.assertEqual(self.run_audit("--fail-on-range").returncode, 1)

    def test_an_exchange_without_a_supplier_fails_the_audit(self):
        self.write_project("dangling")
        done = self.run_audit()
        self.assertEqual(done.returncode, 1, done.stderr)
        result = json.loads((self.root / "audit" / "audit.json").read_text())
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["unlinked"]["technosphere"], 1)

    def test_a_sample_dataset_that_is_missing_stops_the_audit(self):
        self.write_project()
        sample = {"datasets": [{"code": "not-there"}]}
        (self.root / "sample.json").write_text(json.dumps(sample))
        done = self.run_audit()
        self.assertEqual(done.returncode, 2)
        self.assertIn("not-there", done.stderr)

    def test_it_refuses_to_run_without_its_own_brightway_folder(self):
        env = {k: v for k, v in self.env.items() if k != "BRIGHTWAY2_DIR"}
        done = self.run_audit(env=env)
        self.assertEqual(done.returncode, 2)
        self.assertIn("BRIGHTWAY2_DIR is not set", done.stderr)

    def test_an_unknown_project_is_refused(self):
        done = self.run_audit()
        self.assertEqual(done.returncode, 2)
        self.assertIn("No Brightway project", done.stderr)


if __name__ == "__main__":
    unittest.main()
