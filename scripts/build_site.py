"""Build the public site from the records and an explicit, inventory-free file list.

Run: uv run --no-project --with markdown==3.7 scripts/build_site.py

The site has a page per finding and per contribution, so it holds thousands of them. Issue
details (comment counts, labels) come from GitHub when it can be reached; see triage.py.

The build validates every record first, with the rules of `community.py check`, and writes
nothing while a record is invalid: what the check would refuse must not reach a page.
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
RECORD_FILE = re.compile(r"community/(findings|contributions)/(?:[^/]+/)*([FC][0-9]+)\.json")


def esc(value):
    return html.escape(str(value), quote=True)


def plural(n, word):
    return f"{n} {word}{'' if n == 1 else 's'}"


def revision(root):
    try:
        return subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
    except Exception:
        return None


class Site:
    def __init__(self, out, source_repository=None, source_ref=None, preview_url=None,
                 issues_snapshot=None, offline=False, require_issues=False, root=ROOT):
        self.out = Path(out)
        self.root = Path(root)
        # A record that `community.py check` refuses must not be built into a page either.
        errors, _, _ = community.problems(self.root)
        if errors:
            raise SystemExit("The records are not valid; nothing was built.\n" + "\n".join(errors))
        self.config = json.loads((self.root / "site/config.json").read_text())
        self.repo = self.config["repository"]
        self.source_repo = source_repository or self.repo
        self.ref = source_ref or self.config["source_ref"]
        if preview_url and not preview_url.startswith("https://github.com/"):
            raise ValueError("Preview notice must link to a GitHub pull request")
        self.preview_url = preview_url
        self.dataset = self.config["dataset"]
        self.provider = self.config["provider"]
        self.records_config = community.load_config(self.root)
        self.docs = self.config["documents"]
        self.routes = {d["source"]: d["page"] for d in self.docs}
        self.routes["community/findings/README.md"] = "findings.html"
        self.findings = community.load_findings(self.root)
        self.contributions = community.load_contributions(self.root)
        self.patches = community.load_patches(self.root)
        issues, self.issues_source = triage.load_issues(
            self.repo, issues_snapshot, offline, require_issues
        )
        self.triage = triage.assemble(self.findings, self.repo, issues, self.patches)
        self.built = datetime.date.today().isoformat()
        self.revision = revision(self.root)
        self.written = set()

    # ------------------------------------------------------------------ helpers

    def label(self, stage):
        return community.status_label(stage, self.provider)

    def target(self, link, source):
        """Where a relative link in a source file points on the site (or on GitHub)."""
        path, sep, fragment = link.partition("#")
        absolute = (self.root / Path(source).parent / path).resolve()
        try:
            relative = absolute.relative_to(self.root.resolve()).as_posix()
        except ValueError:
            raise ValueError(f"Link leaves repository: {link}") from None
        page = self.routes.get(relative)
        record = RECORD_FILE.fullmatch(relative)
        if not page and record:
            # A link to a record names the file's real path, so it also works on GitHub.
            if not absolute.is_file():
                raise ValueError(f"{source} links to a record that is not there: {link}")
            page = f"{record.group(1)}/{record.group(2)}.html"
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

    def record_text(self, text, inline=False):
        """Markdown of a record. Records hold no raw HTML, no image, no heading and only
        full https links (the build refused them above), so nothing here needs a source file."""
        rendered = markdown.markdown(text, extensions=["tables", "fenced_code", "sane_lists"])
        # Second line of defence behind the validation: whatever the Markdown turned into,
        # a record puts no address on a page that is not a plain https link.
        for address in re.findall(r'(?:href|src)="([^"]*)"', rendered):
            if not community.HTTPS_URL.fullmatch(html.unescape(address)):
                raise ValueError(f"Record text would link to {address!r}; only https addresses are written")
        rendered = rendered.replace("<table>", '<div class="table-scroll"><table>').replace(
            "</table>", "</table></div>"
        )
        return re.sub(r"^<p>|</p>$", "", rendered.strip()) if inline else rendered

    def issue_link(self, issue, number):
        if not issue:
            return f'<a href="{esc(self.repo)}/issues/{int(number)}">#{int(number)} ↗</a>' if number else ""
        return (
            f'<a href="{esc(issue["url"])}">#{int(issue["number"])} ↗</a> '
            f'<small>{esc(plural(issue["comments"], "comment"))} · updated {esc(issue["updated"])}'
            f'{" · closed" if issue["state"] == "closed" else ""}</small>'
        )

    def thread_links(self, f):
        return " · ".join(
            f'<a href="{esc(u)}">{esc(community.link_label(u))} ↗</a>' for u in f["threads"]
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
<a class="skip" href="#main">Skip to content</a><header class="masthead"><div class="wrap top"><div class="brand"><a class="brand-logo" href="https://www.d-d-s.ch/" aria-label="Départ de Sentier"><img src="{up}assets/dds-logo.svg" alt="Départ de Sentier" width="200" height="94"></a><a class="dataset" href="{up}index.html" aria-label="{esc(self.dataset)} home">{esc(self.dataset)}</a></div><div class="top-links"><a href="{esc(c["sibling_url"])}">{esc(c["sibling_name"])} ↗</a><a href="{esc(self.repo)}">Repository ↗</a></div></div><nav class="wrap nav" aria-label="Main navigation">{nav}</nav></header>
{notice}<main id="main">{main}</main>
<footer><div class="wrap"><p><strong>A Sentier community workspace.</strong><br>Findings and contributions concern {esc(self.provider)}'s dataset. {esc(self.provider)}'s endorsement is not implied.<small class="brand-credit">{snapshot}. <a href="https://github.com/Depart-de-Sentier/dds-logo">Logo</a> by <a href="https://proov.fr/">Sylvain Prevost</a> · <a href="https://www.d-d-s.ch/">Départ de Sentier</a></small></p><p><a href="{up}terms.html">Data and terms</a><br><a href="{up}contribute.html">Take part</a><br><a href="{esc(self.repo)}/issues/new/choose">Open an issue ↗</a></p></div></footer></body></html>'''

    def write(self, page, text):
        """Write one file of the site. A path that leaves the output folder is refused."""
        path = self.out / page
        if not path.resolve().is_relative_to(self.out.resolve()):
            raise ValueError(f"Refusing to write outside the output folder: {page}")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        self.written.add(path)

    def write_json(self, page, data, one_per_line=None):
        """JSON for tools. A list that grows with the records is written one entry per line:
        a third of the size of an indented file, and still readable and comparable."""
        if one_per_line is None:
            self.write(page, json.dumps(data, indent=1, ensure_ascii=False) + "\n")
            return
        entries = data[one_per_line]
        compact = lambda value: json.dumps(value, ensure_ascii=False, separators=(",", ":"))  # noqa: E731
        if isinstance(entries, dict):
            body = ",\n".join(f"{json.dumps(key)}:{compact(value)}" for key, value in entries.items())
            body = "{\n" + body + "\n}"
        else:
            body = "[\n" + ",\n".join(compact(value) for value in entries) + "\n]"
        head = json.dumps({k: v for k, v in data.items() if k != one_per_line}, indent=1, ensure_ascii=False)
        self.write(page, head[: head.rindex("}")].rstrip() + f',\n "{one_per_line}": {body}\n}}\n')

    # ------------------------------------------------------------------ findings

    def concerns(self, f, depth=0):
        """The datasets a finding is about, by code, name and location, then its scope."""
        parts = [
            f'{int(d["code"])} {esc(d["name"])} ({esc(d["location"])})'
            for d in f["datasets"]
            if d.get("role", "subject") == "subject"
        ]
        if f["scope"].strip():
            parts.append(self.record_text(f["scope"], inline=True))
        return "; ".join(parts)

    def also_names(self, f):
        """Datasets a finding names without being about them: consumers, suppliers, comparisons."""
        return "; ".join(
            f'{int(d["code"])} {esc(d["name"])} ({esc(d["location"])}) <small>{esc(d["role"])}</small>'
            for d in f["datasets"]
            if d.get("role", "subject") != "subject"
        )

    def stage_tiles(self, link_prefix=""):
        counts = self.triage["counts"]
        return '<div class="stages">' + "".join(
            f'<a class="stage" id="stage-{s["key"]}" href="{link_prefix}#stage-{s["key"]}" data-filter="{s["key"]}">'
            f'<strong>{counts[s["key"]]}</strong>{esc(s["label"])}</a>'
            for s in community.statuses(self.provider)
            if counts.get(s["key"])
        ) + "</div>"

    def findings_list(self):
        rows = ""
        for f in self.triage["findings"]:
            rid, label = esc(f["id"]), self.label(f["stage"])
            releases = community.release_names(f, self.records_config)
            words = [f["id"], f["title"], f["scope"], releases, label]
            words += [f'{d["code"]} {d["name"]} {d["location"]}' for d in f["datasets"]]
            words += [f'patch {p["id"]}' for p in f["patches"]]
            discussion = self.issue_link(f["tracker"], f["issue"]) or self.thread_links(f)
            rows += (
                f'<tr id="{rid}" data-stage="{esc(f["stage"])}" data-text="{esc(" ".join(words).lower())}">'
                f'<td class="id"><a href="findings/{rid}.html">{rid}</a></td>'
                f'<td><a class="title" href="findings/{rid}.html">{esc(f["title"])}</a>'
                f'<small>{self.concerns(f)} · {esc(releases)}</small></td>'
                f'<td><span class="badge status-{esc(f["stage"])}">{esc(label)}</span></td>'
                f'<td class="thread">{discussion}</td></tr>'
            )
        options = "".join(
            f'<option value="{s["key"]}">{esc(s["label"])}</option>'
            for s in community.statuses(self.provider)
            if self.triage["counts"].get(s["key"])
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
            f'<select id="stage" aria-label="Status"><option value="">All statuses</option>{options}</select>'
            '<span id="count" aria-live="polite"></span></div>'
            '<div class="table-scroll"><table class="list" id="list"><thead><tr><th>#</th><th>Finding</th>'
            f"<th>Status</th><th>Discussion</th></tr></thead><tbody>{rows}</tbody></table></div>"
            + unlisted
            + '<script src="assets/list.js"></script>'
        )

    def facts(self, rows):
        return "<dl class=\"facts\">" + "".join(f"<dt>{k}</dt><dd>{v}</dd>" for k, v in rows if v) + "</dl>"

    def finding_page(self, f):
        rid, p = esc(f["id"]), esc(self.provider)
        thread = " · ".join(x for x in (self.issue_link(f["tracker"], f["issue"]), self.thread_links(f)) if x)
        reported, repeated, sent = f["reported"], f["repeated"], f["sent"]
        answer, fixed, closed = f["answer"], f["fixed_in"], f["closed"]
        releases = {r["id"]: r["name"] for r in self.records_config["releases"]}

        def dated(block, text, link="source"):
            when = f'{esc(block["date"])}; ' if block.get("date") else ""
            return f'{text} <small>({when}<a href="{esc(block["url"])}">{link} ↗</a>)</small>'

        retained = "".join(
            f'<li><strong>{esc(x["kind"].replace("-", " ").capitalize())}.</strong> {esc(x["text"])} '
            f'<a href="{esc(x["evidence_url"])}">evidence ↗</a></li>'
            for x in f["retained"]
        )
        body = (
            f'<p class="crumb"><a href="../findings.html">Findings</a> / {rid}</p>'
            f'<h1>{esc(f["title"])}</h1>'
            f'<p><span class="badge status-{esc(f["stage"])}">{esc(self.label(f["stage"]))}</span> '
            f'<span class="stage-note">{esc(community.status_description(f["stage"], self.provider))}</span></p>'
            + self.facts([
                ("Concerns", self.concerns(f)),
                ("Also names", self.also_names(f)),
                (f"{p} release", esc(community.release_names(f, self.records_config))),
                ("Kind", esc(community.KINDS[f["kind"]]["label"])),
                ("Discussion", thread),
                ("Reported", dated(reported, f'by {esc(reported["by"])}' if reported["by"] else "", "where")),
                ("Second measurement",
                 dated(repeated, f'{esc(repeated["result"].replace("-", " "))}, by {esc(repeated["by"])}', "what they got")
                 if repeated else "not recorded"),
                (f"Reported to {p}", dated(sent, f'batch {esc(sent["batch"])}') if sent else ""),
                (f"{p}'s answer",
                 dated(answer, f'{self.record_text(answer["summary"], inline=True)} '
                               f'<small>{esc(community.OUTCOMES[answer["outcome"]]["label"])}</small>')
                 if answer else ""),
                ("Corrected in",
                 dated(fixed, esc(releases.get(fixed["release"], fixed["release"]))
                       + (f': {self.record_text(fixed["detail"], inline=True)}' if fixed.get("detail") else ""))
                 if fixed else ""),
                ("Closed", dated(closed, self.record_text(closed["reason"], inline=True), "where") if closed else ""),
                ("Community patch",
                 "; ".join(
                     f'<a href="{esc(x["url"])}">Patch {esc(x["id"])} ↗</a>: {self.record_text(x["description"], inline=True)} '
                     f'<small>authorised by {esc(x["authorised_by"] or "nobody yet")}</small>'
                     for x in f["patches"])),
                ("Related", " · ".join(f'<a href="{esc(x)}.html">{esc(x)}</a>' for x in f["related"])),
                ("Next", f'{self.record_text(f["next"]["action"], inline=True)} <small>({esc(f["next"]["role"])})</small>' if f["next"] else ""),
            ])
            + "<h2>Observation</h2>"
            + self.record_text(f["observation"])
            + (f"<h2>What it affects</h2>{self.record_text(f['exposure'])}" if f["exposure"].strip() else "")
            + (f"<h2>How it was checked</h2>{self.record_text(f['method'])}" if f["method"].strip() else "")
            + (f"<h2>Kept on record</h2><ul>{retained}</ul>" if retained else "")
            + (f"<h2>Notes</h2>{self.record_text(f['notes'])}" if f["notes"].strip() else "")
            + f'<p class="source">Record: <a href="{esc(self.source_repo)}/blob/{esc(self.ref)}/{esc(f["path"])}">{esc(f["path"])} ↗</a></p>'
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
            cid = esc(c["id"])
            checks = self.checks(c)
            passed = sum(bool(r) and r.get("status") == "passed" for _, r in checks)
            kind = community.CONTRIBUTION_CLASS[c["class"]]["label"]
            text = " ".join([c["id"], c["title"], c["status"], kind, c["layer"]["kind"]]).lower()
            rows += (
                f'<tr id="{cid}" data-stage="{esc(c["status"])}" data-text="{esc(text)}">'
                f'<td class="id"><a href="contributions/{cid}.html">{cid}</a></td>'
                f'<td><a class="title" href="contributions/{cid}.html">{esc(c["title"])}</a>'
                f'<small>{esc(kind)}</small></td>'
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

        cid = esc(c["id"])
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
        kind = community.CONTRIBUTION_CLASS[c["class"]]
        group = community.CONTRIBUTION_GROUPS[kind["group"]].format(provider=self.provider)
        body = (
            f'<p class="crumb"><a href="../contributions.html">Contributions</a> / {cid}</p>'
            f'<h1>{esc(c["title"])}</h1>'
            f'<p><span class="badge {esc(c["status"])}">{esc(c["status"])}</span></p>'
            + self.facts([
                ("Kind", f'{esc(kind["label"])} <small>{esc(group.lower())}</small>'),
                ("Builds on", f'{esc(baseline["dataset"])} {esc(baseline["release"])}'),
                ("Implementation", implementation),
                ("Discussion and evidence",
                 " · ".join(x for x in [self.issue_link(None, c["issue"])] + [link(u) for u in c["evidence"]] if x)),
                ("Reviewers", esc(", ".join(c["required_reviewers"])) or "not yet named"),
                ("Approvals", plural(len(c["approvals"]), "approval") + " recorded"),
                ("Goes to", esc(c["upstream_project"])),
                ("Next", f'{esc(c["next_action"])} <small>({esc(c.get("review_role", ""))})</small>' if c.get("next_action") else ""),
            ])
            + '<h2>Required checks</h2><div class="table-scroll"><table><thead><tr><th>Check</th><th>Result</th><th></th></tr></thead>'
            f"<tbody>{check_rows}</tbody></table></div>"
            + (f"<h2>What the checks cover</h2><p>{esc(c['validation_scope'])}</p>" if c.get("validation_scope") else "")
            + (f"<h2>Kept on record</h2><ul>{retained}</ul>" if retained else "")
            + f'<p class="source">Record: <a href="{esc(self.source_repo)}/blob/{esc(self.ref)}/{esc(c.path)}">{esc(c.path)} ↗</a></p>'
        )
        return self.shell(f'{c["id"]} · {c["title"]}', body, "contributions.html", depth=1)

    # ------------------------------------------------------------------ overview

    def stage_href(self, key):
        return "findings.html" + (f"#stage-{key}" if self.triage["counts"].get(key) else "")

    def overview(self):
        d, p, counts = esc(self.dataset), esc(self.provider), self.triage["counts"]
        total = len(self.findings)
        with_provider = counts.get("sent", 0) + counts.get("answered", 0) + counts.get("fixed", 0)
        waiting = counts.get("filed", 0)  # the same number as its tile and its filter
        accepted = sum(c["status"] == "accepted" for c in self.contributions)
        return f'''<section class="wrap hero"><div><p class="eyebrow">{d} · open dataset collaboration</p><h1>Make the dataset better.<br>Together.</h1><p class="lead">Users of the {d} inventory database report what they find here and repeat each other's measurements. The findings go to {p}, which decides what it changes. Community patches apply the corrections for those who need them now.</p><div class="actions"><a class="button primary" href="findings.html">See the findings →</a><a class="button" href="contribute.html">Take part</a></div></div><div class="route"><span class="tag">How a finding reaches {p}</span><ol><li><span>01</span>Measured on {p}'s release</li><li><span>02</span>Discussed and repeated by a second person</li><li><span>03</span>Reported to {p}</li><li><span>04</span>{p} decides what it changes</li><li><span>05</span>Answer recorded, next release checked</li></ol><p class="aside">Meanwhile, a <a href="import.html">patched release</a> applies the corrections (in preparation).</p></div></section>
<div class="strip"><div class="wrap"><span><strong><a href="findings.html">{plural(total, "finding")}</a></strong> · {with_provider} reported to, answered or corrected by {p}</span><span><strong><a href="{self.stage_href("filed")}">{waiting} need a second measurement</a></strong> · help wanted</span><span><strong><a href="contributions.html">{plural(len(self.contributions), "contribution")}</a></strong> · {accepted} accepted</span></div></div>
<section class="wrap section"><p class="eyebrow">What happens here</p><h2>Feedback to {p} comes first.</h2><div class="cards"><div class="card"><span class="number">01 / FEEDBACK TO {p.upper()}</span><h3>Findings {p} can act on</h3><p>A finding is measured on {p}'s release files, repeated by a second person and reported to {p}. {p} decides what it changes. Its answer is recorded here, and so is a correction once a release contains it.</p><a href="{self.stage_href("answered")}">See what {p} answered →</a></div><div class="card"><span class="number">02 / CONTRIBUTIONS</span><h3>Proposals, models and variants</h3><p>Mappings, rebuilt inventories and method variants such as residual electricity mixes, each with evidence and named reviewers. An accepted contribution may become a recommendation to {p}. A variant keeps its own name and never replaces {p}'s numbers.</p><a href="contributions.html">See the contributions →</a></div><div class="card"><span class="number">03 / MEANWHILE</span><h3>A patched release, for convenience</h3><p>{p}'s release with community patches applied, for those who need the corrections now. Each patch names its author and who authorised it. In preparation.</p><a href="import.html">How it is built →</a></div></div></section>
<section class="wrap section" style="padding-top:0"><p class="eyebrow">Where things stand</p><h2>Every finding has a status, computed from its dated evidence.</h2>{self.stage_tiles("findings.html")}<div class="band"><p><strong>Found something in the data?</strong><br>Report it with the dataset code, the release and what you measured. Its status stays "{esc(self.label("filed"))}" until a second person has repeated it.</p><a class="button" href="{esc(self.repo)}/issues/new?template=bafu-data-finding.yml">Report a finding ↗</a></div></section>'''

    # --------------------------------------------------------- machine-readable

    def finding_summary(self, f):
        """One finding for api/v1/findings.json: coordination fields only, absolute addresses."""
        base = self.config["site_url"]
        dates = {name: (f[name] or {}).get("date") for name in community.EVIDENCE}
        return {
            "id": f["id"],
            "issue": f["issue"],
            "title": f["title"],
            "kind": f["kind"],
            "status": f["stage"],
            "status_label": self.label(f["stage"]),
            "datasets": [d["code"] for d in f["datasets"]],
            "scope": f["scope"],
            "releases": f["releases"],
            "patches": [x["id"] for x in f["patches"]],
            "answer_outcome": f["answer"]["outcome"] if f["answer"] else None,
            "reported": dates["reported"],
            "repeated": dates["repeated"],
            "sent": dates["sent"],
            "answered": dates["answer"],
            "fixed": dates["fixed_in"],
            "closed": dates["closed"],
            "changed": f["changed"],
            "waiting_since": f["waiting_since"],
            "url": f'{base}findings/{f["id"]}.html',
            "json": f'{base}api/v1/findings/{f["id"]}.json',
        }

    def write_data(self):
        """Machine-readable outputs for other projects: coordination data only, no inventory rows."""
        placed = sorted(self.triage["findings"], key=community.finding_number)
        base, counts = self.config["site_url"], self.triage["counts"]
        identity = {"generated": self.built, "revision": self.revision, "site": base}
        record_fields = community.FINDING_FIELDS
        self.write_json("api/v1/findings.json", {
            "schema": "sentier-bafu/findings/1",
            **identity,
            "statuses": community.statuses(self.provider),
            "findings": [self.finding_summary(f) for f in placed],
        }, one_per_line="findings")
        for f in placed:
            summary = self.finding_summary(f)
            self.write_json(f'api/v1/findings/{f["id"]}.json', {
                "schema": "sentier-bafu/finding/1",
                **identity,
                "record": {key: f[key] for key in record_fields},
                "status": f["stage"],
                "status_label": summary["status_label"],
                "patches": f["patches"],
                "related": f["related"],
                "changed": f["changed"],
                "waiting_since": f["waiting_since"],
                "discussion": f["tracker"],
                "url": summary["url"],
                "source": f'{self.source_repo}/blob/{self.ref}/{f["path"]}',
            })
        self.write_json("api/v1/datasets.json", {
            "schema": "sentier-bafu/datasets/1",
            **identity,
            "roles": community.DATASET_ROLES,
            "datasets": {str(code): entry for code, entry in community.dataset_index(self.findings, self.patches).items()},
        }, one_per_line="datasets")
        self.write_json("api/v1/contributions.json", {
            "schema": "sentier-bafu/contributions/1",
            **identity,
            "classes": [
                {k: v.format(provider=self.provider) for k, v in c.items()} for c in community.CONTRIBUTION_CLASSES
            ],
            "contributions": [
                {
                    "id": c["id"],
                    "issue": c["issue"],
                    "title": c["title"],
                    "class": c["class"],
                    "status": c["status"],
                    "url": f'{base}contributions/{c["id"]}.html',
                }
                for c in self.contributions
            ],
        })
        status = {
            "dataset": self.dataset,
            "findings": len(self.findings),
            "findings_by_stage": counts,
            "contributions": len(self.contributions),
            "accepted": sum(c["status"] == "accepted" for c in self.contributions),
            "source_ref": self.ref,
            "revision": self.revision,
            "built": self.built,
            "issues": self.issues_source,
            "preview": bool(self.preview_url),
        }
        self.write_json("api/v1/status.json", {
            "schema": "sentier-bafu/status/1",
            **status,
            "findings_by_status": {s["key"]: counts.get(s["key"], 0) for s in community.STATUSES},
            "patches": len((self.patches or {}).get("patches", [])),
        })
        for name in ("finding", "contribution"):
            self.write(f"schema/{name}.schema.json", (ROOT / f"schema/{name}.schema.json").read_text())
        # The one-line-per-finding table is a build output, never a committed file.
        self.write("ledger.md", community.index_text(self.findings, self.records_config))
        # Kept at the root, in their earlier shape, for readers that have not moved to api/v1.
        self.write_json("findings.json", [
            dict(id=f["id"], title=f["title"], status=f["stage"], stage=f["stage"],
                 release=community.release_names(f, self.records_config),
                 links=community.discussion_links(f, self.repo), page=f'findings/{f["id"]}.html')
            for f in placed
        ])
        self.write("status.json", json.dumps(status, indent=2) + "\n")

    # --------------------------------------------------------------------- build

    def build(self):
        out = self.out
        # status.json marks a folder this build wrote before; only there may pages be removed.
        rebuilt = (out / "status.json").exists()
        self.written = set()
        out.mkdir(parents=True, exist_ok=True)
        shutil.copytree(self.root / "site/assets", out / "assets", dirs_exist_ok=True)
        shutil.copyfile(self.root / "site/style.css", out / "style.css")
        (out / ".nojekyll").touch()
        self.write("index.html", self.shell("Overview", self.overview(), "index.html", wide=True))
        inserts = {
            "<!-- findings-list -->": self.findings_list,
            "<!-- contributions-list -->": self.contributions_list,
        }
        for doc in self.docs:
            rendered = self.render((self.root / doc["source"]).read_text(), doc["source"])
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
        self.write_data()
        if rebuilt:
            # A page of an earlier build that this one no longer writes would stay reachable.
            for stale in sorted((set(out.rglob("*.html")) | set((out / "api").rglob("*.json"))) - self.written):
                stale.unlink()
        pages = sum(1 for _ in out.rglob("*.html"))
        print(f"Built {self.dataset}: {pages} pages in {out}")
        # For maintainers, in the build log only: a public page does not report housekeeping.
        differences = self.triage["label_differences"]
        if differences:
            print(
                f"Labels of {plural(len(differences), 'issue')} differ from the records: "
                + ", ".join(f"#{d['issue']}" for d in differences)
            )


def build(out, source_repository=None, source_ref=None, preview_url=None, issues_snapshot=None,
          offline=False, require_issues=False, root=ROOT):
    Site(out, source_repository, source_ref, preview_url, issues_snapshot, offline, require_issues, root).build()


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
