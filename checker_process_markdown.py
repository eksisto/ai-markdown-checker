#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
一个智能处理 Markdown 文件的脚本。

功能:
- 自动忽略 YAML Front Matter。
- 使用AST（抽象语法树）解析 Markdown，精准识别并忽略代码块、表格等非段落内容。
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
    - 针对没有标点结尾的独立文本块（如未加句号的列表项），也会将其作为独立句子保留。

    Args:
        text_blocks (list[str]): 待处理的文本块列表。

    Returns:
        list[str]: 清理和分割后的句子列表。
    """
    print("正在进行句子分割...")

    # 优化的中英文通用的正则表达式：
    # 匹配以下几种句尾模式 (包含中英文标点及嵌套引号/括号)：
    # 1. 单独的句尾标点：。！？.!?
    # 2. 句尾标点 + 后括号/引号：如 。” | ！」 | ." | ?) | !' 等
    # 3. 后括号/引号 + 句尾标点：如 ”。 | 」！ | ". | )? 等
    # 包含符号： ） ” ’ 」 』 ) ] } " '
    sentence_pattern = re.compile(
        r'([^。！？.!?]+?(?:[。！？.!?][）”’」』"\'\)\]}]+|[）”’」』"\'\)\]}]+[。！？.!?]|[。！？.!?]))'
    )

    cleaned_sentences = []

    for block in text_blocks:
        # 1. 先在整个文本块中过滤掉可能跨行的公式块 $$...$$
        # 使用 re.DOTALL 使得 . 可以匹配换行符，从而正确识别跨行公式
        block = re.sub(r'\$\$.+?\$\$', '', block, flags=re.DOTALL)

        # 2. 将处理后的文本块按换行符分割，即使在同一个段落中，不同行的文本也会被分开处理
        sub_lines = block.split('\n')

        for text in sub_lines:
            text = text.strip()
            if not text:
                continue

            sentences = sentence_pattern.findall(text)

            # 检查是否有未被正则捕获的残留文本（如结尾没有标点的情况）
            # 计算已捕获句子的总长度
            captured_len = sum(len(s) for s in sentences)

            if captured_len < len(text):
                remainder = text[captured_len:].strip()
                if remainder:
                    # 将残留部分作为一个新句子
                    sentences.append(remainder)

            # 清理每个句子，去除多余空白
            for s in sentences:
                s_cleaned = s.strip()
                if not s_cleaned:  # 跳过空句子
                    continue
                # 将多个连续空格压缩为单个空格
                s_cleaned = re.sub(r'\s+', ' ', s_cleaned)
                cleaned_sentences.append(s_cleaned)

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
