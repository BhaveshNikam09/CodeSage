import hashlib
import hmac
import os

from flask import Blueprint, jsonify, request

from engine.engine import ReviewEngine
from pr_assistant.github_client import GitHubClientError
from pr_assistant.github_reviewer import GitHubPRReviewer
from pr_assistant.reviewer import PRReviewBuilder
from support.error_handler import handle_api_error
from support.response_format import format_error, format_success

pr_bp = Blueprint("pr_assistant", __name__)
engine = ReviewEngine()
review_builder = PRReviewBuilder()
github_reviewer = GitHubPRReviewer(engine=engine, review_builder=review_builder)
suggestion_states = {}


@pr_bp.route("/pr-review", methods=["POST"])
@handle_api_error
def generate_pr_review():
    data = request.get_json()
    code = data.get("code", "")
    filename = data.get("filename", "code.py")

    if not code:
        return jsonify(format_error("No code provided")), 400

    analysis = engine.review(code, filename)
    review = review_builder.build(analysis, filename, code, _feedback_snapshot())
    return jsonify(format_success(review))


@pr_bp.route("/github/pr-review", methods=["POST"])
@handle_api_error
def generate_github_pr_review():
    data = request.get_json()
    owner = data.get("owner")
    repo = data.get("repo")
    pull_number = data.get("pull_number")
    post_comments = bool(data.get("post_comments", False))

    if not owner or not repo or not pull_number:
        return jsonify(format_error("owner, repo, and pull_number are required")), 400

    try:
        review = github_reviewer.review_pull_request(
            owner,
            repo,
            int(pull_number),
            post_comments=post_comments,
            max_inline_comments=int(data.get("max_inline_comments", 20)),
        )
        return jsonify(format_success(review))
    except GitHubClientError as error:
        return jsonify(format_error(str(error))), 502


@pr_bp.route("/github/status", methods=["GET"])
@handle_api_error
def github_status():
    token = os.getenv("CODESAGE_GITHUB_TOKEN", "")
    webhook_secret = os.getenv("CODESAGE_GITHUB_WEBHOOK_SECRET", "")
    return jsonify(format_success({
        "token_configured": bool(token and token != "PASTE_NEW_TOKEN_HERE"),
        "token_preview": _token_preview(token),
        "webhook_secret_configured": bool(webhook_secret and webhook_secret != "PASTE_RANDOM_WEBHOOK_SECRET_HERE"),
        "webhook_url": "/api/github/webhook",
    }))


@pr_bp.route("/github/webhook", methods=["POST"])
@handle_api_error
def github_webhook():
    if not _valid_github_signature(request):
        return jsonify(format_error("Invalid GitHub webhook signature")), 401

    event = request.headers.get("X-GitHub-Event", "")
    payload = request.get_json() or {}
    if event != "pull_request":
        return jsonify(format_success({"ignored": True, "reason": f"Unsupported event: {event}"}))

    action = payload.get("action")
    if action not in ("opened", "synchronize", "reopened", "ready_for_review"):
        return jsonify(format_success({"ignored": True, "reason": f"Ignored pull_request action: {action}"}))

    pull_request = payload.get("pull_request", {})
    repository = payload.get("repository", {})
    owner = repository.get("owner", {}).get("login")
    repo = repository.get("name")
    pull_number = pull_request.get("number")

    if not owner or not repo or not pull_number:
        return jsonify(format_error("Webhook payload is missing repository or pull request data")), 400

    try:
        review = github_reviewer.review_pull_request(
            owner,
            repo,
            int(pull_number),
            post_comments=True,
            max_inline_comments=int(os.getenv("CODESAGE_MAX_INLINE_COMMENTS", "20")),
        )
        return jsonify(format_success({
            "processed": True,
            "repository": f"{owner}/{repo}",
            "pull_number": pull_number,
            "status": review["status"],
            "posted": {
                "inline_count": len(review.get("posted", {}).get("inline", [])),
                "general": bool(review.get("posted", {}).get("general")),
            },
        }))
    except GitHubClientError as error:
        return jsonify(format_error(str(error))), 502


@pr_bp.route("/suggestions/action", methods=["POST"])
@handle_api_error
def update_suggestion_action():
    data = request.get_json()
    suggestion_id = data.get("suggestion_id")
    action = data.get("action")

    if not suggestion_id:
        return jsonify(format_error("suggestion_id is required")), 400

    if action not in ("accepted", "ignored", "resolved", "rejected"):
        return jsonify(format_error("Invalid action")), 400

    suggestion_states[suggestion_id] = action
    return jsonify(format_success({
        "suggestion_id": suggestion_id,
        "status": action,
    }))


def _feedback_snapshot():
    return {
        "accepted": [
            suggestion_id
            for suggestion_id, action in suggestion_states.items()
            if action == "accepted"
        ],
        "rejected": [
            suggestion_id
            for suggestion_id, action in suggestion_states.items()
            if action in ("rejected", "ignored")
        ],
    }


def _valid_github_signature(req) -> bool:
    secret = os.getenv("CODESAGE_GITHUB_WEBHOOK_SECRET")
    if not secret:
        return True

    signature = req.headers.get("X-Hub-Signature-256", "")
    if not signature.startswith("sha256="):
        return False

    expected = "sha256=" + hmac.new(secret.encode("utf-8"), req.get_data(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(signature, expected)


def _token_preview(token: str) -> str:
    if not token or token == "PASTE_NEW_TOKEN_HERE":
        return ""
    if len(token) <= 8:
        return "***"
    return f"{token[:4]}...{token[-4:]}"
