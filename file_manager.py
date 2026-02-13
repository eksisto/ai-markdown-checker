#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
文件管理模块
负责文件和目录的管理操作
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional, Dict

BASE_DIR = Path(__file__).resolve().parent


def ensure_output_dir() -> Path:
    """
    确保 output 目录存在

    Returns:
        output 目录路径
    """
    output_dir = BASE_DIR / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def list_output_files(pattern: str = "*.txt") -> List[Path]:
    """
    列出 output 目录中的文件

    Args:
        pattern: 文件匹配模式

    Returns:
        排序后的文件路径列表
    """
    output_dir = ensure_output_dir()
    return sorted([p for p in output_dir.glob(pattern) if p.is_file()])


def list_markdown_files(posts_dir: Path) -> List[Path]:
    """
    列出文章目录中的所有 Markdown 文件

    Args:
        posts_dir: 文章目录路径

    Returns:
        排序后的 Markdown 文件路径列表
    """
    if not posts_dir.exists():
        return []
    return sorted([p for p in posts_dir.rglob("*.md") if p.is_file()])


def make_output_stem(path: Path) -> str:
    """
    为输出文件生成文件名（不带扩展名）

    Args:
        path: 源文件路径

    Returns:
        文件名（stem）
    """
    return path.stem


def resolve_md_path(filename: str, posts_dir: Path, cache: Dict[str, Path]) -> Optional[Path]:
    """
    解析 Markdown 文件路径

    Args:
        filename: 文件名
        posts_dir: 文章目录
        cache: 路径缓存字典

    Returns:
        解析后的文件路径，如果未找到则返回 None
    """
    # 检查缓存
    if filename in cache:
        return cache[filename]

    # 在 posts_dir 中递归搜索
    matches = [p for p in posts_dir.rglob(filename) if p.is_file()]

    if len(matches) == 1:
        cache[filename] = matches[0]
        return matches[0]

    if len(matches) > 1:
        # 多个匹配项，需要用户选择（由调用者处理）
        return None

    # 未找到匹配项
    return None


def replace_sentence_in_file(path: Path, old_sentence: str, new_sentence: str) -> bool:
    """
    在文件中替换句子

    Args:
        path: 文件路径
        old_sentence: 原句子
        new_sentence: 新句子

    Returns:
        是否成功替换
    """
    try:
        content = path.read_text(encoding="utf-8")
    except Exception:
        return False

    if old_sentence not in content:
        return False

    updated = content.replace(old_sentence, new_sentence, 1)

    try:
        path.write_text(updated, encoding="utf-8")
    except Exception:
        return False

    return True


def check_sentence_in_file(path: Path, sentence: str) -> bool:
    """
    检查句子是否存在于文件中

    Args:
        path: 文件路径
        sentence: 要检查的句子

    Returns:
        句子是否存在
    """
    try:
        content = path.read_text(encoding="utf-8")
        return sentence in content
    except Exception:
        return False
