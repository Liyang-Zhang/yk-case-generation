# yk-case-generation 详细实现文档（阶段总结）

本文档按实际执行顺序，完整记录当前项目的设计、实现与运行口径，供后续开发、交付和运维使用。

---

## 0. 项目目标与范围

### 0.1 业务目标
- 输入：LIMS 项目号（`projectNumber`），对应 5 个信息源（3 个文本字段 + 2 个附件字段）。
- 输出：一份可追溯、可给前端展示的病例 JSON。
- 核心原则：先保证“文本抓全 + 证据可追溯”，再做结构化归并；不做医疗推断。

### 0.2 当前范围（MVP）
- 支持附件格式：`docx/pdf/png/jpg/jpeg`（压缩包支持解压后继续处理）。
- OCR 使用腾讯 GeneralAccurateOCR。
- 结构化病例由 LLM（默认）生成，rule 仅兜底。
- 提供两类输出：
  - 内部输出：`case.json`（结构化+证据）
  - 前端输出：`frontend.json`（业务展示友好）

### 0.3 非目标（本阶段）
- 不做前端页面。
- 不做人工审核流程的后端状态机（仅输出状态字段）。
- 不做性能指标（无黄金标注集）。

---

## 1. 总体架构与目录

### 1.1 核心目录
- `src/yk_case_generation/services/`：核心服务模块
- `src/yk_case_generation/schemas/`：JSON schema
- `src/yk_case_generation/prompts/`：LLM prompt
- `scripts/`：批处理脚本
- `runs/`：一键流水线产物目录（按项目号分目录）
- `outputs/`：开发集离线运行产物

### 1.2 核心模型
- `DocumentIR`（`models/document_ir.py`）：统一中间表示
  - `DocumentIR -> Source[] -> Page[] -> Line[]`
  - `Line` 含 `text/confidence/polygon/bbox/parag_no/flags`

### 1.3 两层产物模型
- 内部病例 schema：`case_schema_v1.json`
- 前端响应 schema：`case_response_v1.json`

---

## 2. 端到端流程（按执行顺序）

## Step A. 拉取项目信息（LIMS）

### A.1 输入
- `projectNumber`

### A.2 实现
- 服务：`services/lims_api.py`
- 接口：`GET https://newlims-api.yikongenomics.cn/RD/getProjectInfo?projectNumber=...`
- 解析字段：
  - 文本：`salesNotes`, `otherInfo`, `communicationInformation`
  - 附件：`inspectionOrderAttachment`, `diagnosticReportAttachments`

### A.3 输出
- `runs/<pid>/raw/<pid>.json`

### A.4 失败口径
- 网络/状态码/`code!=1` 视为失败，流水线终止。

---

## Step B. 附件下载与解压

### B.1 实现
- 编排内逻辑：`services/pipeline_runner.py`
- URL 解析保留原始文件名（支持 query 中 `fileNames`）
- 自动补全无协议 URL（`DOWNLOAD_PREFIX`）

### B.2 解压策略
- stdlib：`zip/tar/gz/tgz/bz2`
- 命令行：`unrar`（rar），`7z`（7z）
- 解压目录：`<filename>_extracted/`

### B.3 输出
- `runs/<pid>/attachments/`

### B.4 失败口径
- 某个附件失败不会中断全部；整体可标记 `partial`。

---

## Step C. 附件转 OCR 输入图

### C.1 实现
- 服务：`services/attachment_processing.py`
- 子模块：
  - `docx_render.py`：docx -> pdf（libreoffice headless）
  - `pdf_render.py`：pdf -> page images（pdf2image）
  - `image_preprocess.py`：预处理（缩放、对比度增强、JPEG 压缩 <5MB）

### C.2 规则
- `docx`：先转 PDF，再逐页图片
- `pdf`：逐页图片
- 图片：直接预处理
- 不支持格式直接跳过

### C.3 输出
- `runs/<pid>/ocr_inputs/<pid>/*.jpg`

---

## Step D. OCR 识别

### D.1 实现
- 服务：`services/ocr_runner.py`
- 客户端：`services/ocr_clients/tencent.py`
- 接口：腾讯 `GeneralAccurateOCR`

### D.2 配置
- 必需：`TENCENT_SECRET_ID`, `TENCENT_SECRET_KEY`
- 可选：`TENCENT_REGION`, `TENCENT_OCR_ENDPOINT`

### D.3 输出
- `runs/<pid>/ocr_results/*.json`

### D.4 重试
- 单张图片 OCR 调用重试（tenacity）

---

## Step E. OCR + LIMS 组装为 normalized IR

### E.1 实现
- 服务：`services/ir_builder.py`
- OCR 解析：`services/ocr_normalizer.py`

### E.2 合并逻辑
- LIMS 三段文本固定作为 `lims_text_1..3`
- OCR 按 `source_id=project/attachment_stem` 聚合页

### E.3 关键标记逻辑（Line.flags）
- `low_confidence`：低置信度
- `boilerplate`：跨页重复高的模板文本
- `checkbox_option / checkbox_state`：勾选项识别
- `form_template`：模板页/模板语义

### E.4 复选框与模板保护
- 未勾选项不应作为患者事实（后续 case 阶段继续保护）
- OCR 拆分“符号行 + 文本行”时，做近邻回挂

### E.5 输出
- `runs/<pid>/<pid>_normalized_ir.json`

---

## Step F. Case Builder（内部病例）

### F.1 实现
- 主服务：`services/case_builder.py`
- 候选事实：`services/candidate_fact_builder.py`
- LLM 客户端：`services/llm_client.py`
- Prompt：
  - `prompts/case_stage1_zh.md`（候选筛选）
  - `prompts/case_stage2_zh.md`（按 schema 组装）

### F.2 模式
- 默认 `llm`（推荐）
- `rule` 明确指定时可用（兜底）

### F.3 LLM 两阶段
1. Stage1：从候选事实中筛“病例相关事实”，保留 evidence
2. Stage2：按 `case_schema_v1.json` 产出最终 case

### F.4 防误提取策略（核心）
- 未勾选项剔除（包括 OCR 方框误识别为 `口/日/曰/□`）
- 检测项目/套餐类噪声过滤，不作为病例事实
- 英文重噪句过滤（业务展示优先中文）

### F.5 当前 case 字段口径
- `patient_info`
- `chief_complaint`
- `medical_history`
- `family_history`
- `diagnosis`
- `tests_and_exams`（保留结果性信息）
- `quality`

### F.6 输出
- `runs/<pid>/cases/<pid>_case.json`

---

## Step G. Frontend Response Builder（前端输出）

### G.1 实现
- 服务：`services/case_response_builder.py`
- Schema：`schemas/case_response_v1.json`

### G.2 目标
- 给业务和前端同事直接使用：更稳定、更可读
- 保留 evidence 引用，支持“查看依据”

### G.3 字段
- `schema_version`
- `case_id`
- `status`（`ok/partial/failed`）
- `summary`
- `narrative`（新增，完整病例段落）
- `sections`（结构化事实）
- `quality`

### G.4 status 判定口径（当前）
- `failed`：
  - `chief_complaint/medical_history/diagnosis/tests_and_exams` 全空
- `ok`：
  - 有核心信息（`chief_complaint` 或 `medical_history` 或 `diagnosis`）
  - 且无 `warnings/missing_critical`
- `partial`：
  - 其余情况（包括仅有 `tests_and_exams`）

### G.5 narrative 生成策略（当前）
- 规则拼接顺序：
  - 患者信息 -> 主诉 -> 病史 -> 家族史 -> 诊断 -> 检查结果
- 段内去重、简单打分（优先临床相关句，弱化背景噪声）
- 无内容时给兜底文案

### G.6 输出
- `runs/<pid>/frontend/<pid>_frontend.json`

---

## 3. 一键工具化入口（已打通）

## 3.1 CLI 命令
- `ykcg project-run <PROJECT_ID> --output-dir runs --mode llm`

## 3.2 编排实现
- 服务：`services/pipeline_runner.py`
- 一次性串联 A->G 全步骤
- 产出步骤元信息：`run_meta.json`

## 3.3 run_meta 内容
- 项目级状态
- 每步开始/结束时间、耗时、错误
- 统计：附件数、OCR 图片数、OCR 结果数
- 关键产物路径

---

## 4. 配置与交付方式

## 4.1 配置读取
- `config.py` 使用 pydantic-settings
- 支持 `.env`（已启用）+ 系统环境变量覆盖

## 4.2 推荐交付方式
- 提供 `.env.example`
- 部署环境注入真实密钥（不入库）

## 4.3 关键环境变量
- OCR：
  - `TENCENT_SECRET_ID`
  - `TENCENT_SECRET_KEY`
  - `TENCENT_REGION`（可选）
  - `TENCENT_OCR_ENDPOINT`（可选）
- LLM：
  - `LLM_MODE`
  - `LLM_ENDPOINT`
  - `LLM_API_KEY`
  - `LLM_MODEL`
  - `LLM_TIMEOUT`

---

## 5. 当前已知问题与口径说明

1. 开发集无标准答案（gold case），当前无法做严谨性能评估。  
2. 结果质量迭代主要依赖：
   - 失败样本回看
   - 字段覆盖率
   - 噪声泄漏检查
3. `tests_and_exams` 已限制为结果导向，但仍需持续观察边界样本。
4. `narrative` 为规则拼接，可读性显著提升，但仍可继续优化语言自然度。

---

## 6. 运行建议（实操）

1. 先跑单项目：
   - `ykcg project-run <PID> --output-dir runs --mode llm`
2. 先看 `run_meta.json` 判定流程是否成功。
3. 再看 `frontend.json` 检查：
   - `status` 是否符合预期
   - `summary/narrative` 是否可读
   - `sections` 是否有证据可追溯
4. 批量跑开发集后做统计（状态分布、空字段、噪声命中）。

---

## 7. 下一阶段建议（不在本次交付中）

1. 增加批量 `project-run`（CSV 输入）官方命令。  
2. 增加自动化评估脚本（覆盖率/空样本/噪声泄漏）。  
3. 建立小规模 gold 标注集，形成回归基线。  
4. 对 `narrative` 做更细粒度句子排序与去模板化。  

