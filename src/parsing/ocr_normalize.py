"""
Post-OCR text cleanup before resume parsing (name, email, years, structure).

Tesseract often inserts spaces between letters (header names), around @ and dots
in emails, and between digits in years. Normalizing early improves downstream
extract_primary_email, resolve_candidate_full_name, and estimate_years_experience.
"""
from __future__ import annotations

import re

# 3-letter first names: allow surname break after 3 letters when OCR uses single spaces only.
# Boost OCR two-token splits when the second token is a very common family name
# (fixes "A h m a d A l i" without a dictionary of all first names).
_OCR_SURNAME_HINT = frozenset(
    {
        "ali",
        "khan",
        "lee",
        "li",
        "wang",
        "zhang",
        "liu",
        "chen",
        "yang",
        "singh",
        "kumar",
        "patel",
        "sharma",
        "verma",
        "malik",
        "raza",
        "syed",
        "hussain",
        "naqvi",
        "jafri",
        "abbas",
        "rizvi",
        "ansari",
        "butt",
        "sheikh",
        "mirza",
        "iqbal",
        "farooq",
        "siddiqui",
        "qureshi",
        "nawaz",
        "rehman",
        "yousaf",
        "yousuf",
        "akhtar",
        "mahmood",
        "rao",
        "reddy",
        "nair",
        "menon",
        "joshi",
        "desai",
        "kapoor",
        "gupta",
        "bose",
        "roy",
        "das",
        "sen",
        "kim",
        "park",
        "choi",
        "nguyen",
        "tran",
        "pham",
        "garcia",
        "rodriguez",
        "martinez",
        "lopez",
        "gonzalez",
        "perez",
        "sanchez",
        "torres",
        "flores",
        "rivera",
        "diaz",
        "smith",
        "jones",
        "brown",
        "taylor",
        "thomas",
        "jackson",
        "white",
        "harris",
        "martin",
        "clark",
        "lewis",
        "walker",
        "hall",
        "allen",
        "young",
        "king",
        "wright",
        "scott",
        "green",
        "baker",
        "adams",
        "nelson",
        "carter",
        "mitchell",
        "roberts",
        "turner",
        "phillips",
        "campbell",
        "parker",
        "evans",
        "edwards",
        "collins",
        "stewart",
        "morris",
        "rogers",
        "reed",
        "cook",
        "morgan",
        "bell",
        "murphy",
        "bailey",
        "cooper",
        "richardson",
        "cox",
        "howard",
        "ward",
        "peterson",
        "gray",
        "ramirez",
        "james",
        "watson",
        "brooks",
        "kelly",
        "sanders",
        "price",
        "bennett",
        "wood",
        "barnes",
        "ross",
        "henderson",
        "coleman",
        "jenkins",
        "perry",
        "powell",
        "long",
        "patterson",
        "hughes",
        "washington",
        "butler",
        "simmons",
        "foster",
        "gonzales",
        "bryant",
        "alexander",
        "russell",
        "griffin",
        "hayes",
        "sherazi",
        "siddiqi",
        "hashmi",
        "chaudhry",
    }
)

# Two-letter given names common in East Asian / transliterated headers (``L i M i n g``).
_OCR_SHORT_FIRST = frozenset({"li", "wu", "lu", "ma", "yu", "xu", "he", "hu", "su", "bo", "jo", "qi", "an"})


def _score_ocr_spaced_two_word_split(w1: str, w2: str) -> float:
    sc = 0.0
    for w in (w1, w2):
        if len(w) < 2:
            return -1e9
        low = w.lower()
        vow = sum(1 for c in low if c in "aeiouy")
        if vow == 0:
            return -1e9
        sc += vow * 1.15 + min(len(w), 11) * 0.85
    sc -= 0.4 * abs(len(w1) - len(w2))
    lo2 = w2.lower()
    if lo2 in _OCR_SURNAME_HINT:
        sc += 24.0
    lo1 = w1.lower()
    if len(w1) == 2 and lo1 in _OCR_SHORT_FIRST and len(w2) >= 3:
        sc += 16.0
    # Short trailing token after a long given name (e.g. Li, Wu) — light boost when not in hint set.
    if len(w1) >= 5 and 2 <= len(w2) <= 4:
        sc += 3.0
    return sc


def _best_two_word_spaced_singles(s: str) -> str | None:
    """
    Split a run like ``AhmadAli`` (from ``A h m a d A l i``) into ``Ahmad Ali``.

    Greedy ``ahead`` counting used elsewhere merges the tail of the first name with the
    surname (``d`` + ``Ali``), which triggers a bogus break after ``Ahma``.
    """
    n = len(s)
    if n < 6:
        return None
    scored: list[tuple[float, int]] = []
    for k in range(2, min(16, n - 2)):
        w1, w2 = s[:k], s[k:]
        if len(w2) < 2:
            continue
        if k < 3 and len(w2) < 4:
            continue
        if n >= 7 and len(w2) < 3:
            continue
        sc = _score_ocr_spaced_two_word_split(w1, w2)
        scored.append((sc, k))
    if not scored:
        return None
    scored.sort(key=lambda t: (-t[0], abs(t[1] - n // 2)))
    top, k_best = scored[0][0], scored[0][1]
    if len(scored) > 1 and top - scored[1][0] < 1.25:
        # Ambiguous (e.g. long single given name); keep one token.
        return None
    w1b, w2b = s[:k_best], s[k_best:]
    if _score_ocr_spaced_two_word_split(w1b, w2b) < 8.5:
        return None
    return f"{w1b} {w2b}"


def _score_one_ocr_name_token(w: str) -> float:
    if len(w) < 2:
        return -1e9
    low = w.lower()
    vow = sum(1 for c in low if c in "aeiouy")
    if vow == 0:
        return -1e9
    return vow * 1.1 + min(len(w), 12) * 0.9


def _best_three_word_spaced_singles(s: str) -> str | None:
    """
    Reconstruct e.g. ``A h s a n F a r h a n S h e r a z i`` → three tokens (``Ahsan Farhan Sherazi``).
    The two-way splitter cannot express three name parts; without this the greedy fallback mangles
    the line and name extraction can pick a garbage line instead.
    """
    n = len(s)
    if n < 10 or n > 50:
        return None
    best_sc = -1e9
    best: tuple[int, int] | None = None
    for k1 in range(3, min(12, n - 5)):
        for k2 in range(k1 + 2, min(n - 1, k1 + 12)):
            if n - k2 < 2:
                continue
            w1, w2, w3 = s[:k1], s[k1:k2], s[k2:]
            if not (2 <= len(w1) <= 12 and 2 <= len(w2) <= 12 and 2 <= len(w3) <= 12):
                continue
            sc = _score_one_ocr_name_token(w1) + _score_one_ocr_name_token(w2) + _score_one_ocr_name_token(w3)
            sc -= 0.2 * (abs(len(w1) - len(w2)) + abs(len(w2) - len(w3)))
            w1l, w2l, w3l = w1.lower(), w2.lower(), w3.lower()
            if w3l in _OCR_SURNAME_HINT:
                sc += 18.0
            if w2l in _OCR_SURNAME_HINT:
                sc += 10.0
            if w1l in _OCR_SHORT_FIRST and len(w1) <= 3:
                sc += 5.0
            if sc > best_sc:
                best_sc = sc
                best = (k1, k2)
    if best is None or best_sc < 22.0:
        return None
    k1, k2 = best
    return f"{s[:k1]} {s[k1:k2]} {s[k2:]}"


_COMMON_3_FIRST = frozenset(
    {
        "ali",
        "amy",
        "ann",
        "ava",
        "ben",
        "bob",
        "dan",
        "dee",
        "eli",
        "eva",
        "ian",
        "jim",
        "joe",
        "joy",
        "kim",
        "leo",
        "liz",
        "max",
        "mia",
        "raj",
        "ray",
        "rob",
        "roy",
        "sam",
        "sue",
        "tom",
        "zac",
        "zoe",
    }
)


def _collapse_spaced_ocr_join_singles(chunk: str, *, break_for_surname: bool) -> str:
    """
    Collapse spaced single letters inside one chunk (e.g. 'J o h n' or 'S m i t h').
    If break_for_surname, split 'John Smith' style runs (single spaces only); otherwise
    merge every consecutive single-letter token into one word (for job titles, etc.).
    """
    s = chunk.strip()
    if not s or len(s) > 120:
        return chunk
    parts = s.split()
    if len(parts) < 4:
        return chunk
    # Entire line/chunk is spaced letters (``A h m a d A l i``). Greedy lookahead counts
    # the rest of the line as one run and can split after ``Ahma``; enumerate a 2-word split.
    if (
        break_for_surname
        and len(parts) >= 6
        and all(len(p) == 1 and p.isalpha() for p in parts)
    ):
        flat = "".join(parts)
        # Long single-space headers are often "First Middle Last" in South Asian / US résumés.
        if len(parts) >= 10 and len(flat) >= 14:
            three = _best_three_word_spaced_singles(flat)
            if three:
                return three
        two = _best_two_word_spaced_singles(flat)
        if two:
            return two
    singles = sum(1 for p in parts if len(p) == 1 and p.isalpha())
    if singles / len(parts) < 0.42:
        return chunk
    if sum(1 for p in parts if any(c.isdigit() for c in p)) > len(parts) * 0.25:
        return chunk

    def _should_break(buf: list[str], ahead: int) -> bool:
        if not break_for_surname or ahead < 4:
            return False
        n = len(buf)
        if 4 <= n <= 12:
            return True
        if n == 3 and "".join(buf).lower() in _COMMON_3_FIRST:
            return True
        return False

    i = 0
    words: list[str] = []
    while i < len(parts):
        p = parts[i]
        if len(p) == 1 and p.isalpha():
            buf = [p]
            i += 1
            while i < len(parts) and len(parts[i]) == 1 and parts[i].isalpha():
                j = i
                ahead = 0
                while j < len(parts) and len(parts[j]) == 1 and parts[j].isalpha():
                    ahead += 1
                    j += 1
                if _should_break(buf, ahead):
                    break
                buf.append(parts[i])
                i += 1
            if len(buf) >= 2:
                words.append("".join(buf))
            else:
                words.append(buf[0])
        else:
            words.append(p)
            i += 1
    out = " ".join(words)
    return out if len(out) >= 2 else chunk


def _collapse_spaced_ocr_header_line(line: str, line_index: int = 0) -> str:
    """
    If a line looks like spaced-out letters (e.g. 'J o h n   S m i t h'), collapse
    single-letter runs. Double spaces / tabs mark word boundaries (names, titles after years).
    """
    s = line.strip()
    if not s or len(s) > 120:
        return line
    if re.search(r"\s{2,}", s):
        chunks = re.split(r"\s{2,}", s)
        merged = [_collapse_spaced_ocr_join_singles(ch, break_for_surname=False) for ch in chunks]
        merged = [m.strip() for m in merged if m.strip()]
        out = " ".join(merged)
        return out if len(out) >= 4 else line
    if line_index < 4:
        return _collapse_spaced_ocr_join_singles(s, break_for_surname=True)
    return _collapse_spaced_ocr_join_singles(s, break_for_surname=False)


def _domain_consumed_len(right: str, dom_c: str) -> int | None:
    """Minimal prefix length of `right` whose stripped domain chars equal dom_c."""
    want = dom_c.lower()
    acc = []
    for k in range(1, len(right) + 1):
        ch = right[k - 1]
        if ch.isalnum() or ch in ".-":
            acc.append(ch.lower())
        cur = "".join(acc)
        if cur == want:
            return k
        if len(cur) > len(want) or (len(cur) == len(want) and cur != want):
            return None
    return None


def _collapse_spaced_email_in_line(line: str) -> str:
    """Remove spaces inside a spaced OCR email (local@domain.tld)."""
    if "@" not in line:
        return line

    def _compact_at_index(at: int) -> tuple[str, int, int] | None:
        left, right = line[:at], line[at + 1 :]
        mpre = re.search(r"(?i)^(.*?\b(?:e[-_]?mail|contact)\s*[:=#]?\s*)(.*)$", left)
        if mpre:
            prefix, local_raw = mpre.group(1), mpre.group(2)
        else:
            prefix, local_raw = "", left
        local_c = re.sub(r"[^A-Za-z0-9._%+-]", "", local_raw)
        dom_c = re.sub(r"[^A-Za-z0-9.-]", "", right)
        if not local_c or "@" in local_c or "." not in dom_c:
            return None
        tld = dom_c.rsplit(".", 1)[-1]
        if len(tld) < 2 or not tld.isalpha():
            return None
        if not re.match(r"^[\w.%+-]+$", local_c):
            return None
        dom_len = _domain_consumed_len(right, dom_c)
        if dom_len is None:
            return None
        compact = f"{local_c}@{dom_c}"
        start = len(prefix)
        end = at + 1 + dom_len
        return compact, start, end

    for m in re.finditer("@", line):
        got = _compact_at_index(m.start())
        if got:
            compact, start, end = got
            return line[:start] + compact + line[end:]
    m = re.search(
        r"([\w.%+-][\w.%+\s-]{0,80}?)\s*@\s*([\w.\s-]{1,100}\.[A-Za-z]{2,24})\b",
        line,
        re.IGNORECASE,
    )
    if not m:
        return _repair_email_line_spacing(line)
    local_raw = m.group(1).strip()
    dom_raw = m.group(2).strip()
    local_raw = re.sub(r"^.*?\b(?:e[-_]?mail|contact)\s*[:=#]?\s*", "", local_raw, flags=re.IGNORECASE)
    local_c = re.sub(r"\s+", "", local_raw)
    dom_c = re.sub(r"\s+", "", dom_raw)
    if not local_c or "@" in local_c or not dom_c.count("."):
        return _repair_email_line_spacing(line)
    compact = f"{local_c}@{dom_c}"
    return line[: m.start()] + compact + line[m.end() :]


def _repair_email_line_spacing(line: str) -> str:
    """Fix spaces around @ and dots on lines that contain an email."""
    if "@" not in line:
        return line
    ln = line
    ln = re.sub(r"(?<=[\w.%+-])\s+@\s+", "@", ln)
    ln = re.sub(r"\s+@\s+", "@", ln)
    ln = re.sub(r"(?<=@[\w.%+-])\s+\.\s+", ".", ln)
    ln = re.sub(
        r"\s+\.\s+(com|org|net|edu|io|co|uk|pk|in|de|fr|gov|ai|app|dev)\b",
        r".\1",
        ln,
        flags=re.IGNORECASE,
    )
    return ln


def _normalize_spaced_section_words(text: str) -> str:
    """Fix common OCR spacing in section headers and small words."""
    t = text
    replacements = (
        (r"(?i)\b(e\s*x\s*p\s*e\s*r\s*i\s*e\s*n\s*c\s*e)\b", "Experience"),
        (r"(?i)\b(w\s*o\s*r\s*k\s*e\s*x\s*p\s*e\s*r\s*i\s*e\s*n\s*c\s*e)\b", "Work Experience"),
        (r"(?i)\b(p\s*r\s*o\s*f\s*e\s*s\s*s\s*i\s*o\s*n\s*a\s*l\s*e\s*x\s*p\s*e\s*r\s*i\s*e\s*n\s*c\s*e)\b", "Professional Experience"),
        (r"(?i)\b(e\s*d\s*u\s*c\s*a\s*t\s*i\s*o\s*n)\b", "Education"),
        (r"(?i)\b(c\s*o\s*n\s*t\s*a\s*c\s*t)\b", "Contact"),
        (r"(?i)\b(e\s*[-]?\s*m\s*a\s*i\s*l)\b", "Email"),
        (r"(?i)\b(s\s*u\s*m\s*m\s*a\s*r\s*y)\b", "Summary"),
        (r"(?i)\b(p\s*r\s*o\s*f\s*i\s*l\s*e)\b", "Profile"),
        (r"(?i)\b(o\s*f)\b", "of"),
    )
    for pat, repl in replacements:
        t = re.sub(pat, repl, t)
    return t


def _collapse_year_token(tok: str) -> str:
    s = re.sub(r"\s+", "", tok.strip())
    if re.match(r"^(19|20)\d{2}$", s):
        return s
    return tok.strip()


def _collapse_spaced_digits_in_years(text: str) -> str:
    """Collapse spaces between digits in 4-digit years and common year ranges."""

    def fix_year_range(m: re.Match) -> str:
        full = m.group(0)
        msep = re.search(r"[-–—]+", full)
        if not msep:
            return full
        a, b = full[: msep.start()], full[msep.end() :]
        a2 = _collapse_year_token(a)
        b_stripped = b.strip()
        if re.match(r"(?i)present|current|now|ongoing", b_stripped):
            return f"{a2}-{b_stripped.lower().split()[0]}"
        b2 = _collapse_year_token(b_stripped)
        return f"{a2}-{b2}"

    t = re.sub(
        r"(?<![0-9])(?:\d(?:\s+\d){3})\s*[-–—]{1,2}\s*(?:(?:\d(?:\s+\d){3})|present|current|now|ongoing)\b",
        fix_year_range,
        text,
        flags=re.IGNORECASE,
    )
    t = re.sub(r"(?<!\d)(?:\d(?:\s+\d){3})(?!\d)", lambda m: re.sub(r"\s+", "", m.group(0)), t)
    t = re.sub(r"(?i)(\d{1,2}(?:\.\d)?)\s*\+\s*(years?|yrs|yr)\b", r"\1+ \2", t)
    return t


def _normalize_spaced_years_word(text: str) -> str:
    """y e a r s → years, y e a r → year (word boundaries)."""
    t = re.sub(r"(?i)\by\s*e\s*a\s*r\s*s\b", "years", text)
    t = re.sub(r"(?i)\by\s*e\s*a\s*r\b", "year", t)
    t = re.sub(r"(?i)\by\s*r\s*s\b", "yrs", t)
    return t


def _normalize_name_label_ocr(text: str) -> str:
    """N a m e : → Name: (first ~18 lines)."""
    lines = text.split("\n")
    out: list[str] = []
    for i, ln in enumerate(lines):
        if i < 18:
            ln2 = re.sub(r"(?i)\b(n)\s*(a)\s*(m)\s*(e)\s*([:;])", r"Name\5", ln)
            ln2 = re.sub(r"(?i)\b(f\s*u\s*l\s*l\s*n\s*a\s*m\s*e)\s*([:;])", r"Full name\2", ln2)
            out.append(ln2)
        else:
            out.append(ln)
    return "\n".join(out)


def normalize_resume_text_for_ocr(text: str) -> str:
    """
    Apply OCR-oriented fixes to raw extracted text before email/name/years parsing.
    Safe for non-OCR text (mostly no-ops when patterns don't match).
    """
    if not isinstance(text, str) or not text.strip():
        return text or ""

    t = text.replace("\r\n", "\n").replace("\r", "\n")
    t = t.replace("\u00a0", " ").replace("\u2009", " ").replace("\u200b", "").replace("\u200c", "").replace("\ufeff", "")
    t = _normalize_spaced_section_words(t)
    t = _normalize_spaced_years_word(t)
    t = _collapse_spaced_digits_in_years(t)
    t = _normalize_name_label_ocr(t)

    lines = t.split("\n")
    fixed: list[str] = []
    for i, ln in enumerate(lines):
        if i < 36:
            if "@" in ln:
                ln = _collapse_spaced_email_in_line(ln)
                ln = _repair_email_line_spacing(ln)
                at = ln.find("@")
                if at > 0:
                    left = _collapse_spaced_ocr_header_line(ln[:at].strip(), line_index=i)
                    ln = (left + ln[at:]).strip() if left else ln
            else:
                ln = _collapse_spaced_ocr_header_line(ln, line_index=i)
        fixed.append(ln)
    return "\n".join(fixed)
