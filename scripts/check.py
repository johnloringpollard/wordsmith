#!/usr/bin/env python3
"""Run local release checks without starting the desktop or contacting providers."""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

from package import ROOT, release_files


def run(*command, timeout=60):
    print("+ " + " ".join(map(str, command)), flush=True)
    subprocess.run(command, cwd=ROOT, check=True, timeout=timeout, env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--omarchy", action="store_true", help="Require installed Omarchy manifest and QML checks")
    args = parser.parse_args()
    manifest = json.loads((ROOT / "manifest.json").read_text())
    expected = {"schemaVersion": 1, "id": "io.github.johnloringpollard.rewerd", "name": "Reword", "author": "John Pollard", "license": "MIT"}
    for key, value in expected.items():
        if manifest.get(key) != value:
            raise ValueError(f"Unexpected manifest {key}")
    if not re.fullmatch(r"\d+\.\d+\.\d+(?:-[A-Za-z0-9.-]+)?", manifest.get("version", "")):
        raise ValueError("Invalid release version")
    if manifest.get("kinds") != ["bar-widget", "service"] or manifest.get("entryPoints") != {"barWidget": "Panel.qml", "service": "Service.qml"}:
        raise ValueError("Unexpected plugin entry points")
    if "omarchy.clonedFrom" in manifest or manifest.get("omarchy", {}).get("clonedFrom"):
        raise ValueError("Remove clone-only metadata")
    patterns = [r"/home/[A-Za-z0-9_.-]+/", r"/Users/[A-Za-z0-9_.-]+/", r"\bsk-(?:proj-|ant-)?[A-Za-z0-9_-]{20,}", r"\bAIza[A-Za-z0-9_-]{30,}", r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"]
    for name, path in release_files():
        if path.suffix in {".png"}:
            continue
        text = path.read_text()
        if any(re.search(pattern, text) for pattern in patterns):
            raise ValueError(f"Possible credential or personal path in {name}")
    for name in ("backend.py", "providers.py", "instructions.py", "Panel.qml", "Service.qml"):
        text = (ROOT / name).read_text()
        if "john.edit-ai" in text or ".config/omarchy/edit-ai" in text:
            raise ValueError(f"Legacy identity or settings path in {name}")
    for name in ("settings.json", "instructions.json", ".env"):
        if (ROOT / name).exists():
            raise ValueError(f"Private configuration in repository: {name}")
    run(sys.executable, "-B", "-m", "unittest", "discover", "-v")
    if not shutil.which("node"):
        raise ValueError("Node.js is required for the QML JavaScript behavior tests")
    run("node", "--test", "test_panel_reopen.cjs")
    if args.omarchy:
        qmllint = shutil.which("qmllint") or "/usr/lib/qt6/bin/qmllint"
        if not shutil.which("omarchy") or not Path(qmllint).is_file():
            raise ValueError("--omarchy requires omarchy and qmllint")
        shell = Path(os.environ.get("OMARCHY_PATH", "/usr/share/omarchy")) / "shell"
        if not shell.is_dir():
            raise ValueError("Set OMARCHY_PATH to the installed Omarchy directory")
        run("omarchy", "plugin", "validate", str(ROOT))
        with tempfile.TemporaryDirectory(prefix="rewerd-qml-imports-") as directory:
            imports = Path(directory)
            (imports / "qs").symlink_to(shell, target_is_directory=True)
            run(qmllint, "-I", str(imports), str(ROOT / "Panel.qml"), str(ROOT / "Service.qml"), timeout=30)
    else:
        print("SKIP installed Omarchy manifest/QML checks; use --omarchy on Omarchy")
    print("Release checks passed. Pattern scanning is not a complete secret audit.")


if __name__ == "__main__":
    main()
