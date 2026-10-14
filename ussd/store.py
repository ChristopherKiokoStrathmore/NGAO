"""Data access for the USSD service.

Writes: USSD_SESSIONS only (one upsert per hop).
Reads:  SUBSCRIBERS.preferred_lang (to know whether a number is new and which
        language to use) and WARDS (county and ward lists for registration).
        These reads are read-only; SUBSCRIBERS is written by the backend via §5.

OracleStore is used when DB_DSN is set. MemoryStore is for local runs and
tests; its ward list is a DEV FIXTURE whose ids do not match the real WARDS table.
"""

import logging
import os
import threading
import time
from dataclasses import dataclass

log = logging.getLogger(__name__)

# DEV FIXTURE ONLY. Real ward ids come from WARDS (loaded by data/).
DEV_WARDS = [
    (1, "Uasin Gishu", "Moiben"),
    (2, "Uasin Gishu", "Kapseret"),
    (3, "Uasin Gishu", "Kimumu"),
    (4, "Uasin Gishu", "Ngeria"),
    (5, "Uasin Gishu", "Tapsagoi"),
    (6, "Uasin Gishu", "Kiplombe"),
    (7, "Uasin Gishu", "Simat/Kapseret"),
    (8, "Uasin Gishu", "Kipkenyo"),
    (9, "Garissa", "Township"),
    (10, "Garissa", "Iftin"),
    (11, "Garissa", "Balambala"),
    (12, "Garissa", "Dadaab"),
]


@dataclass
class SessionMeta:
    """What we knew about the number when the session started."""
    start_lang: str | None  # None = new number, show the language prompt first
    created: float


class SessionCache:
    """Per-session facts that USSD_SESSIONS has no column for.

    Kept in process memory, so run the service as a single worker process
    (threads are fine). Entries expire after the USSD session timeout.
    """

    def __init__(self, ttl_s: int = 600):
        self.ttl_s = ttl_s
        self._data: dict[str, SessionMeta] = {}
        self._lock = threading.Lock()

    def get(self, session_id: str) -> SessionMeta | None:
        with self._lock:
            self._expire()
            return self._data.get(session_id)

    def put(self, session_id: str, meta: SessionMeta) -> None:
        with self._lock:
            self._data[session_id] = meta

    def _expire(self) -> None:
        cutoff = time.time() - self.ttl_s
        for sid in [s for s, m in self._data.items() if m.created < cutoff]:
            del self._data[sid]


class MemoryStore:
    def __init__(self, wards=DEV_WARDS):
        self._wards = list(wards)
        self._langs: dict[str, str] = {}
        self.sessions: dict[str, dict] = {}

    def preferred_lang(self, phone: str) -> str | None:
        return self._langs.get(phone)

    def note_language(self, phone: str, lang: str) -> None:
        # Mirrors what the backend stores, so local runs behave like production.
        self._langs[phone] = lang

    def last_text(self, session_id: str) -> str:
        return self.sessions.get(session_id, {}).get("last_text", "")

    def upsert_session(self, session_id: str, phone: str, text: str) -> None:
        self.sessions[session_id] = {"phone": phone, "last_text": text, "updated_at": time.time()}

    def counties(self) -> list[str]:
        return sorted({c for _, c, _ in self._wards})

    def wards(self, county: str) -> list[tuple[int, str]]:
        return sorted(((i, w) for i, c, w in self._wards if c == county), key=lambda x: x[1])


class OracleStore:
    def __init__(self, pool):
        self.pool = pool
        self._ward_cache: tuple[float, list] | None = None

    @classmethod
    def from_env(cls) -> "OracleStore":
        import oracledb

        params = {
            "user": os.environ["DB_USER"],
            "password": os.environ["DB_PASSWORD"],
            "dsn": os.environ["DB_DSN"],
            "min": 1, "max": 4, "increment": 1,
        }
        wallet = os.getenv("DB_WALLET_DIR")
        if wallet:
            params.update(config_dir=wallet, wallet_location=wallet,
                          wallet_password=os.getenv("DB_WALLET_PASSWORD"))
        return cls(oracledb.create_pool(**params))

    def preferred_lang(self, phone: str) -> str | None:
        with self.pool.acquire() as conn, conn.cursor() as cur:
            cur.execute("SELECT preferred_lang FROM subscribers WHERE phone = :p", p=phone)
            row = cur.fetchone()
            return row[0].strip() if row else None

    def note_language(self, phone: str, lang: str) -> None:
        pass  # the backend wrote SUBSCRIBERS through POST /ussd/language

    def last_text(self, session_id: str) -> str:
        with self.pool.acquire() as conn, conn.cursor() as cur:
            cur.execute("SELECT last_text FROM ussd_sessions WHERE session_id = :s", s=session_id)
            row = cur.fetchone()
            return (row[0] or "") if row else ""

    def upsert_session(self, session_id: str, phone: str, text: str) -> None:
        with self.pool.acquire() as conn, conn.cursor() as cur:
            cur.execute(
                """
                MERGE INTO ussd_sessions t
                USING (SELECT :s AS session_id, :p AS phone, :t AS last_text FROM dual) src
                ON (t.session_id = src.session_id)
                WHEN MATCHED THEN UPDATE SET
                  t.last_text = src.last_text, t.updated_at = SYSTIMESTAMP
                WHEN NOT MATCHED THEN INSERT (session_id, subscriber_id, phone, last_text, updated_at)
                  VALUES (src.session_id,
                          (SELECT subscriber_id FROM subscribers WHERE phone = src.phone),
                          src.phone, src.last_text, SYSTIMESTAMP)
                """,
                s=session_id, p=phone, t=text[:200],
            )
            conn.commit()

    def _all_wards(self) -> list[tuple[int, str, str]]:
        # WARDS changes rarely; cache it for 10 minutes to keep hops fast.
        if self._ward_cache and time.time() - self._ward_cache[0] < 600:
            return self._ward_cache[1]
        with self.pool.acquire() as conn, conn.cursor() as cur:
            cur.execute("SELECT ward_id, county, ward_name FROM wards ORDER BY county, ward_name")
            rows = [(int(i), c, w) for i, c, w in cur]
        self._ward_cache = (time.time(), rows)
        return rows

    def counties(self) -> list[str]:
        return sorted({c for _, c, _ in self._all_wards()})

    def wards(self, county: str) -> list[tuple[int, str]]:
        return [(i, w) for i, c, w in self._all_wards() if c == county]


def store_from_env():
    if os.getenv("DB_DSN"):
        return OracleStore.from_env()
    log.warning("DB_DSN not set: using MemoryStore with DEV ward fixture")
    return MemoryStore()
