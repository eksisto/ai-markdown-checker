#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
一个智能处理 Markdown 文件的脚本。

功能:
- 自动忽略 YAML Front Matter。
- 使用 AST（抽象语法树）解析 Markdown，精准识别并忽略代码块、表格等非段落内容。
-只提取段落、列表、引用中的文本。
- 将提取的内容按句子（以'。'、'！'、'？'结尾，包括与括号的组合）分割。
- 将结果以每句一行的形式输出到文本文件。
"""

import argparse
import os
import re
import sys

try:
    from markdown_it import MarkdownIt
except ImportError as exc:
    print("❌ 错误: 无法导入模块 'markdown_it'。", file=sys.stderr)
    print(f"   详情: {exc}", file=sys.stderr)
    print("   请使用当前解释器安装:", file=sys.stderr)
    print(f"   {sys.executable} -m pip install markdown-it-py", file=sys.stderr)
    sys.exit(1)


def extract_text_from_markdown(file_path: str) -> list[str]:
    """
    读取Markdown文件，智能提取其中的纯文本内容。

    处理流程:
    1. 读取文件并移除 Front Matter。
    2. 使用 markdown-it-py 将 Markdown 解析为 token 流。
     3. 遍历 token，只提取段落和列表项中的文本内容。
         这样可以自然地忽略代码块、表格、标题等。

    Args:
        file_path (str): Markdown 文件的路径。

    Returns:
        list[str]: 提取出的文本块列表（每段/项为一个元素）。
    """
    print(f"📄 正在读取和解析输入文件: {file_path}")
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except FileNotFoundError:
        print(f"❌ 错误: 输入文件未找到 -> {file_path}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"❌ 错误: 读取文件时发生未知错误 -> {e}", file=sys.stderr)
        sys.exit(1)

    # 1. 移除 Front Matter
    parts = content.split('---', 2)
    if len(parts) == 3 and parts[0].strip() == '':
        print("  - 检测到 Front Matter，已自动忽略。")
        markdown_body = parts[2]
    else:
        print("  - 未检测到 Front Matter，将处理整个文件。")
        markdown_body = content

    # 2. 保护转义字符，避免被 markdown-it-py 移除
    # 使用 \uE000 作为占位符，匹配反斜杠后跟着 ASCII 标点符号的情况
    # 这样 markdown-it 看到的是 "\uE000" + "\X"，它会将 \X 处理为转义字符（只保留 X），
    # 最终我们得到 "\uE000" + "X"，再将其替换回 "\X"
    markdown_body = re.sub(
        r'\\([!"#$%&\'()*+,-./:;<=>?@\[\\\]^_`{|}~])', '\uE000' + r'\\\1', markdown_body)

    # 3. 使用 markdown-it-py 解析
    print("  - 正在使用 AST 解析 Markdown 结构...")
    # 启用表格支持，以便正确识别和过滤表格内容
    md = MarkdownIt().enable('table')
    tokens = md.parse(markdown_body)

    # 4. 提取目标文本
    text_blocks = []
    # 只关心段落与列表项内的文本
    # 'inline' token 包含了该块的实际文本内容

    stack = []

    def _extract_inline_text(inline_token):
        # Rebuild text from inline children, preserving markdown inline styles.
        if not inline_token.children:
            return inline_token.content.replace('\uE000', '\\')
        parts = []
        link_stack = []  # 用于处理链接 [text](url)

        for child in inline_token.children:
            if child.type == "image":
                if link_stack:
                    link_stack[-1]["has_image"] = True
                continue
            elif child.type == "text":
                parts.append(child.content)
            elif child.type == "html_inline":
                parts.append(child.content)
            elif child.type == "code_inline":
                # 保留行内代码的反引号
                parts.append(f"`{child.content}`")
            elif child.type == "strong_open":
                parts.append(child.markup)
            elif child.type == "strong_close":
                parts.append(child.markup)
            elif child.type == "em_open":
                parts.append(child.markup)
            elif child.type == "em_close":
                parts.append(child.markup)
            elif child.type == "link_open":
                # 记录链接开始在 parts 列表中的索引
                href = child.attrGet("href") or ""
                link_stack.append({
                    "parts_index": len(parts),
                    "href": href,
                    "has_image": False
                })
                parts.append("[")
            elif child.type == "link_close":
                if link_stack:
                    link_info = link_stack.pop()
                    if link_info.get("has_image"):
                        # 发现图片，撤销从 [ 开始的所有添加
                        parts = parts[:link_info["parts_index"]]
                    else:
                        parts.append("]")
                        parts.append(f"({link_info['href']})")
                else:
                    parts.append("]")
            elif child.type in ("softbreak", "hardbreak"):
                parts.append("\n")
        return "".join(parts).replace('\uE000', '\\')

    for token in tokens:
        if token.nesting == 1:
            stack.append(token.type)
            continue
        if token.nesting == -1:
            if stack:
                stack.pop()
            continue

        if token.type != "inline":
            continue

        inline_text = _extract_inline_text(token).strip()
        if not inline_text:
            continue

        in_paragraph = "paragraph_open" in stack
        in_list_item = "list_item_open" in stack
        in_heading = "heading_open" in stack
        # 检查所有表格相关的 token，确保完全过滤表格内容
        table_tokens = {"table_open", "thead_open",
                        "tbody_open", "tr_open", "th_open", "td_open"}
        in_table = any(t in table_tokens for t in stack)
        in_blockquote = "blockquote_open" in stack

        # 包含块引用内容
        if (in_paragraph or in_list_item or in_blockquote) and not in_heading and not in_table:
            text_blocks.append(inline_text)

    print(f"  - 成功从 {len(text_blocks)} 个段落/列表项/引用中提取文本。")
    return text_blocks


def split_into_sentences(text_blocks: list[str]) -> list[str]:
    """
    将文本块列表中的内容分割成句子，并进行清理。

    特别处理：
    - 兼容中英文分句规则。
    - 当句号、问号、感叹号与右（后）括号或引号（如 ”、’、"、'、）等）组合出现时，以最后一个符号作为断句点。
    - 考虑 Markdown 内联样式（加粗、斜体、删除线等），如果样式包裹多个句子，保持样式完整性，以长的为最终划分句标准。
    - 针对没有标点结尾的独立文本块（如未加句号的列表项），也会将其作为独立句子保留。

    Args:
        text_blocks (list[str]): 待处理的文本块列表。

    Returns:
        list[str]: 清理和分割后的句子列表。
    """
    print("正在进行句子分割...")

    # 句末标点的正则表达式
    sentence_end_pattern = re.compile(
        r'(?:[。！？.!?]+[）”’」』"\'\)\]\}]+|[）”’」』"\'\)\]\}]+[。！？.!?]+|[。！？.!?]+)'
    )

    def find_inline_style_ranges(text: str) -> list[tuple[int, int, str]]:
        """
        查找文本中所有 Markdown 内联样式的区间。

        Returns:
            list[tuple[int, int, str]]: (start_pos, end_pos, marker) 列表
        """
        ranges = []

        # Markdown 内联样式标记，按长度从长到短排序，避免匹配冲突
        # 格式: (marker, is_symmetric)
        markers = [
            ('***', True),   # 加粗斜体
            ('**', True),    # 加粗
            ('~~', True),    # 删除线
            ('*', True),     # 斜体
            ('_', True),     # 斜体（下划线）
        ]

        for marker, is_symmetric in markers:
            marker_len = len(marker)
            pos = 0

            while pos < len(text):
                # 查找开始标记
                start = text.find(marker, pos)
                if start == -1:
                    break

                # 查找结束标记
                end_search_start = start + marker_len
                end = text.find(marker, end_search_start)

                if end == -1:
                    # 没有找到结束标记，跳过此开始标记
                    pos = start + 1
                    continue

                # 记录区间 [start, end + marker_len)
                ranges.append((start, end + marker_len, marker))
                pos = end + marker_len

        # 按开始位置排序
        ranges.sort(key=lambda x: x[0])
        return ranges

    def is_inside_style(pos: int, style_ranges: list[tuple[int, int, str]]) -> tuple[bool, int]:
        """
        检查位置 pos 是否在某个样式区间内。

        Returns:
            (is_inside, style_end): 如果在样式内，返回(True, 样式结束位置)，否则(False, pos)
        """
        for start, end, marker in style_ranges:
            if start < pos < end:
                return True, end
        return False, pos

    def find_sentence_boundary(text: str, start_pos: int, style_ranges: list[tuple[int, int, str]]) -> int:
        """
        从 start_pos 开始查找下一个句子的结束位置。
        考虑句末标点和 Markdown 内联样式，以较长的边界为准。

        Returns:
            句子结束位置的索引（不包含该位置）。
        """
        search_text = text[start_pos:]
        match = sentence_end_pattern.search(search_text)

        if not match:
            # 没有找到句末标点，返回文本结束位置
            return len(text)

        # 句末标点的绝对结束位置
        punctuation_end = start_pos + match.end()

        # 检查标点位置是否在某个内联样式中
        is_inside, style_end = is_inside_style(
            punctuation_end - 1, style_ranges)

        if is_inside:
            # 在样式内，使用样式结束位置
            return style_end
        else:
            # 不在样式内，使用标点位置
            return punctuation_end

    cleaned_sentences = []

    for block in text_blocks:
        # 1. 先在整个文本块中过滤掉可能跨行的公式块 $$...$$
        block = re.sub(r'\$\$.+?\$\$', '', block, flags=re.DOTALL)

        # 2. 将处理后的文本块按换行符分割
        sub_lines = block.split('\n')

        for text in sub_lines:
            text = text.strip()
            if not text:
                continue

            # 识别所有内联样式区间
            style_ranges = find_inline_style_ranges(text)

            # 使用新的分句逻辑
            pos = 0
            while pos < len(text):
                end_pos = find_sentence_boundary(text, pos, style_ranges)
                sentence = text[pos:end_pos].strip()

                if sentence:
                    # 将多个连续空格压缩为单个空格
                    sentence = re.sub(r'\s+', ' ', sentence)
                    cleaned_sentences.append(sentence)

                if end_pos == pos:
                    # 防止无限循环
                    pos += 1
                else:
                    pos = end_pos

    print(f"  - 成功分割出 {len(cleaned_sentences)} 个句子。")
    return cleaned_sentences


def write_to_txt(sentences: list[str], output_path: str, source_file_path: str):
    """
    将句子列表写入指定的文本文件，每句一行。

        额外说明:
        - 为了便于定位，每句前会添加可过滤的标签，格式为: "@@S000001|filename.md@@ "。
            该标签使用固定前缀和零填充数字，并包含来源文件名，方便定位。

    Args:
        sentences (list[str]): 句子列表。
        output_path (str): 输出文件的路径。
        source_file_path (str): 来源 Markdown 文件路径。
    """
    print(f"正在写入结果到: {output_path}")
    try:
        source_name = os.path.basename(source_file_path)
        with open(output_path, 'w', encoding='utf-8') as f:
            if not sentences:
                f.write("")  # 写入空文件
            else:
                tagged_lines = []
                for idx, sentence in enumerate(sentences, start=1):
                    tag = f"@@S{idx:06d}|{source_name}@@ "
                    tagged_lines.append(tag + sentence)
                f.write('\n'.join(tagged_lines) + '\n')
    except Exception as e:
        print(f"❌ 错误: 写入文件时发生错误 -> {e}", file=sys.stderr)
        sys.exit(1)


def main():
    """
    主函数，编排整个处理流程。
    """
    parser = argparse.ArgumentParser(
        description="智能处理 Markdown文件：忽略代码/表格，提取段落内容并按句分割。",
        epilog="示例: python checker_process_markdown.py my_article.md output.txt"
    )
    parser.add_argument("input_file", help="要处理的 Markdown 文件名及路径。")
    parser.add_argument("output_file", help="导出的 txt 文件名及路径。")

    args = parser.parse_args()

    # 核心处理流程
    extracted_text = extract_text_from_markdown(args.input_file)
    sentences_list = split_into_sentences(extracted_text)
    write_to_txt(sentences_list, args.output_file, args.input_file)

    print("\n🎉全部处理完成！结果已成功保存。")


if __name__ == "__main__":
    main()
