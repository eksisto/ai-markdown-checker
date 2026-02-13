#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
一个优雅的、逐行处理文本文件的自动化 AI 脚本。

功能:
- 逐行读取指定的输入文本文件。
- 将每一行内容发送给 Ollama API 进行处理。
- 将 API 返回的结果逐行写入指定的输出文本文件。
- 提供用户友好的进度条显示。
- 通过命令行参数指定输入和输出文件，方便使用。
- API 配置通过配置文件设置，无需设置环境变量。
- 支持流式输出（streaming），更快的响应速度和更好的用户体验。
"""

import sys
import os
import time
import json
import ollama
from tqdm import tqdm
from pydantic import BaseModel

# --- 1. 配置区域 ---

CONFIG_FILENAME = "config.json"


class CheckResult(BaseModel):
    """文本检查结果的数据模型"""
    original_text: str
    error_type: str
    description: str
    checked_text: str


REQUIRED_CONFIG_KEYS = [
    "SYSTEM_PROMPT",
    "OLLAMA_MODEL",
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
    """根据配置检查并初始化 Ollama 客户端，同时验证连接性。"""
    try:
        # 配置 Ollama 客户端
        client_kwargs = {}
        if config.get("OLLAMA_HOST"):
            client_kwargs['host'] = config["OLLAMA_HOST"]

        client = ollama.Client(**client_kwargs)

        # 通过列出模型来验证连接
        models = client.list()
        return client
    except Exception as e:
        print(f"❌ 错误：无法连接到 Ollama 服务器。请确保 Ollama 服务正在运行。")
        if config.get("OLLAMA_HOST"):
            print(f"🔍 尝试连接的地址: {config['OLLAMA_HOST']}")
        print(f"🔍 详细错误: {e}")
        sys.exit(1)

# --- 3. 核心处理函数 ---


def get_ai_response(client: ollama.Client, content: str, config: dict) -> str:
    """
    向 Ollama API 发送单次请求并获取结果（使用流式输出）。

    Args:
        client: 已初始化的 Ollama 客户端实例。
        content: 要发送给 AI 处理的单行文本。

    Returns:
        AI 返回的处理结果字符串（JSON格式）。如果发生 API 错误，则返回错误信息。
    """
    if not content:
        return ""  # 如果行为空，则直接返回空字符串

    try:
        # 构建系统提示词
        system_prompt = (
            f"{config['SYSTEM_PROMPT']}\n\n"
            "如果没有错误，error_type和description填写空字符串，checked_text与original_text保持一致。"
        )

        json_examples = (
            "以下是一些示例输出：\n"
            '{"original_text":"小明紧紧的抱住了妈妈。","error_type":"错别字","description":"“的/地”混淆，状语用“地”。","checked_text":"小明紧紧地抱住了妈妈。"}\n'
            '{"original_text":"我跑的很快。","error_type":"错别字","description":"“的/得”混淆，补语用“得”。","checked_text":"我跑得很快。"}\n'
            '{"original_text":"他己经完成了今天的任务。","error_type":"错别字","description":"“己/已”混淆。","checked_text":"他已经完成了今天的任务。"}\n'
            '{"original_text":"他滥用手中的权利，为自己谋取私利。","error_type":"错别字","description":"“权力/权利”混淆。","checked_text":"他滥用手中的权力，为自己谋取私利。"}\n'
            '{"original_text":"会议上，他一个大胆的建议。","error_type":"增删字","description":"缺少谓语“提出”。","checked_text":"会议上，他提出了一个大胆的建议。"}\n'
            '{"original_text":"我们必须全面提升各项服务指标和水平。","error_type":"修辞错误","description":"“指标”和“水平”语义重复，用词冗余。","checked_text":"我们必须全面提升各项服务水平。"}\n'
            '{"original_text":"这是一件可歌可泣的小事。","error_type":"用词不当","description":"“可歌可泣”褒贬不当，与“小事”不符。","checked_text":"这是一件令人感动的小事。"}\n'
            '{"original_text":"他昨天买了一本新书在书店里。","error_type":"语序不当","description":"地点状语“在书店里”应置于动词“买”前。","checked_text":"他昨天在书店里买了一本新书。"}\n'
            '{"original_text":"通过这次讨论，加强了对环保的认识。","error_type":"成分残缺","description":"缺少主语。","checked_text":"通过这次讨论，大家加强了对环保的认识。"}\n'
            '{"original_text":"我们要牢牢把握住这次机会，积极争取。","error_type":"搭配不当","description":"“把握住”与“争取”搭配不当。","checked_text":"我们要牢牢把握住这次机会，积极争取成功。"}\n'
            '{"original_text":"能否按期完成任务，关键在于质量。","error_type":"逻辑错误","description":"“能否”是两面性，后句不能只说一面。","checked_text":"能否按期完成任务，关键在于能否保证质量。"}\n'
            '{"original_text":"傍晚时分，公园里传来阵阵欢声笑语。","error_type":"","description":"","checked_text":"傍晚时分，公园里传来阵阵欢声笑语。"}'
        )

        # 构建 options 参数
        options = {}
        if "temperature" in config:
            options["temperature"] = config["temperature"]
        if "top_p" in config:
            options["top_p"] = config["top_p"]

        # 使用流式输出以获得更快的响应体验
        stream = client.chat(
            model=config["OLLAMA_MODEL"],
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "system", "content": json_examples},
                {"role": "user", "content": content}
            ],
            format=CheckResult.model_json_schema(),  # 使用 Pydantic 模型的 JSON schema
            options=options,
            stream=True,  # 启用流式输出
            think=False,  # 关闭 Ollama 思考
        )

        # 收集流式响应
        ai_result = ""
        for chunk in stream:
            if chunk.get('message', {}).get('content'):
                ai_result += chunk['message']['content']
        ai_result = ai_result.strip()

        # 使用 Pydantic 模型验证 JSON 结果
        try:
            result = CheckResult.model_validate_json(ai_result)
            # 将验证后的结果转换回 JSON 字符串（压缩格式）
            return result.model_dump_json(exclude_none=True)
        except Exception as e:
            log_line(f"\n⚠️ 警告: 无法验证 JSON 格式，将返回原始结果: {str(e)[:100]}")
            return ai_result
    except Exception as e:
        error_message = f"API_ERROR: {str(e)}"
        # 使用 \n 确保错误信息在终端中换行显示，不影响 tqdm 进度条
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
    print("✅ Ollama 客户端初始化及连接性验证成功！")
    print(f"🤖 模型: {config['OLLAMA_MODEL']}")
    print(f"⚡ 提示词: \"{config['SYSTEM_PROMPT']}\"")
    if config.get("OLLAMA_HOST"):
        print(f"🦙 Ollama 地址: {config['OLLAMA_HOST']}")
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

                # 解析 JSON 结果，判断是否有错误
                try:
                    result_json = json.loads(ai_result)
                    # 如果 error_type 为空或没有错误，则跳过不写入
                    if not result_json.get("error_type") or result_json.get("error_type").strip() == "":
                        time.sleep(config["REQUEST_DELAY_SECONDS"])
                        continue
                except json.JSONDecodeError:
                    # 如果无法解析 JSON，仍然写入原始结果
                    log_line(f"\n⚠️ 无法解析 JSON 结果，写入原始内容: {ai_result[:50]}")

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
