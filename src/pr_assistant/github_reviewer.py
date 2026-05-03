from typing import Dict, List, Optional

from engine.engine import ReviewEngine
from pr_assistant.diff_mapper import build_reviewable_files, nearest_diff_line
from pr_assistant.github_client import GitHubClient
from pr_assistant.reviewer import PRReviewBuilder


class GitHubPRReviewer:
    """Fetch, review, and optionally comment on GitHub pull requests."""

    def __init__(
        self,
        client: Optional[GitHubClient] = None,
        engine: Optional[ReviewEngine] = None,
        review_builder: Optional[PRReviewBuilder] = None,
    ):
        self.client = client or GitHubClient()
        self.engine = engine or ReviewEngine()
        self.review_builder = review_builder or PRReviewBuilder()

    def review_pull_request(
        self,
        owner: str,
        repo: str,
        pull_number: int,
        post_comments: bool = False,
        max_inline_comments: int = 20,
    ) -> Dict:
        pr = self.client.get_pull_request(owner, repo, pull_number)
        files = self.client.list_pull_files(owner, repo, pull_number)
        commit_id = pr.get("head", {}).get("sha", "")
        contents = self._fetch_contents(owner, repo, files, commit_id)
        reviewable_files = build_reviewable_files(files, contents)

        file_reviews = []
        inline_comments = []
        final_code = {}

        for file_payload in reviewable_files:
            filename = file_payload["filename"]
            analysis = self.engine.review(file_payload["content"], filename)
            review = self.review_builder.build(analysis, filename, file_payload["content"])
            self._attach_github_metadata(review, file_payload, commit_id)
            file_reviews.append(review)
            final_code[filename] = review["final_improved_code"]
            inline_comments.extend(review["inline_comments"])

        inline_comments = self._prioritize_postable_comments(inline_comments, max_inline_comments)
        summary = self._summary(file_reviews, inline_comments)
        general_body = self._general_comment_body(summary, file_reviews)
        posted = {"inline": [], "general": None}

        if post_comments:
            posted = self._post_comments(owner, repo, pull_number, commit_id, inline_comments, general_body)

        return {
            "repository": f"{owner}/{repo}",
            "pull_number": pull_number,
            "commit_id": commit_id,
            "pr_title": pr.get("title", ""),
            "pr_url": pr.get("html_url", ""),
            "status": "changes_requested" if inline_comments else "approved",
            "summary_of_issues": summary,
            "file_wise_review": file_reviews,
            "inline_comments": inline_comments,
            "diff_suggestions": [comment.get("github_suggestion") for comment in inline_comments if comment.get("github_suggestion")],
            "final_improved_code": final_code,
            "posted": posted,
            "automation": {
                "trigger": "manual_or_webhook",
                "post_comments": post_comments,
                "max_inline_comments": max_inline_comments,
            },
        }

    def _fetch_contents(self, owner: str, repo: str, files: List[Dict], ref: str) -> Dict[str, str]:
        contents = {}
        for file_info in files:
            filename = file_info.get("filename", "")
            if not filename or file_info.get("status") == "removed":
                continue
            try:
                contents[filename] = self.client.get_file_content(owner, repo, filename, ref)
            except Exception:
                contents[filename] = ""
        return contents

    def _attach_github_metadata(self, review: Dict, file_payload: Dict, commit_id: str) -> None:
        filename = file_payload["filename"]
        mapping = file_payload["line_mapping"]

        for comment in review["inline_comments"]:
            mapped = nearest_diff_line(comment["line"], mapping)
            comment["file"] = filename
            comment["github"] = {
                "path": filename,
                "commit_id": commit_id,
                "line": mapped["line"] if mapped else comment["line"],
                "side": mapped["side"] if mapped else "RIGHT",
                "position": mapped.get("position") if mapped else None,
                "postable": bool(mapped),
            }
            comment["github_body"] = self._inline_comment_body(comment)
            comment["github_suggestion"] = self._github_suggestion(comment)

    def _inline_comment_body(self, comment: Dict) -> str:
        body = [
            f"**CodeSage AI Review**: {comment['review_comment']}",
            "",
            f"Severity: `{comment['severity']}` | Category: `{comment['category']}`",
        ]
        suggestion = self._github_suggestion(comment)
        if suggestion:
            body.extend(["", suggestion])
        elif comment.get("suggestion"):
            body.extend(["", f"Suggested action: {comment['suggestion']}"])
        return "\n".join(body)

    def _github_suggestion(self, comment: Dict) -> Optional[str]:
        new_code = comment.get("new_code")
        if not new_code:
            return None
        return f"```suggestion\n{new_code}\n```"

    def _prioritize_postable_comments(self, comments: List[Dict], limit: int) -> List[Dict]:
        severity_rank = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        postable = [comment for comment in comments if comment.get("github", {}).get("postable")]
        postable.sort(key=lambda item: (severity_rank.get(item.get("severity", "medium"), 2), item["file"], item["line"]))
        return postable[:limit]

    def _summary(self, file_reviews: List[Dict], inline_comments: List[Dict]) -> Dict:
        categories = {}
        for comment in inline_comments:
            categories[comment["category"]] = categories.get(comment["category"], 0) + 1
        return {
            "total_files_reviewed": len(file_reviews),
            "total_inline_comments": len(inline_comments),
            "categories": categories,
            "files": [{
                "file": review["file"],
                "issues": len(review["inline_comments"]),
                "auto_apply_ready": sum(1 for item in review["inline_comments"] if item.get("fix_edit")),
            } for review in file_reviews],
        }

    def _general_comment_body(self, summary: Dict, file_reviews: List[Dict]) -> str:
        lines = [
            "## CodeSage AI PR Review",
            "",
            "### Summary of issues",
            f"- Files reviewed: {summary['total_files_reviewed']}",
            f"- Inline comments prepared: {summary['total_inline_comments']}",
        ]
        if summary["categories"]:
            lines.append(f"- Categories: {', '.join(f'{name}: {count}' for name, count in summary['categories'].items())}")
        lines.extend(["", "### File-wise review"])
        for file_summary in summary["files"]:
            lines.append(f"- `{file_summary['file']}`: {file_summary['issues']} issue(s), {file_summary['auto_apply_ready']} suggestion(s)")
        lines.extend(["", "### Diff suggestions"])
        for review in file_reviews:
            for suggestion in review["diff_suggestions"][:5]:
                lines.append(f"- `{suggestion['file']}` lines {suggestion['lines']}: {', '.join(suggestion['changes'][:2])}")
        return "\n".join(lines)

    def _post_comments(
        self,
        owner: str,
        repo: str,
        pull_number: int,
        commit_id: str,
        inline_comments: List[Dict],
        general_body: str,
    ) -> Dict:
        posted = {"inline": [], "general": None}
        posted["general"] = self.client.post_general_comment(owner, repo, pull_number, general_body)
        for comment in inline_comments:
            github = comment["github"]
            posted["inline"].append(self.client.post_inline_comment(
                owner,
                repo,
                pull_number,
                commit_id,
                github["path"],
                github["line"],
                comment["github_body"],
                github["side"],
            ))
        return posted
