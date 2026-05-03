import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SRC = os.path.join(ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from engine.engine import ReviewEngine
from pr_assistant.reviewer import PRReviewBuilder


def messages(result):
    return [issue["message"] for issue in result["issues"]]


def test_ai_flags_duplicate_branches_without_model():
    code = """
def status(flag):
    if flag:
        return "ok"
    else:
        return "ok"
"""

    result = ReviewEngine().review(code, "sample.py")

    assert any("duplicate logic" in message.lower() for message in messages(result))


def test_ai_filters_low_value_short_variable_typo_noise():
    code = """
def read_value(data):
    return da
"""

    result = ReviewEngine().review(code, "sample.py")

    assert not any("variable name too short" in message.lower() for message in messages(result))


def test_ai_flags_unreachable_code():
    code = """
def calculate():
    return 1
    print("never runs")
"""

    result = ReviewEngine().review(code, "sample.py")

    assert any("unreachable" in message.lower() for message in messages(result))


def test_ai_flags_http_request_without_timeout_with_fix():
    code = 'import requests\nresponse = requests.get(url)\n'

    result = ReviewEngine().review(code, "sample.py")
    issue = next(issue for issue in result["issues"] if "no timeout" in issue["message"].lower())

    assert issue["fix_edit"]["replacement"] == "response = requests.get(url, timeout=10)"


def test_ai_flags_dynamic_sql_interpolation():
    code = 'cursor.execute(f"SELECT * FROM users WHERE id = {user_id}")\n'

    result = ReviewEngine().review(code, "sample.py")

    assert any("sql query" in message.lower() for message in messages(result))


def test_static_hardcoded_api_key_has_safe_fix_edit():
    code = 'api_key = "abc123"\n'

    result = ReviewEngine().review(code, "sample.py")
    issue = next(issue for issue in result["issues"] if issue["message"] == "Hardcoded API key")

    assert issue["fix_edit"]["replacement"] == 'api_key = os.getenv("API_KEY", "")'
    assert issue["fix_edit"]["additional_import"] == "import os"


def test_static_eval_has_safe_fix_edit():
    code = "value = eval(raw)\n"

    result = ReviewEngine().review(code, "sample.py")
    issue = next(issue for issue in result["issues"] if issue["message"] == "Arbitrary code execution risk")

    assert issue["fix_edit"]["replacement"] == "value = ast.literal_eval(raw)"
    assert issue["fix_edit"]["additional_import"] == "import ast"


def test_undefined_typo_uses_exact_line_and_safe_fix_edit():
    code = """
def build_domain_url(domain):
    return d.strip()
"""

    result = ReviewEngine().review(code, "sample.py")
    issue = next(issue for issue in result["issues"] if 'Undefined variable "d"' in issue["message"])

    assert issue["line"] == 3
    assert issue["fix_edit"]["original"] == "    return d.strip()"
    assert issue["fix_edit"]["replacement"] == "    return domain.strip()"
    assert "Accept Fix" in issue["explanation"]


def test_pr_review_returns_strict_diff_sections_and_final_code():
    code = 'api_key = "abc123"\nvalue = eval(raw)\n'
    analysis = ReviewEngine().review(code, "sample.py")

    review = PRReviewBuilder().build(analysis, "sample.py", code)

    assert review["status"] == "changes_requested"
    assert review["pr_title"].startswith("fix:")
    assert review["overwrite_mode"]["supported"] is True
    assert "## Summary of Issues" in review["markdown_review"]
    assert "## Detailed PR Review" in review["markdown_review"]
    assert "## File-wise Changes" in review["markdown_review"]
    assert "## Diff Suggestions" in review["markdown_review"]
    assert "## Final Improved Code" in review["markdown_review"]
    assert any(item["file"] == "sample.py" and item["lines"] == "1" for item in review["diff_suggestions"])
    assert 'api_key = os.getenv("API_KEY", "")' in review["final_improved_code"]
    assert "value = ast.literal_eval(raw)" in review["final_improved_code"]
    assert "import os" in review["final_improved_code"]
    assert "import ast" in review["final_improved_code"]


def test_pr_review_keeps_manual_comments_when_no_safe_patch_exists():
    code = """
def status(flag):
    if flag:
        return "ok"
    else:
        return "ok"
"""
    analysis = ReviewEngine().review(code, "sample.py")

    review = PRReviewBuilder().build(analysis, "sample.py", code)

    manual = next(item for item in review["diff_suggestions"] if item["apply"]["ready"] is False)
    assert manual["new_code"] is None
    assert "Manual review required" in manual["diff_hunk"]
    assert "senior" not in review["markdown_review"].lower()
