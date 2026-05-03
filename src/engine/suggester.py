import os
from typing import List

from support.error_handler import handle_error


class AISuggester:
    """
    Optional trained-model suggestion engine.
    The model is lazy-loaded only when CODESAGE_ENABLE_MODEL=1 to keep the IDE flow responsive.
    """

    def __init__(self, model_path="./trained-generative-model"):
        self.model_path = model_path
        self.model = None
        self.tokenizer = None
        self.cache = {}
        self.enable_model = os.getenv("CODESAGE_ENABLE_MODEL", "0") == "1"
        self.available = False
        self._load_attempted = False

    @handle_error
    def _load_model(self):
        """Load the trained model only when explicitly enabled."""
        if self._load_attempted:
            return self.available

        self._load_attempted = True

        if not self.enable_model:
            return False

        if not self._has_model_files():
            print("AI model not found. Using fast rule-based AI mode.")
            return False

        try:
            import torch
            from transformers import AutoModelForSeq2SeqLM, AutoTokenizer

            self.tokenizer = AutoTokenizer.from_pretrained(self.model_path)
            self.model = AutoModelForSeq2SeqLM.from_pretrained(self.model_path)
            self.model.eval()

            if torch.cuda.is_available():
                self.model = self.model.cuda()

            self.available = True
            return True
        except Exception as e:
            print(f"AI model not available. Using fast rule-based AI mode. Reason: {e}")
            return False

    def _has_model_files(self):
        if not os.path.isdir(self.model_path):
            return False

        has_config = os.path.exists(os.path.join(self.model_path, "config.json"))
        has_weights = (
            os.path.exists(os.path.join(self.model_path, "pytorch_model.bin"))
            or os.path.exists(os.path.join(self.model_path, "model.safetensors"))
        )
        return has_config and has_weights

    def get_suggestions_batch(self, code_blocks: List[str]) -> List[str]:
        """Get AI suggestions for multiple code blocks."""
        if not self.available and not self._load_model():
            return [None] * len(code_blocks)

        try:
            import torch

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
                prompts = [f"suggest bug: {code}" for code in uncached]
                inputs = self.tokenizer(
                    prompts,
                    return_tensors="pt",
                    max_length=256,
                    truncation=True,
                    padding=True,
                )

                if torch.cuda.is_available():
                    inputs = {k: v.cuda() for k, v in inputs.items()}

                with torch.no_grad():
                    outputs = self.model.generate(
                        inputs.input_ids,
                        max_length=64,
                        num_beams=2,
                        early_stopping=True,
                    )

                suggestions = self.tokenizer.batch_decode(outputs, skip_special_tokens=True)

                for idx, suggestion in zip(uncached_idx, suggestions):
                    cleaned = self._validate_suggestion(suggestion)
                    results[idx] = cleaned
                    self.cache[hash(code_blocks[idx])] = cleaned

            return results
        except Exception:
            return [None] * len(code_blocks)

    def _validate_suggestion(self, suggestion: str) -> str:
        """Validate and clean AI output."""
        if not suggestion or len(suggestion) < 15:
            return None

        if any(x in suggestion for x in ["def ", "for ", "if ", "return "]):
            return None

        actionable = ["add", "use", "avoid", "replace", "check", "validate", "fix"]
        if not any(word in suggestion.lower() for word in actionable):
            return None

        suggestion = suggestion.strip()
        if suggestion[0].islower():
            suggestion = suggestion[0].upper() + suggestion[1:]
        if not suggestion.endswith("."):
            suggestion += "."

        return suggestion if 15 < len(suggestion) < 200 else None
