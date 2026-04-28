from __future__ import annotations

import argparse

from bidflow.gui.server import serve


def add_parser(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = subparsers.add_parser("gui", help="Launch the local BidFlow GUI.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-browser", action="store_true", help="Do not open a browser automatically.")


def run(args: argparse.Namespace) -> int:
    serve(host=args.host, port=args.port, open_browser=not args.no_browser)
    return 0
