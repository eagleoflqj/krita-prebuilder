#!/usr/bin/env python3
"""Create deterministic local SDK archives; this command never publishes."""

import argparse
import gzip
import hashlib
import json
import os
import platform
import re
import shutil
import tarfile
import tempfile
from pathlib import Path
from typing import NotRequired, TypedDict

from sdk import CACHE_DIR, EMSCRIPTEN_VERSION, PACKAGES, QT_VERSION

ROOT = Path(__file__).resolve().parents[1]
BUILD_DIR = ROOT / "build"
INSTALL = BUILD_DIR / "install-jspi"
HOST_INSTALL = BUILD_DIR / "install"


class FileInfo(TypedDict, total=False):
    sha256: str
    executable: bool
    symlink: str


class TargetInfo(TypedDict):
    architecture: str
    threads: bool
    qt_linkage: str
    cxx_exceptions: str
    jspi: bool
    wasm_simd128: NotRequired[bool]


class SDKManifest(TypedDict):
    schema: int
    stage: str
    profile: str
    complete_krita_sdk: bool
    emscripten: str
    qt: str
    kde_frameworks: str
    target: TargetInfo
    host: dict[str, str | list[str]]
    limitations: list[str]
    sources: dict[str, object]
    files: dict[str, FileInfo]


def sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def inventory(folder: Path) -> dict[str, FileInfo]:
    result: dict[str, FileInfo] = {}
    for path in sorted(folder.rglob("*")):
        name = path.relative_to(folder).as_posix()
        if path.is_symlink():
            resolved = path.resolve()
            if not resolved.is_relative_to(folder.resolve()):
                raise ValueError(f"Non-relocatable symlink: {path}")
            result[name] = {"symlink": os.readlink(path)}
        elif path.is_file():
            result[name] = {
                "sha256": sha256(path),
                "executable": bool(path.stat().st_mode & 0o111),
            }
    return result


def deterministic_archive(folder: Path, destination: Path) -> None:
    with (
        destination.open("wb") as output,
        gzip.GzipFile(
            filename="", fileobj=output, mode="wb", mtime=0, compresslevel=6
        ) as compressed,
        tarfile.open(
            fileobj=compressed, mode="w", format=tarfile.PAX_FORMAT
        ) as archive,
    ):
        for path in sorted(folder.rglob("*")):
            info = archive.gettarinfo(
                str(path), arcname=path.relative_to(folder).as_posix()
            )
            info.uid = info.gid = info.mtime = 0
            info.uname = info.gname = ""
            info.pax_headers = {}
            if path.is_file() and not path.is_symlink():
                with path.open("rb") as stream:
                    archive.addfile(info, stream)
            else:
                archive.addfile(info)


def build_stage(stage: Path, profile: str) -> SDKManifest:
    required = [
        "host/libexec/moc",
        "host/libexec/rcc",
        "host/libexec/uic",
        "host/lib/libQt6Core.a",
        "target/lib/libQt6Widgets.a",
        "target/lib/libKF6CoreAddons.a",
        "target/lib/libKF6ConfigCore.a",
    ]
    if profile == "dependencies":
        required += [
            "host/bin/qsb",
            "host/libexec/qmlcachegen",
            "host/libexec/qmltyperegistrar",
            "host/libexec/qmlimportscanner",
        ]
        required += [
            "target/lib/" + name
            for name in [
                "libQt6Svg.a",
                "libQt6Core5Compat.a",
                "libQt6PrintSupport.a",
                "libQt6Qml.a",
                "libQt6Quick.a",
                "libQt6QuickWidgets.a",
                "libQt6QuickControls2.a",
                "libQt6QuickTemplates2.a",
                "libQt6QuickLayouts.a",
                "libQt6ShaderTools.a",
                "libKF6WidgetsAddons.a",
                "libKF6Completion.a",
                "libKF6Codecs.a",
                "libKF6GuiAddons.a",
                "libKF6I18n.a",
                "libKF6ItemViews.a",
                "libKF6ColorScheme.a",
                "libz.a",
                "libpng16.a",
                "libexpat.a",
                "liblcms2.a",
                "libquazip1-qt6.a",
                "libexiv2.a",
                "libfreetype.a",
                "libharfbuzz.a",
                "libfontconfig.a",
                "libfribidi.a",
                "libunibreak.a",
                "libgsl.a",
                "libgslcblas.a",
            ]
        ]
    for name in required:
        path = (
            HOST_INSTALL if name.startswith(("host/", "common/")) else INSTALL
        ) / name
        if not path.is_file():
            raise ValueError(f"Missing SDK component: {name}")
    for name in ["host", "target", "common"]:
        shutil.copytree(
            (HOST_INSTALL if name in ("host", "common") else INSTALL) / name,
            stage / name,
            symlinks=True,
        )
    # Qt Wasm uses CMake exports and has no Qt6Core.pc. Do not ship unusable
    # downstream .pc files that could silently pick up a native system Qt.
    for pc in (stage / "target/lib/pkgconfig").glob("*.pc"):
        if re.search(r"^Requires(?:\.private)?:.*\bQt6", pc.read_text(), re.MULTILINE):
            pc.unlink()
    # Carry component license texts alongside the binaries.
    from sdk import prepare

    own_license = stage / "licenses/krita-prebuilder"
    own_license.mkdir(parents=True)
    shutil.copy2(ROOT / "LICENSE", own_license / "LICENSE")
    packages = PACKAGES
    for component in packages:
        source = prepare(component)
        dest = stage / "licenses" / component
        dest.mkdir(parents=True)
        for path in source.iterdir():
            if path.name.upper().startswith(
                ("LICENSE", "LICENCE", "COPYING", "COPYRIGHT", "NOTICE", "AUTHORS")
            ):
                if path.is_dir():
                    shutil.copytree(path, dest / path.name, symlinks=True)
                else:
                    shutil.copy2(path, dest / path.name)
        if component == "freetype":
            for name in ["FTL.TXT", "GPLv2.TXT"]:
                shutil.copy2(source / "docs" / name, dest / name)
    version = EMSCRIPTEN_VERSION
    cache = BUILD_DIR / "compiler-cache" / f"emscripten-{version}-jspi"
    shutil.copytree(
        cache,
        stage / "emscripten-cache",
        symlinks=True,
        ignore=shutil.ignore_patterns("node_compile_cache", "*.lock", "sanity.txt"),
    )
    manifest: SDKManifest = {
        "schema": 1,
        "stage": "krita-dependencies" if profile == "dependencies" else "plugin-probe",
        "profile": "widgets-painting-poc"
        if profile == "dependencies"
        else "plugin-probe",
        "complete_krita_sdk": False,
        "emscripten": version,
        "qt": QT_VERSION,
        "kde_frameworks": "6.24.0",
        "target": {
            "architecture": "wasm32",
            "threads": True,
            "qt_linkage": "static",
            "cxx_exceptions": "wasm-native",
            "jspi": True,
            "wasm_simd128": False,
        },
        "host": {
            "system": platform.system(),
            "architecture": platform.machine(),
            "libc": list(platform.libc_ver()),
        },
        "limitations": [
            "Complete Krita application not linked yet",
            "No independent rebuild comparison yet",
            "Desktop printing and translation resources deferred",
            "No host process APIs or named timezone backend in the browser",
            "Host compiler/runtime and build image are not yet pinned",
        ],
        "sources": json.loads((ROOT / "sources.json").read_text()),
        "files": inventory(stage),
    }
    (stage / "sdk.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    )
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--profile", choices=["stage0", "dependencies"], default="dependencies"
    )
    parser.add_argument(
        "--tag", choices=["stage0", "stage1", "stage2", "stage3", "stage4-jspi"]
    )
    parser.add_argument(
        "--staging-dir",
        type=Path,
        default=BUILD_DIR,
        help="Temporary packaging storage, independent of build paths",
    )
    parser.add_argument("--output-dir", type=Path, default=CACHE_DIR / "prebuilt")
    parser.add_argument(
        "--check-repeat",
        action="store_true",
        help="compare two packagings of the same staged files; not a rebuild proof",
    )
    args = parser.parse_args()
    output = args.output_dir
    output.mkdir(parents=True, exist_ok=True)
    args.staging_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix="sdk-package-", dir=args.staging_dir
    ) as temporary_name:
        temporary = Path(temporary_name)
        stage = temporary / "sdk"
        stage.mkdir()
        manifest = build_stage(stage, args.profile)
        tag = args.tag or "stage4-jspi"
        binary = output / f"krita-wasm-sdk-{tag}.tar.gz"
        if binary.exists():
            raise ValueError(
                f"Preserving existing archive: {binary}; choose a fresh output directory"
            )
        deterministic_archive(stage, binary)
        if args.check_repeat:
            second = temporary / "repeat.tar.gz"
            deterministic_archive(stage, second)
            if sha256(binary) != sha256(second):
                raise ValueError("Packaging is not deterministic")
            print(
                "PASS: repeated packaging is byte-identical (not an independent rebuild)",
                flush=True,
            )
        hashes = {binary.name: sha256(binary)}
        print(
            json.dumps(
                {
                    "stage": manifest["stage"],
                    "archives": hashes,
                },
                indent=2,
            )
        )


if __name__ == "__main__":
    main()
