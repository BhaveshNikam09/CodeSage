# Security pattern rules
SECURITY_PATTERNS = {
    r'os\.system\s*\(': {
        'severity': 'critical',
        'message': 'Command injection vulnerability',
        'fix': 'Use subprocess.run() with shell=False',
        'type': 'security'
    },
    r'eval\s*\(': {
        'severity': 'critical',
        'message': 'Arbitrary code execution risk',
        'fix': 'Use ast.literal_eval() instead',
        'type': 'security'
    },
    r'exec\s*\(': {
        'severity': 'critical',
        'message': 'Code execution vulnerability',
        'fix': 'Avoid exec() or validate strictly',
        'type': 'security'
    },
    r'pickle\.loads?\s*\(': {
        'severity': 'high',
        'message': 'Unsafe deserialization',
        'fix': 'Use JSON or validate pickle source',
        'type': 'security'
    },
    r'password\s*=\s*[\'"][^\'"]+[\'"]': {
        'severity': 'critical',
        'message': 'Hardcoded password',
        'fix': 'Use environment variables: os.getenv("PASSWORD")',
        'type': 'security'
    },
    r'api[_-]?key\s*=\s*[\'"][^\'"]+[\'"]': {
        'severity': 'critical',
        'message': 'Hardcoded API key',
        'fix': 'Use environment variables or secrets manager',
        'type': 'security'
    },
    r'secret\s*=\s*[\'"][^\'"]+[\'"]': {
        'severity': 'critical',
        'message': 'Hardcoded secret',
        'fix': 'Use secure configuration',
        'type': 'security'
    },
}

# Code quality patterns
QUALITY_PATTERNS = {
    r'range\s*\(\s*len\s*\(': {
        'severity': 'low',
        'message': 'Inefficient iteration pattern',
        'fix': 'Use enumerate(): for i, item in enumerate(items)',
        'type': 'quality'
    },
    r'except\s*:': {
        'severity': 'medium',
        'message': 'Bare except clause',
        'fix': 'Specify exception types: except (ValueError, IOError)',
        'type': 'quality'
    },
    r'type\s*\(\s*\w+\s*\)\s*==': {
        'severity': 'low',
        'message': 'Use isinstance for type checking',
        'fix': 'Replace: isinstance(obj, type)',
        'type': 'quality'
    },
    r'open\s*\([^)]*\)(?!.*with)': {
        'severity': 'medium',
        'message': 'File not closed properly',
        'fix': 'Use context manager: with open(...) as f:',
        'type': 'bug'
    },
}

# Variable name typo detection patterns
TYPO_PATTERNS = [
    (r'\breturn\s+(\w{1,3})\b', r'Variable name too short in return statement'),
    (r'\b(da|dat|dta|ata)\b(?!ta)', r'Possible typo: might be "data"'),
    (r'\b(usr|usre|uesr)\b', r'Possible typo: might be "user"'),
    (r'\b(rslt|reslt|reult)\b', r'Possible typo: might be "result"'),
]

# Severity colors for UI
SEVERITY_COLORS = {
    'critical': '#DC2626',
    'high': '#EF4444',
    'medium': '#F59E0B',
    'low': '#3B82F6'
}

# Analysis configuration
ANALYSIS_CONFIG = {
    'max_file_size_mb': 5,
    'timeout_seconds': 30,
    'enable_ai': True,
    'enable_complexity': True,
}
