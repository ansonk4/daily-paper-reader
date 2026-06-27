#!/usr/bin/env python

import hashlib
import html
import io
import json
import os
import re
import tarfile
import time
from datetime import datetime, timezone
from typing import Any, Dict, List

import requests


AUTHOR_RELEVANCE_WEIGHT = 0.60
AUTHOR_BACKGROUND_WEIGHT = 0.40
AUTHOR_PROFILE_EXTRACTION_VERSION = "author-profile-extraction-v3"
AUTHOR_RATING_RUBRIC_VERSION = "author-rating-rubric-v5"
AUTHOR_RATING_LLM_BATCH_SIZE = 10
GENERIC_AUTHOR_RATING_EXPLANATION = "Author rating synthesized from available public metadata."


def norm_text(value: Any) -> str:
    return str(value or "").strip()


def normalize_author_name(value: Any) -> str:
    text = norm_text(value).lower()
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"[^a-z0-9\u00c0-\u024f\u4e00-\u9fff ]+", "", text)
    return text.strip()


def normalize_title(value: Any) -> str:
    text = norm_text(value).lower()
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"[^a-z0-9 ]+", "", text)
    return text.strip()


def clamp_score(value: Any) -> float:
    try:
        score = float(value)
    except Exception:
        score = 0.0
    return max(0.0, min(10.0, score))


def _coerce_count(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value >= 0 else None
    if isinstance(value, float):
        if value < 0 or not value.is_integer():
            return None
        return int(value)
    text = norm_text(value).replace(",", "")
    if not re.fullmatch(r"\d+", text):
        return None
    return int(text)


def _first_count(*values: Any) -> int | None:
    for value in values:
        count = _coerce_count(value)
        if count is not None:
            return count
    return None


def _count_from_citation_hints(hints: Any, field_names: List[str]) -> int | None:
    text = norm_text(hints)
    if not text:
        return None
    for field in field_names:
        match = re.search(rf"\b{re.escape(field)}\s*=\s*([0-9][0-9,]*)", text)
        if match:
            return _coerce_count(match.group(1))
    return None


def _profile_metric_count(profile: Dict[str, Any], metric: str) -> int | None:
    openalex = profile.get("openalex") if isinstance(profile.get("openalex"), dict) else {}
    semantic = profile.get("semantic_scholar") if isinstance(profile.get("semantic_scholar"), dict) else {}
    if metric == "citation":
        return _first_count(
            profile.get("citation_count"),
            semantic.get("citation_count"),
            profile.get("cited_by_count"),
            openalex.get("cited_by_count"),
            _count_from_citation_hints(profile.get("citation_hints"), ["citation_count", "cited_by_count"]),
        )
    if metric == "paper":
        return _first_count(
            profile.get("paper_count"),
            semantic.get("paper_count"),
            profile.get("works_count"),
            openalex.get("works_count"),
            _count_from_citation_hints(profile.get("citation_hints"), ["paper_count", "works_count"]),
        )
    return None


def _count_text(value: Any) -> str:
    count = _coerce_count(value)
    return str(count) if count is not None else ""


def combine_relevance_author_scores(relevance_score: Any, author_score: Any) -> float:
    score = (
        AUTHOR_RELEVANCE_WEIGHT * clamp_score(relevance_score)
        + AUTHOR_BACKGROUND_WEIGHT * clamp_score(author_score)
    )
    return round(max(0.0, min(10.0, score)), 4)


def _as_author_record(item: Any, index: int) -> Dict[str, Any]:
    if isinstance(item, dict):
        name = norm_text(item.get("name") or item.get("display_name") or item.get("author") or item.get("full_name"))
        record = dict(item)
        record["name"] = name
    else:
        record = {"name": norm_text(item)}
    record["index"] = index
    return record


def _paper_authors(paper: Dict[str, Any]) -> List[Dict[str, Any]]:
    raw = paper.get("authors") or paper.get("author_infos") or paper.get("authors_info") or []
    if isinstance(raw, str):
        items: List[Any] = [part.strip() for part in re.split(r",|，", raw) if part.strip()]
    elif isinstance(raw, list):
        items = raw
    else:
        items = []
    return [record for idx, item in enumerate(items) if (record := _as_author_record(item, idx)).get("name")]


def _append_unique(items: List[str], value: Any) -> None:
    text = norm_text(value)
    if text and text not in items:
        items.append(text)


def _text_values(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if norm_text(value) else []
    if isinstance(value, dict):
        out: List[str] = []
        for key in (
            "name",
            "display_name",
            "affiliation",
            "institution",
            "organization",
            "department",
            "school",
            "group",
            "company",
        ):
            out.extend(_text_values(value.get(key)))
        return out
    if isinstance(value, list):
        out = []
        for item in value:
            out.extend(_text_values(item))
        return out
    text = norm_text(value)
    return [text] if text else []


def _extract_named_affiliations(raw: Any, focus: Dict[str, Any]) -> List[str]:
    name = focus.get("name")
    role = norm_text(focus.get("role"))
    out: List[str] = []
    if isinstance(raw, dict):
        for key, value in raw.items():
            if _names_match(name, key) or (role and norm_text(key) == role):
                for text in _text_values(value):
                    _append_unique(out, text)
        return out
    if isinstance(raw, list):
        for idx, item in enumerate(raw):
            if isinstance(item, dict):
                item_name = item.get("name") or item.get("display_name") or item.get("author")
                if _names_match(name, item_name) or idx == int(focus.get("index") or -1):
                    for key in (
                        "affiliation",
                        "affiliations",
                        "raw_affiliation",
                        "raw_affiliations",
                        "institution",
                        "institutions",
                        "organization",
                        "organizations",
                        "department",
                        "departments",
                    ):
                        for text in _text_values(item.get(key)):
                            _append_unique(out, text)
            else:
                for text in _extract_named_affiliations(norm_text(item), focus):
                    _append_unique(out, text)
        return out
    text = norm_text(raw)
    if not text:
        return out
    parts = [p.strip() for p in re.split(r";|\n", text) if p.strip()]
    for part in parts:
        m = re.match(r"^(.+?)(?:\s*\([^)]*\))?\s*[:：]\s*(.+)$", part)
        if not m:
            continue
        label = re.sub(r"\([^)]*\)", "", m.group(1)).strip()
        if _names_match(name, label) or (role and label == role):
            _append_unique(out, m.group(2))
    return out


def _local_author_metadata(paper: Dict[str, Any], focus: Dict[str, Any]) -> Dict[str, Any]:
    metadata = focus.get("metadata") if isinstance(focus.get("metadata"), dict) else {}
    affiliations: List[str] = []
    for key in (
        "affiliation",
        "affiliations",
        "raw_affiliation",
        "raw_affiliations",
        "raw_affiliation_string",
        "raw_affiliation_strings",
        "institution",
        "institutions",
        "organization",
        "organizations",
        "department",
        "departments",
    ):
        for text in _text_values(metadata.get(key)):
            _append_unique(affiliations, text)
    for key in (
        "author_affiliations",
        "author_affiliation",
        "affiliations",
        "author_row",
        "authors_row",
        "paper_author_row",
        "author_metadata",
    ):
        for text in _extract_named_affiliations(paper.get(key), focus):
            _append_unique(affiliations, text)
    for key in ("group", "lab", "school", "university", "company", "employer"):
        for text in _text_values(metadata.get(key)):
            _append_unique(affiliations, text)
    return {
        "source": "paper_author_row" if affiliations else "",
        "affiliations": affiliations,
    }


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    text = norm_text(value).lower()
    return text in {"1", "true", "yes", "y", "equal", "co-first", "cofirst", "shared"}


def _marked_equal_contribution(record: Dict[str, Any]) -> bool:
    keys = (
        "equal_contribution",
        "co_first",
        "cofirst",
        "co_first_author",
        "is_co_first",
        "is_cofirst",
        "shared_first_authorship",
    )
    if any(_truthy(record.get(key)) for key in keys):
        return True
    joined = " ".join(
        norm_text(record.get(key))
        for key in ("note", "notes", "contribution", "contribution_note", "author_note", "marker")
    ).lower()
    return bool(re.search(r"\b(equal contribution|co[- ]?first|joint first|shared first)\b", joined))


def _paper_equal_contribution_names(paper: Dict[str, Any]) -> set[str]:
    raw = (
        paper.get("equal_contribution_authors")
        or paper.get("co_first_authors")
        or paper.get("cofirst_authors")
        or []
    )
    if isinstance(raw, str):
        items: List[Any] = [part.strip() for part in re.split(r",|，", raw) if part.strip()]
    elif isinstance(raw, list):
        items = raw
    else:
        items = []
    names: set[str] = set()
    for item in items:
        if isinstance(item, int):
            continue
        if isinstance(item, dict):
            item = item.get("name") or item.get("display_name")
        name = normalize_author_name(item)
        if name:
            names.add(name)
    return names


def _paper_equal_contribution_indices(paper: Dict[str, Any]) -> set[int]:
    raw = (
        paper.get("equal_contribution_authors")
        or paper.get("co_first_authors")
        or paper.get("cofirst_authors")
        or []
    )
    if not isinstance(raw, list):
        return set()
    indices: set[int] = set()
    for item in raw:
        if isinstance(item, int):
            indices.add(item)
        elif isinstance(item, str) and item.strip().isdigit():
            indices.add(int(item.strip()))
    return indices


def select_focus_authors(paper: Dict[str, Any]) -> List[Dict[str, Any]]:
    authors = _paper_authors(paper)
    if not authors:
        return []

    equal_names = _paper_equal_contribution_names(paper)
    equal_indices = _paper_equal_contribution_indices(paper)
    selected: List[Dict[str, Any]] = []
    seen: set[str] = set()

    def add(record: Dict[str, Any], role: str) -> None:
        name = norm_text(record.get("name"))
        key = normalize_author_name(name)
        if not key or key in seen:
            return
        seen.add(key)
        selected.append(
            {
                "name": name,
                "role": role,
                "index": int(record.get("index") or 0),
                "metadata": {k: v for k, v in record.items() if k not in {"name", "role", "index"}},
            }
        )

    add(authors[0], "first_author")
    for record in authors[1:]:
        index = int(record.get("index") or 0)
        name_key = normalize_author_name(record.get("name"))
        if (
            _marked_equal_contribution(record)
            or name_key in equal_names
            or index in equal_indices
            or (index + 1) in equal_indices
        ):
            add(record, "co_first_author")

    if len(authors) > 1:
        add(authors[-1], "last_author")
    return selected


def _safe_filename(key: str) -> str:
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:24]
    slug = re.sub(r"[^a-z0-9]+", "-", key.lower()).strip("-")[:70]
    return f"{slug or 'author'}-{digest}.json"


def _read_json(path: str) -> Dict[str, Any] | None:
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def _write_json(path: str, data: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def _extract_year(paper: Dict[str, Any]) -> str:
    for key in ("year", "published", "date", "updated"):
        text = norm_text(paper.get(key))
        m = re.search(r"(19|20)\d{2}", text)
        if m:
            return m.group(0)
    return ""


def _names_match(a: Any, b: Any) -> bool:
    aa = normalize_author_name(a)
    bb = normalize_author_name(b)
    if not aa or not bb:
        return False
    return aa == bb or aa.split()[-1:] == bb.split()[-1:] and aa[0] == bb[0]


def _name_appears_in_text(name: Any, text: Any) -> bool:
    nn = normalize_author_name(name)
    tt = normalize_author_name(text)
    return bool(nn and tt and (nn in tt or _names_match(name, text)))


def _author_at_role(authorships: List[Dict[str, Any]], focus: Dict[str, Any]) -> Dict[str, Any] | None:
    if not authorships:
        return None
    name = focus.get("name")
    for authorship in authorships:
        author = authorship.get("author") if isinstance(authorship.get("author"), dict) else {}
        if _names_match(name, author.get("display_name") or authorship.get("name")):
            return authorship
    idx = int(focus.get("index") or 0)
    if 0 <= idx < len(authorships):
        return authorships[idx]
    if focus.get("role") == "last_author":
        return authorships[-1]
    return None


def _arxiv_base_id(paper: Dict[str, Any]) -> str:
    raw = " ".join(norm_text(paper.get(key)) for key in ("id", "paper_id", "link", "url"))
    m = re.search(r"(\d{4}\.\d{4,5})(?:v\d+)?", raw)
    return m.group(1) if m else ""


def _extract_balanced_braces(text: str, start: int) -> str:
    open_idx = text.find("{", start)
    if open_idx < 0:
        return ""
    depth = 0
    escaped = False
    for idx in range(open_idx, len(text)):
        ch = text[idx]
        if escaped:
            escaped = False
            continue
        if ch == "\\":
            escaped = True
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[open_idx + 1 : idx]
    return ""


def _strip_latex_comments(text: str) -> str:
    lines: List[str] = []
    for line in text.splitlines():
        match = re.search(r"(?<!\\)%", line)
        lines.append(line[: match.start()] if match else line)
    return "\n".join(lines)


def _latex_blocks(text: str, command: str) -> List[str]:
    out: List[str] = []
    pattern = "\\" + command
    start = 0
    while True:
        idx = text.find(pattern, start)
        if idx < 0:
            return out
        block = _extract_balanced_braces(text, idx + len(pattern))
        if block:
            out.append(block)
        start = idx + len(pattern)


def _clean_latex_text(value: str) -> str:
    text = value
    text = text.replace("\\&", "&")
    text = re.sub(r"%.*", "", text)
    text = re.sub(r"\\IEEEauthorrefmark\{[^}]*\}", " ", text)
    text = re.sub(r"\\thanks\{.*?\}", " ", text, flags=re.S)
    text = re.sub(r"\\[a-zA-Z]+\*?(?:\[[^\]]*\])?", " ", text)
    text = re.sub(r"[{}$^]", " ", text)
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip(" ,;")


def _clean_affiliation_text(value: str) -> str:
    text = _clean_latex_text(value)
    text = re.sub(r"\[[0-9.]+\s*cm\]", " ", text)
    text = re.sub(r"\b(?:e-?mail|emails?|contact)\s*:.*$", " ", text, flags=re.I)
    text = re.sub(r"https?://\S+", " ", text)
    text = re.sub(r"\b(?:github|hf\.co|dataset|source code|code and data|tabular)\b.*$", " ", text, flags=re.I)
    text = re.sub(r"\S+@\S+", " ", text)
    text = text.replace("\\", " ")
    return re.sub(r"\s+", " ", text).strip(" ,;")


def _is_affiliation_noise(value: str) -> bool:
    text = norm_text(value)
    if not text:
        return True
    lower = text.lower()
    if lower in {"c", "l", "r", "cc", "ll", "rr"}:
        return True
    if "@" in text or "http://" in lower or "https://" in lower:
        return True
    if re.search(r"\b(?:github|hf\.co|tabular|texttt|href|faGithub|hflogo)\b", text):
        return True
    return not re.search(r"[A-Za-z\u4e00-\u9fff]", text)


def _clean_affiliation_items(values: List[str]) -> List[str]:
    out: List[str] = []
    for value in values:
        text = _clean_affiliation_text(value)
        if not _is_affiliation_noise(text):
            _append_unique(out, text)
    return out


def _looks_like_person_name_line(value: str) -> bool:
    text = norm_text(value)
    if not text or any(token in text.lower() for token in ("university", "institute", "college", "school", "department", "lab", "center", "centre", "research", "security")):
        return False
    return bool(re.fullmatch(r"[A-Z][A-Za-z.'-]+(?:\s+[A-Z][A-Za-z.'-]+){1,4}", text))


def _latex_marker_numbers(value: str) -> List[str]:
    return re.findall(r"\d+", value or "")


def _markers_for_focus_in_latex_text(text: str, focus: Dict[str, Any]) -> List[str]:
    markers: List[str] = []
    author_patterns = (
        r"([^,\\\\\n]+?)\\textsuperscript\{([^}]+)\}",
        r"([^,\\\\\n]+?)\$\^\{([^}]+)\}\$",
    )
    for pattern in author_patterns:
        for raw_name, raw_markers in re.findall(pattern, text, flags=re.S):
            if not _name_appears_in_text(focus.get("name"), _clean_latex_text(raw_name)):
                continue
            for marker in _latex_marker_numbers(raw_markers):
                _append_unique(markers, marker)
    if markers:
        return markers
    for row in re.split(r",|\\\\|\\and\b", text):
        if not _name_appears_in_text(focus.get("name"), _clean_latex_text(row)):
            continue
        for marker in _latex_marker_numbers(row):
            _append_unique(markers, marker)
    return markers


def _marked_affiliations_from_latex(text: str) -> Dict[str, str]:
    affiliations: Dict[str, str] = {}
    aff_patterns = (
        r"(?:\\normalfont)?\\textsuperscript\{(\d+)\}(.+?)(?=(?:\\normalfont)?\\textsuperscript\{\d+\}|\$\^\{\d+\}\$|\\\\|\n\s*\n|$)",
        r"\$\^\{(\d+)\}\$(.+?)(?=\$\^\{\d+\}\$|(?:\\normalfont)?\\textsuperscript\{\d+\}|\\\\|\n\s*\n|$)",
    )
    for pattern in aff_patterns:
        for marker, raw_aff in re.findall(pattern, text, flags=re.S):
            aff = _clean_affiliation_text(raw_aff)
            aff = re.split(r"\s+(?:quad|qquad)\s+", aff)[0].strip()
            if not _is_affiliation_noise(aff):
                affiliations.setdefault(marker, aff)
    return affiliations


def _latex_parbox_blocks(text: str) -> List[str]:
    blocks: List[str] = []
    for match in re.finditer(r"\\parbox(?:\[[^\]]*\])?\s*\{[^{}]*\}\s*", text):
        block = _extract_balanced_braces(text, match.end())
        if block:
            blocks.append(block)
    return blocks


def _extract_parbox_author_profile(body: str, focus: Dict[str, Any]) -> Dict[str, Any]:
    for block in _latex_parbox_blocks(body):
        rows = [
            _clean_affiliation_text(row)
            for row in re.split(r"\\\\|\\par\b", block)
            if _clean_affiliation_text(row)
        ]
        if not rows or not _name_appears_in_text(focus.get("name"), rows[0]):
            continue
        affiliations = _clean_affiliation_items(rows[1:])
        if affiliations:
            return {
                "source": "arxiv_source",
                "name": norm_text(focus.get("name")),
                "affiliations": affiliations[:4],
                "author_row": rows[0],
            }
    return {}


def _extract_marked_author_profile(body: str, focus: Dict[str, Any]) -> Dict[str, Any]:
    aff_start_match = re.search(
        r"\\\\(?:\[[^\]]*\])?\s*(?=(?:\\normalfont)?\\textsuperscript\{\d+\}|\$\^\{\d+\}\$)",
        body,
        flags=re.S,
    )
    author_body = body[: aff_start_match.start()] if aff_start_match else body
    affiliation_body = body[aff_start_match.end() :] if aff_start_match else body
    affiliations = _marked_affiliations_from_latex(affiliation_body)

    author_patterns = (
        r"([^,\\\\\n]+?)\\textsuperscript\{([^}]+)\}",
        r"([^,\\\\\n]+?)\$\^\{([^}]+)\}\$",
    )
    for pattern in author_patterns:
        for raw_name, raw_markers in re.findall(pattern, author_body, flags=re.S):
            name = _clean_latex_text(raw_name)
            if not _name_appears_in_text(focus.get("name"), name):
                continue
            affs = [affiliations[num] for num in _latex_marker_numbers(raw_markers) if num in affiliations]
            if affs:
                return {
                    "source": "arxiv_source",
                    "name": norm_text(focus.get("name")),
                    "affiliations": affs[:4],
                    "author_row": name,
                }
    return {}


def _extract_icml_author_profile(source: str, focus: Dict[str, Any]) -> Dict[str, Any]:
    affiliations: Dict[str, str] = {}
    for key, raw_aff in re.findall(r"\\icmlaffiliation\{([^}]+)\}\{([^}]+)\}", source, flags=re.S):
        aff = _clean_affiliation_text(raw_aff)
        if not _is_affiliation_noise(aff):
            affiliations[norm_text(key)] = aff
    if not affiliations:
        return {}
    for raw_name, raw_keys in re.findall(r"\\icmlauthor\{([^}]+)\}\{([^}]+)\}", source, flags=re.S):
        name = _clean_latex_text(raw_name)
        if not _name_appears_in_text(focus.get("name"), name):
            continue
        affs = [affiliations[key.strip()] for key in raw_keys.split(",") if key.strip() in affiliations]
        if affs:
            return {
                "source": "arxiv_source",
                "name": norm_text(focus.get("name")),
                "affiliations": affs[:4],
                "author_row": name,
            }
    return {}


def _extract_acm_author_profile(source: str, focus: Dict[str, Any]) -> Dict[str, Any]:
    matches = list(re.finditer(r"\\author\s*\{", source))
    for idx, match in enumerate(matches):
        raw_name = _extract_balanced_braces(source, match.start())
        name = _clean_latex_text(raw_name)
        if not _name_appears_in_text(focus.get("name"), name):
            continue
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(source)
        segment = source[match.end() : end]
        markers = _markers_for_focus_in_latex_text(raw_name, focus)
        marked_affiliations: Dict[str, str] = {}
        for block in _latex_blocks(segment, "institution"):
            for marker, affiliation in _marked_affiliations_from_latex(block).items():
                marked_affiliations.setdefault(marker, affiliation)
        affs = [
            marked_affiliations[marker]
            for marker in markers
            if marker in marked_affiliations
        ]
        if affs:
            return {
                "source": "arxiv_source",
                "name": norm_text(focus.get("name")),
                "affiliations": affs[:4],
                "author_row": name,
            }
        affs: List[str] = []
        for block in _latex_blocks(segment, "institution"):
            aff = _clean_affiliation_text(block)
            if not _is_affiliation_noise(aff):
                _append_unique(affs, aff)
        if not affs:
            for block in _latex_blocks(segment, "affiliation"):
                text = _clean_affiliation_text(block)
                if not _is_affiliation_noise(text):
                    _append_unique(affs, text)
        if affs:
            return {
                "source": "arxiv_source",
                "name": norm_text(focus.get("name")),
                "affiliations": affs[:4],
                "author_row": name,
            }
    return {}


def _extract_aaai_author_profile(source: str, focus: Dict[str, Any]) -> Dict[str, Any]:
    author_blocks = _latex_blocks(source, "author")
    affiliation_blocks = _latex_blocks(source, "affiliations")
    if not author_blocks or not affiliation_blocks:
        return {}
    author_body = max(author_blocks, key=len)
    if not _name_appears_in_text(focus.get("name"), _clean_latex_text(author_body)):
        return {}
    rows = [
        row
        for row in re.split(r"\\\\|\\and\b", max(affiliation_blocks, key=len))
        if norm_text(row)
    ]
    affiliations = _clean_affiliation_items(rows)
    if affiliations:
        return {
            "source": "arxiv_source",
            "name": norm_text(focus.get("name")),
            "affiliations": affiliations[:4],
            "author_row": _clean_latex_text(author_body),
        }
    return {}


def _affiliation_overlap(affiliations: List[str], candidate_affiliations: List[str]) -> bool:
    left = " ".join(normalize_title(item) for item in affiliations if norm_text(item))
    if not left:
        return False
    for candidate in candidate_affiliations:
        right = normalize_title(candidate)
        if right and (right in left or left in right):
            return True
    return False


def _extract_latex_author_profile(source: str, focus: Dict[str, Any]) -> Dict[str, Any]:
    source = _strip_latex_comments(source)
    for extractor in (_extract_icml_author_profile, _extract_acm_author_profile, _extract_aaai_author_profile):
        profile = extractor(source, focus)
        if profile:
            return profile
    author_blocks = _latex_blocks(source, "author")
    if not author_blocks:
        return {}
    body = max(author_blocks, key=len)
    affiliation_by_mark: Dict[str, str] = {}
    for block in _latex_blocks(body, "IEEEauthorblockA"):
        mark_match = re.search(r"\\IEEEauthorrefmark\{([^}]+)\}", block)
        if not mark_match:
            continue
        affiliation = _clean_latex_text(block)
        if affiliation:
            affiliation_by_mark[norm_text(mark_match.group(1))] = affiliation
    name_blocks = _latex_blocks(body, "IEEEauthorblockN") or [body]
    for block in name_blocks:
        rows = re.split(r",|\\\\", block)
        for row in rows:
            mark_match = re.search(r"\\IEEEauthorrefmark\{([^}]+)\}", row)
            name = _clean_latex_text(row)
            if not name or not _names_match(focus.get("name"), name):
                continue
            mark = norm_text(mark_match.group(1)) if mark_match else ""
            affiliation = affiliation_by_mark.get(mark, "")
            if affiliation:
                return {
                    "source": "arxiv_source",
                    "name": norm_text(focus.get("name")),
                    "affiliations": [affiliation],
                    "author_row": name,
                }
    marked = _extract_marked_author_profile(body, focus)
    if marked:
        return marked
    parbox = _extract_parbox_author_profile(body, focus)
    if parbox:
        return parbox
    simple_body = re.sub(r"\\(?:thanks|footnote|footnotetext)\{.*?\}", " ", body, flags=re.S)
    simple_body = re.sub(r"\\footnotemark(?:\[[^\]]*\])?", " ", simple_body)
    simple_body = re.sub(r"\\vspace\{[^}]*\}", " ", simple_body)
    chunks = [chunk for chunk in re.split(r"\\\\|\\and\b", simple_body) if norm_text(chunk)]
    cleaned_chunks = [_clean_latex_text(chunk) for chunk in chunks]
    cleaned_chunks = [chunk for chunk in cleaned_chunks if chunk]
    for idx, chunk in enumerate(cleaned_chunks):
        if not _name_appears_in_text(focus.get("name"), chunk):
            continue
        candidate_rows: List[str] = []
        for row in cleaned_chunks[idx + 1 :]:
            if _looks_like_person_name_line(row):
                break
            candidate_rows.append(row)
        affiliations = _clean_affiliation_items(candidate_rows)
        if affiliations:
            return {
                "source": "arxiv_source",
                "name": norm_text(focus.get("name")),
                "affiliations": affiliations[:4],
                "author_row": chunk,
            }
    if len(cleaned_chunks) >= 2:
        name_row = cleaned_chunks[0]
        if _name_appears_in_text(focus.get("name"), name_row) or any(
            _name_appears_in_text(focus.get("name"), part) for part in re.split(r",| and |\s+quad\s+", name_row)
        ):
            affiliations = _clean_affiliation_items(cleaned_chunks[1:])
            if affiliations:
                return {
                    "source": "arxiv_source",
                    "name": norm_text(focus.get("name")),
                    "affiliations": affiliations[:4],
                    "author_row": name_row,
                }
    return {}


class AuthorProfileRater:
    def __init__(
        self,
        cache_dir: str,
        client: Any | None = None,
        session: Any | None = None,
        timeout: int = 20,
    ) -> None:
        self.cache_dir = cache_dir
        self.client = client
        self.session = session or requests.Session()
        self.timeout = timeout

    def _cache_path(self, category: str, key: str) -> str:
        return os.path.join(self.cache_dir, category, _safe_filename(key))

    def _profile_key(self, paper: Dict[str, Any], focus: Dict[str, Any]) -> str:
        return "|".join(
            [
                AUTHOR_PROFILE_EXTRACTION_VERSION,
                normalize_author_name(focus.get("name")),
                normalize_title(paper.get("title")),
                _extract_year(paper),
                norm_text(paper.get("id") or paper.get("paper_id")),
            ]
        )

    def _rating_key(self, paper: Dict[str, Any], focuses: List[Dict[str, Any]]) -> str:
        names = ",".join(normalize_author_name(item.get("name")) for item in focuses)
        return "|".join([AUTHOR_RATING_RUBRIC_VERSION, normalize_title(paper.get("title")), _extract_year(paper), names])

    def _get_json(self, url: str, params: Dict[str, Any]) -> Dict[str, Any]:
        resp = self.session.get(url, params=params, timeout=self.timeout)
        if getattr(resp, "status_code", 200) != 200:
            return {}
        data = resp.json()
        return data if isinstance(data, dict) else {}

    def _fetch_openalex_profile(self, paper: Dict[str, Any], focus: Dict[str, Any]) -> Dict[str, Any]:
        title = norm_text(paper.get("title"))
        if not title:
            return {}
        data = self._get_json(
            "https://api.openalex.org/works",
            {
                "search": title,
                "per-page": 3,
                "select": "id,title,publication_year,authorships,primary_location,locations_count,cited_by_count",
            },
        )
        results = data.get("results") if isinstance(data.get("results"), list) else []
        if not results:
            return {}
        work = results[0]
        authorships = work.get("authorships") if isinstance(work.get("authorships"), list) else []
        authorship = _author_at_role(authorships, focus)
        if not isinstance(authorship, dict):
            return {}
        author = authorship.get("author") if isinstance(authorship.get("author"), dict) else {}
        institutions = authorship.get("institutions") if isinstance(authorship.get("institutions"), list) else []
        affiliation_items = []
        for inst in institutions:
            if isinstance(inst, dict) and norm_text(inst.get("display_name")):
                affiliation_items.append(norm_text(inst.get("display_name")))
        raw_aff = authorship.get("raw_affiliation_strings") or authorship.get("raw_affiliation_string") or []
        if isinstance(raw_aff, str):
            affiliation_items.append(raw_aff)
        elif isinstance(raw_aff, list):
            affiliation_items.extend(norm_text(item) for item in raw_aff if norm_text(item))
        author_stats: Dict[str, Any] = {}
        author_id = norm_text(author.get("id"))
        if author_id:
            try:
                author_stats = self._get_json(
                    author_id,
                    {"select": "id,display_name,works_count,cited_by_count,last_known_institutions"},
                )
            except Exception:
                author_stats = {}
        return {
            "source": "openalex",
            "paper_title": norm_text(work.get("title")),
            "paper_year": work.get("publication_year"),
            "name": norm_text(author.get("display_name") or focus.get("name")),
            "affiliations": affiliation_items,
            "works_count": author_stats.get("works_count"),
            "cited_by_count": author_stats.get("cited_by_count") or author.get("cited_by_count"),
            "author_id": author_id,
        }

    def _fetch_openalex_author_profile(
        self,
        paper: Dict[str, Any],
        focus: Dict[str, Any],
        affiliation_hints: List[str],
    ) -> Dict[str, Any]:
        name = norm_text(focus.get("name"))
        if not name:
            return {}
        data = self._get_json(
            "https://api.openalex.org/authors",
            {
                "search": name,
                "per-page": 10,
                "select": "id,display_name,works_count,cited_by_count,last_known_institutions",
            },
        )
        results = data.get("results") if isinstance(data.get("results"), list) else []
        best: Dict[str, Any] = {}
        best_score = -1
        for candidate in results:
            if not isinstance(candidate, dict) or not _names_match(name, candidate.get("display_name")):
                continue
            institutions = candidate.get("last_known_institutions") if isinstance(candidate.get("last_known_institutions"), list) else []
            candidate_affiliations = [
                norm_text(inst.get("display_name"))
                for inst in institutions
                if isinstance(inst, dict) and norm_text(inst.get("display_name"))
            ]
            score = 10 if normalize_author_name(name) == normalize_author_name(candidate.get("display_name")) else 5
            if _affiliation_overlap(affiliation_hints, candidate_affiliations):
                score += 20
            cited = candidate.get("cited_by_count")
            works = candidate.get("works_count")
            if isinstance(cited, int):
                score += min(cited, 10000) / 10000
            if isinstance(works, int):
                score += min(works, 1000) / 10000
            if score > best_score:
                best_score = score
                best = {
                    "source": "openalex",
                    "paper_title": norm_text(paper.get("title")),
                    "paper_year": _extract_year(paper),
                    "name": norm_text(candidate.get("display_name") or name),
                    "affiliations": candidate_affiliations,
                    "works_count": candidate.get("works_count"),
                    "cited_by_count": candidate.get("cited_by_count"),
                    "author_id": norm_text(candidate.get("id")),
                    "lookup": "author_search",
                }
        return best

    def _fetch_semantic_scholar_profile(self, paper: Dict[str, Any], focus: Dict[str, Any]) -> Dict[str, Any]:
        title = norm_text(paper.get("title"))
        if not title:
            return {}
        data = self._get_json(
            "https://api.semanticscholar.org/graph/v1/paper/search",
            {
                "query": title,
                "limit": 3,
                "fields": "title,year,authors.name,authors.authorId,authors.affiliations,authors.paperCount,authors.citationCount",
            },
        )
        results = data.get("data") if isinstance(data.get("data"), list) else []
        if not results:
            return {}
        paper_hit = results[0]
        authors = paper_hit.get("authors") if isinstance(paper_hit.get("authors"), list) else []
        author_hit = None
        for candidate in authors:
            if isinstance(candidate, dict) and _names_match(focus.get("name"), candidate.get("name")):
                author_hit = candidate
                break
        if author_hit is None:
            idx = int(focus.get("index") or 0)
            if 0 <= idx < len(authors) and isinstance(authors[idx], dict):
                author_hit = authors[idx]
            elif focus.get("role") == "last_author" and authors and isinstance(authors[-1], dict):
                author_hit = authors[-1]
        if not isinstance(author_hit, dict):
            return {}
        aff = author_hit.get("affiliations") if isinstance(author_hit.get("affiliations"), list) else []
        return {
            "source": "semantic_scholar",
            "paper_title": norm_text(paper_hit.get("title")),
            "paper_year": paper_hit.get("year"),
            "name": norm_text(author_hit.get("name") or focus.get("name")),
            "affiliations": [norm_text(item) for item in aff if norm_text(item)],
            "paper_count": author_hit.get("paperCount"),
            "citation_count": author_hit.get("citationCount"),
            "author_id": norm_text(author_hit.get("authorId")),
        }

    def _fetch_semantic_scholar_author_profile(
        self,
        paper: Dict[str, Any],
        focus: Dict[str, Any],
        affiliation_hints: List[str],
    ) -> Dict[str, Any]:
        name = norm_text(focus.get("name"))
        if not name:
            return {}
        data = self._get_json(
            "https://api.semanticscholar.org/graph/v1/author/search",
            {
                "query": name,
                "limit": 10,
                "fields": "name,authorId,affiliations,paperCount,citationCount",
            },
        )
        results = data.get("data") if isinstance(data.get("data"), list) else []
        best: Dict[str, Any] = {}
        best_score = -1
        for candidate in results:
            if not isinstance(candidate, dict) or not _names_match(name, candidate.get("name")):
                continue
            candidate_affiliations = [
                norm_text(item)
                for item in (candidate.get("affiliations") if isinstance(candidate.get("affiliations"), list) else [])
                if norm_text(item)
            ]
            score = 10 if normalize_author_name(name) == normalize_author_name(candidate.get("name")) else 5
            if _affiliation_overlap(affiliation_hints, candidate_affiliations):
                score += 20
            citations = candidate.get("citationCount")
            papers = candidate.get("paperCount")
            if isinstance(citations, int):
                score += min(citations, 10000) / 10000
            if isinstance(papers, int):
                score += min(papers, 1000) / 10000
            if score > best_score:
                best_score = score
                best = {
                    "source": "semantic_scholar",
                    "paper_title": norm_text(paper.get("title")),
                    "paper_year": _extract_year(paper),
                    "name": norm_text(candidate.get("name") or name),
                    "affiliations": candidate_affiliations,
                    "paper_count": candidate.get("paperCount"),
                    "citation_count": candidate.get("citationCount"),
                    "author_id": norm_text(candidate.get("authorId")),
                    "lookup": "author_search",
                }
        return best

    def _fetch_arxiv_source_profile(self, paper: Dict[str, Any], focus: Dict[str, Any]) -> Dict[str, Any]:
        arxiv_id = _arxiv_base_id(paper)
        if not arxiv_id:
            return {}
        resp = self.session.get(f"https://arxiv.org/e-print/{arxiv_id}", params={}, timeout=self.timeout)
        if getattr(resp, "status_code", 200) != 200:
            return {}
        content = getattr(resp, "content", b"")
        if not isinstance(content, (bytes, bytearray)) or not content:
            return {}
        tex_sources: List[str] = []
        try:
            with tarfile.open(fileobj=io.BytesIO(content), mode="r:*") as tar:
                members = [m for m in tar.getmembers() if m.isfile() and m.name.lower().endswith(".tex")]

                def source_priority(member: tarfile.TarInfo) -> tuple[int, int, str]:
                    base = os.path.basename(member.name).lower()
                    root_level = 0 if "/" not in member.name.strip("/") else 1
                    if base in {"main.tex", "paper.tex", "arxiv.tex", "arvix.tex", "ms.tex", "article.tex"}:
                        return (0, root_level, member.name)
                    if any(token in base for token in ("main", "paper", "arxiv", "article")):
                        return (1, root_level, member.name)
                    return (2, root_level, member.name)

                members.sort(key=source_priority)
                for member in members[:24]:
                    extracted = tar.extractfile(member)
                    if extracted is None:
                        continue
                    tex_sources.append(extracted.read(500_000).decode("utf-8", errors="ignore"))
        except tarfile.TarError:
            tex_sources.append(bytes(content[:500_000]).decode("utf-8", errors="ignore"))
        for source in tex_sources:
            profile = _extract_latex_author_profile(source, focus)
            if profile:
                return profile
        return {}

    def _merge_local_profile(self, profile: Dict[str, Any], local: Dict[str, Any]) -> Dict[str, Any]:
        if not local.get("source"):
            return self._drop_split_affiliation_fields(profile)
        merged = dict(profile)
        local_affiliations = [text for text in (local.get("affiliations") or []) if norm_text(text)]
        if local_affiliations and not norm_text(merged.get("affiliation")):
            merged["affiliation"] = "; ".join(local_affiliations[:4])
        evidence = [
            item.strip()
            for item in re.split(r",\s*", norm_text(merged.get("evidence_source")))
            if item.strip() and item.strip() != "metadata lookup unavailable"
        ]
        if local.get("source") not in evidence:
            evidence.insert(0, local.get("source"))
        merged["evidence_source"] = ", ".join(evidence)
        if norm_text(merged.get("confidence")) == "low" and norm_text(merged.get("affiliation")):
            merged["confidence"] = "medium"
        return self._drop_split_affiliation_fields(merged)

    @staticmethod
    def _drop_split_affiliation_fields(profile: Dict[str, Any]) -> Dict[str, Any]:
        cleaned = dict(profile)
        for key in ("group", "school", "company"):
            cleaned.pop(key, None)
        return cleaned

    def _profile_has_signal(self, profile: Dict[str, Any]) -> bool:
        return bool(norm_text(profile.get("affiliation")))

    def _profile_has_citation_signal(self, profile: Dict[str, Any]) -> bool:
        if norm_text(profile.get("citation_hints")):
            return True
        openalex = profile.get("openalex") if isinstance(profile.get("openalex"), dict) else {}
        semantic = profile.get("semantic_scholar") if isinstance(profile.get("semantic_scholar"), dict) else {}
        return any(
            value is not None
            for value in (
                openalex.get("cited_by_count"),
                openalex.get("works_count"),
                semantic.get("citation_count"),
                semantic.get("paper_count"),
            )
        )

    def _rating_has_author_signal(self, rating: Dict[str, Any]) -> bool:
        profiles = rating.get("author_profiles")
        return (
            self._profiles_have_author_signal(profiles)
            and not self._is_neutral_fallback_rating(rating)
        )

    def _profiles_have_author_signal(self, profiles: Any) -> bool:
        return isinstance(profiles, list) and any(
            isinstance(profile, dict)
            and self._profile_has_signal(profile)
            for profile in profiles
        )

    def _is_neutral_fallback_rating(self, rating: Dict[str, Any]) -> bool:
        explanation = norm_text(rating.get("author_rating_explanation")).lower()
        status = norm_text(rating.get("author_rating_status")).lower()
        score = clamp_score(rating.get("author_score"))
        fallback_markers = (
            "neutral low-confidence",
            "no llm client",
            "llm output was unavailable",
            "llm synthesis failed",
            "author rating failed",
            "insufficient author metadata",
            "metadata lookup or llm synthesis failed",
        )
        return score == 4.5 and (
            status == "fallback" or any(marker in explanation for marker in fallback_markers)
        )

    def fetch_author_profile(self, paper: Dict[str, Any], focus: Dict[str, Any]) -> Dict[str, Any]:
        key = self._profile_key(paper, focus)
        path = self._cache_path("profiles", key)
        local = _local_author_metadata(paper, focus)
        cached = _read_json(path)
        if cached is not None:
            merged = self._merge_local_profile(cached, local)
            if self._profile_has_signal(merged) and self._profile_has_citation_signal(merged):
                if merged != cached:
                    _write_json(path, merged)
                return merged

        arxiv_source: Dict[str, Any] = {}
        openalex: Dict[str, Any] = {}
        semantic: Dict[str, Any] = {}
        for source_name, fetcher in (
            ("arxiv_source", self._fetch_arxiv_source_profile),
            ("openalex", self._fetch_openalex_profile),
            ("semantic_scholar", self._fetch_semantic_scholar_profile),
        ):
            try:
                if source_name == "arxiv_source":
                    arxiv_source = fetcher(paper, focus)
                elif source_name == "openalex":
                    openalex = fetcher(paper, focus)
                else:
                    semantic = fetcher(paper, focus)
            except Exception:
                continue
            time.sleep(0.05)

        affiliation_hints: List[str] = []
        for payload in (local, arxiv_source, openalex, semantic):
            for aff in payload.get("affiliations") or []:
                _append_unique(affiliation_hints, aff)

        if not (openalex.get("cited_by_count") is not None or openalex.get("works_count") is not None):
            try:
                openalex_author = self._fetch_openalex_author_profile(paper, focus, affiliation_hints)
            except Exception:
                openalex_author = {}
            if openalex_author:
                if openalex:
                    merged_openalex = dict(openalex)
                    merged_openalex.update({k: v for k, v in openalex_author.items() if v not in (None, "", [])})
                    existing_affiliations = list(openalex.get("affiliations") or [])
                    for aff in openalex_author.get("affiliations") or []:
                        _append_unique(existing_affiliations, aff)
                    merged_openalex["affiliations"] = existing_affiliations
                    openalex = merged_openalex
                else:
                    openalex = openalex_author
                for aff in openalex_author.get("affiliations") or []:
                    _append_unique(affiliation_hints, aff)

        if not (semantic.get("citation_count") is not None or semantic.get("paper_count") is not None):
            try:
                semantic_author = self._fetch_semantic_scholar_author_profile(paper, focus, affiliation_hints)
            except Exception:
                semantic_author = {}
            if semantic_author:
                if semantic:
                    merged_semantic = dict(semantic)
                    merged_semantic.update({k: v for k, v in semantic_author.items() if v not in (None, "", [])})
                    existing_affiliations = list(semantic.get("affiliations") or [])
                    for aff in semantic_author.get("affiliations") or []:
                        _append_unique(existing_affiliations, aff)
                    merged_semantic["affiliations"] = existing_affiliations
                    semantic = merged_semantic
                else:
                    semantic = semantic_author

        affiliations: List[str] = []
        for payload in (local, arxiv_source, openalex, semantic):
            for aff in payload.get("affiliations") or []:
                text = norm_text(aff)
                if text and text not in affiliations:
                    affiliations.append(text)
        citations = [
            f"OpenAlex cited_by_count={openalex.get('cited_by_count')}" if openalex.get("cited_by_count") is not None else "",
            f"OpenAlex works_count={openalex.get('works_count')}" if openalex.get("works_count") is not None else "",
            f"Semantic Scholar citation_count={semantic.get('citation_count')}" if semantic.get("citation_count") is not None else "",
            f"Semantic Scholar paper_count={semantic.get('paper_count')}" if semantic.get("paper_count") is not None else "",
        ]
        evidence_sources = [p.get("source") for p in (local, arxiv_source, openalex, semantic) if p.get("source")]
        profile = {
            "name": norm_text(focus.get("name")),
            "role": norm_text(focus.get("role")),
            "affiliation": "; ".join(affiliations[:4]),
            "citation_count": _first_count(semantic.get("citation_count"), openalex.get("cited_by_count")),
            "paper_count": _first_count(semantic.get("paper_count"), openalex.get("works_count")),
            "citation_hints": "; ".join(item for item in citations if item),
            "confidence": "medium" if evidence_sources else "low",
            "evidence_source": ", ".join(evidence_sources) or "metadata lookup unavailable",
            "arxiv_source": arxiv_source,
            "openalex": openalex,
            "semantic_scholar": semantic,
        }
        _write_json(path, profile)
        return profile

    def _neutral_rating(self, profiles: List[Dict[str, Any]], reason: str) -> Dict[str, Any]:
        return {
            "author_score": 4.5,
            "author_rating_explanation": reason,
            "author_profiles": [self._public_author_profile(profile) for profile in profiles if isinstance(profile, dict)],
            "author_rating_status": "fallback",
        }

    @staticmethod
    def _public_author_profile(profile: Dict[str, Any]) -> Dict[str, str]:
        return {
            "name": norm_text(profile.get("name")),
            "role": norm_text(profile.get("role")),
            "affiliation": norm_text(profile.get("affiliation")),
            "citation_count": _count_text(_profile_metric_count(profile, "citation")),
            "paper_count": _count_text(_profile_metric_count(profile, "paper")),
            "citation_hints": norm_text(profile.get("citation_hints")),
            "confidence": norm_text(profile.get("confidence")),
            "evidence_source": norm_text(profile.get("evidence_source")),
        }

    def _normalize_llm_rating(
        self,
        parsed: Dict[str, Any],
        profiles: List[Dict[str, Any]],
    ) -> Dict[str, Any] | None:
        raw_score = parsed.get("author_score")
        if raw_score is None:
            raw_score = parsed.get("score")
        if raw_score is None:
            raw_score = parsed.get("rating")
        if raw_score is None:
            return None
        try:
            float(raw_score)
        except Exception:
            return None
        author_score = clamp_score(raw_score)

        author_profiles = parsed.get("author_profiles")
        if not isinstance(author_profiles, list):
            author_profiles = [self._public_author_profile(profile) for profile in profiles if isinstance(profile, dict)]
        else:
            normalized_profiles: List[Dict[str, Any]] = []
            fallback_by_key = {
                (normalize_author_name(profile.get("name")), norm_text(profile.get("role"))): profile
                for profile in profiles
                if isinstance(profile, dict)
            }
            for idx, profile in enumerate(author_profiles):
                if not isinstance(profile, dict):
                    continue
                fallback = fallback_by_key.get(
                    (normalize_author_name(profile.get("name")), norm_text(profile.get("role")))
                )
                if fallback is None and idx < len(profiles) and isinstance(profiles[idx], dict):
                    fallback = profiles[idx]
                merged_profile = dict(fallback or {})
                merged_profile.update(profile)
                if isinstance(fallback, dict):
                    for key in ("affiliation", "citation_count", "paper_count", "citation_hints", "confidence", "evidence_source"):
                        if norm_text(fallback.get(key)):
                            merged_profile[key] = fallback.get(key)
                normalized_profiles.append(self._public_author_profile(merged_profile))
            author_profiles = normalized_profiles or [
                self._public_author_profile(profile) for profile in profiles if isinstance(profile, dict)
            ]

        explanation = (
            norm_text(parsed.get("author_rating_explanation"))
            or norm_text(parsed.get("explanation"))
            or norm_text(parsed.get("reason"))
        )
        if not explanation or explanation == GENERIC_AUTHOR_RATING_EXPLANATION:
            return None
        return {
            "author_score": author_score,
            "author_rating_explanation": explanation,
            "author_profiles": author_profiles,
            "author_rating_status": "rated",
        }

    def _call_llm_rating(self, paper: Dict[str, Any], profiles: List[Dict[str, Any]]) -> Dict[str, Any]:
        if self.client is None:
            return self._neutral_rating(
                profiles,
                "Insufficient author metadata or no LLM client; assigned a neutral low-confidence author rating.",
            )

        schema = {
            "type": "object",
            "properties": {
                "author_score": {"type": "number"},
                "author_rating_explanation": {"type": "string"},
                "author_profiles": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "role": {"type": "string"},
                            "affiliation": {"type": "string"},
                            "citation_count": {"type": "string"},
                            "paper_count": {"type": "string"},
                            "citation_hints": {"type": "string"},
                            "confidence": {"type": "string"},
                            "evidence_source": {"type": "string"},
                        },
                        "required": ["name"],
                        "additionalProperties": False,
                    },
                },
            },
            "required": ["author_score", "author_rating_explanation", "author_profiles"],
            "additionalProperties": False,
        }
        system_prompt = (
            "You rate AI paper author/source background from verified metadata only. "
            "Do not infer prestige from a name alone. Return JSON only."
        )
        public_profiles = [
            self._public_author_profile(profile)
            for profile in profiles
            if isinstance(profile, dict)
        ]
        user_prompt = (
            "Rate the paper's focus authors on a 0-10 author/source background scale.\n"
            "Score bands are ranges, not ordinal list numbers:\n"
            "9-10: Major AI/tech companies or elite AI research labs: DeepMind, OpenAI, Anthropic, Google Research, Meta AI, Microsoft Research, NVIDIA, FAIR, DeepSeek, ByteDance Seed, Qwen, Moonshot AI, etc.\n"
            "8-9: Top US AI schools/labs: Stanford, MIT, CMU, Berkeley, Princeton, Harvard, UW, UIUC, Cornell, Georgia Tech, Caltech, etc.\n"
            "6-8: Top European, Chinese, and Hong Kong AI schools/labs: Oxford, Cambridge, ETH Zurich, EPFL, Tsinghua, Peking, Shanghai Jiao Tong, Zhejiang, USTC, CAS, HKUST, CUHK, HKU, CityU, PolyU, etc.\n"
            "5-6: Mid-tier US research universities with concrete AI/CS research output.\n"
            "0-5: Schools not included in the top or mid-tier bands above, including Korea or India schools, unknown, independent, weakly verifiable, unrelated, self-published-only, or author-provided-only affiliations. This bucket must not receive 6+.\n\n"
            "Use only the metadata below. Verified affiliation text is sufficient rating evidence; "
            "citation counts are optional tie-breakers. Do not assign a neutral score solely because citation_hints are missing "
            "when affiliations identify concrete institutions, labs, or companies. If metadata is truly insufficient, assign a neutral 4-5 score and mark confidence low.\n"
            "Do not treat branch-campus names as the parent institution unless the supplied metadata explicitly says so; in particular, The Chinese University of Hong Kong, Shenzhen / CUHK-Shenzhen is distinct from The Chinese University of Hong Kong / CUHK and must not receive the CUHK/Hong Kong top-school boost solely from that name.\n"
            "A lab/company name that appears only in author-provided paper metadata is not enough for a 6+ score unless it is already a widely recognized institution/company in the score bands above or has visible third-party-verifiable research/citation evidence in the supplied metadata.\n"
            "The explanation must cite the concrete affiliation/source evidence and why the chosen score band applies; generic explanations are invalid.\n"
            "Return exactly one JSON object with this shape and no extra top-level keys:\n"
            "{\n"
            '  "author_score": 0.0,\n'
            '  "author_rating_explanation": "brief evidence-based explanation",\n'
            '  "author_profiles": [\n'
            "    {\n"
            '      "name": "author name",\n'
            '      "role": "first_author|co_first_author|last_author",\n'
            '      "affiliation": "verified affiliation or empty string",\n'
            '      "citation_count": "total citation count or empty string",\n'
            '      "paper_count": "total paper count or empty string",\n'
            '      "citation_hints": "citation evidence or empty string",\n'
            '      "confidence": "high|medium|low",\n'
            '      "evidence_source": "metadata source names or empty string"\n'
            "    }\n"
            "  ]\n"
            "}\n"
            "author_score must be a number from 0 to 10. author_profiles must be an array; include one object for each focus author when possible. "
            "Use empty strings for unknown optional profile fields instead of null. Do not include markdown, code fences, comments, or explanatory text outside the JSON.\n"
            f"Paper: {json.dumps({'title': paper.get('title'), 'year': _extract_year(paper), 'id': paper.get('id')}, ensure_ascii=False)}\n"
            f"Focus author profiles: {json.dumps(public_profiles, ensure_ascii=False)}\n"
        )
        resp = self.client.chat_structured(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            schema_name="author_rating",
            schema=schema,
            strict=True,
            allow_json_object_fallback=True,
        )
        parsed = resp.get("parsed")
        if resp.get("refusal") or not isinstance(parsed, dict):
            return self._neutral_rating(
                profiles,
                "Author-rating LLM output was unavailable; assigned a neutral low-confidence author rating.",
            )

        rating = self._normalize_llm_rating(parsed, profiles)
        if rating is None:
            return self._neutral_rating(
                profiles,
                "Author-rating LLM output was unavailable; assigned a neutral low-confidence author rating.",
            )
        return rating

    def _call_llm_ratings_batch(
        self,
        batch: List[tuple[Dict[str, Any], List[Dict[str, Any]]]],
    ) -> List[Dict[str, Any]]:
        if self.client is None:
            return [
                self._neutral_rating(
                    profiles,
                    "Insufficient author metadata or no LLM client; assigned a neutral low-confidence author rating.",
                )
                for _, profiles in batch
            ]

        schema = {
            "type": "object",
            "properties": {
                "ratings": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "paper_id": {"type": "string"},
                            "author_score": {"type": "number"},
                            "author_rating_explanation": {"type": "string"},
                            "author_profiles": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "name": {"type": "string"},
                                        "role": {"type": "string"},
                                        "affiliation": {"type": "string"},
                                        "citation_count": {"type": "string"},
                                        "paper_count": {"type": "string"},
                                        "citation_hints": {"type": "string"},
                                        "confidence": {"type": "string"},
                                        "evidence_source": {"type": "string"},
                                    },
                                    "required": ["name"],
                                    "additionalProperties": False,
                                },
                            },
                        },
                        "required": ["paper_id", "author_score", "author_rating_explanation", "author_profiles"],
                        "additionalProperties": False,
                    },
                }
            },
            "required": ["ratings"],
            "additionalProperties": False,
        }
        system_prompt = (
            "You rate AI paper author/source background from verified metadata only. "
            "Do not infer prestige from a name alone. Return JSON only."
        )
        papers_payload = [
            {
                "paper_id": f"paper_{idx}",
                "paper": {
                    "title": paper.get("title"),
                    "year": _extract_year(paper),
                    "id": paper.get("id"),
                },
                "focus_author_profiles": [
                    self._public_author_profile(profile)
                    for profile in profiles
                    if isinstance(profile, dict)
                ],
            }
            for idx, (paper, profiles) in enumerate(batch)
        ]
        user_prompt = (
            "Rate each paper's focus authors on a 0-10 author/source background scale.\n"
            "Score bands are ranges, not ordinal list numbers:\n"
            "9-10: Major AI/tech companies or elite AI research labs: DeepMind, OpenAI, Anthropic, Google Research, Meta AI, Microsoft Research, NVIDIA, FAIR, DeepSeek, ByteDance Seed, Qwen, Moonshot AI, etc.\n"
            "8-9: Top US AI schools/labs: Stanford, MIT, CMU, Berkeley, Princeton, Harvard, UW, UIUC, Cornell, Georgia Tech, Caltech, etc.\n"
            "6-8: Top European, Chinese, and Hong Kong AI schools/labs: Oxford, Cambridge, ETH Zurich, EPFL, Tsinghua, Peking, Shanghai Jiao Tong, Zhejiang, USTC, CAS, HKUST, CUHK, HKU, CityU, PolyU, etc.\n"
            "5-6: Mid-tier US research universities with concrete AI/CS research output.\n"
            "0-5: Schools not included in the top or mid-tier bands above, including Korea or India schools, unknown, independent, weakly verifiable, unrelated, self-published-only, or author-provided-only affiliations. This bucket must not receive 6+.\n\n"
            "Use only the metadata below. Verified affiliation text is sufficient rating evidence; "
            "citation counts are optional tie-breakers. Do not assign a neutral score solely because citation_hints are missing "
            "when affiliations identify concrete institutions, labs, or companies. If metadata is truly insufficient, assign a neutral 4-5 score and mark confidence low.\n"
            "Do not treat branch-campus names as the parent institution unless the supplied metadata explicitly says so; in particular, The Chinese University of Hong Kong, Shenzhen / CUHK-Shenzhen is distinct from The Chinese University of Hong Kong / CUHK and must not receive the CUHK/Hong Kong top-school boost solely from that name.\n"
            "A lab/company name that appears only in author-provided paper metadata is not enough for a 6+ score unless it is already a widely recognized institution/company in the score bands above or has visible third-party-verifiable research/citation evidence in the supplied metadata.\n"
            "Each explanation must cite the concrete affiliation/source evidence and why the chosen score band applies; generic explanations are invalid.\n"
            "Return exactly one JSON object with this shape and no extra top-level keys:\n"
            "{\n"
            '  "ratings": [\n'
            "    {\n"
            '      "paper_id": "paper_0",\n'
            '      "author_score": 0.0,\n'
            '      "author_rating_explanation": "brief evidence-based explanation",\n'
            '      "author_profiles": [\n'
            "        {\n"
            '          "name": "author name",\n'
            '          "role": "first_author|co_first_author|last_author",\n'
            '          "affiliation": "verified affiliation or empty string",\n'
            '          "citation_count": "total citation count or empty string",\n'
            '          "paper_count": "total paper count or empty string",\n'
            '          "citation_hints": "citation evidence or empty string",\n'
            '          "confidence": "high|medium|low",\n'
            '          "evidence_source": "metadata source names or empty string"\n'
            "        }\n"
            "      ]\n"
            "    }\n"
            "  ]\n"
            "}\n"
            "Return one ratings item for every input paper_id and preserve each paper_id exactly. "
            "author_score must be a number from 0 to 10. author_profiles must be an array; include one object for each focus author when possible. "
            "Use empty strings for unknown optional profile fields instead of null. Do not include markdown, code fences, comments, or explanatory text outside the JSON.\n"
            f"Papers: {json.dumps(papers_payload, ensure_ascii=False)}\n"
        )
        resp = self.client.chat_structured(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            schema_name="author_rating_batch",
            schema=schema,
            strict=True,
            allow_json_object_fallback=True,
        )
        parsed = resp.get("parsed")
        if resp.get("refusal") or not isinstance(parsed, dict) or not isinstance(parsed.get("ratings"), list):
            return [
                self._neutral_rating(
                    profiles,
                    "Author-rating LLM output was unavailable; assigned a neutral low-confidence author rating.",
                )
                for _, profiles in batch
            ]

        raw_by_id = {
            norm_text(item.get("paper_id")): item
            for item in parsed.get("ratings", [])
            if isinstance(item, dict)
        }
        ratings: List[Dict[str, Any]] = []
        for idx, (_, profiles) in enumerate(batch):
            raw = raw_by_id.get(f"paper_{idx}")
            rating = self._normalize_llm_rating(raw, profiles) if isinstance(raw, dict) else None
            ratings.append(
                rating
                if rating is not None
                else self._neutral_rating(
                    profiles,
                    "Author-rating LLM output was unavailable; assigned a neutral low-confidence author rating.",
                )
            )
        return ratings

    def rate_paper(self, paper: Dict[str, Any]) -> Dict[str, Any]:
        focuses = select_focus_authors(paper)
        if not focuses:
            return self._neutral_rating([], "No author metadata was available; assigned a neutral low-confidence author rating.")

        rating_path = self._cache_path("ratings", self._rating_key(paper, focuses))
        cached = _read_json(rating_path)
        if cached is not None and self._rating_has_author_signal(cached):
            sanitized_cached = dict(cached)
            cached_profiles = cached.get("author_profiles")
            if isinstance(cached_profiles, list):
                sanitized_cached["author_profiles"] = [
                    self._public_author_profile(profile)
                    for profile in cached_profiles
                    if isinstance(profile, dict)
                ]
            return sanitized_cached

        profiles = [self.fetch_author_profile(paper, focus) for focus in focuses]
        try:
            rating = self._call_llm_rating(paper, profiles)
        except Exception:
            rating = self._neutral_rating(
                profiles,
                "Author metadata lookup or LLM synthesis failed; assigned a neutral low-confidence author rating.",
            )
        rating["rated_at"] = datetime.now(timezone.utc).isoformat()
        if not (self._is_neutral_fallback_rating(rating) and self._profiles_have_author_signal(profiles)):
            _write_json(rating_path, rating)
        return rating

    def rate_papers(
        self,
        papers: List[Dict[str, Any]],
        batch_size: int = AUTHOR_RATING_LLM_BATCH_SIZE,
    ) -> List[Dict[str, Any]]:
        batch_size = max(1, int(batch_size or AUTHOR_RATING_LLM_BATCH_SIZE))
        results: List[Dict[str, Any] | None] = [None] * len(papers)
        pending: List[Dict[str, Any]] = []

        for idx, paper in enumerate(papers):
            focuses = select_focus_authors(paper)
            if not focuses:
                results[idx] = self._neutral_rating(
                    [],
                    "No author metadata was available; assigned a neutral low-confidence author rating.",
                )
                continue

            rating_path = self._cache_path("ratings", self._rating_key(paper, focuses))
            cached = _read_json(rating_path)
            if cached is not None and self._rating_has_author_signal(cached):
                sanitized_cached = dict(cached)
                cached_profiles = cached.get("author_profiles")
                if isinstance(cached_profiles, list):
                    sanitized_cached["author_profiles"] = [
                        self._public_author_profile(profile)
                        for profile in cached_profiles
                        if isinstance(profile, dict)
                    ]
                results[idx] = sanitized_cached
                continue

            profiles = [self.fetch_author_profile(paper, focus) for focus in focuses]
            pending.append(
                {
                    "idx": idx,
                    "paper": paper,
                    "profiles": profiles,
                    "rating_path": rating_path,
                }
            )

        for start in range(0, len(pending), batch_size):
            chunk = pending[start : start + batch_size]
            batch_payload = [(entry["paper"], entry["profiles"]) for entry in chunk]
            try:
                ratings = self._call_llm_ratings_batch(batch_payload)
            except Exception:
                ratings = [
                    self._neutral_rating(
                        entry["profiles"],
                        "Author metadata lookup or LLM synthesis failed; assigned a neutral low-confidence author rating.",
                    )
                    for entry in chunk
                ]
            if len(ratings) < len(chunk):
                ratings = list(ratings) + [
                    self._neutral_rating(
                        entry["profiles"],
                        "Author-rating LLM output was unavailable; assigned a neutral low-confidence author rating.",
                    )
                    for entry in chunk[len(ratings) :]
                ]

            for entry, rating in zip(chunk, ratings):
                if not isinstance(rating, dict):
                    rating = self._neutral_rating(
                        entry["profiles"],
                        "Author-rating LLM output was unavailable; assigned a neutral low-confidence author rating.",
                    )
                rating["rated_at"] = datetime.now(timezone.utc).isoformat()
                if not (
                    self._is_neutral_fallback_rating(rating)
                    and self._profiles_have_author_signal(entry["profiles"])
                ):
                    _write_json(entry["rating_path"], rating)
                results[entry["idx"]] = rating

        return [
            rating
            if isinstance(rating, dict)
            else self._neutral_rating(
                [],
                "Author-rating LLM output was unavailable; assigned a neutral low-confidence author rating.",
            )
            for rating in results
        ]
