import ast
import hashlib
import re
from typing import Dict, List, Optional, Set, Tuple

from engine.suggester import AISuggester


class AIAnalysisEngine:
    """
    Context-aware AI analysis layer.
    Keeps generated fixes structured so clients can apply one safe edit at a time.
    """

    def __init__(self):
        self.suggester = AISuggester()

    def analyze(self, code: str, static_results: Optional[Dict] = None, filename: str = "code.py") -> Dict:
        lines = code.splitlines()
        static_fingerprints = self._static_fingerprints(static_results or {})
        suggestions = self._contextual_rules(code, lines, filename, static_fingerprints)
        suggestions.extend(self._model_suggestions(code, filename))

        normalized = []
        seen = set()
        for suggestion in suggestions:
            if suggestion["confidence"] < 0.72:
                continue
            key = (suggestion["line"], suggestion["category"], self._normalize_message(suggestion["message"]))
            if key in seen:
                continue
            seen.add(key)
            normalized.append(self._with_id(suggestion, code, filename))

        return {
            "available": True,
            "model_available": self.suggester.available,
            "suggestions": normalized,
            "summary": self._summary(normalized),
        }

    def _contextual_rules(
        self,
        code: str,
        lines: List[str],
        filename: str,
        static_fingerprints: Set[Tuple[int, str]],
    ) -> List[Dict]:
        suggestions = []

        for idx, line in enumerate(lines, start=1):
            stripped = line.strip()
            indent = line[: len(line) - len(line.lstrip())]

            if "os.system(" in stripped and not self._covered(idx, "command injection", static_fingerprints):
                suggestions.append(self._suggestion(
                    filename,
                    idx,
                    "security",
                    "critical",
                    "Avoid shell command execution with os.system.",
                    "os.system executes through the shell and can turn user-controlled values into command injection.",
                    "Use subprocess.run with argument lists and shell=False.",
                    None,
                    0.93,
                ))

            if re.search(r"\beval\s*\(", stripped) and not self._covered(idx, "arbitrary code execution", static_fingerprints):
                replacement = re.sub(r"\beval\s*\(", "ast.literal_eval(", line)
                suggestions.append(self._suggestion(
                    filename,
                    idx,
                    "security",
                    "critical",
                    "Replace eval with ast.literal_eval for data parsing.",
                    "eval can execute arbitrary Python. literal_eval only parses Python literals such as strings, numbers, lists, and dicts.",
                    "Replace eval(...) with ast.literal_eval(...), then ensure ast is imported.",
                    self._edit(idx, idx, line, replacement, additional_import="import ast"),
                    0.95,
                ))

            if re.search(r"password\s*=\s*['\"][^'\"]+['\"]", stripped, re.IGNORECASE) and not self._covered(idx, "hardcoded password", static_fingerprints):
                replacement = re.sub(r"=\s*['\"][^'\"]+['\"]", '= os.getenv("PASSWORD", "")', line)
                suggestions.append(self._suggestion(
                    filename,
                    idx,
                    "security",
                    "critical",
                    "Move hardcoded password into configuration.",
                    "Secrets committed in source code can leak through git history, logs, or screenshots.",
                    "Read the password from an environment variable.",
                    self._edit(idx, idx, line, replacement, additional_import="import os"),
                    0.9,
                ))

            if "range(len(" in stripped and not self._covered(idx, "inefficient iteration", static_fingerprints):
                suggestions.append(self._suggestion(
                    filename,
                    idx,
                    "performance",
                    "low",
                    "Loop uses index-based iteration where direct iteration is safer.",
                    "Index-driven loops make bounds and item access more fragile, and they often hide unnecessary repeated indexing.",
                    "Prefer direct iteration or enumerate when the index is also needed.",
                    None,
                    0.82,
                ))

            if re.match(r"except\s*:", stripped) and not self._covered(idx, "bare except", static_fingerprints):
                replacement = line.replace("except:", "except Exception:")
                suggestions.append(self._suggestion(
                    filename,
                    idx,
                    "readability",
                    "medium",
                    "Avoid bare except clauses.",
                    "Bare except catches system-exiting exceptions and hides unrelated failures.",
                    "Catch a specific exception type, or use except Exception as a temporary broad boundary.",
                    self._edit(idx, idx, line, replacement),
                    0.86,
                ))

        suggestions.extend(self._ast_context_rules(code, lines, filename, static_fingerprints))
        return suggestions

    def _ast_context_rules(
        self,
        code: str,
        lines: List[str],
        filename: str,
        static_fingerprints: Set[Tuple[int, str]],
    ) -> List[Dict]:
        suggestions = []
        try:
            tree = ast.parse(code)
        except SyntaxError:
            return suggestions

        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                for default in node.args.defaults:
                    if isinstance(default, (ast.List, ast.Dict, ast.Set)) and not self._covered(node.lineno, "mutable default", static_fingerprints):
                        line = lines[node.lineno - 1] if node.lineno - 1 < len(lines) else ""
                        suggestions.append(self._suggestion(
                            filename,
                            node.lineno,
                            "bugs",
                            "medium",
                            "Do not use mutable objects as default arguments.",
                            "Default arguments are created once when the function is defined, so later calls can share mutated state.",
                            "Use None as the default and initialize the list, dict, or set inside the function.",
                            None,
                            0.9,
                            line,
                        ))

            if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div) and not self._covered(node.lineno, "division", static_fingerprints):
                line = lines[node.lineno - 1] if node.lineno - 1 < len(lines) else ""
                suggestions.append(self._suggestion(
                    filename,
                    node.lineno,
                    "bugs",
                    "high",
                    "Validate the denominator before division.",
                    "This expression can raise ZeroDivisionError if the denominator reaches zero.",
                    "Check the denominator and handle the zero case before dividing.",
                    None,
                    0.78,
                    line,
                ))

            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "open" and not self._covered(node.lineno, "file", static_fingerprints):
                line = lines[node.lineno - 1] if node.lineno - 1 < len(lines) else ""
                suggestions.append(self._suggestion(
                    filename,
                    node.lineno,
                    "bugs",
                    "medium",
                    "Open files with a context manager.",
                    "A with block closes the file reliably even when reading or processing fails.",
                    "Use with open(...) as f around the file operation.",
                    None,
                    0.84,
                    line,
                ))

            if isinstance(node, ast.Call):
                suggestions.extend(self._call_suggestions(node, lines, filename, static_fingerprints))

            if isinstance(node, ast.ExceptHandler) and self._handler_swallows_exception(node):
                suggestions.append(self._suggestion(
                    filename,
                    node.lineno,
                    "bugs",
                    "medium",
                    "Exception handler silently swallows failures.",
                    "A handler that only passes or returns a fallback can hide broken behavior and make production failures difficult to diagnose.",
                    "Log the exception, narrow the handled exception type, or re-raise when recovery is not intentional.",
                    None,
                    0.86,
                    self._line(lines, node.lineno),
                ))

            if isinstance(node, (ast.For, ast.While)) and self._contains_nested_loop(node):
                suggestions.append(self._suggestion(
                    filename,
                    node.lineno,
                    "performance",
                    "medium",
                    "Nested loop may become expensive for larger inputs.",
                    "This loop contains another loop, which can turn simple list growth into quadratic work as input size increases.",
                    "Consider indexing data in a dictionary or set before the loop if the inner scan searches for matching values.",
                    None,
                    0.76,
                    self._line(lines, node.lineno),
                ))

            if isinstance(node, ast.If) and self._branches_are_duplicate(node):
                suggestions.append(self._suggestion(
                    filename,
                    node.lineno,
                    "code_smell",
                    "medium",
                    "Conditional branches contain duplicate logic.",
                    "When both branches perform the same work, the condition adds noise and can hide missing behavior.",
                    "Collapse the duplicated branch or move the shared logic outside the condition.",
                    None,
                    0.88,
                    self._line(lines, node.lineno),
                ))

            if isinstance(node, ast.Compare) and self._compares_to_bool_literal(node):
                suggestions.append(self._suggestion(
                    filename,
                    node.lineno,
                    "code_smell",
                    "low",
                    "Boolean comparison is redundant.",
                    "Comparing a boolean expression to True or False makes conditions harder to scan and can behave oddly with non-bool truthy values.",
                    "Use the expression directly, or use not expression for the false case.",
                    None,
                    0.74,
                    self._line(lines, node.lineno),
                ))

            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                suggestions.extend(self._unreachable_code_suggestions(node, lines, filename))

        return suggestions

    def _call_suggestions(
        self,
        node: ast.Call,
        lines: List[str],
        filename: str,
        static_fingerprints: Set[Tuple[int, str]],
    ) -> List[Dict]:
        suggestions = []
        call_name = self._call_name(node.func)
        line = self._line(lines, node.lineno)

        if (
            call_name in ("requests.get", "requests.post", "requests.put", "requests.patch", "requests.delete")
            and not self._has_keyword(node, "timeout")
            and not self._covered(node.lineno, "timeout", static_fingerprints)
        ):
            replacement = self._append_keyword_to_call_line(lines, node, "timeout=10")
            suggestions.append(self._suggestion(
                filename,
                node.lineno,
                "bugs",
                "medium",
                "HTTP request has no timeout.",
                "Without a timeout, a slow or stalled remote service can hang the worker indefinitely and exhaust request capacity.",
                "Pass an explicit timeout value to the requests call.",
                self._edit(node.lineno, node.lineno, lines[node.lineno - 1], replacement) if replacement else None,
                0.88,
                line,
            ))

        if (
            call_name == "yaml.load"
            and not self._has_keyword(node, "Loader")
            and not self._covered(node.lineno, "yaml", static_fingerprints)
        ):
            original = lines[node.lineno - 1]
            replacement = original.replace("yaml.load(", "yaml.safe_load(")
            suggestions.append(self._suggestion(
                filename,
                node.lineno,
                "security",
                "high",
                "Use safe YAML parsing.",
                "yaml.load can construct arbitrary Python objects when the input is attacker-controlled.",
                "Use yaml.safe_load unless custom object construction is explicitly required.",
                self._edit(node.lineno, node.lineno, original, replacement),
                0.91,
                line,
            ))

        if (
            call_name in ("subprocess.run", "subprocess.Popen", "subprocess.call", "subprocess.check_output")
            and self._keyword_is_true(node, "shell")
            and not self._covered(node.lineno, "shell", static_fingerprints)
        ):
            suggestions.append(self._suggestion(
                filename,
                node.lineno,
                "security",
                "critical",
                "Avoid shell=True in subprocess calls.",
                "shell=True routes the command through a shell, so user-controlled values can become command injection.",
                "Pass arguments as a list and keep shell=False.",
                None,
                0.93,
                line,
            ))

        if (
            call_name.endswith(".execute")
            and node.args
            and self._looks_like_dynamic_sql(node.args[0])
            and not self._covered(node.lineno, "sql", static_fingerprints)
        ):
            suggestions.append(self._suggestion(
                filename,
                node.lineno,
                "security",
                "critical",
                "SQL query is built with string interpolation.",
                "Interpolated SQL can let user-controlled values alter the query structure.",
                "Use parameterized queries and pass values separately to execute.",
                None,
                0.9,
                line,
            ))

        return suggestions

    def _model_suggestions(self, code: str, filename: str) -> List[Dict]:
        blocks = self._extract_functions(code)
        raw_suggestions = self.suggester.get_suggestions_batch([block["code"] for block in blocks])
        suggestions = []

        for block, message in zip(blocks, raw_suggestions):
            if not message or self._is_trivial_model_suggestion(message):
                continue
            suggestions.append(self._suggestion(
                filename,
                block["line"],
                "improvements",
                "medium",
                message,
                "The local generative model flagged this function after reviewing its surrounding context.",
                message,
                None,
                0.72,
                block["name"],
            ))

        return suggestions

    def _extract_functions(self, code: str) -> List[Dict]:
        try:
            tree = ast.parse(code)
        except SyntaxError:
            return []

        lines = code.splitlines()
        blocks = []
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                end = getattr(node, "end_lineno", node.lineno)
                blocks.append({
                    "name": node.name,
                    "line": node.lineno,
                    "code": "\n".join(lines[node.lineno - 1:end]),
                })
        return blocks

    def _suggestion(
        self,
        file: str,
        line: int,
        category: str,
        severity: str,
        message: str,
        explanation: str,
        fix: str,
        edit: Optional[Dict],
        confidence: float,
        snippet: str = "",
    ) -> Dict:
        return {
            "file": file,
            "line": line,
            "end_line": line,
            "column": 0,
            "category": category,
            "severity": severity,
            "message": message,
            "explanation": explanation,
            "fix": fix,
            "fix_edit": edit,
            "confidence": confidence,
            "source": "ai",
            "code_snippet": snippet,
            "status": "open",
        }

    def _edit(
        self,
        start_line: int,
        end_line: int,
        original: str,
        replacement: str,
        additional_import: Optional[str] = None,
    ) -> Dict:
        return {
            "start_line": start_line,
            "end_line": end_line,
            "original": original,
            "replacement": replacement,
            "additional_import": additional_import,
        }

    def _with_id(self, suggestion: Dict, code: str, filename: str) -> Dict:
        raw = f"{filename}:{suggestion['line']}:{suggestion['message']}:{code}"
        suggestion["id"] = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]
        return suggestion

    def _summary(self, suggestions: List[Dict]) -> Dict:
        categories = {"bugs": 0, "improvements": 0, "readability": 0, "performance": 0, "security": 0, "code_smell": 0}
        for suggestion in suggestions:
            categories[suggestion["category"]] = categories.get(suggestion["category"], 0) + 1
        return {
            "total": len(suggestions),
            "categories": categories,
            "auto_fixable": sum(1 for suggestion in suggestions if suggestion.get("fix_edit")),
        }

    def _static_fingerprints(self, static_results: Dict) -> Set[Tuple[int, str]]:
        fingerprints = set()
        for issue in static_results.get("issues", []):
            fingerprints.add((issue.get("line", 0), self._normalize_message(issue.get("message", ""))))
        return fingerprints

    def _covered(self, line: int, keyword: str, fingerprints: Set[Tuple[int, str]]) -> bool:
        normalized = self._normalize_message(keyword)
        return any(issue_line == line and normalized in message for issue_line, message in fingerprints)

    def _normalize_message(self, message: str) -> str:
        return re.sub(r"\s+", " ", message.lower()).strip()

    def _line(self, lines: List[str], line: int) -> str:
        return lines[line - 1].strip() if 0 < line <= len(lines) else ""

    def _handler_swallows_exception(self, node: ast.ExceptHandler) -> bool:
        if not node.body:
            return False
        return all(isinstance(stmt, (ast.Pass, ast.Return, ast.Constant)) for stmt in node.body)

    def _contains_nested_loop(self, node: ast.AST) -> bool:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.For, ast.While)):
                return True
            if self._contains_nested_loop(child):
                return True
        return False

    def _branches_are_duplicate(self, node: ast.If) -> bool:
        if not node.body or not node.orelse:
            return False
        return [ast.dump(stmt) for stmt in node.body] == [ast.dump(stmt) for stmt in node.orelse]

    def _compares_to_bool_literal(self, node: ast.Compare) -> bool:
        values = [node.left] + list(node.comparators)
        return any(isinstance(value, ast.Constant) and isinstance(value.value, bool) for value in values)

    def _call_name(self, node: ast.AST) -> str:
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            parent = self._call_name(node.value)
            return f"{parent}.{node.attr}" if parent else node.attr
        return ""

    def _has_keyword(self, node: ast.Call, name: str) -> bool:
        return any(keyword.arg == name for keyword in node.keywords)

    def _keyword_is_true(self, node: ast.Call, name: str) -> bool:
        for keyword in node.keywords:
            if keyword.arg == name and isinstance(keyword.value, ast.Constant):
                return keyword.value.value is True
        return False

    def _looks_like_dynamic_sql(self, node: ast.AST) -> bool:
        if isinstance(node, ast.JoinedStr):
            return True
        if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Mod, ast.Add)):
            return True
        if isinstance(node, ast.Call) and self._call_name(node.func).endswith(".format"):
            return True
        return False

    def _append_keyword_to_call_line(self, lines: List[str], node: ast.Call, keyword_text: str) -> Optional[str]:
        if node.lineno != getattr(node, "end_lineno", node.lineno):
            return None

        original = lines[node.lineno - 1]
        end_col = getattr(node, "end_col_offset", None)
        if end_col is None or end_col <= 0 or end_col > len(original):
            return None

        close_index = end_col - 1
        if original[close_index] != ")":
            return None

        before_close = original[:close_index]
        separator = "" if before_close.rstrip().endswith("(") else ", "
        return f"{before_close}{separator}{keyword_text}{original[close_index:]}"

    def _unreachable_code_suggestions(self, node: ast.AST, lines: List[str], filename: str) -> List[Dict]:
        suggestions = []
        body = getattr(node, "body", [])
        for index, stmt in enumerate(body[:-1]):
            if isinstance(stmt, (ast.Return, ast.Raise, ast.Break, ast.Continue)):
                next_stmt = body[index + 1]
                suggestions.append(self._suggestion(
                    filename,
                    getattr(next_stmt, "lineno", getattr(stmt, "lineno", 0)),
                    "bugs",
                    "medium",
                    "Code after an exit statement is unreachable.",
                    "Statements after return, raise, break, or continue in the same block will never execute.",
                    "Remove the unreachable statement or move it before the exit statement if it is required.",
                    None,
                    0.92,
                    self._line(lines, getattr(next_stmt, "lineno", 0)),
                ))
                break
        return suggestions

    def _is_trivial_model_suggestion(self, message: str) -> bool:
        trivial_terms = ("rename", "variable name", "naming", "short name", "formatting", "style")
        return any(term in message.lower() for term in trivial_terms)
