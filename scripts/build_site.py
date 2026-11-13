"""Build the public site from the records and an explicit, inventory-free file list.

Run: uv run --no-project --with markdown==3.7 scripts/build_site.py

The site has a page per finding and per contribution, so it holds thousands of them. Issue
details (comment counts, labels) come from GitHub when it can be reached; see triage.py.
"""

import argparse
import datetime
import html
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import markdown

sys.path.insert(0, str(Path(__file__).resolve().parent))
import community  # noqa: E402
import triage  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
RECORD_PAGES = {"community/findings": "findings", "community/contributions": "contributions"}


def esc(value):
    return html.escape(str(value), quote=True)


def plural(n, word):
    return f"{n} {word}{'' if n == 1 else 's'}"


def revision():
    try:
        return subprocess.run(
            ["git", "-C", str(ROOT), "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
    except Exception:
        return None


class Site:
    def __init__(self, out, source_repository=None, source_ref=None, preview_url=None,
                 issues_snapshot=None, offline=False, require_issues=False):
        self.out = Path(out)
        self.config = json.loads((ROOT / "site/config.json").read_text())
        self.repo = self.config["repository"]
        self.source_repo = source_repository or self.repo
        self.ref = source_ref or self.config["source_ref"]
        if preview_url and not preview_url.startswith("https://github.com/"):
            raise ValueError("Preview notice must link to a GitHub pull request")
        self.preview_url = preview_url
        self.dataset = self.config["dataset"]
        self.provider = self.config["provider"]
        self.docs = self.config["documents"]
        self.routes = {d["source"]: d["page"] for d in self.docs}
        self.routes["community/findings.md"] = "findings.html"  # the generated ledger
        self.findings = community.load_findings(ROOT)
        self.contributions = sorted(
            (json.loads(p.read_text()) for p in (ROOT / "community/contributions").glob("C*.json")),
            key=lambda c: int(re.sub(r"\D", "", c["id"]) or 0),
        )
        issues, self.issues_source = triage.load_issues(
            self.repo, issues_snapshot, offline, require_issues
        )
        self.triage = triage.assemble(self.findings, self.repo, issues)
        self.built = datetime.date.today().isoformat()
        self.revision = revision()

    # ------------------------------------------------------------------ helpers

    def named(self, text):
        return esc(text).replace("the provider", esc(self.provider))

    def target(self, link, source):
        """Where a relative link in a source file points on the site (or on GitHub)."""
        path, sep, fragment = link.partition("#")
        absolute = (ROOT / Path(source).parent / path).resolve()
        try:
            relative = absolute.relative_to(ROOT).as_posix()
        except ValueError:
            raise ValueError(f"Link leaves repository: {link}") from None
        page = self.routes.get(relative)
        folder = RECORD_PAGES.get(str(Path(relative).parent))
        if not page and folder and relative.endswith(".json"):
            page = f"{folder}/{Path(relative).stem}.html"
        if not page and relative in RECORD_PAGES:
            page = f"{RECORD_PAGES[relative]}.html"
        if page:
            return page + (sep + fragment if sep else ""), True
        return f"{self.source_repo}/blob/{self.ref}/{relative}" + (sep + fragment if sep else ""), False

    def render(self, text, source, depth=0, inline=False):
        """Markdown to HTML, with relative links resolved against the source file."""
        rendered = markdown.markdown(text, extensions=["tables", "fenced_code", "sane_lists", "toc"])

        def rewrite(match):
            link = html.unescape(match.group(1))
            if re.match(r"^(https?:|mailto:|#)", link):
                return match.group(0)
            url, local = self.target(link, source)
            return f'href="{esc(("../" * depth if local else "") + url)}"'

        rendered = re.sub(r'href="([^"]+)"', rewrite, rendered)
        rendered = rendered.replace("<table>", '<div class="table-scroll"><table>').replace(
            "</table>", "</table></div>"
        )
        if inline:
            rendered = re.sub(r"^<p>|</p>$", "", rendered.strip())
        return rendered

    def issue_link(self, issue, number):
        if not issue:
            return f'<a href="{self.repo}/issues/{number}">#{number} ↗</a>' if number else ""
        return (
            f'<a href="{esc(issue["url"])}">#{issue["number"]} ↗</a> '
            f'<small>{plural(issue["comments"], "comment")} · updated {esc(issue["updated"])}'
            f'{" · closed" if issue["state"] == "closed" else ""}</small>'
        )

    def shell(self, title, body, current, depth=0, wide=False):
        up = "../" * depth
        nav = "".join(
            f'<a href="{up}{page}"' + (' aria-current="page"' if page == current else "") + f">{label}</a>"
            for page, label in self.config["nav"]
        )
        notice = (
            '<aside class="preview-notice" aria-label="Review preview"><div class="wrap">'
            "<strong>Review preview.</strong> These changes are proposed for the shared repository. "
            f'<a href="{esc(self.preview_url)}">Review the pull request ↗</a></div></aside>'
            if self.preview_url
            else ""
        )
        snapshot = f"Built {self.built}" + (f" from {esc(self.revision)}" if self.revision else "")
        if self.issues_source:
            snapshot += "; discussions read from GitHub at build time"
        c = self.config
        main = body if wide else f'<div class="wrap page"><article class="article">{body}</article></div>'
        return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{esc(title)} · {esc(self.dataset)} · Sentier</title><meta name="description" content="{esc(c["description"])}"><meta name="theme-color" content="#3c5343"><link rel="icon" href="{up}assets/favicon-32x32.png" type="image/png"><link rel="stylesheet" href="{up}style.css"></head><body>
<a class="skip" href="#main">Skip to content</a><header class="masthead"><div class="wrap top"><div class="brand"><a class="brand-logo" href="https://www.d-d-s.ch/" aria-label="Départ de Sentier"><img src="{up}assets/dds-logo.svg" alt="Départ de Sentier" width="200" height="94"></a><a class="dataset" href="{up}index.html" aria-label="{esc(self.dataset)} home">{esc(self.dataset)}</a></div><div class="top-links"><a href="{esc(c["sibling_url"])}">{esc(c["sibling_name"])} ↗</a><a href="{self.repo}">Repository ↗</a></div></div><nav class="wrap nav" aria-label="Main navigation">{nav}</nav></header>
{notice}<main id="main">{main}</main>
<footer><div class="wrap"><p><strong>A Sentier community workspace.</strong><br>Findings and contributions concern {esc(self.provider)}'s dataset. {esc(self.provider)}'s endorsement is not implied.<small class="brand-credit">{snapshot}. <a href="https://github.com/Depart-de-Sentier/dds-logo">Logo</a> by <a href="https://proov.fr/">Sylvain Prevost</a> · <a href="https://www.d-d-s.ch/">Départ de Sentier</a></small></p><p><a href="{up}terms.html">Data and terms</a><br><a href="{up}contribute.html">Take part</a><br><a href="{self.repo}/issues/new/choose">Open an issue ↗</a></p></div></footer></body></html>'''

    def write(self, page, html_text):
        path = self.out / page
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(html_text)
        self.written.add(path)

    # ------------------------------------------------------------------ findings

    def stage_tiles(self, link_prefix=""):
        counts = self.triage["counts"]
        return '<div class="stages">' + "".join(
            f'<a class="stage" id="stage-{key}" href="{link_prefix}#stage-{key}" data-filter="{key}">'
            f"<strong>{counts[key]}</strong>{self.named(title)}</a>"
            for key, title, _ in triage.STAGES
            if counts.get(key)
        ) + "</div>"

    def findings_list(self):
        rows = ""
        for f in self.triage["findings"]:
            text = " ".join([f["id"], f["title"], f["datasets"], f["release"], f["status"]]).lower()
            rows += (
                f'<tr id="{f["id"]}" data-stage="{f["stage"]}" data-text="{esc(text)}">'
                f'<td class="id"><a href="findings/{f["id"]}.html">{f["id"]}</a></td>'
                f'<td><a class="title" href="findings/{f["id"]}.html">{esc(f["title"])}</a>'
                f'<small>{self.render(f["datasets"], "community/findings.md", inline=True)} · {esc(f["release"])}</small></td>'
                f'<td><span class="badge status-{esc(f["status"])}">{esc(f["status"])}</span>'
                + ('<br><small>awaiting a second measurement</small>' if f["stage"] == "needs-triage" else "")
                + f'</td><td class="thread">{self.issue_link(f["issue"], f["issue_number"]) or "<small>external thread</small>"}</td></tr>'
            )
        options = "".join(
            f'<option value="{key}">{self.named(title)}</option>'
            for key, title, _ in triage.STAGES
            if self.triage["counts"].get(key)
        )
        unlisted = ""
        if self.triage["unlisted"]:
            # Number and link only: an issue's title is not reviewed text.
            unlisted = (
                '<h2 id="unlisted">Filed, awaiting a record</h2>'
                "<p>Issues filed as findings that have no record yet.</p><ul class=\"plain\">"
                + "".join(f"<li>{self.issue_link(i, i['number'])}</li>" for i in self.triage["unlisted"])
                + "</ul>"
            )
        return (
            self.stage_tiles()
            + '<div class="filter"><input id="q" type="search" placeholder="Search: dataset code, name, word" aria-label="Search findings">'
            f'<select id="stage" aria-label="Stage"><option value="">All stages</option>{options}</select>'
            '<span id="count" aria-live="polite"></span></div>'
            '<div class="table-scroll"><table class="list" id="list"><thead><tr><th>#</th><th>Finding</th>'
            f"<th>Status</th><th>Discussion</th></tr></thead><tbody>{rows}</tbody></table></div>"
            + unlisted
            + '<script src="assets/list.js"></script>'
        )

    def facts(self, rows):
        return "<dl class=\"facts\">" + "".join(f"<dt>{k}</dt><dd>{v}</dd>" for k, v in rows if v) + "</dl>"

    def finding_page(self, f):
        stage = next(s for s in triage.STAGES if s[0] == f["stage"])
        thread = self.issue_link(f["issue"], f["issue_number"])
        thread += "".join(f' · <a href="{self.repo}/issues/{n}">#{n}</a>' for n in f["other_issues"])
        thread += "".join(
            f'{" · " if thread or n else ""}<a href="{esc(u)}">{esc(community.link_label(u))} ↗</a>'
            for n, u in enumerate(f["external"])
        )
        if f["label_differs"]:
            thread += " <small>(the issue's labels do not show this status yet)</small>"
        patch, provider, shipped = f["community_patch"], f["provider_response"], f["provider_correction_shipped"]
        retained = "".join(
            f'<li><strong>{esc(x["kind"].replace("-", " ").capitalize())}.</strong> {esc(x["text"])} '
            f'<a href="{esc(x["evidence_url"])}">evidence ↗</a></li>'
            for x in f["retained"]
        )
        body = (
            f'<p class="crumb"><a href="../findings.html">Findings</a> / {f["id"]}</p>'
            f'<h1>{esc(f["title"])}</h1>'
            f'<p><span class="badge status-{esc(f["status"])}">{esc(f["status"])}</span> '
            f'<span class="stage-note">{self.named(stage[2])}</span></p>'
            + self.facts([
                ("Dataset(s)", self.render(f["datasets"], "community/findings.md", 1, True)),
                ("Release", esc(f["release"])),
                ("Discussion", thread),
                ("Community patch",
                 f'<a href="{esc(patch["url"])}">{esc(patch["id"])} ↗</a> <small>authorised by '
                 f'{esc(patch["authorisation"].get("by", "a named person"))}</small>' if patch else ""),
                (f"{esc(self.provider)}'s answer",
                 # The site names the provider, not the person; the record keeps who answered.
                 f'{esc(provider["public_summary"])} <small>({esc(provider["date"])}; '
                 f'<a href="{esc(provider["evidence_url"])}">source ↗</a>)</small>' if provider else ""),
                ("Fixed in", esc(shipped["release"]) if shipped else ""),
                ("Next", f'{esc(f["next_action"])} <small>({esc(f["review_role"])})</small>' if f["next_action"] else ""),
            ])
            + "<h2>Observation</h2>"
            + self.render(f["observation"], "community/findings.md", 1)
            + (f"<h2>How it was checked</h2><p>{esc(f['validation_scope'])}</p>" if f["validation_scope"] else "")
            + (f"<h2>Kept on record</h2><ul>{retained}</ul>" if retained else "")
            + (f"<h2>Notes</h2>{self.render(f['notes'], 'community/findings.md', 1)}" if f.get("notes") else "")
            + f'<p class="source">Record: <a href="{self.source_repo}/blob/{self.ref}/community/findings/{f["id"]}.json">community/findings/{f["id"]}.json ↗</a></p>'
        )
        return self.shell(f'{f["id"]} · {f["title"]}', body, "findings.html", depth=1)

    # ------------------------------------------------------------- contributions

    @staticmethod
    def checks(record):
        results = {}
        for run in record["runs"]:
            for check in run.get("checks", []):
                results[check["id"]] = check
        return [(name, results.get(name)) for name in record["required_checks"]]

    def contributions_list(self):
        rows = ""
        for c in self.contributions:
            checks = self.checks(c)
            passed = sum(bool(r) and r.get("status") == "passed" for _, r in checks)
            text = " ".join([c["id"], c["title"], c["status"], c["layer"]["kind"]]).lower()
            rows += (
                f'<tr id="{c["id"]}" data-stage="{esc(c["status"])}" data-text="{esc(text)}">'
                f'<td class="id"><a href="contributions/{c["id"]}.html">{c["id"]}</a></td>'
                f'<td><a class="title" href="contributions/{c["id"]}.html">{esc(c["title"])}</a>'
                f'<small>{esc(c["layer"]["kind"])}</small></td>'
                f'<td><span class="badge {esc(c["status"])}">{esc(c["status"])}</span></td>'
                f'<td class="thread">{passed} of {len(checks)} checks passed<br><small>{plural(len(c["approvals"]), "approval")}</small></td></tr>'
            )
        statuses = sorted({c["status"] for c in self.contributions})
        options = "".join(f'<option value="{esc(s)}">{esc(s.capitalize())}</option>' for s in statuses)
        return (
            '<div class="filter"><input id="q" type="search" placeholder="Search contributions" aria-label="Search contributions">'
            f'<select id="stage" aria-label="Status"><option value="">All statuses</option>{options}</select>'
            '<span id="count" aria-live="polite"></span></div>'
            '<div class="table-scroll"><table class="list" id="list"><thead><tr><th>#</th><th>Contribution</th>'
            f"<th>Status</th><th>Checks</th></tr></thead><tbody>{rows}</tbody></table></div>"
            '<script src="assets/list.js"></script>'
        )

    def contribution_page(self, c):
        def link(url, label=None):
            return f'<a href="{esc(url)}">{esc(label or url.split("//")[-1])} ↗</a>' if url else ""

        check_rows = "".join(
            f"<tr><td><code>{esc(name)}</code></td><td>"
            + (f'<span class="badge check-{esc(r["status"])}">{esc(r["status"])}</span>' if r else '<span class="badge">not run</span>')
            + "</td><td>"
            + (link(r.get("evidence_url"), "evidence") if r else "")
            + "</td></tr>"
            for name, r in self.checks(c)
        )
        baseline, layer = c["baseline"], c["layer"]
        revision_text = str(layer["implementation_revision"] or "")
        if re.fullmatch(r"[0-9a-f]{40}", revision_text):
            revision_text = revision_text[:12]
        elif len(revision_text) > 22:
            revision_text = revision_text[:22] + "…"
        implementation = link(layer["implementation_url"]) or ("not public yet" if revision_text else "")
        if revision_text:
            implementation += f" <small>at <code>{esc(revision_text)}</code></small>"
        retained = "".join(
            f'<li><strong>{esc(x["kind"].replace("-", " ").capitalize())}.</strong> {esc(x["text"])} '
            f'{link(x["evidence_url"], "evidence")}</li>'
            for x in c.get("retained", [])
        )
        body = (
            f'<p class="crumb"><a href="../contributions.html">Contributions</a> / {c["id"]}</p>'
            f'<h1>{esc(c["title"])}</h1>'
            f'<p><span class="badge {esc(c["status"])}">{esc(c["status"])}</span></p>'
            + self.facts([
                ("Kind", esc(layer["kind"])),
                ("Builds on", f'{esc(baseline["dataset"])} {esc(baseline["release"])}'),
                ("Implementation", implementation),
                ("Discussion and evidence", " · ".join(link(u) for u in c["evidence"])),
                ("Reviewers", esc(", ".join(c["required_reviewers"])) or "not yet named"),
                ("Approvals", plural(len(c["approvals"]), "approval") + " recorded"),
                ("Goes to", esc(c["upstream_project"])),
                ("Next", f'{esc(c["next_action"])} <small>({esc(c.get("review_role", ""))})</small>' if c.get("next_action") else ""),
            ])
            + '<h2>Required checks</h2><div class="table-scroll"><table><thead><tr><th>Check</th><th>Result</th><th></th></tr></thead>'
            f"<tbody>{check_rows}</tbody></table></div>"
            + (f"<h2>What the checks cover</h2><p>{esc(c['validation_scope'])}</p>" if c.get("validation_scope") else "")
            + (f"<h2>Kept on record</h2><ul>{retained}</ul>" if retained else "")
            + f'<p class="source">Record: <a href="{self.source_repo}/blob/{self.ref}/community/contributions/{c["id"]}.json">community/contributions/{c["id"]}.json ↗</a></p>'
        )
        return self.shell(f'{c["id"]} · {c["title"]}', body, "contributions.html", depth=1)

    # ------------------------------------------------------------------ overview

    def stage_href(self, key):
        return "findings.html" + (f"#stage-{key}" if self.triage["counts"].get(key) else "")

    def overview(self):
        d, p, counts = esc(self.dataset), esc(self.provider), self.triage["counts"]
        total = len(self.findings)
        with_provider = counts.get("upstream-reported", 0) + counts.get("upstream-fixed", 0)
        waiting = counts.get("needs-triage", 0)  # the same number as its tile and its filter
        accepted = sum(c["status"] == "accepted" for c in self.contributions)
        return f'''<section class="wrap hero"><div><p class="eyebrow">{d} · open dataset collaboration</p><h1>Make the dataset better.<br>Together.</h1><p class="lead">Users of the {d} inventory database report what they find here and repeat each other's measurements. The findings go to {p}, which decides what it changes. Community patches apply the corrections for those who need them now.</p><div class="actions"><a class="button primary" href="findings.html">See the findings →</a><a class="button" href="contribute.html">Take part</a></div></div><div class="route"><span class="tag">How a finding reaches {p}</span><ol><li><span>01</span>Measured on {p}'s release</li><li><span>02</span>Discussed and repeated by a second person</li><li><span>03</span>Reported to {p}</li><li><span>04</span>{p} decides what it changes</li><li><span>05</span>Answer recorded, next release checked</li></ol><p class="aside">Meanwhile, a <a href="import.html">patched release</a> applies the corrections (in preparation).</p></div></section>
<div class="strip"><div class="wrap"><span><strong><a href="findings.html">{plural(total, "finding")}</a></strong> · {with_provider} reported to or fixed by {p}</span><span><strong><a href="{self.stage_href("needs-triage")}">{waiting} awaiting a second measurement</a></strong> · help wanted</span><span><strong><a href="contributions.html">{plural(len(self.contributions), "contribution")}</a></strong> · {accepted} accepted</span></div></div>
<section class="wrap section"><p class="eyebrow">What happens here</p><h2>Feedback to {p} comes first.</h2><div class="cards"><div class="card"><span class="number">01 / FEEDBACK TO {p.upper()}</span><h3>Findings {p} can act on</h3><p>A finding is measured on {p}'s release files, repeated by a second person and reported to {p}. {p} decides what it changes. Its answer is recorded here, and so is a correction once a release contains it.</p><a href="{self.stage_href("upstream-reported")}">See what was reported →</a></div><div class="card"><span class="number">02 / CONTRIBUTIONS</span><h3>Proposals, models and variants</h3><p>Mappings, rebuilt inventories and method variants such as residual electricity mixes, each with evidence and named reviewers. An accepted contribution may become a recommendation to {p}. A variant keeps its own name and never replaces {p}'s numbers.</p><a href="contributions.html">See the contributions →</a></div><div class="card"><span class="number">03 / MEANWHILE</span><h3>A patched release, for convenience</h3><p>{p}'s release with community patches applied, for those who need the corrections now. Each patch names its author and who authorised it. In preparation.</p><a href="import.html">How it is built →</a></div></div></section>
<section class="wrap section" style="padding-top:0"><p class="eyebrow">Where things stand</p><h2>Every finding has a stage, a discussion and a next step.</h2>{self.stage_tiles("findings.html")}<div class="band"><p><strong>Found something in the data?</strong><br>Report it with the dataset code, the release and what you measured. It gets a number and stays marked as awaiting a second measurement until a second person has repeated it.</p><a class="button" href="{self.repo}/issues/new?template=bafu-data-finding.yml">Report a finding ↗</a></div></section>'''

    # --------------------------------------------------------------------- build

    def build(self):
        out = self.out
        # status.json marks a folder this build wrote before; only there may pages be removed.
        rebuilt = (out / "status.json").exists()
        self.written = set()
        out.mkdir(parents=True, exist_ok=True)
        shutil.copytree(ROOT / "site/assets", out / "assets", dirs_exist_ok=True)
        shutil.copyfile(ROOT / "site/style.css", out / "style.css")
        (out / ".nojekyll").touch()
        self.write("index.html", self.shell("Overview", self.overview(), "index.html", wide=True))
        inserts = {
            "<!-- findings-list -->": self.findings_list,
            "<!-- contributions-list -->": self.contributions_list,
        }
        for doc in self.docs:
            rendered = self.render((ROOT / doc["source"]).read_text(), doc["source"])
            for marker, make in inserts.items():
                if marker in rendered:
                    rendered = rendered.replace(marker, make())
            self.write(doc["page"], self.shell(doc["title"], rendered, doc["page"]))
        for f in self.triage["findings"]:
            self.write(f'findings/{f["id"]}.html', self.finding_page(f))
        for c in self.contributions:
            self.write(f'contributions/{c["id"]}.html', self.contribution_page(c))
        for old, new in self.config.get("redirects", {}).items():
            self.write(old, f'<!doctype html><meta charset="utf-8"><title>Moved</title><meta http-equiv="refresh" content="0; url={esc(new)}"><a href="{esc(new)}">This page moved.</a>')
        # Pages serves 404.html for any missing path, so its links need a base.
        base = self.config["site_url"]
        missing = self.shell("Page not found", '<h1>That page is missing.</h1><p><a href="index.html">Back to the overview →</a></p>', "404.html")
        self.write("404.html", missing.replace("<head>", f'<head><base href="{esc(base)}">', 1))
        # Machine-readable index for other projects; coordination data only, no inventory rows.
        index = [
            dict(id=f["id"], title=f["title"], status=f["status"], stage=f["stage"], release=f["release"],
                 links=f["links"], page=f'findings/{f["id"]}.html')
            for f in sorted(self.triage["findings"], key=community.finding_number)
        ]
        (out / "findings.json").write_text(json.dumps(index, indent=1, ensure_ascii=False) + "\n")
        (out / "status.json").write_text(json.dumps({
            "dataset": self.dataset,
            "findings": len(self.findings),
            "findings_by_stage": self.triage["counts"],
            "contributions": len(self.contributions),
            "accepted": sum(c["status"] == "accepted" for c in self.contributions),
            "source_ref": self.ref,
            "revision": self.revision,
            "built": self.built,
            "issues": self.issues_source,
            "preview": bool(self.preview_url),
        }, indent=2) + "\n")
        if rebuilt:
            # A page of an earlier build that this one no longer writes would stay reachable.
            for stale in sorted(set(out.rglob("*.html")) - self.written):
                stale.unlink()
        pages = sum(1 for _ in out.rglob("*.html"))
        print(f"Built {self.dataset}: {pages} pages in {out}")


def build(out, source_repository=None, source_ref=None, preview_url=None, issues_snapshot=None,
          offline=False, require_issues=False):
    Site(out, source_repository, source_ref, preview_url, issues_snapshot, offline, require_issues).build()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=ROOT / "_site")
    parser.add_argument("--source-repository", help="Repository containing this build's source")
    parser.add_argument("--source-ref", help="Source branch or revision for repository links")
    parser.add_argument("--preview-url", help="Show a review notice linking to this pull request")
    parser.add_argument("--issues", type=Path, help="Issue snapshot (JSON) instead of reading GitHub")
    parser.add_argument("--offline", action="store_true", help="Do not read issues from GitHub")
    parser.add_argument("--require-issues", action="store_true", help="Fail when GitHub cannot be read")
    args = parser.parse_args()
    build(args.out, args.source_repository, args.source_ref, args.preview_url, args.issues,
          args.offline, args.require_issues)
