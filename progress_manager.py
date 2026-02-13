#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
进度管理模块
负责保存和加载审查进度
"""

from __future__ import annotations

import configparser
from pathlib import Path
from typing import Tuple

BASE_DIR = Path(__file__).resolve().parent
PROGRESS_FILE = BASE_DIR / "review_progress.ini"
PROGRESS_SECTION = "review_progress"


def load_review_progress() -> Tuple[str, str, int]:
    """
    加载审查进度

    Returns:
        (change_file 路径, change_out_file 路径, 下一个索引)
    """
    if not PROGRESS_FILE.exists():
        return "", "", 0

    config = configparser.ConfigParser()
    try:
        config.read(PROGRESS_FILE, encoding="utf-8")
        if PROGRESS_SECTION not in config:
            return "", "", 0

        section = config[PROGRESS_SECTION]
        change_path = section.get("change_file", "")
        change_out_file = section.get("change_out_file", "")
        next_index = int(section.get("next_index", "0"))
        return change_path, change_out_file, max(0, next_index)
    except Exception:
        return "", "", 0


def save_review_progress(change_path: Path, change_out_file: Path, next_index: int) -> None:
    """
    保存审查进度

    Args:
        change_path: change 文件路径
        change_out_file: change_out 文件路径
        next_index: 下一个要处理的索引
    """
    config = configparser.ConfigParser()
    config[PROGRESS_SECTION] = {
        "change_file": str(change_path),
        "change_out_file": str(change_out_file),
        "next_index": str(max(0, next_index)),
    }
    try:
        with open(PROGRESS_FILE, "w", encoding="utf-8") as f:
            config.write(f)
    except Exception as e:
        print(f"⚠️ 保存进度失败: {e}")


def clear_review_progress() -> None:
    """
    清除审查进度文件
    """
    try:
        if PROGRESS_FILE.exists():
            PROGRESS_FILE.unlink()
    except Exception as e:
        print(f"⚠️ 清除进度失败: {e}")


def has_review_progress() -> bool:
    """
    检查是否存在审查进度

    Returns:
        是否存在未完成的审查进度
    """
    return PROGRESS_FILE.exists()
