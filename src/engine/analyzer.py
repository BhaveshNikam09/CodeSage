import ast
import re
from radon.complexity import cc_visit
from typing import List, Dict
from utils.constants import SECURITY_PATTERNS, QUALITY_PATTERNS

class StaticAnalyzer:
    """
    Core static code analysis using AST and patterns.
    Works independently without AI.
    """
    
    def analyze(self, code: str) -> Dict:
        """Main analysis method."""
        try:
            results = {
                'issues': [],
                'complexity': {},
                'statistics': {},
                'summary': {}
            }
            
            # Pattern-based detection
            results['issues'].extend(self._pattern_scan(code))
            
            # AST-based detection
            results['issues'].extend(self._ast_scan(code))
            
            # Complexity analysis
            results['complexity'] = self._complexity_scan(code)
            
            # Statistics
            results['statistics'] = self._calculate_stats(code, results['issues'])
            
            # Summary
            results['summary'] = self._generate_summary(results)
            
            return results
            
        except Exception as e:
            return {'error': str(e), 'issues': [], 'statistics': {}, 'summary': {}}
    
    def _pattern_scan(self, code: str) -> List[Dict]:
        """Regex-based pattern detection."""
        issues = []
        lines = code.split('\n')
        
        all_patterns = {**SECURITY_PATTERNS, **QUALITY_PATTERNS}
        
        for line_num, line in enumerate(lines, 1):
            for pattern, info in all_patterns.items():
                if re.search(pattern, line, re.IGNORECASE):
                    issues.append({
                        'line': line_num,
                        'column': 0,
                        'severity': info['severity'],
                        'message': info['message'],
                        'fix': info['fix'],
                        'type': info['type'],
                        'code_snippet': line.strip()
                    })
            
            # Check for common typos
            from utils.constants import TYPO_PATTERNS
            for typo_pattern, message in TYPO_PATTERNS:
                if re.search(typo_pattern, line):
                    match = re.search(typo_pattern, line)
                    if match:
                        issues.append({
                            'line': line_num,
                            'column': 0,
                            'severity': 'high',
                            'message': message,
                            'fix': 'Check for spelling errors in variable names',
                            'type': 'bug',
                            'code_snippet': line.strip()
                        })
        
        return issues
    
    def _ast_scan(self, code: str) -> List[Dict]:
        """AST-based structural analysis."""
        issues = []
        
        try:
            tree = ast.parse(code)
            
            for node in ast.walk(tree):
                # Division by zero
                if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
                    issues.append({
                        'line': node.lineno,
                        'column': node.col_offset,
                        'severity': 'high',
                        'message': 'Potential division by zero',
                        'fix': 'Add validation: if denominator != 0',
                        'type': 'bug',
                        'code_snippet': ''
                    })
                
                # Mutable defaults
                if isinstance(node, ast.FunctionDef):
                    for default in node.args.defaults:
                        if isinstance(default, (ast.List, ast.Dict)):
                            issues.append({
                                'line': node.lineno,
                                'column': node.col_offset,
                                'severity': 'medium',
                                'message': 'Mutable default argument',
                                'fix': 'Use None: def func(arg=None): arg = arg or []',
                                'type': 'bug',
                                'code_snippet': f'def {node.name}(...)'
                            })
                    
                    # Check for undefined variables in function
                    issues.extend(self._check_undefined_vars(node, code))
                
                # File not closed (missing 'with' statement)
                if isinstance(node, ast.Call):
                    if isinstance(node.func, ast.Name) and node.func.id == 'open':
                        issues.append({
                            'line': node.lineno,
                            'column': node.col_offset,
                            'severity': 'medium',
                            'message': 'File opened without context manager',
                            'fix': 'Use: with open(path, "r") as f: data = f.read()',
                            'type': 'bug',
                            'code_snippet': ''
                        })
        
        except SyntaxError as e:
            issues.append({
                'line': e.lineno or 0,
                'column': e.offset or 0,
                'severity': 'critical',
                'message': f'Syntax Error: {e.msg}',
                'fix': 'Check for typos, missing colons, or incomplete statements',
                'type': 'syntax',
                'code_snippet': e.text.strip() if e.text else ''
            })
        except Exception as e:
            # Catch other parsing errors
            issues.append({
                'line': 0,
                'column': 0,
                'severity': 'critical',
                'message': f'Code parsing error: {str(e)}',
                'fix': 'Fix syntax and structural errors',
                'type': 'syntax',
                'code_snippet': ''
            })
        
        return issues
    
    def _check_undefined_vars(self, func_node: ast.FunctionDef, code: str) -> List[Dict]:
        """Check for undefined or typo variables in function."""
        issues = []
        
        try:
            # Get all variable assignments in function
            assigned_vars = set()
            used_vars = set()
            
            for node in ast.walk(func_node):
                # Variables being assigned
                if isinstance(node, ast.Assign):
                    for target in node.targets:
                        if isinstance(target, ast.Name):
                            assigned_vars.add(target.id)
                
                # Variables being used
                if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
                    used_vars.add(node.id)
            
            # Check for typos/undefined variables
            # Common pattern: assigned 'data' but returned 'da' or 'dat'
            for used in used_vars:
                if used not in assigned_vars and used not in dir(__builtins__):
                    # Check if it looks like a typo
                    for assigned in assigned_vars:
                        if assigned.startswith(used) and len(assigned) > len(used):
                            issues.append({
                                'line': func_node.lineno,
                                'column': 0,
                                'severity': 'critical',
                                'message': f'Undefined variable "{used}" - possibly typo of "{assigned}"',
                                'fix': f'Change "{used}" to "{assigned}"',
                                'type': 'bug',
                                'code_snippet': f'return {used}'
                            })
                            break
        except:
            pass
        
        return issues
    
    def _complexity_scan(self, code: str) -> Dict:
        """Cyclomatic complexity analysis."""
        complexity_data = {}
        
        try:
            results = cc_visit(code)
            for item in results:
                complexity_data[item.name] = {
                    'complexity': item.complexity,
                    'line': item.lineno,
                    'classification': 'Simple' if item.complexity <= 5 else
                                    'Moderate' if item.complexity <= 10 else 'Complex'
                }
        except:
            pass
        
        return complexity_data
    
    def _calculate_stats(self, code: str, issues: List[Dict]) -> Dict:
        """Calculate code statistics."""
        lines = code.split('\n')
        
        return {
            'total_lines': len(lines),
            'code_lines': sum(1 for l in lines if l.strip() and not l.strip().startswith('#')),
            'total_issues': len(issues),
            'critical': sum(1 for i in issues if i['severity'] == 'critical'),
            'high': sum(1 for i in issues if i['severity'] == 'high'),
            'medium': sum(1 for i in issues if i['severity'] == 'medium'),
            'low': sum(1 for i in issues if i['severity'] == 'low'),
        }
    
    def _generate_summary(self, results: Dict) -> Dict:
        """Generate summary."""
        stats = results['statistics']
        
        # Calculate score
        penalty = (stats['critical'] * 20 + stats['high'] * 10 + 
                  stats['medium'] * 5 + stats['low'] * 2)
        score = max(0, 100 - penalty)
        
        return {
            'score': score,
            'status': 'critical' if stats['critical'] > 0 else
                     'warning' if stats['high'] > 0 else 'pass'
        }