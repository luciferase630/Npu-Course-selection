from __future__ import annotations

import argparse


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="bidflow", description="BidFlow course-bidding sandbox CLI.")
    parser.add_argument("--config", "-c", default=None, help="Global config path. Defaults to ~/.bidflow/config.yaml.")
    subparsers = parser.add_subparsers(dest="command")
    subparsers.add_parser("agent", help="Manage bidding agents.")
    subparsers.add_parser("market", help="Generate and inspect markets.")
    subparsers.add_parser("session", help="Run online sessions.")
    subparsers.add_parser("replay", help="Run fixed-background replays.")
    subparsers.add_parser("analyze", help="Analyze run outputs.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        return 0
    parser.error(f"subcommand '{args.command}' is not implemented yet")
    return 2
