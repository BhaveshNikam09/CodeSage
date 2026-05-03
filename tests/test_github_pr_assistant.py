import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SRC = os.path.join(ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from pr_assistant.diff_mapper import map_patch_lines, nearest_diff_line
from pr_assistant.github_reviewer import GitHubPRReviewer


class FakeGitHubClient:
    def __init__(self):
        self.inline_comments = []
        self.general_comments = []

    def get_pull_request(self, owner, repo, pull_number):
        return {
            "title": "Test PR",
            "html_url": "https://github.example/pr/1",
            "head": {"sha": "abc123"},
        }

    def list_pull_files(self, owner, repo, pull_number):
        return [{
            "filename": "sample.py",
            "status": "modified",
            "patch": "@@ -1,2 +1,2 @@\n api_key = 'abc123'\n-value = raw\n+value = eval(raw)",
        }]

    def get_file_content(self, owner, repo, path, ref):
        return "api_key = 'abc123'\nvalue = eval(raw)\n"

    def post_general_comment(self, owner, repo, issue_number, body):
        self.general_comments.append(body)
        return {"id": 1, "body": body}

    def post_inline_comment(self, owner, repo, pull_number, commit_id, path, line, body, side="RIGHT"):
        payload = {
            "commit_id": commit_id,
            "path": path,
            "line": line,
            "body": body,
            "side": side,
        }
        self.inline_comments.append(payload)
        return payload


def test_patch_line_mapping_tracks_new_lines_and_positions():
    patch = "@@ -10,3 +10,4 @@\n keep\n-old\n+new\n+extra\n context"

    mapping = map_patch_lines(patch)

    assert mapping[11]["change"] == "added"
    assert mapping[11]["position"] == 3
    assert mapping[12]["change"] == "added"
    assert nearest_diff_line(13, mapping)["line"] == 13


def test_github_reviewer_builds_suggestion_blocks_and_comment_metadata():
    client = FakeGitHubClient()
    reviewer = GitHubPRReviewer(client=client)

    review = reviewer.review_pull_request("octo", "repo", 1, post_comments=True)

    assert review["repository"] == "octo/repo"
    assert review["commit_id"] == "abc123"
    assert review["summary_of_issues"]["total_files_reviewed"] == 1
    assert client.general_comments
    assert client.inline_comments
    assert client.inline_comments[0]["commit_id"] == "abc123"
    assert client.inline_comments[0]["path"] == "sample.py"
    assert "```suggestion" in client.inline_comments[0]["body"]
    assert review["diff_suggestions"]
    assert "sample.py" in review["final_improved_code"]
