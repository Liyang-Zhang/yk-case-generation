"""Client for YK LIMS project info endpoint."""
from typing import Tuple, List
import httpx

BASE_URL = "https://newlims-api.yikongenomics.cn/RD/getProjectInfo"


class ProjectInfoError(Exception):
    pass


def fetch_project_info(project_number: str) -> dict:
    params = {"projectNumber": project_number}
    try:
        resp = httpx.get(BASE_URL, params=params, timeout=20)
    except Exception as exc:
        raise ProjectInfoError(f"request_failed: {exc}")

    if resp.status_code != 200:
        raise ProjectInfoError(f"http_status_{resp.status_code}")

    payload = resp.json()
    if not payload or payload.get("code") != 1:
        raise ProjectInfoError(f"unexpected_response: {payload}")
    return payload.get("data", {})


def project_payload_to_inputs(data: dict) -> Tuple[List[str], List[str]]:
    """Map project payload to lims_texts and attachment URLs.

    LIMS texts: salesNotes, otherInfo, communicationInformation (missing fields become "").
    Attachments: inspectionOrderAttachment and diagnosticReportAttachments (comma/semicolon split tolerated).
    """
    lims_texts = [
        data.get("salesNotes", ""),
        data.get("otherInfo", ""),
        data.get("communicationInformation", ""),
    ]

    attachments: List[str] = []
    for key in ["inspectionOrderAttachment", "diagnosticReportAttachments"]:
        val = data.get(key)
        if not val:
            continue
        # Allow multiple URLs separated by comma/semicolon
        parts = [p.strip() for p in str(val).replace(";", ",").split(",") if p.strip()]
        attachments.extend(parts)

    return lims_texts, attachments
