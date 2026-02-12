# Pipeline Status (as of 2026-01-27)

## Done
- Project fetch & attachments
  - `scripts/fetch_projects.py` pulls LIMS fields + downloads attachments; preserves filenames; auto-prefixes missing protocol; unpacks zip/tar/gz/bz2/rar/7z. Errors recorded per file.
- Font/render setup
  - LibreOffice headless + CJK fonts + poppler; Dockerfile includes `libreoffice-writer`, `fonts-noto-cjk`, `fonts-wqy-*`, `poppler-utils`, `unrar-free`, `p7zip-full`.
- Attachment preprocessing
  - Supports docx/pdf/png/jpg. Docx → PDF (libreoffice) → page images; PDF → page images (pdf2image/poppler); images preprocessed (resize ≤2048px, <5MB, contrast boost) → JPEG.
  - Script: `scripts/prep_ocr_inputs.py --attachments data/devset/attachments --out data/devset/ocr_inputs`.
- OCR
  - Tencent GeneralAccurateOCR wired via SDK. Client in `services/ocr_clients/tencent.py`; runner `services/ocr_runner.py`; batch script `scripts/run_ocr_inputs.py --images ... --out data/devset/ocr_results`.
  - Devset (20 projects) OCR results stored in `data/devset/ocr_results/*.json`.
- OCR → IR
  - Added normalizer: parse OCR JSON (top-level or Response) into Page/Line with bbox/confidence/checkbox/low_confidence, parag_no.
  - Aggregation: `ir_builder.build_ir_for_project` merges LIMS texts + OCR sources, boilerplate marking via hash; output `DocumentIR`.
  - Added template-safety flags in IR: `form_template`, `checkbox_option`, `checkbox_state` (`checked/unchecked`) to avoid treating unselected template items as patient facts.
  - CLI: `scripts/ocr_to_ir.py --raw-dir data/devset/raw --ocr-results data/devset/ocr_results --ocr-inputs data/devset/ocr_inputs --out outputs [--project ...]`.
- Case builder MVP
  - Implemented `generate_case` with default `llm` mode (OpenAI-compatible, required env: LLM_ENDPOINT, LLM_API_KEY, LLM_MODEL) and explicit `rule` fallback.
  - Added schema validation (`jsonschema`) and safeguards to prevent unchecked template options from entering diagnosis.
  - Added CLI: `scripts/build_case_from_ir.py --ir outputs --out outputs/cases --mode llm|rule`.
  - Source type expanded to include `ocr_attachment`.
- Data samples
  - Cleaned project numbers: `data/samples/clean_project_numbers.xlsx`.
  - Devset list: `data/samples/dev_projects.csv` (20 ids from 25GDT/25IFGS head/tail).
  - Raw fetch & attachments and OCR inputs/results regenerated.
- README updated with fetch/preprocess/OCR steps; env includes pdf2image, tencentcloud SDK, pydantic-settings.

## Todo
- OCR → IR
  - Improve boilerplate heuristics; handle missing page inference if ocr_results flattened differently.
- End-to-end CLI
  - One-shot from project_number: fetch → attachments → preprocess → OCR → IR.
- Case builder
  - LLM prompt + schema validation; evidence refs (`source_id/page/line_id/quote`), negation handling; retry on JSON fail.
- De-dup/quality
  - Hash-based boilerplate marking; optional hash cache to skip re-OCR identical files.
- Optional
  - Add rar/7z stronger handling (password detect); improve image preprocessing (binarization toggle, hash dedup of duplicated attachments).

## Credentials
- OCR: uses env vars `TENCENT_SECRET_ID`, `TENCENT_SECRET_KEY`, optional `TENCENT_REGION`, `TENCENT_OCR_ENDPOINT`.

## Key paths
- Data: `data/devset/attachments`, `data/devset/ocr_inputs`, `data/devset/ocr_results`.
- Scripts: `scripts/fetch_projects.py`, `scripts/prep_ocr_inputs.py`, `scripts/run_ocr_inputs.py`.
- Services: `services/attachment_processing.py`, `image_preprocess.py`, `pdf_render.py`, `docx_render.py`, `ocr_clients/tencent.py`, `ocr_runner.py`.
