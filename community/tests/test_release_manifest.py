"""The manifest of a patched release, on a made-up run: three small files, no data of the provider."""

import contextlib
import copy
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import release_manifest as rm  # noqa: E402

FILE = """<?xml version='1.0' encoding='UTF-8'?>
<ecoSpold xmlns="http://www.EcoInvent.org/EcoSpold01" xmlns:bcf="urn:bafu-community-fixes:extensions:1">
  <dataset number="{number}">
    <metaInformation/>
    <flowData/>
    <bcf:extensions>
      <bcf:dataset>{marks}</bcf:dataset>
    </bcf:extensions>
  </dataset>
</ecoSpold>
"""
# The fields of a step in a run summary, with the two the manifest must leave out.
STEP = {"reported_by": "A Reporter, Some Company", "confirmed_by": "A Person, the provider (email)",
        "references": ["https://example.org/thread"], "fields": {"flowData/exchange/@meanValue": 3},
        "xsd_checked": 3, "error": None}


def step(sid, kind, datasets, findings=(), authorised="An Authoriser", **more):
    return dict(STEP, id=sid, kind=kind, description=f"What {sid} does.", authored_by="An Author",
                authorised_by=authorised, findings=list(findings), datasets=datasets, exchanges=datasets,
                changes=datasets * 2, **more)


class ManifestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.out = Path(self.tmp.name) / "out"
        self.out.mkdir()
        marks = {
            100001: ["<bcf:importFix>boolean-spelling</bcf:importFix>", "<bcf:patch>0001-first</bcf:patch>",
                     "<bcf:patch>0002-second</bcf:patch>"],
            100002: ["<bcf:patch>0002-second</bcf:patch>"],
            100003: [],
        }
        for number, lines in marks.items():
            (self.out / f"process_{number}.xml").write_text(FILE.format(number=number, marks="".join(lines)))
        digest, size = rm.fingerprint(self.out, rm.files_of(self.out))
        self.summary = {
            "summary_version": 1, "status": "completed", "error": None,
            "started": "2026-11-13T16:00:00+01:00", "finished": "2026-11-13T16:05:00+01:00",
            "release": {"url": "https://files.example.org/release.zip", "archive_sha256": "ab" * 32,
                        "fingerprint": "cd" * 32, "files": 3, "datasets": 3, "exchanges": 40},
            "software": {"bafu-community-fixes": "0.1.0", "git commit": "abc1234", "Python": "3.14.7",
                         "platform": "Linux"},
            "options": {"XSD schema check": "after import and after every patch", "extensions in output": True,
                        "only patches": "all", "skipped patches": "none",
                        "placeholders for missing data": "year 1111"},
            "steps": [step("boolean-spelling", "import fix", 1), step("0001-first", "patch", 1, ["F1"]),
                      step("0002-second", "patch", 2), step("0003-third", "patch", 0, ["F3"], None)],
            "totals": {"steps": 4, "datasets_changed": 2, "values_changed": 8},
            "output": {"files": 3, "bytes": size, "fingerprint": digest},
        }

    def manifest(self, **options):
        return rm.manifest(self.summary, self.out, "patched-2026-v1.1", "f" * 40, **options)

    def refused(self):
        with self.assertRaises(rm.Refused) as raised:
            self.manifest()
        return str(raised.exception)


class ManifestTests(ManifestCase):
    def test_a_manifest_says_what_was_built_from_what_by_which_patches(self):
        data = self.manifest()
        self.assertEqual(set(data), rm.TOP_KEYS)
        self.assertEqual((data["format"], data["tag"]), ("sentier-bafu/patched-release/1", "patched-2026-v1.1"))
        self.assertEqual(data["provider_release"]["archive_sha256"], "ab" * 32)
        self.assertEqual(data["tool"], {"name": "bafu-community-fixes", "version": "0.1.0", "revision": "f" * 40})
        self.assertEqual(data["output"], self.summary["output"])
        first, second, third = data["patches"]
        self.assertEqual(first, {
            "id": "0001-first", "description": "What 0001-first does.", "findings": ["F1"], "author": "An Author",
            "authorised_by": "An Authoriser", "result": "applied", "datasets_changed": 1, "exchanges_changed": 1,
            "values_changed": 2, "datasets": [100001],
        })
        self.assertEqual((second["datasets"], second["findings"]), ([100001, 100002], []))
        self.assertEqual((third["result"], third["datasets"], third["authorised_by"]), ("not needed", [], None))
        self.assertEqual(data["import_fixes"], [{"id": "boolean-spelling", "description": "What boolean-spelling does.",
                                                 "result": "applied", "datasets_changed": 1, "values_changed": 2}])
        self.assertEqual(rm.shape_errors(data), [])

    def test_a_manifest_names_the_author_and_the_authoriser_and_nobody_else(self):
        text = json.dumps(self.manifest())
        for words in ("A Reporter", "A Person", "the provider (email)", "example.org/thread", "placeholders"):
            self.assertNotIn(words, text)
        self.assertNotIn(self.tmp.name, text, "no path of the machine")

    def test_the_release_id_comes_from_the_site_configuration_when_it_names_the_archive(self):
        self.assertIsNone(self.manifest()["provider_release"]["id"])
        root = Path(self.tmp.name) / "repo"
        (root / "site").mkdir(parents=True)
        (root / "community/findings/0").mkdir(parents=True)
        config = json.loads((ROOT / "site/config.json").read_text())
        config["releases"][-1]["archive_sha256"] = "ab" * 32
        (root / "site/config.json").write_text(json.dumps(config))
        for rid in ("F1", "F3"):
            (root / f"community/findings/0/{rid}.json").write_text((ROOT / f"community/findings/0/{rid}.json").read_text())
        self.assertEqual(self.manifest(root=root)["provider_release"]["id"], config["releases"][-1]["id"])

    def test_what_is_refused(self):
        cases = []

        def case(words, change):
            cases.append((words, change))

        case("the run did not complete", lambda s: s.update(status="failed"))
        case("the run did not complete", lambda s: s.update(output=None))
        case("not a release this revision of the tool knows", lambda s: s["release"].update(url=None))
        case("not the ones the summary describes", lambda s: s["output"].update(fingerprint="0" * 64))
        case("not the ones the summary describes", lambda s: s["output"].update(files=4))
        case("the summary counts 2 changed datasets, the written files carry its mark on 1",
             lambda s: s["steps"][1].update(datasets=2))
        case("patch 0002-second changed data and names nobody who authorised it",
             lambda s: s["steps"][2].update(authorised_by=None))
        case("patch 0001-first names F9999, which has no record", lambda s: s["steps"][1].update(findings=["F9999"]))
        case("step 0001-first failed", lambda s: s["steps"][1].update(error="expected 126.22, found 18"))
        case("the mark of a patch the summary does not list: 0002-second", lambda s: s["steps"].pop(2))
        original = copy.deepcopy(self.summary)
        for words, change in cases:
            self.summary = copy.deepcopy(original)
            change(self.summary)
            self.assertIn(words, self.refused())

    def test_a_file_changed_after_the_run_is_noticed(self):
        path = self.out / "process_100003.xml"
        path.write_text(path.read_text().replace("<flowData/>", "<flowData> </flowData>"))
        self.assertIn("not the ones the summary describes", self.refused())

    def test_only_a_manifest_passes_the_check_before_publishing(self):
        good = self.manifest()
        changes = (
            lambda d: d.update(inventory=[{"name": "Example", "amount": 1.0}]),
            lambda d: d["patches"][0].update(confirmed_by="A Person"),
            lambda d: d["patches"][0].update(datasets=[100001, 100001]),
            lambda d: d["patches"][0].update(datasets=["100001"]),
            lambda d: d["patches"][0].update(result="adopted by the provider"),
            lambda d: d["patches"][0].update(description="line\nline"),
            lambda d: d["output"].update(fingerprint="short"),
            lambda d: d["provider_release"].update(url="http://example.org/x.zip"),
            lambda d: d.update(format="something else"),
            lambda d: d.update(tag="patched; rm -rf"),
        )
        for change in changes:
            data = copy.deepcopy(good)
            change(data)
            self.assertTrue(rm.shape_errors(data), change)
        self.assertEqual(rm.shape_errors([]), ["the manifest holds other fields than a manifest has"])


class CommandTests(ManifestCase):
    def run_main(self, *args):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = rm.main([str(arg) for arg in args])
        return code, out.getvalue()

    def test_the_command_writes_the_manifest_and_the_text_of_the_release(self):
        folder = Path(self.tmp.name)
        (folder / "summary.json").write_text(json.dumps(self.summary))
        code, text = self.run_main("--summary", folder / "summary.json", "--output", self.out, "--tag", "patched-1",
                                   "--revision", "f" * 40, "--out", folder / "release/manifest.json",
                                   "--notes", folder / "release/notes.md")
        self.assertEqual(code, 0, text)
        self.assertEqual(json.loads((folder / "release/manifest.json").read_text())["tag"], "patched-1")
        notes = (folder / "release/notes.md").read_text()
        self.assertIn("It holds no inventory", notes)
        self.assertIn("| 0001-first | F1 | An Author | An Authoriser | applied | 1 |", notes)
        self.assertIn("| 0003-third | F3 | An Author | nobody yet | not needed | 0 |", notes)
        self.assertIn("The provider decides what it changes.", notes)
        code, text = self.run_main("--verify", folder / "release/manifest.json")
        self.assertEqual((code, text), (0, "manifest.json: a manifest of 3 patches, and nothing else\n"))

    def test_a_refused_run_writes_nothing(self):
        folder = Path(self.tmp.name)
        self.summary["status"] = "failed"
        (folder / "summary.json").write_text(json.dumps(self.summary))
        code, text = self.run_main("--summary", folder / "summary.json", "--output", self.out,
                                   "--out", folder / "manifest.json")
        self.assertEqual(code, 1)
        self.assertIn("No manifest written: the run did not complete", text)
        self.assertFalse((folder / "manifest.json").exists())

    def test_verify_refuses_a_file_that_is_something_else(self):
        folder = Path(self.tmp.name)
        (folder / "manifest.json").write_text(json.dumps({"format": rm.FORMAT, "exchanges": []}))
        self.assertEqual(self.run_main("--verify", folder / "manifest.json")[0], 1)
        (folder / "manifest.json").write_text("<ecoSpold/>")
        self.assertEqual(self.run_main("--verify", folder / "manifest.json"),
                         (1, "manifest.json: not a JSON file\n"))


if __name__ == "__main__":
    unittest.main()
