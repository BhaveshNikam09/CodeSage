# CodeSage – AI Code Reviewer & PR Assistant

## 📌 Overview
CodeSage is an AI-powered assistant that:
- Reviews source code inside IDEs (VS Code, Jupyter)
- Detects bugs, vulnerabilities, and performance issues
- Suggests optimizations with natural language explanations
- Simulates Pull Request (PR) feedback (GitHub-style)

## 🎯 Goals
- Provide real-time inline feedback
- Improve code quality and security
- Reduce manual review time

## 🚀 Tech Stack
- **Languages**: Python, JavaScript (VS Code Extension)
- **AI Models**: CodeT5, CodeBERT
- **Frameworks**: Hugging Face Transformers, FastAPI
- **Static Analysis**: Pylint, Radon, Bandit
- **IDE Integration**: VS Code API, Jupyter Magic Commands
- **Deployment**: Localhost / Docker

## 🛠️ Project Structure
See folder layout in repository.

## ▶️ Quickstart
```bash
cd CodeSage
pip install -r requirements.txt
python template.py
uvicorn app.app:app --reload
```
