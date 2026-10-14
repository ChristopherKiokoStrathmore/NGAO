"""MvuaSmart USSD menu state machine (Jiandikishe, Ripoti, Hali, Lugha, Acha).

The screen is a pure function of the inputs entered so far in this session
(`1*2*20`) plus what we knew about the number when the session started.
Every hop replays the whole path, so:

* API calls that end the session (register, report, status, stop) run on the
  END screen, which is always the newest input.
* The language call is mid-session, so it runs only when the language choice is
  the newest input. Replays on later hops reuse the choice without calling again.
* An invalid input is skipped: the same screen is shown again with
  "Invalid choice", and later inputs are read against that same screen.

All screen text lives in TEXT below. Swahili copy must be checked by a native
speaker before the demo.
"""

from dataclasses import dataclass

from backend import BackendError

LANG_PROMPT = "Chagua lugha / Choose language\n1. Kiswahili\n2. English"
MAX_SCREEN = 182  # USSD screen limit in characters, including "CON "
MORE = "98"

TEXT = {
    "sw": {
        "main": "MvuaSmart\n1. Jiandikishe\n2. Ripoti\n3. Hali ya kata yangu\n4. Lugha / Language\n5. Acha ujumbe",
        "lang_set": "Lugha: Kiswahili",
        "invalid": "Chaguo si sahihi.",
        "error": "Samahani, jaribu tena.",
        "role": "Wewe ni:\n1. Mkulima\n2. Mfugaji\n3. Wote wawili",
        "county": "Chagua kaunti:",
        "ward": "Chagua kata:",
        "more": "Zaidi",
        "no_wards": "Samahani, hakuna kata zilizopatikana. Jaribu baadaye.",
        "consent": "Ukubali kupokea tahadhari za mvua na ushauri wa shamba bure kwa SMS?\n1. Ndiyo\n2. Hapana",
        "registered": "Asante! Umesajiliwa.",
        "declined": "Sawa, hujasajiliwa. Piga tena wakati wowote.",
        "report": "Unaona nini?\n1. Magunia yaliyolowa\n2. Mifugo wagonjwa/wafu\n3. Mafuriko\n4. Kisima/bwawa limekauka\n5. Nyingine",
        "bags_count": "Magunia mangapi yamelowa? Weka namba:",
        "animal_kind": "Mifugo:\n1. Wagonjwa\n2. Wamekufa",
        "animal_count": "Wanyama wangapi? Weka namba:",
        "bad_number": "Weka namba sahihi.",
        "reported": "Asante! Ripoti yako imepokelewa. Itasaidia kuboresha tahadhari za eneo lako.",
        "other": "Tafadhali tutumie SMS ukieleza unachoona shambani.",
        "stop_confirm": "Acha kupokea ujumbe wa MvuaSmart?\n1. Ndiyo, acha\n2. Hapana",
        "stopped": "Umeondolewa. Piga tena ili kujiandikisha upya.",
        "kept": "Sawa, utaendelea kupokea ujumbe wa MvuaSmart.",
    },
    "en": {
        "main": "MvuaSmart\n1. Register\n2. Report\n3. My ward status\n4. Lugha / Language\n5. Stop alerts",
        "lang_set": "Language: English",
        "invalid": "Invalid choice.",
        "error": "Sorry, please try again.",
        "role": "You are a:\n1. Farmer\n2. Herder\n3. Both",
        "county": "Choose county:",
        "ward": "Choose ward:",
        "more": "More",
        "no_wards": "Sorry, no wards are available. Please try later.",
        "consent": "Agree to receive free rain alerts and farm advice by SMS?\n1. Yes\n2. No",
        "registered": "Thank you! You are registered.",
        "declined": "OK, you are not registered. Dial again any time.",
        "report": "What do you see?\n1. Wet bags of grain\n2. Sick or dead animals\n3. Flooding\n4. Water point dry\n5. Other",
        "bags_count": "How many bags are wet? Enter a number:",
        "animal_kind": "Animals:\n1. Sick\n2. Dead",
        "animal_count": "How many animals? Enter a number:",
        "bad_number": "Enter a valid number.",
        "reported": "Thank you! Your report was received. It helps improve alerts for your area.",
        "other": "Please send us an SMS describing what you see on your farm.",
        "stop_confirm": "Stop MvuaSmart alerts?\n1. Yes, stop\n2. No",
        "stopped": "You have been unsubscribed. Dial again to register.",
        "kept": "OK, you will keep receiving MvuaSmart alerts.",
    },
}

LANGS = {"1": "sw", "2": "en"}
ROLES = {"1": "farmer", "2": "herder", "3": "both"}
# Menu 2 choice -> (report_type, unit). Animals pick sick/dead on the next screen.
REPORTS = {"1": ("wet_bags", "bags"), "3": ("flooding", None), "4": ("water_point_dry", None)}
ANIMALS = {"1": "sick_animals", "2": "dead_animals"}


def con(text: str) -> str:
    return f"CON {text}"


def end(text: str) -> str:
    return f"END {text}"


class Reply(Exception):
    """Raised to stop walking the path and send this screen."""

    def __init__(self, screen: str):
        super().__init__(screen)
        self.screen = screen


class Path:
    def __init__(self, text: str):
        self.tokens = [t.strip() for t in text.split("*")] if text else []
        self.i = 0

    def next(self) -> str | None:
        if self.i >= len(self.tokens):
            return None
        self.i += 1
        return self.tokens[self.i - 1]

    @property
    def at_newest(self) -> bool:
        """True when the token just read is the one the user entered this hop."""
        return self.i == len(self.tokens)


@dataclass
class Ctx:
    phone: str
    session_id: str
    lang: str
    backend: object
    store: object


def _choose(path: Path, screen: str, valid, lang: str) -> str:
    """Read the next valid choice, or raise a CON prompt for `screen`."""
    invalid_last = False
    while True:
        token = path.next()
        if token is None:
            prefix = TEXT[lang]["invalid"] + "\n" if invalid_last else ""
            raise Reply(con(prefix + screen))
        if token in valid:
            return token
        invalid_last = path.at_newest


def _number(path: Path, screen: str, lang: str, lo: int = 1, hi: int = 100000) -> int:
    invalid_last = False
    while True:
        token = path.next()
        if token is None:
            prefix = TEXT[lang]["bad_number"] + "\n" if invalid_last else ""
            raise Reply(con(prefix + screen))
        if token.isdigit() and lo <= int(token) <= hi:
            return int(token)
        invalid_last = path.at_newest


def _pages(title: str, labels: list[str], more: str) -> list[str]:
    """Split a numbered list into screens that fit the USSD limit.

    Numbers run across pages (page 2 starts at 6, say), so a number always
    means the same item. Every page except the last ends with "98. More".
    """
    budget = MAX_SCREEN - len("CON ") - len(TEXT["sw"]["invalid"]) - 1
    footer = f"\n{MORE}. {more}"
    pages, current = [], title
    for n, label in enumerate(labels, start=1):
        line = f"\n{n}. {label}"
        if current != title and len(current) + len(line) + len(footer) > budget:
            pages.append(current + footer)
            current = title
        current += line
    pages.append(current)
    return pages


def _pick_from_list(path: Path, title: str, labels: list[str], lang: str) -> int:
    """Return the 0-based index chosen from a long, paged list."""
    pages = _pages(title, labels, TEXT[lang]["more"])
    valid = {str(n) for n in range(1, len(labels) + 1)}
    page = 0
    while True:
        more = {MORE} if page < len(pages) - 1 else set()
        token = _choose(path, pages[page], valid | more, lang)
        if token == MORE:
            page += 1
            continue
        return int(token) - 1


def _language(path: Path, ctx: Ctx, screen: str) -> str:
    choice = _choose(path, screen, LANGS, ctx.lang)
    lang = LANGS[choice]
    if path.at_newest:
        try:
            ctx.backend.set_language(ctx.phone, lang)
        except BackendError:
            raise Reply(end(TEXT[lang]["error"]))
        ctx.store.note_language(ctx.phone, lang)
    return lang


def _register(path: Path, ctx: Ctx) -> str:
    t = TEXT[ctx.lang]
    role = ROLES[_choose(path, t["role"], ROLES, ctx.lang)]

    counties = ctx.store.counties()
    if not counties:
        return end(t["no_wards"])
    county = counties[_pick_from_list(path, t["county"], counties, ctx.lang)]

    wards = ctx.store.wards(county)
    if not wards:
        return end(t["no_wards"])
    ward_id, _ = wards[_pick_from_list(path, t["ward"], [w for _, w in wards], ctx.lang)]

    if _choose(path, t["consent"], {"1", "2"}, ctx.lang) == "2":
        return end(t["declined"])
    ctx.backend.register(ctx.phone, ward_id=ward_id, role=role, lang=ctx.lang, consent=True)
    return end(t["registered"])


def _report(path: Path, ctx: Ctx) -> str:
    t = TEXT[ctx.lang]
    choice = _choose(path, t["report"], {"1", "2", "3", "4", "5"}, ctx.lang)
    if choice == "5":
        return end(t["other"])  # free text goes by SMS; nothing is sent from here
    if choice == "2":
        report_type = ANIMALS[_choose(path, t["animal_kind"], ANIMALS, ctx.lang)]
        count, unit = _number(path, t["animal_count"], ctx.lang), "animals"
    else:
        report_type, unit = REPORTS[choice]
        count = _number(path, t["bags_count"], ctx.lang) if report_type == "wet_bags" else None
    ctx.backend.report(ctx.phone, ctx.session_id, report_type, count, unit)
    return end(t["reported"])


def _status(ctx: Ctx) -> str:
    text = ctx.backend.ward_status(ctx.phone).strip()
    return end(text[: MAX_SCREEN - len("END ")] or TEXT[ctx.lang]["error"])


def _stop(path: Path, ctx: Ctx) -> str:
    t = TEXT[ctx.lang]
    if _choose(path, t["stop_confirm"], {"1", "2"}, ctx.lang) == "2":
        return end(t["kept"])
    ctx.backend.unsubscribe(ctx.phone)
    return end(t["stopped"])


def handle(text: str, ctx: Ctx, is_new: bool) -> str:
    """Return the full reply body (starting with CON or END) for this hop."""
    path = Path(text)
    try:
        if is_new:
            ctx.lang = _language(path, ctx, LANG_PROMPT)
        notice = ""
        while True:
            t = TEXT[ctx.lang]
            choice = _choose(path, notice + t["main"], {"1", "2", "3", "4", "5"}, ctx.lang)
            notice = ""
            if choice == "1":
                return _register(path, ctx)
            if choice == "2":
                return _report(path, ctx)
            if choice == "3":
                return _status(ctx)
            if choice == "4":
                ctx.lang = _language(path, ctx, LANG_PROMPT)
                notice = TEXT[ctx.lang]["lang_set"] + "\n"
                continue
            if choice == "5":
                return _stop(path, ctx)
    except Reply as r:
        return r.screen
    except BackendError:
        return end(TEXT[ctx.lang]["error"])
