# Building and verifying the SDK

The current recipes use Emscripten 7.0.0, Qt 6.10.2 and KDE Frameworks 6.24.0. Use Emscripten from your current environment (`EMSDK` or `emcc` on `PATH`). `EMSDK_ROOT` is an optional override. The Emscripten version is stored in `.emscripten-version`. Qt versions are read from `sources.json`; all Qt module versions must agree with its `qtbase` entry. The shared installation is read without activation changes. The host build requires Python 3.12 or newer, CMake, Ninja, a native C/C++ compiler, gperf and pkg-config; the workflow records its environment and installs its build utilities.

Downloaded source archives are stored in `cache/downloads/`. Packaged SDK binaries, corresponding sources and checksum files are written to `cache/prebuilt/`. Extracted sources, build directories, install staging, compiler caches, temporary files and logs stay under `build/`. Both directories are ignored by Git. Package filenames retain the `krita-wasm-sdk` prefix used by consumers. Binary packages include file inventories and component notices; corresponding-source packages include locked upstream archives, recipes and patches.

## Build the SDK

Run the following commands from the repository root. The host build fetches checksum-locked sources and compiles native tools; the JSPI build compiles the Wasm dependency closure. The host prefix is `build/install/host` and the target prefix is `build/install-jspi/target`. Build commands and compiler output stream directly to the terminal and CI log, including host tools, target dependencies, supplements, catalogs and browser diagnostics.

```sh
scripts/build-jspi-host
scripts/build-jspi
scripts/check-target.py
scripts/warm-cache
scripts/build-dependency-probe
scripts/build-loop-probe
scripts/test-browser-probe.py build/jspi/sdk-smoke --expect SDK_SMOKE_OK
scripts/test-browser-probe.py build/jspi/sdk-deps --expect SDK_DEPS_OK
scripts/test-browser-probe.py build/jspi/event-loop-probe-sdk --expect LOOP_PROBE_OK
scripts/package.py --profile dependencies --check-repeat
```

The existing SDK runner uses a fresh headless Firefox profile and a loopback static server with isolation headers. It does not use a personal browser profile. Wasm JSPI requires `WebAssembly.Suspending` and `WebAssembly.promising` in the tested browser.

## Internationalization supplement

After building the base SDK:

```sh
scripts/i18n.py build
scripts/i18n.py catalogs --catalogs build/i18n/catalogs-a
scripts/i18n.py catalogs --catalogs build/i18n/catalogs-b
scripts/i18n.py compare --catalogs build/i18n/catalogs-a --compare build/i18n/catalogs-b
scripts/build-i18n-probe
(cd build/jspi/sdk-i18n && node gettext.js && node gettext.js C && node gettext.js POSIX)
scripts/test-browser-probe.py build/jspi/sdk-i18n --expect SDK_I18N_OK
scripts/i18n.py package --catalogs build/i18n/catalogs-a --tag local --check-repeat
```

The supplement contains GNU gettext host tools, libintl, KI18n/Transcript and Qt/KDE catalogs. Its matching source archive includes the recipes, patches and locked supplement inputs. Catalog comparison verifies the two generated catalog trees; it is not an independent full-SDK rebuild.

## QtCore correction supplement

Fresh full builds include the Qt native-event dispatch patches. Queued browser events snapshot their transient target and composed path before dispatch returns; the event-loop probe exercises this through a real Shadow DOM pointer event as well as synchronous dialogs, threads and exceptions. Consumers that need a separate archive bound to an immutable base can generate the existing supplement with:

```sh
python3 scripts/qtcore-correction.py --base-sdk PATH_TO_VERIFIED_BASE --output cache/prebuilt/qtcore-local
```

This copies the base QtCore archive before replacing its corrected object. It verifies the exact base inventory and includes corresponding Qt source and licenses. Choose a new output directory rather than overwriting an existing package.

## Verification boundary

CI runs C/C++ formatting and Python checks first. It then builds and packages the SDK, internationalization supplement and QtCore correction, uploads them, and runs archive checks, catalog and packaging comparisons, and runtime probes. Failed verification does not prevent downloading the uploaded artifacts. A packaged-SDK probe rebuild temporarily hides the original target prefix and uses the extracted SDK with its compiler cache frozen, then runs the resulting probe in Firefox. Repeat packaging uses separate `build/package-repeat/` outputs and compares them with the uploaded archives.

After all checks pass, pushes to `main` and manual runs on `main` create or update the `latest` tag and the `Nightly build` prerelease. It contains the SDK, internationalization and QtCore correction archives, their corresponding sources and available checksum files. PRs and manual runs on other branches do not publish.

A fresh build in this repository and a remote CI run have not yet been verified. Source checksums, target-archive checks and repeated packaging are distinct checks. `--check-repeat` compares packaging of one staged tree, not independent compilation. A cold build, actual browser execution, artifact relocation and two independently compiled matching SDKs must be verified separately. The current workflow uses Ubuntu 26.04 and `emscripten-core/setup-emsdk@v16`, reading its Emscripten version from `.emscripten-version`; its host compiler and complete build image are not yet fully pinned.

## C and C++ formatting

Use clang-format 22, which is preinstalled on the Ubuntu 26.04 runner. The repository configuration preserves embedded JavaScript in Emscripten macros and keeps string literals intact.

```sh
scripts/format.sh
scripts/format.sh --check
```

The default applies formatting; `--check` reports formatting errors without modifying files. CI uses `scripts/format.sh --check` before Python setup and dependency builds.

## Python checks

For local development, create an isolated environment and install the pinned checking tools:

```sh
python3 -m venv build/python-checks
build/python-checks/bin/python -m pip install --cache-dir cache/pip -r requirements.txt
build/python-checks/bin/ruff format --check scripts
build/python-checks/bin/ruff check scripts
build/python-checks/bin/mypy
```

CI uses Python 3.14 from `actions/setup-python` and runs these checks directly without creating a virtual environment. Use `build/python-checks/bin/ruff format scripts` to apply formatting locally.
