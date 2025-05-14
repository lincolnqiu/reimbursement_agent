'''
extraction.py
=============
该文件负责从 PDF 发票中提取结构化信息。它结合了两种主要方法：
1. 使用 `pdfplumber`库进行基于规则的文本提取。
2. 调用 OpenAI GPT-4o (Vision) API 进行图像 OCR 和智能信息提取，作为 `pdfplumber` 无法完整解析时的兜底方案。

此文件定义了与 LLM 交互所需的 Pydantic 模型 (`LLMInvoiceOutput`)，
以及实际执行提取的核心函数：`extract_with_pdfplumber`、`call_llm_ocr` 和 `parse_invoice`。

更新条件：
- 当发票的 PDF 文本布局发生较大变化，影响 `pdfplumber` 的规则提取时，需更新 `extract_with_pdfplumber` 中的逻辑或 `config.REGEX_PATTERNS`。
- 当 OpenAI API 发生变化或需要调整 LLM 的提示、模型参数时，需更新 `call_llm_ocr`。
- 当需要提取新的字段或修改现有字段的提取逻辑时，可能需要同时更新 `config.FIELDS`、Pydantic 模型以及此文件中的提取函数。
'''

import os
import re
import base64
from io import BytesIO
from typing import Dict, Optional

import pdfplumber
from pdf2image import convert_from_path, exceptions as pdf2image_exceptions
from openai import OpenAI
from pydantic import BaseModel, Field
from dotenv import load_dotenv

from config import FIELDS, REGEX_PATTERNS

# 加载 .env 文件 (如果 OpenAI key 等敏感信息存放在此)
load_dotenv()

# +++++ Pydantic Models for LLM Output +++++
class LLMInvoiceOutput(BaseModel):
    invoice_type: Optional[str] = Field(None, description="发票类型，例如 '增值税普通发票', '增值税专用发票', '普通发票', '专用发票'")
    invoice_number: Optional[str] = Field(None, description="发票号码")
    category: Optional[str] = Field(None, description="主要货物或应税劳务、服务名称。如果是多个项目，选择最主要的一个或综合描述。例如 *住宿服务*费, *咨询*服务, *办公用品*等。")
    amount: Optional[str] = Field(None, description="价税合计 (小写) 金额，字符串格式，例如 '198.00', '600'")

LLMInvoiceOutput.model_rebuild()
# ----- End Pydantic Models -----

_openai_client = None # 全局 OpenAI Client 实例

def get_openai_client():
    """获取或初始化 OpenAI Client (单例模式)"""
    global _openai_client
    if _openai_client is None:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            print("❌ OPENAI_API_KEY 未在环境变量中设置。LLM 调用将失败。")
            print("   请在项目根目录创建 .env 文件并填入 OPENAI_API_KEY=\"sk-xxxxxxxx\"")
            return None
        _openai_client = OpenAI(
            api_key=api_key,
            base_url=os.getenv("OPENAI_BASE_URL"),  # 可选, 用于代理
        )
    return _openai_client

def extract_with_pdfplumber(pdf_path: str) -> Dict[str, Optional[str]]:
    """使用 pdfplumber 解析 PDF，提取字段。返回 dict，即使字段缺失也返回键。"""
    # 默认结果字典，同时引入 is_trip_sheet 标志位，后续流程可据此做分流
    result = {k: None for k in FIELDS}
    result["is_trip_sheet"] = False
    try:
        with pdfplumber.open(pdf_path) as pdf:
            text = "".join(page.extract_text() or "" for page in pdf.pages)

            # ====== 行程单检测 ======
            # 滴滴、美团等行程单通常包含关键词『行程单』『TRIP TABLE』
            if any(keyword in text for keyword in ["行程单", "TRIP TABLE"]):
                # 标记为行程单并直接返回，暂不做后续字段提取
                result["is_trip_sheet"] = True
                return result

            # 1️⃣ 发票类型 & 号码 & 金额 —— 直接按对应 regex 提取
            for key in ("invoice_type", "invoice_number", "amount"):
                m = REGEX_PATTERNS[key].search(text)
                if m:
                    if key == "invoice_type":
                        result[key] = "专票" if "专用" in m.group(1) else "普票"
                    else:
                        result[key] = m.group(1)

            # 2️⃣ 类别 —— 先尝试 *星号* 包围，再回退列名前缀
            cat_match = REGEX_PATTERNS["category_star"].search(text)
            if cat_match:
                potential_category = cat_match.group(1).strip()
                if 0 < len(potential_category) <= 30: # 简单长度校验
                    result["category"] = potential_category
            
            if not result["category"]:
                cat_match = REGEX_PATTERNS["category_column"].search(text)
                if cat_match:
                    potential_category = cat_match.group(1).strip()
                    # 避免提取过长或看起来像表头串的情况
                    if 0 < len(potential_category) <= 30 and not any(kw in potential_category for kw in ["规格", "型号", "单位", "数量", "单价", "金额", "税率", "税额"]):
                        result["category"] = potential_category

            # 3️⃣ 最后兜底：从文件名推断类别（假设文件名格式 如 8_信息技术服务_4200元.pdf）
            if not result["category"]:
                base_name = os.path.basename(pdf_path)
                name_part = os.path.splitext(base_name)[0]  # 去掉扩展名
                parts = name_part.split("_")
                for p in parts[1:]:
                    # 确保 p 是字符串，并且不含典型列标题或看起来不像类别
                    if isinstance(p, str) and re.search(r"[\u4e00-\u9fff]", p) and \
                       not re.search(r"\d", p) and 0 < len(p.strip()) <= 15 and \
                       not any(kw in p for kw in ["票", "元", "规格", "型号", "pdf"]):
                        result["category"] = p.strip()
                        break
    except Exception as e:
        print(f"❌ 使用 pdfplumber 处理 {pdf_path} 出错: {e}")
    return result

def call_llm_ocr(pdf_path: str) -> Dict[str, Optional[str]]:
    """使用 OpenAI GPT-4o (Vision) 和 Pydantic 结构化输出识别发票图片。"""
    print(f"ℹ️ 尝试使用 LLM OCR 识别: {os.path.basename(pdf_path)}")
    client = get_openai_client()
    if not client:
        return {k: None for k in FIELDS}

    img_base64 = None
    try:
        # 将PDF首页转为PNG图片 (1-indexed for pages)
        images = convert_from_path(pdf_path, first_page=1, last_page=1, dpi=200)
        if images:
            buffered = BytesIO()
            images[0].save(buffered, format="PNG")
            img_base64 = base64.b64encode(buffered.getvalue()).decode('utf-8')
    except pdf2image_exceptions.PDFInfoNotInstalledError:
        print("❌ Poppler (pdfinfo) 未安装或未在系统 PATH 中。LLM OCR 需要此工具转换PDF。")
        print("   请参照 `CONTEXTS/发票报销工具使用指南.md` 或 `requirements.txt` 中的 Poppler 安装说明。")
        return {k: None for k in FIELDS}
    except Exception as e:
        print(f"❌ PDF 转图片失败 ({os.path.basename(pdf_path)}): {e}")
        return {k: None for k in FIELDS}

    if not img_base64:
        print(f"❌ 未能从 PDF 生成图片用于 LLM 识别: {os.path.basename(pdf_path)}")
        return {k: None for k in FIELDS}

    try:
        completion = client.beta.chat.completions.parse(
            model="gpt-4o-mini",  # 可选 'gpt-4o-mini' 速度更快成本更低，但对复杂图片效果可能稍逊
            messages=[
                {
                    "role": "system",
                    "content": (
                        "你是一个专业的中国发票识别助手。"
                        "请仔细分析提供的发票图片，并严格按照定义的 JSON Schema 提取信息。"
                        "如果内容是形成报销单，直接return空"
                        "如果某个字段在图片中无法找到或无法确定，请将其值设为 null。"
                        "对于'invoice_type'，请明确指出是'普通发票'还是'专用发票'或类似的准确表述 (如'电子发票（普通发票）')。"
                        "对于'category'，请提取主要的商品或服务名称，例如 '*信息技术服务*咨询费', '*办公用品*采购'。如果是多个项目，选择最主要的一个或进行简短的综合描述。"
                        "对于'amount'，请提取图片中价税合计的小写金额，并以字符串形式返回。"
                        "对于'invoice_number'，请提取发票号码。"
                    ),
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/png;base64,{img_base64}"},
                        },
                        {"type": "text", "text": "请从这张发票图片中提取关键信息。"},
                    ],
                },
            ],
            response_format=LLMInvoiceOutput,
            temperature=0.1, 
            max_tokens=500, # 限制输出 token 数量，避免过长或无关内容
        )

        if completion.choices[0].message.parsed:
            parsed_invoice: LLMInvoiceOutput = completion.choices[0].message.parsed
            
            extracted_info = {k: None for k in FIELDS}
            extracted_info["invoice_number"] = parsed_invoice.invoice_number
            extracted_info["amount"] = parsed_invoice.amount # 已经是字符串
            extracted_info["category"] = parsed_invoice.category

            if parsed_invoice.invoice_type:
                type_lower = parsed_invoice.invoice_type.lower()
                if "专用" in type_lower:
                    extracted_info["invoice_type"] = "专票"
                elif "普通" in type_lower:
                    extracted_info["invoice_type"] = "普票"
                else: 
                    print(f"⚠️ LLM 返回的发票类型 '{parsed_invoice.invoice_type}' 未能明确归类为普票/专票，将直接使用。")
                    extracted_info["invoice_type"] = parsed_invoice.invoice_type
            
            print(f"✅ LLM OCR 成功: {os.path.basename(pdf_path)} -> {extracted_info}")
            return extracted_info
        elif completion.choices[0].message.refusal:
            print(f"⚠️ LLM 拒绝处理或返回格式不符 ({os.path.basename(pdf_path)}): {completion.choices[0].message.refusal}")
            return {k: None for k in FIELDS}
        else:
            print(f"⚠️ LLM 返回未知错误，无法解析 ({os.path.basename(pdf_path)})")
            return {k: None for k in FIELDS}

    except Exception as e:
        import traceback
        print(f"❌ 调用 OpenAI API 或解析时出错 ({os.path.basename(pdf_path)}): {e}")
        print(traceback.format_exc()) # 打印详细的 traceback
        return {k: None for k in FIELDS}

def parse_invoice(pdf_path: str) -> Dict[str, Optional[str]]:
    """先尝试 pdfplumber，若结果缺失则用 LLM 补足。"""
    info = extract_with_pdfplumber(pdf_path)
    # 如果是行程单，直接返回，不做进一步提取
    if info.get("is_trip_sheet"):
        return info

    # 仅检查核心字段是否完整 (忽略诸如 is_trip_sheet 等辅助标记)
    core_values_complete = all(info.get(k) for k in FIELDS)
    if not core_values_complete:
        # 检查是否所有字段都是None，或者关键字段如号码和金额缺失，才考虑LLM
        all_none = all(info.get(k) is None for k in FIELDS)
        critical_missing = not info.get("invoice_number") or not info.get("amount")

        if all_none or critical_missing or any(info.get(k) is None for k in ["invoice_type", "category"]):
            print(f"ℹ️ pdfplumber 提取不完整: {info}，尝试 LLM OCR。")
            llm_info = call_llm_ocr(pdf_path)
            # 仅补全缺失字段
            for k, v in llm_info.items():
                if not info.get(k) and v: # 如果原始info中该字段为空，且llm提取到了值
                    info[k] = v
    return info 

import asyncio
from openai import AsyncOpenAI

# ===== 异步 OpenAI Client 单例 =====
_openai_async_client = None  # AsyncOpenAI 实例 (全局)


def get_async_openai_client() -> Optional[AsyncOpenAI]:
    """获取或初始化 AsyncOpenAI Client (单例模式)。"""
    global _openai_async_client
    if _openai_async_client is None:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            print("❌ OPENAI_API_KEY 未设置，异步 LLM 调用将失败。")
            return None
        _openai_async_client = AsyncOpenAI(
            api_key=api_key,
            base_url=os.getenv("OPENAI_BASE_URL"),
        )
    return _openai_async_client


# ===== 辅助函数：PDF → PNG(base64) =====
def _pdf_first_page_to_base64_sync(pdf_path: str) -> Optional[str]:
    """同步函数：将 PDF 首页转换为 PNG 并返回 base64 字符串。"""
    try:
        images = convert_from_path(pdf_path, first_page=1, last_page=1, dpi=200)
        if images:
            buffered = BytesIO()
            images[0].save(buffered, format="PNG")
            return base64.b64encode(buffered.getvalue()).decode("utf-8")
    except pdf2image_exceptions.PDFInfoNotInstalledError:
        print("❌ Poppler 未安装，LLM OCR 无法执行 PDF → 图片 转换。")
    except Exception as e:
        print(f"❌ PDF 转图片失败 ({os.path.basename(pdf_path)}): {e}")
    return None


# ===== 异步版 LLM OCR =====
async def call_llm_ocr_async(pdf_path: str) -> Dict[str, Optional[str]]:
    """异步调用 OpenAI Vision 接口进行 OCR，返回提取信息 dict。"""
    print(f"ℹ️ [async] 尝试 LLM OCR: {os.path.basename(pdf_path)}")
    client = get_async_openai_client()
    if not client:
        return {k: None for k in FIELDS}

    # 1) PDF → base64 PNG 放到线程池执行，避免阻塞事件循环
    img_base64 = await asyncio.to_thread(_pdf_first_page_to_base64_sync, pdf_path)
    if not img_base64:
        return {k: None for k in FIELDS}

    try:
        completion = await client.beta.chat.completions.parse(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "你是一个专业的中国发票识别助手。请严格按照 JSON Schema 提取信息。"
                        "若某字段缺失则返回 null。"
                    ),
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/png;base64,{img_base64}"},
                        },
                        {"type": "text", "text": "请从这张发票图片中提取关键信息。"},
                    ],
                },
            ],
            response_format=LLMInvoiceOutput,
            temperature=0.1,
            max_tokens=500,
        )

        msg = completion.choices[0].message
        if msg.parsed:
            p: LLMInvoiceOutput = msg.parsed
            extracted_info = {k: None for k in FIELDS}
            extracted_info.update(
                {
                    "invoice_number": p.invoice_number,
                    "amount": p.amount,
                    "category": p.category,
                }
            )
            if p.invoice_type:
                tl = p.invoice_type.lower()
                if "专用" in tl:
                    extracted_info["invoice_type"] = "专票"
                elif "普通" in tl:
                    extracted_info["invoice_type"] = "普票"
                else:
                    extracted_info["invoice_type"] = p.invoice_type
            print(f"✅ [async] LLM OCR 成功: {os.path.basename(pdf_path)} -> {extracted_info}")
            return extracted_info
        elif msg.refusal:
            print(f"⚠️ [async] LLM 拒绝处理 ({os.path.basename(pdf_path)}): {msg.refusal}")
        else:
            print(f"⚠️ [async] LLM 返回未知状态 ({os.path.basename(pdf_path)})")
    except Exception as e:
        import traceback
        print(f"❌ [async] 调用 OpenAI API 出错 ({os.path.basename(pdf_path)}): {e}")
        print(traceback.format_exc())
    return {k: None for k in FIELDS}


# ===== 异步发票解析 =====
async def parse_invoice_async(pdf_path: str) -> Dict[str, Optional[str]]:
    """异步版本：线程池运行 pdfplumber，必要时调用异步 LLM OCR 补全。"""
    info = await asyncio.to_thread(extract_with_pdfplumber, pdf_path)

    # 如果是行程单，直接返回，不做进一步提取
    if info.get("is_trip_sheet"):
        return info

    # 仅检查核心字段是否完整 (忽略诸如 is_trip_sheet 等辅助标记)
    core_values_complete = all(info.get(k) for k in FIELDS)
    if not core_values_complete:
        # 检查是否所有字段都是None，或者关键字段如号码和金额缺失，才考虑LLM
        all_none = all(info.get(k) is None for k in FIELDS)
        critical_missing = not info.get("invoice_number") or not info.get("amount")

        if all_none or critical_missing or any(info.get(k) is None for k in [
            "invoice_type", "category"]):
            llm_info = await call_llm_ocr_async(pdf_path)
            for k, v in llm_info.items():
                if not info.get(k) and v:
                    info[k] = v
    return info