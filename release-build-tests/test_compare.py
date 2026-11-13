"""Comparing two builds: which rows changed, which step explains them, which scores moved.

Synthetic tables only. The tests that need pandas are skipped where it isn't installed.
"""

import importlib.util
import sys
import unittest
from collections import namedtuple
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY / "scripts"))

from release_build import compare_builds as compare  # noqa: E402

HAS_PANDAS = importlib.util.find_spec("pandas") is not None
AMOUNT = "0001-strawberry-polyethylene-disposal"
LOCATION = "0002-supplier-locations"
NAMES = "0007-flow-names"
COMPARTMENTS = "0008-flow-compartments"


class Explain(unittest.TestCase):
    def test_a_recorded_step_that_changes_the_field_explains_the_row(self):
        self.assertEqual(compare.explain({"amount"}, [AMOUNT, "0010-links"], "exchange"), [AMOUNT])
        self.assertEqual(compare.explain({"location"}, [LOCATION], "exchange"), [LOCATION])

    def test_a_step_on_another_dataset_or_another_field_does_not(self):
        self.assertEqual(compare.explain({"amount"}, [], "exchange"), [])
        self.assertEqual(compare.explain({"amount"}, [LOCATION], "exchange"), [])
        self.assertEqual(compare.explain({"unit"}, [AMOUNT, NAMES], "exchange"), [])
        self.assertEqual(compare.explain({"amount"}, ["not-in-the-table"], "exchange"), [])

    def test_rename_and_compartment_move_are_told_apart(self):
        both = [NAMES, COMPARTMENTS]
        self.assertEqual(compare.explain({"flow", "name"}, both, "exchange"), [NAMES])
        self.assertEqual(compare.explain({"flow"}, both, "exchange"), [COMPARTMENTS])
        self.assertEqual(compare.explain({"flow"}, [NAMES], "exchange"), [NAMES])

    def test_two_steps_together_can_explain_one_row(self):
        self.assertEqual(
            compare.explain({"amount", "location"}, [AMOUNT, LOCATION], "exchange"),
            sorted([AMOUNT, LOCATION]),
        )

    def test_dataset_fields_have_their_own_table(self):
        self.assertEqual(
            compare.explain({"location"}, ["location-codes"], "process"), ["location-codes"]
        )
        self.assertEqual(compare.explain({"location"}, [LOCATION], "process"), [])


class Graph(unittest.TestCase):
    consumers = {"a": {"b"}, "b": {"c", "d"}, "x": {"y"}, "d": {"b"}}

    def test_downstream_follows_consumers_and_includes_the_seed(self):
        self.assertEqual(compare.downstream({"a"}, self.consumers), {"a", "b", "c", "d"})
        self.assertEqual(compare.downstream({"c"}, self.consumers), {"c"})
        self.assertEqual(compare.downstream(set(), self.consumers), set())

    def test_attribute_names_the_steps_upstream_of_each_moved_dataset(self):
        reach = {"one": {"a", "b"}, "two": {"b", "c"}}
        self.assertEqual(
            compare.attribute({"a", "b", "z"}, reach), {"a": ["one"], "b": ["one", "two"], "z": []}
        )


Entry = namedtuple("Entry", "target_code conversion_factor")
Method = namedtuple("Method", "method_id cfs")


@unittest.skipUnless(HAS_PANDAS, "pandas is not installed here")
class Tables(unittest.TestCase):
    def inventory(self, **changes):
        import pandas as pd

        processes = pd.DataFrame(
            {
                "process_id": ["farm", "gas", "mix"],
                "name": ["Fruit", "Gas, at production", "Mix"],
                "location": ["CH", "NO", changes.get("mix_location", "Europe without Switzerland")],
            }
        )
        rows = [
            ("farm", "farm", "Fruit", "production", 1.0, None),
            ("farm", "waste", "Disposal", "technosphere", changes.get("disposal", 100.0), "CH"),
            ("farm", "co2-old", "Carbon dioxide", "biosphere", 1.0, None),
            ("gas", "gas", "Gas, at production", "production", 1.0, None),
            (
                "gas",
                changes.get("gas_flow", "gas-old"),
                changes.get("gas_name", "Gas, natural/m3"),
                "biosphere",
                1.0,
                None,
            ),
            ("mix", "mix", "Mix", "production", 1.0, None),
            (
                "mix",
                "gas",
                "Gas, at production",
                "technosphere",
                2.0,
                changes.get("declared", "XX"),
            ),
            ("mix", "farm", "Fruit", "technosphere", 0.0, "CH"),
        ]
        columns = ["process_id", "flow", "flow_name", "flow_type", "amount", "location"]
        exchanges = pd.DataFrame(rows, columns=columns)
        exchanges["position"] = exchanges.groupby("process_id").cumcount()
        return processes, exchanges

    def setUp(self):
        self.base = self.inventory()
        self.cand = self.inventory(
            disposal=0.01,
            gas_flow="gas-new",
            gas_name="Gas, natural",
            declared="NO",
            mix_location="EURwoCH",
        )
        self.steps = {
            "farm": ["renumber-exchanges", AMOUNT],
            "gas": [NAMES, "0010-links"],
            "mix": ["location-codes", LOCATION],
        }
        self.bridge = {"gas-old": Entry("ef-gas", 35.98), "co2-old": Entry("ef-co2", 1.0)}
        self.methods = [
            Method("climate", (("ef-co2", 1.0),)),
            Method("fossils", (("ef-gas", 1.0),)),
        ]
        self.effective = compare.effective_factors(self.bridge, self.methods)

    def test_every_changed_row_is_attributed(self):
        result = compare.compare_rows(self.base, self.cand, self.steps)
        summary = result["summary"]
        self.assertEqual(summary["exchange_rows_compared"], 8)
        self.assertEqual(summary["exchange_rows_changed"], 3)
        self.assertEqual(summary["unexplained_count"], 0)
        self.assertEqual(summary["by_step"][AMOUNT], {"amount": 1, "rows": 1, "datasets": 1})
        self.assertEqual(
            summary["by_step"][NAMES], {"flow": 1, "name": 1, "rows": 1, "datasets": 1}
        )
        # Two steps recorded on "mix" can both change an exchange location: both are named
        self.assertEqual(
            summary["by_step"][f"location-codes + {LOCATION}"],
            {"location": 1, "rows": 1, "datasets": 1},
        )
        self.assertEqual(
            summary["dataset_rows_changed_by_step"], {"location-codes": {"location": 1}}
        )

    def test_a_change_no_recorded_step_explains_is_reported(self):
        result = compare.compare_rows(self.base, self.cand, {"gas": [NAMES], "mix": [LOCATION]})
        summary = result["summary"]
        self.assertEqual(summary["unexplained_count"], 2)  # the amount, and the dataset location
        self.assertIn("unexplained", summary["by_step"])
        self.assertEqual(
            {(item["dataset"], *item["fields"]) for item in summary["unexplained"]},
            {("farm", "amount"), ("mix", "location")},
        )

    def test_identical_builds_have_no_changes(self):
        summary = compare.compare_rows(self.base, self.base, {})["summary"]
        self.assertEqual(summary["exchange_rows_changed"], 0)
        self.assertEqual(summary["unexplained_count"], 0)

    def test_a_renamed_flow_that_the_mapping_does_not_know_loses_its_ef_flow(self):
        rows = compare.compare_rows(self.base, self.cand, self.steps)["rows"]
        flows = compare.compare_flows(rows, self.bridge, self.effective, {"ef-gas": "Natural Gas"})
        self.assertEqual(flows["exchanges_that_lost_their_ef_3_1_flow"], 1)
        self.assertEqual(flows["flows_that_lost_their_ef_3_1_flow"], 1)
        (flow,) = flows["flows_that_changed_identity"]
        self.assertEqual(
            (flow["name_before"], flow["name_after"]), ("Gas, natural/m3", "Gas, natural")
        )
        self.assertEqual(flow["ef_3_1_flow_before"], "Natural Gas")
        self.assertIsNone(flow["ef_3_1_flow_after"])
        self.assertEqual(flow["methods_whose_factor_changes"], ["fossils"])
        self.assertEqual(flow["steps"], [NAMES])

    def test_a_renamed_flow_that_the_mapping_knows_stays_linked(self):
        bridge = {**self.bridge, "gas-new": Entry("ef-gas", 35.98)}
        effective = compare.effective_factors(bridge, self.methods)
        rows = compare.compare_rows(self.base, self.cand, self.steps)["rows"]
        flows = compare.compare_flows(rows, bridge, effective, {})
        self.assertEqual(flows["exchanges_that_lost_their_ef_3_1_flow"], 0)
        (flow,) = flows["flows_that_changed_identity"]
        self.assertEqual(flow["methods_whose_factor_changes"], [])
        self.assertEqual(flow["ef_3_1_flow_after"], "EF 3.1 flow ef-gas")

    def test_seeds_are_the_datasets_whose_change_can_move_a_method(self):
        rows = compare.compare_rows(self.base, self.cand, self.steps)["rows"]
        seeds = compare.relevant_seeds(rows, self.effective, ["climate", "fossils"])
        self.assertEqual(dict(seeds["climate"]), {AMOUNT: {"farm"}})
        self.assertEqual(dict(seeds["fossils"]), {AMOUNT: {"farm"}, NAMES: {"gas"}})

    def test_zero_amount_inputs_are_not_supply_chain_links(self):
        graph = compare.consumer_graph(self.base[1], self.cand[1])
        self.assertEqual(dict(graph), {"waste": {"farm"}, "gas": {"mix"}})  # not farm -> mix

    def test_moved_scores_are_attributed_or_reported(self):
        import pandas as pd

        rows = compare.compare_rows(self.base, self.cand, self.steps)["rows"]
        seeds = compare.relevant_seeds(rows, self.effective, ["climate", "fossils"])
        graph = compare.consumer_graph(self.base[1], self.cand[1])
        index = pd.Index(["farm", "gas", "mix"], name="code")
        before = pd.DataFrame(
            {"climate": [300.0, 0.0, 0.0], "fossils": [5.0, 36.0, 72.0]}, index=index
        )
        after = pd.DataFrame(
            {"climate": [1.0, 0.0, 0.0], "fossils": [0.1, 0.0, 72.0 * (1 + 1e-9)]}, index=index
        )
        names = {"farm": {"name": "Fruit", "location": "CH"}}
        result = compare.compare_scores(before, after, seeds, graph, names)
        climate, fossils = result["methods"]
        self.assertEqual(climate["datasets_moved"], 1)
        self.assertEqual(climate["moved_by_step"], {AMOUNT: 1})
        self.assertEqual(climate["moved"][0]["name"], "Fruit")
        self.assertAlmostEqual(climate["moved"][0]["change_percent"], -99.6666667, places=5)
        self.assertEqual(fossils["moved_by_step"], {AMOUNT: 1, NAMES: 1})
        self.assertEqual(fossils["datasets_that_could_move"], {AMOUNT: 1, NAMES: 2})
        self.assertEqual(fossils["differences_below_tolerance"], 1)  # the solver noise on "mix"
        self.assertEqual(result["unexplained_moves"], 0)

        after.loc["mix", "climate"] = 9.0  # nothing upstream of "mix" changed for climate
        result = compare.compare_scores(before, after, seeds, graph, names)
        self.assertEqual(result["unexplained_moves"], 1)
        self.assertEqual(result["methods"][0]["moved_by_step"], {AMOUNT: 1, "unexplained": 1})

    def test_declared_supplier_location_is_compared_with_the_linked_dataset(self):
        before = compare.declared_against_linked(*self.base)
        after = compare.declared_against_linked(*self.cand)
        self.assertEqual(before["technosphere_inputs"], 3)
        self.assertEqual(before["without_a_linked_dataset"], 1)  # "waste" is not a dataset here
        self.assertEqual(
            before["declared_location_differs"] - after["declared_location_differs"], 1
        )


if __name__ == "__main__":
    unittest.main()
