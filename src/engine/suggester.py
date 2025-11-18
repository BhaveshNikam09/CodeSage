import torch
from transformers import AutoTokenizer, AutoModelForSeq2SeqLM
import re
from typing import List
from support.error_handler import handle_error

class AISuggester:
    """
    AI suggestion engine using your trained CodeT5 model.
    """
    
    def __init__(self, model_path="./trained-generative-model"):
        self.model_path = model_path
        self.model = None
        self.tokenizer = None
        self.cache = {}
        self.available = self._load_model()
    
    @handle_error
    def _load_model(self):
        """Load your trained model."""
        try:
            self.tokenizer = AutoTokenizer.from_pretrained(self.model_path)
            self.model = AutoModelForSeq2SeqLM.from_pretrained(self.model_path)
            self.model.eval()
            
            if torch.cuda.is_available():
                self.model = self.model.cuda()
            
            return True
        except Exception as e:
            print(f"⚠️ AI model not available: {e}")
            return False
    
    def get_suggestions_batch(self, code_blocks: List[str]) -> List[str]:
        """Get AI suggestions for multiple code blocks."""
        if not self.available:
            return [None] * len(code_blocks)
        
        try:
            # Check cache
            results = []
            uncached = []
            uncached_idx = []
            
            for i, code in enumerate(code_blocks):
                key = hash(code)
                if key in self.cache:
                    results.append(self.cache[key])
                else:
                    uncached.append(code)
                    uncached_idx.append(i)
                    results.append(None)
            
            if uncached:
                # Batch inference
                prompts = [f"suggest bug: {code}" for code in uncached]
                inputs = self.tokenizer(
                    prompts,
                    return_tensors="pt",
                    max_length=256,
                    truncation=True,
                    padding=True
                )
                
                if torch.cuda.is_available():
                    inputs = {k: v.cuda() for k, v in inputs.items()}
                
                with torch.no_grad():
                    outputs = self.model.generate(
                        inputs.input_ids,
                        max_length=64,
                        num_beams=2,
                        early_stopping=True
                    )
                
                suggestions = self.tokenizer.batch_decode(outputs, skip_special_tokens=True)
                
                # Cache and validate
                for idx, suggestion in zip(uncached_idx, suggestions):
                    cleaned = self._validate_suggestion(suggestion)
                    results[idx] = cleaned
                    self.cache[hash(code_blocks[idx])] = cleaned
            
            return results
        
        except Exception as e:
            return [None] * len(code_blocks)
    
    def _validate_suggestion(self, suggestion: str) -> str:
        """Validate and clean AI output."""
        if not suggestion or len(suggestion) < 15:
            return None
        
        # Reject code snippets
        if any(x in suggestion for x in ["def ", "for ", "if ", "return "]):
            return None
        
        # Must be actionable
        actionable = ['add', 'use', 'avoid', 'replace', 'check', 'validate', 'fix']
        if not any(word in suggestion.lower() for word in actionable):
            return None
        
        # Format
        suggestion = suggestion.strip()
        if suggestion[0].islower():
            suggestion = suggestion[0].upper() + suggestion[1:]
        if not suggestion.endswith('.'):
            suggestion += '.'
        
        return suggestion if 15 < len(suggestion) < 200 else None