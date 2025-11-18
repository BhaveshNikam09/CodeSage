import os
import sys

print("=" * 70)
print("🔍 CodeSage Model Diagnostic")
print("=" * 70)

# Check 1: Model directory exists
model_path = "./trained-generative-model"
print(f"\n1. Checking model directory: {model_path}")

if os.path.exists(model_path):
    print("   ✅ Directory exists")
    
    # List all files in model directory
    print("\n   📁 Files in model directory:")
    for file in os.listdir(model_path):
        file_path = os.path.join(model_path, file)
        size = os.path.getsize(file_path) / (1024 * 1024)  # MB
        print(f"      - {file} ({size:.2f} MB)")
else:
    print("   ❌ Directory NOT found")
    print(f"\n   💡 Current working directory: {os.getcwd()}")
    print(f"   💡 Expected path: {os.path.abspath(model_path)}")
    sys.exit(1)

# Check 2: Required files
print("\n2. Checking required model files:")
required_files = [
    'config.json',
    'pytorch_model.bin',
    'tokenizer_config.json',
    'vocab.json',
    'merges.txt',
    'special_tokens_map.json'
]

missing_files = []
for file in required_files:
    file_path = os.path.join(model_path, file)
    if os.path.exists(file_path):
        print(f"   ✅ {file}")
    else:
        print(f"   ❌ {file} - MISSING")
        missing_files.append(file)

if missing_files:
    print(f"\n   ⚠️ Missing files: {', '.join(missing_files)}")
    print("   💡 Your model might be incomplete or corrupted")
else:
    print("\n   ✅ All required files present")

# Check 3: Try loading the model
print("\n3. Testing model loading:")

try:
    print("   Loading tokenizer...")
    from transformers import AutoTokenizer
    tokenizer = AutoTokenizer.from_pretrained(model_path)
    print("   ✅ Tokenizer loaded successfully")
except Exception as e:
    print(f"   ❌ Tokenizer loading failed: {str(e)}")
    sys.exit(1)

try:
    print("   Loading model...")
    from transformers import AutoModelForSeq2SeqLM
    model = AutoModelForSeq2SeqLM.from_pretrained(model_path)
    print("   ✅ Model loaded successfully")
    
    # Get model size
    param_count = sum(p.numel() for p in model.parameters())
    print(f"   📊 Model parameters: {param_count:,}")
    
except Exception as e:
    print(f"   ❌ Model loading failed: {str(e)}")
    sys.exit(1)

# Check 4: Test inference
print("\n4. Testing inference:")
try:
    test_code = "def divide(a, b):\n    return a / b"
    prompt = f"suggest bug: {test_code}"
    
    inputs = tokenizer(prompt, return_tensors="pt", max_length=128, truncation=True)
    
    with torch.no_grad():
        outputs = model.generate(
            inputs.input_ids,
            max_length=64,
            num_beams=2,
            early_stopping=True
        )
    
    suggestion = tokenizer.decode(outputs[0], skip_special_tokens=True)
    print(f"   ✅ Inference successful")
    print(f"   💡 Test output: {suggestion}")
    
except Exception as e:
    print(f"   ❌ Inference failed: {str(e)}")

print("\n" + "=" * 70)
print("✅ Diagnostic complete!")
print("=" * 70)