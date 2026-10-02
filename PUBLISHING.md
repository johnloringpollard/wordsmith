# Release Reword

The public repository is `johnloringpollard/reword`. Prepare releases as drafts until their files and checks have been reviewed. A GitHub release is separate from an Omarchy marketplace listing.

The display name is Reword. Its stable plugin ID remains `io.github.johnloringpollard.rewerd`, and settings remain in `~/.config/rewerd/`. The existing development installation uses `john.edit-ai` and `~/.config/omarchy/edit-ai/`; its runtime code and built-in defaults match the release after substituting those two identifiers.

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
gh release view v1.0.1 --repo johnloringpollard/reword
```

Use `RELEASE_NOTES.md` as the release body. The archive is named `rewerd-1.0.1.tar.gz` to match the existing packaging contract; the release title is **Reword 1.0.1**.

## Publish a verified release

1. Recheck the repository contents and release assets.
2. Publish the draft after the owner authorizes the release.
3. Update the [existing marketplace submission](https://github.com/omacom/omarchy-plugin-marketplace/issues/9678) with the verified commit and current repository URL. Do not create a duplicate submission.

## Marketplace submission

Follow the current [publishing guide](https://plugins.omarchy.org/publish.html) and [CLI submission guide](https://github.com/omacom/omarchy-plugin-marketplace/blob/main/SUBMISSION.md).

Use these values:

| Field | Value |
| --- | --- |
| Title | `[Plugin]: Reword` |
| Repository URL | `https://github.com/johnloringpollard/reword` |
| Category | `Productivity` |
| Tags | `AI`, `Bar`, `Quickshell` |
| Suggest a missing tag | Leave empty |

Maintainer notes should state the Omarchy Quattro, Hyprland Lua, Python 3, and wl-clipboard requirements. Cursor optionally requires its Agent CLI. The plugin sends selected or copied text, writing defaults, and the rewrite prompt to the chosen provider. Credentials and prompts remain outside the plugin directory. The optional shortcut is configured manually.

Report the checks actually performed. The portable tests and QML checks do not establish live provider access or a full desktop lifecycle. Paid provider requests and a separate real-desktop lifecycle have not been repeated for this release.

Keep all six headings from the current issue form, and confirm every required acknowledgment before submitting. A listing requires automated checks and an explicit maintainer decision; publishing a GitHub release alone does not list it in the marketplace.
