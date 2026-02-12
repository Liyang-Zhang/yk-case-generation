# yk-case-generation Pipeline Overview

本文档梳理当前项目从项目号到结构化病例输出的完整流程，方便后续迭代和对齐。

## 1. 目标与输入输出

- 目标：针对每个 `projectNumber` 产出一份可追溯的结构化病例 JSON。
- 输入（逻辑上）：
  - 3 个 LIMS 文本源：`salesNotes`、`otherInfo`、`communicationInformation`
  - 2 个附件字段：`inspectionOrderAttachment`、`diagnosticReportAttachments`
- 当前附件主流程支持：`docx/pdf/png/jpg/jpeg`（压缩包会先解压，解压后按文件类型继续处理）。
- 关键中间产物：
  - `raw/*.json`：LIMS 原始字段
  - `ocr_inputs/*.jpg`：OCR 预处理输入图
  - `ocr_results/*.json`：OCR 原始响应
  - `outputs/*_normalized_ir.json`：统一 IR
  - `outputs/cases*_/*_case.json`：病例输出

## 2. 端到端流程

### Step A. 拉取项目与附件

- 脚本：`scripts/fetch_projects.py`
- 功能：
  - 调用 `https://newlims-api.yikongenomics.cn/RD/getProjectInfo?projectNumber=...`
  - 保存 5 个信息字段到 `data/devset/raw/<project>.json`
  - 下载附件并保留原始文件名到 `data/devset/attachments/<project>/`
  - 自动解压 `zip/tar/gz/bz2/rar/7z`

### Step B. 附件预处理到 OCR 输入

- 脚本：`scripts/prep_ocr_inputs.py`
- 核心服务：`src/yk_case_generation/services/attachment_processing.py`
- 功能：
  - `docx -> pdf -> page images`
  - `pdf -> page images`
  - `image -> direct preprocess`
  - 对每页做图像增强和体积控制，输出 JPEG 到 `ocr_inputs`

### Step C. OCR 调用

- 脚本：`scripts/run_ocr_inputs.py`
- 核心服务：
  - `src/yk_case_generation/services/ocr_runner.py`
  - `src/yk_case_generation/services/ocr_clients/tencent.py`
- 功能：
  - 调腾讯 GeneralAccurateOCR
  - 保存每张图的原始 OCR JSON 到 `ocr_results`

### Step D. OCR + LIMS 组装为 IR

- 脚本：`scripts/ocr_to_ir.py`
- 核心服务：`src/yk_case_generation/services/ir_builder.py`
- 功能：
  - 合并 3 个 LIMS 文本 + OCR 行结果到 `DocumentIR`
  - 行级信息包含：`text/confidence/bbox/polygon/parag_no/flags`
  - 标注关键 flags：`low_confidence`、`boilerplate`、`form_template`、`checkbox_state`
  - 输出 `outputs/<project>_normalized_ir.json`

### Step E. IR -> Case 生成

- 脚本：`scripts/build_case_from_ir.py`
- 核心服务：`src/yk_case_generation/services/case_builder.py`
- 模式：
  - 默认 `llm`（需配置 OpenAI-compatible endpoint）
  - `rule` 仅兜底
- LLM 两阶段：
  - Stage1：候选事实筛选（`prompts/case_stage1_zh.md`）
  - Stage2：按 schema 组装最终病例（`prompts/case_stage2_zh.md`）
- 输出：`outputs/cases*/<project>_case.json`

### Step F. Case -> Frontend Response

- 脚本：`scripts/build_case_response.py`
- 核心服务：`src/yk_case_generation/services/case_response_builder.py`
- 作用：
  - 将内部 `case.json` 转换成前端消费契约（DTO）
  - 保留证据引用（`source_id/page/line_id/quote`）用于前端“查看原文”
  - 新增 `status`（ok/partial/failed）和 `summary`（业务可读）
- 输出：`outputs/cases_frontend/*_frontend.json`

## 3. CLI 入口

- 文件：`src/yk_case_generation/cli/__main__.py`
- 命令：
  - `ykcg project-run`：主命令，输入项目号跑完整链路
  - `ykcg project-run-batch`：批量命令，CSV 输入项目号批量执行
  - `ykcg inspect-run`：调试命令，查看 `run_meta` 失败步骤
  - `ykcg build-response`：调试命令，从 `case.json` 生成前端 JSON

## 4. 当前字段/策略（业务向）

- LIMS 文本优先级高于附件 OCR 文本。
- 已做防误提取：
  - 未勾选模板项不作为患者事实
  - 检测项目/套餐类信息尽量过滤，避免污染病例
  - OCR 将方框识别成 `口/日/曰/□` 的情况也作为未勾选信号处理
- 业务目标聚焦：病例相关内容（症状、病史、家族史、诊断）而不是检测套餐信息。

## 5. 环境与配置

- 环境：`env/environment.yml`（micromamba）
- 容器：`docker/Dockerfile`
- OCR 相关环境变量：
  - `TENCENT_SECRET_ID`
  - `TENCENT_SECRET_KEY`
  - 可选：`TENCENT_REGION`, `TENCENT_OCR_ENDPOINT`
- LLM 相关环境变量：
  - `LLM_ENDPOINT`
  - `LLM_API_KEY`
  - `LLM_MODEL`
  - 可选：`LLM_MODE`（默认 `llm`）

## 6. 常用命令（开发集）

```bash
# 1) 拉取项目与附件
micromamba run -n yk-case-generation python scripts/fetch_projects.py \
  --csv data/samples/dev_projects.csv --out data/devset

# 2) 生成 OCR 输入图
micromamba run -n yk-case-generation python scripts/prep_ocr_inputs.py \
  --attachments data/devset/attachments --out data/devset/ocr_inputs

# 3) 执行 OCR
micromamba run -n yk-case-generation python scripts/run_ocr_inputs.py \
  --images data/devset/ocr_inputs --out data/devset/ocr_results

# 4) 生成 normalized IR
micromamba run -n yk-case-generation python scripts/ocr_to_ir.py \
  --raw-dir data/devset/raw \
  --ocr-results data/devset/ocr_results \
  --ocr-inputs data/devset/ocr_inputs \
  --out outputs

# 5) IR 生成病例
micromamba run -n yk-case-generation python scripts/build_case_from_ir.py \
  --ir outputs --out outputs/cases_llm --mode llm

# 6) 生成前端响应 JSON
micromamba run -n yk-case-generation python scripts/build_case_response.py \
  --case outputs/cases_llm --out outputs/cases_frontend

# 7) 一键跑通（输入项目号，输出frontend json）
micromamba run -n yk-case-generation ykcg project-run <PROJECT_ID> \
  --output-dir runs --mode llm

# 8) 批量跑开发集
micromamba run -n yk-case-generation ykcg project-run-batch \
  data/samples/dev_projects.csv --output-dir runs --mode llm
```

## 7. 当前关注点（下一步）

- 继续提升“病例相关信息”召回（主诉/诊断/计划）并保持高精度。
- 进一步约束 tests_and_exams 只保留“检测结果”，不保留“检测项目/套餐”。
- 统一 schema 与 prompt 的字段定义，避免迭代中字段漂移。
- TODO（评估）：当前开发集缺少 gold case 标注，先持续推进工程开发，后续补标注集用于量化评估（Precision/Recall/F1）。
- 工具化：`project-run` 已打通，后续可增加批量模式（CSV输入）和可配置重试策略。
