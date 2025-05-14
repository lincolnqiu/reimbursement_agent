'''
config.py
=========
该文件包含发票报销工具所需的所有配置常量。

定义了输入/输出目录、Excel 文件路径、关键字段名、以及用于解析发票的正则表达式。

更新条件：
- 当目录结构、目标 Excel 文件名、需要提取的字段或发票文本格式发生变化时，需要更新此文件中的相应常量。
'''

import os
import re

# -------- 目录配置 -------- #
INPUT_DIR = "input"
OUTPUT_DIR = "output"
DUPLICATES_DIR = "duplicates"  # 存放重复发票的目录
TRIP_SHEETS_DIR = "trip_sheets"  # 行程单（如滴滴出行）单独存放
EXCEL_PATH = os.path.join(OUTPUT_DIR, "invoice_report.xlsx")

# -------- 字段配置 -------- #
# 需要抽取的字段
FIELDS = [
    "invoice_type",  # 普票 / 专票
    "amount",        # 含税金额
    "category",      # 货物或服务名称
    "invoice_number" # 8 位发票号码
]

# -------- 正则表达式汇总（针对电子普票/专票新版样式优化） -------- #

# 说明：
# 1. 电子票标题通常两种：
#    • 电子发票（普通发票）
#    • 电子发票（增值税专用发票）
# 2. 发票号码长度：纸质票 8 位，电子票 20 位左右，因此统一匹配 8-20 位数字。
# 3. 金额位置示例：
#    （小写）¥198.00 或 （小写）￥6427.50
#
# 若后续格式再变，可继续在此处微调。

REGEX_PATTERNS = {
    # 捕获「普通」或「专用」，用于后续映射成 普票/专票
    "invoice_type": re.compile(r"(普通|专用)发票"),

    # 金额允许整数或两位小数
    "amount": re.compile(r"小写[）)\s]*[¥￥]?([0-9]+(?:\.[0-9]{2})?)"),

    # 发票号码：8-20 位数字
    "invoice_number": re.compile(r"发票号码[:：\s]*([0-9]{8,20})"),

    # 类别：优先匹配 *xxx*，否则匹配列名前缀
    "category_star": re.compile(r"\*([^*]{1,30})\*"),
    "category_column": re.compile(r"(?:项目名称|货物或应税劳务、服务名称)[\\s:：]*([^\\s]+)")
} 