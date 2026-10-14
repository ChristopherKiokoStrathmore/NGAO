import json

import pytest

import wasiliana


def test_form_body():
    req = wasiliana.parse("application/x-www-form-urlencoded",
                          b"sessionId=s1&phoneNumber=0712345678&serviceCode=*384%2355%23&text=1*2")
    assert (req.session_id, req.phone, req.text) == ("s1", "+254712345678", "1*2")


def test_json_body():
    body = json.dumps({"sessionId": "s2", "phoneNumber": "254712345678", "text": ""}).encode()
    req = wasiliana.parse("application/json", body)
    assert (req.session_id, req.phone, req.text) == ("s2", "+254712345678", "")


def test_field_override(monkeypatch):
    monkeypatch.setenv("WASILIANA_FIELD_PHONE", "MSISDN_X")
    req = wasiliana.parse("application/json", b'{"sessionId":"s3","MSISDN_X":"+254712345678"}')
    assert req.phone == "+254712345678"


def test_missing_fields():
    with pytest.raises(wasiliana.BadRequest):
        wasiliana.parse("application/json", b'{"text":"1"}')
