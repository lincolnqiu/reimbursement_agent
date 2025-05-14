"""
reimbursement_tool.py
=====================
该脚本是发票批量处理和报销辅助工具的主入口点。它协调以下操作：
1.  从 `input/` 目录读取 PDF 发票文件。
2.  调用 `extraction` 模块解析每张发票，提取关键信息（发票类型、金额、类别、发票号码），
    该模块会首先尝试 `pdfplumber`，如果结果不完整则使用 LLM OCR 进行兜底。
3.  调用 `file_utils` 模块处理文件：
    - 根据发票号码进行去重，并将重复文件移至 `duplicates/` 目录。
    - 将已成功处理的 PDF 重命名并保存到 `output/` 目录。
4.  将所有提取到的、非重复的发票信息保存为 `output/invoice_data.json` 文件，以便后续人工或脚本进一步处理。
5.  支持通过命令行参数 `--stage` 进行分阶段测试。

更新条件：
- 当主处理流程或命令行参数需要调整时，更新此文件。
- 当需要引入新的处理模块或更改现有模块的调用方式时，更新此文件。
"""

import os
# import shutil # 功能已移至 file_utils.py
from typing import Dict, List, Optional # Optional 可能仍需，List 和 Dict 肯定需要
import argparse
from collections import defaultdict
import json # <-- 新增导入
import asyncio  # 新增：用于并发解析
import shutil  # 新增：在后续阶段仅复制文件，不再二次重命名
import uuid    # 新增：生成全局唯一文件名（UUID）

# # +++++ 新增导入 +++++ # 已移至 extraction.py
# import base64
# from io import BytesIO
# from openai import OpenAI
# from pydantic import BaseModel, Field
# from dotenv import load_dotenv
# from pdf2image import convert_from_path, exceptions as pdf2image_exceptions
# # ----- 结束新增导入 -----

# +++++ 从 config.py 导入配置 +++++
from config import INPUT_DIR, OUTPUT_DIR, DUPLICATES_DIR, TRIP_SHEETS_DIR  # FIELDS 和 REGEX_PATTERNS 由 extraction.py 使用
# ----- 结束导入配置 -----

# +++++ 从 extraction.py 导入功能 +++++
from extraction import parse_invoice, extract_with_pdfplumber # LLMInvoiceOutput, get_openai_client, call_llm_ocr 是内部实现细节
# ----- 结束导入 ----

# +++++ 从 excel_utils.py 导入功能 +++++
# NOTE: Excel 生成逻辑已移除，如需报表请使用单独脚本处理。
# ----- 结束导入 -----

# +++++ 从 file_utils.py 导入功能 +++++
from file_utils import handle_duplicate_invoice
# ----- 结束导入 -----

# +++++ 引入 Trip Sheet 解析函数 +++++
from trip_sheet_parser import parse_trip_sheet_pdf


# -------- 主流程 -------- #

def main():
    # ---------- CLI 解析 ---------- #
    parser = argparse.ArgumentParser(description="中国发票批量处理 / 报销辅助脚本")
    parser.add_argument(
        "--stage",
        choices=["pdfplumber", "llm", "rename", "json"],
        default="json",
        help="分阶段测试：pdfplumber=仅文本解析；llm=解析+LLM兜底；rename=重命名并查重；json=完整流程（保存 JSON）"
    )
    args = parser.parse_args()

    os.makedirs(INPUT_DIR, exist_ok=True)
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    os.makedirs(DUPLICATES_DIR, exist_ok=True)
    os.makedirs(TRIP_SHEETS_DIR, exist_ok=True)

    pdf_files = [f for f in os.listdir(INPUT_DIR) if f.lower().endswith(".pdf")]
    if not pdf_files:
        print("📂 未找到任何 PDF 发票，请将文件放入 input/ 目录后再运行。")
        return

    # ---------- 首轮统一重命名 → UUID ---------- #
    renamed_files = []
    for original_name in pdf_files:
        original_path = os.path.join(INPUT_DIR, original_name)

        # 生成唯一 UUID 文件名，避免极端情况下的冲突
        while True:
            uuid_str = uuid.uuid4().hex  # 无连字符，更精简
            new_name = f"{uuid_str}.pdf"
            new_path = os.path.join(INPUT_DIR, new_name)
            if not os.path.exists(new_path):
                break  # 确保文件名唯一

        try:
            os.rename(original_path, new_path)
            # print(f"🔄 重命名: {original_name} → {new_name}")
            renamed_files.append(new_name)
        except OSError as e:
            print(f"❌ 重命名 {original_name} 失败: {e}")

    # 后续流程统一使用重命名后的文件列表
    pdf_files = renamed_files

    seen_numbers = set()
    parsed_rows: List[Dict[str, str]] = []  # 发票解析结果
    trip_sheet_paths: List[str] = []        # 待解析的行程单 PDF 路径
    seq_counter = 1  # 序号计数器（用于重命名）

    async def run_parsing():
        """并发解析 PDF，返回解析结果列表（顺序与 pdf_files 保持一致）。"""
        tasks = []
        for pdf_path in [os.path.join(INPUT_DIR, f) for f in pdf_files]:
            if args.stage == "pdfplumber":
                tasks.append(asyncio.to_thread(extract_with_pdfplumber, pdf_path))
            else:
                from extraction import parse_invoice_async  # 延迟导入避免循环
                tasks.append(parse_invoice_async(pdf_path))
        return await asyncio.gather(*tasks, return_exceptions=True)

    # 同步函数 main() 里启动异步解析
    parsed_results = asyncio.run(run_parsing())

    # ---------- 处理解析结果 ---------- #
    for pdf_name, result in zip(pdf_files, parsed_results):
        if isinstance(result, Exception):
            print(f"❌ 解析 {pdf_name} 时抛出异常: {result}")
            continue

        info = result

        if args.stage == "pdfplumber":
            # ===== 行程单分流 =====
            if info.get("is_trip_sheet"):
                dest_path = os.path.join(TRIP_SHEETS_DIR, pdf_name)
                try:
                    shutil.copy2(os.path.join(INPUT_DIR, pdf_name), dest_path)
                    print(f"🚕 行程单已识别并复制至 {TRIP_SHEETS_DIR}: {pdf_name}")
                except Exception as e:
                    print(f"❌ 复制行程单 {pdf_name} 失败: {e}")
                continue  # 行程单不再参与普通发票流程

            print(f"[pdfplumber] {pdf_name} -> {info}")
            continue  # pdfplumber 阶段到此结束

        if args.stage == "llm":
            print(f"[llm] {pdf_name} -> {info}")
            continue  # llm 阶段到此结束

        pdf_path = os.path.join(INPUT_DIR, pdf_name)

        # ===== 行程单统一分流（所有阶段适用） =====
        if info.get("is_trip_sheet"):
            dest_path = os.path.join(TRIP_SHEETS_DIR, pdf_name)
            try:
                shutil.copy2(pdf_path, dest_path)
                print(f"🚕 行程单已识别并复制至 {TRIP_SHEETS_DIR}: {pdf_name}")
                trip_sheet_paths.append(dest_path)  # 收集待解析路径
            except Exception as e:
                print(f"❌ 复制行程单 {pdf_name} 失败: {e}")
            continue  # 行程单不走常规发票流程

        # ---------- 重命名 / 去重 ---------- #
        invoice_number = info.get("invoice_number")
        if not invoice_number:
            print(f"⚠️ 无法取得发票号码，跳过文件 {pdf_name}")
            continue

        if args.stage in ["rename", "json"]:
            if handle_duplicate_invoice(pdf_path, invoice_number, seen_numbers):
                continue

        if args.stage == "rename":
            # 仅复制到 OUTPUT_DIR，保持 UUID 文件名
            dest_name = os.path.basename(pdf_path)
            dest_path = os.path.join(OUTPUT_DIR, dest_name)
            try:
                shutil.copy2(pdf_path, dest_path)
                print(f"✅ 已复制: {dest_name} → {OUTPUT_DIR}")
            except Exception as e:
                print(f"❌ 复制 {dest_name} 失败: {e}")
            continue

        # json 阶段：复制并写入 info → parsed_rows
        dest_name = os.path.basename(pdf_path)
        dest_path = os.path.join(OUTPUT_DIR, dest_name)
        try:
            shutil.copy2(pdf_path, dest_path)
        except Exception as e:
            print(f"❌ 复制 {dest_name} 失败: {e}")
            continue

        info["file_name"] = dest_name  # 记录 UUID 文件名
        parsed_rows.append(info)
        seq_counter += 1  # 仍保留计数器，供日志等用途

    # ---------- 行程单解析（并发） ---------- #
    if trip_sheet_paths:
        print(f"🚌 即将解析 {len(trip_sheet_paths)} 份行程单…")

        async def run_trip_sheet_tasks():
            tasks = [asyncio.to_thread(parse_trip_sheet_pdf, p) for p in trip_sheet_paths]
            return await asyncio.gather(*tasks)

        trip_results = asyncio.run(run_trip_sheet_tasks())

        import re

        def _safe_float(s):
            try:
                return float(re.sub(r"[^0-9.]+", "", str(s)))
            except ValueError:
                return None

        for res in trip_results:
            if not res:
                continue

            base_name = os.path.splitext(res.get("file_name", "unknown.pdf"))[0] + ".json"
            json_out = os.path.join(OUTPUT_DIR, base_name)

            # —— 保存行程单 JSON ——
            try:
                with open(json_out, "w", encoding="utf-8") as f:
                    json.dump(res, f, ensure_ascii=False, indent=4)
                print(f"💾 已保存行程单 JSON: {json_out}")
            except IOError as e:
                print(f"❌ 保存行程单 JSON 失败 ({base_name}): {e}")

            # —— 关联到发票 ——
            total_amt = res.get("total_amount")
            if total_amt is None:
                continue
            linked = False
            for inv in parsed_rows:
                inv_amt = _safe_float(inv.get("amount"))
                if inv_amt is None:
                    continue
                # 金额相等 ±0.01 且类别看似运输服务（可选）
                if abs(inv_amt - total_amt) < 0.01:
                    inv["has_trip_sheet"] = True
                    inv["trip_sheet_file"] = os.path.basename(json_out)
                    linked = True
                    break
            if not linked:
                print(f"⚠️ 未找到与行程单 {base_name} 匹配的发票（金额 {total_amt}）。")

    # ---------- 最终保存 / 更新发票 JSON ---------- #
    if parsed_rows:
        json_output_path = os.path.join(OUTPUT_DIR, "invoice_data.json")
        try:
            with open(json_output_path, "w", encoding="utf-8") as f:
                json.dump(parsed_rows, f, ensure_ascii=False, indent=4)
            print(f"💾 数据已保存到 JSON 文件: {json_output_path}")
        except IOError as e:
            print(f"❌ 保存 JSON 文件失败: {e}")
    else:
        if args.stage == "json":
            print("⚠️ 没有可保存到 JSON 的发票数据！")


if __name__ == "__main__":
    import time
    
    start_time = time.time()
    try:
        main()
    finally:
        end_time = time.time()
        print(f"✅ 程序执行完成，总耗时: {end_time - start_time:.2f} 秒") 