# CodeSage

> AI-powered code review assistant — analyze Python files, catch bugs, and review GitHub pull requests directly from VS Code.

---

## Features

- **Instant code analysis** — rule-based AI review runs by default with zero setup
- **Severity-grouped findings** — issues grouped into Errors, Warnings, and Suggestions
- **Inline highlights** — red, yellow, and blue severity decorations directly in the editor
- **Accept / Reject fixes** — one-click fix application or dismissal from the review panel
- **GitHub PR integration** — post automated review comments to open pull requests
- **Webhook support** — auto-trigger reviews on PR open, sync, reopen, or ready-for-review events
- **Optional local model** — swap in a local transformer model with a single environment flag

---

## Prerequisites

- Python 3.9+
- Node.js 18+ (for the VS Code extension)
- VS Code 1.75+

---

## Quick Start

### 1. Install dependencies

```powershell
.\venv\python.exe -m pip install -r requirements.txt
```

### 2. Start the backend

```powershell
.\venv\python.exe -m src.app.app
```

Backend runs at `http://127.0.0.1:5000`.

Verify it's up:

```powershell
Invoke-RestMethod http://127.0.0.1:5000/health
```

### 3. Launch the VS Code extension

1. Open VS Code and load the `vscode-extension` folder:

   ```
   D:\Final Year Project\CodeSage\vscode-extension
   ```

2. Press `F5` to open an Extension Development Host.
3. Open any Python file.

---

## Usage

Run commands from the **Command Palette** (`Ctrl+Shift+P`) or click the **CodeSage** status bar item.

| Command | Description |
|---|---|
| `CodeSage: Analyze Code` | Analyze the current file and open the review panel |
| `Review with CodeSage` | Open a PR-style local review panel with grouped findings |
| `CodeSage: Review GitHub Pull Request` | Preview or post review comments to a GitHub PR |

**Typical workflow:**

```
Open file → Analyze Code → Review grouped panel → Hover inline issue → Accept Fix or Reject
```

---

## Configuration

### Enable the local transformer model

By default, CodeSage uses a fast rule-based engine. To switch to the local transformer model:

```powershell
$env:CODESAGE_ENABLE_MODEL="1"
.\venv\python.exe -m src.app.app
```

### GitHub PR Assistant

Set your GitHub credentials before starting the backend. **Never commit tokens to the repository.**

```powershell
$env:CODESAGE_GITHUB_TOKEN="github_pat_..."
$env:CODESAGE_GITHUB_WEBHOOK_SECRET="shared-webhook-secret"
.\venv\python.exe -m src.app.app
```

Manually trigger a PR review:

```powershell
Invoke-RestMethod http://127.0.0.1:5000/api/github/pr-review `
  -Method Post `
  -ContentType "application/json" `
  -Body '{"owner":"OWNER","repo":"REPO","pull_number":1,"post_comments":false}'
```

### Webhook setup

Point your GitHub repository webhook at:

```
https://YOUR-BACKEND/api/github/webhook
```

Supported events: `pull_request` — `opened`, `synchronize`, `reopened`, `ready_for_review`

---

## Running Tests

**Backend tests:**

```powershell
.\venv\python.exe -m pytest
```

**Extension syntax check:**

```powershell
node --check vscode-extension\extension.js
```

---

## Deployment

### Deploy to Render

1. Push the project to GitHub.
2. In [Render](https://render.com), create a new **Web Service** from the repo.
3. Use these settings:

   | Field | Value |
   |---|---|
   | Build Command | `pip install -r requirements.txt` |
   | Start Command | `gunicorn src.app.app:app --bind 0.0.0.0:$PORT --workers 1 --timeout 120` |
   | Health Check Path | `/health` |

4. Add the following environment variables in the Render dashboard:

   | Variable | Value |
   |---|---|
   | `CODESAGE_GITHUB_TOKEN` | Your GitHub PAT |
   | `CODESAGE_GITHUB_WEBHOOK_SECRET` | A random secret string |
   | `CODESAGE_ENABLE_MODEL` | `0` |
   | `CODESAGE_MAX_INLINE_COMMENTS` | `20` |

5. After deploy, Render provides a public URL such as:

   ```
   https://codesage-ai.onrender.com
   ```

6. In your GitHub repository settings, create a webhook:

   | Field | Value |
   |---|---|
   | Payload URL | `https://YOUR-RENDER-URL/api/github/webhook` |
   | Content type | `application/json` |
   | Secret | Same value as `CODESAGE_GITHUB_WEBHOOK_SECRET` |
   | Events | Pull requests |

### Publish the VS Code extension

```powershell
cd vscode-extension
vsce package
vsce publish
```

> Requires publisher credentials configured in `vsce`.

---

## Manual End-to-End Test

1. Start the backend: `.\venv\python.exe -m src.app.app`
2. Launch the extension: press `F5` in VS Code
3. Open a Python file containing a risky pattern, e.g. `eval(user_input)`
4. Run `CodeSage: Analyze Code`
5. Confirm the side panel groups findings into **Errors**, **Warnings**, and **Suggestions**
6. Confirm inline highlights use red, yellow, and blue severity colors
7. Use **View Details**, **Reject**, and **Accept Fix** to interact with findings

---

## Security

- Never commit `CODESAGE_GITHUB_TOKEN` or `CODESAGE_GITHUB_WEBHOOK_SECRET` to version control
- Always set secrets as environment variables on your deployment platform
- The webhook secret validates that incoming events originate from GitHub

---

## License

MIT
