# Project instructions

Build and usage details are in `docs/BUILD.md`. Record build, browser and independent reproducibility evidence separately.

- This repository builds external dependencies for krita.js; the application consumes verified prebuilts and never builds those dependencies itself.
- Keep source/toolchain versions and checksums fixed. Discover emsdk through the current environment, with no personal path defaults. Use the existing emsdk read-only; do not install, activate or upgrade it without explicit permission.
- Use static Qt 6, Wasm pthreads, JSPI and native exceptions for the application target. Keep host and target prefixes separate.
- Keep downloaded archives and application SDK packages in ignored `cache/`; put sources, builds, compiler caches and logs in ignored `build/` on a verified disk filesystem. Preserve existing source/build trees and artifacts.
- Own repository code uses MIT. Preserve upstream dependency and patch licenses, component notices and source provenance.
