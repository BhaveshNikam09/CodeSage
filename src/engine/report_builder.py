from datetime import datetime
import json
from typing import Dict

class ReportBuilder:
    """Generate analysis reports in various formats."""
    
    @staticmethod
    def generate_json(results: Dict, filename: str = None) -> str:
        """Generate JSON report."""
        report = {
            'timestamp': datetime.now().isoformat(),
            'analysis': results
        }
        
        json_str = json.dumps(report, indent=2)
        
        if filename:
            with open(filename, 'w') as f:
                f.write(json_str)
        
        return json_str
    
    @staticmethod
    def generate_html(results: Dict) -> str:
        """Generate HTML report."""
        stats = results.get('statistics', {})
        summary = results.get('summary', {})
        issues = results.get('issues', [])
        
        html = f"""
<!DOCTYPE html>
<html>
<head>
    <title>CodeSage Analysis Report</title>
    <style>
        body {{ font-family: Arial; margin: 20px; background: #f5f5f5; }}
        .container {{ max-width: 1200px; margin: 0 auto; background: white; padding: 30px; }}
        .score {{ font-size: 48px; font-weight: bold; color: #2563EB; }}
        .issue {{ background: #f8f9fa; padding: 15px; margin: 10px 0; border-left: 4px solid; }}
        .critical {{ border-color: #DC2626; }}
        .high {{ border-color: #EF4444; }}
        .medium {{ border-color: #F59E0B; }}
        .low {{ border-color: #3B82F6; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>CodeSage Analysis Report</h1>
        <div class="score">{summary.get('score', 0)}/100</div>
        <p>Status: {summary.get('status', 'unknown').upper()}</p>
        
        <h2>Issues Found: {stats.get('total_issues', 0)}</h2>
"""
        
        for issue in issues:
            html += f"""
        <div class="issue {issue['severity']}">
            <strong>Line {issue['line']}</strong>: {issue['message']}<br>
            <code>{issue.get('code_snippet', '')}</code><br>
            <em>Fix: {issue['fix']}</em>
        </div>
"""
        
        html += """
    </div>
</body>
</html>
"""
        return html


# ============================================================================
# FILE: models/inference.py
# Model inference wrapper
# ============================================================================

from engine.suggester import AISuggester

class InferenceModel:
    """Wrapper for model inference."""
    
    def __init__(self):
        self.suggester = AISuggester()
    
    def predict(self, code_snippets):
        """Run inference on code snippets."""
        return self.suggester.get_suggestions_batch(code_snippets)
    
    @property
    def is_available(self):
        """Check if model is available."""
        return self.suggester.available