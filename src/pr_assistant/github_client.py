import json
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Dict, List, Optional


class GitHubClient:
    """Small GitHub REST client for PR review automation."""

    def __init__(self, token: Optional[str] = None, api_base: Optional[str] = None):
        self.token = token or os.getenv("CODESAGE_GITHUB_TOKEN")
        self.api_base = (api_base or os.getenv("CODESAGE_GITHUB_API_BASE") or "https://api.github.com").rstrip("/")

    @property
    def configured(self) -> bool:
        return bool(self.token)

    def get_pull_request(self, owner: str, repo: str, pull_number: int) -> Dict:
        return self._request("GET", f"/repos/{owner}/{repo}/pulls/{pull_number}")

    def list_pull_files(self, owner: str, repo: str, pull_number: int) -> List[Dict]:
        return self._paginated("GET", f"/repos/{owner}/{repo}/pulls/{pull_number}/files")

    def get_file_content(self, owner: str, repo: str, path: str, ref: str) -> str:
        encoded_path = "/".join(urllib.parse.quote(part) for part in path.split("/"))
        payload = self._request("GET", f"/repos/{owner}/{repo}/contents/{encoded_path}?ref={urllib.parse.quote(ref)}")
        if payload.get("encoding") != "base64":
            return ""

        import base64

        raw = payload.get("content", "")
        return base64.b64decode(raw).decode("utf-8", errors="replace")

    def post_inline_comment(
        self,
        owner: str,
        repo: str,
        pull_number: int,
        commit_id: str,
        path: str,
        line: int,
        body: str,
        side: str = "RIGHT",
    ) -> Dict:
        return self._request("POST", f"/repos/{owner}/{repo}/pulls/{pull_number}/comments", {
            "body": body,
            "commit_id": commit_id,
            "path": path,
            "line": line,
            "side": side,
        })

    def post_general_comment(self, owner: str, repo: str, issue_number: int, body: str) -> Dict:
        return self._request("POST", f"/repos/{owner}/{repo}/issues/{issue_number}/comments", {
            "body": body,
        })

    def _paginated(self, method: str, path: str) -> List[Dict]:
        page = 1
        items = []
        while True:
            separator = "&" if "?" in path else "?"
            chunk = self._request(method, f"{path}{separator}per_page=100&page={page}")
            if not chunk:
                break
            items.extend(chunk)
            if len(chunk) < 100:
                break
            page += 1
        return items

    def _request(self, method: str, path: str, payload: Optional[Dict] = None):
        if not self.token:
            raise GitHubClientError("CODESAGE_GITHUB_TOKEN is not configured")

        body = None if payload is None else json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            f"{self.api_base}{path}",
            data=body,
            method=method,
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json",
                "User-Agent": "CodeSage-AI-PR-Assistant",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )

        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                data = response.read().decode("utf-8")
                return json.loads(data) if data else {}
        except urllib.error.HTTPError as error:
            details = error.read().decode("utf-8", errors="replace")
            raise GitHubClientError(f"GitHub API returned {error.code}: {details}") from error
        except urllib.error.URLError as error:
            raise GitHubClientError(f"GitHub API request failed: {error.reason}") from error


class GitHubClientError(RuntimeError):
    pass
