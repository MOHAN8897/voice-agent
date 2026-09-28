"""Realign saved compiled-brain text to the dial language (audit migration helper).

Runtime dial paths already call `realign_compiled_brain_for_session` on locked brains.
Use this module to batch-fix on-disk copies after language-pack updates.
"""
from __future__ import annotations

import argparse
from pathlib import Path

from server.brain.script_entities import realign_compiled_brain_for_session


def realign_file(path: Path, language: str, *, direction: str = "outbound") -> bool:
    text = path.read_text(encoding="utf-8")
    aligned = realign_compiled_brain_for_session(text, language, direction=direction)
    if aligned == text:
        return False
    path.write_text(aligned, encoding="utf-8")
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description="Realign compiled brain files for a locale.")
    parser.add_argument("paths", nargs="+", type=Path, help="compiled brain .txt files")
    parser.add_argument("--language", required=True, help="BCP-47 locale, e.g. te-IN")
    parser.add_argument("--direction", default="outbound", choices=("outbound", "inbound"))
    args = parser.parse_args()
    changed = 0
    for path in args.paths:
        if realign_file(path, args.language, direction=args.direction):
            changed += 1
            print(f"updated {path}")
    print(f"done: {changed}/{len(args.paths)} files changed")


if __name__ == "__main__":
    main()
