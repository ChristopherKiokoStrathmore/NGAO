"""Client for the USSD-to-backend contract (docs/API_CONTRACT.md §5).

Every call is bounded by BACKEND_TIMEOUT_S so the reply to Wasiliana still
goes out inside its ~10 second window. Any failure raises BackendError, which
the menu turns into an END screen in the subscriber's language.
"""

import logging
import os

import requests

log = logging.getLogger(__name__)


class BackendError(RuntimeError):
    pass


class BackendClient:
    def __init__(self, base_url: str, token: str, timeout: float = 4.0, session=None):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.http = session or requests.Session()
        self.http.headers.update({"Authorization": f"Bearer {token}"})

    @classmethod
    def from_env(cls) -> "BackendClient":
        return cls(
            base_url=os.environ["BACKEND_BASE_URL"],
            token=os.environ["USSD_SERVICE_TOKEN"],
            timeout=float(os.getenv("BACKEND_TIMEOUT_S", "4")),
        )

    def _call(self, method: str, path: str, **kwargs) -> dict:
        url = f"{self.base_url}{path}"
        try:
            resp = self.http.request(method, url, timeout=self.timeout, **kwargs)
        except requests.RequestException as exc:
            log.error("%s %s failed: %s", method, path, exc)
            raise BackendError(str(exc)) from exc
        if resp.status_code >= 400:
            try:
                err = resp.json().get("error", {})
            except ValueError:
                err = {}
            log.error("%s %s -> %s %s (request_id=%s)", method, path, resp.status_code,
                      err.get("code"), err.get("request_id"))
            raise BackendError(f"{resp.status_code} {err.get('code', '')}".strip())
        try:
            return resp.json() if resp.content else {}
        except ValueError as exc:
            raise BackendError("backend returned non-JSON") from exc

    def set_language(self, phone: str, lang: str) -> dict:
        return self._call("POST", "/ussd/language", json={"phone": phone, "preferred_lang": lang})

    def register(self, phone: str, ward_id: int, role: str, lang: str, consent: bool) -> dict:
        return self._call("POST", "/ussd/register", json={
            "phone": phone, "ward_id": ward_id, "role": role,
            "preferred_lang": lang, "consent": consent,
        })

    def report(self, phone: str, session_id: str, report_type: str,
               count: int | None, unit: str | None) -> dict:
        return self._call("POST", "/ussd/report", json={
            "phone": phone, "session_id": session_id, "report_type": report_type,
            "count": count, "unit": unit,
        })

    def ward_status(self, phone: str) -> str:
        return self._call("GET", "/ussd/ward-status", params={"phone": phone}).get("text", "")

    def unsubscribe(self, phone: str) -> dict:
        return self._call("POST", "/ussd/unsubscribe", json={"phone": phone})


class DevBackend:
    """Stand-in for local runs before the real §5 endpoints exist. Logs every call."""

    def __init__(self):
        self.calls: list[tuple[str, dict]] = []
        self.status_text = {"sw": "Kata yako: hakuna alama ya hatari leo.",
                            "en": "Your ward: no risk score today."}
        self.langs: dict[str, str] = {}

    def _log(self, name: str, **kw):
        self.calls.append((name, kw))
        log.info("DevBackend %s %s", name, kw)

    def set_language(self, phone, lang):
        self.langs[phone] = lang
        self._log("language", phone=phone, preferred_lang=lang)
        return {"preferred_lang": lang}

    def register(self, phone, ward_id, role, lang, consent):
        self._log("register", phone=phone, ward_id=ward_id, role=role,
                  preferred_lang=lang, consent=consent)
        return {"subscriber_id": 1, "status": "ACTIVE"}

    def report(self, phone, session_id, report_type, count, unit):
        self._log("report", phone=phone, session_id=session_id,
                  report_type=report_type, count=count, unit=unit)
        return {"report_id": 1}

    def ward_status(self, phone):
        self._log("ward-status", phone=phone)
        return self.status_text[self.langs.get(phone, "sw")]

    def unsubscribe(self, phone):
        self._log("unsubscribe", phone=phone)
        return {"status": "STOPPED"}
