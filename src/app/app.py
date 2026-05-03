import os
import sys

SRC_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

try:
    from dotenv import load_dotenv

    PROJECT_ROOT = os.path.abspath(os.path.join(SRC_DIR, ".."))
    load_dotenv(os.path.join(PROJECT_ROOT, ".env"))
except Exception:
    pass

try:
    sys.stdout.reconfigure(encoding="utf-8")
except AttributeError:
    pass

from flask import Flask, render_template, request, jsonify
from routes.analyze import analyze_bp
from routes.feedback import feedback_bp
from routes.pr_assistant import pr_bp
from werkzeug.utils import secure_filename
from utils.config_loader import ConfigLoader
from utils.logger import Logger
from models.load_model import check_model_exists, get_model_info

# Initialize Flask app
app = Flask(__name__)

# Load configuration
config = ConfigLoader.load()
app.config['MAX_CONTENT_LENGTH'] = config['analysis']['max_file_size_mb'] * 1024 * 1024
app.config['UPLOAD_FOLDER'] = 'uploads'

# Setup logger
logger = Logger.setup()

# Register blueprints
app.register_blueprint(analyze_bp, url_prefix='/api')
app.register_blueprint(feedback_bp, url_prefix='/api')
app.register_blueprint(pr_bp, url_prefix='/api')

# Ensure required directories exist
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs('logs', exist_ok=True)
os.makedirs('data', exist_ok=True)

@app.route('/')
def index():
    """Render main UI."""
    return render_template('index.html')

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint."""
    model_info = get_model_info()
    
    return jsonify({
        'status': 'healthy',
        'model': model_info,
        'version': '1.0.0'
    })

@app.route('/upload', methods=['POST'])
def upload_file():
    """Handle file upload."""
    try:
        if 'file' not in request.files:
            return jsonify({'error': 'No file provided'}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400
        
        if file and file.filename.endswith('.py'):
            filename = secure_filename(file.filename)
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)
            
            # Read file content
            with open(filepath, 'r', encoding='utf-8') as f:
                code = f.read()
            
            # Clean up
            os.remove(filepath)
            
            logger.info(f"File uploaded: {filename}")
            return jsonify({'success': True, 'code': code})
        
        return jsonify({'error': 'Only .py files allowed'}), 400
    
    except Exception as e:
        logger.error(f"Upload error: {str(e)}")
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    print("=" * 70)
    print("🚀 CodeSage - AI Code Reviewer")
    print("=" * 70)
    print("\n✅ Static Analyzer: Ready")
    
    model_status = "✅ Ready" if check_model_exists() else "⚠️  Not Found (Using pattern-only mode)"
    print(f"🤖 AI Model: {model_status}")
    
    host = config['server']['host']
    port = config['server']['port']
    debug = config['server']['debug']
    
    print(f"\n🌐 Server: http://{host}:{port}")
    print("=" * 70)
    
    app.run(debug=debug, port=port, host=host)
