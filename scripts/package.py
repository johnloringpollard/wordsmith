#!/usr/bin/env python3
"""Build a deterministic runtime archive from an explicit release allowlist."""
import gzip
import hashlib
import io
import json
from pathlib import Path
import re
import tarfile

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = (
    "manifest.json", "Panel.qml", "Service.qml", "backend.py", "providers.py",
    "instructions.py", "README.md", "LICENSE",
)
ASSETS = ("assets/rewerd.svg", "preview.png")


def release_files(root=ROOT):
    names = list(RUNTIME) + [name for name in ASSETS if (root / name).exists()]
    for name in sorted(names):
        path = root / name
        if path.is_symlink() or any((root / p).is_symlink() for p in path.relative_to(root).parents if p != Path('.')):
            raise ValueError(f"Symlink not allowed: {name}")
        if not path.is_file():
            raise ValueError(f"Missing release file: {name}")
        yield name, path


def main():
    version = json.loads((ROOT / "manifest.json").read_text())["version"]
    if not re.fullmatch(r"\d+\.\d+\.\d+(?:-[A-Za-z0-9.-]+)?", version):
        raise ValueError("Version must be a safe semantic version")
    files = list(release_files())
    archive = io.BytesIO()
    with gzip.GzipFile(fileobj=archive, mode="wb", filename="", mtime=0) as compressed:
        with tarfile.open(fileobj=compressed, mode="w", format=tarfile.USTAR_FORMAT) as tar:
            for name, path in files:
                data = path.read_bytes()
                info = tarfile.TarInfo(f"rewerd-{version}/{name}")
                info.size = len(data)
                info.mode = 0o644
                info.mtime = 0
                info.uid = info.gid = 0
                info.uname = info.gname = ""
                tar.addfile(info, io.BytesIO(data))
    destination = ROOT / "dist"
    destination.mkdir(exist_ok=True)
    target = destination / f"rewerd-{version}.tar.gz"
    target.write_bytes(archive.getvalue())
    digest = hashlib.sha256(archive.getvalue()).hexdigest()
    target.with_suffix(target.suffix + ".sha256").write_text(f"{digest}  {target.name}\n")
    print(target)
    print(f"SHA256 {digest}")


if __name__ == "__main__":
    main()
