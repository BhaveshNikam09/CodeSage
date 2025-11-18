from engine.suggester import AISuggester

class InferenceModel:
    """Wrapper for model inference."""
    
    def __init__(self):
        self.suggester = AISuggester()
    
    def predict(self, code_snippets):
        """Run inference on code snippets."""
        return self.suggester.get_suggestions_batch(code_snippets)