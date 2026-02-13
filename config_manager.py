#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
配置管理模块
负责加载、保存和验证配置文件
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Tuple, List, Any

BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = BASE_DIR / "config.json"

# 必需的配置项
REQUIRED_CONFIG_KEYS = [
    "SYSTEM_PROMPT",
    "OLLAMA_MODEL",
    "REQUEST_DELAY_SECONDS",
]


def load_config() -> Dict[str, Any]:
    """
    加载配置文件

    Returns:
        配置字典，如果文件不存在或解析失败则返回空字典
    """
    if not CONFIG_PATH.exists():
        return {}
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"⚠️ 警告：加载配置失败 {e}")
        return {}


def save_config(config: Dict[str, Any]) -> None:
    """
    保存配置到文件

    Args:
        config: 配置字典
    """
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"⚠️ 保存配置失败: {e}")


def get_posts_dir(config: Dict[str, Any] = None) -> Path:
    """
    获取文章目录路径

    Args:
        config: 配置字典，如果为 None 则自动加载

    Returns:
        文章目录的绝对路径
    """
    if config is None:
        config = load_config()

    posts = config.get("POSTS_DIR")
    if isinstance(posts, str) and posts.strip():
        return (BASE_DIR / posts).resolve()
    return (BASE_DIR / "posts").resolve()


def validate_config(config: Dict[str, Any]) -> Tuple[bool, str]:
    """
    验证配置是否完整

    Args:
        config: 配置字典

    Returns:
        (是否有效, 错误信息)
    """
    missing = [k for k in REQUIRED_CONFIG_KEYS if not config.get(k)]
    if missing:
        return False, f"缺少配置项：{', '.join(missing)}"
    return True, ""


def get_config_value(key: str, default: Any = None) -> Any:
    """
    获取单个配置项的值

    Args:
        key: 配置项键名
        default: 默认值

    Returns:
        配置值或默认值
    """
    config = load_config()
    return config.get(key, default)


def set_config_value(key: str, value: Any) -> None:
    """
    设置单个配置项的值

    Args:
        key: 配置项键名
        value: 配置值
    """
    config = load_config()
    config[key] = value
    save_config(config)
