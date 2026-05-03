import os

def check_model_exists(model_path="trained-generative-model"):
    """Check if trained model exists."""
    if not os.path.exists(model_path):
        return False

    has_config = os.path.exists(os.path.join(model_path, 'config.json'))
    has_weights = (
        os.path.exists(os.path.join(model_path, 'pytorch_model.bin')) or
        os.path.exists(os.path.join(model_path, 'model.safetensors'))
    )

    return has_config and has_weights

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
