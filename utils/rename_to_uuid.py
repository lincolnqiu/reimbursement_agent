"""
rename_to_uuid.py
=================
该脚本是一个辅助工具，用于批量将 `input/` 目录中的 PDF 文件重命名为 **UUID** 形式，避免因中文或特殊字符导致的路径/编码问题，也方便后续上传或分享。

功能概述：
1. 遍历 `input/` 目录所有后缀为 `.pdf` 的文件。
2. 为每个文件生成 `uuid4().hex` 形式的新文件名，如 `3fa85f64b9e24e1da3c0305bce3da4b7.pdf`。
3. 将旧→新文件名映射写入 `input/rename_mapping.json`，若文件已存在则追加。

更新条件：
- 如果需要支持其他文件类型，请修改 `EXTENSIONS` 列表。
- 若想更改映射文件格式，可调整 `write_mapping` 函数。
"""

import os
import json
import uuid
from pathlib import Path
from typing import Dict, List

# 与 reimbursement_tool 保持一致的目录
INPUT_DIR = "input"
MAPPING_PATH = os.path.join(INPUT_DIR, "rename_mapping.json")
EXTENSIONS = [".pdf"]


def load_mapping() -> Dict[str, str]:
    if os.path.exists(MAPPING_PATH):
        with open(MAPPING_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def write_mapping(mapping: Dict[str, str]):
    with open(MAPPING_PATH, "w", encoding="utf-8") as f:
        json.dump(mapping, f, ensure_ascii=False, indent=2)
    print(f"📄 映射表已更新 -> {MAPPING_PATH}")


def rename_files() -> List[str]:
    os.makedirs(INPUT_DIR, exist_ok=True)
    mapping = load_mapping()
    renamed: List[str] = []

    for file in os.listdir(INPUT_DIR):
        filepath = Path(INPUT_DIR) / file
        if not filepath.is_file():
            continue
        if filepath.suffix.lower() not in EXTENSIONS:
            continue
        if file in mapping:  # 已重命名过
            continue

        new_name = f"{uuid.uuid4().hex}{filepath.suffix}"
        new_path = filepath.with_name(new_name)
        counter = 1
        # 避免极罕见的 UUID 冲突
        while new_path.exists():
            new_name = f"{uuid.uuid4().hex}{filepath.suffix}"
            new_path = filepath.with_name(new_name)
            counter += 1
        filepath.rename(new_path)
        mapping[file] = new_name
        renamed.append(f"{file} -> {new_name}")

    write_mapping(mapping)
    return renamed


def main():
    renamed_list = rename_files()
    if renamed_list:
        print("✅ 已重命名以下文件：")
        for line in renamed_list:
            print("  ", line)
    else:
        print("ℹ️ 没有需要重命名的 PDF，或文件已处理。")


if __name__ == "__main__":
    main() 