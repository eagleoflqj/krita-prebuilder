# krita-prebuilder

Build recipes and packaging for Krita’s WebAssembly dependencies, including static Qt 6 and KDE Frameworks. The SDK supports Wasm threads, JavaScript Promise Integration (JSPI) and native Wasm exceptions. The krita.js application consumes these prebuilts instead of compiling third-party dependencies itself.

## Build

Follow [Building and verifying the SDK](docs/BUILD.md) for requirements, build commands, browser checks and packaging. SDK and corresponding-source archives are written to `cache/prebuilt/`.

## License

Repository-owned build scripts and probes use the [MIT License](LICENSE), copyright Krita contributors. Dependencies and upstream-derived patches retain their own licenses; MIT does not apply to the generated SDK as a whole. See [patch provenance](patches/PROVENANCE.md) for patch origins.
