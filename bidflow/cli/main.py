from __future__ import annotations

import argparse

from bidflow.cli import agent, analyze, market, replay, session


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="bidflow", description="BidFlow course-bidding sandbox CLI.")
    parser.add_argument("--config", "-c", default=None, help="Global config path. Defaults to ~/.bidflow/config.yaml.")
    subparsers = parser.add_subparsers(dest="command")
    agent.add_parser(subparsers)
    market.add_parser(subparsers)
    session.add_parser(subparsers)
    replay.add_parser(subparsers)
    analyze.add_parser(subparsers)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        return 0
    if args.command == "agent":
        return agent.run(args)
    if args.command == "market":
        return market.run(args)
    if args.command == "session":
        return session.run(args)
    if args.command == "replay":
        return replay.run(args)
    if args.command == "analyze":
        return analyze.run(args)
    parser.error(f"unknown command '{args.command}'")
    return 2
