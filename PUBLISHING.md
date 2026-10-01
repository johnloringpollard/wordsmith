# Release Wordsmith

The review repository is `johnloringpollard/wordsmith`. Keep it private and keep the GitHub release in draft until the owner finishes reviewing it. A GitHub draft release is separate from an Omarchy marketplace listing. The marketplace has no documented unpublished listing editor.

The display name is Wordsmith. Its stable plugin ID remains `io.github.johnloringpollard.rewerd`, and settings remain in `~/.config/rewerd/`. The existing development installation uses `john.edit-ai` and `~/.config/omarchy/edit-ai/`; its runtime code and built-in defaults match the release after substituting those two identifiers.

## Verify the review build

Run from this checkout:

```sh
python3 scripts/check.py --omarchy
python3 scripts/verify_settings_ui.py
python3 scripts/render_preview.py
python3 scripts/package.py
```

The archive allowlist includes only runtime files, README, license, and preview assets. It excludes credentials, saved prompts, logs, caches, and development tools. Review the files and archive before uploading. Pattern scanning is not a complete secret audit.

The preview uses sample text. Never upload screenshots containing personal selections, prompts, or credentials.

## Update the GitHub draft

Commit the reviewed changes and push them to `main`. Keep the release draft pinned to the full commit SHA that produced its attached archive. Upload the archive, checksum, and sample-data screenshots together. If they change, replace the existing draft assets and update the target SHA.

```sh
gh release view v1.0.0 --repo johnloringpollard/wordsmith
```

Use `RELEASE_NOTES.md` as the release body. The archive is named `rewerd-1.0.0.tar.gz` to match the existing packaging contract; the release title is **Wordsmith 1.0.0**.

## Publish later

After the owner approves publication:

1. Recheck the repository contents and release assets.
2. Make the repository public.
3. Publish the draft release.
4. Prepare the marketplace submission below and review every acknowledgment with the owner.
5. Submit only after the owner approves the completed issue body.

Do not submit an issue merely to reserve an unpublished listing. Marketplace approval can lead to publication.

## Marketplace submission

Follow the current [publishing guide](https://plugins.omarchy.org/publish.html) and [CLI submission guide](https://github.com/omacom/omarchy-plugin-marketplace/blob/main/SUBMISSION.md).

Use these values:

| Field | Value |
| --- | --- |
| Title | `[Plugin]: Wordsmith` |
| Repository URL | `https://github.com/johnloringpollard/wordsmith` |
| Category | `Productivity` |
| Tags | `AI`, `Bar`, `Quickshell` |
| Suggest a missing tag | Leave empty |

Maintainer notes should state the Omarchy Quattro, Hyprland Lua, Python 3, and wl-clipboard requirements. Cursor optionally requires its Agent CLI. The plugin sends selected or copied text, writing defaults, and the rewrite prompt to the chosen provider. Credentials and prompts remain outside the plugin directory. The optional shortcut is configured manually.

Report the checks actually performed. The portable tests and QML checks do not establish live provider access or a full desktop lifecycle. Paid provider requests and a separate real-desktop lifecycle have not been repeated for this release.

Keep all six headings from the current issue form, and confirm every required acknowledgment before submitting. A listing requires automated checks and an explicit maintainer decision; publishing a GitHub release alone does not list it in the marketplace.
