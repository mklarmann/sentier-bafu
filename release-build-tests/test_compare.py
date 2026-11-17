"""Comparing two builds: which rows changed, which step explains them, which scores moved.

Synthetic tables only. The tests that need pandas are skipped where it isn't installed.
"""

import importlib.util
import json
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


class StepFields(unittest.TestCase):
    """What a step that the table does not list can explain: what the run says it changed."""

    def summary(self, **fields):
        return {"steps": [{"id": id, "fields": changed} for id, changed in fields.items()]}

    def test_a_new_patch_explains_the_fields_the_run_summary_says_it_changed(self):
        fields = compare.step_fields(
            self.summary(
                **{
                    "0012-unit": {
                        "flowData/exchange/@unit": 2,
                        "metaInformation/processInformation/referenceFunction/@unit": 2,
                    },
                    "0013-amount": {"flowData/exchange/@meanValue": 1},
                    "0014-supplier": {"flowData/exchange/@number": 1},
                    "0015-direction": {"flowData/exchange/inputGroup": 1},
                }
            )
        )
        self.assertEqual(
            fields["0012-unit"], {"exchange": {"flow", "unit"}, "process": {"reference_unit"}}
        )
        self.assertEqual(fields["0013-amount"], {"exchange": {"amount"}, "process": set()})
        self.assertEqual(fields["0014-supplier"]["exchange"], {"flow"})
        self.assertEqual(fields["0015-direction"]["exchange"], {"kind"})
        self.assertEqual(
            compare.explain({"unit"}, ["0012-unit"], "exchange", fields), ["0012-unit"]
        )
        self.assertEqual(
            compare.explain({"reference_unit"}, ["0012-unit"], "process", fields), ["0012-unit"]
        )
        self.assertEqual(compare.explain({"amount"}, ["0012-unit"], "exchange", fields), [])

    def test_a_step_in_the_table_keeps_what_the_table_says(self):
        # even if a run says it changed more: that is then an unexplained row, on purpose
        fields = compare.step_fields(
            self.summary(
                **{AMOUNT: {"flowData/exchange/@meanValue": 3, "flowData/exchange/@unit": 3}}
            )
        )
        self.assertEqual(fields[AMOUNT], compare.STEP_FIELDS[AMOUNT])
        self.assertEqual(compare.explain({"unit"}, [AMOUNT], "exchange", fields), [])

    def test_steps_the_importer_can_not_see_explain_nothing(self):
        fields = compare.step_fields(
            self.summary(
                **{
                    "0004-flow-cas-numbers-added": {"flowData/exchange/@CASNumber": 9},
                    "0010-brightway-flows-links": {
                        "flowData/exchange/extensions/@brightwayFlow": 9
                    },
                    "0003-flag-not-maintained": {"extensions/@maintenance": 9},
                    # the adapter gives every exchange its original number back
                    "renumber-exchanges": {"flowData/exchange/@number": 9},
                }
            )
        )
        self.assertEqual(set(fields), set(compare.STEP_FIELDS))

    def test_a_layer_explains_a_substituted_supplier(self):
        fields = compare.step_fields(None, {"step": "C900-other"})
        self.assertEqual(
            compare.explain({"flow", "name", "location"}, ["C900-other"], "exchange", fields),
            ["C900-other"],
        )
        self.assertEqual(compare.explain({"amount"}, ["C900-other"], "exchange", fields), [])

    def test_the_steps_of_a_dataset_include_the_layer_that_changed_it(self):
        import json
        import tempfile

        with tempfile.TemporaryDirectory() as folder:
            build = Path(folder)
            (build / "adapter-receipt.json").write_text(
                json.dumps(
                    {"steps_by_dataset": {"crop": {"import_fixes": ["a"], "patches": ["b"]}}}
                )
            )
            self.assertEqual(compare.read_steps(build), {"crop": ["a", "b"]})
            (build / "layer-receipt.json").write_text(
                json.dumps({"step": "C900-other", "datasets_changed": ["crop", "farm"]})
            )
            self.assertEqual(
                compare.read_steps(build),
                {"crop": ["a", "b", "C900-other"], "farm": ["C900-other"]},
            )

    def test_a_step_both_builds_share_explains_no_difference_between_them(self):
        # the patched copy and a contribution: the patch is in both, the layer in one
        candidate = {"crop": ["0007-flow-names", "C900-other"], "farm": ["C900-other"]}
        patched = {"crop": ["0007-flow-names"], "mill": ["location-codes"]}
        alone = compare.steps_of_the_candidate_alone(candidate, patched)
        self.assertEqual(alone, {"crop": ["C900-other"], "farm": ["C900-other"]})
        fields = compare.step_fields(None, {"step": "C900-other"})
        # a supplier of the same location: only the flow and its name change
        changed = {"flow", "name"}
        self.assertEqual(
            compare.explain(changed, candidate["crop"], "exchange", fields), ["0007-flow-names"]
        )
        self.assertEqual(
            compare.explain(changed, alone["crop"], "exchange", fields), ["C900-other"]
        )
        # the provider release has no step recorded: nothing is taken away
        self.assertEqual(compare.steps_of_the_candidate_alone(candidate, {}), candidate)


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

    def layered(self, **planted):
        """The base and a candidate in which a layer repoints the mix's gas input to the
        farm; `planted` changes the candidate beyond what the layer's receipt lists."""
        base = self.inventory()
        processes, exchanges = self.inventory()
        mix_gas = (exchanges["process_id"] == "mix") & (exchanges["flow"] == "gas")
        exchanges.loc[mix_gas, ["flow", "flow_name", "location"]] = ["farm", "Fruit", "CH"]
        for (process, position), values in planted.get("rows", {}).items():
            row = (exchanges["process_id"] == process) & (exchanges["position"] == position)
            exchanges.loc[row, list(values)] = list(values.values())
        receipt = {
            "step": "C900-other",
            "datasets_changed": ["mix"],
            "exchanges": [
                {"dataset": "mix", "position": 1}
                | {"before": {"flow": "gas"}, "after": {"flow": "farm"}}
            ],
        }
        steps = {"mix": ["C900-other"], "farm": ["C900-other"]}
        fields = compare.step_fields(None, receipt)
        return compare.compare_rows(base, (processes, exchanges), steps, fields, receipt)["summary"]

    def test_a_layer_explains_the_input_its_receipt_lists(self):
        summary = self.layered()
        self.assertEqual(summary["exchange_rows_changed"], 1)
        self.assertEqual(summary["unexplained_count"], 0)
        self.assertEqual(summary["by_step"]["C900-other"]["rows"], 1)

    def test_an_undeclared_repointing_in_a_dataset_the_layer_touches_is_unexplained(self):
        # the mix's second input, which the receipt does not list, is repointed too
        planted = {("mix", 2): {"flow": "gas", "flow_name": "Gas, at production"}}
        summary = self.layered(rows=planted)
        self.assertEqual(summary["exchange_rows_changed"], 2)
        self.assertEqual(summary["by_step"]["C900-other"]["rows"], 1)
        self.assertEqual(summary["unexplained_count"], 1)
        self.assertEqual(summary["unexplained"], [{"dataset": "mix", "fields": ["flow", "name"]}])

    def test_a_declared_input_that_took_another_supplier_is_unexplained(self):
        planted = {("mix", 1): {"flow": "mix", "flow_name": "Mix"}}
        summary = self.layered(rows=planted)
        self.assertEqual(summary["unexplained_count"], 1)
        self.assertNotIn("C900-other", summary["by_step"])

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

    def test_what_moved_is_written_for_the_site_dataset_by_dataset(self):
        """`before-after.json`: the same counts as the comparison, every moved dataset with its
        results in every method, the furthest first, and each step with what it changed."""
        import pandas as pd
        from release_build import before_after_account
        from runrecord import before_after

        rows = compare.compare_rows(self.base, self.cand, self.steps)
        seeds = compare.relevant_seeds(rows["rows"], self.effective, ["climate", "fossils"])
        graph = compare.consumer_graph(self.base[1], self.cand[1])
        index = pd.Index(["farm", "gas", "mix"], name="code")
        before = pd.DataFrame(
            {"climate": [300.0, 0.0, 0.0], "fossils": [5.0, 36.0, 72.0]}, index=index
        )
        after = pd.DataFrame(
            {"climate": [1.0, 0.0, 0.0], "fossils": [0.1, 0.0, 72.0 * (1 + 1e-9)]}, index=index
        )
        names = {
            "farm": {"name": "Fruit", "location": "CH"},
            "gas": {"name": "Gas", "location": "NO"},
        }
        moved, reach = {}, {}
        scores = compare.compare_scores(before, after, seeds, graph, names, moved, reach)
        self.assertEqual(
            moved, {"climate": {"farm": [AMOUNT]}, "fossils": {"farm": [AMOUNT], "gas": [NAMES]}}
        )
        # what each step can move: everything downstream of what it changed, per method
        self.assertEqual(reach["climate"], {AMOUNT: {"farm"}})
        self.assertEqual(reach["fossils"], {AMOUNT: {"farm"}, NAMES: {"gas", "mix"}})
        comparison = {
            "scores": scores,
            "rows": rows["summary"],
            "builds": {"candidate": {"datasets": 3}},
            "linked_on_the_declared_flow": {"exchanges": 2},
            "elementary_flows": {"exchanges_that_lost_their_ef_3_1_flow": 1},
        }
        records = (
            {"patched": False, "databases": {"inventory": "x-2026"}},
            {
                "patched": True,
                "databases": {"inventory": "x-2026-patched"},
                "release": {"name": "X:2026"},
            },
        )
        steps = {AMOUNT: {"kind": "patch", "description": "Correct the disposal. "}}

        def account(**more):
            return before_after_account.account(
                comparison, records, (before.to_dict(), after.to_dict()), moved, names,
                {"climate": "kg CO2 eq"}, steps, reach, **more,
            )  # fmt: skip

        data = account()
        self.assertEqual(before_after.shape_errors(data), [])
        self.assertEqual(data["title"], "X:2026 and the patched copy")
        self.assertEqual(
            (data["before"]["label"], data["after"]["label"]), ("X:2026", "Patched copy")
        )
        self.assertIn("`x-2026`", data["before"]["about"])
        self.assertEqual(
            data["items"], {"one": "dataset", "many": "datasets", "compared": 3, "moved": 2}
        )
        climate, fossils = data["indicators"]
        self.assertEqual((climate["unit"], climate["moved"]), ("kg CO2 eq", 1))
        self.assertEqual((climate["lower"], climate["unexplained"]), (1, 0))
        self.assertEqual((fossils["moved"], fossils["lower"], fossils["higher"]), (2, 2, 0))
        self.assertEqual(sum(fossils["bands"]), 3)
        # the furthest from no change first: a factor of 300 lies further than a lost score,
        # which counts as a factor of 100
        self.assertEqual([item["id"] for item in data["moved"]], ["farm", "gas"])
        farm = data["moved"][0]
        self.assertEqual((farm["name"], farm["place"], farm["causes"]), ("Fruit", "CH", [AMOUNT]))
        self.assertEqual(farm["values"], {"climate": [300.0, 1.0], "fossils": [5.0, 0.1]})
        causes = {cause["id"]: cause for cause in data["causes"]}
        self.assertEqual(causes[AMOUNT]["kind"], "patch")
        self.assertEqual(causes[AMOUNT]["title"], "Correct the disposal.")
        amount = causes[AMOUNT]
        self.assertEqual(
            (amount["rows"], amount["changed"], amount["moved"]), (1, {"amount": 1}, 1)
        )
        # a row two steps explain together is listed under both names. Such a pair has no
        # reach of its own, so it has no count of what it moved and no claim: not "0", unknown
        both = causes[f"location-codes + {LOCATION}"]
        self.assertEqual(
            (both["kind"], both["moved"], both["claim"]), ("two steps together", None, None)
        )
        # each step's claim is worked out: how many datasets it reaches, and never which
        self.assertEqual(
            (amount["claim"]["derived"], amount["claim"]["reach"], amount["claim"]["scope"]),
            (True, 1, []),
        )
        self.assertEqual(causes[NAMES]["claim"]["reach"], 2)
        # a step that changed nothing a result depends on claims that nothing moves
        nothing = before_after_account.derived_claim(LOCATION, reach)
        self.assertEqual((nothing["derived"], nothing["reach"]), (True, 0))
        self.assertIn("Nothing this step changed can move a result", nothing["text"])
        # every value has a class; what moved inside a step's reach is as claimed, and "mix",
        # which the names step reaches and which did not move, is unchanged: a reach that was
        # worked out says what may move
        self.assertEqual(climate["classes"], {"unchanged": 2, "as claimed": 1})
        self.assertEqual(fossils["classes"], {"unchanged": 1, "as claimed": 2})
        self.assertEqual(farm["classes"], {"climate": "as claimed", "fossils": "as claimed"})
        self.assertEqual(farm["moved"], ["climate", "fossils"])
        # noise is not measured, and the file claims nothing about it that was not measured
        self.assertEqual(
            data["noise"],
            {
                "measured": False,
                "between": None,
                "note": "Both builds were made in one run, on one machine.",
            },
        )
        self.assertEqual(data["rows"]["differ"], rows["summary"]["exchange_rows_changed"])
        self.assertEqual(len(data["notes"]), 2)
        # a page lists only so many datasets with their results, and says how many it left out
        short = account(listed=1)
        self.assertEqual(
            ([item["id"] for item in short["moved"]], short["moved_not_listed"]), (["farm"], 1)
        )
        self.assertEqual(short["items"]["moved"], 2)
        # a name of any length, with a line break in it, is a name the format takes
        long = dict(names) | {"farm": {"name": "Fruit\n" + "x" * 500, "location": "C\tH" * 40}}
        written = before_after_account.account(
            comparison, records, (before.to_dict(), after.to_dict()), moved, long,
            {"climate": "kg CO2 eq"}, steps, reach,
        )  # fmt: skip
        self.assertEqual(before_after.shape_errors(written), [])
        self.assertTrue(written["moved"][0]["name"].startswith("Fruit xxx"))
        # a score that moved outside every step's reach is not claimed: what the comparison
        # calls unexplained, and the two counts must agree
        outside = after.copy()
        outside.loc["mix", "climate"] = 9.0
        moved_2, reach_2 = {}, {}
        scores_2 = compare.compare_scores(before, outside, seeds, graph, names, moved_2, reach_2)
        found = before_after_account.account(
            comparison | {"scores": scores_2}, records, (before.to_dict(), outside.to_dict()),
            moved_2, names, {"climate": "kg CO2 eq"}, steps, reach_2,
        )  # fmt: skip
        self.assertEqual(found["indicators"][0]["classes"]["not claimed"], 1)
        self.assertEqual(found["indicators"][0]["unexplained"], 1)
        mix = next(item for item in found["moved"] if item["id"] == "mix")
        self.assertEqual((mix["classes"]["climate"], mix["causes"]), ("not claimed", []))
        wider = reach_2 | {"climate": {AMOUNT: {"farm", "mix"}}}
        with self.assertRaisesRegex(ValueError, "0 moved outside every step's reach"):
            before_after_account.account(
                comparison | {"scores": scores_2},
                records,
                (before.to_dict(), outside.to_dict()),
                moved_2,
                names,
                {},
                steps,
                wider,
            )
        # a count that is not the comparison's own stops the file from being written
        scores["methods"][0]["datasets_moved"] = 2
        with self.assertRaisesRegex(ValueError, "the comparison counted 2 moved of 3"):
            account()

    def chain_inputs(self):
        """What compare_scores gives the writers, on the synthetic tables."""
        import pandas as pd

        rows = compare.compare_rows(self.base, self.cand, self.steps)
        seeds = compare.relevant_seeds(rows["rows"], self.effective, ["climate", "fossils"])
        graph = compare.consumer_graph(self.base[1], self.cand[1])
        index = pd.Index(["farm", "gas", "mix"], name="code")
        before = pd.DataFrame(
            {"climate": [300.0, 0.0, 2.0], "fossils": [5.0, 36.0, 72.0]}, index=index
        )
        after = pd.DataFrame(
            {"climate": [1.0, 0.0, 2.0], "fossils": [0.1, 0.0, 72.0 * (1 + 1e-9)]}, index=index
        )
        names = {
            "farm": {"name": "Fruit", "location": "CH"},
            "gas": {"name": "Gas", "location": "NO"},
        }
        moved, reach = {}, {}
        scores = compare.compare_scores(before, after, seeds, graph, names, moved, reach)
        comparison = {
            "scores": scores,
            "rows": rows["summary"],
            "builds": {"candidate": {"datasets": 3}},
            "linked_on_the_declared_flow": {"exchanges": 2},
            "elementary_flows": {"exchanges_that_lost_their_ef_3_1_flow": 0},
        }
        records = (
            {"databases": {"inventory": "x-2026"}, "tools": {"this repository": "abc1234"}},
            {"databases": {"inventory": "x-2026-patched"}, "release": {"name": "X:2026"}},
        )
        steps = {AMOUNT: {"kind": "patch", "description": "Correct the disposal."}}
        units = {"farm": "kg", "gas": "MJ", "mix": "MJ"}
        return comparison, records, (before.to_dict(), after.to_dict()), names, steps, reach, units

    @unittest.skipUnless(
        importlib.util.find_spec("sentier_diagnostics"), "needs sentier-diagnostics"
    )
    def test_the_comparison_is_written_as_a_chain_in_the_shared_format(self):
        import tempfile

        from release_build import diagnostics_account as account
        from sentier_diagnostics import fileformat

        comparison, records, scores, names, steps, reach, units = self.chain_inputs()
        data = account.chain(
            comparison, records, scores, names, {"climate": "kg CO2 eq"}, steps, reach, units,
            item_groups={"farm": "agriculture", "gas": "fuels"},
        )  # fmt: skip
        self.assertEqual(fileformat.errors(data), [])
        # a dataset's sector is its group; one without a sector has none
        groups = {item["id"]: item["group"] for item in data["items"]}
        self.assertEqual(groups.get("farm"), "agriculture")
        self.assertEqual([s["id"] for s in data["states"]], ["before", "after"])
        (step,) = data["steps"]
        # the claim is the comparison's reach (farm in climate; farm, gas and mix in fossil
        # resources), published as a count only
        self.assertEqual((step["claim"]["reach"], step["claim"]["scope"][0]["items"]), (3, None))
        climate = data["counts"]["steps"]["fixes"]["climate"]
        self.assertEqual(climate["verdicts"]["as claimed"], 1)
        self.assertEqual(climate["verdicts"]["not claimed"], 0)
        # with a build of the world's factors, the countries' factors are a step of their own,
        # claimed in the categories the install report names
        with tempfile.TemporaryDirectory() as tmp:
            world, provider = Path(tmp) / "world", Path(tmp) / "provider"
            for folder in (world / "audit", provider / "logs"):
                folder.mkdir(parents=True)
            (world / "audit" / "scores.csv").write_text(
                "code,climate,fossils\nfarm,300,5\ngas,0,36\nmix,1.5,72\n"
            )
            report = {"coverage": {"located_by_method": [["climate", 1], ["fossils", 0]]}}
            (provider / "logs" / "install-report.json").write_text(json.dumps(report))
            data = account.chain(
                comparison, records, scores, names, {}, steps, reach, units,
                world=world, candidate=provider,
            )  # fmt: skip
            self.assertEqual(fileformat.errors(data), [])
            self.assertEqual([s["id"] for s in data["states"]], ["world", "before", "after"])
            located = data["steps"][0]
            self.assertEqual(located["claim"]["text"], "Climate may move; nothing else moves.")
            self.assertEqual(located["claim"]["scope"][0]["indicators"], ["climate"])
            # mix moved 1.5 -> 2 in climate: as claimed; nothing moved in fossils
            self.assertEqual(
                data["counts"]["steps"]["located-factors"]["climate"]["verdicts"]["as claimed"], 1
            )
            # an install report that does not say where the countries' factors are refuses
            (provider / "logs" / "install-report.json").write_text(json.dumps({"coverage": {}}))
            with self.assertRaisesRegex(account.ChainError, "located_by_method"):
                account.chain(
                    comparison, records, scores, names, {}, steps, reach, units,
                    world=world, candidate=provider,
                )  # fmt: skip
        # a value that moved outside every reach where the comparison says all is explained
        # stops the file: the two must agree
        narrowed = {method: {} for method in reach}
        with self.assertRaisesRegex(account.ChainError, "outside the reach of every step"):
            account.chain(comparison, records, scores, names, {}, steps, narrowed, units)

    def test_a_contribution_is_compared_with_the_patched_copy_under_its_own_name(self):
        from release_build import before_after_account

        patched = {"databases": {"inventory": "x-patched"}, "release": {"name": "X:2026"}}
        with_layer = patched | {
            "databases": {"inventory": "x-c7"},
            "contribution": {"id": "C7", "standing": "not authorised", "step": "C7-sea"},
        }
        title, before, after = before_after_account.sides(patched, with_layer)
        self.assertEqual(title, "The patched copy and contribution C7")
        self.assertEqual((before[0], after[0]), ("Patched copy", "Contribution C7"))
        self.assertIn("`x-patched`", before[1])
        self.assertIn("`x-c7`", after[1])
        self.assertIn("not authorised", after[1])

    def test_corrected_flows_are_listed_with_the_ef_flow_they_stay_on(self):
        receipt = {
            "source_observations": [
                {
                    "dataset": "gas",
                    "position": 1,
                    "declared": {"name": "Gas, natural/m3", "category": "resources"},
                    "patched": {"name": "Gas, natural", "category": "resources"},
                },
                {
                    "dataset": "farm",
                    "position": 2,
                    "declared": {"name": "Carbon dioxide", "category": "biotic"},
                    "patched": {"name": "Carbon dioxide", "category": "in air"},
                },
            ]
        }
        steps = {"gas": [NAMES], "farm": [COMPARTMENTS, AMOUNT]}
        result = compare.declared_flows(
            receipt, self.base[1], steps, self.bridge, {"ef-gas": "Natural Gas"}
        )
        self.assertEqual(
            (result["exchanges"], result["datasets"], result["unexplained"]), (2, 2, 0)
        )
        by_step = {flow["steps"][0]: flow for flow in result["flows"]}
        self.assertEqual(by_step[NAMES]["ef_3_1_flow"], ["Natural Gas"])
        self.assertTrue(by_step[NAMES]["linked_to_ef_3_1"])
        self.assertEqual(by_step[COMPARTMENTS]["ef_3_1_flow"], ["EF 3.1 flow ef-co2"])

        result = compare.declared_flows(receipt, self.base[1], {}, self.bridge, {})
        self.assertEqual(result["unexplained"], 2)
        self.assertEqual(
            compare.declared_flows({}, self.base[1], {}, self.bridge, {})["exchanges"], 0
        )

    def test_the_name_of_the_release_is_not_a_changed_row(self):
        processes = self.base[0].assign(source="bafu-2026", source_version="v1")
        patched = self.base[0].assign(source="bafu-2026-v1-patched", source_version="tree-1")
        summary = compare.compare_rows((processes, self.base[1]), (patched, self.base[1]), {})[
            "summary"
        ]
        self.assertEqual(summary["dataset_rows_changed_by_step"], {})
        self.assertEqual(summary["unexplained_count"], 0)

    def test_declared_supplier_location_is_compared_with_the_linked_dataset(self):
        before = compare.declared_against_linked(*self.base)
        after = compare.declared_against_linked(*self.cand)
        self.assertEqual(before["technosphere_inputs"], 3)
        self.assertEqual(before["without_a_linked_dataset"], 1)  # "waste" is not a dataset here
        self.assertEqual(before["no_declared_location"], 0)
        self.assertNotIn("declared_unit_differs", before)  # these tables carry no units
        self.assertEqual(
            before["declared_location_differs"] - after["declared_location_differs"], 1
        )

    def test_declared_units_are_compared_with_the_linked_datasets_unit(self):
        processes, exchanges = self.base
        processes = processes.assign(reference_unit=["kg", "MJ", "kWh"])
        exchanges = exchanges.assign(unit=["kg", "kg", "kg", "MJ", "Nm3", "kWh", "kWh", "p"])
        result = compare.declared_against_linked(processes, exchanges)
        # "mix" takes gas in kWh from a dataset in MJ, and fruit in p from a dataset in kg;
        # the input without a linked dataset is not counted
        self.assertEqual(result["declared_unit_differs"], 2)
        self.assertEqual(
            result["declared_and_linked_units"],
            {"kWh for a dataset in MJ": 1, "p for a dataset in kg": 1},
        )


class Guards(unittest.TestCase):
    """Two builds are compared only when a difference between them can be a step's."""

    def builds(self, tmp, first, second):
        import json

        made = []
        for name, record in (("first", first), ("second", second)):
            folder = Path(tmp) / name
            folder.mkdir()
            (folder / "build.json").write_text(json.dumps(record))
            made.append(folder)
        return made

    def refused(self, first, second):
        import contextlib
        import io
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            one, other = self.builds(tmp, first, second)
            with self.assertRaises(compare.CompareError) as raised:
                compare.compare(one, other)
            # and the command says so in one line, and writes no comparison
            out, said = Path(tmp) / "comparison.json", io.StringIO()
            with contextlib.redirect_stderr(said):
                code = compare.main(
                    [
                        str(one),
                        str(other),
                        "--out",
                        str(out),
                        "--before-after",
                        str(Path(tmp) / "b.json"),
                    ]
                )
            self.assertEqual(
                (code, out.exists(), (Path(tmp) / "b.json").exists()), (2, False, False)
            )
            self.assertIn("Comparison failed:", said.getvalue())
            self.assertNotIn("Traceback", said.getvalue())
        return str(raised.exception)

    def test_a_build_with_the_countries_factors_is_not_compared_with_one_without(self):
        why = self.refused({"install": {"located": True}}, {"install": {"located": False}})
        self.assertIn("that country's factor", why)
        # a build made before the rule says nothing, and did not apply it
        self.assertFalse(compare.located_of(Path("/nowhere")))
        self.assertIn("that country's factor", self.refused({"install": {"located": True}}, {}))

    def test_two_builds_of_two_linkings_are_not_compared(self):
        why = self.refused({"linking": compare.LINKINGS[0]}, {"linking": compare.LINKINGS[1]})
        self.assertIn("Compare two builds of one linking", why)

    def test_a_build_of_the_second_linking_without_its_file_says_so(self):
        linked = {"linking": compare.LINKINGS[1], "install": {"located": True}}
        why = self.refused(linked, linked)
        self.assertIn(compare.FLOW_LINKS, why)
        self.assertIn("before a build kept that file", why)


class Published(unittest.TestCase):
    def test_two_builds_are_put_side_by_side_only_when_both_were_compared(self):
        import json
        import tempfile

        def summary(share):
            categories = {"energy": {"compared": 9, "within_1_percent": share}}
            return {"joined": 9, "not_joined": 1, "categories": categories}

        with tempfile.TemporaryDirectory() as temp:
            base, cand = Path(temp) / "base", Path(temp) / "cand"
            base.mkdir()
            cand.mkdir()
            (base / "published-results.json").write_text(json.dumps(summary(97.75)))
            self.assertIsNone(compare.published_results(base, cand))
            (cand / "published-results.json").write_text(json.dumps(summary(11.56)))
            result = compare.published_results(base, cand)
        self.assertEqual(
            result["within_1_percent"]["energy"], {"baseline": 97.75, "candidate": 11.56}
        )
        self.assertEqual(result["not_joined"], {"baseline": 1, "candidate": 1})


if __name__ == "__main__":
    unittest.main()
