from flask import Blueprint, request, jsonify
from engine.analyzer import StaticAnalyzer
from engine.suggester import AISuggester
from support.response_format import format_success, format_error
from support.error_handler import handle_api_error
import ast

analyze_bp = Blueprint('analyze', __name__)
analyzer = StaticAnalyzer()
suggester = AISuggester()

@analyze_bp.route('/analyze', methods=['POST'])
@handle_api_error
def analyze_code():
    """Analyze Python code."""
    data = request.get_json()
    code = data.get('code', '')
    
    if not code:
        return jsonify(format_error('No code provided')), 400
    
    # Run static analysis
    results = analyzer.analyze(code)
    
    # Get AI suggestions if available
    if suggester.available:
        functions = extract_functions(code)
        if functions:
            codes = [f['code'] for f in functions]
            suggestions = suggester.get_suggestions_batch(codes)
            
            for func, suggestion in zip(functions, suggestions):
                if suggestion:
                    results['issues'].append({
                        'line': func['lineno'],
                        'column': 0,
                        'severity': 'medium',
                        'message': suggestion,
                        'fix': suggestion,
                        'type': 'ai',
                        'code_snippet': func['name']
                    })
    
    return jsonify(format_success(results))

def extract_functions(code):
    """Extract functions from code."""
    functions = []
    try:
        tree = ast.parse(code)
        lines = code.split('\n')
        
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                start = node.lineno - 1
                end = node.end_lineno if hasattr(node, 'end_lineno') else start + 10
                functions.append({
                    'name': node.name,
                    'code': '\n'.join(lines[start:end]),
                    'lineno': node.lineno
                })
    except:
        pass
    
    return functions