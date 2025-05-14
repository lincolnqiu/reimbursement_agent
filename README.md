# 发票批量处理 / 报销辅助工具 🧾✨

> **开发说明**：本项目完全Cursor-friendly: 重大改变都保存了contexts/，且每个文件头上都有说明。

## 目录简介

| 目录/文件         | 作用 |
|-------------------|------|
| `src/`            | 主要源码目录，包含业务逻辑模块 |
| `input/`          | 待处理的 PDF 发票文件放置处 (运行时自动创建) |
| `output/`         | 处理完毕的文件与 JSON 汇总 (运行时自动创建) |
| `trip_sheets/`    | 行程单（如滴滴出行）解析后存放的 PDF 与 JSON |
| `duplicates/`     | 检测到重复发票后存放的 PDF |
| `.gitignore`      | Git 忽略规则 |
| `README.md`       | 项目说明文件 (当前文件) |

## 功能亮点

1. **📄 PDF 发票解析**：优先使用 `pdfplumber` 抽取关键信息，若信息不全则回退到 LLM OCR (需配置 OpenAI API Key)。
2. **🔍 重复发票检测**：按发票号码去重，将重复文件统一移动到 `duplicates/` 目录。
3. **📝 自动重命名**：将原始文件统一重命名为 UUID，后续流程避免冲突。
4. **🚕 行程单识别与解析**：自动检测交通行程单 (滴滴 / 高德等)，解析表格后生成 JSON 并与对应发票关联。
5. **📦 JSON 汇总报表**：所有发票信息最终写入 `output/invoice_data.json`，便于系统对接或调试。
6. **🛠️ 分阶段运行**：`--stage` 参数支持 `pdfplumber / llm / rename / json`，方便开发调试。

## 快速开始 🚀

### 1. 克隆仓库
```bash
git clone <your-repo-url> && cd reimbursement_agent
```

### 2. 创建并激活虚拟环境 (推荐 venv)
```bash
python -m venv venv
# macOS / Linux
source venv/bin/activate
# Windows (PowerShell)
# .\venv\Scripts\Activate.ps1
```

### 3. 安装依赖
```bash
pip install -r requirements.txt
```
> 📌 如需额外使用 Node 包，请改用 `yarn` 而非 `npm` (参见自定义规范)。

### 4. 准备输入
- 将需处理的 **PDF 发票** 放入 `input/` 目录。（首次运行脚本会自动创建目录）

### 5. 运行脚本
```bash
# 完整流程 (默认)
python src/main.py

# 或者分阶段调试，例如仅解析文本：
python src/main.py --stage pdfplumber
```
运行完成后，可在 `output/` 查看：
- 解析后的 PDF (`*.pdf`)
- 汇总 JSON (`invoice_data.json`)
- 行程单 JSON (`*.json`，与行程单 PDF 同名)

## 环境变量 & 配置

| 变量                | 说明 |
|---------------------|------|
| `OPENAI_API_KEY`    | 使用 LLM OCR 时需填写的 OpenAI Key |
| `OPENAI_BASE_URL`   | （可选）自定义 OpenAI 代理地址 |

其他常量（目录、Excel 路径、正则等）可在 `src/config.py` 中调整。

## 贡献指南 🤝
1. **新功能**：请先提 Issue 说明需求，再提 PR。 
2. **代码风格**：遵循 PEP 8，文件头需包含中文描述性注释 (见现有文件示例)。
3. **提交信息**：建议使用简洁的中文描述，必要时加入 emoji。

## 未来计划 📅
- [ ] 支持更多发票类型解析 (如机打发票)。
- [ ] 提供 Web 界面上传与进度查看。
- [ ] 单元测试覆盖率 > 80%。

---

> 若在使用过程中遇到问题，欢迎提 Issue 或联系维护者。祝报销顺利！🎉 