"""Run the local TeaGuard application on loopback; all policy lives in modules."""

import argparse
import json
from http.server import ThreadingHTTPServer
from pathlib import Path

from teaguard.http_app import make_handler
from teaguard.nature_service import VERSION, NatureService

ROOT = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=50115)
    args = parser.parse_args()
    (ROOT / "runtime").mkdir(exist_ok=True)
    service = NatureService()
    with ThreadingHTTPServer(("127.0.0.1", args.port), make_handler(service)) as server:
        receipt = {
            "url": f"http://127.0.0.1:{server.server_port}/",
            "version": VERSION,
            "model_fit": False,
        }
        (ROOT / "runtime/runtime.json").write_text(
            json.dumps(receipt), encoding="utf-8"
        )
        print(json.dumps(receipt), flush=True)
        server.serve_forever()


if __name__ == "__main__":
    main()
