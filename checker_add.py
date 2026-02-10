#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Git 差异提取工具
提取工作目录相对于 HEAD 的所有新增和修改的代码行
"""

import os
import sys
import argparse
from pathlib import Path
from datetime import datetime
import subprocess


class GitDiffExtractor:
    """Git 差异提取器"""

    def __init__(self, repo_path):
        self.repo_path = Path(repo_path).resolve()
        self._validate_repo()

    def _validate_repo(self):
        """验证是否为有效的 Git 仓库"""
        if not self.repo_path.exists():
            raise ValueError(f"路径不存在: {self.repo_path}")

        git_dir = self.repo_path / ".git"
        if not git_dir.exists():
            raise ValueError(f"不是有效的 Git 仓库: {self.repo_path}")

    def _run_git_command(self, *args):
        """执行 Git 命令"""
        try:
            result = subprocess.run(
                ["git", "-C", str(self.repo_path)] + list(args),
                capture_output=True,
                encoding='utf-8',
                errors='replace',
                check=True
            )
            return result.stdout if result.stdout else ""
        except subprocess.CalledProcessError as e:
            error_msg = e.stderr if e.stderr else str(e)
            print(f"Git 命令执行失败: {error_msg}", file=sys.stderr)
            return ""
        except FileNotFoundError:
            raise ValueError("未找到 Git 命令，请确保 Git 已安装并在 PATH 中")
        except Exception as e:
            print(f"执行 Git 命令时发生错误: {e}", file=sys.stderr)
            return ""

    def get_tracked_changes(self):
        """获取已跟踪文件的变更"""
        diff_output = self._run_git_command("diff", "HEAD")

        if not diff_output:
            print("提示: 没有检测到已跟踪文件的变更")
            return []

        return self._parse_diff(diff_output)

    def get_untracked_files(self):
        """获取未跟踪的文件内容"""
        untracked_output = self._run_git_command(
            "ls-files", "--others", "--exclude-standard"
        )

        if not untracked_output:
            print("提示: 没有检测到未跟踪的文件")
            return []

        untracked_files = [f.strip()
                           for f in untracked_output.split('\n') if f.strip()]

        changes = []
        for file_path in untracked_files:
            full_path = self.repo_path / file_path
            if full_path.is_file():
                try:
                    content = None
                    for encoding in ['utf-8', 'gbk', 'latin-1']:
                        try:
                            with open(full_path, 'r', encoding=encoding) as f:
                                content = f.readlines()
                                break
                        except UnicodeDecodeError:
                            continue

                    if content is None:
                        with open(full_path, 'rb') as f:
                            content = f.read().decode('utf-8', errors='replace').split('\n')

                    for line_num, line in enumerate(content, 1):
                        changes.append({
                            'file': file_path,
                            'line_num': line_num,
                            'content': line.rstrip('\n\r'),
                            'type': 'new_file'
                        })
                except Exception as e:
                    print(f"⚠️ 警告: 读取文件失败 {file_path}: {e}", file=sys.stderr)

        return changes

    def _parse_diff(self, diff_output):
        """解析 diff 输出，提取新增和修改的行"""
        if not diff_output:
            return []

        changes = []
        current_file = None
        line_num = 0

        lines = diff_output.split('\n')

        for line in lines:
            if line.startswith('diff --git'):
                current_file = None
                line_num = 0
            elif line.startswith('+++'):
                file_path = line[6:].strip()
                if file_path != '/dev/null' and file_path.startswith('b/'):
                    current_file = file_path[2:]
                elif file_path != '/dev/null':
                    current_file = file_path
            elif line.startswith('@@'):
                try:
                    parts = line.split('@@')
                    if len(parts) >= 2:
                        range_info = parts[1].strip().split()
                        for part in range_info:
                            if part.startswith('+'):
                                line_num = int(part.split(',')[0][1:])
                                break
                except Exception as e:
                    print(f"⚠️ 警告: 解析行号失败: {e}", file=sys.stderr)
                    line_num = 0
            elif current_file and line.startswith('+') and not line.startswith('+++'):
                content = line[1:]
                changes.append({
                    'file': current_file,
                    'line_num': line_num,
                    'content': content,
                    'type': 'added'
                })
                line_num += 1
            elif current_file and line and not line.startswith('-') and not line.startswith('\\'):
                if line_num > 0:
                    line_num += 1

        return changes

    def extract_all_changes(self):
        """提取所有变更"""
        print("正在分析 Git 仓库变更...")
        print(f"仓库路径: {self.repo_path}")

        tracked_changes = self.get_tracked_changes()
        print(f"✅ 已跟踪文件变更: {len(tracked_changes)} 行")

        untracked_changes = self.get_untracked_files()
        print(f"✅ 未跟踪文件新增: {len(untracked_changes)} 行")

        all_changes = tracked_changes + untracked_changes
        return all_changes

    def save_to_file(self, changes, output_file, include_metadata=True):
        """保存变更到文件"""
        output_path = Path(output_file)

        try:
            with open(output_path, 'w', encoding='utf-8') as f:
                # 直接写入变更内容，不添加文件头
                for idx, change in enumerate(changes, start=1):
                    if include_metadata:
                        # 统一标签格式，便于后续审查流程解析
                        tag = f"@@S{idx:06d}|{change['file']}@@ "
                        f.write(f"{tag}{change['content']}\n")
                    else:
                        # 只输出代码内容
                        f.write(f"{change['content']}\n")

            print(f"\n✅ 结果已保存到: {output_path.resolve()}")
            print(f"✅ 共提取 {len(changes)} 行变更代码")
        except Exception as e:
            raise ValueError(f"保存文件失败: {e}")


def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description='提取 Git 仓库中工作目录相对于 HEAD 的所有新增和修改的代码行',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  %(prog)s /path/to/repo
  %(prog)s /path/to/repo -o changes.txt
  %(prog)s /path/to/repo --no-metadata
        """
    )

    parser.add_argument(
        'repo_path',
        help='Git 仓库路径'
    )

    parser.add_argument(
        '-o', '--output',
        default='git_changes.txt',
        help='输出文件路径 (默认: git_changes.txt)'
    )

    parser.add_argument(
        '--no-metadata',
        action='store_true',
        help='不包含文件名和行号信息，只输出纯代码内容'
    )

    args = parser.parse_args()

    try:
        extractor = GitDiffExtractor(args.repo_path)
        changes = extractor.extract_all_changes()

        if not changes:
            print("\n⚠️ 没有检测到任何变更！")
            print("提示: 请确保工作目录有未提交的修改或新增文件")
            return 0

        extractor.save_to_file(
            changes,
            args.output,
            include_metadata=not args.no_metadata
        )

        return 0

    except Exception as e:
        print(f"\n❌ 错误: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
