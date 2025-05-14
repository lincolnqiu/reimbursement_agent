**快速测试脚本：用 Python + OpenAI SDK 验证「结构化输出 / 发票信息提取」**

> **作用**：向 GPT-4o 发送一段发票相关的描述，要求它**必须**返回符合我们预定义 JSON Schema（发票结构）的结构化结果，然后打印该发票对象。
> **依赖**：`pip install --upgrade openai pydantic python-dotenv`（SDK ≥ 1.26.0 支持 `.beta.chat.completions.parse`，`dotenv` 用于管理环境变量）

```python
# test_structured_invoice.py
\"\"\"
测试脚本：使用 OpenAI SDK 结构化生成发票信息 🧾

本文件演示如何使用新版 OpenAI Python SDK（≥ 1.26.0）和 `beta.chat.completions.parse` 方法，
向模型请求发票信息并以我们定义的 Pydantic `Invoice` Schema 严格返回。

功能概述：
1. 定义包含递归行项目的 `Invoice` 数据模型；
2. 调用 OpenAI 接口并要求模型返回符合 Schema 的 JSON；
3. 将返回数据自动解析为 Pydantic 对象并打印。

⚙️ 使用前准备：
- 在环境变量中设置 `OPENAI_API_KEY`（必填）以及 `OPENAI_BASE_URL`（如需自定义域名时可填）。
  建议创建 `.env` 文件并填入以下内容：
  OPENAI_API_KEY=sk-...
  OPENAI_BASE_URL=https://your-proxy-endpoint/v1  # 如无自定义可省略
- 依赖：`pip install --upgrade openai pydantic python-dotenv`（建议在 venv 环境中执行）。

如需变更字段或新增业务信息，请同步修改下方 `Invoice` / `LineItem` 定义。
\"\"\"

from __future__ import annotations

import os
from typing import List

from openai import OpenAI
from pydantic import BaseModel, Field
from dotenv import load_dotenv


class LineItem(BaseModel):
    \"\"\"单条发票行项目。\"\"\"

    description: str = Field(..., description=\"商品或服务描述\")
    quantity: int = Field(..., description=\"数量\")
    unit_price: float = Field(..., description=\"单价，单位：元\")
    total_price: float = Field(..., description=\"本行金额，单位：元\")


class Invoice(BaseModel):
    \"\"\"发票信息的结构化表示，包含多个行项目。\"\"\"

    invoice_number: str = Field(..., description=\"发票号码\")
    invoice_date: str = Field(..., description=\"开票日期，格式 YYYY-MM-DD\")
    seller_name: str = Field(..., description=\"销方名称\")
    buyer_name: str = Field(..., description=\"购方名称\")
    items: List[LineItem] = Field(default_factory=list, description=\"行项目列表\")
    subtotal: float = Field(..., description=\"小计金额（不含税）\")
    tax: float = Field(..., description=\"税额\")
    total: float = Field(..., description=\"价税合计\")
    currency: str = Field(..., description=\"币种 (例如 CNY)\")

    # 递归模型设置（虽然此处 LineItem 非递归 Invoice，但保持与官方示例一致的写法）
    # Pydantic v2 中，如果模型自身递归（例如 Component 包含 List[Component]）
    # 则 model_config = {\"recursive\": True} 是需要的。
    # 对于 Invoice 包含 List[LineItem] 这种非自身递归的嵌套，此标记不是必需的，
    # 但加上也无害，且能处理更复杂的递归场景。
    # 对于 Invoice 包含 List[LineItem]，`LineItem.model_rebuild()` 和 `Invoice.model_rebuild()`
    # 也并非严格必要，因为类型已完全定义。但若存在复杂的向前引用或动态修改，则 rebuild 有用。
    # 此处保留 model_rebuild() 作为良好实践，特别是在复杂 schema 或动态生成 schema 时。
    model_config = {\"recursive\": True} 

Invoice.model_rebuild()  # 确保 Pydantic 模型构建完成，特别是涉及 ForwardRefs 时
LineItem.model_rebuild() # 虽然简单，也加上以保持一致性


# ---------- 读取 .env ----------
load_dotenv()  # 在当前目录自动加载 .env 文件中的环境变量


# ---------- 调用 OpenAI 接口 ----------
client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY"),  # 令牌由用户自行配置
    base_url=os.getenv("OPENAI_BASE_URL"),  # 如官方地址可留空
)

completion = client.beta.chat.completions.parse(
    model="gpt-4o-mini",  # gpt-4o / gpt-4o-mini 均可
    messages=[
        {
            "role": "system",
            "content": (
                \"你是一名资深财务助手。请严格依据给定 JSON Schema 生成发票信息，\"
                \"不要输出任何与 Schema 不匹配的内容。\"
            ),
        },
        {
            "role": "user",
            "content": (
                \"请为以下交易生成一张示例发票：\\n\"
                \"销方：上海例子科技有限公司\\n\"
                \"购方：北京示例采购中心\\n\"
                \"行项目：\\n\"
                \"1. SaaS 订阅费，数量 1，单价 1000 元；\\n\"
                \"2. 咨询服务，数量 2，单价 500 元；\\n\"
                \"3. 技术支持，数量 3，单价 200 元；\\n\"
                \"税率为 13%。\"
            ),
        },
    ],
    response_format=Invoice,  # ◎ 关键：让 SDK 严格校验 Schema 并自动解析
    temperature=0.1,
)

msg = completion.choices[0].message

# ---------- 输出 ----------
if msg.parsed:
    invoice: Invoice = msg.parsed
    # ensure_ascii=False 在 model_dump_json 中是默认行为，indent=2 便于阅读
    print(\"--- 解析后的发票对象 ---\")
    print(invoice.model_dump_json(indent=2)) 
elif msg.refusal:
    print(\"--- 模型拒绝或返回格式不符 ---\")
    print(msg.refusal)
else:
    print(\"--- 未知错误 ---\")
    print(\"未能解析消息，且没有明确的拒绝信息。\")
```

### 关键点拆解

| 步骤                                     | Why (原理)                                                                                                |
| ---------------------------------------- | ------------------------------------------------------------------------------------------------------- |
| **Pydantic `Invoice` / `LineItem` 模型** | 定义清晰的数据结构，作为与 OpenAI API 沟通的契约。SDK 会将其转换为 JSON Schema。                               |
| **`response_format=Invoice`**            | SDK ≥ 1.26.0 的核心功能：自动将 Pydantic 模型转为 JSON Schema 发给 API，并要求 API 严格按此 Schema 返回。返回的 JSON 会被自动反序列化为 `Invoice` Pydantic 对象。若模型拒绝或返回格式不符，`msg.refusal` 会有提示。 |
| **`temperature=0.1`**                    | 对于结构化数据提取，通常希望结果更具确定性，较低的温度有助于此。                                                              |
| **`load_dotenv()`**                      | 从 `.env` 文件加载环境变量（如 `OPENAI_API_KEY`），避免硬编码敏感信息。                                       |
| **`invoice.model_dump_json(indent=2)`**  | Pydantic V2 推荐的序列化为 JSON 字符串的方法，`indent=2` 用于美化输出。                                     |

### 运行示例（终端）

首先，确保你的项目根目录下有一个 `.env` 文件，内容类似：
```env
OPENAI_API_KEY="sk-YOUR_API_KEY_HERE"
# 如果使用自定义 OpenAI 兼容 API 端点，请取消注释并修改下一行
# OPENAI_BASE_URL="https://your-openai-compatible-api-endpoint/v1"
```

然后，在你的虚拟环境中执行：
```bash
# 激活虚拟环境 (例如：source .venv/bin/activate)
# 安装依赖 (如果还没装):
# pip install --upgrade openai pydantic python-dotenv

python test_structured_invoice.py
```

若一切顺利，将看到类似的发票 JSON 数据：

```json
{
  "invoice_number": "INV-20231001",
  "invoice_date": "2023-10-01",
  "seller_name": "上海例子科技有限公司",
  "buyer_name": "北京示例采购中心",
  "items": [
    {
      "description": "SaaS 订阅费",
      "quantity": 1,
      "unit_price": 1000.0,
      "total_price": 1000.0
    },
    {
      "description": "咨询服务",
      "quantity": 2,
      "unit_price": 500.0,
      "total_price": 1000.0
    },
    {
      "description": "技术支持",
      "quantity": 3,
      "unit_price": 200.0,
      "total_price": 600.0
    }
  ],
  "subtotal": 2600.0,
  "tax": 338.0,
  "total": 2938.0,
  "currency": "CNY"
}
```

此输出已 **100 %** 符合我们用 Pydantic 定义的 `Invoice` Schema，可以直接用于后续的程序处理。

[1]: https://openai.com/index/introducing-structured-outputs-in-the-api/ "Introducing Structured Outputs in the API | OpenAI"
