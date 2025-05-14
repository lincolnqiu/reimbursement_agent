'''
trip_sheet_parser.py
===================
该文件专门负责解析存放于 `trip_sheets/` 目录中的 *行程单（Trip Sheet）* PDF，
并将以下结构化信息保存为 JSON：
1. `total_amount`：行程单合计金额（浮点数）。
2. `trips`：列表，每一项包含：
   • `date` 上车日期，格式 `yyyy/mm/dd`。
   • `origin` 起点字符串。
   • `destination` 终点字符串。
   • `amount` 该行程金额（浮点数）。

典型使用场景：主流程 (`src/main.py`) 已将检测到的行程单 PDF 复制到 `trip_sheets/` 目录，
若需要进一步解析行程单表格并生成报表，可直接调用本脚本：

```bash
python src/trip_sheet_parser.py            # 解析全部行程单并输出 JSON
python src/trip_sheet_parser.py foo.pdf    # 仅解析指定文件
```

更新条件：
- 行程单版式或表头发生变化导致表格列索引变动时，需要调整 `_extract_trips_from_table` 中的列映射。
- 需要提取更多字段（如车型、里程等）时，扩展 `_extract_trips_from_table` 的返回值。
'''

import os
import json
import re
from typing import List, Dict, Any, Optional

import pdfplumber

from config import TRIP_SHEETS_DIR, OUTPUT_DIR

# ---------- 正则 ---------- #
_TOTAL_AMOUNT_REGEX = re.compile(r"合计\s*([0-9]+(?:\.[0-9]{1,2})?)\s*元")
_YEAR_IN_RANGE_REGEX = re.compile(r"行程起止日期[:：]\s*([0-9]{4})-")
_DATE_PART_REGEX = re.compile(r"(\d{2})-(\d{2})")
_AMOUNT_REGEX_SIMPLE = re.compile(r"[0-9]+(?:\.[0-9]{1,2})?")


# ---------- 内部帮助函数 ---------- #

def _extract_year(full_text: str) -> str:
    """从整页文本中提取行程年份，默认当前年份。"""
    m = _YEAR_IN_RANGE_REGEX.search(full_text)
    if m:
        return m.group(1)
    # 兜底：使用当前年份
    from datetime import datetime
    return str(datetime.now().year)


def _standardize_date(date_part: str, year: str) -> Optional[str]:
    """将如 '04-11' 转成 'YYYY/MM/DD'。若匹配失败返回 None。"""
    m = _DATE_PART_REGEX.match(date_part)
    if not m:
        return None
    month, day = m.groups()
    return f"{year}/{month}/{day}"


def _extract_trips_from_table(table: List[List[str]], year: str) -> List[Dict[str, Any]]:
    """根据已识别的行程表格（含表头）提取 trips 列表。"""
    trips: List[Dict[str, Any]] = []

    # 先确定表头所在行（含『上车时间』关键词）
    header_idx = None
    for idx, row in enumerate(table):
        if row and any("上车时间" in (cell or "") for cell in row):
            header_idx = idx
            break
    if header_idx is None:
        # 未找到表头
        return trips

    # ---------- 动态确定列索引 ---------- #
    header_row = table[header_idx]

    def _find_col(keyword: str) -> Optional[int]:
        for i, cell in enumerate(header_row):
            if cell and keyword in cell:
                return i
        return None

    DATE_COL = _find_col("上车时间") or 2  # 回退默认
    ORIGIN_COL = _find_col("起点") or 5
    DEST_COL = _find_col("终点") or (ORIGIN_COL + 1)
    AMOUNT_COL = _find_col("金额")
    if AMOUNT_COL is None:
        # 兜底：尝试在 header 中包含 '金额[' 或 '[' 字符的列
        AMOUNT_COL = next((i for i, c in enumerate(header_row) if c and "金额" in c), 8)

    for row in table[header_idx + 1:]:
        if not row or not row[0]:  # 跳过空行
            continue
        # 尝试行号是数字来判断有效行
        try:
            int(str(row[0]).strip())
        except ValueError:
            continue

        # --- 日期 --- #
        date_raw = (row[DATE_COL] or "").strip() if len(row) > DATE_COL else ""
        date_std = _standardize_date(date_raw.split()[0] if date_raw else "", year)
        if not date_std:
            # 若日期无法解析，跳过该行
            continue

        # --- 起点 / 终点 --- #
        origin = (row[ORIGIN_COL] or "").strip() if len(row) > ORIGIN_COL else ""
        destination = (row[DEST_COL] or "").strip() if len(row) > DEST_COL else ""

        # --- 金额 --- #
        amount_raw = (row[AMOUNT_COL] or "") if len(row) > AMOUNT_COL else ""
        # 去掉诸如 '元'、'￥'、'¥' 等符号
        amount_raw_clean = re.sub(r"[元¥￥,]", "", amount_raw)
        amt_match = _AMOUNT_REGEX_SIMPLE.search(amount_raw_clean)
        amount_val: Optional[float] = float(amt_match.group()) if amt_match else None

        if not origin and not destination and amount_val is None:
            # 可能是表格尾部空行
            continue

        trips.append({
            "date": date_std,
            "origin": origin,
            "destination": destination,
            "amount": amount_val,
        })

    return trips


# ---------- 核心解析函数 ---------- #

def parse_trip_sheet_pdf(pdf_path: str) -> Dict[str, Any]:
    """解析单个 Trip Sheet PDF，返回包含合计金额与 trips 列表的 dict。"""
    result: Dict[str, Any] = {
        "file_name": os.path.basename(pdf_path),
        "total_amount": None,
        "trips": [],
    }

    try:
        with pdfplumber.open(pdf_path) as pdf:
            # —— 先整体文本，用于抓总金额 & 年份 ——
            full_text = "".join(page.extract_text() or "" for page in pdf.pages)

            # 合计金额
            amount_match = _TOTAL_AMOUNT_REGEX.search(full_text)
            if amount_match:
                result["total_amount"] = float(amount_match.group(1))

            # 年份，用于格式化日期
            year = _extract_year(full_text)

            # —— 遍历表格 ——
            for page in pdf.pages:
                tables = page.extract_tables() or []
                for table in tables:
                    trips_from_table = _extract_trips_from_table(table, year)
                    if trips_from_table:
                        result["trips"].extend(trips_from_table)
    except Exception as e:
        print(f"❌ 解析行程单 {os.path.basename(pdf_path)} 失败: {e}")

    return result


# ---------- CLI 入口 ---------- #

def main():
    """遍历 trip_sheets/ 目录，解析所有 PDF 并保存 JSON。"""
    import argparse
    parser = argparse.ArgumentParser(description="解析 trip_sheets 目录中的行程单 PDF，并生成 JSON 数据。")
    parser.add_argument("pdf", nargs="?", help="可选：仅解析指定的 PDF 文件。路径可以是绝对或相对。")
    args = parser.parse_args()

    # —— 准备目标文件列表 ——
    if args.pdf:
        target_files = [args.pdf] if os.path.isfile(args.pdf) else []
        if not target_files:
            print(f"⚠️ 指定的文件不存在：{args.pdf}")
            return
    else:
        if not os.path.isdir(TRIP_SHEETS_DIR):
            print(f"⚠️ 未找到目录 {TRIP_SHEETS_DIR}，请先运行主流程识别并分流行程单。")
            return
        target_files = [os.path.join(TRIP_SHEETS_DIR, f) for f in os.listdir(TRIP_SHEETS_DIR) if f.lower().endswith(".pdf")]
        if not target_files:
            print(f"📂 {TRIP_SHEETS_DIR} 目录为空，没有可解析的 PDF。")
            return

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    for pdf_path in target_files:
        base_name = os.path.basename(pdf_path)
        print(f"🚌 正在解析行程单: {base_name}")
        parsed_result = parse_trip_sheet_pdf(pdf_path)

        json_name = os.path.splitext(base_name)[0] + ".json"
        json_path = os.path.join(OUTPUT_DIR, json_name)

        try:
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(parsed_result, f, ensure_ascii=False, indent=4)
            print(f"💾 行程单数据已保存至: {json_path}")
        except IOError as e:
            print(f"❌ 保存 JSON 失败 ({json_name}): {e}")


if __name__ == "__main__":
    main() 