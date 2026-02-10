#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
一个优雅的、逐行处理文本文件的自动化 AI 脚本。

功能:
- 逐行读取指定的输入文本文件。
- 将每一行内容发送给 OpenAI API 进行处理。
- 将 API 返回的结果逐行写入指定的输出文本文件。
- 提供用户友好的进度条显示。
- 通过命令行参数指定输入和输出文件，方便使用。
- API 密钥和 API URL 通过配置文件配置，无需设置环境变量。
"""

import sys
import os
import time
import json
from openai import OpenAI, APIConnectionError, AuthenticationError
from tqdm import tqdm

# --- 1. 配置区域 ---

CONFIG_FILENAME = "config.json"

REQUIRED_CONFIG_KEYS = [
    "OPENAI_API_KEY",
    "USER_PROMPT",
    "GPT_MODEL",
    "REQUEST_DELAY_SECONDS",
]


def load_config() -> dict:
    """从外部配置文件读取配置，找不到时退出并提示。"""
    config_path = os.path.join(os.path.dirname(__file__), CONFIG_FILENAME)
    if not os.path.exists(config_path):
        print(f"❌ 错误：未找到配置文件 '{config_path}'。")
        print("🔍 请复制同目录示例配置并填写相关参数。")
        sys.exit(1)

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
    except json.JSONDecodeError as e:
        print(f"❌ 错误：配置文件不是有效的 JSON。")
        print(f"🔍 详细错误: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"❌ 错误：读取配置文件失败。")
        print(f"🔍 详细错误: {e}")
        sys.exit(1)

    missing_keys = [key for key in REQUIRED_CONFIG_KEYS if key not in config]
    if missing_keys:
        missing = ", ".join(missing_keys)
        print("❌ 错误：配置文件缺少必要字段。")
        print(f"🔍 缺少字段: {missing}")
        sys.exit(1)

    return config

# --- 2. 初始化与检查 ---


def initialize_client(config: dict):
    """根据配置检查并初始化 OpenAI 客户端，同时验证 API 连接性。"""
    if not config.get("OPENAI_API_KEY"):
        print("❌ 错误：请在配置文件中设置您的 `OPENAI_API_KEY`。")
        sys.exit(1)

    try:
        client = OpenAI(
            api_key=config["OPENAI_API_KEY"],
            base_url=config.get("OPENAI_API_BASE_URL")  # 如果为 None，库会自动使用默认值
        )
        # 通过一个轻量级请求来验证 API 密钥和网络连接是否正常
        client.models.list()
        return client
    except AuthenticationError:
        print("❌ 错误：API 密钥无效或已过期。请检查您的 `OPENAI_API_KEY`。")
        sys.exit(1)
    except APIConnectionError as e:
        print(f"❌ 错误：无法连接到 API 服务器。请检查您的网络连接或 `OPENAI_API_BASE_URL` 设置。")
        print(f"🔍 详细信息: {e.__cause__}")
        sys.exit(1)
    except Exception as e:
        print(f"❌ 错误：初始化 OpenAI 客户端时发生未知错误。")
        print(f"🔍 详细错误: {e}")
        sys.exit(1)

# --- 3. 核心处理函数 ---


def get_ai_response(client: OpenAI, content: str, config: dict) -> str:
    """
    向 OpenAI API 发送单次请求并获取结果。

    Args:
        client: 已初始化的 OpenAI 客户端实例。
        content: 要发送给 AI 处理的单行文本。

    Returns:
        AI 返回的处理结果字符串。如果发生 API 错误，则返回错误信息。
    """
    if not content:
        return ""  # 如果行为空，则直接返回空字符串

    try:
        response = client.chat.completions.create(
            model=config["GPT_MODEL"],
            messages=[
                {"role": "system", "content": config["USER_PROMPT"]},
                {"role": "user", "content": content}
            ],
            temperature=0.5,
            max_tokens=1500,
        )
        ai_result = response.choices[0].message.content.strip()
        return ai_result
    except Exception as e:
        error_message = f"API_ERROR: {str(e)}"
        # 使用 \n 确保错误信息在终端中换行显示，不影响tqdm进度条
        print(f"\n处理行 '{content[:30]}...' 时发生错误: {error_message}")
        return error_message


def split_label(line: str) -> tuple[str, str]:
    """从行中拆分 @@S000001|filename.md@@ 标签"""
    if line.startswith("@@S"):
        end = line.find("@@ ")
        if end != -1:
            label = line[: end + 3]
            return label, line[end + 3:]
    return "", line


def log_line(message: str) -> None:
    """在不破坏进度条的情况下编写日志行"""
    tqdm.write(message)


class PauseController:
    """通过非阻塞键检查处理暂停/恢复/停止输入"""

    def __init__(self) -> None:
        try:
            import msvcrt  # type: ignore
        except ImportError:
            self._msvcrt = None
        else:
            self._msvcrt = msvcrt

        self.paused = False
        self.stop = False

    def poll(self) -> None:
        if not self._msvcrt:
            return
        while self._msvcrt.kbhit():
            ch = self._msvcrt.getch()
            if ch in (b"p", b"P"):
                self.paused = not self.paused
                state = "已暂停" if self.paused else "已继续"
                log_line(f"{state}（P 键暂停，Q 键终止）")
            elif ch in (b"q", b"Q"):
                self.stop = True
                log_line("收到终止指令，准备安全退出...")

    def wait_if_paused(self) -> None:
        while self.paused and not self.stop:
            time.sleep(0.2)
            self.poll()

# --- 4. 主执行逻辑 ---


def main():
    """脚本主入口函数。"""
    if len(sys.argv) != 3:
        print("❌ 错误：参数数量不正确。")
        print("📚 用法: python ai_process.py <输入文件路径> <输出文件路径>")
        sys.exit(1)

    input_filepath, output_filepath = sys.argv[1], sys.argv[2]

    if not os.path.exists(input_filepath):
        print(f"❌ 错误：输入文件 '{input_filepath}' 不存在。")
        sys.exit(1)

    # 读取配置并初始化客户端
    config = load_config()
    client = initialize_client(config)
    print("✅ OpenAI 客户端初始化及连接性验证成功！")
    print(f"🤖 模型: {config['GPT_MODEL']}")
    print(f"⚡ 提示词: \"{config['USER_PROMPT']}\"")
    if config.get("OPENAI_API_BASE_URL"):
        print(f"  API地址: {config['OPENAI_API_BASE_URL']}")
    print("-" * 50)

    try:
        with open(input_filepath, 'r', encoding='utf-8') as f_in:
            lines_to_process = f_in.readlines()
    except Exception as e:
        print(f"❌ 错误：读取输入文件 '{input_filepath}' 失败。")
        print(f"🔎 详细错误: {e}")
        sys.exit(1)

    print(f"准备处理文件 '{input_filepath}' 中的 {len(lines_to_process)} 行内容...")

    pause_controller = PauseController()
    log_line("提示：按 P 键可暂停/继续，按 Q 键可终止处理。")

    try:
        with open(output_filepath, 'w', encoding='utf-8') as f_out:
            for line in tqdm(lines_to_process, desc="AI 处理进度", unit=" 行", ncols=100):
                pause_controller.poll()
                if pause_controller.stop:
                    break

                pause_controller.wait_if_paused()
                if pause_controller.stop:
                    break

                content_to_process = line.strip()
                label, content_to_process = split_label(content_to_process)

                ai_result = get_ai_response(client, content_to_process, config)

                if ai_result in ("没有问题", "没有问题。"):
                    time.sleep(config["REQUEST_DELAY_SECONDS"])
                    continue

                f_out.write(f"{label}{ai_result}\n")
                f_out.flush()  # 实时将结果写入磁盘，防止程序意外中断时丢失数据

                time.sleep(config["REQUEST_DELAY_SECONDS"])
    except Exception as e:
        print(f"\n❌ 错误：在写入输出文件 '{output_filepath}' 时发生严重错误，处理已中断。")
        print(f"🔎 详细错误: {e}")
        sys.exit(1)

    print("-" * 50)
    if pause_controller.stop:
        print("⚠️ 已根据用户指令终止处理。")
    else:
        print("🎉 处理完成！")
    print(f"所有结果已成功保存至: '{output_filepath}'")


if __name__ == "__main__":
    main()
