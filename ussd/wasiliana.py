"""Wasiliana USSD request adapter.

This is the only module that knows how a Wasiliana session POST looks.

[Assumption until confirmed] The field names below follow the common Kenyan
gateway convention (sessionId, phoneNumber, serviceCode, text, with `text`
holding every input so far joined by `*`). docs.wasiliana.com did not publish the
USSD payload when this was written. Confirm against their docs or a logged live
request, then change the defaults here or override them with env vars:

    WASILIANA_FIELD_SESSION, WASILIANA_FIELD_PHONE,
    WASILIANA_FIELD_TEXT, WASILIANA_FIELD_SERVICE_CODE
    WASILIANA_TEXT_MODE = cumulative (default) | latest

Both JSON and form-encoded bodies are accepted.
"""

import json
import logging
import os
import re
from dataclasses import dataclass
from urllib.parse import parse_qs

log = logging.getLogger(__name__)

DEFAULT_FIELDS = {
    "session": ["sessionId", "session_id", "SESSION_ID"],
    "phone": ["phoneNumber", "msisdn", "phone", "MSISDN"],
    "text": ["text", "ussd_string", "input", "USSD_STRING"],
    "service_code": ["serviceCode", "service_code", "SERVICE_CODE"],
}


class BadRequest(ValueError):
    pass


@dataclass(frozen=True)
class UssdRequest:
    session_id: str
    phone: str  # E.164
    text: str   # as sent by Wasiliana (cumulative or latest input, see TEXT_MODE)
    service_code: str = ""


def text_mode() -> str:
    return os.getenv("WASILIANA_TEXT_MODE", "cumulative").strip().lower()


def _candidates(key: str) -> list[str]:
    override = os.getenv(f"WASILIANA_FIELD_{key.upper()}")
    return [override] if override else DEFAULT_FIELDS[key]


def _pick(body: dict, key: str) -> str:
    for name in _candidates(key):
        if name in body and body[name] is not None:
            return str(body[name])
    return ""


def _decode(content_type: str, raw: bytes) -> dict:
    content_type = (content_type or "").lower()
    text = raw.decode("utf-8", errors="replace")
    if "json" in content_type or text.lstrip().startswith("{"):
        try:
            data = json.loads(text or "{}")
        except json.JSONDecodeError as exc:
            raise BadRequest(f"invalid JSON: {exc}") from exc
        if not isinstance(data, dict):
            raise BadRequest("JSON body must be an object")
        return data
    return {k: v[-1] for k, v in parse_qs(text, keep_blank_values=True).items()}


def normalize_phone(phone: str) -> str:
    """Return E.164 (+2547XXXXXXXX) for Kenyan numbers; leave others as +digits."""
    digits = re.sub(r"\D", "", phone or "")
    if not digits:
        return ""
    if digits.startswith("0") and len(digits) == 10:
        digits = "254" + digits[1:]
    elif len(digits) == 9 and digits[0] in "17":
        digits = "254" + digits
    return "+" + digits


def parse(content_type: str, raw: bytes, query: dict | None = None) -> UssdRequest:
    body = _decode(content_type, raw)
    if query:
        # Some gateways send the session on the query string; the body wins.
        body = {**query, **body}
    session_id = _pick(body, "session").strip()
    phone = normalize_phone(_pick(body, "phone"))
    if not session_id or not phone:
        log.warning("Unrecognised Wasiliana payload keys: %s", sorted(body))
        raise BadRequest("session id and phone are required")
    return UssdRequest(
        session_id=session_id,
        phone=phone,
        text=_pick(body, "text").strip(),
        service_code=_pick(body, "service_code"),
    )
