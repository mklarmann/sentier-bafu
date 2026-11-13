"""A contribution's layer: reading it, refusing what isn't one, applying a substitution.

Plain data only; the layer on the importer's real tables is in `test_whole_path.py`.
"""

import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import synthetic_release  # noqa: E402
from release_build import layer  # noqa: E402

PROCESSES = {
    "crop": {"name": "Crop", "location": "CH", "reference_unit": "kg"},
    "mix": {"name": "Mix", "location": "RER", "reference_unit": "kWh"},
    "plant": {"name": "Plant", "location": "CH", "reference_unit": "kWh"},
    "boiler": {"name": "Boiler", "location": "CH", "reference_unit": "MJ"},
}


def exchanges():
    def row(owner, flow, name, kind, unit, location, amount):
        return {
            "process_id": owner,
            "flow": flow,
            "flow_name": name,
            "flow_type": kind,
            "unit": unit,
            "location": location,
            "amount": amount,
        }

    return [
        row("crop", "crop", "Crop", "production", "kg", "CH", 1.0),
        row("crop", "mix", "Mix", "technosphere", "kWh", "RER", 0.05),
        row("crop", "co2", "Carbon dioxide", "biosphere", "kg", None, 0.2),
        row("crop", "mix", "Mix", "technosphere", "kWh", "RER", 0.01),
        row("mix", "mix", "Mix", "production", "kWh", "RER", 1.0),
    ]


def made(**changes):
    data = {
        "schema": layer.SCHEMA,
        "contribution": "C900",
        "name": "own-plant",
        "database": "bafu-2026-v1-c900-own-plant",
        "title": "The crop takes its electricity from the plant",
        "authored_by": "A. Tester",
        "changes": [
            {
                "kind": "supplier-substitution",
                "dataset": {"code": "crop", "name": "Crop", "location": "CH"},
                "replaced_supplier": {"code": "mix", "name": "Mix", "location": "RER"},
                "new_supplier": {"code": "plant", "name": "Plant", "location": "CH"},
            }
        ],
    }
    return data | changes


class Reading(unittest.TestCase):
    def test_a_layer_is_read_with_only_the_fields_a_layer_has(self):
        checked = layer.validate(made(extra="ignored", authorised_by=None))
        self.assertNotIn("extra", checked)
        self.assertIsNone(checked["authorised_by"])
        self.assertEqual(checked["references"], [])
        self.assertEqual(layer.step_id(checked), "C900-own-plant")

    def test_the_made_up_layer_of_the_whole_path_is_a_layer(self):
        self.assertEqual(
            layer.step_id(layer.validate(synthetic_release.LAYER)), "C900-direct-plant-supply"
        )

    def test_a_file_is_read_with_its_name_and_checksum(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "C900-own-plant.json"
            path.write_text(json.dumps(made()))
            loaded = layer.load(path)
            self.assertEqual(loaded["file"], "C900-own-plant.json")
            self.assertEqual(len(loaded["sha256"]), 64)
            self.assertEqual(layer.find(folder), [path])
            self.assertEqual(layer.find(Path(folder) / "not-there"), [])
            path.write_text("{not json")
            with self.assertRaisesRegex(layer.LayerError, "C900-own-plant.json"):
                layer.load(path)

    def test_what_is_not_a_layer_is_refused_with_the_reason(self):
        cases = {
            "schema must be": made(schema="something/else"),
            "`title` is missing": made(title=" "),
            "an id like C012": made(contribution="12"),
            "lower case words": made(name="Own Plant"),
            "a person's name, or null": made(authorised_by=""),
            "at least one change": made(changes=[]),
            "`kind` must be one of supplier-substitution": made(changes=[{"kind": "amount"}]),
            "fingerprint of a provider release": made(release={"fingerprint": "abc"}),
        }
        for message, data in cases.items():
            with self.assertRaisesRegex(layer.LayerError, message):
                layer.validate(data)
        change = copy.deepcopy(made()["changes"][0])
        change["new_supplier"] = change["replaced_supplier"]
        with self.assertRaisesRegex(layer.LayerError, "the new supplier is the replaced one"):
            layer.validate(made(changes=[change]))
        change = copy.deepcopy(made()["changes"][0])
        del change["dataset"]["location"]
        with self.assertRaisesRegex(layer.LayerError, "`location` of dataset crop is missing"):
            layer.validate(made(changes=[change]))


class LayersOfTheRepository(unittest.TestCase):
    """Every layer in `community/layers/` is found and built by the release run."""

    FOLDER = REPOSITORY / "community" / "layers"

    def test_every_layer_file_is_a_layer_with_a_name_of_its_own(self):
        layers = [layer.load(path) for path in layer.find(self.FOLDER)]
        for loaded in layers:
            self.assertEqual(loaded["file"], f"{layer.step_id(loaded)}.json")
        for key in ("database", "name"):
            values = [loaded[key] for loaded in layers]
            self.assertEqual(len(values), len(set(values)), f"two layers with one {key}")

    def test_the_release_run_looks_in_that_folder(self):
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "build_release", REPOSITORY / "scripts" / "build_release.py"
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.assertEqual(module.LAYERS, self.FOLDER)


class Names(unittest.TestCase):
    def test_a_contribution_never_takes_the_name_of_a_release(self):
        for name in ("bafu-2026", "bafu-2026-v1-patched", "bafu-2026-v1-patched-residual"):
            with self.assertRaisesRegex(layer.LayerError, "built under its own name"):
                layer.check_database_name(name, "C900")
            with self.assertRaisesRegex(layer.LayerError, "built under its own name"):
                layer.validate(made(database=name))

    def test_the_name_says_which_contribution_it_is(self):
        layer.check_database_name("bafu-2026-v1-c900-own-plant", "C900")
        with self.assertRaisesRegex(layer.LayerError, "must name its contribution, C900"):
            layer.check_database_name("bafu-2026-v1-patched-own-plant", "C900")
        for name in ("With Capitals", "ends-residual", ""):
            with self.assertRaisesRegex(layer.LayerError, "not a database name"):
                layer.check_database_name(name)


class Substituting(unittest.TestCase):
    def test_the_input_takes_the_new_supplier_and_keeps_amount_and_unit(self):
        rows = exchanges()
        changed = layer.substitute(PROCESSES, rows, layer.validate(made()))
        self.assertEqual([entry["position"] for entry in changed], [1, 3])
        self.assertEqual(
            changed[0],
            {
                "change": 1,
                "kind": "supplier-substitution",
                "dataset": "crop",
                "position": 1,
                "unit": "kWh",
                "amount": 0.05,
                "before": {"flow": "mix", "flow_name": "Mix", "location": "RER"},
                "after": {"flow": "plant", "flow_name": "Plant", "location": "CH"},
            },
        )
        self.assertEqual(
            (rows[1]["flow"], rows[1]["amount"], rows[1]["unit"]), ("plant", 0.05, "kWh")
        )
        # nothing else moved: the production row, the emission, the other dataset
        untouched = exchanges()
        for index in (0, 2, 4):
            self.assertEqual(rows[index], untouched[index])

    def test_one_of_two_inputs_can_be_named_by_its_position(self):
        data = made()
        data["changes"][0]["exchange"] = {"position": 3}
        rows = exchanges()
        changed = layer.substitute(PROCESSES, rows, layer.validate(data))
        self.assertEqual([entry["position"] for entry in changed], [3])
        self.assertEqual((rows[1]["flow"], rows[3]["flow"]), ("mix", "plant"))
        data["changes"][0]["exchange"] = {"position": 2}  # the emission
        with self.assertRaisesRegex(layer.LayerError, "exchange 2 of crop is not an input of mix"):
            layer.substitute(PROCESSES, exchanges(), layer.validate(data))

    def test_a_layer_written_for_other_data_stops(self):
        def stops(message, processes=PROCESSES, rows=None, **changes):
            data = made()
            data["changes"][0] |= changes
            with self.assertRaisesRegex(layer.LayerError, message):
                layer.substitute(processes, rows or exchanges(), layer.validate(data))

        stops(
            "the release has no dataset gone",
            new_supplier={"code": "gone", "name": "Plant", "location": "CH"},
        )
        stops(
            r"dataset plant is 'Plant' \(CH\) in the release, not 'Plant' \(DE\)",
            new_supplier={"code": "plant", "name": "Plant", "location": "DE"},
        )
        stops(
            "crop has no input of plant; nothing to substitute",
            replaced_supplier={"code": "plant", "name": "Plant", "location": "CH"},
            new_supplier={"code": "mix", "name": "Mix", "location": "RER"},
        )
        stops(
            "the input is in kWh and the new supplier's unit is MJ; a substitution converts "
            "nothing",
            new_supplier={"code": "boiler", "name": "Boiler", "location": "CH"},
        )


if __name__ == "__main__":
    unittest.main()
