# CodeSage - AI-powered code review system

## Local Run

From the project root:

```powershell
.\venv\python.exe -m pip install -r requirements.txt
.\venv\python.exe -m src.app.app
```

Backend URL:

```text
http://127.0.0.1:5000
```

Health check:

```powershell
Invoke-RestMethod http://127.0.0.1:5000/health
```

The fast rule-based AI review runs by default. To enable the local transformer model:

```powershell
$env:CODESAGE_ENABLE_MODEL="1"
.\venv\python.exe -m src.app.app
```

## VS Code Extension

1. Open VS Code.
2. Open this folder:

```text
D:\Final Year Project\CodeSage\vscode-extension
```

3. Press `F5`.
4. In the Extension Development Host, open a Python file.
5. Run `CodeSage: Analyze Code` from the command palette or click the `CodeSage` status bar item.
6. Run `Review with CodeSage` for a PR-style local review panel.
7. Run `CodeSage: Review GitHub Pull Request` to preview or post review comments for a GitHub PR.

Expected flow:

```text
Open file -> Analyze Code -> Review grouped panel -> Hover inline issue -> Accept Fix or Reject
```

## Test Flow

Backend tests:

```powershell
.\venv\python.exe -m pytest
```

Extension syntax check:

```powershell
node --check vscode-extension\extension.js
```

## GitHub PR Assistant

Set the GitHub token in the backend environment. Do not commit tokens to the repo.

```powershell
$env:CODESAGE_GITHUB_TOKEN="github_pat_..."
$env:CODESAGE_GITHUB_WEBHOOK_SECRET="shared-webhook-secret"
.\venv\python.exe -m src.app.app
```

Manual PR review endpoint:

```powershell
Invoke-RestMethod http://127.0.0.1:5000/api/github/pr-review `
  -Method Post `
  -ContentType "application/json" `
  -Body '{"owner":"OWNER","repo":"REPO","pull_number":1,"post_comments":false}'
```

Webhook URL for GitHub:

```text
https://YOUR-BACKEND/api/github/webhook
```

Webhook events:

```text
pull_request: opened, synchronize, reopened, ready_for_review
```

Deployment notes:

```text
Backend: deploy the Flask app on Render, Railway, or AWS with CODESAGE_GITHUB_TOKEN and CODESAGE_GITHUB_WEBHOOK_SECRET as environment variables.
Extension: package from vscode-extension with vsce package, then publish with vsce publish after setting publisher credentials.
```

## Fast Render Deployment

1. Push this project to GitHub.
2. Open Render and create a new Web Service from that GitHub repo.
3. Use:

```text
Build Command: pip install -r requirements.txt
Start Command: gunicorn src.app.app:app --bind 0.0.0.0:$PORT --workers 1 --timeout 120
Health Check Path: /health
```

4. Add environment variables in Render:

```text
CODESAGE_GITHUB_TOKEN=your_new_pat
CODESAGE_GITHUB_WEBHOOK_SECRET=your_random_secret
CODESAGE_ENABLE_MODEL=0
CODESAGE_MAX_INLINE_COMMENTS=20
```

5. After deploy, Render gives a public URL like:

```text
https://codesage-ai.onrender.com
```

6. Your GitHub webhook payload URL becomes:

```text
https://codesage-ai.onrender.com/api/github/webhook
```

7. In GitHub repo settings, create the webhook:

```text
Payload URL: https://YOUR-RENDER-URL/api/github/webhook
Content type: application/json
Secret: same value as CODESAGE_GITHUB_WEBHOOK_SECRET
Events: Pull requests
```

Manual end-to-end check:

1. Start backend with `.\venv\python.exe -m src.app.app`.
2. Launch the extension with `F5`.
3. Open a Python file containing a risky pattern like `eval(user_input)`.
4. Run `CodeSage: Analyze Code`.
5. Confirm the side panel groups findings into Errors, Warnings, and Suggestions.
6. Confirm inline highlights use red, yellow, and blue severity colors.
7. Use `View Details`, `Reject`, and `Accept Fix`.
