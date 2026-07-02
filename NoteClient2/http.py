from __future__ import annotations
import requests
from typing import Any, Dict, Optional

class HttpClient:
    def __init__(self, base_headers: Dict[str, str], cookies: Dict[str, str]):
        self.base_headers = dict(base_headers)
        self.cookies = cookies

    def set_cookies(self, cookies: Dict[str, str]) -> None:
        self.cookies = cookies

    def get(self, url: str, headers: Optional[Dict[str, str]] = None, **kwargs) -> Dict[str, Any]:
        try:
            resp = requests.get(url, headers={**self.base_headers, **(headers or {})}, cookies=self.cookies, **kwargs)
            return {
                "ok": resp.status_code == 200,
                "status_code": resp.status_code,
                "text": resp.text,
                "json": self._safe_json(resp),
            }
        except Exception as e:
            return {"ok": False, "error": {"type": type(e).__name__, "message": str(e), "where": "GET", "url": url}}

    def post(self, url: str, headers: Optional[Dict[str, str]] = None, **kwargs) -> Dict[str, Any]:
        try:
            resp = requests.post(url, headers={**self.base_headers, **(headers or {})}, cookies=self.cookies, **kwargs)
            # S3 の presigned POST は成功時に 204 No Content を返す仕様のため、
            # 200/201 のみを成功扱いにすると画像アップロードが常に失敗してしまう。
            ok = resp.status_code in (200, 201, 204)
            return {
                "ok": ok,
                "status_code": resp.status_code,
                "text": resp.text,
                "json": self._safe_json(resp),
            }
        except Exception as e:
            return {"ok": False, "error": {"type": type(e).__name__, "message": str(e), "where": "POST", "url": url}}

    def put(self, url: str, headers: Optional[Dict[str, str]] = None, **kwargs) -> Dict[str, Any]:
        try:
            resp = requests.put(url, headers={**self.base_headers, **(headers or {})}, cookies=self.cookies, **kwargs)
            ok = resp.status_code in (200, 201)
            return {
                "ok": ok,
                "status_code": resp.status_code,
                "text": resp.text,
                "json": self._safe_json(resp),
            }
        except Exception as e:
            return {"ok": False, "error": {"type": type(e).__name__, "message": str(e), "where": "PUT", "url": url}}

    @staticmethod
    def _safe_json(resp: requests.Response) -> Any:
        try:
            return resp.json()
        except Exception:
            return None
        