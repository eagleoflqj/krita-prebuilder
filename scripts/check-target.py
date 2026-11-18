#!/usr/bin/env python3
"""Reject host archives and target pkg-config metadata that escapes the SDK."""

import os
import re
import subprocess
from pathlib import Path

from sdk import emsdk_root

root = Path(__file__).resolve().parents[1]
emsdk = emsdk_root()
target = root / "build/install-jspi/target"
configuration = (target / "include/QtCore/qconfig.h").read_text()
for feature in ("wasm_jspi", "wasm_exceptions"):
    if f"#define QT_FEATURE_{feature} 1" not in configuration:
        raise SystemExit(f"SDK requires Qt feature: {feature}")
reader = emsdk / "upstream/bin/llvm-readobj"
archives = list(target.rglob("*.a"))
for archive in archives:
    result = subprocess.run(
        [reader, "--file-headers", archive], check=True, capture_output=True, text=True
    )
    formats = re.findall(r"^Format: (.+)$", result.stdout, re.MULTILINE)
    if not formats or any(value != "WASM" for value in formats):
        raise SystemExit(f"Non-Wasm archive member: {archive}: {set(formats)}")
for pattern in ("*.so", "*.dylib", "*.dll"):
    if list(target.rglob(pattern)):
        raise SystemExit(f"Unexpected shared target library: {pattern}")
for path in target.rglob("*"):
    if path.is_file():
        with path.open("rb") as stream:
            if stream.read(4) == b"\x7fELF":
                raise SystemExit(
                    f"Native ELF binary leaked into the target prefix: {path}"
                )
# Public headers/templates are part of normal API consumption; standalone
# external translation units must already be compiled in this SDK.
for path in (target / "lib/cmake").rglob("*.cmake"):
    for line in path.read_text().splitlines():
        if "INTERFACE_SOURCES" in line and re.search(
            r'\.(?:cpp|cxx|cc|c)(?:[;"\s>]|$)', line
        ):
            raise SystemExit(
                f"External compilation source leaked through CMake: {path}"
            )
        if "INTERFACE_LINK_LIBRARIES" in line and re.search(
            r'[";\s](/[^";\s]+\.(?:a|o))(?=[";\s]|$)', line
        ):
            raise SystemExit(
                f"Non-relocatable absolute archive/object exported through CMake: {path}"
            )
        if "INTERFACE_INCLUDE_DIRECTORIES" in line and re.search(
            r'[";\s]/[^";\s]+', line
        ):
            raise SystemExit(
                f"Non-relocatable absolute include directory exported through CMake: {path}"
            )
environment = {
    **os.environ,
    "PKG_CONFIG_PATH": "",
    "PKG_CONFIG_LIBDIR": f"{target}/lib/pkgconfig:{target}/share/pkgconfig",
}
# Qt/KDE and QuaZip use CMake exports: Qt Wasm does not ship Qt6Core.pc.
packages = [
    "zlib",
    "libpng",
    "lcms2",
    "freetype2",
    "harfbuzz",
    "fontconfig",
    "fribidi",
    "libunibreak",
    "exiv2",
]
result = subprocess.run(
    ["pkg-config", "--static", "--libs", *packages],
    env=environment,
    check=True,
    capture_output=True,
    text=True,
)
for library_directory in re.findall(r"(?:^|\s)-L(\S+)", result.stdout):
    if not Path(library_directory).resolve().is_relative_to(target.resolve()):
        raise SystemExit(
            f"Target pkg-config leaked a host library search path: {library_directory}"
        )
print(
    f"PASS: {len(archives)} target archives contain only Wasm objects; static pkg-config paths stay inside the SDK"
)
