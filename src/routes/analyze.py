from flask import Blueprint, request, jsonify
from engine.engine import ReviewEngine
from support.response_format import format_success, format_error
from support.error_handler import handle_api_error

analyze_bp = Blueprint('analyze', __name__)
engine = ReviewEngine()

@analyze_bp.route('/analyze', methods=['POST'])
@handle_api_error
def analyze_code():
    data = request.get_json()
    code = data.get("code", "")
    filename = data.get("filename", "code.py")

    if not code:
        return jsonify(format_error("No code provided")), 400

    results = engine.review(code, filename)
    return jsonify(format_success(results))
