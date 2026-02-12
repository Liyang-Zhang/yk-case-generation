"""Tencent OCR client wrapper for GeneralAccurateOCR."""
from __future__ import annotations
import base64
import json
from typing import Any, Dict

from tencentcloud.common import credential
from tencentcloud.common.profile.http_profile import HttpProfile
from tencentcloud.common.profile.client_profile import ClientProfile
from tencentcloud.ocr.v20181119 import ocr_client, models

from yk_case_generation.config import settings


class TencentOCRClient:
    def __init__(self, secret_id: str | None = None, secret_key: str | None = None, region: str | None = None, endpoint: str | None = None):
        self.secret_id = secret_id or settings.tencent_secret_id
        self.secret_key = secret_key or settings.tencent_secret_key
        self.region = region or settings.tencent_region
        self.endpoint = endpoint or settings.tencent_ocr_endpoint
        if not self.secret_id or not self.secret_key:
            raise ValueError("Tencent OCR credentials not configured")

        cred = credential.Credential(self.secret_id, self.secret_key)
        http_profile = HttpProfile()
        http_profile.endpoint = self.endpoint
        client_profile = ClientProfile()
        client_profile.httpProfile = http_profile
        self.client = ocr_client.OcrClient(cred, self.region, client_profile)

    def general_accurate_image(self, image_bytes: bytes) -> Dict[str, Any]:
        req = models.GeneralAccurateOCRRequest()
        b64 = base64.b64encode(image_bytes).decode("utf-8")
        params = {
            "ImageBase64": b64,
        }
        req.from_json_string(json.dumps(params))
        resp = self.client.GeneralAccurateOCR(req)
        return json.loads(resp.to_json_string())
