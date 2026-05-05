"""Interactive single-line prompts for the sort-files CLI."""
from __future__ import annotations

import sys
from pathlib import Path


def _prompt(question: str, valid: tuple[str, ...], default: str | None = None) -> str:
    """Read a single-line answer constrained to ``valid`` (case-insensitive).
    Re-prompts until a valid answer or EOF.
    """
    suffix = f" [{('/'.join(valid))}]"
    if default:
        suffix += f" (default: {default})"
    suffix += " > "
    while True:
        try:
            answer = input(question + suffix).strip().lower()
        except EOFError:
            print()
            return default or valid[0]
        if not answer and default:
            return default
        for v in valid:
            if answer == v.lower() or answer == v.lower()[0]:
                return v
        print(f"  please answer one of: {', '.join(valid)}")


def _prompt_path(question: str) -> Path:
    while True:
        try:
            answer = input(question + " > ").strip()
        except EOFError:
            print()
            sys.exit(1)
        if answer:
            return Path(answer).expanduser().resolve()
        print("  please enter a path")
