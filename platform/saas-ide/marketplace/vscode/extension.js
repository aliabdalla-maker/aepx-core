"use strict";
// Opens the hosted AEP-X Agentic IDE from VS Code. The extension reads no workspace files, stores no
// credentials and makes no network calls itself: sign-in, plans and agent work all happen in the IDE.
const vscode = require("vscode");
const { ideUrl, newProjectUrl, MODULES, PRICING } = require("./url.js");

function configuredIde() {
  // machine-scoped setting: a cloned workspace's .vscode/settings.json cannot redirect it.
  return ideUrl(vscode.workspace.getConfiguration("aepx").get("ideUrl"));
}

function activate(context) {
  const open = (url) => vscode.env.openExternal(vscode.Uri.parse(url));
  context.subscriptions.push(
    vscode.commands.registerCommand("aepx.openIde", () => open(configuredIde())),
    vscode.commands.registerCommand("aepx.openPricing", () => open(PRICING)),
    vscode.commands.registerCommand("aepx.newProject", async () => {
      const pick = await vscode.window.showQuickPick(
        MODULES.map(m => ({ label: m.label, detail: m.detail, id: m.id })),
        { title: "AEP-X: new project in…", placeHolder: "Choose an IDE" });
      if (pick) open(newProjectUrl(vscode.workspace.getConfiguration("aepx").get("ideUrl"), pick.id));
    }),
  );
  const item = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Right, 100);
  item.text = "$(rocket) AEP-X";
  item.tooltip = "Open the AEP-X Agentic IDE";
  item.command = "aepx.openIde";
  if (vscode.workspace.getConfiguration("aepx").get("showStatusBar", true)) item.show();
  context.subscriptions.push(item);
}

function deactivate() {}

module.exports = { activate, deactivate };
