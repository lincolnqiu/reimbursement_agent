"""
此文件用于计算目录中所有PDF发票的总金额。
它通过解析PDF文件名中的金额信息来计算，不需要读取PDF内容。
当有新的PDF发票添加到目录时，重新运行此脚本以更新总金额。
"""

import os
import re
from collections import defaultdict

def extract_amount(filename):
    """从文件名中提取金额"""
    match = re.search(r'_(\d+(?:\.\d+)?)元', filename)
    if match:
        return float(match.group(1))
    return 0.0

def calculate_totals():
    """计算所有PDF发票的总金额和按类别统计的金额"""
    total_amount = 0.0
    category_totals = defaultdict(float)
    
    # 遍历当前目录中的所有PDF文件
    for filename in os.listdir('.'):
        if filename.endswith('.pdf'):
            # 提取类别（第一个下划线之前的部分）
            category = filename.split('_')[0]
            amount = extract_amount(filename)
            
            total_amount += amount
            category_totals[category] += amount
    
    return total_amount, category_totals

def main():
    total, categories = calculate_totals()
    
    print("\n=== 发票总额统计 ===")
    print(f"\n总金额: {total:,.2f}元")
    
    print("\n按类别统计:")
    print("-" * 30)
    for category, amount in sorted(categories.items()):
        print(f"{category}: {amount:,.2f}元")
    print("-" * 30)

if __name__ == "__main__":
    main() 