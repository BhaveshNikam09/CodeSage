from engine.analyzer import StaticAnalyzer
from engine.ai_analysis import AIAnalysisEngine
import re

class ReviewEngine:
    """
    Central orchestration engine.
    Combines static analysis and AI-based suggestions.
    """

    def __init__(self):
        self.static_analyzer = StaticAnalyzer()
        self.ai_analyzer = AIAnalysisEngine()

    def review(self, code: str, filename: str = "code.py") -> dict:
        # Step 1: Static analysis
        results = self.static_analyzer.analyze(code)
        results["issues"] = self._clean_static_issues(results.get("issues", []))
        self._attach_safe_static_fixes(code, results["issues"])

        # Step 2: Context-aware AI suggestions
        ai_results = self.ai_analyzer.analyze(code, results, filename)
        results["ai"] = ai_results
        results["suggestions"] = ai_results["suggestions"]

        for suggestion in ai_results["suggestions"]:
            if self._is_duplicate_issue(results["issues"], suggestion):
                continue
            results["issues"].append({
                "id": suggestion["id"],
                "line": suggestion["line"],
                "column": suggestion["column"],
                "severity": suggestion["severity"],
                "message": suggestion["message"],
                "fix": suggestion["fix"],
                "type": suggestion["category"],
                "source": "ai",
                "explanation": suggestion["explanation"],
                "fix_edit": suggestion["fix_edit"],
                "code_snippet": suggestion.get("code_snippet", "")
            })

        results["statistics"] = self.static_analyzer._calculate_stats(code, results["issues"])
        results["summary"] = self.static_analyzer._generate_summary(results)

        return results

    def _clean_static_issues(self, issues):
        cleaned = []
        seen = set()
        undefined_by_line = {}

        for issue in issues:
            message = issue.get("message", "")
            line = issue.get("line", 0)

            if self._is_low_value_typo(issue):
                continue

            if message.startswith("Undefined variable"):
                count = undefined_by_line.get(line, 0)
                if count >= 2:
                    continue
                undefined_by_line[line] = count + 1

            key = (line, issue.get("type", ""), self._normalize_message(message))
            if key in seen:
                continue
            seen.add(key)
            cleaned.append(issue)

        return cleaned

    def _is_duplicate_issue(self, issues, suggestion):
        suggestion_text = self._normalize_message(suggestion.get("message", ""))
        suggestion_fix = self._normalize_message(suggestion.get("fix", ""))

        for issue in issues:
            if issue.get("line") != suggestion.get("line"):
                continue

            issue_text = self._normalize_message(issue.get("message", ""))
            issue_fix = self._normalize_message(issue.get("fix", ""))
            if issue_text and (issue_text in suggestion_text or suggestion_text in issue_text):
                return True
            if issue_fix and suggestion_fix and (issue_fix in suggestion_fix or suggestion_fix in issue_fix):
                return True

        return False

    def _is_low_value_typo(self, issue):
        message = issue.get("message", "").lower()
        snippet = issue.get("code_snippet", "")

        if "variable name too short" in message:
            return True

        if "possibly typo" in message and len(snippet) <= 3:
            return True

        return False

    def _normalize_message(self, message):
        return re.sub(r"\s+", " ", str(message).lower()).strip()

    def _attach_safe_static_fixes(self, code, issues):
        lines = code.splitlines()

        for issue in issues:
            if issue.get("fix_edit"):
                continue

            line_no = issue.get("line", 0)
            if line_no <= 0 or line_no > len(lines):
                issue["fix_edit"] = None
                issue["explanation"] = issue.get("fix", issue.get("message", ""))
                continue

            original = lines[line_no - 1]
            edit = self._build_static_fix_edit(issue, original, line_no)
            issue["fix_edit"] = edit
            issue["source"] = issue.get("source", "static")
            issue["explanation"] = self._explain_static_issue(issue)

    def _build_static_fix_edit(self, issue, original, line_no):
        message = issue.get("message", "")
        fix = issue.get("fix", "")

        if message == "Hardcoded API key":
            return self._secret_edit(original, line_no, "API_KEY")

        if message == "Hardcoded password":
            return self._secret_edit(original, line_no, "PASSWORD")

        if message == "Hardcoded secret":
            return self._secret_edit(original, line_no, "SECRET")

        if "Arbitrary code execution risk" in message and "eval(" in original:
            replacement = re.sub(r"\beval\s*\(", "ast.literal_eval(", original)
            return self._edit(line_no, original, replacement, "import ast")

        if "Bare except clause" in message and re.search(r"\bexcept\s*:", original):
            replacement = re.sub(r"\bexcept\s*:", "except Exception:", original)
            return self._edit(line_no, original, replacement)

        typo_match = re.search(r'Change "([^"]+)" to "([^"]+)"', fix)
        if typo_match:
            old_name, new_name = typo_match.groups()
            replacement = re.sub(rf"\b{re.escape(old_name)}\b", new_name, original)
            if replacement != original:
                return self._edit(line_no, original, replacement)

        return None

    def _secret_edit(self, original, line_no, env_name):
        if not re.search(r"=\s*['\"][^'\"]+['\"]", original):
            return None

        replacement = re.sub(r"=\s*['\"][^'\"]+['\"]", f'= os.getenv("{env_name}", "")', original)
        return self._edit(line_no, original, replacement, "import os")

    def _edit(self, line_no, original, replacement, additional_import=None):
        if replacement == original:
            return None

        return {
            "start_line": line_no,
            "end_line": line_no,
            "original": original,
            "replacement": replacement,
            "additional_import": additional_import,
        }

    def _explain_static_issue(self, issue):
        message = issue.get("message", "")

        if message == "Hardcoded API key":
            return "This line embeds a credential in source code. Accept Fix replaces the literal value with os.getenv(\"API_KEY\", \"\") and adds import os when needed."

        if message == "Hardcoded password":
            return "This line embeds a password in source code. Accept Fix replaces the literal value with os.getenv(\"PASSWORD\", \"\") and adds import os when needed."

        if message == "Hardcoded secret":
            return "This line embeds a secret in source code. Accept Fix replaces the literal value with os.getenv(\"SECRET\", \"\") and adds import os when needed."

        if "Arbitrary code execution risk" in message:
            return "eval can execute arbitrary Python. Accept Fix replaces eval(...) with ast.literal_eval(...) and adds import ast when needed."

        if "Bare except clause" in message:
            return "Bare except catches too much and hides failures. Accept Fix narrows it to except Exception."

        if message.startswith("Undefined variable") and issue.get("fix_edit"):
            return f"{issue.get('fix', message)}. Accept Fix replaces the misspelled identifier on this exact line."

        return issue.get("fix", message)

    def _extract_functions(self, code: str):
        import ast

        functions = []
        lines = code.split("\n")

        try:
            tree = ast.parse(code)

            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    start = node.lineno - 1
                    end = getattr(node, "end_lineno", start + 10)
                    functions.append({
                        "name": node.name,
                        "code": "\n".join(lines[start:end]),
                        "lineno": node.lineno
                    })
        except:
            pass

        return functions
