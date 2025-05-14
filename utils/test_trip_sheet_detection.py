"""test_trip_sheet_detection.py
===============================
该脚本位于 utils/ 目录，用于快速测试行程单检测是否生效。

执行方式：
    python utils/test_trip_sheet_detection.py

它会遍历 config.INPUT_DIR 中的所有 PDF，调用 extraction.extract_with_pdfplumber，
然后输出每个文件的 `is_trip_sheet` 标记结果，方便开发调试。🚕
"""

import os
import sys
from pathlib import Path

# 确保可以从工作区根运行脚本
ROOT_DIR = Path(__file__).resolve().parent.parent
SRC_DIR = ROOT_DIR / "src"
sys.path.insert(0, str(SRC_DIR))

from config import INPUT_DIR  # type: ignore
from extraction import extract_with_pdfplumber  # type: ignore


def main() -> None:
    pdf_files = [f for f in os.listdir(INPUT_DIR) if f.lower().endswith(".pdf")]
    if not pdf_files:
        print("📂 input/ 目录为空，无 PDF 可测试。")
        return

    for pdf_name in pdf_files:
        pdf_path = Path(INPUT_DIR) / pdf_name
        info = extract_with_pdfplumber(str(pdf_path))
        flag = "✅ 行程单" if info.get("is_trip_sheet") else "❌ 普通发票"
        print(f"{pdf_name}: {flag}")


if __name__ == "__main__":
    main() 