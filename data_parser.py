#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
数据解析模块
负责解析 AI 输出和标签数据
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Dict, List, Tuple


def split_label(line: str) -> Tuple[str, str]:
    """
    从行中分离标签和内容

    Args:
        line: 待解析的行

    Returns:
        (标签, 内容)
    """
    if line.startswith("@@S"):
        end = line.find("@@ ")
        if end != -1:
            label = line[: end + 3]
            return label, line[end + 3:]
    return "", line


def parse_label(label: str) -> Tuple[str, str]:
    """
    解析标签获取文件名

    Args:
        label: 标签字符串

    Returns:
        (标签, 文件名)
    """
    match = re.match(r"^@@S\d+\|([^@]+)@@\s*$", label)
    if not match:
        return "", ""
    return label, match.group(1)


def parse_ai_json(text: str) -> Dict[str, str]:
    """
    解析 AI 输出的 JSON 格式

    Args:
        text: AI 输出文本

    Returns:
        包含 original_text, error_type, description, checked_text 的字典
    """
    try:
        data = json.loads(text)
        return {
            "original_text": data.get("original_text", ""),
            "error_type": data.get("error_type", ""),
            "description": data.get("description", ""),
            "checked_text": data.get("checked_text", ""),
        }
    except (json.JSONDecodeError, AttributeError):
        # 如果解析失败，返回空字典
        return {
            "original_text": "",
            "error_type": "",
            "description": "",
            "checked_text": text.strip(),
        }


def load_change_out(path: Path) -> Dict[str, Dict[str, str]]:
    """
    加载 AI 处理结果文件

    Args:
        path: change_out 文件路径

    Returns:
        标签到数据的映射字典
    """
    data: Dict[str, Dict[str, str]] = {}
    with open(path, "r", encoding="utf-8") as f:
        for raw_line in f:
            line = raw_line.strip()
            if not line:
                continue
            label, content = split_label(line)
            if not label:
                continue
            parsed = parse_ai_json(content)
            data[label] = {
                "original_text": parsed["original_text"],
                "error_type": parsed["error_type"],
                "description": parsed["description"],
                "checked_text": parsed["checked_text"],
                "raw": content,
            }
    return data


def load_filtered_change_lines(path: Path, labels: set[str]) -> List[Tuple[str, str]]:
    """
    加载过滤后的 change 文件行

    Args:
        path: change 文件路径
        labels: 要保留的标签集合

    Returns:
        (标签, 句子) 元组列表
    """
    items: List[Tuple[str, str]] = []
    with open(path, "r", encoding="utf-8") as f:
        for raw_line in f:
            line = raw_line.strip()
            if not line:
                continue
            label, sentence = split_label(line)
            if label and label in labels:
                items.append((label, sentence))
    return items
