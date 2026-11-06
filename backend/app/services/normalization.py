
import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from difflib import SequenceMatcher
from enum import Enum
from typing import Optional

from .contextual_schemas import ExtractedField, FieldType


FIELD_PATTERNS = {

    "name": [
        r"(?:applicant|employee|customer)?\s*name"
    ],

    "date_of_birth": [
        r"date\s*of\s*birth",
        r"\bdob\b"
    ],

    "address": [
        r"\baddress\b"
    ],

    "pan_number": [
        r"\bpan(?:\s*number)?\b"
    ],

    "aadhaar_number": [
        r"\baadhaar(?:\s*number)?\b",
        r"\buid\b"
    ],

    "account_number": [
        r"account\s*(?:number|no\.?)"
    ],

    "salary": [
        r"basic\s*salary",
        r"monthly\s*salary",
        r"total\s*salary",
        r"net\s*pay"
    ],

    "annual_income": [
        r"annual\s*income",
        r"yearly\s*income"
    ],

    "employee_id": [
        r"employee\s*(?:id|no\.?)"
    ],

    "phone": [
        r"(?:mobile|phone|contact)\s*(?:number|no\.?)?"
    ],

    "email": [
        r"\be-?mail\b"
    ],

    "supplier": [
        r"\b(?:supplier|vendor|payee)\b"
    ],

    "invoice_number": [
        r"\binvoice\s*(?:number|no\.?)\b"
    ],

    "purchase_order": [
        r"\bpurchase\s*order\b"
    ],

    "document_date": [
        r"\b(?:invoice|order|transaction)\s*date\b"
    ],

    "amount": [
        r"\b(?:total\s*amount|approved\s*total|amount\s*(?:transferred|paid)?)\b"
    ],

    "transaction_id": [
        r"\btransaction\s*(?:id|number|no\.?)\b"
    ],

    "reference": [
        r"\breference\b"
    ],
}


def clean_text(text):

    text = text.replace("\x0c", "\n")
    text = text.replace("\u00a0", " ")

    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()


def normalize_value(field, value):

    value = value.strip()

    if field == "pan_number":
        return value.upper().replace(" ", "")

    if field == "email":
        return value.lower()

    if field in ["salary", "annual_income"]:

        return re.sub(
            r"[^\d.,-]",
            "",
            value
        )

    return value


def extract_fields(text, pages=None):

    fields = {}
    field_metadata = {}

    lines = clean_text(text).splitlines()

    all_blocks = [
        block
        for page in pages or []
        for block in page.get("blocks", [])
    ]

    def is_field_label(value):
        return any(
            re.fullmatch(rf"\s*(?:{pattern})\s*", value, re.IGNORECASE)
            for patterns in FIELD_PATTERNS.values()
            for pattern in patterns
        )

    def value_locations(value):
        target_tokens = [
            re.sub(r"[\W_]+", "", token.casefold())
            for token in re.findall(
                r"[\w]+(?:[.,/-][\w]+)*",
                value,
                re.UNICODE,
            )
        ]
        target_tokens = [token for token in target_tokens if token]
        matches = []

        grouped_blocks = {}
        for block in all_blocks:
            bbox = block.get("bbox")
            if not isinstance(bbox, dict):
                continue
            if {"x", "y", "width", "height"}.issubset(bbox):
                x0, y0, width, height = (
                    bbox["x"],
                    bbox["y"],
                    bbox["width"],
                    bbox["height"],
                )
            elif {"x0", "y0", "x1", "y1"}.issubset(bbox):
                x0, y0 = bbox["x0"], bbox["y0"]
                width, height = bbox["x1"] - x0, bbox["y1"] - y0
            else:
                continue
            grouped_blocks.setdefault(
                block.get("page_number", 1),
                [],
            ).append((y0 + height / 2, x0, block))

        for page_blocks in grouped_blocks.values():
            lines_by_y = []
            for center_y, _, block in sorted(page_blocks):
                if not lines_by_y or abs(center_y - lines_by_y[-1][0]) > 4:
                    lines_by_y.append([center_y, [block]])
                else:
                    lines_by_y[-1][1].append(block)

            for _, line_blocks in lines_by_y:
                line_blocks.sort(
                    key=lambda block: (
                        block.get("bbox", {}).get("x", block.get("bbox", {}).get("x0", 0))
                    )
                )
                line_token_blocks = []
                for block in line_blocks:
                    line_token_blocks.extend(
                        (
                            re.sub(r"[\W_]+", "", token.casefold()),
                            block,
                        )
                        for token in re.findall(
                            r"[\w]+(?:[.,/-][\w]+)*",
                            str(block.get("text", "")),
                            re.UNICODE,
                        )
                    )
                line_token_blocks = [
                    pair for pair in line_token_blocks if pair[0]
                ]
                line_tokens = [pair[0] for pair in line_token_blocks]
                for start in range(len(line_tokens) - len(target_tokens) + 1):
                    if line_tokens[start:start + len(target_tokens)] == target_tokens:
                        matches.extend(
                            block
                            for _, block in line_token_blocks[
                                start:start + len(target_tokens)
                            ]
                        )

        if not matches:
            target_set = set(target_tokens)
            for block in all_blocks:
                block_tokens = {
                    re.sub(r"[\W_]+", "", token.casefold())
                    for token in re.findall(
                        r"[\w]+(?:[.,/-][\w]+)*",
                        str(block.get("text", "")),
                        re.UNICODE,
                    )
                }
                if target_set.intersection(block_tokens):
                    matches.append(block)

        by_page = {}
        confidences = []

        for block in matches:
            bbox = block.get("bbox")
            if not isinstance(bbox, dict):
                continue

            page_number = block.get("page_number", 1)
            if {"x", "y", "width", "height"}.issubset(bbox):
                x0 = bbox["x"]
                y0 = bbox["y"]
                x1 = x0 + bbox["width"]
                y1 = y0 + bbox["height"]
            elif {"x0", "y0", "x1", "y1"}.issubset(bbox):
                x0, y0, x1, y1 = (
                    bbox["x0"],
                    bbox["y0"],
                    bbox["x1"],
                    bbox["y1"],
                )
            else:
                continue

            bounds = by_page.setdefault(
                page_number,
                [x0, y0, x1, y1],
            )
            bounds[0] = min(bounds[0], x0)
            bounds[1] = min(bounds[1], y0)
            bounds[2] = max(bounds[2], x1)
            bounds[3] = max(bounds[3], y1)

            confidence = block.get("confidence")
            if confidence is not None:
                confidences.append(float(confidence))

        locations = [
            {
                "page_number": page_number,
                "bbox": {
                    "x": bounds[0],
                    "y": bounds[1],
                    "width": bounds[2] - bounds[0],
                    "height": bounds[3] - bounds[1],
                },
            }
            for page_number, bounds in sorted(by_page.items())
        ]

        return locations, (
            sum(confidences) / len(confidences)
            if confidences else None
        )

    for field_name, patterns in FIELD_PATTERNS.items():

        for line_index, line in enumerate(lines):

            for pattern in patterns:
                if (
                    field_name == "purchase_order"
                    and line_index == 0
                    and line.strip().casefold() == "purchase order"
                ):
                    continue

                same_line_match = re.search(
                    rf"{pattern}\s*[:\-]\s*(.+)$",
                    line,
                    re.IGNORECASE,
                )
                if same_line_match:
                    raw_value = same_line_match.group(1)
                elif re.fullmatch(
                    rf"\s*(?:{pattern})\s*",
                    line,
                    re.IGNORECASE,
                ):
                    next_line = (
                        lines[line_index + 1].strip()
                        if line_index + 1 < len(lines)
                        else ""
                    )
                    if not next_line or is_field_label(next_line):
                        continue
                    raw_value = next_line
                else:
                    continue

                value = normalize_value(field_name, raw_value)
                if not value:
                    continue

                fields[field_name] = value
                locations, confidence = value_locations(value)
                field_metadata[field_name] = {
                    "confidence": confidence,
                    "locations": locations,
                }
                break

            if field_name in fields:
                break

    # PAN pattern fallback
    if "pan_number" not in fields:

        match = re.search(
            r"\b[A-Z]{5}[0-9]{4}[A-Z]\b",
            text.upper()
        )

        if match:
            fields["pan_number"] = match.group()

    # Email fallback
    if "email" not in fields:

        match = re.search(
            r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}",
            text
        )

        if match:
            fields["email"] = match.group()

    # Indian mobile number fallback
    if "phone" not in fields:

        match = re.search(
            r"(?<!\d)(?:\+91[- ]?)?[6-9]\d{9}(?!\d)",
            text
        )

        if match:
            fields["phone"] = match.group()

    return {
        "fields": fields,
        "field_metadata": field_metadata,
        "cleaned_text": clean_text(text)
    }


def normalize_extraction(ocr_result):

    text = ocr_result.get("full_text", "")
    pages = ocr_result.get("pages", [])

    result = extract_fields(text, pages)

    return {
        "document_text": result["cleaned_text"],
        "fields": result["fields"],
        "field_metadata": result["field_metadata"],
        "pages": pages
    }


class Relation(str, Enum):
    EXACT = "exact"
    FORMAT_ONLY = "format_only"
    COMPATIBLE = "compatible"
    TYPO = "typo"
    DIFFERENT = "different"
    UNCOMPARABLE = "uncomparable"


RELATION_RANK = {
    Relation.EXACT: 0,
    Relation.FORMAT_ONLY: 1,
    Relation.COMPATIBLE: 2,
    Relation.TYPO: 3,
    Relation.DIFFERENT: 4,
    Relation.UNCOMPARABLE: 5,
}
CONSISTENT = {Relation.EXACT, Relation.FORMAT_ONLY}


@dataclass
class Comparison:
    relation: Relation
    similarity: float = 0.0
    detail: str = ""
    ocr_confusable: bool = False
    magnitude: float = 0.0


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
    criticality: float
    unique: bool = True
    identity: bool = False
    best_match: bool = True


def _value_text(value: Optional[str]) -> str:
    return re.sub(r"\s+", " ", (value or "").replace("\u00a0", " ")).strip()


def _alnum(value: Optional[str]) -> str:
    return re.sub(r"[^A-Z0-9]", "", _value_text(value).upper())


def _similarity(left: str, right: str) -> float:
    return SequenceMatcher(None, left, right).ratio()


def _edit_distance(left: str, right: str) -> int:
    previous = list(range(len(right) + 1))
    for i, char_left in enumerate(left, 1):
        current = [i]
        for j, char_right in enumerate(right, 1):
            current.append(min(
                current[-1] + 1,
                previous[j] + 1,
                previous[j - 1] + (char_left != char_right),
            ))
        previous = current
    return previous[-1]


def is_blank_value(value: Optional[str]) -> bool:
    return not _value_text(value) or _value_text(value).lower() in {
        "n/a", "na", "nil", "none", "null", "unknown", "illegible",
        "unreadable", "not available", "not provided", "not readable",
        "---", "--", "-", ".", "?",
    }


def label_text(label: Optional[str]) -> str:
    label = _value_text(label).lower().replace("'", "").replace("\u2019", "")
    return re.sub(r"[^a-z0-9]+", " ", label).strip()


def infer_concept(field: ExtractedField) -> Concept:
    label = label_text(field.label)
    field_type = field.field_type
    if field_type == FieldType.OTHER:
        if re.search(r"\bname\b", label):
            field_type = FieldType.NAME
        elif re.search(r"\b(dob|date|birth|expiry|issued|issue)\b", label):
            field_type = FieldType.DATE
        elif re.search(r"\b(address|residence)\b", label):
            field_type = FieldType.ADDRESS
        elif re.search(r"\b(amount|income|salary|loan|balance|total|fee|premium|limit)\b", label):
            field_type = FieldType.AMOUNT
        elif re.search(r"\b(pan|aadhaar|aadhar|passport|account|license|voter|uid)\b", label):
            field_type = FieldType.ID_NUMBER

    if field_type == FieldType.NAME:
        for pattern, key, display, criticality, unique, identity in (
            (r"\bfathers?\b", "father_name", "father's name", 0.5, True, False),
            (r"\bmothers?\b", "mother_name", "mother's name", 0.5, True, False),
            (r"\b(spouse|husband|wife)\b", "spouse_name", "spouse's name", 0.5, True, False),
            (r"\b(guardian|parent)\b", "guardian_name", "guardian's name", 0.5, True, False),
            (r"\b(nominee|beneficiary|payee|witness|introducer|referee|guarantor|surety|co applicant|joint|"
             r"second holder|second applicant|signator|authorized|authorised|representative|contact person)\b",
             "third_party_name", "third-party name", 0.4, False, False),
            (r"\b(employer|company|organization|organisation|firm|business|institution|bank|branch|college|"
             r"university|school)\b", "organization_name", "organisation name", 0.5, False, False),
        ):
            if re.search(pattern, label):
                return Concept(key, Kind.NAME, display, criticality, unique, identity)
        return Concept("person_name", Kind.NAME, "name", 0.8, identity=True)

    if field_type == FieldType.DATE:
        if re.search(r"\b(dob|date of birth|birth date|born)\b", label):
            return Concept("date_of_birth", Kind.DATE, "date of birth", 0.9, identity=True)
        if re.search(r"\b(expiry|expiration|expires|validity|valid up to|valid until|valid till)\b", label):
            return Concept("expiry_date", Kind.DATE, "expiry date", 0.5)
        if re.search(r"\b(issue|issued|issuance)\b", label):
            return Concept("issue_date", Kind.DATE, "issue date", 0.5)
        return Concept(f"date:{label or 'unlabelled'}", Kind.DATE, _value_text(field.label) or "date", 0.5)

    if field_type == FieldType.AMOUNT:
        if re.search(r"\b(in words|words)\b", label) or (
            field.value.strip() and not re.search(r"\d", field.value)
        ):
            return Concept("amount_in_words", Kind.AMOUNT, "amount in words", 0.8, unique=False, best_match=False)
        if re.search(r"\b(loan|principal|sanctioned|facility|requested|limit)\b", label):
            return Concept("loan_amount", Kind.AMOUNT, "loan amount", 0.8, unique=False)
        if re.search(r"\b(income|salary|wage|earning|ctc|net pay|take home|remuneration)\b", label):
            return Concept("income", Kind.AMOUNT, "income", 0.8, unique=False)
        return Concept(f"amount:{label or 'unlabelled'}", Kind.AMOUNT, _value_text(field.label) or "amount", 0.6)

    if field_type == FieldType.ADDRESS:
        if "permanent" in label:
            return Concept("address_permanent", Kind.ADDRESS, "permanent address", 0.5)
        if re.search(r"\b(current|present|residential|residence|correspondence|communication|mailing)\b", label):
            return Concept("address_current", Kind.ADDRESS, "current address", 0.5)
        if re.search(r"\b(office|business|work|employer)\b", label):
            return Concept("address_office", Kind.ADDRESS, "office address", 0.4)
        return Concept("address", Kind.ADDRESS, "address", 0.5)

    if field_type in (FieldType.ID_NUMBER, FieldType.DOCUMENT_REFERENCE, FieldType.OTHER):
        if re.search(r"\bpan\b|permanent account", label) or re.fullmatch(r"[A-Z]{5}[0-9]{4}[A-Z]", _alnum(field.value)):
            return Concept("pan", Kind.IDENTIFIER, "PAN", 1.0, identity=True)
        if re.search(r"\b(aadhaar|aadhar|adhaar|uid|uidai)\b", label) or re.fullmatch(r"\d{12}", _alnum(field.value)):
            return Concept("aadhaar", Kind.IDENTIFIER, "Aadhaar number", 1.0, identity=True)
        if "passport" in label:
            return Concept("passport_number", Kind.IDENTIFIER, "passport number", 1.0, identity=True)
        if re.search(r"\b(account|acct)\b", label):
            return Concept("account_number", Kind.IDENTIFIER, "account number", 0.9, unique=False)
        kind = Kind.IDENTIFIER if field_type != FieldType.OTHER else Kind.TEXT
        return Concept(
            f"{field_type.value}:{label or 'unlabelled'}",
            kind,
            _value_text(field.label) or field_type.value.replace("_", " "),
            0.6 if kind == Kind.IDENTIFIER else 0.3,
            unique=False,
            best_match=False,
        )

    return Concept(f"{field_type.value}:{label or 'unlabelled'}", Kind.TEXT,
                   _value_text(field.label) or "text", 0.3, unique=False, best_match=False)


@dataclass(frozen=True)
class ParsedDate:
    candidates: tuple[date, ...]


_MONTHS = {name.lower(): number for number, name in enumerate(
    ("", "January", "February", "March", "April", "May", "June", "July", "August",
     "September", "October", "November", "December")) if name}
_MONTHS.update({name[:3]: number for name, number in tuple(_MONTHS.items())})


def parse_date(raw: Optional[str]) -> Optional[ParsedDate]:
    text = _value_text(raw).lower()
    if not text:
        return None
    formats = ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y",
               "%d/%m/%y", "%d-%m-%y", "%d %b %Y", "%d %B %Y",
               "%b %d, %Y", "%B %d, %Y")
    for date_format in formats:
        try:
            parsed = datetime.strptime(text, date_format).date()
            candidates = [parsed]
            if date_format in ("%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y"):
                try:
                    alternate = date(parsed.year, parsed.day, parsed.month)
                except ValueError:
                    pass
                else:
                    if alternate not in candidates:
                        candidates.append(alternate)
            return ParsedDate(tuple(candidates))
        except ValueError:
            continue
    return None


@dataclass(frozen=True)
class ParsedAmount:
    value: Decimal
    currency: Optional[str] = None


_NUMBER_WORDS = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11,
    "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16,
    "seventeen": 17, "eighteen": 18, "nineteen": 19, "twenty": 20, "thirty": 30,
    "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90,
}
_SCALES = {"hundred": 100, "thousand": 1_000, "lakh": 100_000, "lakhs": 100_000,
           "lac": 100_000, "lacs": 100_000, "million": 1_000_000, "crore": 10_000_000,
           "crores": 10_000_000}


def _amount_in_words(text: str) -> Optional[Decimal]:
    total = current = 0
    seen = False
    for word in re.findall(r"[a-z]+", text.lower()):
        if word in ("rupee", "rupees", "only", "and"):
            continue
        if word in _NUMBER_WORDS:
            current += _NUMBER_WORDS[word]
            seen = True
        elif word in _SCALES:
            scale = _SCALES[word]
            current = max(current, 1)
            if scale == 100:
                current *= scale
            else:
                total += current * scale
                current = 0
            seen = True
        else:
            return None
    return Decimal(total + current) if seen else None


def parse_amount(raw: Optional[str]) -> Optional[ParsedAmount]:
    text = _value_text(raw)
    if not text:
        return None
    lower = text.lower()
    currency = "INR" if re.search(r"\b(rs\.?|inr|rupees?)\b|₹", lower) else None
    match = re.search(r"\d[\d,]*(?:\.\d+)?", text)
    if match:
        try:
            value = Decimal(match.group().replace(",", ""))
        except InvalidOperation:
            return None
        suffix = re.match(r"\s*(k|thousand|lakhs?|lacs?|crores?|million|mn|billion|bn)\b",
                          text[match.end():], re.IGNORECASE)
        if suffix:
            factor = {"k": 1_000, "thousand": 1_000, "lakh": 100_000, "lakhs": 100_000,
                      "lac": 100_000, "lacs": 100_000, "crore": 10_000_000, "crores": 10_000_000,
                      "million": 1_000_000, "mn": 1_000_000, "billion": 1_000_000_000, "bn": 1_000_000_000}
            value *= factor[suffix.group(1).lower()]
        return ParsedAmount(value, currency)
    words = _amount_in_words(lower)
    return ParsedAmount(words, currency) if words is not None else None


def compare_amounts(a: str, b: str) -> Comparison:
    parsed_a, parsed_b = parse_amount(a), parse_amount(b)
    if parsed_a is None or parsed_b is None:
        return Comparison(Relation.UNCOMPARABLE, detail="an amount could not be read as a number")
    if parsed_a.value == parsed_b.value:
        same = _value_text(a).lower() == _value_text(b).lower()
        return Comparison(Relation.EXACT if same else Relation.FORMAT_ONLY, 1.0, "same amount")
    largest = max(abs(parsed_a.value), abs(parsed_b.value))
    magnitude = float(abs(parsed_a.value - parsed_b.value) / largest) if largest else 1.0
    sim = 1.0 - magnitude
    digits_a, digits_b = _alnum(str(parsed_a.value)), _alnum(str(parsed_b.value))
    if magnitude <= 0.002:
        relation = Relation.COMPATIBLE
    elif _edit_distance(digits_a, digits_b) <= 1:
        relation = Relation.TYPO
    else:
        relation = Relation.DIFFERENT
    return Comparison(relation, sim, f"{parsed_a.value} vs {parsed_b.value}", magnitude=magnitude)


def _name_tokens(value: Optional[str]) -> list[str]:
    tokens = re.findall(r"[a-z]+", _value_text(value).lower())
    return [token for token in tokens if token not in {"mr", "mrs", "ms", "miss", "dr", "shri", "sri", "smt"}]


def _compare_names(a: str, b: str) -> Comparison:
    left, right = _name_tokens(a), _name_tokens(b)
    if not left or not right:
        return Comparison(Relation.UNCOMPARABLE, detail="a name is empty")
    left_sorted, right_sorted = sorted(left), sorted(right)
    if left_sorted == right_sorted:
        relation = Relation.EXACT if _value_text(a).lower() == _value_text(b).lower() else Relation.FORMAT_ONLY
        return Comparison(relation, 1.0, "same name after normalisation")
    def covers(short: list[str], long: list[str]) -> bool:
        unmatched = list(long)
        for token in short:
            match = next((candidate for candidate in unmatched if candidate == token), None)
            if match is None and len(token) == 1:
                match = next((candidate for candidate in unmatched if candidate.startswith(token)), None)
            if match is None:
                return False
            unmatched.remove(match)
        return True

    if covers(left, right) or covers(right, left):
        return Comparison(Relation.COMPATIBLE, 0.9, "one name omits or abbreviates part of the other")
    similarity = _similarity(" ".join(left_sorted), " ".join(right_sorted))
    relation = Relation.TYPO if similarity >= 0.82 else Relation.DIFFERENT
    return Comparison(relation, similarity, "names differ")


def _address_tokens(value: Optional[str]) -> tuple[set[str], Optional[str]]:
    text = _value_text(value).lower()
    pins = re.findall(r"(?<!\d)(\d{5,6})(?!\d)", text)
    pin = pins[-1] if pins else None
    if pin:
        text = text.replace(pin, " ")
    tokens = re.findall(r"[a-z0-9]+", text)
    abbreviations = {"rd": "road", "st": "street", "ave": "avenue", "mg": "mg"}
    tokens = [abbreviations.get(token, token) for token in tokens if token not in {"the", "of", "and", "no", "at", "in"}]
    merged = []
    initial_group = ""
    for token in tokens:
        if len(token) == 1 and token.isalpha():
            initial_group += token
        else:
            if initial_group:
                merged.append(initial_group)
                initial_group = ""
            merged.append(token)
    if initial_group:
        merged.append(initial_group)
    return set(merged), pin


def _compare_addresses(a: str, b: str) -> Comparison:
    left, pin_left = _address_tokens(a)
    right, pin_right = _address_tokens(b)
    if not left or not right:
        return Comparison(Relation.UNCOMPARABLE, detail="an address is empty")
    if pin_left and pin_right and pin_left != pin_right:
        return Comparison(Relation.DIFFERENT, 0.0, f"postal codes differ ({pin_left} vs {pin_right})")
    overlap = len(left & right)
    similarity = overlap / len(left | right)
    if left == right:
        same = _value_text(a).lower() == _value_text(b).lower()
        return Comparison(Relation.EXACT if same else Relation.FORMAT_ONLY, 1.0, "same address after normalisation")
    if overlap / min(len(left), len(right)) >= 0.9:
        return Comparison(Relation.COMPATIBLE, similarity, "one address omits part of the other")
    return Comparison(Relation.TYPO if similarity >= 0.85 else Relation.DIFFERENT, similarity, "addresses differ")


def _ocr_confusable(a: str, b: str) -> bool:
    if len(a) != len(b):
        return False
    confusable = {frozenset(pair) for pair in ("0O", "1I", "1L", "17", "5S", "2Z", "8B")}
    changes = [(left, right) for left, right in zip(a.upper(), b.upper()) if left != right]
    return bool(changes) and all(frozenset(pair) in confusable for pair in changes)


def _compare_identifiers(a: str, b: str) -> Comparison:
    left, right = _alnum(a), _alnum(b)
    if not left or not right:
        return Comparison(Relation.UNCOMPARABLE, detail="an identifier is empty")
    masked_left = bool(re.search(r"[X*#\u2022]{3,}", _value_text(a).upper()))
    masked_right = bool(re.search(r"[X*#\u2022]{3,}", _value_text(b).upper()))

    def mask_tail(value: str, masked: bool) -> str:
        if not masked:
            return value
        return re.sub(r"^[X*#]+", "", value)

    if masked_left or masked_right:
        visible_left = mask_tail(left, masked_left)
        visible_right = mask_tail(right, masked_right)
        if visible_left and visible_right and (
            visible_left.endswith(visible_right) or visible_right.endswith(visible_left)
        ):
            return Comparison(Relation.FORMAT_ONLY, 1.0, "one value is masked; the visible characters match")
    if left == right:
        same = _value_text(a).upper() == _value_text(b).upper()
        return Comparison(Relation.EXACT if same else Relation.FORMAT_ONLY, 1.0, "same identifier")
    if _ocr_confusable(left, right):
        return Comparison(Relation.TYPO, _similarity(left, right), "identifiers differ by look-alike characters",
                          ocr_confusable=True)
    if len(left) == len(right) and _edit_distance(left, right) <= 2:
        return Comparison(Relation.TYPO, _similarity(left, right), "identifiers differ slightly")
    return Comparison(Relation.DIFFERENT, _similarity(left, right), "identifiers are different")


def compare_values(kind: Kind, a: str, b: str) -> Comparison:
    if kind == Kind.NAME:
        return _compare_names(a, b)
    if kind == Kind.AMOUNT:
        return compare_amounts(a, b)
    if kind == Kind.ADDRESS:
        return _compare_addresses(a, b)
    if kind == Kind.IDENTIFIER:
        return _compare_identifiers(a, b)
    if kind == Kind.DATE:
        date_a, date_b = parse_date(a), parse_date(b)
        if date_a is None or date_b is None:
            return Comparison(Relation.UNCOMPARABLE, detail="a date could not be parsed")
        if set(date_a.candidates) & set(date_b.candidates):
            same = date_a.candidates[0] == date_b.candidates[0]
            relation = Relation.EXACT if same and _value_text(a) == _value_text(b) else Relation.FORMAT_ONLY
            return Comparison(relation, 1.0, "same date")
        digits_a = date_a.candidates[0].strftime("%Y%m%d")
        digits_b = date_b.candidates[0].strftime("%Y%m%d")
        relation = Relation.TYPO if _edit_distance(digits_a, digits_b) <= 1 else Relation.DIFFERENT
        return Comparison(relation, _similarity(digits_a, digits_b), "dates differ",
                          ocr_confusable=_ocr_confusable(digits_a, digits_b))
    left, right = _value_text(a), _value_text(b)
    if not left or not right:
        return Comparison(Relation.UNCOMPARABLE, detail="a value is empty")
    if left.lower() == right.lower():
        return Comparison(Relation.EXACT, 1.0, "same text")
    similarity = _similarity(left.lower(), right.lower())
    return Comparison(Relation.TYPO if similarity >= 0.9 else Relation.DIFFERENT, similarity, "texts differ")


@dataclass
class IdFormatCheck:
    valid: bool
    expected: str
    repaired: Optional[str] = None
    repair_note: Optional[str] = None


_IDENTIFIER_FORMATS = {
    "pan": (re.compile(r"[A-Z]{5}[0-9]{4}[A-Z]"), "5 letters, 4 digits, 1 letter"),
    "aadhaar": (re.compile(r"[0-9]{12}"), "12 digits"),
    "passport_number": (re.compile(r"[A-Z][0-9]{7}"), "1 letter followed by 7 digits"),
}
_LOOKALIKE_ALTERNATIVES = {"Z": "2", "2": "Z", "O": "0", "0": "O", "I": "1", "1": "I", "S": "5", "5": "S"}


def check_identifier_format(concept_key: str, raw: Optional[str]) -> Optional[IdFormatCheck]:
    specification = _IDENTIFIER_FORMATS.get(concept_key)
    value = _alnum(raw)
    if specification is None or not value or re.search(r"[X*#\u2022]{3,}", _value_text(raw).upper()):
        return None
    pattern, expected = specification
    if pattern.fullmatch(value):
        return IdFormatCheck(True, expected)
    repairs = []
    for index, character in enumerate(value):
        alternate = _LOOKALIKE_ALTERNATIVES.get(character)
        candidate = value[:index] + alternate + value[index + 1:] if alternate else ""
        if candidate and pattern.fullmatch(candidate):
            repairs.append((index, character, alternate, candidate))
    if len(repairs) == 1:
        index, character, alternate, candidate = repairs[0]
        return IdFormatCheck(False, expected, candidate,
                             f"becomes valid if '{character}' at position {index + 1} is read as '{alternate}'")
    return IdFormatCheck(False, expected)


def display_normalized(kind: Kind, raw: Optional[str]) -> Optional[str]:
    if kind == Kind.NAME:
        return " ".join(_name_tokens(raw)) or None
    if kind == Kind.IDENTIFIER:
        return _alnum(raw) or None
    if kind == Kind.AMOUNT:
        parsed = parse_amount(raw)
        return f"{parsed.value.normalize()}" if parsed else None
    if kind == Kind.DATE:
        parsed = parse_date(raw)
        return parsed.candidates[0].isoformat() if parsed else None
    if kind == Kind.ADDRESS:
        return " ".join(sorted(_address_tokens(raw)[0])) or None
    return _value_text(raw).lower() or None
