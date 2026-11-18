#!/usr/bin/env python3
"""Build and package a QtCore correction against an immutable base SDK."""

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from collections.abc import Sequence
from pathlib import Path

from package import SDKManifest, deterministic_archive, inventory
from sdk import (
    EMSCRIPTEN_VERSION,
    QT_VERSION,
    CommandArg,
    archive_path,
    emsdk_root,
    prepare,
)

ROOT = Path(__file__).resolve().parents[1]


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-sdk", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    base = args.base_sdk.resolve(strict=True)
    output = args.output.resolve()
    if output.exists():
        raise ValueError(
            "Preserving existing correction output; select a new directory"
        )
    manifest: SDKManifest = json.loads((base / "sdk.json").read_text())
    if (
        manifest["qt"] != QT_VERSION
        or manifest["emscripten"] != EMSCRIPTEN_VERSION
        or not manifest["target"].get("jspi")
        or manifest["target"].get("cxx_exceptions") != "wasm-native"
    ):
        raise ValueError(
            "Correction requires the pinned Qt/Emscripten JSPI/native-exception base SDK"
        )
    core = base / "target/lib/libQt6Core.a"
    if digest(core) != manifest["files"]["target/lib/libQt6Core.a"]["sha256"]:
        raise ValueError("Base QtCore archive was modified")
    source = prepare("qtbase")
    identity: dict[str, str] = json.loads((source / ".sdk-source.json").read_text())
    build = ROOT / "build/qtcore-correction" / identity["patch_digest"][:12]
    build.mkdir(parents=True, exist_ok=True)
    temporary = ROOT / "build/tmp"
    temporary.mkdir(parents=True, exist_ok=True)
    emsdk = emsdk_root()
    version = json.loads(
        (emsdk / "upstream/emscripten/emscripten-version.txt").read_text()
    )
    if version != manifest["emscripten"]:
        raise ValueError("Shared emsdk version mismatch; it was not changed")
    environment = {
        **os.environ,
        "EM_CONFIG": str(emsdk / ".emscripten"),
        "EMSDK": str(emsdk),
        "EM_CACHE": str(base / "emscripten-cache"),
        "EM_FROZEN_CACHE": "1",
        "TMPDIR": str(temporary),
        "EMCC_TEMP_DIR": str(temporary),
        "CCACHE_DISABLE": "1",
        "PATH": str(emsdk / "upstream/emscripten") + ":" + os.environ["PATH"],
    }

    def run(command: Sequence[CommandArg]) -> None:
        subprocess.run(list(map(str, command)), env=environment, check=True)

    run(
        [
            base / "target/bin/qt-cmake",
            "-S",
            ROOT / "qtcore-dispatch",
            "-B",
            build,
            "-G",
            "Ninja",
            "-DCMAKE_BUILD_TYPE=Release",
            "-DCMAKE_EXPORT_COMPILE_COMMANDS=ON",
            f"-DQT_SOURCE={source}",
            f"-DBASE_SDK={base}",
            f"-DQT_HOST_PATH={base / 'host'}",
            f"-DCMAKE_PREFIX_PATH={base / 'target'}",
        ]
    )
    run(["cmake", "--build", build, "--parallel", "2"])
    objects = list(build.rglob("qwasmsuspendresumecontrol.cpp.o"))
    if len(objects) != 1:
        raise ValueError("Expected one corrected QtCore object")
    ar = emsdk / "upstream/emscripten/emar"
    members = subprocess.check_output(
        [str(ar), "t", str(core)], text=True, env=environment
    ).splitlines()
    if members.count(objects[0].name) != 1:
        raise ValueError("Base QtCore archive member identity mismatch")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix="qtcore-package-", dir=ROOT / "build"
    ) as staging:
        stage = Path(staging) / "sdk"
        stage.mkdir()
        library = stage / "target/lib/libQt6Core.a"
        library.parent.mkdir(parents=True)
        shutil.copyfile(core, library)
        run([ar, "rD", library, objects[0]])
        run([ar, "sD", library])
        shutil.copytree(
            base / "licenses/qtbase", stage / "licenses/qtbase", symlinks=True
        )
        provenance = {
            "schema": 1,
            "stage": "qtcore",
            "emscripten": manifest["emscripten"],
            "qt": manifest["qt"],
            "kde_frameworks": manifest["kde_frameworks"],
            "host": manifest["host"],
            "target": manifest["target"],
            "base_sdk_inventory_sha256": digest(base / "sdk.json"),
            "base_qtcore_sha256": digest(core),
            "sources": identity,
            "files": inventory(stage),
        }
        (stage / "sdk.json").write_text(
            json.dumps(provenance, indent=2, sort_keys=True) + "\n"
        )
        sources = Path(staging) / "sources"
        sources.mkdir()
        shutil.copyfile(archive_path("qtbase"), sources / archive_path("qtbase").name)
        for name in ["patches/qtbase", "qtcore-dispatch"]:
            shutil.copytree(ROOT / name, sources / "recipes" / name)
        for name in [
            "sources.json",
            "LICENSE",
            ".emscripten-version",
            ".clang-format",
            "pyproject.toml",
            "requirements.txt",
        ]:
            shutil.copyfile(ROOT / name, sources / "recipes" / name)
        for name in ["sdk.py", "package.py", "qtcore-correction.py"]:
            path = sources / "recipes/scripts" / name
            path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / "scripts" / name, path)
        output.mkdir()
        archives = [
            output / "krita-wasm-qtcore-jspi.tar.gz",
            output / "krita-wasm-qtcore-jspi-sources.tar.gz",
        ]
        deterministic_archive(stage, archives[0])
        deterministic_archive(sources, archives[1])
        hashes = {path.name: digest(path) for path in archives}
        (output / "SHA256SUMS").write_text(
            "".join(f"{value}  {key}\n" for key, value in hashes.items())
        )
        print(
            json.dumps(
                {
                    "archives": hashes,
                    "base_sdk_inventory_sha256": provenance[
                        "base_sdk_inventory_sha256"
                    ],
                },
                indent=2,
            )
        )


if __name__ == "__main__":
    main()
