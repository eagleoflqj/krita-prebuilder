#!/usr/bin/env python3
"""Run a local probe in a fresh headless Firefox; test server is not a product backend."""

import argparse
import shutil
import subprocess
import tempfile
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--page", default="index.html")
    parser.add_argument("--expect", default="PTHREAD_PROBE_OK")
    parser.add_argument("--timeout", type=int, default=45)
    parser.add_argument(
        "--isolation",
        choices=["headers", "service-worker"],
        default="headers",
        help="service-worker sends no COOP/COEP headers from the server",
    )
    args = parser.parse_args()
    directory = args.directory.resolve(strict=True)
    firefox = shutil.which("firefox")
    if not firefox:
        raise SystemExit("Firefox is required")
    passed = threading.Event()
    failures: list[str] = []

    class Handler(SimpleHTTPRequestHandler):
        def end_headers(self) -> None:
            if args.isolation == "headers":
                self.send_header("Cross-Origin-Opener-Policy", "same-origin")
                self.send_header("Cross-Origin-Embedder-Policy", "require-corp")
            self.send_header("Cache-Control", "no-store")
            super().end_headers()

        def do_GET(self) -> None:
            request = urlsplit(self.path)
            if request.path == "/__probe_result":
                status = parse_qs(request.query).get("status", [""])[0]
                if status == args.expect:
                    passed.set()
                elif status.startswith("FAIL:"):
                    failures.append(status)
                    passed.set()
                self.send_response(204)
                self.end_headers()
            elif request.path == "/__probe_log":
                print(parse_qs(request.query).get("message", [""])[0], flush=True)
                self.send_response(204)
                self.end_headers()
            else:
                super().do_GET()

    temporary = ROOT / "build/tmp"
    temporary.mkdir(parents=True, exist_ok=True)
    with ThreadingHTTPServer(
        ("127.0.0.1", 0), partial(Handler, directory=str(directory))
    ) as server:
        server.daemon_threads = True
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        url = f"http://127.0.0.1:{server.server_port}/{args.page}?test=1"
        try:
            with tempfile.TemporaryDirectory(
                prefix="firefox-probe-", dir=temporary
            ) as profile:
                process = subprocess.Popen(
                    [
                        firefox,
                        "--headless",
                        "--no-remote",
                        "--profile",
                        profile,
                        url,
                    ],
                    stderr=subprocess.STDOUT,
                )
                try:
                    success = passed.wait(args.timeout)
                finally:
                    process.terminate()
                    try:
                        process.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()
            if failures:
                raise SystemExit(failures[0])
            if not success:
                raise SystemExit(
                    f"No success report within {args.timeout}s; see browser output above"
                )
            print(f"PASS in Firefox: {args.expect}")
        finally:
            server.shutdown()
            thread.join()


if __name__ == "__main__":
    main()
