#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
主程序，CLI 版
"""

from __future__ import annotations

import os
import sys
import subprocess
import ctypes
import shutil
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from clear_output_cache import clear_output_cache
from config_manager import load_config, save_config, get_posts_dir
from progress_manager import load_review_progress, save_review_progress, clear_review_progress
from file_manager import (
    ensure_output_dir,
    list_output_files,
    list_markdown_files,
    make_output_stem,
    resolve_md_path,
    replace_sentence_in_file,
    check_sentence_in_file,
)
from data_parser import (
    split_label,
    parse_label,
    parse_ai_json,
    load_change_out,
    load_filtered_change_lines,
)


BASE_DIR = Path(__file__).resolve().parent


ANSI_RESET = "\x1b[0m"
ANSI_BOLD = "\x1b[1m"
ANSI_DIM = "\x1b[2m"
ANSI_REVERSE = "\x1b[7m"
ANSI_CYAN = "\x1b[36m"
ANSI_YELLOW = "\x1b[33m"
ANSI_GREEN = "\x1b[32m"
ANSI_RED = "\x1b[31m"
ANSI_GRAY = "\x1b[90m"


def _enable_vt_mode() -> None:
    if os.name != "nt":
        return
    try:
        handle = ctypes.windll.kernel32.GetStdHandle(-11)
        mode = ctypes.c_uint32()
        if ctypes.windll.kernel32.GetConsoleMode(handle, ctypes.byref(mode)) == 0:
            return
        ENABLE_VIRTUAL_TERMINAL_PROCESSING = 0x0004
        new_mode = mode.value | ENABLE_VIRTUAL_TERMINAL_PROCESSING
        ctypes.windll.kernel32.SetConsoleMode(handle, new_mode)
    except Exception:
        return


def _supports_color() -> bool:
    if not sys.stdout.isatty():
        return False
    if os.environ.get("NO_COLOR"):
        return False
    return True


def _style(text: str, *codes: str) -> str:
    if not _supports_color() or not codes:
        return text
    return "".join(codes) + text + ANSI_RESET


def _term_width() -> int:
    try:
        width = shutil.get_terminal_size().columns
    except OSError:
        width = 80
    return max(60, min(width, 100))


def _hr(width: Optional[int] = None) -> str:
    line_width = width or _term_width()
    return "-" * line_width


def _render_header(title: str) -> None:
    width = _term_width()
    label = f"[ {title} ]"
    if len(label) > width:
        label = label[: max(0, width - 1)]
    print(_style(label.center(width), ANSI_BOLD, ANSI_CYAN))
    print(_style(_hr(width), ANSI_GRAY))


def _render_footer(text: str) -> None:
    if not text:
        return
    print()
    print(_style(text, ANSI_DIM, ANSI_GRAY))


POSTS_DIR = get_posts_dir()


def clear_screen() -> None:
    os.system("cls")


def read_key() -> str:
    try:
        import msvcrt
    except ImportError:
        return ""

    ch = msvcrt.getch()
    if ch in (b"\x00", b"\xe0"):
        ch2 = msvcrt.getch()
        if ch2 == b"H":
            return "up"
        if ch2 == b"P":
            return "down"
        return ""
    if ch == b"\r":
        return "enter"
    if ch in (b"q", b"Q"):
        return "quit"
    if ch in (b"c", b"C"):
        return "clear"
    return ""


def menu(
        title: str,
        options: List[str],
        footer: str = "",
        allow_clear: bool = False,
) -> Optional[int]:
    if not options:
        return None

    _enable_vt_mode()
    index = 0
    width = _term_width()
    left_pad = " " * 2
    while True:
        clear_screen()
        _render_header(title)
        print()
        for i, option in enumerate(options):
            is_active = i == index
            prefix = "> " if is_active else "  "
            max_width = max(10, width - len(left_pad) - len(prefix))
            text = option
            if len(text) > max_width:
                text = text[: max(0, max_width - 3)] + "..."
            label = _style(text, ANSI_REVERSE) if is_active else text
            line = f"{prefix}{label}"
            print(left_pad + line)
        if footer:
            _render_footer(footer)

        key = read_key()
        if key == "up":
            index = (index - 1) % len(options)
        elif key == "down":
            index = (index + 1) % len(options)
        elif key == "enter":
            return index
        elif key == "quit":
            return None
        elif key == "clear" and allow_clear:
            return -2


def run_script(args: List[str]) -> int:
    result = subprocess.run(
        [sys.executable] + args,
        cwd=str(BASE_DIR),
    )
    return result.returncode


def wait_for_key(message: str = "按任意键继续...") -> None:
    print()
    print(_style(message, ANSI_DIM, ANSI_GRAY))
    read_key()


def resolve_md_path_cli(filename: str, cache: Dict[str, Path]) -> Optional[Path]:
    """
    CLI 特有的 Markdown 路径解析函数，包含用户交互
    """
    # 先尝试使用通用的解析函数
    path = resolve_md_path(filename, POSTS_DIR, cache)
    if path:
        return path

    # 如果有多个匹配项，让用户选择
    matches = [p for p in POSTS_DIR.rglob(filename) if p.is_file()]
    if len(matches) > 1:
        print("发现多个同名文件，请选择：")
        for i, p in enumerate(matches, start=1):
            print(f"  {i}. {p}")
        try:
            choice = input("输入序号选择: ").strip()
            index = int(choice) - 1
            if 0 <= index < len(matches):
                cache[filename] = matches[index]
                return matches[index]
        except (ValueError, EOFError):
            pass

    # 让用户手动输入路径
    try:
        custom = input(f"未找到 {filename}，请输入完整路径(回车跳过): ").strip()
    except EOFError:
        custom = ""
    if custom:
        custom_path = Path(custom)
        if custom_path.exists() and custom_path.is_file():
            cache[filename] = custom_path
            return custom_path
    return None


def mode_changed_files() -> None:
    # 清除旧的审查进度
    clear_review_progress()

    clear_screen()
    _render_header("模式 1：校对修改的 Markdown 文件（需要 Git）")
    print(_style(f"目录：{POSTS_DIR}", ANSI_GRAY))
    print()

    output_dir = ensure_output_dir()
    change_path = output_dir / "changes.txt"
    change_out_path = output_dir / "changes_out.txt"

    rc = run_script([
        str(BASE_DIR / "checker_add.py"),
        str(POSTS_DIR),
        "-o",
        str(change_path),
    ])
    if rc != 0:
        print(_style("提取更改失败", ANSI_RED))
        wait_for_key()
        return

    rc = run_script([
        str(BASE_DIR / "checker_ai.py"),
        str(change_path),
        str(change_out_path),
    ])
    if rc != 0:
        print(_style("AI 处理失败", ANSI_RED))
        wait_for_key()
        return

    print(_style(f"完成。输出: {change_out_path}", ANSI_GREEN))
    wait_for_key()


def mode_single_file() -> None:
    # 清除旧的审查进度
    clear_review_progress()

    files = list_markdown_files(POSTS_DIR)
    if not files:
        clear_screen()
        _render_header("模式 2：选择一个 Markdown 文件")
        print(_style("没有找到 Markdown 文件", ANSI_YELLOW))
        wait_for_key()
        return

    options = [str(p.relative_to(POSTS_DIR)) for p in files]
    selected_index = menu(
        "模式 2：选择一个 Markdown 文件",
        options,
        footer="上下键切换，回车选择，Q 键返回",
    )
    if selected_index is None:
        return

    selected_file = files[selected_index]
    stem = make_output_stem(selected_file)
    output_dir = ensure_output_dir()
    temp_file = output_dir / f"{stem}.txt"
    out_file = output_dir / f"{stem}_out.txt"

    clear_screen()
    _render_header("模式 2：已选择文件")
    print(_style(f"选择: {selected_file}", ANSI_GRAY))
    print()

    rc = run_script([
        str(BASE_DIR / "checker_process_markdown.py"),
        str(selected_file),
        str(temp_file),
    ])
    if rc != 0:
        print(_style("提取段落出错", ANSI_RED))
        wait_for_key()
        return

    rc = run_script([
        str(BASE_DIR / "checker_ai.py"),
        str(temp_file),
        str(out_file),
    ])
    if rc != 0:
        print(_style("AI 处理失败", ANSI_RED))
        wait_for_key()
        return

    print(_style(f"完成。输出: {out_file}", ANSI_GREEN))
    wait_for_key()


def mode_review_changes() -> None:
    output_files = list_output_files("*.txt")
    if not output_files:
        clear_screen()
        _render_header("模式 3：用户审查修改")
        print(_style("output 目录中没有可选的 .txt 文件", ANSI_YELLOW))
        wait_for_key()
        return

    change_options = [
        p.name
        for p in output_files
        if "_out" not in p.stem
    ]
    selected_change_index = menu(
        "模式 3：选择 Markdown 处理文件（change.txt 或 filename.txt）",
        change_options,
        footer="上下键切换，回车选择，Q 键返回",
    )
    if selected_change_index is None:
        return

    change_path = output_files[selected_change_index]

    change_out_candidates = [
        p for p in output_files if p.name.endswith("_out.txt")
    ]
    if not change_out_candidates:
        change_out_candidates = output_files

    change_out_options = [p.name for p in change_out_candidates]
    selected_out_index = menu(
        "模式 3：选择 AI 结果文件（change_out.txt 或 filename_out.txt）",
        change_out_options,
        footer="上下键切换，回车选择，Q 键返回",
    )
    if selected_out_index is None:
        return

    change_out_path = change_out_candidates[selected_out_index]

    clear_screen()
    _render_header("模式 3：用户审查修改")
    print(_style(f"change.txt: {change_path}", ANSI_GRAY))
    print(_style(f"change_out.txt: {change_out_path}", ANSI_GRAY))
    print()

    change_out_data = load_change_out(change_out_path)
    if not change_out_data:
        print(_style("change_out.txt 中没有可处理的内容", ANSI_YELLOW))
        wait_for_key()
        return

    filtered_lines = load_filtered_change_lines(
        change_path, set(change_out_data.keys()))
    if not filtered_lines:
        print(_style("change.txt 中没有匹配到 change_out.txt 的标签", ANSI_YELLOW))
        wait_for_key()
        return

    total_lines = len(filtered_lines)

    progress_change, progress_out, progress_index = load_review_progress()
    change_path_resolved = str(change_path.resolve())
    change_out_path_resolved = str(change_out_path.resolve())
    start_index = 0
    if progress_change == change_path_resolved and progress_out == change_out_path_resolved:
        if 0 <= progress_index < len(filtered_lines):
            start_index = progress_index
        else:
            clear_review_progress()
    else:
        save_review_progress(change_path, change_out_path, 0)

    md_cache: Dict[str, Path] = {}
    failed_pairs: List[Tuple[str, str]] = []
    for idx in range(start_index, len(filtered_lines)):
        label, sentence = filtered_lines[idx]

        ai_info = change_out_data.get(label, {})
        original_text = ai_info.get("original_text") or sentence
        error_type = ai_info.get("error_type", "")
        description = ai_info.get("description", "")
        checked_text = ai_info.get("checked_text") or ai_info.get("raw", "")

        # 1. 解析标签并定位文件
        _, filename = parse_label(label)
        md_path = None
        if filename:
            md_path = resolve_md_path_cli(filename, md_cache)

        # 2. 预检查句子是否存在于文件中
        exists = False
        if md_path:
            exists = check_sentence_in_file(md_path, sentence)

        # 3. 如果没找到，直接跳过并记录
        if not exists:
            change_line = f"{label}{sentence}"
            raw_out = ai_info.get("raw") or ai_info.get("checked_text") or ""
            out_line = f"{label}{raw_out}" if raw_out else label
            failed_pairs.append((change_line, out_line))
            save_review_progress(change_path, change_out_path, idx + 1)
            continue

        # 4. 只有存在时才让用户审查
        clear_screen()
        _render_header("模式 3：用户审查修改")
        print(_style(f"进度: {idx + 1}/{total_lines}", ANSI_GREEN))
        print(_style("Enter 应用 AI 建议 | Ctrl+P 跳过不修改 | 输入新句子并回车确认 | Q 退出并保存进度", ANSI_GRAY))
        print()

        print(_style(_hr(), ANSI_GRAY))
        print(f"文件: {md_path}")
        print(_style(_hr(), ANSI_GRAY))
        print(f"原句: {original_text}")
        if error_type:
            print(_style(f"错误类型: {error_type}", ANSI_YELLOW))
        if description:
            print(_style(f"说明: {description}", ANSI_CYAN))
        print(f"建议: {checked_text}")
        print(_style(_hr(), ANSI_GRAY))
        print("输入修改后的句子，直接回车应用 AI 建议，Ctrl+P 跳过，输入 Q 退出并保存进度：")

        # 读取用户输入，支持 Ctrl+P 跳过
        try:
            import msvcrt
            import sys

            sys.stdout.write("> ")
            sys.stdout.flush()

            buffer = []
            while True:
                ch = msvcrt.getwch()

                # Ctrl+P 跳过
                if ch == '\x10':
                    print("\n[已跳过]")
                    save_review_progress(change_path, change_out_path, idx + 1)
                    new_text = None
                    break

                # Enter 确认
                elif ch == '\r':
                    print()
                    new_text = "".join(buffer)
                    break

                # Backspace
                elif ch == '\x08':
                    if buffer:
                        sys.stdout.write('\b \b')
                        sys.stdout.flush()
                        buffer.pop()

                # Ctrl+C 取消
                elif ch == '\x03':
                    print("\n[已取消]")
                    save_review_progress(change_path, change_out_path, idx)
                    return

                else:
                    sys.stdout.write(ch)
                    sys.stdout.flush()
                    buffer.append(ch)

        except (ImportError, EOFError):
            # 如果 msvcrt 不可用，回退到标准输入
            try:
                new_text = input("> ")
            except EOFError:
                new_text = ""

        # 如果按了 Ctrl+P 跳过，继续下一个
        if new_text is None:
            continue

        # 检查是否退出
        if new_text.strip().lower() == "q":
            save_review_progress(change_path, change_out_path, idx)
            print(_style("已保存进度，稍后可继续。", ANSI_YELLOW))
            wait_for_key()
            return

        new_text = new_text.strip()

        # 如果什么都不输入直接回车，应用 AI 建议
        if not new_text:
            new_text = checked_text.strip()
            if not new_text:
                save_review_progress(change_path, change_out_path, idx + 1)
                continue

        if not replace_sentence_in_file(md_path, sentence, new_text):
            # 虽然前面检查过存在，但由于多线程或磁盘延迟（极少数情况）可能失败
            print("未找到可替换的句子，跳过该条。")
            change_line = f"{label}{sentence}"
            raw_out = ai_info.get("raw") or ai_info.get("checked_text") or ""
            out_line = f"{label}{raw_out}" if raw_out else label
            failed_pairs.append((change_line, out_line))

        save_review_progress(change_path, change_out_path, idx + 1)

    print("\n✅ 审查完成")
    clear_review_progress()

    # 成功结束后自动删除 changes.txt 和 changes_out.txt
    if change_path.name == "changes.txt" and change_out_path.name == "changes_out.txt":
        try:
            change_path.unlink(missing_ok=True)
            change_out_path.unlink(missing_ok=True)
            print(_style("已自动的 changes.txt 和 changes_out.txt", ANSI_DIM, ANSI_GRAY))
        except Exception as e:
            print(_style(f"⚠️ 自动删除失败: {e}", ANSI_RED))

    if failed_pairs:
        print()
        print(_style("以下句子未能自动替换，请手动处理：", ANSI_YELLOW))
        print(_style("（一行原句，一行 AI 修改建议）", ANSI_DIM, ANSI_GRAY))
        print()
        for change_line, out_line in failed_pairs:
            print(change_line)
            print(out_line)
    wait_for_key()


def get_multiline_input() -> str:
    try:
        import msvcrt
    except ImportError:
        print("当前环境不支持特定按键输入 (msvcrt missing)")
        return input("由于环境限制，请使用单行输入: ")

    print(_style(_hr(), ANSI_GRAY))
    print("多行输入模式")
    print("说明: Enter 换行 | Ctrl+S 保存并退出 | Esc 取消")
    print(_style(_hr(), ANSI_GRAY))

    buffer = []
    sys.stdout.write("> ")
    sys.stdout.flush()

    while True:
        ch = msvcrt.getwch()

        # Ctrl+S is \x13
        if ch == '\x13':
            print("\n[已保存]")
            return "".join(buffer)

        # Esc is \x1b
        elif ch == '\x1b':
            print("\n[已取消]")
            return ""

        # Enter is \r
        elif ch == '\r':
            sys.stdout.write('\n')
            buffer.append('\n')

        # Backspace is \x08
        elif ch == '\x08':
            if buffer:
                # 简单的退格处理，不支持跨行回退
                if buffer[-1] != '\n':
                    sys.stdout.write('\b \b')
                buffer.pop()

        # Ctrl+C is \x03
        elif ch == '\x03':
            print("\n[已取消]")
            return ""

        else:
            sys.stdout.write(ch)
            buffer.append(ch)

        sys.stdout.flush()


def mode_config() -> None:
    global POSTS_DIR
    while True:
        config = load_config()
        if not config:
            _render_header("配置选项")
            print("无法加载配置文件 config.json")
            wait_for_key()
            return

        keys = list(config.keys())
        display_options = []
        for k in keys:
            val = str(config[k]).replace("\n", "\\n")
            if len(val) > 40:
                val = val[:37] + "..."
            display_options.append(f"{k}: {val}")

        display_options.append("返回上级菜单")

        choice = menu(
            "配置选项",
            display_options,
            footer="上下键切换，回车选择修改，Q 键返回",
        )

        if choice is None or choice == len(keys):
            break

        key = keys[choice]
        current_val = config[key]

        clear_screen()
        _render_header(f"修改配置: {key}")
        print(f"当前值: {current_val}")
        print("请输入新值 (直接回车保持不变):")

        if key == "SYSTEM_PROMPT":
            new_val = get_multiline_input()
        else:
            print(_style("提示: 仅支持单行输入", ANSI_DIM, ANSI_GRAY))
            try:
                new_val = input("> ").strip()
            except EOFError:
                new_val = ""

        if new_val:
            # 简单的类型保留
            if isinstance(current_val, int):
                try:
                    new_val = int(new_val)
                except ValueError:
                    print("错误: 必须输入整数")
                    wait_for_key()
                    continue

            config[key] = new_val
            save_config(config)
            print("配置已保存")

            # 如果更改了 POSTS_DIR，更新全局变量
            if key == "POSTS_DIR":
                # 重新加载逻辑
                POSTS_DIR = get_posts_dir()

            wait_for_key()


def mode_git_commit() -> None:
    rc = run_script([
        str(BASE_DIR / "git_commit.py"),
    ])
    if rc != 0:
        print("Git 提交失败")
        wait_for_key()


def main() -> int:
    if not POSTS_DIR.exists():
        clear_screen()
        _render_header("AI Markdown Checker")
        print("文章目录没有找到")
        print(f"预期：{POSTS_DIR}")
        wait_for_key("按任意键退出...")
        return 1

    ensure_output_dir()

    while True:
        choice = menu(
            "AI Markdown Checker",
            [
                "模式 1：校对修改的 Markdown 文件（需要 Git）",
                "模式 2：校对特定的 Markdown 文件",
                "模式 3：用户审查修改",
                "Git：提交至暂存区",
                "配置选项",
                "退出",
            ],
            footer="↑↓ 选择 | Enter 确认 | Q 退出 | C 清除缓存",
            allow_clear=True,
        )
        if choice is None or choice == 5:
            break
        if choice == -2:
            removed = clear_output_cache(BASE_DIR)
            print(f"已清除 output 缓存，共移除 {removed} 项。")
            wait_for_key()
            continue
        if choice == 0:
            mode_changed_files()
        elif choice == 1:
            mode_single_file()
        elif choice == 2:
            mode_review_changes()
        elif choice == 3:
            mode_git_commit()
        elif choice == 4:
            mode_config()

    return 0


if __name__ == "__main__":
    sys.exit(main())
