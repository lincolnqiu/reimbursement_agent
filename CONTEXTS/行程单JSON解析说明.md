# 行程单 JSON 解析说明 📄

> 本文件描述 `src/trip_sheet_parser.py` 的功能、使用方法与维护要点。
> 若脚本逻辑、输出格式或存储路径有变动，请同步更新本说明。

---

## 1️⃣ 脚本定位

`src/trip_sheet_parser.py` 专用于解析 **行程单（Trip Sheet）** PDF，将其表格数据
(上车日期、起点、终点、金额) 及合计金额抽取，保存至 `output/trip_sheet_data.json`。

与发票主流程 (`src/main.py`) 相互独立：
1. 主流程负责检测并分流行程单至 `trip_sheets/` 目录；
2. 本脚本负责后续表格解析及 JSON 报表生成。

---

## 2️⃣ 使用示例 🧪

```bash
# 解析 trip_sheets 目录下所有 PDF
python src/trip_sheet_parser.py

# 仅解析指定文件
python src/trip_sheet_parser.py trip_sheets/1234abcd.pdf
```

成功后将在 `output/` 生成 `trip_sheet_data.json`：

```json
[
  {
    "file_name": "1234abcd.pdf",
    "total_amount": 11111,
    "trips": [
      {
        "date": "2025/04/11",
        "origin": "上海",
        "destination": "北京",
        "amount": 1111
      },
      // ... 其余行程 ...
    ]
  }
]
```

---

## 3️⃣ 维护提示 ⚙️

1. **表格列索引**：如行程单版式或列顺序改变，需在 `_extract_trips_from_table` 中调整
   `DATE_COL / ORIGIN_COL / DEST_COL / AMOUNT_COL`。
2. **金额解析**：默认正则 `r"[0-9]+(?:\.[0-9]{1,2})?"`，如出现千位分隔符或货币符号，请更新
   `_AMOUNT_REGEX_SIMPLE`。
3. **日期年份**：脚本根据 `行程起止日期：YYYY-MM-DD` 获取年份。若文本格式改变，请更新
   `_YEAR_IN_RANGE_REGEX`。

> 💡 **建议**：若未来需导出 Excel、制作可视化报告，可基于本 JSON 再行处理，而无需
> 直接在主流程中修改行程单逻辑。 