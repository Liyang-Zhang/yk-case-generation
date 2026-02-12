# yk-case-generation

本项目是一个面向 CLI 的病例生成工具：输入 LIMS 项目号，自动拉取 5 个信息源（3 个文本 + 2 个附件），完成 OCR、结构化整合，并输出可追溯病例 JSON 与前端展示 JSON。

## 1. 快速开始

1. 创建环境  
`micromamba env create -f env/environment.yml`

2. 配置密钥  
`cp .env.example .env`，并填写真实配置（见下方“配置说明”）

3. 运行单项目全流程（推荐主命令）  
`micromamba run -n yk-case-generation ykcg project-run <PROJECT_ID> --output-dir runs --mode llm`

4. 批量运行（CSV）  
`micromamba run -n yk-case-generation ykcg project-run-batch data/samples/dev_projects.csv --output-dir runs --mode llm`

5. 调试命令  
- 查看单项目运行状态：  
`micromamba run -n yk-case-generation ykcg inspect-run <PROJECT_ID> --output-dir runs`
- 从内部病例 JSON 生成前端 JSON：  
`micromamba run -n yk-case-generation ykcg build-response <path/to/_case.json>`

## 2. 配置说明（.env）

项目通过 `pydantic-settings` 读取配置，支持 `.env`。  
优先级：**系统环境变量 > `.env`**。

推荐做法：
1. `cp .env.example .env`
2. 填写：
   - `TENCENT_SECRET_ID`
   - `TENCENT_SECRET_KEY`
   - `LLM_ENDPOINT`
   - `LLM_API_KEY`
   - `LLM_MODEL`
3. 直接执行命令，无需每次 `export`

## 3. 一键流水线输出

执行 `project-run` 后，会在 `runs/<PROJECT_ID>/` 生成：

- `raw/<PROJECT_ID>.json`：LIMS 原始字段
- `attachments/`：下载附件与解压文件
- `ocr_inputs/<PROJECT_ID>/`：OCR 输入图片
- `ocr_results/`：OCR 原始结果
- `<PROJECT_ID>_normalized_ir.json`：统一中间表示
- `cases/<PROJECT_ID>_case.json`：内部结构化病例（可追溯）
- `frontend/<PROJECT_ID>_frontend.json`：前端展示 JSON
- `run_meta.json`：每个步骤的状态、耗时、错误信息

## 4. 数据模型

- 内部病例 Schema：`src/yk_case_generation/schemas/case_schema_v1.json`
- 前端响应 Schema：`src/yk_case_generation/schemas/case_response_v1.json`

前端响应包含：
- `status`：`ok / partial / failed`
- `summary`：摘要
- `narrative`：完整病例段落
- `sections`：结构化分栏（含 evidence）
- `quality`：告警与缺失项

## 5. OCR 与附件处理

- 支持附件：`docx/pdf/png/jpg/jpeg`
- 压缩包自动解压：`zip/tar/gz/bz2/rar/7z`
- `docx -> pdf -> 图片`，`pdf -> 图片`，图片统一预处理后再 OCR

腾讯 OCR 凭据必需：
- `TENCENT_SECRET_ID`
- `TENCENT_SECRET_KEY`

## 6. LLM 生成

- 默认模式：`llm`
- 采用两阶段：
  1. Stage1：候选事实筛选（保留证据）
  2. Stage2：按 schema 生成病例 JSON
- 若结构不合法，触发一次“仅修结构不改事实”修复调用

## 7. 常见问题

1. `status=failed` 但流程命令成功？
- 命令成功表示工程流程跑完；`status` 是病例内容可用性判断。
- 请查看 `frontend.json` 与 `run_meta.json` 具体原因。

2. 运行失败怎么定位？
- 优先看 `runs/<PROJECT_ID>/run_meta.json` 的 `steps` 与 `error`。

3. 中文 PDF 转换乱码？
- 需安装 CJK 字体（Dockerfile 已内置）。

## 8. 相关文档

- 流程总览：`docs/PIPELINE_OVERVIEW.md`
- 详细实现：`docs/IMPLEMENTATION_DETAILED.md`
- 技术汇报：`docs/REPORT_TECHNICAL.md`
- 管理汇报：`docs/REPORT_EXECUTIVE.md`
