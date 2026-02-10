#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""清除 output 目录下的缓存文件"""

from __future__ import annotations

from pathlib import Path
import shutil


def clear_output_cache(base_dir: Path, output_name: str = "output") -> int:
    """清除 output 目录下的所有文件，并返回删除的文件数量。"""
    output_dir = base_dir / output_name
    if not output_dir.exists():
        return 0

    removed = 0
    for entry in output_dir.iterdir():
        try:
            if entry.is_dir() and not entry.is_symlink():
                shutil.rmtree(entry)
            else:
                entry.unlink(missing_ok=True)
            removed += 1
        except Exception:
            # Best-effort cleanup; skip entries that cannot be removed.
            continue
    return removed
