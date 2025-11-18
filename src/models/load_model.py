import os

def check_model_exists(model_path="trained-generative-model"):
    """Check if trained model exists."""
    required_files = ['config.json', 'pytorch_model.bin']
    
    if not os.path.exists(model_path):
        return False
    
    for file in required_files:
        if not os.path.exists(os.path.join(model_path, file)):
            return False
    
    return True

def get_model_info(model_path="trained-generative-model"):
    """Get model information."""
    if not check_model_exists(model_path):
        return {
            'available': False,
            'error': 'Model not found'
        }
    
    return {
        'path': model_path,
        'available': True,
        'type': 'CodeT5',
        'status': 'Ready'
    }