from datetime import datetime
from typing import Dict, List, Optional, Tuple


class PRReviewBuilder:
    """Build GitHub-style review output from normalized analysis results."""

    SUMMARY_BUCKETS = ("bugs", "security", "performance", "readability", "code_smell", "improvements")
    COMMIT_SCOPES = {
        "bugs": "fix",
        "security": "fix",
        "performance": "perf",
        "readability": "refactor",
        "code_smell": "refactor",
        "improvements": "chore",
    }

    def build(
        self,
        analysis: Dict,
        filename: str = "code.py",
        code: str = "",
        feedback: Optional[Dict] = None,
    ) -> Dict:
        issues = self._prioritized_issues(analysis.get("issues", []), feedback or {})
        lines = code.splitlines()
        comments = [self._comment(issue, filename, lines) for issue in issues]
        final_code, applied_change_ids = self._apply_safe_edits(code, comments)
        diff_suggestions = [self._diff_suggestion(comment) for comment in comments]
        summary = self._summary(comments)
        file_changes = self._file_wise_changes(filename, comments)
        pr_title = self._pr_title(comments)
        pr_description = self._pr_description(summary, comments)
        commit_messages = self._commit_messages(comments)

        review = {
            "created_at": datetime.utcnow().isoformat() + "Z",
            "file": filename,
            "status": "changes_requested" if comments else "approved",
            "pr_title": pr_title,
            "pr_description": pr_description,
            "commit_messages": commit_messages,
            "summary_of_issues": self._summary_of_issues(comments),
            "detailed_pr_review": self._detailed_review(comments),
            "file_wise_changes": file_changes,
            "diff_suggestions": diff_suggestions,
            "final_improved_code": final_code,
            "overwrite_mode": {
                "supported": bool(applied_change_ids),
                "applied_suggestion_ids": applied_change_ids,
                "mode": "overwrite",
                "safety": "Only non-overlapping safe fix_edit replacements are included in final_improved_code.",
            },
            "inline_comments": comments,
            "suggested_changes": diff_suggestions,
            "summary": summary,
            "learning": self._learning_summary(feedback or {}),
        }
        review["markdown_review"] = self._markdown_review(review)
        return review

    def _prioritized_issues(self, issues: List[Dict], feedback: Dict) -> List[Dict]:
        severity_rank = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        accepted = set(feedback.get("accepted", []))
        rejected = set(feedback.get("rejected", []))

        def score(issue: Dict) -> Tuple[int, int, int]:
            issue_id = issue.get("id", "")
            feedback_rank = -1 if issue_id in accepted else 1 if issue_id in rejected else 0
            return (
                feedback_rank,
                severity_rank.get(issue.get("severity", "medium"), 2),
                issue.get("line", 0),
            )

        return sorted(issues, key=score)

    def _comment(self, issue: Dict, filename: str, lines: List[str]) -> Dict:
        category = self._category(issue)
        fix_edit = issue.get("fix_edit")
        start_line = self._line_number(fix_edit.get("start_line") if fix_edit else issue.get("line"), 1)
        end_line = self._line_number(fix_edit.get("end_line") if fix_edit else issue.get("end_line", start_line), start_line)
        old_code = self._old_code(issue, fix_edit, lines, start_line, end_line)
        new_code = self._new_code(fix_edit)
        change_notes = self._change_notes(issue, category, old_code, new_code)

        return {
            "id": issue.get("id") or f"{filename}:{start_line}:{issue.get('message', '')}",
            "file": issue.get("file", filename),
            "line": start_line,
            "end_line": end_line,
            "lines": self._line_label(start_line, end_line),
            "severity": issue.get("severity", "medium"),
            "category": category,
            "message": issue.get("message", ""),
            "review_comment": self._human_comment(issue, category),
            "suggestion": issue.get("fix", ""),
            "explanation": issue.get("explanation", issue.get("message", "")),
            "old_code": old_code,
            "new_code": new_code,
            "changes": change_notes,
            "diff_hunk": self._diff_hunk(start_line, old_code, new_code),
            "fix_edit": fix_edit,
            "apply": {
                "mode": "overwrite",
                "ready": bool(fix_edit and new_code is not None),
                "start_line": start_line,
                "end_line": end_line,
                "replacement": new_code,
                "additional_import": fix_edit.get("additional_import") if fix_edit else None,
            },
            "status": issue.get("status", "open"),
            "source": issue.get("source", "static"),
            "confidence": issue.get("confidence", 0),
        }

    def _summary(self, comments: List[Dict]) -> Dict:
        summary = {bucket: [] for bucket in self.SUMMARY_BUCKETS}
        for comment in comments:
            bucket = comment["category"] if comment["category"] in summary else "improvements"
            summary[bucket].append({
                "line": comment["line"],
                "lines": comment["lines"],
                "message": comment["message"],
                "severity": comment["severity"],
                "auto_apply": comment["apply"]["ready"],
            })
        return summary

    def _summary_of_issues(self, comments: List[Dict]) -> List[Dict]:
        return [{
            "file": comment["file"],
            "lines": comment["lines"],
            "severity": comment["severity"],
            "category": comment["category"],
            "issue": comment["message"],
            "review_comment": comment["review_comment"],
        } for comment in comments]

    def _detailed_review(self, comments: List[Dict]) -> List[Dict]:
        return [{
            "file": comment["file"],
            "lines": comment["lines"],
            "comment": comment["review_comment"],
            "why_it_matters": comment["explanation"],
            "suggested_action": comment["suggestion"],
            "auto_apply_ready": comment["apply"]["ready"],
        } for comment in comments]

    def _file_wise_changes(self, filename: str, comments: List[Dict]) -> List[Dict]:
        return [{
            "file": filename,
            "total_comments": len(comments),
            "auto_apply_ready": sum(1 for comment in comments if comment["apply"]["ready"]),
            "changes": [{
                "lines": comment["lines"],
                "category": comment["category"],
                "message": comment["message"],
                "status": "ready_to_apply" if comment["apply"]["ready"] else "manual_review",
            } for comment in comments],
        }]

    def _diff_suggestion(self, comment: Dict) -> Dict:
        return {
            "file": comment["file"],
            "lines": comment["lines"],
            "old_code": comment["old_code"],
            "new_code": comment["new_code"],
            "diff_hunk": comment["diff_hunk"],
            "changes": comment["changes"],
            "apply": comment["apply"],
        }

    def _apply_safe_edits(self, code: str, comments: List[Dict]) -> Tuple[str, List[str]]:
        if not code:
            return "", []

        lines = code.splitlines()
        newline = "\n"
        safe_comments = [
            comment for comment in comments
            if comment["apply"]["ready"] and self._valid_edit_range(comment, len(lines))
        ]
        safe_comments.sort(key=lambda item: item["line"], reverse=True)

        occupied = set()
        applied_ids = []
        for comment in safe_comments:
            edit_range = set(range(comment["line"], comment["end_line"] + 1))
            if occupied.intersection(edit_range):
                continue
            occupied.update(edit_range)

            replacement_lines = str(comment["new_code"]).splitlines()
            start = comment["line"] - 1
            end = comment["end_line"] - 1
            lines[start:end + 1] = replacement_lines
            applied_ids.append(comment["id"])

        imports = [
            comment["apply"]["additional_import"]
            for comment in comments
            if comment["id"] in applied_ids and comment["apply"].get("additional_import")
        ]
        for import_line in reversed(list(dict.fromkeys(imports))):
            if import_line and not any(line.strip() == import_line.strip() for line in lines):
                lines.insert(0, import_line)

        final_code = newline.join(lines)
        if code.endswith(("\n", "\r\n")):
            final_code += newline
        return final_code, list(reversed(applied_ids))

    def _valid_edit_range(self, comment: Dict, total_lines: int) -> bool:
        return 1 <= comment["line"] <= comment["end_line"] <= total_lines

    def _pr_title(self, comments: List[Dict]) -> str:
        if not comments:
            return "chore: approve clean CodeSage review"
        top = comments[0]
        scope = self.COMMIT_SCOPES.get(top["category"], "fix")
        return f"{scope}: address {top['category']} issue in review"

    def _pr_description(self, summary: Dict, comments: List[Dict]) -> str:
        total = len(comments)
        fixable = sum(1 for comment in comments if comment["apply"]["ready"])
        if not total:
            return "CodeSage found no blocking review issues."
        categories = ", ".join(f"{name}: {len(items)}" for name, items in summary.items() if items)
        return f"CodeSage reviewed this change as a PR and found {total} issue(s), with {fixable} overwrite-ready fix(es). Categories: {categories}."

    def _commit_messages(self, comments: List[Dict]) -> List[str]:
        messages = []
        seen = set()
        for comment in comments:
            scope = self.COMMIT_SCOPES.get(comment["category"], "fix")
            message = f"{scope}: {self._commit_subject(comment)}"
            if message not in seen:
                seen.add(message)
                messages.append(message)
        return messages or ["chore: no review changes required"]

    def _commit_subject(self, comment: Dict) -> str:
        text = comment["message"].lower().rstrip(".")
        replacements = {
            "arbitrary code execution risk": "replace unsafe eval usage",
            "hardcoded api key": "move api key to environment",
            "hardcoded password": "move password to environment",
            "bare except clause": "narrow broad exception handling",
            "inefficient iteration pattern": "improve iteration logic",
        }
        return replacements.get(text, text[:72])

    def _learning_summary(self, feedback: Dict) -> Dict:
        accepted = feedback.get("accepted", [])
        rejected = feedback.get("rejected", [])
        return {
            "enabled": True,
            "accepted_count": len(accepted),
            "rejected_count": len(rejected),
            "strategy": "Pattern weights are simulated from accepted/rejected suggestion IDs for fast local inference.",
        }

    def _markdown_review(self, review: Dict) -> str:
        return "\n".join([
            "## Summary of Issues",
            self._markdown_summary(review["summary_of_issues"]),
            "",
            "## Detailed PR Review",
            self._markdown_detailed(review["detailed_pr_review"]),
            "",
            "## File-wise Changes",
            self._markdown_file_changes(review["file_wise_changes"]),
            "",
            "## Diff Suggestions",
            self._markdown_diffs(review["diff_suggestions"]),
            "",
            "## Final Improved Code",
            "```",
            review["final_improved_code"],
            "```",
        ])

    def _markdown_summary(self, issues: List[Dict]) -> str:
        if not issues:
            return "- No blocking issues found."
        return "\n".join(
            f"- [{issue['severity']}] {issue['file']}:{issue['lines']} - {issue['issue']}"
            for issue in issues
        )

    def _markdown_detailed(self, details: List[Dict]) -> str:
        if not details:
            return "- Approved. No inline comments required."
        return "\n".join(
            f"- {item['file']}:{item['lines']} - {item['comment']} Suggested action: {item['suggested_action']}"
            for item in details
        )

    def _markdown_file_changes(self, file_changes: List[Dict]) -> str:
        blocks = []
        for file_change in file_changes:
            blocks.append(f"- FILE: {file_change['file']}")
            blocks.append(f"  Total comments: {file_change['total_comments']}")
            blocks.append(f"  Auto-apply ready: {file_change['auto_apply_ready']}")
        return "\n".join(blocks)

    def _markdown_diffs(self, suggestions: List[Dict]) -> str:
        if not suggestions:
            return "- No diffs required."

        blocks = []
        for suggestion in suggestions:
            blocks.extend([
                f"FILE: {suggestion['file']}",
                f"LINES: {suggestion['lines']}",
                "",
                "OLD CODE:",
                "```",
                suggestion["old_code"] or "",
                "```",
                "",
                "NEW CODE:",
                "```",
                suggestion["new_code"] or "Manual review required. No safe overwrite patch was generated.",
                "```",
                "",
                "CHANGES:",
                *[f"- {change}" for change in suggestion["changes"]],
                "",
            ])
        return "\n".join(blocks).rstrip()

    def _category(self, issue: Dict) -> str:
        issue_type = issue.get("type") or issue.get("category") or "improvements"
        if issue_type in ("bug", "bugs", "syntax"):
            return "bugs"
        if issue_type in ("quality", "readability"):
            return "readability"
        if issue_type in ("security", "performance", "code_smell"):
            return issue_type
        return "improvements" if issue_type == "ai" else issue_type

    def _line_number(self, value, fallback: int) -> int:
        try:
            number = int(value)
            return number if number > 0 else fallback
        except (TypeError, ValueError):
            return fallback

    def _line_label(self, start_line: int, end_line: int) -> str:
        return str(start_line) if start_line == end_line else f"{start_line}-{end_line}"

    def _old_code(self, issue: Dict, fix_edit: Optional[Dict], lines: List[str], start_line: int, end_line: int) -> str:
        if fix_edit and fix_edit.get("original") is not None:
            return str(fix_edit["original"])
        if lines and 1 <= start_line <= end_line <= len(lines):
            return "\n".join(lines[start_line - 1:end_line])
        return issue.get("code_snippet", "")

    def _new_code(self, fix_edit: Optional[Dict]) -> Optional[str]:
        if not fix_edit:
            return None
        replacement = fix_edit.get("replacement")
        return None if replacement is None else str(replacement)

    def _change_notes(self, issue: Dict, category: str, old_code: str, new_code: Optional[str]) -> List[str]:
        old_count = len(old_code.splitlines()) if old_code else 0
        new_count = len(new_code.splitlines()) if new_code else 0
        notes = [f"Replaced {old_count} line(s) with {new_count} line(s)." if new_code is not None else "Manual review required; no safe overwrite patch generated."]
        if category == "performance":
            notes.append("Reviewed for unnecessary repeated work and scaling risk.")
        if category == "security":
            notes.append("Reduced exposure to injection, leaked secrets, or unsafe execution.")
        if category == "bugs":
            notes.append("Tightened behavior around an edge case or runtime failure.")
        if issue.get("fix"):
            notes.append(issue["fix"])
        return notes

    def _diff_hunk(self, start_line: int, old_code: str, new_code: Optional[str]) -> str:
        old_lines = old_code.splitlines() or [""]
        new_lines = (new_code.splitlines() if new_code is not None else ["Manual review required."])
        body = [f"@@ -{start_line},{len(old_lines)} +{start_line},{len(new_lines)} @@"]
        body.extend(f"-{line}" for line in old_lines)
        body.extend(f"+{line}" for line in new_lines)
        return "\n".join(body)

    def _human_comment(self, issue: Dict, category: str) -> str:
        message = issue.get("message", "This needs review")
        templates = {
            "security": f"This is risky in production: {message}. Please replace it with the suggested safer pattern before merging.",
            "bugs": f"This can fail at runtime: {message}. The edge case should be handled explicitly.",
            "performance": f"This may scale poorly: {message}. Consider the suggested change so larger inputs do not degrade.",
            "readability": f"This makes the code harder to maintain: {message}. Tightening it will make future changes safer.",
            "code_smell": f"This is a code smell: {message}. I would simplify it before this PR lands.",
        }
        return templates.get(category, f"This needs a concrete follow-up: {message}.")
