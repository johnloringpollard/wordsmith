# Reword 1.0.1

Renamed the plugin to Reword. Existing settings, saved prompts, and keyboard shortcuts keep working.

Rewrite selected or copied text in a small Omarchy panel using your own OpenAI, Claude, Google Gemini, or Cursor account.

- Select text in your browser, Omawrite, or another application. If nothing is selected, Reword uses plain text from the clipboard.
- Adjust the prompt, review the rewrite, then replace the selection or copy the result.
- Save prompts and automatically reuse the last prompt.
- Edit shared writing defaults in Settings: no em dashes, rare emojis, preserved meaning and voice, accurate details, and concise wording. Explicit style requests take priority.
- Recover the original text and last completed rewrite after closing the panel. Reopening with the same input also keeps a pending rewrite running. Different selected or copied text starts fresh; the comparison stays in memory until the plugin restarts.
- Separate provider and writing-defaults editors return to Settings after saving. Back discards unsaved changes.
- Use a compact panel with a pen-and-sparkle icon, consistent header spacing, and keyboard shortcut keycaps.
- Add an optional Super+Shift+R shortcut. Enter rewrites; the next Enter replaces and closes, or copies and closes for clipboard input.
- Keep provider keys and prompts in private local files outside the plugin directory.

Requires Omarchy's Quattro shell, Hyprland Lua dispatchers, Python 3, and wl-clipboard. Cursor additionally requires its Agent CLI. Provider usage is billed by the provider. Replacement works in editable fields with standard copy/paste support; terminal and clipboard input use copying instead.

The release includes an MIT license, a preview rendered from the panel with sample text, a deterministic runtime archive, and its SHA-256 checksum. Install from the repository using Omarchy's standard plugin commands.

## Verification

- 63 Python tests and 53 QML JavaScript behavior tests pass without provider requests.
- Installed Omarchy manifest validation and QML lint were not repeated on the macOS release machine.
- Settings UI checks cover navigation, saved and canceled drafts, failure handling, and keyboard focus.
- The actual QML panel renders offscreen; preview interaction checks cover expansion, scrolling, and keyboard toggles.

Live paid provider requests and the full lifecycle in a separate real desktop session have not been repeated for this package.
