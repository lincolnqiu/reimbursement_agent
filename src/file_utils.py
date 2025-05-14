'''
file_utils.py
=============
该文件提供文件处理相关的辅助函数，主要用于发票处理流程中的文件管理。
功能包括：
1.  处理重复发票：检查发票号码是否已存在，如果重复，则将当前发票文件复制到 `duplicates` 目录，
    并确保文件名唯一（通过添加后缀如 `_dup` 或 `_dup1` 等）。
2.  重命名并移动已处理的发票：根据提取的发票信息（序号、类别、金额）生成新的、标准化的文件名，
    并将文件从输入目录复制到输出目录。同样会处理潜在的文件名冲突。

更新条件：
- 当重复文件的处理逻辑（如目标目录、命名规则）需要更改时。
- 当已处理文件的命名规则或目标目录需要调整时。
- 如果底层文件操作（如复制、检查路径存在）需要更复杂的错误处理或日志记录时。
'''

import os
import shutil
from typing import Dict, Set, Optional

from config import OUTPUT_DIR, DUPLICATES_DIR

def handle_duplicate_invoice(pdf_path: str, invoice_number: str, seen_numbers: Set[str]) -> bool:
    """
    检查发票号码是否重复。如果是，则复制到 duplicates 目录并返回 True。
    否则，将发票号码添加到 seen_numbers 并返回 False。
    """
    if invoice_number in seen_numbers:
        pdf_name = os.path.basename(pdf_path)
        duplicate_path = os.path.join(DUPLICATES_DIR, pdf_name)
        counter = 0
        base, ext = os.path.splitext(pdf_name)
        while os.path.exists(duplicate_path):
            counter += 1
            duplicate_path = os.path.join(DUPLICATES_DIR, f"{base}_dup{counter}{ext}")
        
        try:
            shutil.copy2(pdf_path, duplicate_path)
            print(f"🔁 发现重复发票号码: {invoice_number}，已复制到 {duplicate_path}")
        except Exception as e:
            print(f"❌ 复制重复文件 {pdf_name} 到 {DUPLICATES_DIR} 失败: {e}")
        return True # 表示是重复文件
    
    seen_numbers.add(invoice_number)
    return False # 表示不是重复文件

def rename_and_move_processed_pdf(
    pdf_path: str, 
    invoice_info: Dict[str, Optional[str]], 
    seq_counter: int
) -> Optional[str]:
    """
    根据发票信息重命名 PDF，并将其从原始路径复制到 OUTPUT_DIR。
    返回新的文件名 (如果成功)，否则返回 None。
    文件名格式: 序号-类别_金额元_序号.pdf
    """
    pdf_name = os.path.basename(pdf_path)
    category = invoice_info.get("category") or "未知类别"
    amount = invoice_info.get("amount") or "未知金额"

    # 清理类别名中的非法字符
    category_clean = ''.join(c for c in category if c not in r'<>:"/\\|?*')

    base_new_name = f"{seq_counter}-{category_clean}_{amount}元"
    new_name_suffix = ".pdf"
    new_pdf_name = base_new_name + new_name_suffix
    dest_path = os.path.join(OUTPUT_DIR, new_pdf_name)
    
    # 处理文件名冲突
    name_conflict_counter = 1
    while os.path.exists(dest_path):
        new_pdf_name = f"{base_new_name}_{name_conflict_counter}{new_name_suffix}"
        dest_path = os.path.join(OUTPUT_DIR, new_pdf_name)
        name_conflict_counter += 1
    
    try:
        shutil.copy2(pdf_path, dest_path)
        print(f"✅ 已复制并重命名: {pdf_name} -> {new_pdf_name} (存放于 {OUTPUT_DIR})")
        return new_pdf_name
    except Exception as e:
        print(f"❌ 重命名并移动文件 {pdf_name} 时出错: {str(e)}")
        return None 