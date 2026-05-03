const vscode = require("vscode");

const diagnostics = vscode.languages.createDiagnosticCollection("CodeSage");
const state = {
  byUri: new Map(),
  lastAnalysis: new Map(),
  reviewDocs: new Map(),
  panel: undefined,
  panelDocumentUri: undefined,
  output: undefined,
  statusBar: undefined,
  decorations: undefined,
};

function activate(context) {
  state.output = vscode.window.createOutputChannel("CodeSage");
  state.output.appendLine("CodeSage extension activated.");

  state.statusBar = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Left, 100);
  state.statusBar.text = "$(search) CodeSage";
  state.statusBar.tooltip = "Analyze current file with CodeSage";
  state.statusBar.command = "codesage.analyzeCode";
  state.statusBar.show();

  state.decorations = createDecorations();

  context.subscriptions.push(state.output, state.statusBar, diagnostics);
  context.subscriptions.push(vscode.workspace.registerTextDocumentContentProvider("codesage-review", {
    provideTextDocumentContent(uri) {
      return state.reviewDocs.get(uri.toString()) || "";
    },
  }));
  Object.values(state.decorations).forEach((decoration) => context.subscriptions.push(decoration));

  context.subscriptions.push(vscode.commands.registerCommand("codesage.analyzeCode", analyzeActiveFile));
  context.subscriptions.push(vscode.commands.registerCommand("codesage.applyAllFixes", applyAllFixes));
  context.subscriptions.push(vscode.commands.registerCommand("codesage.generatePrReview", generatePrReview));
  context.subscriptions.push(vscode.commands.registerCommand("codesage.reviewWithCodeSage", generatePrReview));
  context.subscriptions.push(vscode.commands.registerCommand("codesage.reviewGitHubPullRequest", reviewGitHubPullRequest));
  context.subscriptions.push(vscode.commands.registerCommand("codesage.acceptFix", openAndAcceptFix));

  context.subscriptions.push(vscode.languages.registerHoverProvider({ scheme: "file" }, {
    provideHover(document, position) {
      const suggestions = openSuggestions(document).filter((item) => item.line - 1 === position.line);
      if (!suggestions.length) return undefined;

      const md = new vscode.MarkdownString();
      md.isTrusted = true;
      suggestions.slice(0, 3).forEach((item) => {
        const icon = item.group === "error" ? "$(error)" : item.group === "warning" ? "$(warning)" : "$(lightbulb)";
        md.appendMarkdown(`${icon} **${item.title}**\n\n`);
        md.appendMarkdown(`${shortText(item.description, 180)}\n\n`);
        md.appendMarkdown(`[View Details](command:codesage.showDetails?${encodeURIComponent(JSON.stringify([document.uri.toString(), item.id]))})`);
        if (item.fix_edit) {
          md.appendMarkdown(` - [Accept Fix](command:codesage.acceptFix?${encodeURIComponent(JSON.stringify([document.uri.toString(), item.id]))})`);
        }
        md.appendMarkdown("\n\n");
      });
      return new vscode.Hover(md);
    },
  }));

  context.subscriptions.push(vscode.commands.registerCommand("codesage.showDetails", async (uriString, suggestionId) => {
    const document = await vscode.workspace.openTextDocument(vscode.Uri.parse(uriString));
    showDetails(document, suggestionId);
  }));
}

function deactivate() {}

async function analyzeActiveFile() {
  const editor = vscode.window.activeTextEditor;
  if (!editor) {
    vscode.window.showWarningMessage("Open a file before running CodeSage.");
    return;
  }

  const document = editor.document;
  const uri = document.uri.toString();

  try {
    showLoadingPanel(document);
    state.statusBar.text = "$(sync~spin) CodeSage";
    state.output.appendLine(`Analyzing ${workspacePath(document)}...`);

    const response = await vscode.window.withProgress({
      location: vscode.ProgressLocation.Notification,
      title: "CodeSage analyzing code",
      cancellable: false,
    }, () => postJson("/api/analyze", {
      code: document.getText(),
      filename: workspacePath(document),
    }));

    const analysis = response.data;
    const suggestions = normalizeSuggestions(analysis, document);
    state.byUri.set(uri, suggestions);
    state.lastAnalysis.set(uri, analysis);

    refreshDocumentState(document);
    state.output.appendLine(`Analysis complete. ${suggestions.length} review items found.`);
    vscode.window.showInformationMessage(`CodeSage found ${suggestions.length} review items.`);
  } catch (error) {
    state.output.appendLine(`Analysis failed: ${error.message}`);
    showErrorPanel(error);
    vscode.window.showErrorMessage(`CodeSage analysis failed: ${error.message}`);
  } finally {
    state.statusBar.text = "$(search) CodeSage";
  }
}

async function generatePrReview() {
  const editor = vscode.window.activeTextEditor;
  if (!editor) {
    vscode.window.showWarningMessage("Open a file before generating a PR review.");
    return;
  }

  try {
    const document = editor.document;
    const response = await postJson("/api/pr-review", {
      code: document.getText(),
      filename: workspacePath(document),
    });
    showPrPanel(document, response.data);
  } catch (error) {
    vscode.window.showErrorMessage(`CodeSage PR review failed: ${error.message}`);
  }
}

async function reviewGitHubPullRequest() {
  try {
    const owner = await vscode.window.showInputBox({ prompt: "GitHub owner or organization", ignoreFocusOut: true });
    if (!owner) return;
    const repo = await vscode.window.showInputBox({ prompt: "GitHub repository name", ignoreFocusOut: true });
    if (!repo) return;
    const pullNumberRaw = await vscode.window.showInputBox({ prompt: "Pull request number", ignoreFocusOut: true, validateInput: (value) => /^\d+$/.test(value) ? undefined : "Enter a numeric PR number." });
    if (!pullNumberRaw) return;
    const postChoice = await vscode.window.showQuickPick(["Preview only", "Post comments to GitHub"], {
      placeHolder: "Choose how CodeSage should handle this PR review",
      ignoreFocusOut: true,
    });
    if (!postChoice) return;

    const response = await vscode.window.withProgress({
      location: vscode.ProgressLocation.Notification,
      title: `CodeSage reviewing ${owner}/${repo}#${pullNumberRaw}`,
      cancellable: false,
    }, () => postJson("/api/github/pr-review", {
      owner,
      repo,
      pull_number: Number(pullNumberRaw),
      post_comments: postChoice === "Post comments to GitHub",
    }));

    showGitHubPrPanel(response.data);
  } catch (error) {
    vscode.window.showErrorMessage(`CodeSage GitHub PR review failed: ${error.message}`);
  }
}

async function openAndAcceptFix(uriString, suggestionId) {
  const document = await vscode.workspace.openTextDocument(vscode.Uri.parse(uriString));
  await vscode.window.showTextDocument(document);
  await acceptFix(document, suggestionId);
}

async function acceptFix(document, suggestionId) {
  const suggestion = openSuggestions(document).find((item) => item.id === suggestionId);
  if (!suggestion || !suggestion.fix_edit) {
    vscode.window.showInformationMessage("This review item has no safe automatic patch. Open View Details and apply the guidance manually.");
    return false;
  }

  await openReviewChangeDiff(document, suggestion);
  const choice = await vscode.window.showInformationMessage(
    `Review the proposed CodeSage change for line ${suggestion.fix_edit.start_line}.`,
    { modal: true },
    "Apply Fix",
    "Cancel"
  );

  if (choice !== "Apply Fix") {
    return false;
  }

  const insertedImport = Boolean(suggestion.fix_edit.additional_import && !document.getText().includes(suggestion.fix_edit.additional_import));
  const applied = await applyFixEdit(document, suggestion);
  if (!applied) return false;

  suggestion.status = "accepted";
  await recordAction(suggestion.id, "accepted");
  await highlightAppliedFix(document, suggestion, insertedImport);
  refreshDocumentState(document);
  vscode.window.showInformationMessage(`Applied CodeSage fix: ${suggestion.title}`);
  return true;
}

async function rejectSuggestion(document, suggestionId) {
  const suggestion = openSuggestions(document).find((item) => item.id === suggestionId);
  if (!suggestion) return;

  suggestion.status = "rejected";
  await recordAction(suggestion.id, "rejected");
  refreshDocumentState(document);
}

async function markResolved(document, suggestionId) {
  const suggestion = openSuggestions(document).find((item) => item.id === suggestionId);
  if (!suggestion) return;

  suggestion.status = "resolved";
  await recordAction(suggestion.id, "resolved");
  refreshDocumentState(document);
}

async function jumpToLine(document, suggestionId) {
  const suggestion = openSuggestions(document).find((item) => item.id === suggestionId);
  if (!suggestion) return;

  const editor = await vscode.window.showTextDocument(document, { preview: false });
  const position = new vscode.Position(Math.max(0, suggestion.line - 1), Math.max(0, suggestion.column || 0));
  editor.selection = new vscode.Selection(position, position);
  editor.revealRange(new vscode.Range(position, position), vscode.TextEditorRevealType.InCenter);
}

async function applyAllFixes() {
  const editor = vscode.window.activeTextEditor;
  if (!editor) {
    vscode.window.showWarningMessage("Open a file before applying fixes.");
    return;
  }

  const document = editor.document;
  await applyAllFixesForDocument(document);
}

async function applyAllFixesForDocument(document) {
  const suggestions = openSuggestions(document)
    .filter((item) => item.fix_edit)
    .sort((a, b) => b.fix_edit.start_line - a.fix_edit.start_line);

  if (!suggestions.length) {
    vscode.window.showInformationMessage("No safe CodeSage fixes are available.");
    return;
  }

  const choice = await vscode.window.showWarningMessage(
    `Apply ${suggestions.length} safe CodeSage fixes to this file?`,
    { modal: true },
    "Apply All"
  );
  if (choice !== "Apply All") return;

  let applied = 0;
  for (const suggestion of suggestions) {
    if (await applyFixEdit(document, suggestion, { addImport: false, save: false })) {
      suggestion.status = "accepted";
      await recordAction(suggestion.id, "accepted");
      applied += 1;
    }
  }

  await applyMissingImports(document, suggestions);
  await document.save();
  refreshDocumentState(document);
  vscode.window.showInformationMessage(`Applied ${applied} CodeSage fixes.`);
}

async function applyFixEdit(document, suggestion, options = {}) {
  const addImport = options.addImport !== false;
  const save = options.save !== false;
  const edit = suggestion.fix_edit;
  const start = edit.start_line - 1;
  const end = edit.end_line - 1;

  if (start < 0 || end >= document.lineCount) {
    vscode.window.showErrorMessage("CodeSage fix is outside the current file.");
    return false;
  }

  const current = document.getText(new vscode.Range(start, 0, end, document.lineAt(end).range.end.character));
  if (edit.original && current.trim() !== edit.original.trim()) {
    vscode.window.showErrorMessage("CodeSage skipped this fix because the code changed after analysis.");
    return false;
  }

  const workspaceEdit = new vscode.WorkspaceEdit();
  workspaceEdit.replace(document.uri, new vscode.Range(start, 0, end, document.lineAt(end).range.end.character), edit.replacement);

  if (addImport && edit.additional_import && !document.getText().includes(edit.additional_import)) {
    workspaceEdit.insert(document.uri, new vscode.Position(0, 0), `${edit.additional_import}\n`);
  }

  const applied = await vscode.workspace.applyEdit(workspaceEdit);
  if (applied && save) await document.save();
  return applied;
}

async function applyMissingImports(document, suggestions) {
  const imports = [...new Set(suggestions.map((item) => item.fix_edit && item.fix_edit.additional_import).filter(Boolean))]
    .filter((line) => !document.getText().includes(line));
  if (!imports.length) return;

  const workspaceEdit = new vscode.WorkspaceEdit();
  workspaceEdit.insert(document.uri, new vscode.Position(0, 0), `${imports.join("\n")}\n`);
  await vscode.workspace.applyEdit(workspaceEdit);
}

async function openReviewChangeDiff(document, suggestion) {
  const originalText = document.getText();
  const proposedText = buildProposedDocumentText(document, suggestion);
  const safeTitle = encodeURIComponent(suggestion.id);
  const originalUri = vscode.Uri.parse(`codesage-review:/original/${safeTitle}/${encodeURIComponent(document.fileName)}`);
  const proposedUri = vscode.Uri.parse(`codesage-review:/proposed/${safeTitle}/${encodeURIComponent(document.fileName)}`);

  state.reviewDocs.set(originalUri.toString(), originalText);
  state.reviewDocs.set(proposedUri.toString(), proposedText);

  await vscode.commands.executeCommand(
    "vscode.diff",
    originalUri,
    proposedUri,
    `CodeSage Review Change: ${suggestion.title}`,
    { preview: false, viewColumn: vscode.ViewColumn.Beside }
  );
}

function buildProposedDocumentText(document, suggestion) {
  const edit = suggestion.fix_edit;
  const lines = document.getText().split(/\r?\n/);
  const start = edit.start_line - 1;
  const end = edit.end_line - 1;

  if (start < 0 || end >= lines.length) {
    return document.getText();
  }

  const replacementLines = String(edit.replacement || "").split(/\r?\n/);
  lines.splice(start, end - start + 1, ...replacementLines);

  if (edit.additional_import && !lines.some((line) => line.trim() === edit.additional_import.trim())) {
    lines.unshift(edit.additional_import);
  }

  return lines.join(document.eol === vscode.EndOfLine.CRLF ? "\r\n" : "\n");
}

async function previewFix(document, suggestion) {
  const editor = await vscode.window.showTextDocument(document, { preview: false });
  const range = fixRange(document, suggestion);
  if (!range) return;

  editor.selection = new vscode.Selection(range.start, range.end);
  editor.revealRange(range, vscode.TextEditorRevealType.InCenter);
  editor.setDecorations(state.decorations.preview, [{
    range,
    hoverMessage: replacementPreview(suggestion),
    renderOptions: {
      after: {
        contentText: `  -> ${shortText(oneLineReplacement(suggestion), 120)}`,
      },
    },
  }]);
}

function clearPreview(document) {
  const editor = vscode.window.visibleTextEditors.find((item) => item.document.uri.toString() === document.uri.toString());
  if (editor) {
    editor.setDecorations(state.decorations.preview, []);
  }
}

async function highlightAppliedFix(document, suggestion, insertedImport = false) {
  const editor = await vscode.window.showTextDocument(document, { preview: false });
  const start = Math.max(0, suggestion.fix_edit.start_line - 1 + (insertedImport ? 1 : 0));
  if (start >= document.lineCount) return;

  const range = new vscode.Range(start, 0, start, Math.max(1, document.lineAt(start).range.end.character));
  editor.revealRange(range, vscode.TextEditorRevealType.InCenter);
  editor.setDecorations(state.decorations.applied, [{ range, hoverMessage: "CodeSage fix applied here." }]);

  setTimeout(() => {
    const activeEditor = vscode.window.visibleTextEditors.find((item) => item.document.uri.toString() === document.uri.toString());
    if (activeEditor) {
      activeEditor.setDecorations(state.decorations.applied, []);
    }
  }, 4500);
}

function fixRange(document, suggestion) {
  const edit = suggestion.fix_edit;
  const start = edit.start_line - 1;
  const end = edit.end_line - 1;
  if (start < 0 || end >= document.lineCount) return undefined;
  return new vscode.Range(start, 0, end, document.lineAt(end).range.end.character);
}

function replacementPreview(suggestion) {
  const importText = suggestion.fix_edit.additional_import ? `\nImport added if missing: ${suggestion.fix_edit.additional_import}` : "";
  return `CodeSage will replace this line with:\n${suggestion.fix_edit.replacement}${importText}`;
}

function oneLineReplacement(suggestion) {
  const importText = suggestion.fix_edit.additional_import ? `${suggestion.fix_edit.additional_import}; ` : "";
  return `${importText}${String(suggestion.fix_edit.replacement || "").replace(/\s+/g, " ").trim()}`;
}

function refreshDocumentState(document) {
  const suggestions = openSuggestions(document);
  setDiagnostics(document, suggestions);
  setDecorations(document, suggestions);
  showReportPanel(document);
}

function setDiagnostics(document, suggestions) {
  const items = suggestions.map((item) => {
    const range = rangeForItem(document, item);
    if (!range) return undefined;
    const diagnostic = new vscode.Diagnostic(range, item.title, toDiagnosticSeverity(item.severity));
    diagnostic.source = "CodeSage";
    diagnostic.code = item.id;
    return diagnostic;
  }).filter(Boolean);
  diagnostics.set(document.uri, items);
}

function setDecorations(document, suggestions) {
  const editor = vscode.window.visibleTextEditors.find((item) => item.document.uri.toString() === document.uri.toString());
  if (!editor) return;

  const grouped = { error: [], warning: [], suggestion: [] };
  suggestions.forEach((item) => {
    const range = rangeForItem(document, item);
    if (range) grouped[item.group].push({ range, hoverMessage: `${item.title}: ${item.description}` });
  });

  editor.setDecorations(state.decorations.error, grouped.error);
  editor.setDecorations(state.decorations.warning, grouped.warning);
  editor.setDecorations(state.decorations.suggestion, grouped.suggestion);
}

function createDecorations() {
  return {
    error: vscode.window.createTextEditorDecorationType({
      backgroundColor: "rgba(248, 81, 73, 0.16)",
      border: "1px solid rgba(248, 81, 73, 0.55)",
      overviewRulerColor: "#f85149",
      overviewRulerLane: vscode.OverviewRulerLane.Right,
    }),
    warning: vscode.window.createTextEditorDecorationType({
      backgroundColor: "rgba(210, 153, 34, 0.16)",
      border: "1px solid rgba(210, 153, 34, 0.55)",
      overviewRulerColor: "#d29922",
      overviewRulerLane: vscode.OverviewRulerLane.Right,
    }),
    suggestion: vscode.window.createTextEditorDecorationType({
      backgroundColor: "rgba(88, 166, 255, 0.14)",
      border: "1px solid rgba(88, 166, 255, 0.5)",
      overviewRulerColor: "#58a6ff",
      overviewRulerLane: vscode.OverviewRulerLane.Right,
    }),
    preview: vscode.window.createTextEditorDecorationType({
      backgroundColor: "rgba(248, 81, 73, 0.18)",
      border: "1px solid rgba(248, 81, 73, 0.7)",
      overviewRulerColor: "#f85149",
      overviewRulerLane: vscode.OverviewRulerLane.Right,
      after: {
        margin: "0 0 0 1.5rem",
        color: "#3fb950",
        fontWeight: "600",
      },
    }),
    applied: vscode.window.createTextEditorDecorationType({
      backgroundColor: "rgba(63, 185, 80, 0.2)",
      border: "1px solid rgba(63, 185, 80, 0.75)",
      overviewRulerColor: "#3fb950",
      overviewRulerLane: vscode.OverviewRulerLane.Right,
    }),
  };
}

function showReportPanel(document) {
  ensureReportPanel(document);
  state.panel.webview.html = reportHtml(document);
}

function showLoadingPanel(document) {
  ensureReportPanel(document);
  state.panel.webview.html = htmlPage(`<div class="loading"><div class="spinner"></div><h1>Analyzing ${escapeHtml(workspacePath(document))}</h1><p>Running static checks and AI review...</p></div>`);
}

function ensureReportPanel(document) {
  state.panelDocumentUri = document.uri.toString();
  if (state.panel) {
    return state.panel;
  }

  state.panel = vscode.window.createWebviewPanel("codesageReport", "CodeSage Review", vscode.ViewColumn.Beside, { enableScripts: true });
  state.panel.onDidDispose(() => {
    state.panel = undefined;
    state.panelDocumentUri = undefined;
  });
  state.panel.webview.onDidReceiveMessage(async (message) => {
    const doc = await documentFromMessage(message, state.panelDocumentUri);
    if (!doc) return;

    if (message.command === "accept") await acceptFix(doc, message.id);
    if (message.command === "reject") await rejectSuggestion(doc, message.id);
    if (message.command === "resolved") await markResolved(doc, message.id);
    if (message.command === "details") showDetails(doc, message.id);
    if (message.command === "manual") await openManualFix(doc, message.id);
    if (message.command === "jump") await jumpToLine(doc, message.id);
    if (message.command === "applyAll") await applyAllFixesForDocument(doc);
  });

  return state.panel;
}

function showErrorPanel(error) {
  if (!state.panel) return;
  state.panel.webview.html = htmlPage(`<section class="empty error-state"><h1>Analysis failed</h1><p>${escapeHtml(error.message)}</p></section>`);
}

function showDetails(document, suggestionId) {
  const suggestion = openSuggestions(document).find((item) => item.id === suggestionId);
  if (!suggestion) return;

  const fixStatus = suggestion.fix_edit
    ? "A reviewable code change is available. Click Review Change to inspect the diff before applying it."
    : "No safe automatic patch is available for this item. CodeSage is reporting this as a manual fix because applying a blind overwrite could break surrounding logic.";

  vscode.window.showInformationMessage(
    `${suggestion.title}\n\n${suggestion.description}\n\nSuggested action: ${suggestion.fix || "Review this code path manually."}\n\n${fixStatus}`,
    { modal: true }
  );
}

function showPrDetails(comments, suggestionId) {
  const comment = comments.find((item) => item.id === suggestionId);
  if (!comment) return;

  const fixStatus = comment.fix_edit
    ? "A reviewable code change is available. Click Review Change to inspect the diff before applying it."
    : "No safe automatic patch is available for this PR comment. Treat it as a manual review note.";

  vscode.window.showInformationMessage(
    `${comment.title}\n\n${comment.description}\n\nSuggested action: ${comment.fix || "Review this PR comment manually."}\n\n${fixStatus}`,
    { modal: true }
  );
}

function showPrPanel(document, review) {
  const panel = vscode.window.createWebviewPanel("codesagePrReview", "CodeSage PR Review", vscode.ViewColumn.Beside, { enableScripts: true });
  const comments = normalizePrComments(review, document);
  mergePrSuggestions(document, comments);
  panel.webview.html = prHtml(review, comments);
  panel.webview.onDidReceiveMessage(async (message) => {
    if (message.command === "jump") await jumpToLine(document, message.id);
    if (message.command === "details") showPrDetails(comments, message.id);
    if (message.command === "accept") {
      const accepted = await acceptFix(document, message.id);
      const item = comments.find((comment) => comment.id === message.id);
      if (accepted && item) item.status = "accepted";
    }
    if (message.command === "manual") await openManualFix(document, message.id);
    if (message.command === "ignore") {
      const item = comments.find((comment) => comment.id === message.id);
      if (item) item.status = "ignored";
      await recordAction(message.id, "ignored");
    }
    if (message.command === "resolved") {
      const item = comments.find((comment) => comment.id === message.id);
      if (item) item.status = "resolved";
      await recordAction(message.id, "resolved");
    }
    panel.webview.html = prHtml(review, comments);
  });
}

function showGitHubPrPanel(review) {
  const panel = vscode.window.createWebviewPanel("codesageGitHubPrReview", "CodeSage GitHub PR Review", vscode.ViewColumn.Beside, { enableScripts: true });
  panel.webview.html = githubPrHtml(review);
}

async function openManualFix(document, suggestionId) {
  await jumpToLine(document, suggestionId);
  showDetails(document, suggestionId);
}

function normalizeSuggestions(analysis, document) {
  const raw = [...(analysis.issues || [])];
  const seen = new Set();

  return raw
    .filter((item) => item && Number.isInteger(item.line) && item.line > 0)
    .map((item, index) => {
      const severity = item.severity || "medium";
      return {
        id: item.id || `${document.uri.toString()}:${item.line}:${index}`,
        file: item.file || workspacePath(document),
        line: item.line,
        end_line: item.end_line || item.line,
        column: item.column || 0,
        severity,
        group: groupForSeverity(severity),
        category: item.type || item.category || "suggestion",
        title: item.message || "CodeSage review item",
        description: item.explanation || item.fix || item.message || "",
        fix: item.fix || "",
        fix_edit: item.fix_edit || undefined,
        confidence: item.confidence || 0,
        source: item.source || "static",
        status: item.status || "open",
      };
    })
    .filter((item) => {
      const key = `${item.line}:${item.category}:${normalizeTitle(item.title)}`;
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    });
}

function normalizePrComments(review, document) {
  return (review.inline_comments || []).map((item, index) => {
    const severity = item.severity || "medium";
    return {
      id: item.id || `${document.uri.toString()}:pr:${item.line}:${index}`,
      file: item.file || workspacePath(document),
      line: item.line || 1,
      end_line: item.end_line || item.line || 1,
      column: item.column || 0,
      severity,
      group: groupForSeverity(severity),
      category: item.category || "pr-comment",
      title: item.message || "PR review comment",
      description: item.explanation || item.suggestion || item.message || "",
      fix: item.suggestion || "",
      fix_edit: item.fix_edit || undefined,
      confidence: item.confidence || 0,
      source: "pr",
      status: item.status || "open",
    };
  });
}

function mergePrSuggestions(document, comments) {
  const uri = document.uri.toString();
  const existing = state.byUri.get(uri) || [];
  const byId = new Map(existing.map((item) => [item.id, item]));
  comments.forEach((comment) => byId.set(comment.id, comment));
  state.byUri.set(uri, [...byId.values()]);
  setDiagnostics(document, openSuggestions(document));
  setDecorations(document, openSuggestions(document));
}

async function documentFromMessage(message, fallbackUri) {
  const uriString = message.uri || fallbackUri;
  if (uriString) {
    return vscode.workspace.openTextDocument(vscode.Uri.parse(uriString));
  }
  return vscode.window.activeTextEditor ? vscode.window.activeTextEditor.document : undefined;
}

async function postJson(path, body) {
  const baseUrl = vscode.workspace.getConfiguration("codesage").get("backendUrl").replace(/\/$/, "");
  const response = await fetch(`${baseUrl}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

  if (!response.ok) throw new Error(`CodeSage backend returned ${response.status}`);
  const payload = await response.json();
  if (!payload.success) throw new Error(payload.message || "CodeSage request failed");
  return payload;
}

async function recordAction(suggestionId, action) {
  try {
    await postJson("/api/suggestions/action", { suggestion_id: suggestionId, action });
  } catch (_) {
    // Local review actions continue to work if action logging is unavailable.
  }
}

function reportHtml(document) {
  const suggestions = openSuggestions(document);
  const analysis = state.lastAnalysis.get(document.uri.toString()) || {};
  const counts = countGroups(suggestions);
  const safeFixes = suggestions.filter((item) => item.fix_edit).length;
  const score = analysis.summary && Number.isInteger(analysis.summary.score) ? analysis.summary.score : "--";

  return htmlPage(`
    <header class="topbar">
      <div>
        <h1>CodeSage Review</h1>
        <p>${escapeHtml(workspacePath(document))}</p>
      </div>
      <button class="primary" onclick="send('applyAll')" ${safeFixes ? "" : "disabled"}>Apply All</button>
    </header>

    <section class="summary-grid">
      <div class="metric"><strong>${score}</strong><span>Score</span></div>
      <div class="metric error"><strong>${counts.error}</strong><span>Errors</span></div>
      <div class="metric warning"><strong>${counts.warning}</strong><span>Warnings</span></div>
      <div class="metric suggestion"><strong>${counts.suggestion}</strong><span>Suggestions</span></div>
    </section>

    ${sectionHtml("Errors", "error", suggestions)}
    ${sectionHtml("Warnings", "warning", suggestions)}
    ${sectionHtml("Suggestions", "suggestion", suggestions)}
    ${suggestions.length ? "" : `<section class="empty"><h2>No open review items</h2><p>This file looks clean.</p></section>`}
  `);
}

function sectionHtml(titleText, group, suggestions) {
  const items = suggestions.filter((item) => item.group === group);
  return `
    <section class="review-section">
      <button class="section-header" onclick="toggleSection('${group}')">
        <span>${escapeHtml(titleText)}</span>
        <span class="count">${items.length}</span>
      </button>
      <div id="section-${group}" class="section-body">
        ${items.map(issueCard).join("") || `<p class="empty-line">No ${escapeHtml(titleText.toLowerCase())}.</p>`}
      </div>
    </section>
  `;
}

function issueCard(item) {
  const canFix = Boolean(item.fix_edit);
  const confidence = item.confidence ? `<span>${Math.round(item.confidence * 100)}% confidence</span>` : "";
  return `
    <article class="card ${escapeHtml(item.group)}">
      <button class="line" onclick="send('jump','${item.id}')">Line ${item.line}</button>
      <div class="card-body">
        <div class="meta">
          <span class="badge ${escapeHtml(item.group)}">${labelForGroup(item.group)}</span>
          <span>${escapeHtml(item.category)}</span>
          ${confidence}
          ${canFix ? `<span class="fixable">Safe fix</span>` : `<span>Manual review</span>`}
        </div>
        <h2>${escapeHtml(item.title)}</h2>
        <p>${escapeHtml(shortText(item.description || item.fix, 240))}</p>
        ${canFix ? diffPreviewHtml(item) : ""}
        <div class="actions">
          ${canFix
            ? `<button class="primary" onclick="send('accept','${item.id}')">Review Change</button>`
            : `<button onclick="send('manual','${item.id}')" title="Jump to the affected line and show the manual review guidance">Manual Fix</button>`}
          <button onclick="send('reject','${item.id}')">Reject</button>
          <button onclick="send('details','${item.id}')">View Details</button>
        </div>
      </div>
    </article>
  `;
}

function prHtml(review, comments) {
  const openComments = comments.filter((item) => item.status === "open");
  const counts = countGroups(openComments);
  return htmlPage(`
    <header class="topbar"><div><h1>PR Review</h1><p>${escapeHtml(review.file || "")}</p></div></header>
    <section class="summary-grid">
      <div class="metric error"><strong>${counts.error}</strong><span>Errors</span></div>
      <div class="metric warning"><strong>${counts.warning}</strong><span>Warnings</span></div>
      <div class="metric suggestion"><strong>${counts.suggestion}</strong><span>Suggestions</span></div>
      <div class="metric"><strong>${openComments.filter((item) => item.fix_edit).length}</strong><span>Fixable</span></div>
    </section>
    <section class="review-section">
      <button class="section-header"><span>Summary</span></button>
      <div class="section-body">
        ${Object.entries(review.summary || {}).map(([name, items]) => `
          <h2>${escapeHtml(title(name))}</h2>
          ${items.length ? items.map((item) => `<p>Line ${item.line}: ${escapeHtml(item.message)}</p>`).join("") : `<p class="empty-line">None</p>`}
        `).join("")}
      </div>
    </section>
    <section class="review-section">
      <button class="section-header"><span>Inline Comments</span><span class="count">${openComments.length}</span></button>
      <div class="section-body">${openComments.map(prCard).join("") || `<p class="empty-line">No open comments.</p>`}</div>
    </section>
  `);
}

function githubPrHtml(review) {
  const summary = review.summary_of_issues || {};
  const comments = review.inline_comments || [];
  return htmlPage(`
    <header class="topbar">
      <div>
        <h1>GitHub PR Review</h1>
        <p>${escapeHtml(review.repository || "")}#${escapeHtml(review.pull_number || "")}</p>
      </div>
    </header>
    <section class="summary-grid">
      <div class="metric"><strong>${escapeHtml(summary.total_files_reviewed || 0)}</strong><span>Files</span></div>
      <div class="metric error"><strong>${escapeHtml(summary.total_inline_comments || 0)}</strong><span>Comments</span></div>
      <div class="metric"><strong>${escapeHtml((review.posted && review.posted.inline || []).length || 0)}</strong><span>Posted</span></div>
      <div class="metric suggestion"><strong>${escapeHtml(review.status || "preview")}</strong><span>Status</span></div>
    </section>
    <section class="review-section">
      <button class="section-header"><span>Inline Comments</span><span class="count">${comments.length}</span></button>
      <div class="section-body">
        ${comments.map((item) => `
          <article class="card ${escapeHtml(groupForSeverity(item.severity))}">
            <button class="line">Line ${escapeHtml(item.github && item.github.line || item.line)}</button>
            <div class="card-body">
              <div class="meta">
                <span>${escapeHtml(item.file)}</span>
                <span>${escapeHtml(item.category)}</span>
                <span>${item.github && item.github.postable ? "GitHub-ready" : "Preview only"}</span>
              </div>
              <h2>${escapeHtml(item.message)}</h2>
              <p>${escapeHtml(shortText(item.review_comment || item.explanation, 260))}</p>
              ${item.github_suggestion ? `<div class="mini-diff"><div class="diff-title">GitHub suggestion</div><div class="diff-row add"><span class="ln">+</span><code>${escapeHtml(item.github_suggestion)}</code></div></div>` : ""}
            </div>
          </article>
        `).join("") || `<p class="empty-line">No inline comments prepared.</p>`}
      </div>
    </section>
  `);
}

function prCard(item) {
  return `
    <article class="card ${escapeHtml(groupForSeverity(item.severity))}">
      <button class="line" onclick="send('jump','${item.id}')">Line ${item.line}</button>
      <div class="card-body">
        <div class="meta"><span>${escapeHtml(item.file)}</span><span>${escapeHtml(item.category)}</span></div>
        <h2>${escapeHtml(item.title)}</h2>
        <p>${escapeHtml(shortText(item.description || item.fix, 240))}</p>
        ${item.fix_edit ? diffPreviewHtml(item) : ""}
        <div class="actions">
          ${item.fix_edit
            ? `<button class="primary" onclick="send('accept','${item.id}')">Review Change</button>`
            : `<button onclick="send('manual','${item.id}')" title="Jump to the affected line and show the manual review guidance">Manual Fix</button>`}
          <button onclick="send('ignore','${item.id}')">Ignore</button>
          <button onclick="send('resolved','${item.id}')">Mark Resolved</button>
          <button onclick="send('details','${item.id}')">View Details</button>
        </div>
      </div>
    </article>
  `;
}

function diffPreviewHtml(item) {
  const edit = item.fix_edit;
  const originalLines = splitDiffLines(edit.original);
  const replacementLines = splitDiffLines(edit.replacement);
  const startLine = edit.start_line || item.line;
  const endLine = edit.end_line || startLine;
  const header = startLine === endLine
    ? `Review change - line ${startLine}`
    : `Review change - lines ${startLine}-${endLine}`;
  const importLine = edit.additional_import
    ? `<div class="diff-row add"><span class="ln">+</span><code>+ ${escapeHtml(edit.additional_import)}</code></div>`
    : "";

  return `
    <div class="mini-diff">
      <div class="diff-title">${escapeHtml(header)}</div>
      ${originalLines.map((line, index) => `
        <div class="diff-row del">
          <span class="ln">${startLine + index}</span>
          <code>- ${escapeHtml(line)}</code>
        </div>
      `).join("")}
      ${importLine}
      ${replacementLines.map((line, index) => `
        <div class="diff-row add">
          <span class="ln">${startLine + index}</span>
          <code>+ ${escapeHtml(line)}</code>
        </div>
      `).join("")}
    </div>
  `;
}

function splitDiffLines(value) {
  const text = String(value || "");
  return text.split(/\r?\n/);
}

function htmlPage(body) {
  return `<!doctype html>
  <html>
    <head>
      <meta charset="utf-8">
      <style>
        :root {
          --error: #f85149;
          --warning: #d29922;
          --suggestion: #58a6ff;
          --muted: var(--vscode-descriptionForeground);
          --border: var(--vscode-panel-border);
          --surface: var(--vscode-editorWidget-background);
        }
        * { box-sizing: border-box; }
        body { margin: 0; padding: 16px; color: var(--vscode-foreground); font-family: var(--vscode-font-family); background: var(--vscode-editor-background); }
        .topbar { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding-bottom: 14px; border-bottom: 1px solid var(--border); }
        h1 { margin: 0; font-size: 18px; font-weight: 650; }
        h2 { margin: 6px 0; font-size: 13px; line-height: 1.35; }
        p { margin: 0; color: var(--muted); line-height: 1.45; }
        button { border: 1px solid var(--vscode-button-border, transparent); color: var(--vscode-button-secondaryForeground); background: var(--vscode-button-secondaryBackground); padding: 5px 9px; border-radius: 4px; cursor: pointer; font: inherit; }
        button:hover { background: var(--vscode-button-secondaryHoverBackground); }
        button:disabled { opacity: 0.42; cursor: not-allowed; }
        .primary { color: var(--vscode-button-foreground); background: var(--vscode-button-background); border-color: transparent; }
        .primary:hover { background: var(--vscode-button-hoverBackground); }
        .summary-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 8px; margin: 14px 0; }
        .metric { padding: 10px; border: 1px solid var(--border); background: var(--surface); border-radius: 6px; }
        .metric strong { display: block; font-size: 19px; line-height: 1; }
        .metric span { color: var(--muted); font-size: 11px; }
        .metric.error strong { color: var(--error); }
        .metric.warning strong { color: var(--warning); }
        .metric.suggestion strong { color: var(--suggestion); }
        .review-section { margin-top: 12px; border: 1px solid var(--border); border-radius: 6px; overflow: hidden; }
        .section-header { width: 100%; display: flex; justify-content: space-between; align-items: center; border: 0; border-radius: 0; background: var(--vscode-sideBarSectionHeader-background); color: var(--vscode-foreground); padding: 9px 11px; font-weight: 650; }
        .count { color: var(--muted); font-weight: 500; }
        .section-body { padding: 8px; }
        .card { display: grid; grid-template-columns: 62px minmax(0, 1fr); gap: 10px; padding: 10px 0; border-bottom: 1px solid var(--border); }
        .card:last-child { border-bottom: 0; }
        .line { align-self: start; text-align: center; color: var(--muted); background: transparent; border: 1px solid var(--border); border-radius: 4px; padding: 5px 4px; font-size: 11px; }
        .card-body { min-width: 0; }
        .meta { display: flex; gap: 7px; flex-wrap: wrap; align-items: center; color: var(--muted); font-size: 11px; }
        .badge { border-radius: 999px; padding: 1px 7px; font-weight: 650; color: var(--vscode-editor-background); }
        .badge.error { background: var(--error); }
        .badge.warning { background: var(--warning); }
        .badge.suggestion { background: var(--suggestion); }
        .fixable { color: var(--vscode-testing-iconPassed); }
        .actions { display: flex; gap: 6px; flex-wrap: wrap; margin-top: 10px; }
        .mini-diff { margin-top: 10px; border: 1px solid var(--border); border-radius: 6px; overflow: hidden; background: var(--vscode-textCodeBlock-background); font-family: var(--vscode-editor-font-family); font-size: 12px; }
        .diff-title { padding: 6px 8px; color: var(--muted); border-bottom: 1px solid var(--border); font-family: var(--vscode-font-family); font-size: 11px; font-weight: 650; }
        .diff-row { display: grid; grid-template-columns: 44px minmax(0, 1fr); align-items: start; min-height: 22px; }
        .diff-row .ln { padding: 3px 7px; color: var(--muted); text-align: right; border-right: 1px solid var(--border); user-select: none; }
        .diff-row code { padding: 3px 8px; white-space: pre-wrap; overflow-wrap: anywhere; color: var(--vscode-editor-foreground); }
        .diff-row.del { background: rgba(248, 81, 73, 0.13); }
        .diff-row.add { background: rgba(63, 185, 80, 0.13); }
        .diff-row.del code { color: #ffb3ad; }
        .diff-row.add code { color: #b7f7c2; }
        .empty, .loading { text-align: center; padding: 28px 12px; border: 1px solid var(--border); border-radius: 6px; background: var(--surface); }
        .empty-line { padding: 8px; }
        .spinner { width: 24px; height: 24px; border: 2px solid var(--border); border-top-color: var(--suggestion); border-radius: 50%; margin: 0 auto 12px; animation: spin .8s linear infinite; }
        @keyframes spin { to { transform: rotate(360deg); } }
      </style>
    </head>
    <body>
      ${body}
      <script>
        const vscode = acquireVsCodeApi();
        function send(command, id) { vscode.postMessage({ command, id }); }
        function toggleSection(group) {
          const el = document.getElementById('section-' + group);
          if (el) el.style.display = el.style.display === 'none' ? 'block' : 'none';
        }
      </script>
    </body>
  </html>`;
}

function openSuggestions(document) {
  return (state.byUri.get(document.uri.toString()) || []).filter((item) => item.status === "open");
}

function rangeForItem(document, item) {
  const start = Math.max(0, item.line - 1);
  if (start >= document.lineCount) return undefined;
  const end = Math.min(document.lineCount - 1, Math.max(start, (item.end_line || item.line) - 1));
  return new vscode.Range(start, 0, end, Math.max(1, document.lineAt(end).range.end.character));
}

function countGroups(suggestions) {
  return suggestions.reduce((acc, item) => {
    acc[item.group] += 1;
    return acc;
  }, { error: 0, warning: 0, suggestion: 0 });
}

function workspacePath(document) {
  return vscode.workspace.asRelativePath(document.uri, false);
}

function toDiagnosticSeverity(severity) {
  if (severity === "critical" || severity === "high") return vscode.DiagnosticSeverity.Error;
  if (severity === "medium") return vscode.DiagnosticSeverity.Warning;
  return vscode.DiagnosticSeverity.Information;
}

function groupForSeverity(severity) {
  if (severity === "critical" || severity === "high") return "error";
  if (severity === "medium") return "warning";
  return "suggestion";
}

function labelForGroup(group) {
  if (group === "error") return "Error";
  if (group === "warning") return "Warning";
  return "Suggestion";
}

function normalizeTitle(value) {
  return String(value || "").toLowerCase().replace(/["'`]/g, "").replace(/\s+/g, " ").trim();
}

function shortText(value, max) {
  const text = String(value || "").replace(/\s+/g, " ").trim();
  return text.length > max ? `${text.slice(0, max - 1)}...` : text;
}

function title(value) {
  return value.charAt(0).toUpperCase() + value.slice(1);
}

function escapeHtml(value) {
  return String(value || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

module.exports = { activate, deactivate };
