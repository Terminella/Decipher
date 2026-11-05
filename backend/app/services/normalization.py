"""
Normalisation and field-level comparison helpers for the contextual-analysis engine (Department 3).

Pure functions, no I/O. Every comparator answers one question:

    "Are these two extracted values the same information, a benign variation,
     a probable OCR slip, or a genuine contradiction?"

and returns a `Comparison` whose `relation` says which one:

    EXACT         identical after basic clean-up                          -> consistent
    FORMAT_ONLY   same information, different presentation                -> consistent
    COMPATIBLE    not contradictory, but one side is less complete/precise (initials, rounding, ...)
    TYPO          small difference (spelling, one character / digit)
    DIFFERENT     contradictory
    UNCOMPARABLE  a value could not be parsed
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from difflib import SequenceMatcher
from enum import Enum
from typing import Optional

from .contextual_schemas import ExtractedField, FieldType


# --------------------------------------------------------------------------------------
# Result types
# --------------------------------------------------------------------------------------
class Relation(str, Enum):
    EXACT = "exact"
    FORMAT_ONLY = "format_only"
    COMPATIBLE = "compatible"
    TYPO = "typo"
    DIFFERENT = "different"
    UNCOMPARABLE = "uncomparable"


RELATION_RANK = {
    Relation.EXACT: 0, Relation.FORMAT_ONLY: 1, Relation.COMPATIBLE: 2,
    Relation.TYPO: 3, Relation.DIFFERENT: 4, Relation.UNCOMPARABLE: 5,
}
CONSISTENT = {Relation.EXACT, Relation.FORMAT_ONLY}


@dataclass
class Comparison:
    relation: Relation
    similarity: float = 0.0          # 0..1
    detail: str = ""                 # human-readable "what differs"
    ocr_confusable: bool = False     # the difference consists only of look-alike characters (O/0, 1/7, ...)
    magnitude: float = 0.0           # relative difference for amounts (0..1)


# --------------------------------------------------------------------------------------
# Generic text helpers
# --------------------------------------------------------------------------------------
def clean_text(value: Optional[str]) -> str:
    if value is None:
        return ""
    text = unicodedata.normalize("NFKC", str(value)).replace("\u00a0", " ")
    return re.sub(r"\s+", " ", text).strip()


def alnum_key(value: Optional[str]) -> str:
    return re.sub(r"[^A-Z0-9]", "", clean_text(value).upper())


def edit_distance(a: str, b: str) -> int:
    """Optimal-string-alignment distance: insert / delete / substitute / swap adjacent, each cost 1."""
    la, lb = len(a), len(b)
    if la == 0:
        return lb
    if lb == 0:
        return la
    prev2: list[int] = []
    prev = list(range(lb + 1))
    for i in range(1, la + 1):
        cur = [i] + [0] * lb
        for j in range(1, lb + 1):
            cost = 0 if a[i - 1] == b[j - 1] else 1
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + cost)
            if i > 1 and j > 1 and a[i - 1] == b[j - 2] and a[i - 2] == b[j - 1]:
                cur[j] = min(cur[j], prev2[j - 2] + 1)
        prev2, prev = prev, cur
    return prev[lb]


_CONFUSABLE_PAIRS = ("0O", "0D", "0Q", "1I", "1L", "17", "5S", "56", "8B", "38", "2Z", "6G", "9G", "UV", "IL", "CG")
_CONFUSABLE = {frozenset(p) for p in _CONFUSABLE_PAIRS}
_LOOKALIKE: dict[str, set[str]] = {}
for _pair in _CONFUSABLE_PAIRS:
    _LOOKALIKE.setdefault(_pair[0], set()).add(_pair[1])
    _LOOKALIKE.setdefault(_pair[1], set()).add(_pair[0])
_DIGRAPHS = (("RN", "M"), ("CL", "D"), ("VV", "W"))


def _collapse_digraphs(text: str) -> str:
    for src, dst in _DIGRAPHS:
        text = text.replace(src, dst)
    return text


def ocr_confusable(a: str, b: str) -> bool:
    """True when a and b differ ONLY in characters that OCR engines commonly mix up (O/0, 1/7, S/5, rn/m ...)."""
    a, b = a.upper(), b.upper()
    if a == b:
        return False
    if _collapse_digraphs(a) == _collapse_digraphs(b):
        return True
    if len(a) != len(b):
        return False
    diffs = [(x, y) for x, y in zip(a, b) if x != y]
    return bool(diffs) and all(frozenset(p) in _CONFUSABLE for p in diffs)


def _ratio(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


_PLACEHOLDER = re.compile(
    r"^(n/?a|nil|none|null|unknown|illegible|unreadable|not (available|provided|readable|applicable)|[-_.?\s]*)$",
    re.IGNORECASE,
)


def is_blank_value(value: Optional[str]) -> bool:
    """Empty, or a placeholder such as 'N/A' or '---'. (A deliberately masked value such as 'XXXX 1234' is NOT blank.)"""
    return bool(_PLACEHOLDER.match(clean_text(value)))


# --------------------------------------------------------------------------------------
# Field "concepts": which fields are comparable with each other, and how much a mismatch matters
# --------------------------------------------------------------------------------------
class Kind(str, Enum):
    NAME = "name"
    DATE = "date"
    AMOUNT = "amount"
    ADDRESS = "address"
    IDENTIFIER = "identifier"
    TEXT = "text"


@dataclass(frozen=True)
class Concept:
    key: str
    kind: Kind
    display: str
    criticality: float            # 0..1 - how serious a disagreement in this concept is
    unique: bool = True           # exactly one value expected per document (enables duplicate-conflict checks)
    identity: bool = False        # helps answer "is this the same person?"
    best_match: bool = True       # True: compare the closest pair; False: compare only if exactly one per document


C_FATHER = Concept("father_name", Kind.NAME, "father's name", 0.5)
C_MOTHER = Concept("mother_name", Kind.NAME, "mother's name", 0.5)
C_SPOUSE = Concept("spouse_name", Kind.NAME, "spouse's name", 0.5)
C_GUARDIAN = Concept("guardian_name", Kind.NAME, "guardian's name", 0.5)
C_THIRD_PARTY = Concept("third_party_name", Kind.NAME, "third-party name", 0.4, unique=False, best_match=False)
C_ORG = Concept("organization_name", Kind.NAME, "organisation name", 0.5, unique=False, best_match=False)
C_PERSON = Concept("person_name", Kind.NAME, "name", 0.8, identity=True)
C_DOB = Concept("date_of_birth", Kind.DATE, "date of birth", 0.9, identity=True)
C_EXPIRY = Concept("expiry_date", Kind.DATE, "expiry date", 0.5)
C_ISSUE = Concept("issue_date", Kind.DATE, "issue date", 0.5)
C_WORDS = Concept("amount_in_words", Kind.AMOUNT, "amount in words", 0.8, unique=False, best_match=False)
C_LOAN = Concept("loan_amount", Kind.AMOUNT, "loan amount", 0.8, unique=False)
C_INCOME = Concept("income", Kind.AMOUNT, "income", 0.8, unique=False)
C_ADDR_PERMANENT = Concept("address_permanent", Kind.ADDRESS, "permanent address", 0.5)
C_ADDR_CURRENT = Concept("address_current", Kind.ADDRESS, "current address", 0.5)
C_ADDR_OFFICE = Concept("address_office", Kind.ADDRESS, "office address", 0.4)
C_ADDRESS = Concept("address", Kind.ADDRESS, "address", 0.5)
C_PAN = Concept("pan", Kind.IDENTIFIER, "PAN", 1.0, identity=True)
C_AADHAAR = Concept("aadhaar", Kind.IDENTIFIER, "Aadhaar number", 1.0, identity=True)
C_PASSPORT = Concept("passport_number", Kind.IDENTIFIER, "passport number", 1.0, identity=True)
C_ACCOUNT = Concept("account_number", Kind.IDENTIFIER, "account number", 0.9, unique=False)

_T = FieldType
_NAMEISH = {_T.NAME}
_IDISH = {_T.ID_NUMBER, _T.DOCUMENT_REFERENCE, _T.OTHER}

# Order matters: first match wins. "father's name" must be caught before the generic person-name rule.
_RULES: list[tuple[frozenset, re.Pattern, Concept]] = [
    (frozenset(_NAMEISH), re.compile(r"\bfathers?\b"), C_FATHER),
    (frozenset(_NAMEISH), re.compile(r"\bmothers?\b"), C_MOTHER),
    (frozenset(_NAMEISH), re.compile(r"\b(spouse|husband|wife)s?\b"), C_SPOUSE),
    (frozenset(_NAMEISH), re.compile(r"\b(guardian|parent)s?\b"), C_GUARDIAN),
    (frozenset(_NAMEISH), re.compile(r"\b(nominee|beneficiary|payee|witness|introducer|referee|guarantor|surety|"
                                     r"co ?applicant|joint|second (holder|applicant)|signator\w*|authori[sz]ed|"
                                     r"representative|contact person|director|partner|manager|officer)\b"), C_THIRD_PARTY),
    (frozenset(_NAMEISH), re.compile(r"\b(employer|company|organi[sz]ation|firm|business|institution|bank|branch|"
                                     r"college|university|school)\b"), C_ORG),
    (frozenset(_NAMEISH), re.compile(r".*"), C_PERSON),
    (frozenset({_T.DATE}), re.compile(r"\b(dob|date of birth|birth ?date|born)\b|\bd o b\b"), C_DOB),
    (frozenset({_T.DATE}), re.compile(r"\b(expiry|expiration|expires?|validity|valid (up ?to|upto|until|till|thru|through|to))\b"),
     C_EXPIRY),
    (frozenset({_T.DATE}), re.compile(r"\b(issue|issued|issuance|doi)\b"), C_ISSUE),
    (frozenset({_T.AMOUNT}), re.compile(r"\bin words\b|\bwords\b"), C_WORDS),
    (frozenset({_T.AMOUNT}), re.compile(r"\b(loan|principal|sanctioned|facility|requested|limit)\b"), C_LOAN),
    (frozenset({_T.AMOUNT}), re.compile(r"\b(income|salary|salaries|wage|wages|earning|earnings|ctc|net pay|take home|"
                                        r"remuneration)\b"), C_INCOME),
    (frozenset({_T.ADDRESS}), re.compile(r"\bpermanent\b"), C_ADDR_PERMANENT),
    (frozenset({_T.ADDRESS}), re.compile(r"\b(current|present|residential|residence|correspondence|communication|mailing)\b"),
     C_ADDR_CURRENT),
    (frozenset({_T.ADDRESS}), re.compile(r"\b(office|business|work|employer)\b"), C_ADDR_OFFICE),
    (frozenset({_T.ADDRESS}), re.compile(r".*"), C_ADDRESS),
    (frozenset(_IDISH), re.compile(r"\bpan\b|permanent account"), C_PAN),
    (frozenset(_IDISH), re.compile(r"\b(aadhaar|aadhar|adhaar|uid|uidai)\b"), C_AADHAAR),
    (frozenset(_IDISH), re.compile(r"\bpassport\b"), C_PASSPORT),
    (frozenset(_IDISH), re.compile(r"\b(account|a c|acct)\b"), C_ACCOUNT),
]

_KIND_BY_TYPE = {
    _T.NAME: Kind.NAME, _T.DATE: Kind.DATE, _T.AMOUNT: Kind.AMOUNT, _T.ADDRESS: Kind.ADDRESS,
    _T.ID_NUMBER: Kind.IDENTIFIER, _T.DOCUMENT_REFERENCE: Kind.IDENTIFIER, _T.OTHER: Kind.TEXT,
}
_DEFAULT_CRITICALITY = {
    _T.NAME: 0.6, _T.DATE: 0.5, _T.AMOUNT: 0.6, _T.ADDRESS: 0.5,
    _T.ID_NUMBER: 0.8, _T.DOCUMENT_REFERENCE: 0.6, _T.OTHER: 0.3,
}


def label_text(label: Optional[str]) -> str:
    text = clean_text(label).lower().replace("'", "").replace("\u2019", "")
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def _effective_type(field: ExtractedField, label: str) -> FieldType:
    """Dept 4 may leave field_type as OTHER; recover it from the label where possible."""
    if field.field_type != _T.OTHER:
        return field.field_type
    if re.search(r"\bname\b", label):
        return _T.NAME
    if re.search(r"\b(dob|date|born|expiry|issued|issue)\b", label):
        return _T.DATE
    if re.search(r"\b(address|residence)\b", label):
        return _T.ADDRESS
    if re.search(r"\b(amount|income|salary|loan|balance|total|fee|premium|limit)\b", label):
        return _T.AMOUNT
    if re.search(r"\b(pan|aadhaar|aadhar|passport|account|licen[cs]e|voter|uid)\b", label):
        return _T.ID_NUMBER
    return _T.OTHER


_PAN_VALUE = re.compile(r"[A-Z]{5}[0-9]{4}[A-Z]")
_AADHAAR_SPACED = re.compile(r"\d{4}\s\d{4}\s\d{4}")


def infer_concept(field: ExtractedField) -> Concept:
    """Decide what a field *means* so that only genuinely comparable fields are compared."""
    label = label_text(field.label)
    ftype = _effective_type(field, label)

    if ftype == _T.AMOUNT and field.value.strip() and not re.search(r"\d", field.value):
        return C_WORDS                                   # "Rupees One Lakh Only"

    for types, pattern, concept in _RULES:
        if ftype in types and pattern.search(label):
            return concept

    if ftype in (_T.ID_NUMBER, _T.DOCUMENT_REFERENCE, _T.OTHER):
        if _PAN_VALUE.fullmatch(alnum_key(field.value)):
            return C_PAN
        if _AADHAAR_SPACED.fullmatch(clean_text(field.value)):
            return C_AADHAAR

    # Unknown label: comparable only with an identically-labelled field of the same type.
    return Concept(
        key=f"{ftype.value}:{label or 'unlabelled'}",
        kind=_KIND_BY_TYPE[ftype],
        display=clean_text(field.label) or ftype.value.replace("_", " "),
        criticality=_DEFAULT_CRITICALITY[ftype],
        unique=False,
        best_match=False,
    )


# --------------------------------------------------------------------------------------
# Names
# --------------------------------------------------------------------------------------
_HONORIFICS = {"mr", "mrs", "ms", "miss", "dr", "prof", "shri", "shree", "sri", "smt", "shrimati",
               "kumari", "kum", "late", "capt", "adv"}


def name_tokens(raw: Optional[str]) -> list[str]:
    text = clean_text(raw).lower().replace("'", "").replace("\u2019", "").replace("`", "")
    text = re.sub(r"[^\w\s]|_", " ", text)
    return [t for t in text.split() if t not in _HONORIFICS]


def _token_relation(a: str, b: str) -> Optional[str]:
    if a == b:
        return "exact"
    if len(a) == 1 or len(b) == 1:
        return "initial" if a[0] == b[0] else None
    short, long_ = (a, b) if len(a) <= len(b) else (b, a)
    if len(short) >= 3 and long_.startswith(short):
        return "typo" if (len(short) >= 4 and len(long_) - len(short) <= 1) else "short_form"
    if ocr_confusable(a, b):
        return "typo"
    if len(short) >= 4 and _ratio(a, b) >= 0.8:
        return "typo"
    return None


_TOKEN_RANK = {"exact": 0, "initial": 1, "short_form": 1, "typo": 2}


def compare_names(a: str, b: str) -> Comparison:
    ta, tb = name_tokens(a), name_tokens(b)
    if not ta or not tb:
        return Comparison(Relation.UNCOMPARABLE, 0.0, "a name is empty or unreadable")
    if ta == tb:
        return Comparison(Relation.EXACT, 1.0, "same name after normalisation")
    if sorted(ta) == sorted(tb):
        return Comparison(Relation.FORMAT_ONLY, 1.0, "same words in a different order")

    sim = _ratio(" ".join(sorted(ta)), " ".join(sorted(tb)))
    short, long_ = (ta, tb) if len(ta) <= len(tb) else (tb, ta)
    unused = list(range(len(long_)))
    matches: list[tuple[str, str, str]] = []
    unmatched: list[str] = []
    for tok in sorted(short, key=len, reverse=True):
        best: Optional[tuple[int, str]] = None
        for idx in unused:
            kind = _token_relation(tok, long_[idx])
            if kind and (best is None or _TOKEN_RANK[kind] < _TOKEN_RANK[best[1]]):
                best = (idx, kind)
        if best:
            unused.remove(best[0])
            matches.append((tok, long_[best[0]], best[1]))
        else:
            unmatched.append(tok)

    if not unmatched:
        typos = [(x, y) for x, y, k in matches if k == "typo"]
        if typos:
            shown = "; ".join(f"'{x}' vs '{y}'" for x, y in typos)
            return Comparison(Relation.TYPO, sim, f"spelling differs: {shown}",
                              ocr_confusable=all(ocr_confusable(x, y) for x, y in typos))
        shortened = any(k in ("initial", "short_form") for _, _, k in matches)
        why = "initials or shortened forms" if shortened else "one name omits part of the other"
        return Comparison(Relation.COMPATIBLE, sim, f"compatible names ({why})")

    leftover = [long_[i] for i in unused]
    fmt = lambda toks: ", ".join(f"'{t}'" for t in toks) or "-"
    return Comparison(Relation.DIFFERENT, sim, f"words without a counterpart: {fmt(unmatched)} vs {fmt(leftover)}")


# --------------------------------------------------------------------------------------
# Dates
# --------------------------------------------------------------------------------------
_MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], start=1)}


@dataclass(frozen=True)
class ParsedDate:
    candidates: tuple            # tuple[date, ...]; first = most likely reading (day-first)


def _make_date(y: int, m: int, d: int) -> Optional[date]:
    try:
        return date(y, m, d)
    except ValueError:
        return None


def _expand_year(yy: int) -> int:
    if yy >= 100:
        return yy
    return 2000 + yy if yy <= date.today().year % 100 else 1900 + yy


def parse_date(raw: Optional[str]) -> Optional[ParsedDate]:
    text = clean_text(raw).lower()
    if not text:
        return None
    if re.fullmatch(r"[0-9oli|/.\-\s]+", text):          # numeric date that may contain OCR look-alikes
        text = text.translate(str.maketrans({"o": "0", "l": "1", "i": "1", "|": "1"}))

    m = re.fullmatch(r"(\d{4})\s*[-/.]\s*(\d{1,2})\s*[-/.]\s*(\d{1,2})", text)          # yyyy-mm-dd
    if m:
        d = _make_date(int(m[1]), int(m[2]), int(m[3]))
        return ParsedDate((d,)) if d else None

    m = re.fullmatch(r"(\d{1,2})\s*[-/.\s]\s*(\d{1,2})\s*[-/.\s]\s*(\d{4}|\d{2})", text)  # dd/mm/yyyy
    if m:
        a, b, y = int(m[1]), int(m[2]), _expand_year(int(m[3]))
        cands: list[date] = []
        for day, month in ((a, b), (b, a)):
            d = _make_date(y, month, day)
            if d and d not in cands:
                cands.append(d)
        return ParsedDate(tuple(cands)) if cands else None

    m = re.fullmatch(r"\d{8}", text)                                                     # ddmmyyyy / yyyymmdd
    if m:
        s = m[0]
        d = (_make_date(int(s[:4]), int(s[4:6]), int(s[6:])) if 1900 <= int(s[:4]) <= 2100
             else _make_date(int(s[4:]), int(s[2:4]), int(s[:2])))
        return ParsedDate((d,)) if d else None

    m = re.fullmatch(r"(\d{1,2})(?:st|nd|rd|th)?[\s\-/.,]*([a-z]{3,9})\.?[\s\-/.,]*(\d{4}|\d{2})", text)  # 12 Jan 2020
    if m and m[2][:3] in _MONTHS:
        d = _make_date(_expand_year(int(m[3])), _MONTHS[m[2][:3]], int(m[1]))
        return ParsedDate((d,)) if d else None

    m = re.fullmatch(r"([a-z]{3,9})\.?[\s\-/.,]*(\d{1,2})(?:st|nd|rd|th)?[\s,\-/.]*(\d{4})", text)       # Jan 12, 2020
    if m and m[1][:3] in _MONTHS:
        d = _make_date(int(m[3]), _MONTHS[m[1][:3]], int(m[2]))
        return ParsedDate((d,)) if d else None
    return None


def compare_dates(a: str, b: str) -> Comparison:
    pa, pb = parse_date(a), parse_date(b)
    if pa is None or pb is None:
        return Comparison(Relation.UNCOMPARABLE, 0.0, "a date could not be parsed")
    da, db = pa.candidates[0], pb.candidates[0]
    if da == db:
        same_raw = clean_text(a).lower() == clean_text(b).lower()
        return Comparison(Relation.EXACT if same_raw else Relation.FORMAT_ONLY, 1.0, f"same date ({da.isoformat()})")
    if set(pa.candidates) & set(pb.candidates):
        return Comparison(Relation.COMPATIBLE, 0.8,
                          f"equal only if day and month are read in opposite order ({da.isoformat()} vs {db.isoformat()})")
    best: Optional[tuple[int, date, date]] = None
    for x in pa.candidates:
        for y in pb.candidates:
            dist = edit_distance(x.strftime("%Y%m%d"), y.strftime("%Y%m%d"))
            if best is None or dist < best[0]:
                best = (dist, x, y)
    assert best is not None
    dist, x, y = best
    detail = f"{x.isoformat()} vs {y.isoformat()} ({abs((x - y).days)} days apart)"
    if dist <= 1:
        return Comparison(Relation.TYPO, 0.9, detail + "; differs by one digit edit",
                          ocr_confusable=ocr_confusable(x.strftime("%Y%m%d"), y.strftime("%Y%m%d")))
    return Comparison(Relation.DIFFERENT, 0.0, detail)


# --------------------------------------------------------------------------------------
# Amounts
# --------------------------------------------------------------------------------------
@dataclass(frozen=True)
class ParsedAmount:
    value: Decimal
    currency: Optional[str]


_MULTIPLIERS = {"lakh": 10**5, "lakhs": 10**5, "lac": 10**5, "lacs": 10**5, "crore": 10**7, "crores": 10**7,
                "thousand": 10**3, "million": 10**6, "mn": 10**6, "billion": 10**9, "bn": 10**9, "k": 10**3}
_CURRENCIES = (("\u20b9", "INR"), ("rs", "INR"), ("inr", "INR"), ("rupee", "INR"),
               ("$", "USD"), ("usd", "USD"), ("dollar", "USD"),
               ("\u20ac", "EUR"), ("eur", "EUR"), ("\u00a3", "GBP"), ("gbp", "GBP"))

_NUM_UNITS = {w: i for i, w in enumerate(
    "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen "
    "seventeen eighteen nineteen".split())}
_NUM_TENS = {w: 10 * (i + 2) for i, w in enumerate("twenty thirty forty fifty sixty seventy eighty ninety".split())}
_NUM_SCALES = {"thousand": 10**3, "lakh": 10**5, "lakhs": 10**5, "lac": 10**5, "lacs": 10**5,
               "crore": 10**7, "crores": 10**7, "million": 10**6, "billion": 10**9}
_NUM_IGNORE = {"rupees", "rupee", "rs", "only", "and", "dollars", "dollar", "usd", "inr", "euro", "euros",
               "pounds", "pound"}


def _detect_currency(text: str) -> Optional[str]:
    low = text.lower()
    for marker, code in _CURRENCIES:
        if len(marker) == 1 and not marker.isalpha():
            if marker in low:
                return code
        elif re.search(rf"\b{re.escape(marker)}s?\b\.?", low):
            return code
    return None


def _fix_numeric_ocr(text: str) -> str:
    """Inside digit groups, read the letter O as zero ("1,5OO" -> "1,500")."""
    def repl(m: re.Match) -> str:
        tok = m.group(0)
        return re.sub(r"[Oo]", "0", tok) if re.search(r"\d", tok) else tok
    return re.sub(r"[\dOo][\dOo,]*(?:\.[\dOo]+)?", repl, text)


def amount_from_words(text: str) -> Optional[Decimal]:
    """'Rupees One Lakh Fifty Thousand Only' -> 150000. None if the text is not a clean number in words."""
    words = re.findall(r"[a-z]+", clean_text(text).lower())
    for i, w in enumerate(words):
        if w in {"paise", "paisa", "cents", "cent"}:
            cut = max((k for k in range(i) if words[k] == "and"), default=i)
            words = words[:cut]
            break
    total = current = 0
    seen = False
    for w in words:
        if w in _NUM_IGNORE:
            continue
        if w in _NUM_UNITS:
            current += _NUM_UNITS[w]
        elif w in _NUM_TENS:
            current += _NUM_TENS[w]
        elif w == "hundred":
            current = max(current, 1) * 100
        elif w in _NUM_SCALES:
            total += max(current, 1) * _NUM_SCALES[w]
            current = 0
        else:
            return None
        seen = True
    return Decimal(total + current) if seen else None


def parse_amount(raw: Optional[str]) -> Optional[ParsedAmount]:
    text = clean_text(raw)
    if not text:
        return None
    currency = _detect_currency(text)
    fixed = _fix_numeric_ocr(text)
    m = re.search(r"\d[\d,]*(?:\.\d+)?", fixed)
    if not m:
        words_value = amount_from_words(text)
        return ParsedAmount(words_value, currency) if words_value is not None else None
    try:
        value = Decimal(m.group(0).replace(",", ""))
    except InvalidOperation:
        return None
    mult = re.match(r"\s*(lakhs?|lacs?|crores?|thousand|million|mn|billion|bn|k)\b", fixed[m.end():], re.IGNORECASE)
    if mult:
        value *= _MULTIPLIERS[mult.group(1).lower()]
    return ParsedAmount(value, currency)


def _digits(value: Decimal) -> str:
    try:
        text = f"{value.quantize(Decimal('0.01')):f}"
    except InvalidOperation:
        text = f"{value:f}"
    return text.replace(".", "").replace("-", "")


def format_amount(value: Decimal) -> str:
    text = f"{value:,.2f}"
    return text.rstrip("0").rstrip(".") if "." in text else text


def compare_amounts(a: str, b: str) -> Comparison:
    pa, pb = parse_amount(a), parse_amount(b)
    if pa is None or pb is None:
        return Comparison(Relation.UNCOMPARABLE, 0.0, "an amount could not be read as a number")
    if pa.currency and pb.currency and pa.currency != pb.currency:
        return Comparison(Relation.DIFFERENT, 0.0, f"currencies differ ({pa.currency} vs {pb.currency})", magnitude=1.0)
    va, vb = pa.value, pb.value
    if va == vb:
        same_raw = clean_text(a).lower() == clean_text(b).lower()
        return Comparison(Relation.EXACT if same_raw else Relation.FORMAT_ONLY, 1.0, f"same amount ({format_amount(va)})")
    hi = max(abs(va), abs(vb))
    mag = float(abs(va - vb) / hi) if hi else 1.0
    detail = f"{format_amount(va)} vs {format_amount(vb)} ({mag:.0%} difference)"
    if mag <= 0.002:
        return Comparison(Relation.COMPATIBLE, 1.0 - mag, detail + ", within rounding tolerance", magnitude=mag)
    da, db = _digits(va), _digits(vb)
    if edit_distance(da, db) <= 1:
        return Comparison(Relation.TYPO, 1.0 - mag, detail + "; differs by one digit edit", ocr_confusable=ocr_confusable(da, db), magnitude=mag)
    return Comparison(Relation.DIFFERENT, 1.0 - mag, detail, magnitude=mag)


# --------------------------------------------------------------------------------------
# Addresses
# --------------------------------------------------------------------------------------
_ADDR_ABBR = {"rd": "road", "st": "street", "ave": "avenue", "apt": "apartment", "bldg": "building", "blk": "block",
              "nr": "near", "opp": "opposite", "sec": "sector", "ph": "phase", "dist": "district", "ste": "suite",
              "flr": "floor", "hno": "house"}
_ADDR_STOP = {"the", "of", "and", "no", "number", "at", "in"}


def address_tokens(raw: Optional[str]) -> tuple[list[str], Optional[str]]:
    text = clean_text(raw).lower()
    pin: Optional[str] = None
    pins = re.findall(r"(?<!\d)(\d{6}|\d{5})(?!\d)", text)
    if pins:
        pin = pins[-1]
        text = text.replace(pin, " ")
    text = re.sub(r"[^\w\s]|_", " ", text.replace("'", ""))
    tokens = [_ADDR_ABBR.get(t, t) for t in text.split()]
    tokens = [t for t in tokens if t and t not in _ADDR_STOP]
    merged: list[str] = []
    run = ""
    for t in tokens:                       # "m g road" -> "mg road"
        if len(t) == 1 and t.isalpha():
            run += t
        else:
            if run:
                merged.append(run)
                run = ""
            merged.append(t)
    if run:
        merged.append(run)
    return merged, pin


def compare_addresses(a: str, b: str) -> Comparison:
    ta, pa = address_tokens(a)
    tb, pb = address_tokens(b)
    sa, sb = set(ta), set(tb)
    if not sa or not sb:
        return Comparison(Relation.UNCOMPARABLE, 0.0, "an address is empty or unreadable")
    overlap = len(sa & sb)
    jaccard = overlap / len(sa | sb)
    contain = overlap / min(len(sa), len(sb))
    sim = max(jaccard, _ratio(" ".join(sorted(ta)), " ".join(sorted(tb))))
    only_a, only_b = sorted(sa - sb), sorted(sb - sa)
    diff = f"only in first: {only_a or '-'}; only in second: {only_b or '-'}"

    if pa and pb and pa != pb:
        rel = Relation.TYPO if (edit_distance(pa, pb) == 1 and sim >= 0.8) else Relation.DIFFERENT
        return Comparison(rel, sim, f"postal codes differ ({pa} vs {pb}); {diff}")
    if sa == sb:
        if bool(pa) != bool(pb):
            return Comparison(Relation.COMPATIBLE, 1.0, "same address, but the postal code appears in only one of them")
        same_raw = clean_text(a).lower() == clean_text(b).lower()
        return Comparison(Relation.EXACT if same_raw else Relation.FORMAT_ONLY, 1.0, "same address after normalisation")
    if contain >= 0.9:
        return Comparison(Relation.COMPATIBLE, sim, f"one address omits parts of the other ({diff})")
    if sim >= 0.85:
        return Comparison(Relation.TYPO, sim, f"very similar addresses ({diff})")
    return Comparison(Relation.DIFFERENT, sim, f"addresses differ ({diff})")


# --------------------------------------------------------------------------------------
# Identifiers (ID numbers, account numbers, document references)
# --------------------------------------------------------------------------------------
_MASK_SET = set("X*\u2022#")
_ID_FORMATS = {
    "pan": (re.compile(r"[A-Z]{5}[0-9]{4}[A-Z]"), "5 letters, 4 digits, 1 letter"),
    "aadhaar": (re.compile(r"[0-9]{12}"), "12 digits"),
    "passport_number": (re.compile(r"[A-Z][0-9]{7}"), "1 letter followed by 7 digits"),
}


def _has_mask(raw: Optional[str]) -> bool:
    return bool(re.search(r"[X*\u2022#]{3,}", clean_text(raw).upper().replace(" ", "").replace("-", "")))


def _mask_key(raw: Optional[str]) -> str:
    return re.sub(r"[^A-Z0-9*\u2022#]", "", clean_text(raw).upper())


def _masked_equal(ka: str, kb: str, ma: bool, mb: bool) -> bool:
    def eq(x: str, y: str) -> bool:
        return x == y or (ma and x in _MASK_SET) or (mb and y in _MASK_SET)

    if len(ka) == len(kb):
        return all(eq(x, y) for x, y in zip(ka, kb))

    def tail(k: str, masked: bool) -> str:
        if not masked:
            return k
        m = re.search(r"[A-Z0-9]+$", k)
        return m.group(0) if m else ""

    ta, tb = tail(ka, ma), tail(kb, mb)
    n = min(len(ta), len(tb))
    return n >= 3 and ta[-n:] == tb[-n:]


def _diff_summary(a: str, b: str) -> str:
    if len(a) == len(b):
        spots = [f"position {i + 1} ('{x}' vs '{y}')" for i, (x, y) in enumerate(zip(a, b)) if x != y]
        return "differs at " + ", ".join(spots[:4])
    return f"edit distance {edit_distance(a, b)}"


def compare_identifiers(a: str, b: str) -> Comparison:
    ma, mb = _has_mask(a), _has_mask(b)
    ka, kb = _mask_key(a), _mask_key(b)
    if not ka or not kb:
        return Comparison(Relation.UNCOMPARABLE, 0.0, "an identifier is empty")
    if ma or mb:
        if _masked_equal(ka, kb, ma, mb):
            return Comparison(Relation.FORMAT_ONLY, 1.0, "one value is masked; the visible characters match")
        return Comparison(Relation.DIFFERENT, 0.0, "the visible characters of the masked value do not match")
    if ka == kb:
        same_raw = clean_text(a).upper() == clean_text(b).upper()
        return Comparison(Relation.EXACT if same_raw else Relation.FORMAT_ONLY, 1.0, "same identifier")
    dist = edit_distance(ka, kb)
    sim = 1.0 - dist / max(len(ka), len(kb))
    if ocr_confusable(ka, kb):
        return Comparison(Relation.TYPO, sim, "identifiers differ only in look-alike characters: " + _diff_summary(ka, kb),
                          ocr_confusable=True)
    if dist <= 2 and min(len(ka), len(kb)) >= 6:
        return Comparison(Relation.TYPO, sim, "identifiers differ slightly: " + _diff_summary(ka, kb))
    return Comparison(Relation.DIFFERENT, sim, "identifiers are different: " + _diff_summary(ka, kb))


@dataclass
class IdFormatCheck:
    valid: bool
    expected: str
    repaired: Optional[str] = None       # a single look-alike substitution that would make the value valid
    repair_note: Optional[str] = None


def check_identifier_format(concept_key: str, raw: Optional[str]) -> Optional[IdFormatCheck]:
    """None when there is no known format, the value is masked, or it is empty."""
    spec = _ID_FORMATS.get(concept_key)
    key = alnum_key(raw)
    if not spec or not key or _has_mask(raw):
        return None
    pattern, expected = spec
    if pattern.fullmatch(key):
        return IdFormatCheck(True, expected)
    found = []
    for i, ch in enumerate(key):
        for alt in _LOOKALIKE.get(ch, ()):
            cand = key[:i] + alt + key[i + 1:]
            if pattern.fullmatch(cand):
                found.append((i, ch, alt, cand))
    if len(found) == 1:
        i, ch, alt, cand = found[0]
        return IdFormatCheck(False, expected, cand, f"becomes valid if '{ch}' at position {i + 1} is read as '{alt}'")
    return IdFormatCheck(False, expected)


# --------------------------------------------------------------------------------------
# Plain text + dispatcher
# --------------------------------------------------------------------------------------
def compare_text(a: str, b: str) -> Comparison:
    ka = re.sub(r"[^a-z0-9]+", " ", clean_text(a).lower()).strip()
    kb = re.sub(r"[^a-z0-9]+", " ", clean_text(b).lower()).strip()
    if not ka or not kb:
        return Comparison(Relation.UNCOMPARABLE, 0.0, "a value is empty")
    if ka == kb:
        return Comparison(Relation.EXACT if clean_text(a).lower() == clean_text(b).lower() else Relation.FORMAT_ONLY,
                          1.0, "same text")
    sim = _ratio(ka, kb)
    if sim >= 0.9:
        return Comparison(Relation.TYPO, sim, "texts are almost identical", ocr_confusable=ocr_confusable(ka, kb))
    return Comparison(Relation.DIFFERENT, sim, "texts differ")


def compare_values(kind: Kind, a: str, b: str) -> Comparison:
    if kind == Kind.NAME:
        return compare_names(a, b)
    if kind == Kind.DATE:
        return compare_dates(a, b)
    if kind == Kind.AMOUNT:
        return compare_amounts(a, b)
    if kind == Kind.ADDRESS:
        return compare_addresses(a, b)
    if kind == Kind.IDENTIFIER:
        return compare_identifiers(a, b)
    return compare_text(a, b)


def display_normalized(kind: Kind, raw: Optional[str]) -> Optional[str]:
    """The normalised form that the engine actually compared - stored as evidence for transparency."""
    if kind == Kind.NAME:
        return " ".join(name_tokens(raw)) or None
    if kind == Kind.DATE:
        p = parse_date(raw)
        return p.candidates[0].isoformat() if p else None
    if kind == Kind.AMOUNT:
        p = parse_amount(raw)
        if not p:
            return None
        return f"{p.currency + ' ' if p.currency else ''}{format_amount(p.value)}"
    if kind == Kind.ADDRESS:
        toks, pin = address_tokens(raw)
        return " ".join(toks + ([pin] if pin else [])) or None
    if kind == Kind.IDENTIFIER:
        return _mask_key(raw) or None
    return clean_text(raw).lower() or None
