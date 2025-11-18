from flask import Blueprint, request, jsonify
from support.response_format import format_success, format_error
from utils.logger import Logger
import json
import os
from datetime import datetime

feedback_bp = Blueprint('feedback', __name__)
logger = Logger.setup()

FEEDBACK_FILE = 'data/feedback.jsonl'

@feedback_bp.route('/feedback', methods=['POST'])
def submit_feedback():
    """Collect user feedback on suggestions."""
    try:
        data = request.get_json()
        issue_id = data.get('issue_id')
        helpful = data.get('helpful')
        comment = data.get('comment', '')
        
        # Create data directory if not exists
        os.makedirs('data', exist_ok=True)
        
        # Store feedback for model retraining (Stage 2)
        feedback_entry = {
            'timestamp': datetime.now().isoformat(),
            'issue_id': issue_id,
            'helpful': helpful,
            'comment': comment
        }
        
        with open(FEEDBACK_FILE, 'a') as f:
            f.write(json.dumps(feedback_entry) + '\n')
        
        logger.info(f"Feedback recorded: {issue_id}")
        
        return jsonify(format_success({
            'message': 'Feedback recorded successfully',
            'issue_id': issue_id
        }))
    
    except Exception as e:
        logger.error(f"Feedback error: {str(e)}")
        return jsonify(format_error(str(e))), 500
