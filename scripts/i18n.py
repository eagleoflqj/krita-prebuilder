#!/usr/bin/env python3
"""Build a relocatable internationalization supplement outside krita.js."""

import argparse
import hashlib
import json
import os
import platform
import shutil
import subprocess
import tempfile
from collections.abc import Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from package import deterministic_archive, inventory, sha256
from sdk import (
    BUILD_DIR,
    C_TARGET_FLAGS,
    CACHE_DIR,
    CXX_EXCEPTION_FLAG,
    EMSCRIPTEN_VERSION,
    PACKAGES,
    QT_VERSION,
    ROOT,
    CommandArg,
    prepare,
)

PREFIX = BUILD_DIR / "i18n-jspi/install"
BUILD = BUILD_DIR / "i18n-jspi/build"
BASE = BUILD_DIR / "install-jspi"
HOST = BUILD_DIR / "install/host"
COMMON = BUILD_DIR / "install/common"
KDE = [
    "kcoreaddons",
    "kconfig",
    "kwidgetsaddons",
    "kcompletion",
    "ki18n",
    "kitemviews",
    "kguiaddons",
    "kcolorscheme",
    "kcodecs",
]


def run(
    command: Sequence[CommandArg],
    cwd: Path | None = None,
    wasm: bool = False,
    env: Mapping[str, str] | None = None,
) -> None:
    arguments = [str(x) for x in command]
    if wasm:
        arguments.insert(0, str(ROOT / "scripts/with-emsdk"))
    print("+", *arguments, flush=True)
    subprocess.run(arguments, cwd=cwd, env=env, check=True)


def build(jobs: int) -> None:
    source = prepare("gettext")
    native = BUILD / ("gettext-host-" + source.name.rsplit("-", 1)[-1])
    target = BUILD / ("gettext-target-" + source.name.rsplit("-", 1)[-1])
    for path in (native, target):
        path.mkdir(parents=True, exist_ok=True)
    print("Building GNU gettext host tools", flush=True)
    run(
        [
            source / "configure",
            f"--prefix={PREFIX / 'host'}",
            "--disable-shared",
            "--enable-static",
            "--disable-java",
            "--disable-csharp",
            "--with-included-libxml",
            "--with-included-libunistring",
            "--disable-nls",
        ],
        native,
    )
    run(["make", f"-j{jobs}"], native)
    tools = PREFIX / "host/bin"
    tools.mkdir(parents=True, exist_ok=True)
    for name in ("msgfmt", "msgmerge"):
        shutil.copy2(native / "gettext-tools/src" / name, tools / (name + ".next"))
        (tools / (name + ".next")).replace(tools / name)
    print("Building GNU gettext Wasm runtime", flush=True)
    env = {
        **os.environ,
        "CFLAGS": "-O2 " + C_TARGET_FLAGS,
        "CXXFLAGS": "-O2 -pthread " + CXX_EXCEPTION_FLAG,
    }
    run(
        [
            "emconfigure",
            source / "gettext-runtime/configure",
            f"--prefix={PREFIX / 'target'}",
            "--host=wasm32-unknown-emscripten",
            "--disable-shared",
            "--enable-static",
            "--with-included-gettext",
            "--enable-nls",
        ],
        target,
        wasm=True,
        env=env,
    )
    run(["make", "-C", "intl", f"-j{jobs}"], target, wasm=True)
    run(["make", "-C", "intl", "install"], target, wasm=True)
    source = prepare("ki18n")
    directory = BUILD / ("ki18n-" + source.name.rsplit("-", 1)[-1])
    print("Building KI18n with GNU gettext and static Transcript", flush=True)
    run(
        [
            BASE / "target/bin/qt-cmake",
            "-S",
            source,
            "-B",
            directory,
            "-G",
            "Ninja",
            "-DCMAKE_BUILD_TYPE=Release",
            f"-DCMAKE_INSTALL_PREFIX={PREFIX / 'target'}",
            "-DBUILD_SHARED_LIBS=OFF",
            "-DBUILD_TESTING=OFF",
            "-DBUILD_WITH_QML=ON",
            "-DBUILD_GEO_SCHEME_HANDLER=OFF",
            "-DKF_SKIP_PO_PROCESSING=ON",
            "-DKF_IGNORE_PLATFORM_CHECK=ON",
            "-DKDE_INSTALL_LIBDIR=lib",
            f"-DCMAKE_CXX_FLAGS=-pthread {CXX_EXCEPTION_FLAG}",
            f"-DCMAKE_C_FLAGS={C_TARGET_FLAGS}",
            f"-DQT_HOST_PATH={HOST}",
            f"-DQT_HOST_PATH_CMAKE_DIR={HOST / 'lib/cmake'}",
            f"-DKF6_HOST_TOOLING={HOST / 'lib/cmake'}",
            f"-DECM_DIR={COMMON / 'share/ECM/cmake'}",
            f"-DCMAKE_PREFIX_PATH={BASE / 'target'}",
            f"-DLibIntl_INCLUDE_DIRS={PREFIX / 'target/include'}",
            f"-DLibIntl_LIBRARIES={PREFIX / 'target/lib/libintl.a'}",
            "-DLibIntl_SYMBOL_FOUND=FALSE",
        ],
        wasm=True,
    )
    run(["cmake", "--build", directory, "--target", "KF6I18n", f"-j{jobs}"], wasm=True)
    config = (directory / "src/i18n/config.h").read_text()
    if (
        "#define HAVE_NL_MSG_CAT_CNTR 1" not in config
        or "#define HAVE_STATIC_KTRANSCRIPT 1" not in config
    ):
        raise ValueError(
            "KI18n must retain the GNU cache counter and static Transcript"
        )
    for name in ("libKF6I18n.a", "libktranscript.a"):
        shutil.copy2(directory / "lib" / name, PREFIX / "target/lib" / name)


def compile_catalogs(output: Path) -> None:
    if output.exists():
        raise ValueError(f"Preserving existing output: {output}")
    output.mkdir(parents=True)
    (BUILD_DIR / "i18n").mkdir(parents=True, exist_ok=True)
    qt = prepare("qttranslations")
    commands: list[list[CommandArg]] = []
    lrelease, lconvert = (HOST / "bin" / name for name in ("lrelease", "lconvert"))
    for path in sorted((qt / "translations").glob("*.ts")):
        dest = output / "qt/translations" / (path.stem + ".qm")
        dest.parent.mkdir(parents=True, exist_ok=True)
        commands.append([lrelease, "-silent", path, "-qm", dest])
    with ThreadPoolExecutor(max_workers=6) as pool:
        list(pool.map(run, commands))
    msgfmt = PREFIX / "host/bin/msgfmt"
    for component in KDE:
        source = prepare(component)
        for path in sorted(
            path
            for folder in ("po", "poqm")
            for path in (source / folder).glob("*/*.po")
        ):
            lang = path.parent.name
            dest = output / "locale" / lang / "LC_MESSAGES"
            dest.mkdir(parents=True, exist_ok=True)
            if path.stem.endswith("_qt"):
                with tempfile.TemporaryDirectory(
                    prefix="po-qm-", dir=BUILD_DIR / "i18n"
                ) as temporary:
                    ts = Path(temporary) / (path.stem + ".ts")
                    run([lconvert, "-i", path, "-o", ts])
                    run(
                        [lrelease, "-silent", ts, "-qm", dest / (path.stem + ".qm")],
                    )
            else:
                run(
                    [msgfmt, "--no-hash", "-o", dest / (path.stem + ".mo"), path],
                )
        for path in sorted((source / "po").glob("*/scripts/**/*")):
            if not path.is_file():
                continue
            parts = list(path.relative_to(source / "po").parts)
            parts[1] = "LC_SCRIPTS"
            dest = output / "locale" / Path(*parts)
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, dest)
            if path.suffix == ".pmap":
                run(
                    [
                        "python3",
                        "-B",
                        BASE / "target/lib/cmake/KF6I18n/ts-pmap-compile.py",
                        path,
                        str(dest) + "c",
                    ],
                )
    print(
        f"Compiled {len(list(output.rglob('*.qm')))} QM and {len(list(output.rglob('*.mo')))} MO catalogs",
        flush=True,
    )


def compare_catalogs(first: Path, second: Path) -> dict[str, str | int | bool]:
    if first.resolve() == second.resolve():
        raise ValueError("Catalog comparison requires independent output directories")

    def hashes(folder: Path) -> dict[str, str]:
        return {
            path.relative_to(folder).as_posix(): sha256(path)
            for path in folder.rglob("*")
            if path.is_file()
        }

    a, b = hashes(first), hashes(second)
    if not a or a != b:
        raise ValueError("Independent catalog outputs differ or are empty")
    result: dict[str, str | int | bool] = {
        "files": len(a),
        "equal": True,
        "inventory_sha256": hashlib.sha256(
            json.dumps(a, sort_keys=True).encode()
        ).hexdigest(),
    }
    print(json.dumps(result, indent=2), flush=True)
    return result


def package(
    catalogs: Path, output: Path, tag: str, *, check_repeat: bool = False
) -> None:
    output.mkdir(parents=True, exist_ok=True)
    binary = output / f"krita-wasm-i18n-{tag}.tar.gz"
    sources = output / f"krita-wasm-i18n-{tag}-sources.tar.gz"
    if binary.exists() or sources.exists():
        raise ValueError("Preserving existing i18n archives; choose a new tag/output")
    with tempfile.TemporaryDirectory(
        prefix="i18n-package-", dir=BUILD_DIR / "i18n"
    ) as temporary_name:
        temporary = Path(temporary_name)
        stage = temporary / "binary"
        for name in ("libintl.a", "libKF6I18n.a", "libktranscript.a"):
            dest = stage / "target/lib" / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(PREFIX / "target/lib" / name, dest)
        for name in ("msgfmt", "msgmerge"):
            dest = stage / "host/bin" / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(PREFIX / "host/bin" / name, dest)
        shutil.copytree(catalogs, stage / "target/share")
        source_stage = temporary / "sources"
        components = ["gettext", "qttranslations", *KDE]
        inputs = PACKAGES
        for component in components:
            entry = inputs[component]
            archive = (
                CACHE_DIR
                / "downloads"
                / entry.get("archive", entry["url"].rsplit("/", 1)[1])
            )
            if sha256(archive) != entry["sha256"]:
                raise ValueError(f"Source mismatch: {component}")
            dest = source_stage / "upstream-archives" / archive.name
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(archive, dest)
            folder = prepare(component)
            for path in folder.iterdir():
                if path.name.upper().startswith(
                    ("COPYING", "LICENSE", "COPYRIGHT", "NOTICE")
                ):
                    target = stage / "licenses" / component / path.name
                    target.parent.mkdir(parents=True, exist_ok=True)
                    if path.is_dir():
                        shutil.copytree(path, target)
                    else:
                        shutil.copy2(path, target)
            if component == "gettext":
                shutil.copy2(
                    folder / "gettext-runtime/intl/COPYING.LIB",
                    stage / "licenses/gettext/COPYING.LIB",
                )
        for name in (
            "scripts",
            "sources.json",
            "patches",
            "tests",
            ".github",
            "docs",
            "AGENTS.md",
            "README.md",
            "LICENSE",
            ".emscripten-version",
            ".clang-format",
            "pyproject.toml",
            "requirements.txt",
        ):
            path = ROOT / name
            if path.is_dir():
                shutil.copytree(
                    path,
                    source_stage / "recipes" / name,
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
                )
            else:
                shutil.copy2(path, source_stage / "recipes" / name)
        manifest = {
            "schema": 1,
            "stage": "i18n",
            "emscripten": EMSCRIPTEN_VERSION,
            "qt": QT_VERSION,
            "kde_frameworks": "6.24.0",
            "host": {"system": platform.system(), "architecture": platform.machine()},
            "target": {
                "architecture": "wasm32",
                "threads": True,
                "qt_linkage": "static",
                "cxx_exceptions": "wasm-native",
                "jspi": True,
            },
            "sources": {name: inputs[name] for name in components},
            "files": inventory(stage),
        }
        (stage / "sdk.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n"
        )
        deterministic_archive(stage, binary)
        if check_repeat:
            repeat = temporary / "repeat.tar.gz"
            deterministic_archive(stage, repeat)
            if sha256(binary) != sha256(repeat):
                raise ValueError("Repeated i18n packaging differs")
        deterministic_archive(source_stage, sources)
    print(
        json.dumps(
            {binary.name: sha256(binary), sources.name: sha256(sources)}, indent=2
        ),
        flush=True,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["build", "catalogs", "compare", "package"])
    parser.add_argument("--jobs", type=int, default=6)
    parser.add_argument("--catalogs", type=Path, default=BUILD_DIR / "i18n/catalogs")
    parser.add_argument("--compare", type=Path)
    parser.add_argument("--output", type=Path, default=CACHE_DIR / "prebuilt")
    parser.add_argument("--tag", default="stage0")
    parser.add_argument(
        "--check-repeat",
        action="store_true",
        help="compare repeated packaging of the same staged files",
    )
    args = parser.parse_args()
    if args.action == "build":
        build(args.jobs)
    elif args.action == "catalogs":
        compile_catalogs(args.catalogs)
    elif args.action == "compare":
        if args.compare is None:
            parser.error("compare requires --compare")
        compare_catalogs(args.catalogs, args.compare)
    else:
        package(args.catalogs, args.output, args.tag, check_repeat=args.check_repeat)


if __name__ == "__main__":
    main()
