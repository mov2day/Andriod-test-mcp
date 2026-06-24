"""File discovery utilities for QE-MCP.

Discovers source and test files, pairs them, and respects ``.gitignore``
rules when present.
"""

from __future__ import annotations

import re
from fnmatch import fnmatch
from pathlib import Path
from typing import Dict, List, Optional


class FileScanner:
    """Walk a repository tree, discover source and test files, and pair them."""

    def __init__(self, repo_path: str | Path) -> None:
        self.repo_path = Path(repo_path).resolve()
        self._gitignore_patterns: List[str] = self._load_gitignore()

    # -- public API ---------------------------------------------------------

    def discover_source_files(
        self,
        globs: List[str],
        exclude_patterns: Optional[List[str]] = None,
    ) -> List[str]:
        """Return source file paths matching any of *globs*.

        Files matching *exclude_patterns* or ``.gitignore`` rules are skipped.
        """
        exclude_patterns = exclude_patterns or []
        results: List[str] = []

        for pattern in globs:
            for path in self.repo_path.rglob(pattern):
                if not path.is_file():
                    continue
                rel = str(path.relative_to(self.repo_path))
                if self._is_ignored(rel, exclude_patterns):
                    continue
                results.append(rel)

        # Deduplicate while preserving order.
        seen: set[str] = set()
        unique: List[str] = []
        for item in results:
            if item not in seen:
                seen.add(item)
                unique.append(item)
        return unique

    def find_test_files(self, test_globs: List[str]) -> List[str]:
        """Return test file paths matching any of *test_globs*."""
        results: List[str] = []
        for pattern in test_globs:
            for path in self.repo_path.rglob(pattern):
                if path.is_file():
                    rel = str(path.relative_to(self.repo_path))
                    if not self._is_gitignored(rel):
                        results.append(rel)

        seen: set[str] = set()
        unique: List[str] = []
        for item in results:
            if item not in seen:
                seen.add(item)
                unique.append(item)
        return unique

    def pair_source_to_test(
        self,
        source_files: List[str],
        test_files: List[str],
        naming_pattern: str,
    ) -> Dict[str, Optional[str]]:
        """Map each source file to its corresponding test file (or ``None``).

        *naming_pattern* is a regex-style pattern where ``{name}`` is
        replaced with the source file's stem.  For example:
        ``test_{name}.py`` or ``{name}_test.py``.
        """
        test_set = set(test_files)
        mapping: Dict[str, Optional[str]] = {}

        for source in source_files:
            source_path = Path(source)
            stem = source_path.stem
            # Build the expected test filename from the pattern.
            expected_name = naming_pattern.replace("{name}", stem)
            # Look for a matching test file in the same directory first, then
            # anywhere in the test list.
            same_dir = str(source_path.parent / expected_name)
            if same_dir in test_set:
                mapping[source] = same_dir
            else:
                # Fallback: search by filename match anywhere.
                match = next(
                    (t for t in test_files if Path(t).name == expected_name),
                    None,
                )
                mapping[source] = match

        return mapping

    # -- .gitignore handling ------------------------------------------------

    def _load_gitignore(self) -> List[str]:
        """Parse ``.gitignore`` at the repo root and return patterns."""
        gitignore = self.repo_path / ".gitignore"
        if not gitignore.exists():
            return []
        patterns: List[str] = []
        for line in gitignore.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith("#"):
                patterns.append(stripped)
        return patterns

    def _is_gitignored(self, rel_path: str) -> bool:
        """Check whether *rel_path* matches any ``.gitignore`` pattern."""
        for pattern in self._gitignore_patterns:
            # Normalise directory patterns.
            clean = pattern.rstrip("/")
            if fnmatch(rel_path, clean) or fnmatch(rel_path, f"{clean}/**"):
                return True
            # Also match if any path component matches.
            parts = Path(rel_path).parts
            if any(fnmatch(part, clean) for part in parts):
                return True
        return False

    def _is_ignored(self, rel_path: str, extra_patterns: List[str]) -> bool:
        """Check gitignore *and* caller-supplied exclude patterns."""
        if self._is_gitignored(rel_path):
            return True
        for pattern in extra_patterns:
            if fnmatch(rel_path, pattern):
                return True
        return False
