import json
import os

class ConfigLoader:
    """Load and manage application configuration."""
    
    DEFAULT_CONFIG = {
        'analysis': {
            'max_file_size_mb': 5,
            'timeout_seconds': 30,
            'enable_complexity': True,
            'enable_security_scan': True
        },
        'ai': {
            'model_path': './trained-generative-model',
            'use_gpu': True,
            'batch_size': 4,
            'enable_ai': True
        },
        'server': {
            'host': '0.0.0.0',
            'port': 5000,
            'debug': True
        }
    }
    
    @staticmethod
    def load(config_file='config.json'):
        """Load configuration from file or use defaults."""
        if os.path.exists(config_file):
            with open(config_file, 'r') as f:
                return json.load(f)
        return ConfigLoader.DEFAULT_CONFIG
    
    @staticmethod
    def save(config, config_file='config.json'):
        """Save configuration to file."""
        with open(config_file, 'w') as f:
            json.dump(config, f, indent=2)