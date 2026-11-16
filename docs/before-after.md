# Before and after: comparing two sets of results

This page is the same file in every Sentier dataset repository that uses the comparison. It
says how to read a comparison, how it is counted, what the file holds and how a repository
writes and shows one.

A comparison answers one question: **what did a change to the data do to the results?** The
same items are calculated twice, in the same indicators, and the two sets of results are
set side by side. The two sides can be:

- a provider's data and a patched copy of it;
- published results and a rebuild of them;
- one database built in two ways.

## How to read one

| What you see | What it means |
|---|---|
| **After ÷ before** | The result after, divided by the result before. 1 is no change, 0.5 is half, 2 is double. |
| **Colour of a cell** | How far the ratio lies from 1, and on which side. A stronger colour is further away. |
| **Moved** | The two results of an item differ by more than the threshold, relative to the larger of the two. A smaller difference is the noise of two separate calculations. |
| **Near zero** | Both results are too small to say anything about their ratio. Such an item counts as not moved. |
| **Zero or other sign** | One result is zero, or the two have different signs. There is no ratio. The item still counts as moved. |
| **Cause** | A step that was taken on the way from one side to the other, such as a patch or a link. Each moved result names the causes that explain it. |
| **Not explained** | A moved result that no cause explains. A run that requires every difference to be explained fails on one. |

The page judges nothing. Whether a change is a correction is said where the change was
decided, not on the page that measures it.

## How it is counted

Every run counts with the same functions, in `scripts/runrecord/before_after.py`, so that
two repositories mean the same by the same word.

- `ratio(before, after)` is `after / before`, or nothing where one side is zero or the signs differ.
- `moved(before, after, threshold, floor)` is true where the two differ by more than `threshold` of the larger.
- `floor_of(values)` is the size below which a result is near zero: 1 % of the median size of the results before.
- `band(before, after, floor)` puts a pair into one of eleven bands.
- `tally(pairs, threshold)` counts one indicator: compared, moved, higher, lower, and the number in each band.

The bands lie equally far from 1 on both sides:

| Below 1 | Around 1 | Above 1 | No ratio |
|---|---|---|---|
| below 0.1 | 0.91 to 1.1 | 1.1 to 1.25 | near zero |
| 0.1 to 0.5 | | 1.25 to 2 | opposite sign or zero |
| 0.5 to 0.8 | | 2 to 10 | |
| 0.8 to 0.91 | | above 10 | |

A run chooses its threshold and its floor and the file says the threshold. A run that
compares two builds of the same data sets no floor, because every difference counts there. A
run that compares with published results uses the floor, because rounding dominates near
zero.

## The file

A run writes `before-after.json` beside its own account. The format is
`sentier/before-after/1`. The module's own text describes every key; in short:

| Part | What it holds |
|---|---|
| `title`, `before`, `after` | What is compared, and a sentence about each side. |
| `items` | What an item is called, how many were compared, how many moved in any indicator. |
| `indicators` | Per indicator: compared, moved, higher, lower, not explained, the count per band, and a reason where one is known for the whole indicator. |
| `causes` | Each step that changed the data: how many rows it changed and of what kind, how many items, and how many items it moved. |
| `rows` | The rows of the data that were compared, that differ, and that nothing explains. |
| `moved` | Items that moved, each with its two results per indicator and its causes. |
| `moved_not_listed` | Items that moved and are not listed. |
| `notes` | Sentences for below the comparison. |

**The list of moved items holds results of single items.** A repository lists only as many as
its data's terms allow it to show, and says how many it left out. A comparison may hold
counts only: `moved` is then empty, and the page shows the indicators and the causes.

A file read from a run is data. The check refuses a key the format does not know, a number
that is not finite, a result of an indicator the file does not hold, and a text that is too
long. A page shows nothing the check did not pass.

## Writing one

```python
from runrecord import before_after

counts = before_after.tally(pairs, threshold=1e-6, bands=True)
data = before_after.account(
    "The export and the linked copy",
    ("The export", "As it is shipped."),
    ("The linked copy", None),
    ("product", "products", compared, moved_in_any),
    [before_after.indicator("x:climate", "Climate change", counts, unit="kg CO2 eq")],
    step="comparison",  # the step of the run it belongs to
    threshold=1e-6,
    bands=before_after.BANDS,
    causes=[before_after.cause("link-1", kind="link", rows=4, items=2, moved=2)],
    moved=[before_after.item("p-1", "Wheat", {"x:climate": (2.0, 1.0)}, causes=["link-1"])],
)
before_after.write(data, folder / before_after.FILE)
```

`account` and `write` raise an error for a comparison a page could not show.

## Showing one

**On a site that the shared build writes.** The run keeps `before-after.json` in the same
artifact as `run.json` and `transcript.json`. The build then writes the page
`before-after.html`, and the step of the walk through the run that the file names gets a
button that leads to it. The page is in no navigation; it leads back to its step. The same
comparison is a file of the site, `api/v1/before-after.json`. Where the record also holds the
last run that was made for a tag, that run's comparison is `tag-before-after.html`. A run that
did not happen on a public runner brings its file with
`scripts/last_run.py --local ... --before-after before-after.json`.

**On a site whose frame is its own.** `scripts/sitebuild/beforeafter.py` has `body(data)`: the
page without a frame, as markup. Put it into the site's own frame and load
`assets/before-after.css` and `assets/before-after.js` with it. The styles are written with the
tokens of the shared stylesheet (`--index`, `--surface`, `--line`, `--wait`, `--fail`, the sizes
and the spaces); a site that defines those tokens needs nothing else. `said` is how a text of
the file is shown: pass a function of the site's own to link its records.

Without the script the page is still a page to read: the counts, the causes, each indicator,
the first hundred rows of ratios and the results of the twenty items that moved furthest.
The script sorts by any indicator, filters by name, cause and group, and shows the results
of any listed item.

## What is not in it yet

- **Why one item differs, by flow and by process.** A breakdown of a single item is a file
  per item that the page would load when the item is opened. The format has no place for it
  yet.
- **Variants of one comparison** (the same pair calculated under two rules). Today each
  variant is a file of its own.
- **A reason for a single item**, beyond the item's `note`.
