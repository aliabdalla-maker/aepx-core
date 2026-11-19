// Navigation policy for the desktop shell (pure, unit-tested): only the bundled console and the
// configured control-plane origin load inside the window; everything else opens in the browser.
function allowedInWindow(url, apiOrigin) {
  try {
    const u = new URL(url);
    if (u.protocol === "file:") return true;
    return apiOrigin ? u.origin === new URL(apiOrigin).origin && u.protocol === "https:" : false;
  } catch { return false; }
}
module.exports = { allowedInWindow };
