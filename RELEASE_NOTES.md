# Rewerd 1.0.0

Rewrite selected or copied text in a small Omarchy panel using your own OpenAI, Claude, Google Gemini, or Cursor account.

- Select text in your browser, Omawrite, or another application. If nothing is selected, Rewerd uses plain text from the clipboard.
- Adjust the prompt, review the rewrite, then replace the selection or copy the result.
- Save prompts and automatically reuse the last prompt.
- Add an optional Super+Alt+E shortcut. Enter rewrites; the next Enter replaces and closes, or copies and closes for clipboard input.
- Keep provider keys and prompts in private local files outside the plugin directory.

Requires Omarchy's Quattro shell, Hyprland Lua dispatchers, Python 3, and wl-clipboard. Cursor additionally requires its Agent CLI. Provider usage is billed by the provider. Replacement works in editable fields with standard copy/paste support; terminal and clipboard input use copying instead.

The release includes an MIT license, a preview rendered from the panel with sample text, a deterministic runtime archive, and its SHA-256 checksum. Install from the repository using Omarchy's standard plugin commands.

## Verification

- 47 Python tests and 41 QML JavaScript behavior tests pass without provider requests.
- Omarchy manifest validation and QML lint complete successfully. Lint reports existing dynamic-shell type and unqualified-access warnings.
- The actual QML panel renders offscreen; preview interaction checks cover expansion, scrolling, and keyboard toggles.
- Standard Omarchy add, enable, disable, update, and remove commands pass in an isolated filesystem with shell IPC stubbed. Removal preserves separate saved settings.
- Desktop selection, replacement, clipboard fallback, and the keyboard workflow were exercised on the development build before packaging. This release changes its plugin ID and settings directory.

Live paid provider requests and the full lifecycle in a separate real desktop session have not been repeated for this package.
