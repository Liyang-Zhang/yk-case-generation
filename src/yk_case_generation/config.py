from pydantic import Field
from pydantic_settings import BaseSettings
from typing import Optional

class Settings(BaseSettings):
    tencent_secret_id: Optional[str] = Field(default=None, env="TENCENT_SECRET_ID")
    tencent_secret_key: Optional[str] = Field(default=None, env="TENCENT_SECRET_KEY")
    tencent_region: str = Field(default="ap-beijing", env="TENCENT_REGION")
    tencent_ocr_endpoint: str = Field(default="ocr.tencentcloudapi.com", env="TENCENT_OCR_ENDPOINT")
    ocr_region: str = Field(default="ap-beijing")
    low_confidence_threshold: float = Field(default=0.6)
    boilerplate_repeat_threshold: int = Field(default=3)
    storage_dir: str = Field(default="outputs")
    llm_mode: str = Field(default="llm", env="LLM_MODE")
    llm_endpoint: Optional[str] = Field(default=None, env="LLM_ENDPOINT")
    llm_api_key: Optional[str] = Field(default=None, env="LLM_API_KEY")
    llm_model: str = Field(default="gpt-4o-mini", env="LLM_MODEL")
    llm_timeout: int = Field(default=120, env="LLM_TIMEOUT")

    class Config:
        env_file = ".env"

settings = Settings()
