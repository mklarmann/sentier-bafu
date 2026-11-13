"""A stand-in for the GitHub REST API, for the tests of scripts/intake.py and scripts/sync.py.

It keeps a repository in memory (branches with their files, pull requests, issues with labels
and comments, label definitions, commit statuses) and answers the requests those two scripts
send. Nothing here reaches the network. A request it does not know is an error, so a test
also shows that a script sends no request it should not.

    fake = FakeGitHub(issues={48: {"labels": ["bafu-finding"]}})
    api = GitHub("sentier-dev/sentier-bafu", "token", transport=fake)
"""

import base64
import hashlib
import json
import re
import urllib.parse

REPOSITORY = "sentier-dev/sentier-bafu"
BOT = {"login": "github-actions[bot]", "type": "Bot"}


class FakeGitHub:
    def __init__(self, issues=None, labels=None, files=None, remaining=5000):
        self.branches = {"main": dict(files or {})}
        self.heads = {"main": "a" * 40}
        self.history = {"main": []}  # per branch: [(sha, path, author)]
        self.pulls = []
        self.issues = {}
        for number, issue in (issues or {}).items():
            self.add_issue(number, **issue)
        self.labels = {
            name: {"name": name, "color": "ededed", "description": ""} for name in (labels or [])
        }
        for issue in self.issues.values():
            for name in issue["labels"]:
                self.labels.setdefault(name, {"name": name, "color": "ededed", "description": ""})
        self.statuses = []
        self.calls = []
        self.remaining = remaining
        self.fail = None  # (method, path pattern, status): answer that request with an error once
        self.next_id = 1000

    # ------------------------------------------------------------------ state for the tests

    def add_issue(self, number, labels=(), state="open", state_reason=None, pull_request=False, comments=()):
        self.issues[number] = {
            "number": number,
            "state": state,
            "state_reason": state_reason,
            "labels": list(labels),
            "pull_request": pull_request,
            "comments": [dict(comment) for comment in comments],
        }

    def writes(self):
        return [call for call in self.calls if call[0] != "GET"]

    def bodies(self, issue):
        return [comment["body"] for comment in self.issues[issue]["comments"]]

    def commit(self, branch, path, text, author=BOT):
        """A commit on a branch, as a person or the workflow would make it."""
        self.next_id += 1
        sha = hashlib.sha1(f"{branch}{path}{text}{self.next_id}".encode()).hexdigest()
        self.branches[branch][path] = text
        self.heads[branch] = sha
        self.history[branch].append((sha, path, author))
        return sha

    def merge(self, number):
        """Merge a pull request into main, as a maintainer would."""
        pull = next(p for p in self.pulls if p["number"] == number)
        self.branches["main"].update(self.branches[pull["head"]])
        self.heads["main"] = hashlib.sha1(f"merge{number}".encode()).hexdigest()
        pull.update(state="closed", merged=True)

    # ------------------------------------------------------------------------- the transport

    def __call__(self, method, url, headers, body):
        parsed = urllib.parse.urlsplit(url)
        prefix = f"/repos/{REPOSITORY}"
        assert parsed.path.startswith(prefix), f"request outside the repository: {url}"
        path = urllib.parse.unquote(parsed.path[len(prefix):])
        query = dict(urllib.parse.parse_qsl(parsed.query))
        payload = json.loads(body) if body else None
        self.calls.append((method, path, payload))
        if self.remaining <= 0:
            return self.answer(403, {"message": "API rate limit exceeded"})
        self.remaining -= 1
        if self.fail and self.fail[0] == method and re.fullmatch(self.fail[1], path):
            status, self.fail = self.fail[2], None
            return self.answer(status, {"message": "injected failure"})
        status, data = self.route(method, path, query, payload)
        return self.answer(status, data)

    def answer(self, status, data):
        headers = {"x-ratelimit-remaining": str(self.remaining)}
        return status, headers, json.dumps(data).encode()

    def page(self, items, query):
        size, number = int(query.get("per_page", 30)), int(query.get("page", 1))
        return 200, items[(number - 1) * size: number * size]

    def issue_item(self, issue):
        item = {
            "number": issue["number"],
            "state": issue["state"],
            "state_reason": issue["state_reason"],
            "labels": [{"name": name} for name in issue["labels"]],
        }
        if issue["pull_request"]:
            item["pull_request"] = {}
        return item

    def route(self, method, path, query, payload):
        match = re.fullmatch(r"/issues", path)
        if match and method == "GET":
            wanted = query.get("labels")
            found = [self.issue_item(i) for n, i in sorted(self.issues.items()) if not wanted or wanted in i["labels"]]
            return self.page(found, query)
        match = re.fullmatch(r"/issues/(\d+)", path)
        if match:
            issue = self.issues.get(int(match.group(1)))
            if not issue:
                return 404, {"message": "Not Found"}
            if method == "PATCH":
                issue.update({key: payload[key] for key in ("state", "state_reason") if key in payload})
            return 200, self.issue_item(issue)
        match = re.fullmatch(r"/issues/(\d+)/comments", path)
        if match:
            issue = self.issues[int(match.group(1))]
            if method == "GET":
                return self.page(issue["comments"], query)
            self.next_id += 1
            issue["comments"].append({"id": self.next_id, "body": payload["body"], "user": BOT})
            return 201, issue["comments"][-1]
        match = re.fullmatch(r"/issues/(\d+)/labels", path)
        if match and method == "POST":
            issue = self.issues[int(match.group(1))]
            for name in payload["labels"]:
                self.labels.setdefault(name, {"name": name, "color": "ededed", "description": ""})
                if name not in issue["labels"]:
                    issue["labels"].append(name)
            return 200, [{"name": name} for name in issue["labels"]]
        match = re.fullmatch(r"/issues/(\d+)/labels/(.+)", path)
        if match and method == "DELETE":
            issue = self.issues[int(match.group(1))]
            if match.group(2) not in issue["labels"]:
                return 404, {"message": "Label does not exist"}
            issue["labels"].remove(match.group(2))
            return 200, [{"name": name} for name in issue["labels"]]
        if path == "/labels" and method == "GET":
            return self.page(sorted(self.labels.values(), key=lambda label: label["name"]), query)
        if path == "/labels" and method == "POST":
            if payload["name"] in self.labels:
                return 422, {"message": "Validation Failed"}
            self.labels[payload["name"]] = dict(payload)
            return 201, payload
        match = re.fullmatch(r"/labels/(.+)", path)
        if match and method == "PATCH":
            self.labels[match.group(1)].update(payload)
            return 200, self.labels[match.group(1)]
        if path == "/pulls" and method == "GET":
            head = query["head"].split(":", 1)[1]
            return 200, [p for p in self.pulls if p["head"] == head]
        if path == "/pulls" and method == "POST":
            if any(p["head"] == payload["head"] and p["state"] == "open" for p in self.pulls):
                return 422, {"message": "A pull request already exists"}
            self.next_id += 1
            self.pulls.append(dict(payload, number=self.next_id, state="open", merged=False))
            return 201, self.pulls[-1]
        match = re.fullmatch(r"/git/ref/heads/(.+)", path)
        if match and method == "GET":
            if match.group(1) not in self.heads:
                return 404, {"message": "Not Found"}
            return 200, {"object": {"sha": self.heads[match.group(1)]}}
        if path == "/git/refs" and method == "POST":
            branch = payload["ref"].removeprefix("refs/heads/")
            if branch in self.heads:
                return 422, {"message": "Reference already exists"}
            self.point(branch, payload["sha"])
            return 201, {"ref": payload["ref"]}
        match = re.fullmatch(r"/git/refs/heads/(.+)", path)
        if match and method == "PATCH":
            self.point(match.group(1), payload["sha"])
            return 200, {"object": {"sha": payload["sha"]}}
        match = re.fullmatch(r"/contents/(.+)", path)
        if match and method == "GET":
            text = self.branches.get(query["ref"], {}).get(match.group(1))
            if text is None:
                return 404, {"message": "Not Found"}
            return 200, {"sha": blob(text), "encoding": "base64", "content": base64.b64encode(text.encode()).decode()}
        if match and method == "PUT":
            branch, name = payload["branch"], match.group(1)
            current = self.branches[branch].get(name)
            if (current is not None) != ("sha" in payload) or (current is not None and payload["sha"] != blob(current)):
                return 409, {"message": "sha does not match"}
            sha = self.commit(branch, name, base64.b64decode(payload["content"]).decode())
            return 200 if current is not None else 201, {"commit": {"sha": sha}}
        if path == "/commits" and method == "GET":
            touching = [entry for entry in self.history.get(query["sha"], []) if entry[1] == query["path"]]
            return 200, [{"sha": sha, "author": author} for sha, _, author in reversed(touching)][:1]
        match = re.fullmatch(r"/statuses/([0-9a-f]{40})", path)
        if match and method == "POST":
            self.statuses.append(dict(payload, sha=match.group(1)))
            return 201, payload
        raise AssertionError(f"the fake GitHub does not know {method} {path}")

    def point(self, branch, sha):
        source = next(name for name, head in self.heads.items() if head == sha)
        self.branches[branch] = dict(self.branches[source])
        self.heads[branch] = sha
        self.history[branch] = []


def blob(text):
    return hashlib.sha1(text.encode()).hexdigest()
