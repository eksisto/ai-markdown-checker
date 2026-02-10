#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""POSTS_DIR 的 Git 提交助手"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional
import subprocess


BASE_DIR = Path(__file__).resolve().parent


def load_posts_dir() -> Path:
    config_path = BASE_DIR / "config.json"
    default_path = BASE_DIR / "posts"

    if not config_path.exists():
        return default_path.resolve()

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
            path_str = config.get("POSTS_DIR")
            if path_str:
                return (BASE_DIR / path_str).resolve()
    except Exception as e:
        print(f"Warning: Failed to load config: {e}")

    return default_path.resolve()


POSTS_DIR = load_posts_dir()


def wait_for_key(message: str = "按任意键退出...") -> None:
    print()
    print(message)
    try:
        import msvcrt
    except ImportError:
        input()
        return

    msvcrt.getch()


def run_git(args: list[str], capture_output: bool = False) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git"] + args,
        cwd=str(POSTS_DIR),
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE if capture_output else None,
        stderr=subprocess.PIPE if capture_output else None,
    )


def ensure_git_repo() -> bool:
    git_dir = POSTS_DIR / ".git"
    if git_dir.exists():
        return True

    print("⚠️ 警告: POSTS_DIR 不是 Git 仓库。")
    try:
        choice = input("是否在此处初始化一个新的 Git 仓库? (y/n): ").strip()
    except EOFError:
        return False

    if choice.lower() != "y":
        print("操作已取消。")
        return False

    result = run_git(["init"], capture_output=True)
    if result.returncode == 0:
        print("✅ Git 仓库初始化成功！")
        return True

    print("❌ 错误: Git 仓库初始化失败！")
    if result.stderr:
        print(result.stderr.strip())
    return False


def has_pending_changes() -> Optional[bool]:
    result = run_git(["status", "--porcelain"], capture_output=True)
    if result.returncode != 0:
        print("❌ 错误: 无法检查 Git 状态。")
        if result.stderr:
            print(result.stderr.strip())
        return None
    return bool(result.stdout.strip())


def show_changes_summary() -> bool:
    print("以下是当前未提交的更改:")
    diff_stat_result = run_git(
        ["diff", "--stat", "--color=always"], capture_output=True)
    if diff_stat_result.returncode == 0 and diff_stat_result.stdout:
        print("变更统计:")
        print(diff_stat_result.stdout.rstrip())

    diff_result = run_git(["diff", "--word-diff=plain",
                          "--color=always"], capture_output=True)
    if diff_result.returncode == 0 and diff_result.stdout:
        diff_output = diff_result.stdout.replace("-]{+", "-] {+")
        print()
        print("变更详情：")
        print(diff_output.rstrip())

    try:
        choice = input("确认继续提交这些更改? (y/n): ").strip()
    except EOFError:
        return False

    if choice.lower() == "y":
        return True

    print("操作已取消。")
    return False


def get_commit_message() -> str:
    default_msg = f"Auto-commit on {datetime.now():%Y-%m-%d %H:%M:%S}"
    print("请输入本次提交的说明 (直接按 Enter 将使用默认日期作为信息):")
    try:
        msg = input("  > ").strip()
    except EOFError:
        msg = ""
    if not msg:
        print(f"未提供提交说明，已使用默认值: \"{default_msg}\"")
        return default_msg
    return msg


def main() -> int:
    if not POSTS_DIR.exists():
        print(f"POSTS_DIR 未找到: {POSTS_DIR}")
        wait_for_key()
        return 1

    print("--- Git 自动提交助手已启动 ---")
    print(f"工作目录: {POSTS_DIR}")

    try:
        os.chdir(POSTS_DIR)
    except OSError as e:
        print(f"切换目录失败: {e}")
        wait_for_key()
        return 1

    try:
        if not ensure_git_repo():
            wait_for_key()
            return 0

        pending = has_pending_changes()
        if pending is None:
            wait_for_key()
            return 1

        if not pending:
            print("工作区非常干净，没有任何需要提交的更改。无需操作。")
            wait_for_key()
            return 0

        if not show_changes_summary():
            wait_for_key()
            return 0

        print("正在将所有更改添加到暂存区 (git add .)...")
        add_result = run_git(["add", "."], capture_output=True)
        if add_result.returncode != 0:
            print("添加文件失败。")
            if add_result.stderr:
                print(add_result.stderr.strip())
            wait_for_key()
            return add_result.returncode

        commit_msg = get_commit_message()
        print("正在执行提交...")
        commit_result = run_git(
            ["commit", "-m", commit_msg], capture_output=True)
        if commit_result.returncode == 0:
            print("✅ 提交成功！")
            print(f"提交信息: \"{commit_msg}\"")
            wait_for_key()
            return 0

        print("❌ 提交失败！")
        if commit_result.stderr:
            print(commit_result.stderr.strip())
        else:
            print("可能的原因包括：合并冲突、pre-commit 钩子失败等。")
        wait_for_key()
        return commit_result.returncode
    except FileNotFoundError:
        print("未找到 Git 命令，请先安装 Git。")
        wait_for_key()
        return 1


if __name__ == "__main__":
    sys.exit(main())
