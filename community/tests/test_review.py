"""Reviewing a change: the classes of a comparison, the index of a review, and their pages.

A comparison of the second version says of every value which of six classes it is in
(`scripts/runrecord/before_after.py`), and a run that built several states says which pairs
of them were compared (`review.json`, `scripts/runrecord/review.py`). What the tests hold:

- the made-up example every repository runs on has one value of each class, and no other;
- a file of the first version is still a file a page can show, and is checked as one;
- a file is data: what the format does not describe is refused, whatever its type;
- a claim a repository keeps to itself is published as a count, never as an empty claim;
- the index finds the pair of builds that differs by exactly the chosen causes, or says
  which build is missing;
- a run's record carries the review and its comparisons, and one bad file takes no other
  with it;
- a sibling site gets the pages from the shared files alone.
"""

import copy
import html
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

import last_run  # noqa: E402
from runrecord import before_after, example, review  # noqa: E402
from test_before_after import a_comparison, a_record  # noqa: E402
from test_last_run import OTHER_LINES, OTHER_RUN, a_transcript, another_account  # noqa: E402
from test_sibling_site import build_site, sibling  # noqa: E402

CLIMATE, WATER = example.CLIMATE, example.WATER
PAIR = example.PAGE.removesuffix(".html") + ".json"


def first_version(data):
    """A comparison as the first version of the format wrote it."""
    old = {k: v for k, v in data.items() if k not in before_after.ADDED["file"]}
    old["format"] = before_after.FORMATS[0]
    old["indicators"] = [{k: v for k, v in i.items() if k not in before_after.ADDED["indicator"]} for i in old["indicators"]]
    old["causes"] = [{k: v for k, v in c.items() if k not in before_after.ADDED["cause"]} for c in old["causes"]]
    old["moved"] = [{k: v for k, v in m.items() if k not in before_after.ADDED["moved"]} for m in old["moved"]]
    return old


class ClassTests(unittest.TestCase):
    def test_the_example_holds_one_value_of_each_class_and_no_other(self):
        data = example.comparison()
        self.assertEqual(before_after.shape_errors(data), [])
        listed = {(key, item["id"]): kind for item in data["moved"] for key, kind in item["classes"].items()}
        for where, kind in example.EXPECTED.items():
            self.assertEqual(listed[where], kind, where)
        self.assertEqual(set(example.EXPECTED.values()) | {before_after.UNCHANGED}, set(before_after.CLASSES))
        totals = review.totals(data)
        self.assertEqual(totals, dict.fromkeys(before_after.CLASSES, 1) | {before_after.UNCHANGED: 7})
        for indicator in data["indicators"]:
            self.assertEqual(sum(indicator["classes"].values()), indicator["compared"])

    def test_a_value_is_classified_by_the_threshold_the_noise_and_the_claims(self):
        down = (before_after.scope(direction="down", largest=0.25), False)
        cases = [
            ((1.0, 1.0), {}, before_after.UNCHANGED),
            ((1.0, 1.1), {}, before_after.NOT_CLAIMED),
            ((1.0, 1.1), {"noise": 0.2}, before_after.NOISE),
            ((1.0, 1.3), {"noise": 0.2}, before_after.NOT_CLAIMED),
            ((4.0, 3.5), {"covering": [down]}, before_after.AS_CLAIMED),
            ((4.0, 2.0), {"covering": [down]}, before_after.OFF_CLAIM),  # further than it says
            ((4.0, 4.5), {"covering": [down]}, before_after.OFF_CLAIM),  # the other way
            ((4.0, 4.0), {"covering": [down]}, before_after.NOT_MOVED),
            # a reach that was worked out says what may move, not what must
            ((4.0, 4.0), {"covering": [(down[0], True)]}, before_after.UNCHANGED),
            # noise comes before a claim: what two builds of one state differ by proves nothing
            ((4.0, 3.9), {"covering": [down], "noise": 0.1}, before_after.NOISE),
        ]
        for (before, after), more, kind in cases:
            self.assertEqual(before_after.classify(before, after, 1e-6, **more), kind, (before, after, more))
        self.assertIsNone(before_after.classify(None, 1.0, 1e-6))

    def test_the_noise_is_what_two_builds_of_one_state_differ_by(self):
        self.assertEqual(before_after.noise_of(example.BASE[CLIMATE], example.BASE_AGAIN[CLIMATE]), 0.0)
        self.assertAlmostEqual(before_after.noise_of(example.BASE[WATER], example.BASE_AGAIN[WATER]), 0.2 / 4.2)
        noise = example.comparison()["noise"]
        self.assertTrue(noise["measured"])
        self.assertEqual(noise["between"], ["base", "base again"])

    def test_what_a_page_shows_as_moved_is_what_the_run_counted(self):
        # written with six digits, the two results are equal; the run compared them in full
        data = before_after.compare(
            "Two", ("One", None), ("Other", None), ("thing", "things"), [("x", "X", None, None)],
            {"x": {"a": (1.00000001, 1.00000009), "b": (2.0, 2.0)}}, threshold=1e-9, floors=0.0,
        )
        (item,) = data["moved"]
        self.assertEqual(item["values"]["x"], [1.0, 1.0])
        self.assertEqual(item["moved"], ["x"])
        self.assertEqual(data["indicators"][0]["moved"], 1)

    def test_a_ratio_that_is_no_number_is_no_ratio(self):
        self.assertIsNone(before_after.ratio(1e-300, 1e300))
        self.assertIsNone(before_after.ratio(1e300, 1e-300))
        self.assertIsNone(before_after.ratio(0.0, 1.0))
        self.assertEqual(before_after.ratio(-2.0, -1.0), 0.5)
        self.assertEqual(before_after.band(1e-300, 1e300, 0.0), "opposite sign or zero")


class ExampleTests(unittest.TestCase):
    def test_the_examples_in_the_text_of_the_module_are_true(self):
        import doctest

        found = doctest.testmod(before_after)
        self.assertEqual(found.failed, 0)
        self.assertGreaterEqual(found.attempted, 17)


class ClaimTests(unittest.TestCase):
    def test_a_claim_kept_here_is_published_as_a_count(self):
        kept = before_after.claim("It reaches these.", [before_after.scope(["x"], {"a", "b", "c"})], derived=True)
        shown = before_after.published(kept, keep_items=False)
        self.assertEqual((shown["scope"], shown["derived"], shown["reach"]), ([], True, 3))
        # one that lists more than a file may hold is published the same way, whoever stated it
        many = before_after.claim("Many.", [before_after.scope(items={str(n) for n in range(before_after.MAX_SCOPE_ITEMS + 1)})])
        shown = before_after.published(many)
        self.assertEqual((shown["scope"], shown["derived"], shown["reach"]), ([], True, before_after.MAX_SCOPE_ITEMS + 1))
        # and a short stated claim stays as it was stated
        self.assertEqual(before_after.published(example.causes()[1]["claim"])["scope"][0]["items"], ["p2"])

    def test_a_claim_without_a_scope_expects_nothing_to_move(self):
        nothing = before_after.claim("Only a name changes.")
        found = before_after.classes_of({"x": {"a": (1.0, 2.0)}}, 1e-6, claims=[nothing])
        self.assertEqual(found["classes"]["x"]["a"], before_after.NOT_CLAIMED)


class VersionTests(unittest.TestCase):
    def test_a_file_of_the_first_version_is_still_one_a_page_can_show(self):
        old = first_version(a_comparison())
        self.assertEqual(before_after.shape_errors(old), [])
        record = a_record(**{before_after.FILE: old})
        self.assertEqual(record["before_after"], old)
        # and it is checked as what it says it is: the first version has no classes
        old["noise"] = None
        self.assertIn("a key this format does not know: noise", before_after.shape_errors(old))

    @unittest.skipIf(build_site is None, "the site build needs the markdown package")
    def test_a_page_shows_a_file_of_the_first_version(self):
        from sitebuild import beforeafter

        page = beforeafter.body(first_version(a_comparison()))
        self.assertIn("The export and the linked copy", page)
        self.assertNotIn("ba-classes", page)

    def test_what_the_second_version_does_not_describe_is_refused(self):
        good = example.comparison()
        self.assertEqual(before_after.shape_errors(good), [])

        def broken(change):
            data = copy.deepcopy(good)
            change(data)
            return before_after.shape_errors(data)

        cases = {
            "an unknown class": lambda d: d["indicators"][0]["classes"].update({"fine": 1}),
            "a class of a value that is no class": lambda d: d["moved"][0]["classes"].update({CLIMATE: "fine"}),
            "a claim of another shape": lambda d: d["causes"][0]["claim"].pop("derived"),
            "a scope of an indicator the file lacks": lambda d: d["causes"][0]["claim"]["scope"][0].update(indicators=["x:other"]),
            "a direction that is none": lambda d: d["causes"][0]["claim"]["scope"][0].update(direction="sideways"),
            "more moved than compared": lambda d: d["indicators"][0].update(moved=99),
            "more higher and lower than moved": lambda d: d["indicators"][0].update(higher=3, lower=3),
            "two items of one id": lambda d: d["moved"].append(copy.deepcopy(d["moved"][0])),
            "moved in an indicator the file lacks": lambda d: d["moved"][0].update(moved=["x:other"]),
            "a noise that is no number": lambda d: d["indicators"][0].update(noise=float("inf")),
            "a noise between three builds": lambda d: d["noise"].update(between=["a", "b", "c"]),
            "a floor that is no number": lambda d: d["indicators"][0].update(floor="low"),
            "a page of a detail that is a path": lambda d: d["moved"][0].update(detail="../secret.json"),
        }
        for what, change in cases.items():
            self.assertTrue(broken(change), what)

    def test_a_file_of_any_type_is_refused_and_never_raises(self):
        good = example.comparison()
        odd = [None, [], "text", 7, {"format": before_after.FORMAT}, good | {"indicators": 7}, good | {"moved": [7]},
               good | {"moved": [good["moved"][0] | {"id": ["a"]}]}, good | {"causes": [{"id": {"a": 1}}]},
               good | {"indicators": [good["indicators"][0] | {"id": 10**400}]},
               good | {"moved": [good["moved"][0] | {"values": {CLIMATE: [10**400, 1]}}]},
               good | {"threshold": 10**400}, good | {"items": "many"}, good | {"noise": []}, good | {"variants": {}}]
        for data in odd:
            self.assertTrue(before_after.shape_errors(data), repr(data)[:80])
        self.assertTrue(review.shape_errors(None) and review.shape_errors({"format": review.FORMAT, "runs": 7, "causes": []}))

    def test_a_file_is_written_one_item_a_line_and_never_larger_than_a_site_reads(self):
        with tempfile.TemporaryDirectory() as tmp:
            place = before_after.write(example.comparison(), Path(tmp) / before_after.FILE)
            text = place.read_text(encoding="utf-8")
            self.assertEqual(json.loads(text), example.comparison())
            listed = [line for line in text.splitlines() if line.startswith('  {"id"')]
            self.assertEqual(len(listed), len(example.comparison()["moved"]))
            # a title that holds the words `"moved": []` does not move the list
            odd = example.comparison() | {"title": 'A "moved": [] of its own'}
            self.assertEqual(json.loads(before_after.write(odd, place).read_text(encoding="utf-8")), odd)
            still = example.comparison() | {"moved": []}
            self.assertEqual(json.loads(before_after.write(still, place).read_text(encoding="utf-8")), still)
            self.assertEqual(last_run.MAX_FILE, before_after.MAX_BYTES)
            limit, before_after.MAX_BYTES = before_after.MAX_BYTES, 2000
            try:
                with self.assertRaisesRegex(ValueError, "List fewer items"):
                    before_after.write(example.comparison(), Path(tmp) / "large.json")
                self.assertFalse((Path(tmp) / "large.json").exists())
            finally:
                before_after.MAX_BYTES = limit

    def test_a_breakdown_of_one_item_is_a_file_of_its_own(self):
        parts = before_after.detail("p1", {CLIMATE: ("kg CO2 eq", [("Fertiliser", "background process", 6.0, 5.0)], 3)})
        self.assertEqual(before_after.detail_errors(parts), [])
        self.assertEqual(parts["format"], before_after.DETAIL_FORMAT)
        self.assertTrue(before_after.detail_errors(parts | {"exchanges": []}))
        self.assertTrue(before_after.detail_errors({"format": before_after.DETAIL_FORMAT, "item": 7, "indicators": {}}))


class IndexTests(unittest.TestCase):
    def setUp(self):
        self.index = example.index()

    def test_the_index_of_the_example_is_one_a_page_can_show(self):
        self.assertEqual(review.shape_errors(self.index), [])
        (pair,) = self.index["pairs"]
        self.assertEqual(pair["classes"], dict.fromkeys(before_after.CLASSES, 1) | {before_after.UNCHANGED: 7})
        self.assertEqual(review.difference(self.index, pair), (frozenset({"fix-1", "fix-2"}), frozenset()))

    def test_the_pair_that_differs_by_exactly_the_chosen_causes_is_found(self):
        both = review.isolating(self.index, ["fix-1", "fix-2"])
        self.assertEqual(both["pair"]["after"], "changed")
        self.assertEqual((both["also"], both["missing"]), ([], []))
        # no build holds fix-1 alone: the closest pair is named, and what else it holds
        one = review.isolating(self.index, ["fix-1"])
        self.assertIsNone(one["pair"])
        self.assertEqual(one["closest"]["after"], "changed")
        self.assertEqual((one["also"], one["missing"]), (["fix-2"], []))
        nothing = review.isolating(self.index, [])
        self.assertEqual((nothing["pair"], nothing["closest"]), (None, None))
        unknown = review.isolating(self.index, ["fix-9"])
        self.assertEqual((unknown["pair"], unknown["closest"], unknown["missing"]), (None, None, ["fix-9"]))

    def test_a_pair_whose_first_build_holds_more_isolates_nothing(self):
        index = copy.deepcopy(self.index)
        index["runs"] += [review.run("one", "Base with the first fix", ["fix-1"]), review.run("two", "Base with the second fix", ["fix-2"])]
        # from the first fix to the second: fix-2 comes, and fix-1 goes. Two changes, not one.
        index["pairs"].append(review.pair("one", "two"))
        self.assertEqual(review.shape_errors(index), [])
        self.assertEqual(review.difference(index, index["pairs"][-1]), (frozenset({"fix-2"}), frozenset({"fix-1"})))
        found = review.isolating(index, ["fix-2"])
        self.assertIsNone(found["pair"])
        self.assertEqual((found["closest"]["after"], found["also"]), ("changed", ["fix-1"]))
        # with the build in between, the second fix is isolated
        index["pairs"].append(review.pair("one", "changed"))
        self.assertEqual(review.isolating(index, ["fix-2"])["pair"], review.pair("one", "changed"))
        self.assertIsNone(review.isolating(index, ["fix-1"])["pair"])

    def test_what_the_index_does_not_describe_is_refused(self):
        def broken(change):
            data = copy.deepcopy(self.index)
            change(data)
            return review.shape_errors(data)

        cases = {
            "a build of a cause the file lacks": lambda d: d["runs"][2]["contains"].append("fix-9"),
            "a pair of a build the file lacks": lambda d: d["pairs"][0].update(after="elsewhere"),
            "a page that is a path": lambda d: d["pairs"][0].update(page="../index.html"),
            "a class the format lacks": lambda d: d["pairs"][0]["classes"].update({"fine": 1}),
            "two builds of one id": lambda d: d["runs"].append(copy.deepcopy(d["runs"][0])),
            "two causes of one id": lambda d: d["causes"].append(copy.deepcopy(d["causes"][0])),
            "a repeat of a build the file lacks": lambda d: d["runs"][1].update(replica_of="elsewhere"),
            "an identity that is no table of texts": lambda d: d["runs"][0].update(identity={"commit": 7}),
            "a key the format lacks": lambda d: d.update(verdict="fine"),
        }
        for what, change in cases.items():
            self.assertTrue(broken(change), what)
        with self.assertRaisesRegex(ValueError, "not an index of a review"):
            review.index("", [], [], [])


class RecordTests(unittest.TestCase):
    def files(self, **changes):
        return {before_after.FILE: example.comparison(), review.FILE: example.index(), PAIR: example.comparison()} | changes

    def test_a_run_that_reviewed_carries_the_index_and_its_comparisons(self):
        record = a_record(**self.files())
        self.assertEqual(last_run.shape_errors(record), [])
        self.assertEqual(record["review"], example.index())
        self.assertEqual(record["pairs"], {example.PAGE: example.comparison()})
        self.assertIn("its review", last_run.said(record))
        plain = a_record()
        self.assertEqual((plain["review"], plain["pairs"]), (None, {}))

    def test_one_bad_file_takes_no_other_with_it(self):
        # the comparison of the pair is of no shape: the review is shown, that pair has no page
        record = a_record(**self.files(**{PAIR: {"format": before_after.FORMAT, "moved": 7}}))
        self.assertEqual(record["pairs"], {})
        self.assertIsNotNone(record["review"])
        self.assertIsNotNone(record["before_after"])
        self.assertIn(PAIR, record["kept_note"])
        self.assertEqual(last_run.shape_errors(record), [])
        # an index of no shape: the run and its own comparison are shown without it
        record = a_record(**self.files(**{review.FILE: {"format": review.FORMAT, "runs": [{"id": ["x"]}], "causes": []}}))
        self.assertIsNone(record["review"])
        self.assertEqual(record["pairs"], {})
        self.assertIsNotNone(record["before_after"])
        self.assertEqual(record["kept"], "read")
        # a file a check was never written for is a finding, not an error of the build
        record = a_record(**{before_after.FILE: {"format": before_after.FORMAT, "indicators": [{"id": 10**400}]}})
        self.assertIsNone(record["before_after"])
        self.assertIsNotNone(record["summary"])

    def test_a_run_that_was_not_on_github_brings_its_review_too(self):
        lines = a_transcript(OTHER_LINES, exit_code=0)
        record = last_run.local(another_account(), lines, run=OTHER_RUN, compared=example.comparison(),
                                index=example.index(), pairs={example.PAGE: example.comparison()})
        self.assertEqual(last_run.shape_errors(record), [])
        with self.assertRaises(ValueError):
            last_run.local(another_account(), lines, run=OTHER_RUN, index=example.index() | {"runs": []})
        record["pairs"] = {"../x.html": example.comparison()}
        self.assertTrue(last_run.shape_errors(record))


@unittest.skipIf(build_site is None, "the site build needs the markdown package")
class PageTests(unittest.TestCase):
    """A sibling site, made of the shared files alone, with a run that reviewed the example."""

    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.root = sibling(Path(cls.temp.name) / "repository", run={"name": "Linking run", "workflow": "link.yml", "artifact": "link-results"})
        config = json.loads((cls.root / "site/config.json").read_text())
        config["documents"].append({"title": "The run", "source": "site/run.md", "page": "run.html", "description": "The last linking run."})
        config["nav"].append(["run.html", "The run"])
        (cls.root / "site/config.json").write_text(json.dumps(config, indent=2) + "\n")
        (cls.root / "site/run.md").write_text("# The run\n\nWhat the last run did.\n\n<!-- generated: last-run -->\n")
        cls.kept = Path(cls.temp.name) / "kept"
        cls.kept.mkdir()
        compared = example.comparison(step="export as shipped")
        for name, data in (("run.json", another_account()), ("transcript.json", a_transcript(OTHER_LINES, exit_code=0)),
                           (before_after.FILE, compared), (review.FILE, example.index()), (PAIR, example.comparison())):
            (cls.kept / name).write_text(json.dumps(data))
        cls.out = cls.site("with", "--before-after", str(cls.kept / before_after.FILE), "--review", str(cls.kept / review.FILE))
        cls.pages = {name: (cls.out / name).read_text() for name in ("review.html", example.PAGE, "before-after.html", "run.html")}

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    @classmethod
    def run_in(cls, *arguments):
        return subprocess.run([sys.executable, *arguments], cwd=cls.root, capture_output=True, text=True, check=False)

    @classmethod
    def site(cls, name, *more, fails=False):
        record, out = cls.kept / f"{name}.json", Path(cls.temp.name) / f"site-{name}"
        made = cls.run_in("-I", "scripts/last_run.py", "--local", "--summary", str(cls.kept / "run.json"),
                          "--transcript", str(cls.kept / "transcript.json"), *more, "--out", str(record))
        if fails:
            return made
        assert made.returncode == 0, made.stdout + made.stderr
        built = cls.run_in("scripts/build_site.py", "--offline", "--last-run", str(record), "--out", str(out))
        assert built.returncode == 0, built.stdout + built.stderr
        return out

    @staticmethod
    def words(page):
        return " ".join(html.unescape(re.sub(r"<script.*?</script>|<[^>]+>", " ", page, flags=re.S)).split())

    def test_the_site_passes_its_check_and_holds_the_review_as_files(self):
        self.assertEqual(self.run_in("scripts/check_site.py", str(self.out)).returncode, 0)
        self.assertEqual(json.loads((self.out / "api/v1/review.json").read_text()), example.index())
        self.assertEqual(json.loads((self.out / f"api/v1/{PAIR}").read_text()), example.comparison())
        self.assertTrue((self.out / "assets/review.js").is_file())

    def test_build_views_join_the_review_to_the_comparison_and_keep_old_addresses(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "repo"
            shutil.copytree(self.root, root)
            config_file = root / "site/config.json"
            config = json.loads(config_file.read_text())
            config["build_navigation"] = {
                "comparison": "Comparison & diagnostics",
                "pages": {"about/data.html": "Build evidence", "absent.html": "Missing view"},
            }
            config_file.write_text(json.dumps(config))
            out = Path(tmp) / "site"
            build_site.build(out, root=root, offline=True, last_run_snapshot=self.kept / "with.json")
            comparison = (out / "before-after.html").read_text()
            self.assertEqual(comparison.count("<h1>"), 1)
            self.assertIn('id="review"', comparison)
            self.assertIn('id="moved"', comparison)
            self.assertIn('data-rv-cause', comparison)
            self.assertIn('href="before-after.html#review"', (out / example.PAGE).read_text())
            self.assertIn('url=before-after.html#review', (out / "review.html").read_text())
            for name in ("before-after.html", "run.html", example.PAGE, "about/data.html"):
                bar = re.search(r'<nav class="subnav".*?</nav>', (out / name).read_text(), re.S)[0]
                self.assertNotIn("absent.html", bar)
                self.assertIn('aria-current=', bar)
                self.assertIn("Comparison &amp; diagnostics", bar)
            self.assertNotIn('<nav class="subnav"', (out / "findings.html").read_text())
            self.assertNotIn('<nav class="subnav"', (out / "index.html").read_text())
            self.assertEqual(self.run_in("scripts/check_site.py", str(out)).returncode, 0)

            config["build_navigation"]["on_home"] = True
            config_file.write_text(json.dumps(config))
            build_site.build(out, root=root, offline=True, last_run_snapshot=self.kept / "with.json")
            home = (out / "index.html").read_text()
            main = re.search(r'<nav class="nav".*?</nav>', home, re.S)[0]
            bar = re.search(r'<nav class="subnav".*?</nav>', home, re.S)[0]
            self.assertIn('<a href="index.html" aria-current="page">', main)
            self.assertEqual(main.count("aria-current"), 1)
            self.assertIn('aria-label="The run: its parts"', bar)
            self.assertEqual(re.findall(r'href="([^"]+)"', bar), ["run.html", "before-after.html", "about/data.html"])
            self.assertNotIn("aria-current", bar)
            self.assertNotIn('<nav class="subnav"', (out / "findings.html").read_text())

    def test_private_diagnostics_cannot_enter_a_public_run_record(self):
        self.assertTrue(last_run.public_diagnostics_errors({"audience": "local"}))
        self.assertTrue(last_run.public_diagnostics_errors({"audience": "public", "matrix": {"file": "matrix.json"}}))

    def test_public_diagnostics_use_the_same_result_page(self):
        try:
            from sentier_diagnostics import example as diagnostics_example
        except ImportError:
            self.skipTest("the Pages diagnostics renderer is not installed")
        with tempfile.TemporaryDirectory() as tmp:
            record = json.loads((self.kept / "with.json").read_text())
            record["diagnostics"] = diagnostics_example.build()
            snapshot = Path(tmp) / "run.json"
            snapshot.write_text(json.dumps(record))
            out = Path(tmp) / "site"
            build_site.build(out, offline=True, last_run_snapshot=snapshot)
            page = (out / "before-after.html").read_text()
            self.assertEqual(page.count(" data-sentier-diagnostics"), 1)
            self.assertIn('<details class="ba-pair">', page)
            self.assertIn('id="review"', page)
            self.assertIn("before-after.html#diagnostics", (out / "diagnostics.html").read_text())
            self.assertTrue((out / "assets/diagnostics.js").is_file())
            self.assertFalse((out / "matrix.json").exists())
            self.assertEqual(self.run_in("scripts/check_site.py", str(out)).returncode, 0)

    def test_the_walk_leads_to_the_review_and_every_page_leads_back(self):
        first = self.pages["run.html"].split('id="run-step-2"')[0]
        self.assertIn('href="before-after.html"', first)
        self.assertIn('<a class="button" href="review.html">One cause at a time</a>', first)
        self.assertIn('<p class="crumb"><a href="run.html#run-step-1">Step 1 of the linking run</a></p>', self.pages["review.html"])
        self.assertIn('<p class="crumb"><a href="review.html">The review</a></p>', self.pages[example.PAGE])
        for name, page in self.pages.items():
            for part in re.findall(r'<nav class="(?:nav|footer-links)".*?</nav>', page, flags=re.S):
                self.assertNotIn("review", part, name)

    def test_the_review_names_each_cause_with_its_claim_and_each_pair_with_its_counts(self):
        page, text = self.pages["review.html"], self.words(self.pages["review.html"])
        self.assertEqual(len(re.findall(r'<input type="checkbox" data-rv-cause value="fix-[12]" disabled>', page)), 2)
        self.assertIn("Claim. Wheat and rice go down in climate change, by 30 % at most. Nothing else moves.", text)
        self.assertRegex(page, rf'<th scope="row">Base</th><td>Base with both fixes</td><td><code>fix-1</code>, <code>fix-2</code></td>.*?<a href="{example.PAGE}">Compare</a>')
        for kind in before_after.CLASSES:
            self.assertRegex(page, rf"<b>{7 if kind == before_after.UNCHANGED else 1}</b> {kind}")
        self.assertIn("A second build of Base. Two builds of this state differ.", text)
        payload = json.loads(re.search(r'<script type="application/json" data-rv-data>(.*?)</script>', page, flags=re.S).group(1))
        self.assertEqual([run["id"] for run in payload["runs"]], ["base", "base-again", "changed"])

    def test_the_comparison_says_what_the_classes_add_up_to(self):
        page, text = self.pages[example.PAGE], self.words(self.pages[example.PAGE])
        self.assertIn("ba-classes", page)
        for kind in before_after.CLASSES:
            self.assertIn(kind, text)
        self.assertIn("Noise was measured between base and base again", text)
        self.assertIn("All 5 are listed. 1 of them did not move and is listed because a stated claim names it.", text)
        # each item that moved is shown with the class of its value, as the run counted it
        rows = dict(re.findall(r'<tr data-i="\d+"><th scope="row"[^>]*>(?:<[^>]+>)*([A-Za-z]+).*?</th>(.*?)</tr>', page, flags=re.S))
        self.assertIn("k-claimed", rows["Wheat"])
        self.assertIn("k-off", rows["Rice"])
        self.assertIn("k-unclaimed", rows["Barley"])
        self.assertIn("k-noise", rows["Oats"])
        self.assertIn("k-unmet", rows["Maize"])

    def test_a_review_of_another_shape_is_not_made_a_record_of(self):
        (self.kept / "odd-review.json").write_text(json.dumps({"format": review.FORMAT, "runs": 7}))
        made = self.site("odd", "--review", str(self.kept / "odd-review.json"), fails=True)
        self.assertEqual(made.returncode, 1)
        self.assertIn("not written: odd-review.json:", made.stdout)
        self.assertNotIn("Traceback", made.stdout + made.stderr)


class FrameTests(unittest.TestCase):
    """A site with a frame of its own is told what the pages need of it, and is told right."""

    OWN = re.compile(r"^(ba|rv|k|is)-")

    @classmethod
    def setUpClass(cls):
        told = (ROOT / "docs/before-after.md").read_text().split("**On a site whose frame is its own.**")[1]
        told = told.split("A test holds this list")[0]
        cls.tokens = set(re.findall(r"`(--[a-z0-9-]+)`", told))
        cls.tokens |= {f"--s{n}" for n in range(2, 7)}  # "the spaces --s2 to --s6"
        cls.classes = set(re.findall(r"`([a-z][a-z-]*)`", told.split("- classes:")[1]))
        cls.style = (ROOT / "site/assets/before-after.css").read_text()

    def test_every_token_the_styles_read_is_named(self):
        local = set(re.findall(r"(--[a-z0-9-]+)\s*:", self.style))  # set by these styles themselves
        used = set(re.findall(r"var\((--[a-z0-9-]+)", self.style)) - local - {"--d"}
        self.assertEqual(used - self.tokens, set(), "read by the styles and not named in docs/before-after.md")
        self.assertEqual(self.tokens - used, set(), "named in docs/before-after.md and read by no style")

    def test_every_class_of_the_frame_that_a_page_uses_is_named(self):
        used = set()
        for path in ("scripts/sitebuild/beforeafter.py", "scripts/sitebuild/review.py", "site/assets/before-after.js", "site/assets/review.js"):
            source = (ROOT / path).read_text()
            for found in re.findall(r"class=\\?[\"']([A-Za-z0-9 _-]*)", source):
                used |= set(found.split())
        frame = {"wrap", "page", "prose", "wide"}  # of `page()`, the frame of the shared build
        used = {name for name in used if not self.OWN.match(name)} - frame
        self.assertEqual(used - self.classes, set(), "used by a page and not named in docs/before-after.md")
        self.assertEqual(self.classes - used, set(), "named in docs/before-after.md and used by no page")


@unittest.skipIf(build_site is None, "the site build needs the markdown package")
class TextTests(unittest.TestCase):
    """Every text of a file is text on the page, in markup and in the data for the script."""

    def test_no_text_of_a_file_is_markup(self):
        from sitebuild import beforeafter
        from sitebuild import review as review_page

        nasty, word = "<!--<script>alert(1)</script><img src=x onerror=alert(2)>", "<img src=x onerror=alert(2)>"
        data = example.comparison(indicator={"one": word, "many": word}, notes=[nasty])
        data["items"] |= {"one": word, "many": word}
        data["title"] = nasty
        data["moved"][0]["name"] = nasty
        data["causes"][0] |= {"title": nasty, "kind": word}
        data["causes"][0]["claim"]["text"] = nasty
        self.assertEqual(before_after.shape_errors(data), [])
        index = example.index(data)
        index["title"] = nasty
        index["runs"][0] |= {"label": nasty, "identity": {nasty[:40]: nasty}}
        self.assertEqual(review.shape_errors(index), [])
        for page in (beforeafter.body(data), review_page.body(index)):
            outside = re.sub(r'<script type="application/json"[^>]*>.*?</script>', "", page, flags=re.S)
            self.assertNotIn("<img", outside)
            self.assertNotIn("<script>alert", outside)
            self.assertNotIn("<!--", page)
            for payload in re.findall(r'<script type="application/json"[^>]*>(.*?)</script>', page, flags=re.S):
                self.assertNotRegex(payload, r"[<>&]")
                json.loads(payload)

    def test_a_result_below_zero_is_on_the_side_it_moved_to(self):
        from sitebuild import beforeafter

        # from -4 to -2 the result went up, though the ratio is below 1
        self.assertIn("is-above", beforeafter.cell((-4.0, -2.0), True))
        self.assertIn("is-below", beforeafter.cell((-2.0, -4.0), True))
        self.assertIn("is-below", beforeafter.cell((4.0, 2.0), True))
        # a value that moved by less than its digits show is not printed as "no change"
        moved = beforeafter.cell((1.0, 1.0), True)
        self.assertIn('is-slight" title="Moved by less than the digits written here show">≈ 1<', moved)
        self.assertEqual(beforeafter.ratio_text(1.0000004), "1.0000004")
        self.assertIn("is-same", beforeafter.cell((1.0, 1.0), False))


if __name__ == "__main__":
    unittest.main()
