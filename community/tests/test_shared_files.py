"""Sharing files with the sibling repositories: one list here, copies there, and a check.

`site/shared-sets.json` names what this repository shares, in sets. Another repository takes
a set with `scripts/shared_files.py take` and checks its copies with `check`. What the tests
hold:

- a set brings the sets it includes, and nothing else;
- a copy that was edited, a file added by hand to a shared folder, and a file that is gone
  are each found;
- taking a newer commit brings the change, and removes a file that is shared no more;
- the comparison of results (the set `before-after`) works in a repository that took it
  alone, without the rest of the site.
"""

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import shared_files  # noqa: E402

SETS = json.loads((ROOT / shared_files.SETS).read_text())["sets"]


def git(folder, *arguments):
    done = subprocess.run(["git", "-C", str(folder), "-c", "user.name=t", "-c", "user.email=t@example.org",
                           "-c", "commit.gpgsign=false", *arguments], capture_output=True, text=True, check=False)
    assert done.returncode == 0, done.stderr
    return done.stdout.strip()


def a_source(folder):
    """A source repository: the shared files of this one, committed."""
    folder.mkdir(parents=True)
    files, folders = shared_files.expand(SETS, list(SETS))
    for name in sorted(files) + [shared_files.SETS]:
        (folder / name).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(ROOT / name, folder / name)
    for name in folders:
        shutil.copytree(ROOT / name, folder / name, ignore=shutil.ignore_patterns("__pycache__"), dirs_exist_ok=True)
    git(folder, "init", "-q")
    git(folder, "add", "-A")
    git(folder, "commit", "-q", "-m", "shared files")
    return git(folder, "rev-parse", "HEAD")


class SetsTests(unittest.TestCase):
    def test_a_set_brings_the_sets_it_includes(self):
        files, folders = shared_files.expand(SETS, ["before-after"])
        self.assertIn("scripts/sitebuild/beforeafter.py", files)
        self.assertEqual(folders, {"scripts/runrecord"}, "the formats come with the page that shows them")
        self.assertNotIn("scripts/build_site.py", files)
        everything, _ = shared_files.expand(SETS, ["site"])
        self.assertLess(files, everything | {"docs/before-after.md"})
        self.assertIn("scripts/shared_files.py", everything, "who takes the site can take it again")
        with self.assertRaisesRegex(ValueError, "shares no set 'dashboards'"):
            shared_files.expand(SETS, ["dashboards"])

    def test_this_repository_is_the_source_and_every_file_it_names_is_here(self):
        self.assertEqual(shared_files.source_problems(ROOT), [])
        self.assertFalse((ROOT / shared_files.MANIFEST).exists(), "the source takes its files from nowhere")


class TakingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.source, self.other = Path(self.temp.name) / "source", Path(self.temp.name) / "other"
        self.commit = a_source(self.source)
        self.other.mkdir()

    def tearDown(self):
        self.temp.cleanup()

    def test_a_repository_takes_one_set_and_its_check_passes(self):
        full, count, names = shared_files.take(self.source, self.commit, self.other, ["before-after", "sharing"])
        manifest = shared_files.read_manifest(self.other)
        self.assertEqual((full, names), (self.commit, ["before-after", "sharing"]))
        self.assertEqual((manifest["commit"], manifest["sets"]), (self.commit, ["before-after", "sharing"]))
        self.assertEqual(len(manifest["files"]), count)
        self.assertTrue((self.other / "scripts/sitebuild/beforeafter.py").is_file())
        self.assertTrue((self.other / "scripts/shared_files.py").is_file())
        self.assertFalse((self.other / "scripts/build_site.py").exists(), "the site was not asked for")
        self.assertFalse((self.other / "scripts/sitebuild/lastrun.py").exists(), "a single file of a folder is not the folder")
        self.assertEqual(shared_files.problems(self.other), [])

    def test_an_edited_copy_a_file_added_by_hand_and_a_missing_file_are_found(self):
        shared_files.take(self.source, self.commit, self.other, ["before-after"])
        (self.other / "site/assets/before-after.js").write_text("// improved here\n")
        (self.other / "scripts/runrecord/mine.py").write_text("# a file of this repository's own\n")
        (self.other / "docs/before-after.md").unlink()
        found = shared_files.problems(self.other)
        self.assertEqual(len(found), 3)
        self.assertIn(f"site/assets/before-after.js: differs from the file of commit {self.commit[:7]}", found)
        self.assertIn("scripts/runrecord/mine.py: not a shared file, in a shared folder", found)
        self.assertIn("docs/before-after.md: missing", found)

    def test_a_newer_commit_brings_the_change_and_removes_what_is_shared_no_more(self):
        shared_files.take(self.source, self.commit, self.other, ["before-after"])
        # the source improves the page's script, and stops sharing the styles as a file
        (self.source / "site/assets/before-after.js").write_text("// better for everybody\n")
        sets = json.loads((self.source / shared_files.SETS).read_text())
        sets["sets"]["before-after"]["files"].remove("site/assets/before-after.css")
        (self.source / shared_files.SETS).write_text(json.dumps(sets))
        git(self.source, "commit", "-q", "-am", "improve")
        newer = git(self.source, "rev-parse", "HEAD")
        full, _, names = shared_files.take(self.source, newer, self.other)  # the sets taken before
        self.assertEqual((full, names), (newer, ["before-after"]))
        self.assertEqual((self.other / "site/assets/before-after.js").read_text(), "// better for everybody\n")
        self.assertFalse((self.other / "site/assets/before-after.css").exists())
        self.assertEqual(shared_files.problems(self.other), [])

    def test_a_repository_that_took_the_site_before_sets_had_names_takes_the_site_again(self):
        (self.other / "site").mkdir()
        (self.other / shared_files.MANIFEST).write_text(json.dumps(
            {"note": "its own words", "repository": "https://example.org/source", "commit": "0" * 40,
             "folders": ["schema"], "files": {"scripts/gone.py": "0" * 64}}))
        (self.other / "scripts").mkdir()
        (self.other / "scripts/gone.py").write_text("# shared once\n")
        _, _, names = shared_files.take(self.source, self.commit, self.other)
        manifest = shared_files.read_manifest(self.other)
        self.assertEqual(names, ["site"])
        self.assertEqual((manifest["note"], manifest["repository"]), ("its own words", "https://example.org/source"))
        self.assertTrue((self.other / "scripts/build_site.py").is_file())
        self.assertFalse((self.other / "scripts/gone.py").exists())
        self.assertEqual(shared_files.problems(self.other), [])

    def test_the_comparison_works_where_it_was_taken_alone(self):
        """A repository with a site of its own takes the set `before-after` and nothing else:
        it writes a comparison, checks it and gets the page without a frame."""
        shared_files.take(self.source, self.commit, self.other, ["before-after"])
        code = (
            "import sys; sys.path.insert(0, 'scripts')\n"
            "from runrecord import before_after as ba\n"
            "from sitebuild import beforeafter\n"
            "counts = ba.tally([(1.0, 1.0), (2.0, 1.0)], 1e-6, bands=True)\n"
            "data = ba.account('Published and rebuilt', ('Published', None), ('Rebuilt', None),\n"
            "    ('product', 'products', 2, 1), [ba.indicator('x:climate', 'Climate change', counts)],\n"
            "    bands=ba.BANDS, threshold=1e-6, moved=[ba.item('p', 'Wheat', {'x:climate': (2.0, 1.0)})])\n"
            "page = beforeafter.body(data, up='../')\n"
            "assert '<h1>Published and rebuilt</h1>' in page and '>0.5</td>' in page, page[:300]\n"
            "assert '<script src=\"../assets/before-after.js\" defer>' in page\n"
            "print(sorted(m for m in sys.modules if m.startswith(('sitebuild', 'runrecord'))))\n"
        )
        done = subprocess.run([sys.executable, "-I", "-c", code], cwd=self.other, capture_output=True, text=True, check=False)
        self.assertEqual(done.returncode, 0, done.stderr)
        # nothing of the rest of the site was needed
        self.assertEqual(
            done.stdout.strip(),
            "['runrecord', 'runrecord.before_after', 'runrecord.summary', 'sitebuild', 'sitebuild.beforeafter', 'sitebuild.text']",
        )


if __name__ == "__main__":
    unittest.main()
