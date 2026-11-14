"""The scripts and the stylesheet are the same files in every dataset's repository. What
differs from one dataset to another is said in site/config.json and nowhere in the code.

These tests build a made-up sibling of this repository: another provider and dataset, release
ids of another shape, datasets without a number, no patched release and no release build, a
form and a label of its own, and an index colour of its own. It holds the shared files (SHARED,
the list site/README.md gives) and nothing else of this repository: not the patch tool, not
the release build, not their scripts. It must pass the check of the records, build and pass
the check of the site, and it must do so with its own copy of the scripts, started as a
sibling would start them. Then the tests hold the colour to its rules: whether a colour can be
read is computed, not judged by eye.
"""

import io
import json
import re
import shutil
import subprocess
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

# What every dataset's repository has as the same files. site/README.md gives this list.
SHARED = (
    "scripts/build_site.py", "scripts/check_site.py", "scripts/community.py", "scripts/triage.py",
    "scripts/intake.py", "scripts/sync.py", "scripts/github_api.py", "scripts/sitebuild",
    "site/style.css", "site/assets/list.js", "site/assets/nunito-latin.woff2", "site/assets/OFL.txt",
    "site/assets/dds-logo.svg", "site/assets/favicon-32x32.png", "schema",
)
REPO = "https://github.com/sentier-dev/sentier-agribalyse"
SITE = "https://sentier-dev.github.io/sentier-agribalyse/"
AUBERGINE = "#5d4a66"
GREEN = {"color": "#3c5343", "dark": "#2d3f33", "tint": "#dce9e1", "soft": "#84ae99"}  # the stylesheet's own


class Quiet:
    def __enter__(self):
        self.real, sys.stdout = sys.stdout, io.StringIO()

    def __exit__(self, *_):
        sys.stdout = self.real


def sibling(target, findings=(2, 4, 12, 16), **changes):
    """A repository about another dataset: the shared files, and everything else its own.
    Its findings follow their issues, so there is no F1; `findings=()` is a site that has none yet."""
    root = Path(target)
    for name in SHARED:
        source, copy = ROOT / name, root / name
        copy.parent.mkdir(parents=True, exist_ok=True)
        if source.is_dir():
            shutil.copytree(source, copy, ignore=shutil.ignore_patterns("__pycache__"))
        else:
            shutil.copy(source, copy)
    pages = (("index.html", "Overview"), ("findings.html", "Findings"), ("feedback.html", "Feedback to ADEME"),
             ("contributions.html", "Contributions"), ("take-part.html", "Take part"))
    documents = [
        {"title": title, "source": f"site/{page[:-5]}.md", "page": page, "description": f"{title} of the AGRIBALYSE workspace."}
        for page, title in pages[1:]
    ] + [{"title": "Data (JSON)", "source": "site/data.md", "page": "about/data.html", "description": "The data files of this site."}]
    config = dict(
        dataset="AGRIBALYSE", provider="ADEME", repository=REPO, site_url=SITE, source_ref="main",
        releases=[{"id": "3.2", "name": "AGRIBALYSE 3.2", "background": "ecoinvent 3.9.1"}],
        older_numbering_until=0, index=AUBERGINE, lookup_example="F1",
        finding_label="agribalyse-finding", finding_form="agribalyse-data-finding.yml",
        home_title="AGRIBALYSE: community findings", title_suffix="AGRIBALYSE findings",
        description="Users of the AGRIBALYSE database record measured findings here.",
        # No patched release and no release build: no page for them is part of this site.
        nav=[list(page) for page in pages], footer=[["about/data.html", "Data (JSON)"]], documents=documents,
    )
    config.update(changes)
    (root / "site/config.json").write_text(json.dumps(config, indent=2) + "\n")
    # Its own words: a page of prose with the block it asks for, and nothing about this repository.
    blocks = {"findings.html": "findings-list", "feedback.html": "feedback-lists", "contributions.html": "contributions-list",
              "about/data.html": "data-files"}
    for doc in documents:
        asked = f"\n\n<!-- generated: {blocks[doc['page']]} -->" if doc["page"] in blocks else ""
        if doc["page"] == "about/data.html":
            asked += "\n\n<!-- generated: status-vocabulary -->"
        (root / doc["source"]).write_text(f"# {doc['title']}\n\nWhat users of AGRIBALYSE find in the data.{asked}\n")
    # Its own checks, under its own names: it has no patch tool to lint.
    (root / ".github/workflows").mkdir(parents=True)
    (root / ".github/workflows/checks.yml").write_text(
        "name: Checks\non:\n  pull_request:\njobs:\n  records:\n    name: Records and unit tests\n"
        "    runs-on: ubuntu-latest\n  site:\n    name: Site build and links\n    runs-on: ubuntu-latest\n"
    )
    # Its own records: findings about processes that have a name and no number.
    for name in ("community/findings/0", "community/contributions", "community/recommendations"):
        (root / name).mkdir(parents=True)
    (root / "community/recommendations/tracker.json").write_text("[]\n")
    for n in findings:
        record = synthetic_finding(n)
        record.update(datasets=[], scope="The process Wheat grain, conventional, at farm gate (FR).", releases=["3.2"])
        text = json.dumps(record).replace("https://github.com/sentier-dev/sentier-bafu", REPO)
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

    def test_it_runs_on_its_own_copy_of_the_scripts_without_the_patch_tool_or_the_release_build(self):
        """Started as a sibling starts them: its own files, its own folder, a new process. A
        script of the shared set that reaches for a file outside the set fails here."""
        present = sorted(p.relative_to(self.root).as_posix() for p in (self.root / "scripts").iterdir())
        self.assertEqual(present, sorted(name for name in SHARED if name.startswith("scripts/")))
        for gone in ("scripts/last_run.py", "scripts/release_build", "scripts/build_release.py",
                     "scripts/patches_snapshot.py", "src", "site/patched-release.md", "site/run-steps.json"):
            self.assertFalse((self.root / gone).exists(), gone)

        def run(*arguments):
            return subprocess.run([sys.executable, *arguments], cwd=self.root, capture_output=True, text=True, check=False)

        checked = run("scripts/community.py", "check")
        self.assertEqual(checked.returncode, 0, checked.stdout + checked.stderr)
        self.assertIn("Validated 4 findings", checked.stdout)
        self.assertFalse((self.root / "community/findings/0/F1.json").exists())
        out = Path(self.temp.name) / "its-own-build"
        built = run("scripts/build_site.py", "--offline", "--out", str(out))
        self.assertEqual(built.returncode, 0, built.stdout + built.stderr)
        self.assertNotIn("release build", built.stdout)
        self.assertEqual(run("scripts/check_site.py", str(out)).returncode, 0)
        self.assertEqual((out / "findings.html").read_text(), self.pages["findings.html"].replace(str(self.out), str(out)))
        # the scripts the workflows start with the runner's own Python and nothing installed
        names = run("-I", "-c", "import sys; sys.path.insert(0, 'scripts'); import intake, sync, triage; "
                                "print(intake.CHECK_CONTEXTS, intake.FINDING_LABEL, sync.FINDING_LABEL, intake.FORM_FILE)")
        self.assertEqual(names.returncode, 0, names.stderr)
        self.assertEqual(names.stdout.strip(),
                         "('Records and unit tests', 'Site build and links') agribalyse-finding agribalyse-finding "
                         ".github/ISSUE_TEMPLATE/agribalyse-data-finding.yml")

    def test_a_release_id_is_a_name_of_the_configured_list_whatever_its_shape(self):
        record = json.loads((self.root / "community/findings/0/F2.json").read_text())
        self.assertEqual(record["releases"], ["3.2"])
        self.assertIn("releases/3.2.html", self.pages)
        self.assertIn("AGRIBALYSE 3.2 is built on ecoinvent 3.9.1.", self.pages["releases/3.2.html"])
        # an id the list does not have is refused, as in this repository
        record["releases"] = ["4.0"]
        (self.root / "community/findings/0/F2.json").write_text(json.dumps(record))
        try:
            errors, _, _ = community.problems(self.root)
            self.assertTrue(any("4.0" in error for error in errors), errors)
        finally:
            record["releases"] = ["3.2"]
            (self.root / "community/findings/0/F2.json").write_text(json.dumps(record) + "\n")
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

    def test_the_data_page_names_a_finding_the_site_has_and_none_on_a_site_without_one(self):
        data = self.pages["about/data.html"]
        self.assertIn('href="../api/v1/findings/F2.json"', data)
        self.assertIn("Replace F2 by any finding", data)
        self.assertNotIn("F1.json", data)
        self.assertTrue((self.out / "api/v1/findings/F2.json").is_file())
        with tempfile.TemporaryDirectory() as tmp:
            root, out = sibling(Path(tmp) / "repository", findings=()), Path(tmp) / "site"
            with Quiet():
                build_site.build(out, offline=True, root=root)
                self.assertEqual(check_site.check(out), 0, "a site without a finding yet builds and passes")
            text = (out / "about/data.html").read_text()
            self.assertNotIn("api/v1/findings/F", text)
            self.assertIn("api/v1/findings.json", text)

    def test_a_providers_name_takes_the_article_it_needs(self):
        self.assertEqual((community.with_article("BAFU"), community.with_article("ADEME")), ("A BAFU", "An ADEME"))
        self.assertIn("An ADEME release covers the point.", self.pages["index.html"])
        self.assertIn("An ADEME release covers this point", self.pages["about/data.html"])
        for name, text in self.pages.items():
            self.assertNotIn("A ADEME", text, name)

    def test_a_site_without_community_patches_says_nothing_about_them(self):
        self.assertFalse((self.root / "community/patches.json").exists())
        listing, housekeeping = self.pages["findings.html"], self.pages["housekeeping.html"]
        self.assertNotIn('id="patch"', listing)
        self.assertNotIn("Has a patch", listing)
        self.assertIn('id="kind"', listing)  # the other filters are there
        self.assertNotIn("ommunity patch", housekeeping)
        self.assertIn("what in the records and the issues needs a hand", housekeeping)
        self.assertIn('id="check"', housekeeping)

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

    def test_the_list_of_shared_files_is_the_one_the_site_readme_gives(self):
        told = (ROOT / "site/README.md").read_text().split("## A sibling site", 1)[1].split("\n## ", 1)[0]
        for name in SHARED:
            self.assertIn(f"`{name}`" if "/assets/" not in name else f"`{name.rsplit('/', 1)[1]}`", told, name)
            self.assertTrue((ROOT / name).exists(), name)
        # every script of the site and the records is either shared or named as not shared
        scripts = sorted(p.relative_to(ROOT).as_posix() for p in (ROOT / "scripts").iterdir()
                         if p.suffix == ".py" or p.is_dir() and p.name != "__pycache__")
        own = {"scripts/release_build", "scripts/build_release.py", "scripts/export_release.py", "scripts/last_run.py",
               "scripts/patches_snapshot.py", "scripts/full_release_table.py", "scripts/check_patched_release.py",
               "scripts/new_patch.py", "scripts/build_brightway_flows_data.py", "scripts/check_integration_receipt.py",
               "scripts/audit_flow_mapping.py", "scripts/audit_registry.py", "scripts/build_checks.py"}
        self.assertEqual(set(scripts) - set(SHARED) - own, set(), "a new script is shared, or it is this repository's own")

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
