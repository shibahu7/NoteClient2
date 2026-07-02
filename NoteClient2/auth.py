from __future__ import annotations

import os
import json
from datetime import datetime
from time import sleep
from typing import Any, Dict, Optional

from playwright.sync_api import Playwright, sync_playwright, expect

from .http import HttpClient

class AuthManager:
    def __init__(self, email: str, password: str, session_file: str, headers: Dict[str, str]):
        self.email = email
        self.password = password
        self.session_file = session_file
        self.headers = dict(headers)
        self.cookies: Dict[str, str] = {}

    def load_session(self) -> Dict[str, Any]:
        if not os.path.exists(self.session_file):
            return {"ok": False, "error": {"type": "SessionNotFound", "message": "session file not found"}}
        try:
            with open(self.session_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            return {"ok": True, "data": data}
        except Exception as e:
            return {"ok": False, "error": {"type": type(e).__name__, "message": str(e)}}

    def save_session(self) -> Dict[str, Any]:
        try:
            data = {"timestamp": datetime.now().isoformat(), "cookies": self.cookies}
            with open(self.session_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            return {"ok": True, "data": {"path": self.session_file}}
        except Exception as e:
            return {"ok": False, "error": {"type": type(e).__name__, "message": str(e)}}

    def validate_session(self, http: HttpClient) -> Dict[str, Any]:
        if not self.cookies:
            return {"ok": False, "error": {"type": "NoCookies", "message": "cookies not set"}}
        url = "https://note.com/api/v3/users/user_features"
        resp = http.get(url)
        if resp.get("ok"):
            return {"ok": True}
        return {
            "ok": False,
            "error": {
                "type": "SessionInvalid",
                "message": "session invalid",
                "status_code": resp.get("status_code"),
                "detail": resp.get("text"),
            },
        }

    def prepare(self, http: HttpClient) -> Dict[str, Any]:
        # 1) session.json があれば使う
        session = self.load_session()
        if session.get("ok"):
            data = session["data"]
            cookies = data.get("cookies") or {}
            self.cookies = cookies
            http.set_cookies(self.cookies)

            valid = self.validate_session(http)
            if valid.get("ok"):
                return {"ok": True, "data": {"auth": "session"}}

            # 期限などの情報を返す（ログ出しせず、戻り値へ）
            ts = data.get("timestamp")
            hours = None
            if ts:
                try:
                    saved_time = datetime.fromisoformat(ts)
                    hours = (datetime.now() - saved_time).total_seconds() / 3600
                except Exception:
                    hours = None

            # セッション無効なら再ログインへ
            relogin = self._get_cookies()
            if not relogin.get("ok"):
                relogin["error"]["session_hours"] = hours
                return relogin

            http.set_cookies(self.cookies)
            self.save_session()
            return {"ok": True, "data": {"auth": "relogin", "session_hours": hours}}

        # 2) session が無い / 読めない -> ログイン
        relogin = self._get_cookies()
        if not relogin.get("ok"):
            return relogin

        http.set_cookies(self.cookies)
        self.save_session()
        return {"ok": True, "data": {"auth": "login"}}

    def _login(self, playwright: Playwright, email_username: str, password: str) -> Any:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()

        page.goto("https://note.com/login?redirectPath=https%3A%2F%2Fnote.com%2F")
        page.wait_for_load_state("domcontentloaded")
        sleep(2)

        email_box = page.get_by_role("textbox", name="mail@example.com or note ID")
        email_box.click()
        email_box.fill(email_username)

        try:
            expect(email_box).to_have_value(email_username, timeout=3000)
        except Exception:
            email_box.fill("")
            email_box.fill(email_username)
            try:
                expect(email_box).to_have_value(email_username)
            except Exception:
                pass

        password_box = page.get_by_role("textbox", name="パスワード")
        password_box.click()
        password_box.fill(password)

        page.get_by_role("button", name="ログイン").click()
        page.wait_for_load_state("networkidle")

        # note_gql_auth_token は networkidle 後に少し遅れて発行されるため、
        # 発行を待たずに cookies() を取得すると API 認証に必要な cookie が
        # 欠落し、以後の全リクエストが not_login エラーになる。
        for _ in range(20):
            cookies = context.cookies()
            if any(c["name"] == "note_gql_auth_token" for c in cookies):
                break
            sleep(0.5)
        else:
            cookies = context.cookies()

        page.close()
        context.close()
        browser.close()

        return cookies

    def _get_cookies(self) -> Dict[str, Any]:
        try:
            with sync_playwright() as playwright:
                raw = self._login(playwright, self.email, self.password)
                self.cookies = {c["name"]: c["value"] for c in raw}
            return {"ok": True, "data": {"cookies": list(self.cookies.keys())}}
        except Exception as e:
            return {"ok": False, "error": {"type": type(e).__name__, "message": str(e), "where": "playwright_login"}}
