"""Automated verification script checking for hardcoded hex/rgb/hsl colors outside theme.css."""
from __future__ import annotations

import json
from pathlib import Path
import re
import sys

# Pattern matching hex (#FFF, #FFFFFF, #FFFFFFFF) or rgb/rgba or hsl/hsla
COLOR_PATTERN = re.compile(r'(#[0-9a-fA-F]{3,8}|rgba?\([^)]+\)|hsla?\([^)]+\))')

EXCLUDE_DIRS = {".git", ".pytest_cache", "__pycache__", "node_modules", "data", "migrations", ".system_generated"}
EXCLUDE_FILES = {"theme.css"}


def check_files(frontend_dir: Path) -> int:
    allowlist_path = Path(__file__).resolve().parent / "color_allowlist.json"
    allowed_patterns = []
    if allowlist_path.exists():
        with open(allowlist_path, "r", encoding="utf-8") as f:
            allowed_patterns = json.load(f).get("allowed", [])

    violations = []

    for file_path in frontend_dir.rglob("*"):
        if any(ex in file_path.parts for ex in EXCLUDE_DIRS):
            continue
        if file_path.name in EXCLUDE_FILES:
            continue
        if file_path.suffix not in (".css", ".html", ".js"):
            continue

        try:
            lines = file_path.read_text(encoding="utf-8").splitlines()
        except Exception:
            continue

        for line_num, line in enumerate(lines, 1):
            # Skip comments or allowed markers
            if any(allow in line for allow in allowed_patterns):
                continue
            
            # Find matches
            matches = COLOR_PATTERN.findall(line)
            for match in matches:
                # Ignore url(...) or font-family or variable declarations in theme
                if "url(" in line and ("svg" in line or "data:image" in line):
                    continue
                violations.append((file_path, line_num, match, line.strip()))

    if violations:
        print(f"\n[FAIL] Found {len(violations)} hardcoded color occurrences outside theme.css:\n")
        for f, ln, c, code in violations[:40]:
            print(f"  {f.name}:{ln} -> '{c}' in: {code[:70]}")
        if len(violations) > 40:
            print(f"  ... and {len(violations) - 40} more.")
        return len(violations)
    else:
        print("\n[SUCCESS] Zero hardcoded colors found outside theme.css!")
        return 0


if __name__ == "__main__":
    fe_dir = Path(__file__).resolve().parent.parent / "frontend"
    count = check_files(fe_dir)
    sys.exit(0 if count == 0 else 1)
