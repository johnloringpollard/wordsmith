# Publish Rewerd 1.0.0

These are maintainer instructions for a future public release. Preparing this checkout does not create a GitHub repository, release, or marketplace listing.

The permanent plugin ID is `io.github.johnloringpollard.rewerd`. The intended repository is `johnloringpollard/rewerd`, with John Pollard as author and MIT as the license. Keep the ID stable across updates.

## Verify the release

Run from the repository root:

```sh
python3 scripts/check.py --omarchy
python3 scripts/package.py
```

Review the complete staged diff and the archive contents. The package script includes only its named runtime files, README, license, and optional named preview assets. It excludes tests, credentials, logs, caches, and development tools. Repeated builds from identical file contents produce identical archive bytes. Pattern checks can miss secrets, so review the actual files before publishing.

```sh
tar -tzf dist/rewerd-1.0.0.tar.gz
(cd dist && sha256sum -c rewerd-1.0.0.tar.gz.sha256)
git status --short
git diff --cached
```

Before release, manually test click and shortcut opening, fresh selection after reopening, clipboard fallback, replacement, copy, Escape, outside-click dismissal, and provider errors. Test disable, enable, shell restart, and removal in a disposable Omarchy session. Test the chosen providers with your own account only when you intend to make billable requests. Record which desktop and provider checks passed. Portable tests and QML linting do not replace these checks.

Confirm that `preview.png` depicts the release and contains no private text. Confirm ownership and license provenance for code and assets.

## Create the public repository

The commands below publish externally. Run them yourself when ready. Authenticate `gh` as the intended owner first. The prepared checkout has a local `main` commit. Check `git status --short`, `git log -1`, and `git remote -v` before publishing.

Only if your copy has no Git history, initialize and commit it first:

```sh
git init -b main
git add README.md LICENSE PUBLISHING.md RELEASE_NOTES.md manifest.json Panel.qml Service.qml backend.py providers.py instructions.py test_*.py test_panel_reopen.cjs verify_preview.py scripts .github .gitignore .gitattributes preview.png
git diff --cached --stat
git diff --cached
git commit -m "Release Rewerd 1.0.0"
```

Publish the prepared commit and tag:

```sh
gh repo create johnloringpollard/rewerd --public --source=. --remote=origin --description "Rewrite selected text in Omarchy with your own AI provider"
git push -u origin main
git tag -a v1.0.0 -m "Rewerd 1.0.0"
git push origin v1.0.0
```

If the repository already exists, add or verify the intended `origin` and skip `gh repo create`. Do not recreate an existing tag. Confirm the public default branch contains `manifest.json`, README, license, and the runtime files.

Review the included release notes, then attach the generated archive:

```sh
gh release create v1.0.0 dist/rewerd-1.0.0.tar.gz dist/rewerd-1.0.0.tar.gz.sha256 --title "Rewerd 1.0.0" --notes-file RELEASE_NOTES.md
```

The archive is a reviewable release artifact. Standard Omarchy installation uses the Git repository.

## Submit the marketplace listing

Follow the [publishing guide](https://plugins.omarchy.org/publish.html) and open the [Submit a plugin issue form](https://github.com/omacom/omarchy-plugin-marketplace/issues/new?template=submit-plugin.yml). The current form is `.github/ISSUE_TEMPLATE/submit-plugin.yml` in `omacom/omarchy-plugin-marketplace`.

Use these values:

| Field | Value |
| --- | --- |
| Title | `[Plugin]: Rewerd` |
| Repository URL | `https://github.com/johnloringpollard/rewerd` |
| Category | `Productivity` |
| Tags | `AI`, `Bar`, `Quickshell` |
| Suggest a missing tag | Leave empty |

For maintainer notes, state that Rewerd requires Omarchy Quattro, Hyprland Lua dispatchers, Python 3, and wl-clipboard. Explain that direct providers use the user's API key, Cursor optionally requires its CLI, credentials remain outside the plugin directory, and the shortcut is configured manually. Mention that source text and prompts go to the chosen provider. Include the validation results and any untested behavior.

Complete the form's ownership, dependencies, installation, configuration-consent, and listing-review acknowledgments after verifying each one. The form accepts one to three tags. Marketplace approval concerns the listing and is not a security review. Check the current form again before submission because categories and tags can change.

The [development guide](https://plugins.omarchy.org/develop.html) documents the runtime contract and validation commands. A valid manifest and public repository are prerequisites, not a guarantee of approval.
