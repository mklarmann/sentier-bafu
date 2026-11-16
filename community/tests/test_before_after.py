"""What a run compared, before and after: the file, how it reaches a site, and its page.

A run that changes data may say what the change did to the results (`before-after.json`,
`scripts/runrecord/before_after.py`). The file travels with the run like its transcript, and a
site gives it a page of its own that the walk through the run leads to. What the tests hold:

- every run counts alike: what moved, in which direction, and in which band;
- the file is data: a key the format does not know, a number that is not finite or a result
  of something the file does not hold is refused, and a run is shown without such a file;
- the page states nothing the file does not hold, and it is in no navigation;
- a sibling site gets all of it from the shared files alone, in its own words.
"""

import copy
import html
import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import last_run  # noqa: E402
from runrecord import before_after  # noqa: E402
from test_last_run import (  # noqa: E402
    OTHER_LINES, OTHER_RUN, REPOSITORY, GitHubAnswers, a_run, a_transcript, an_archive, another_account,
)
from test_sibling_site import build_site, sibling  # noqa: E402

CLIMATE, WATER = "x:climate", "x:water"


def a_comparison(**changes):
    """What a run of another dataset compared: two products moved, one of them in one indicator
    only, and a third cause that changed rows and moved nothing."""
    pairs = {
        CLIMATE: [(1.0, 1.0)] * 7 + [(2.0, 1.0), (4.0, 6.0), (0.0, 0.0)],
        WATER: [(1.0, 1.0)] * 9 + [(3.0, -3.0)],
    }
    indicators = [
        before_after.indicator(CLIMATE, "Climate change", before_after.tally(pairs[CLIMATE], 1e-6, bands=True),
                               short="Climate", unit="kg CO2 eq", unexplained=0),
        before_after.indicator(WATER, "Water use", before_after.tally(pairs[WATER], 1e-6, bands=True),
                               unit="m3", unexplained=1, reason="One factor is known to differ, see F2."),
    ]
    data = before_after.account(
        "The export and the linked copy",
        ("The export", "As it is shipped."),
        ("The linked copy", None),
        ("product", "products", 10, 3),
        indicators,
        step="export as shipped",
        indicator={"one": "indicator", "many": "indicators"},
        threshold=1e-6,
        bands=before_after.BANDS,
        groups={"farm": "at the farm gate"},
        causes=[
            before_after.cause("link-1", kind="link", title="Wheat takes the supplier of F2.", rows=4,
                               changed={"supplier": 4}, items=2, moved=2),
            before_after.cause("rename-7", kind="correction", rows=12, changed={"name": 12}, items=9, moved=0),
        ],
        rows={"one": "row", "many": "rows", "compared": 500, "differ": 16, "unexplained": 0},
        moved=[
            before_after.item("p-1", "Wheat <grain>", {CLIMATE: (2.0, 1.0), WATER: (1.0, 1.0)}, place="FR",
                              group="farm", causes=["link-1"]),
            before_after.item("p-2", "Barley", {CLIMATE: (4.0, 6.0), WATER: (3.0, -3.0)}, causes=["link-1"]),
        ],
        moved_not_listed=1,
        notes=["Nine products were renamed and none of them moved."],
    )
    return data | changes


class CountingTests(unittest.TestCase):
    def test_every_run_counts_alike(self):
        counted = before_after.tally([(1.0, 1.0), (1.0, 1.0 + 5e-7), (2.0, 1.0), (1.0, 3.0), (1.0, -1.0), (None, 2.0)],
                                     1e-6, bands=True)
        # a difference below the threshold is no move; a missing side is not compared
        self.assertEqual({k: counted[k] for k in ("compared", "moved", "higher", "lower")},
                         {"compared": 5, "moved": 3, "higher": 1, "lower": 2})
        by_band = dict(zip(before_after.BANDS, counted["bands"]))
        self.assertEqual(sum(counted["bands"]), counted["compared"], "every compared pair lies in one band")
        self.assertEqual(by_band["0.91 to 1.1"], 2)
        self.assertEqual((by_band["0.5 to 0.8"], by_band["2 to 10"], by_band["opposite sign or zero"]), (1, 1, 1))

    def test_near_zero_nothing_moves_and_nothing_has_a_ratio(self):
        # the floor is taken from the results before: 1 % of their median size
        pairs = [(100.0, 100.0), (100.0, 100.0), (100.0, 110.0), (1e-9, 5e-9)]
        counted = before_after.tally(pairs, 1e-6, bands=True)
        self.assertEqual(counted["moved"], 1, "a fivefold change far below the floor is not a move")
        self.assertEqual(dict(zip(before_after.BANDS, counted["bands"]))["near zero"], 1)
        # without a floor the same pair moves: the run chooses, and says so with its threshold
        self.assertEqual(before_after.tally(pairs, 1e-6, floor=0.0)["moved"], 2)

    def test_the_bands_lie_as_far_from_one_on_both_sides(self):
        for low, high in ((0.05, 20.0), (0.3, 1 / 0.3), (0.6, 1 / 0.6), (0.85, 1 / 0.85), (0.95, 1 / 0.95)):
            below = before_after.BANDS.index(before_after.band(1.0, low))
            above = before_after.BANDS.index(before_after.band(1.0, high))
            self.assertEqual(below + above, 8, f"{low} and {high} are mirror images")


class ShapeTests(unittest.TestCase):
    def test_a_comparison_a_run_wrote_is_one_a_page_can_show(self):
        self.assertEqual(before_after.shape_errors(a_comparison()), [])
        # and it need not hold more than its counts
        slim = a_comparison(moved=[], causes=[], rows=None, notes=[], groups={}, bands=[])
        for indicator in slim["indicators"]:
            indicator["bands"] = None
        self.assertEqual(before_after.shape_errors(slim), [])

    def test_what_the_format_does_not_describe_is_refused(self):
        def broken(change):
            data = copy.deepcopy(a_comparison())
            change(data)
            return " ".join(before_after.shape_errors(data))

        self.assertIn("does not know: scores", broken(lambda d: d.update(scores=[1])))
        self.assertIn("not a short text", broken(lambda d: d.update(title="x" * 500)))
        self.assertIn("not [before, after]", broken(lambda d: d["moved"][0]["values"].update({CLIMATE: [1.0, float("nan")]})))
        self.assertIn("not [before, after]", broken(lambda d: d["moved"][0]["values"].update({CLIMATE: [1.0, "2"]})))
        self.assertIn("an indicator the file does not hold", broken(lambda d: d["moved"][0]["values"].update({"x:other": [1, 2]})))
        self.assertIn("a cause the file does not hold", broken(lambda d: d["moved"][0].update(causes=["somebody"])))
        self.assertIn("not one of `groups`", broken(lambda d: d["moved"][0].update(group="shop")))
        self.assertIn("one count for each band", broken(lambda d: d["indicators"][0].update(bands=[1, 2])))
        self.assertIn("not a count", broken(lambda d: d["indicators"][0].update(moved=-1)))
        self.assertIn("same id", broken(lambda d: d["indicators"].append(dict(d["indicators"][0]))))
        self.assertIn("at most", broken(lambda d: d.update(moved=d["moved"] * (before_after.MAX_MOVED // 2 + 1))))
        self.assertIn("control", "control" if broken(lambda d: d["notes"].append("a\x07b")) else "")
        self.assertEqual(before_after.shape_errors({"format": "sentier/run/1"}), [f"not a comparison of format {before_after.FORMAT}"])

    def test_a_file_is_written_only_when_a_page_could_show_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            place = Path(tmp) / "kept" / before_after.FILE
            before_after.write(a_comparison(), place)
            self.assertEqual(json.loads(place.read_text()), a_comparison())
            with self.assertRaisesRegex(ValueError, "not a comparison"):
                before_after.write(a_comparison(title=""), Path(tmp) / "other.json")
            self.assertFalse((Path(tmp) / "other.json").exists())


def a_record(**files):
    answers = GitHubAnswers([a_run(3)], artifacts=[{"id": 7, "name": "link-results", "expired": False, "size_in_bytes": 400}])
    kept = {"run.json": another_account(), "transcript.json": a_transcript(OTHER_LINES, exit_code=0)} | files
    archive = an_archive(**kept)
    return last_run.fetch(REPOSITORY, OTHER_RUN, "a-token", transport=answers, fetch=lambda url: archive)


class RecordTests(unittest.TestCase):
    def test_a_run_that_compared_carries_the_comparison_and_one_that_did_not_carries_none(self):
        record = a_record(**{before_after.FILE: a_comparison()})
        self.assertEqual(last_run.shape_errors(record), [])
        self.assertEqual(record["before_after"], a_comparison())
        plain = a_record()
        self.assertEqual(last_run.shape_errors(plain), [])
        self.assertIsNone(plain["before_after"])
        self.assertEqual(plain["kept"], "read")
        # the build log says what was read of each
        self.assertIn("(its own account, transcript and what it compared)", last_run.said(record))
        self.assertIn("(its own account and transcript)", last_run.said(plain))

    def test_a_comparison_of_another_shape_is_left_out_and_the_run_is_still_shown(self):
        record = a_record(**{before_after.FILE: a_comparison(scores=[1, 2, 3])})
        self.assertIsNone(record["before_after"])
        self.assertIn("before-after.json: a key this format does not know: scores", record["kept_note"])
        self.assertEqual(record["kept"], "read")
        self.assertIsNotNone(record["summary"])
        # a record from a file is checked the same way
        record["before_after"] = a_comparison(title="")
        self.assertTrue(any("before-after.json" in error for error in last_run.shape_errors(record)))

    def test_a_run_that_was_not_on_github_brings_its_comparison_too(self):
        lines = a_transcript(OTHER_LINES, exit_code=0)
        record = last_run.local(another_account(), lines, run=OTHER_RUN, compared=a_comparison())
        self.assertEqual(last_run.shape_errors(record), [])
        self.assertEqual(record["before_after"]["title"], "The export and the linked copy")
        with self.assertRaisesRegex(ValueError, "short text"):
            last_run.local(another_account(), lines, run=OTHER_RUN, compared=a_comparison(title=""))


@unittest.skipIf(build_site is None, "the site build needs the markdown package")
class PageTests(unittest.TestCase):
    """A sibling site, made of the shared files alone, with a run that compared."""

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
        for name, data in (("run.json", another_account()), ("transcript.json", a_transcript(OTHER_LINES, exit_code=0)),
                           (before_after.FILE, a_comparison())):
            (cls.kept / name).write_text(json.dumps(data))
        cls.out = cls.site("with", "--before-after", str(cls.kept / before_after.FILE))
        cls.page = (cls.out / "before-after.html").read_text()
        cls.text = " ".join(html.unescape(re.sub(r"<script.*?</script>|<[^>]+>", " ", cls.page, flags=re.S)).split())

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    @classmethod
    def run_in(cls, *arguments):
        return subprocess.run([sys.executable, *arguments], cwd=cls.root, capture_output=True, text=True, check=False)

    @classmethod
    def site(cls, name, *more):
        record, out = cls.kept / f"{name}.json", Path(cls.temp.name) / f"site-{name}"
        made = cls.run_in("-I", "scripts/last_run.py", "--local", "--summary", str(cls.kept / "run.json"),
                          "--transcript", str(cls.kept / "transcript.json"), *more, "--out", str(record))
        assert made.returncode == 0, made.stdout + made.stderr
        built = cls.run_in("scripts/build_site.py", "--offline", "--last-run", str(record), "--out", str(out))
        assert built.returncode == 0, built.stdout + built.stderr
        return out

    def test_the_site_passes_its_check_and_holds_the_comparison_as_a_file(self):
        self.assertEqual(self.run_in("scripts/check_site.py", str(self.out)).returncode, 0)
        self.assertEqual(json.loads((self.out / "api/v1/before-after.json").read_text()), a_comparison())
        self.assertTrue((self.out / "assets/before-after.js").is_file())

    def test_the_step_of_the_walk_leads_to_the_page_and_the_page_leads_back(self):
        walk = (self.out / "run.html").read_text()
        first, second = walk.split('id="run-step-2"')
        self.assertIn('<a class="button" href="before-after.html">What changed, product by product</a>', first)
        self.assertIn("3 products moved", first)
        self.assertNotIn("before-after.html", second.split("</article>")[0], "the link stands in its own step only")
        self.assertIn('<p class="crumb"><a href="run.html#run-step-1">Step 1 of the linking run</a></p>', self.page)

    def test_the_page_is_in_no_navigation(self):
        for name in ("index.html", "findings.html", "run.html", "before-after.html"):
            page = (self.out / name).read_text()
            for part in re.findall(r'<nav class="(?:nav|footer-links)".*?</nav>', page, flags=re.S):
                self.assertNotIn("before-after", part, name)
        # and it marks the page it belongs to as the current one
        self.assertIn('<a href="run.html" aria-current="page">The run</a>', self.page)

    def test_every_number_on_the_page_is_the_files(self):
        for value, label in ((10, "products compared"), (3, "products moved"), (2, "indicators"), (500, "rows compared"),
                             (16, "differ"), (0, "not explained")):
            self.assertIn(f"<div><dt>{label}</dt><dd>{value}</dd></div>", self.page)
        self.assertIn("The export and the linked copy", self.text)
        self.assertIn("As it is shipped.", self.text)
        # a cause with what it changed; one that moved nothing is listed too
        self.assertRegex(self.page, r'<code>link-1</code>.*?<td class="num">4</td><td>4 × supplier</td><td class="num">2</td><td class="num">2</td>')
        self.assertRegex(self.page, r'<code>rename-7</code>.*?<td class="num">12</td><td>12 × name</td><td class="num">9</td><td class="num">0</td>')
        # per indicator: compared, moved, lower, higher, not explained; and the known reason, with its finding linked
        self.assertRegex(self.page, r'Climate change <span class="quiet">kg CO2 eq</span></th><td class="num">10</td><td class="num"><strong>2</strong></td><td class="num">1</td><td class="num">1</td><td class="num">0</td>')
        self.assertIn('One factor is known to differ, see <a href="findings/F2.html">F2</a>.', self.page)
        self.assertIn("1 more moved.", self.text)
        self.assertIn("Nine products were renamed and none of them moved.", self.text)

    def test_a_cell_is_after_over_before_and_says_what_has_no_ratio(self):
        rows = re.findall(r'<tr data-i="\d+">(.*?)</tr>', self.page, flags=re.S)
        self.assertEqual(len(rows), 2)
        wheat, barley = rows
        self.assertIn("Wheat &lt;grain&gt;", wheat, "a name is text")
        self.assertRegex(wheat, r'is-below" style="--d:[0-9.]+">0\.5</td><td class="num ba-cell is-same" title="No change">1</td>')
        self.assertRegex(barley, r'is-above" style="--d:[0-9.]+">1\.5</td><td class="num ba-cell is-opposite"')
        # the results themselves, for a reader without the script
        self.assertRegex(self.page, r'<details class="ba-item"><summary>Barley</summary>.*?<td class="num">4</td><td class="num">6</td><td class="num">\+50 %</td>')
        # and as data for the script, which a name cannot break out of
        payload = re.search(r'<script type="application/json" data-ba-data>(.*?)</script>', self.page, flags=re.S).group(1)
        self.assertEqual(json.loads(payload)["moved"][0]["name"], "Wheat <grain>")
        self.assertNotIn("</", payload)

    def test_the_page_speaks_the_sites_own_words(self):
        for word in ("BAFU", "bafu", "dataset", "Brightway", "patch", "impact categor"):
            self.assertNotIn(word, self.text, word)
        self.assertIn("Per indicator", self.text)

    def test_a_run_that_compared_nothing_has_no_page_and_no_link(self):
        out = self.site("without")
        self.assertFalse((out / "before-after.html").exists())
        self.assertFalse((out / "api/v1/before-after.json").exists())
        self.assertNotIn("before-after", (out / "run.html").read_text())
        self.assertEqual(self.run_in("scripts/check_site.py", str(out)).returncode, 0)

    def test_a_comparison_in_which_nothing_moved_says_so(self):
        still = a_comparison(moved=[], moved_not_listed=0, causes=[])
        still["items"]["moved"] = 0
        (self.kept / "still.json").write_text(json.dumps(still))
        out = self.site("still", "--before-after", str(self.kept / "still.json"))
        self.assertIn("No product moved.", (out / "before-after.html").read_text())
        self.assertIn("no product moved", (out / "run.html").read_text())


if __name__ == "__main__":
    unittest.main()
