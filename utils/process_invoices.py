"""
这个脚本用于处理发票PDF文件。它会：
1. 读取所有PDF文件
2. 从每个PDF中提取"项目名称"中被*包围的内容
3. 提取金额（小写）
4. 用这些信息重命名文件
"""

import os
import re
import pdfplumber

def extract_info_from_pdf(pdf_path):
    try:
        with pdfplumber.open(pdf_path) as pdf:
            text = ""
            for page in pdf.pages:
                text += page.extract_text()
            
            # 查找项目名称中被*包围的内容
            project_name_match = re.search(r'\*([^*]+)\*', text)
            project_name = project_name_match.group(1) if project_name_match else None
            
            # 查找金额（小写）
            amount_match = re.search(r'（小写）¥?(\d+\.\d{2})', text)
            amount = amount_match.group(1) if amount_match else None
            
            return project_name, amount
    except Exception as e:
        print(f"处理文件 {pdf_path} 时出错: {str(e)}")
        return None, None

def main():
    # 获取当前目录下所有PDF文件
    pdf_files = [f for f in os.listdir('.') if f.lower().endswith('.pdf')]
    
    for pdf_file in pdf_files:
        project_name, amount = extract_info_from_pdf(pdf_file)
        
        if project_name and amount:
            # 构建新文件名
            new_filename = f"{project_name}_{amount}元.pdf"
            
            try:
                # 如果新文件名已存在，添加数字后缀
                base_name = new_filename[:-4]
                extension = new_filename[-4:]
                counter = 1
                while os.path.exists(new_filename):
                    new_filename = f"{base_name}_{counter}{extension}"
                    counter += 1
                
                os.rename(pdf_file, new_filename)
                print(f"已重命名: {pdf_file} -> {new_filename}")
            except Exception as e:
                print(f"重命名文件 {pdf_file} 时出错: {str(e)}")
        else:
            print(f"无法从文件 {pdf_file} 中提取所需信息")

if __name__ == "__main__":
    main() 