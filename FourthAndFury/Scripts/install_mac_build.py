"""Install a complete, verified Mac game bundle without interrupting the previous build."""
import ctypes
import os
from pathlib import Path
import plistlib
import shutil
import subprocess
import sys
import tempfile


def install(staged, destination):
    destination.parent.mkdir(parents=True, exist_ok=True)
    if not (staged / "Contents/UE").is_dir():
        raise ValueError(f"Missing cooked game data in {staged}")
    with tempfile.TemporaryDirectory(prefix=".fury-build-", dir=destination.parent) as folder:
        replacement = Path(folder) / destination.name
        subprocess.run(["ditto", staged, replacement], check=True)
        subprocess.run(["codesign", "--verify", "--deep", "--strict", replacement], check=True)
        if destination.exists():
            # Both paths are on the same volume. An unsuccessful exchange keeps the old bundle.
            libc = ctypes.CDLL(None, use_errno=True)
            rename_swap = 0x00000002
            if libc.renamex_np(os.fsencode(replacement), os.fsencode(destination), rename_swap) != 0:
                error = ctypes.get_errno()
                raise OSError(error, os.strerror(error), destination)
        else:
            os.rename(replacement, destination)


def archive(app, guide):
    with (app / "Contents/Info.plist").open("rb") as file:
        version = plistlib.load(file)["CFBundleShortVersionString"]
    name = f"4th-and-Fury-{version}-Mac-arm64.zip"
    with tempfile.TemporaryDirectory(prefix=".fury-archive-", dir=app.parent) as folder:
        work = Path(folder)
        release = work / "4th and Fury"
        release.mkdir()
        subprocess.run(["ditto", app, release / app.name], check=True)
        shutil.copyfile(guide, release / "Play.txt")
        zipfile = work / name
        subprocess.run(["ditto", "-c", "-k", "--keepParent", release, zipfile], check=True)
        check = work / "check"
        subprocess.run(["ditto", "-x", "-k", zipfile, check], check=True)
        subprocess.run(["codesign", "--verify", "--deep", "--strict", check / release.name / app.name], check=True)
        os.replace(zipfile, app.parent / name)
    print(f"Verified archive: {app.parent / name}")


if __name__ == "__main__":
    application = Path(sys.argv[2])
    install(Path(sys.argv[1]), application)
    if len(sys.argv) == 4:
        archive(application, Path(sys.argv[3]))
