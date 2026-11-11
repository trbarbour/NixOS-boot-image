"""Absolute paths of the tools the root helper runs (Codex on #350).

sudo's ``secure_path`` replaces ``PATH``, so the helper must not look tools up
there.  The flake's ``writeImage`` package overwrites this file with the
store paths; in a checkout the defaults are looked up on ``PATH``.
"""

ZSTD = "zstd"
