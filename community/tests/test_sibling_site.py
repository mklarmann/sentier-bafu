"""The scripts and the stylesheet are the same files in every dataset's repository. What
differs from one dataset to another is said in site/config.json and nowhere in the code.

These tests build a made-up sibling of this repository from the same files: another provider
and dataset, release ids of another shape, datasets without a number, no patched release and
no release build, a form and a label of its own, and an index colour of its own. It must pass
the check of the records, build and pass the check of the site. Then they hold the colour to
its rules: whether a colour can be read is computed, not judged by eye.
"""

import io
import json
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import community  # noqa: E402
import frozen  # noqa: E402
from sitebuild import theme  # noqa: E402
from test_site import synthetic_finding  # noqa: E402

try:
    import build_site
    import importlib.util
    spec = importlib.util.spec_from_file_location("check_site", ROOT / "scripts/check_site.py")
    check_site = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(check_site)
except ModuleNotFoundError:  # the markdown package is a site-build dependency only
    build_site = None

REPO = "https://github.com/sentier-dev/sentier-agribalyse"
SITE = "https://sentier-dev.github.io/sentier-agribalyse/"
AUBERGINE = "#5d4a66"
GREEN = {"color": "#3c5343", "dark": "#2d3f33", "tint": "#dce9e1", "soft": "#84ae99"}  # the stylesheet's own


class Quiet:
    def __enter__(self):
        self.real, sys.stdout = sys.stdout, io.StringIO()

    def __exit__(self, *_):
        sys.stdout = self.real


def sibling(target, **changes):
    """A copy of this repository that is about another dataset, from the same scripts."""
    root = frozen.copy_repository(target)
    config = json.loads((root / "site/config.json").read_text())
    config.update(
        dataset="AGRIBALYSE", provider="ADEME", repository=REPO, site_url=SITE,
        releases=[{"id": "3.2", "name": "AGRIBALYSE 3.2", "background": "ecoinvent 3.9.1"}],
        older_numbering_until=0, index=AUBERGINE, lookup_example="F1",
        finding_label="agribalyse-finding", finding_form="agribalyse-data-finding.yml",
        home_title="AGRIBALYSE: community findings", title_suffix="AGRIBALYSE findings",
        description="Users of the AGRIBALYSE database record measured findings here.",
    )
    for key in ("dataset_code_pattern", "ledger_notes", "older_numbering_note", "sibling_name", "sibling_url",
                "assessments"):
        config.pop(key, None)
    # No patched release and no release build: the page for them is not part of this site.
    config["nav"] = [item for item in config["nav"] if item[0] != "patched-release.html"]
    config["documents"] = [doc for doc in config["documents"] if doc["page"] != "patched-release.html"]
    config["redirects"] = {}
    config.update(changes)
    (root / "site/config.json").write_text(json.dumps(config, indent=2) + "\n")
    # Its own words: a page of prose with the blocks it asks for, and nothing about this repository.
    blocks = {"findings.html": "findings-list", "feedback.html": "feedback-lists", "contributions.html": "contributions-list",
              "about/data.html": "data-files"}
    for doc in config["documents"]:
        asked = f"\n\n<!-- generated: {blocks[doc['page']]} -->" if doc["page"] in blocks else ""
        (root / doc["source"]).write_text(f"# {doc['title']}\n\nWhat users of AGRIBALYSE find in the data.{asked}\n")
        doc.pop("also", None)
    (root / "site/config.json").write_text(json.dumps(config, indent=2) + "\n")
    # Its own records: findings about processes that have a name and no number.
    for name in ("community/findings", "community/contributions", "community/recommendations"):
        shutil.rmtree(root / name)
        (root / name).mkdir()
    (root / "community/patches.json").unlink(missing_ok=True)
    (root / "community/recommendations/tracker.json").write_text("[]\n")
    for n in (1, 2, 4, 12):
        record = synthetic_finding(n)
        record.update(datasets=[], scope="The process Wheat grain, conventional, at farm gate (FR).", releases=["3.2"])
        text = json.dumps(record).replace("https://github.com/sentier-dev/sentier-bafu", REPO)
        (root / "community/findings/0").mkdir(exist_ok=True)
        (root / f"community/findings/0/F{n}.json").write_text(text + "\n")
    return root


@unittest.skipIf(build_site is None, "the site build needs the markdown package")
class SiblingSite(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.root = sibling(Path(cls.temp.name) / "repository")
        cls.out = Path(cls.temp.name) / "site"
        with Quiet():
            build_site.build(cls.out, offline=True, root=cls.root)
        cls.pages = {p.relative_to(cls.out).as_posix(): p.read_text() for p in cls.out.rglob("*.html")}

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_its_records_pass_the_check_and_its_site_passes_its_check(self):
        errors, _, _ = community.problems(self.root)
        self.assertEqual(errors, [])
        with Quiet():
            self.assertEqual(check_site.check(self.out), 0)
        self.assertIn("findings/F12.html", self.pages)

    def test_a_release_id_is_a_name_of_the_configured_list_whatever_its_shape(self):
        record = json.loads((self.root / "community/findings/0/F1.json").read_text())
        self.assertEqual(record["releases"], ["3.2"])
        self.assertIn("releases/3.2.html", self.pages)
        self.assertIn("AGRIBALYSE 3.2 is built on ecoinvent 3.9.1.", self.pages["releases/3.2.html"])
        # an id the list does not have is refused, as in this repository
        record["releases"] = ["4.0"]
        (self.root / "community/findings/0/F1.json").write_text(json.dumps(record))
        try:
            errors, _, _ = community.problems(self.root)
            self.assertTrue(any("4.0" in error for error in errors), errors)
        finally:
            record["releases"] = ["3.2"]
            (self.root / "community/findings/0/F1.json").write_text(json.dumps(record) + "\n")
        # and an id that could not be the name of a page is refused by the schema
        for bad in ("../x", "3.2 beta", ""):
            self.assertTrue(community.schema_errors(bad, community.load_schema("finding")["$defs"]["release_id"]), bad)

    def test_a_site_without_a_patched_release_has_no_page_no_link_and_no_run(self):
        self.assertNotIn("patched-release.html", self.pages)
        for name, text in self.pages.items():
            self.assertNotIn("patched-release.html", text, name)
            self.assertNotIn("replay.js", text, name)
        self.assertFalse((self.out / "api/v1/last-run.json").exists())
        self.assertNotIn("last-run.json", self.pages["about/data.html"])
        self.assertNotIn("Patch and release", self.pages["index.html"])

    def test_datasets_without_a_number_are_not_looked_up_by_one(self):
        listing = self.pages["findings.html"]
        self.assertNotIn("data-code", listing)
        self.assertIn('placeholder="Dataset name or word"', listing)
        self.assertIn("Look up a finding number or a word", self.pages["index.html"])
        self.assertNotIn("dataset code", self.pages["index.html"])
        self.assertIn('placeholder="For example F1"', self.pages["index.html"])
        self.assertEqual(list((self.out / "datasets").glob("*.html")) if (self.out / "datasets").exists() else [], [])
        # the script reads what a code looks like from the page, and none from a page that names none
        script = (ROOT / "site/assets/list.js").read_text()
        self.assertIn("list.dataset.code ? new RegExp(list.dataset.code) : null", script)
        self.assertNotRegex(script, r"\\d\{6\}")

    def test_its_form_its_label_and_its_names_come_from_its_configuration(self):
        self.assertIn(f"{REPO}/issues/new?template=agribalyse-data-finding.yml", self.pages["index.html"])
        config = community.load_config(self.root)
        self.assertEqual((config["finding_label"], config["finding_form"]), ("agribalyse-finding", "agribalyse-data-finding.yml"))
        ledger = (self.out / "ledger.md").read_text()
        self.assertTrue(ledger.startswith("# Findings about the AGRIBALYSE data\n"))
        self.assertIn("The number of a finding is the number of its issue.", ledger)
        self.assertNotIn("older numbering", ledger)
        self.assertIn("| [#12](", ledger)  # an issue of its own repository is "here"
        self.assertIn("<author><name>sentier-agribalyse</name></author>", (self.out / "feed.xml").read_text())
        for name, text in self.pages.items():
            self.assertNotIn("sentier-bafu", text.replace('"schema": "sentier-bafu/', ""), name)

    def test_every_page_carries_its_index_colour_and_the_frame_stays(self):
        expected = theme.read({"index": AUBERGINE})
        for name, text in self.pages.items():
            if 'http-equiv="refresh"' in text:
                continue
            self.assertIn('<html lang="en" class="has-index">', text, name)
            self.assertIn(f"<style>:root{{--index:{AUBERGINE};--index-dark:{expected['index-dark']};", text, name)
            self.assertIn(f'<meta name="theme-color" content="{AUBERGINE}">', text, name)
            self.assertEqual(text.count("<style>"), 1, name)
        # the stylesheet is the same file as this repository's: the colour is not written into it
        self.assertEqual((self.out / "style.css").read_bytes(), (ROOT / "site/style.css").read_bytes())
        self.assertIn(f"stroke='%23{AUBERGINE[1:]}'", self.pages["index.html"])

    def test_a_colour_that_can_not_be_read_stops_the_build(self):
        cases = {
            "#9bb7d4": "text in the index colour on the paper",        # too pale for text
            "#b07a1b": "text in the index colour on the paper",        # the amber of "waiting"
            "#6e5540": "where the signals for waiting and failed are",  # readable, but a signal's hue
            "#8c2f2a": "where the signals for waiting and failed are",  # the red-brown of "failed"
        }
        for colour, why in cases.items():
            with self.subTest(colour), tempfile.TemporaryDirectory() as tmp:
                root = sibling(Path(tmp) / "repository", index=colour)
                with self.assertRaises(ValueError) as refused, Quiet():
                    build_site.build(Path(tmp) / "site", offline=True, root=root)
                self.assertIn(why, str(refused.exception))
                self.assertFalse((Path(tmp) / "site").exists(), "nothing is written for a colour that fails")


class IndexColour(unittest.TestCase):
    def test_a_site_that_sets_none_writes_nothing_and_keeps_the_stylesheets_own(self):
        self.assertIsNone(theme.read({}))
        own = json.loads((ROOT / "site/config.json").read_text())
        if "index" not in own:
            style = (ROOT / "site/style.css").read_text()
            for token, value in (("--index", "var(--green)"), ("--index-dark", "var(--green-dark)"),
                                 ("--index-soft", "var(--sage)"), ("--index-tint", "var(--sage-tint)")):
                self.assertIn(f"{token}: {value};", style)

    def test_the_stylesheets_own_green_passes_the_rules_a_configured_colour_must_pass(self):
        colours = theme.read({"index": GREEN})
        self.assertEqual((colours["index"], colours["index-dark"], colours["index-tint"], colours["index-soft"]),
                         (GREEN["color"], GREEN["dark"], GREEN["tint"], GREEN["soft"]))

    def test_what_is_not_given_is_worked_out_and_can_be_read(self):
        for colour in ("#3e5c76", AUBERGINE, "#2f5f63", "#1f1f1f", "#454545"):
            with self.subTest(colour):
                made = theme.read({"index": colour})
                self.assertGreaterEqual(theme.contrast(colour, theme.PAPER), 4.5)
                self.assertGreaterEqual(theme.contrast(theme.WHITE, colour), 4.5)
                self.assertGreaterEqual(theme.contrast(theme.ON, made["index-dark"]), 7)
                self.assertGreaterEqual(theme.contrast(made["index-dark"], made["index-tint"]), 4.5)
                self.assertGreaterEqual(theme.contrast(made["index-soft"], made["index-dark"]), 3)
                # the greys of the dark surface carry text: each reads on what it stands on
                self.assertGreaterEqual(theme.contrast(made["stage-soft"], made["index-dark"]), 7)
                self.assertGreaterEqual(theme.contrast(made["stage-quiet"], made["index-dark"]), 4.5)
                self.assertGreaterEqual(theme.contrast(made["stage-dim"], made["stage-well"]), 4.5)
                self.assertEqual(theme.read({"index": {"color": colour}}), made)
                self.assertRegex(theme.rule(made), r"^:root\{--index:#[0-9a-f]{6};.*\}$")

    def test_each_rule_refuses_what_it_is_for(self):
        self.assertAlmostEqual(theme.contrast("#000000", "#ffffff"), 21.0, places=1)
        self.assertAlmostEqual(theme.contrast("#3c5343", "#f0eee1"), 7.18, places=1)
        cases = (
            ({"color": "#3e5c76", "dark": "#3e5c76"}, "the text of the dark surface"),
            ({"color": "#3e5c76", "tint": "#2f465a"}, "dark text on the tint"),
            ({"color": "#3e5c76", "soft": "#33495c"}, "a mark on the dark surface"),
            ({"color": "#f4f4f4"}, "white text on a button"),
            ("#3e5c7", '"#rrggbb"'),
            ({"dark": "#000000"}, '"index" is a colour, or'),
            ({"color": "#3e5c76", "glow": "#ffffff"}, '"index" is a colour, or'),
            (17, '"index" is a colour, or'),
        )
        for value, why in cases:
            with self.subTest(value=value), self.assertRaises(ValueError) as refused:
                theme.read({"index": value})
            self.assertIn(why, str(refused.exception))
        # a grey has no hue to mistake for a signal, whatever its number says
        self.assertIsNotNone(theme.read({"index": "#4a4a4a"}))


class Names(unittest.TestCase):
    def test_what_differs_between_repositories_is_in_the_configuration_and_checked(self):
        own = community.load_config()
        self.assertTrue((ROOT / ".github/ISSUE_TEMPLATE" / own["finding_form"]).is_file())
        import intake
        import sync
        self.assertEqual(intake.FINDING_LABEL, own["finding_label"])
        self.assertEqual(sync.FINDING_LABEL, own["finding_label"])
        self.assertTrue(intake.FORM_FILE.endswith(own["finding_form"]))
        self.assertIn(own["provider"], intake.HEADING_OF["releases"])
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "site").mkdir()
            base = {"provider": "X", "repository": "https://github.com/a/b", "site_url": "https://a.github.io/b/"}
            file = Path(tmp) / "site/config.json"
            file.write_text(json.dumps(base))
            plain = community.load_config(tmp)
            self.assertEqual((plain["dataset_code_pattern"], plain["finding_label"], plain["finding_form"], plain["dataset"]),
                             (None, "finding", "data-finding.yml", "X"))
            for key, bad in (("dataset_code_pattern", "("), ("dataset_code_pattern", 6), ("finding_label", "Has Capitals"),
                             ("finding_form", "../x.yml"), ("finding_form", "form.txt"),
                             ("ledger_notes", ["<b>x</b>"]), ("ledger_notes", "one"), ("older_numbering_note", 3)):
                file.write_text(json.dumps(base | {key: bad}))
                with self.subTest(key=key, bad=bad), self.assertRaises(ValueError):
                    community.load_config(tmp)

    def test_the_shared_code_names_no_dataset(self):
        """A name of this repository's dataset in the shared files would be wrong in a sibling's copy.
        Two things carry this repository's name on purpose: the names of the file formats of the
        site's data files, which are the same on every site, and the client name sent to GitHub."""
        shared = [ROOT / "scripts" / name for name in
                  ("community.py", "intake.py", "sync.py", "triage.py", "github_api.py", "build_site.py", "check_site.py")]
        shared += sorted((ROOT / "scripts/sitebuild").glob("*.py")) + [ROOT / "site/assets/list.js"]
        allowed = re.compile(r'"schema": "sentier-bafu/[a-z-]+/\d"|sentier-bafu-automation')
        for path in shared:
            if path.name == "lastrun.py":
                continue  # the release build of this repository; a site without one never loads it
            for number, line in enumerate(path.read_text().splitlines(), 1):
                self.assertNotRegex(allowed.sub("", line).lower(), "bafu", f"{path.name}:{number}")


if __name__ == "__main__":
    unittest.main()
