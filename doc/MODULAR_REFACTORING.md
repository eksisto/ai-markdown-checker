# 模块化重构说明

## 概述

本项目已完成模块化重构，将 GUI 和 CLI 共同的功能提取到独立模块中，便于代码复用和维护。

## 模块结构

### 核心模块

#### 1. `config_manager.py` - 配置管理模块

负责配置文件的加载、保存和验证

**主要函数：**

- `load_config()` - 加载配置文件
- `save_config(config)` - 保存配置到文件
- `get_posts_dir(config=None)` - 获取文章目录路径
- `validate_config(config)` - 验证配置完整性
- `get_config_value(key, default=None)` - 获取单个配置项
- `set_config_value(key, value)` - 设置单个配置项

#### 2. `progress_manager.py` - 进度管理模块

负责审查进度的保存和加载

**主要函数：**

- `load_review_progress()` - 加载审查进度
- `save_review_progress(change_path, change_out_file, next_index)` - 保存审查进度
- `clear_review_progress()` - 清除审查进度文件
- `has_review_progress()` - 检查是否存在审查进度

#### 3. `file_manager.py` - 文件管理模块

负责文件和目录的管理操作

**主要函数：**

- `ensure_output_dir()` - 确保 output 目录存在
- `list_output_files(pattern="*.txt")` - 列出 output 目录中的文件
- `list_markdown_files(posts_dir)` - 列出文章目录中的所有 Markdown 文件
- `make_output_stem(path)` - 为输出文件生成文件名
- `resolve_md_path(filename, posts_dir, cache)` - 解析 Markdown 文件路径（基础版）
- `replace_sentence_in_file(path, old_sentence, new_sentence)` - 在文件中替换句子
- `check_sentence_in_file(path, sentence)` - 检查句子是否存在于文件中

#### 4. `data_parser.py` - 数据解析模块

负责解析 AI 输出和标签数据

**主要函数：**

- `split_label(line)` - 从行中分离标签和内容
- `parse_label(label)` - 解析标签获取文件名
- `parse_ai_json(text)` - 解析 AI 输出的 JSON 格式
- `load_change_out(path)` - 加载 AI 处理结果文件
- `load_filtered_change_lines(path, labels)` - 加载过滤后的 change 文件行

### 主程序

#### `checker.py` - CLI 版本

命令行界面版本，包含 CLI 特有的交互功能：

- `resolve_md_path_cli()` - CLI 特有的路径解析（包含命令行交互）
- 其他 CLI 特有的 UI 函数（菜单、终端样式等）

#### `gui.py` - GUI 版本

图形界面版本，包含 GUI 特有的功能：

- `_resolve_md_path()` - GUI 特有的路径解析（使用对话框）
- 其他 GUI 特有的组件（主题管理、Qt Widget 等）

### 辅助脚本

- `checker_add.py` - Git 差异提取
- `checker_ai.py` - AI 处理
- `checker_process_markdown.py` - Markdown 文件处理
- `clear_output_cache.py` - 缓存清理
- `git_commit.py` - Git 提交操作

## 使用方式

### 从模块导入

在其他脚本中导入模块：

```python
# 配置管理
from config_manager import load_config, save_config, get_posts_dir

# 进度管理
from progress_manager import load_review_progress, save_review_progress

# 文件管理
from file_manager import ensure_output_dir, list_markdown_files

# 数据解析
from data_parser import parse_ai_json, load_change_out
```

### CLI 和 GUI 共享逻辑

CLI 和 GUI 现在都使用相同的核心模块，只在用户交互部分有所不同：

- **共享**：配置管理、文件操作、数据解析、进度管理
- **CLI 特有**：命令行菜单、msvcrt 键盘输入、ANSI 终端样式
- **GUI 特有**：Qt 对话框、主题管理、Widget 组件

## 优点

1. **代码复用**：避免重复代码，减少维护成本
2. **模块化**：功能划分清晰，易于理解和修改
3. **可测试性**：独立模块便于单元测试
4. **可扩展性**：容易添加新功能或新的用户界面
5. **统一性**：CLI 和 GUI 使用相同的核心逻辑，保证行为一致

## 后续维护建议

1. **添加新功能**：优先考虑是否可以放入现有模块中
2. **修复 Bug**：如果是核心逻辑问题，修改模块文件即可同时修复 CLI 和 GUI
3. **扩展模块**：如果某个模块功能过多，可以考虑进一步拆分
4. **单元测试**：为每个模块编写测试用例，确保功能正确性

## 示例：添加新功能

假设要添加一个新的配置项处理功能：

1. 在 `config_manager.py` 中添加新函数
2. 在 `checker.py` 和 `gui.py` 中导入并使用该函数
3. 根据需要在 CLI 和 GUI 中添加各自的用户界面

```python
# config_manager.py
def get_advanced_config(key: str) -> Any:
    """新的配置处理函数"""
    config = load_config()
    # ... 处理逻辑
    return result

# checker.py (CLI)
from config_manager import get_advanced_config
# 在 CLI 菜单中使用

# gui.py (GUI)
from config_manager import get_advanced_config
# 在 GUI 界面中使用
```

## 兼容性说明

- 模块化后的代码与原有代码功能完全兼容
- 配置文件格式未改变
- 输出文件格式未改变
- 进度文件格式未改变
