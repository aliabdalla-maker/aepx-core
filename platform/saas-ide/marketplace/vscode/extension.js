const vscode = require("vscode");
function activate(context) {
  context.subscriptions.push(vscode.commands.registerCommand("aepx.openIde", async () => {
    await vscode.env.openExternal(vscode.Uri.parse("https://ide.softwareequality.com/"));
  }));
}
function deactivate() {}
module.exports = { activate, deactivate };
