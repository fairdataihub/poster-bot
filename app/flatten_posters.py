#!/usr/bin/env python3
"""Flatten canonical posters.science records into embedding-ready JSONL.

Walks EXACTLY the 4 canonical merged dirs (31,363 `{repo_id}_complete.json`
records — never extractions/metadata/datacite_cache/azure_snap), sanitizes text
per the anomaly audits, classifies licenses with the repo's own policy module,
and emits one JSON line per poster. Source files are opened read-only.

Usage:
  flatten_posters.py --out /storage/posterbot/scratch/dry.jsonl --limit-per-dir 50
  flatten_posters.py --out /storage/posterbot/scratch/posters.jsonl          # full run
"""
import argparse
import json
import re
import sys
from pathlib import Path

CORPUS = Path("/storage/poster-work")
CANONICAL_DIRS = [
    ("pre2025", "zenodo",   CORPUS / "pre2025/merged/zenodo"),
    ("pre2025", "figshare", CORPUS / "pre2025/merged/figshare"),
    ("data2025", "zenodo",   CORPUS / "data2025/merged/zenodo"),
    ("data2025", "figshare", CORPUS / "data2025/merged/figshare"),
]

# the corpus repo's own license policy (single source of truth)
sys.path.insert(0, str(CORPUS / "repo/scripts/post_processing"))
from license_policy import classify_license  # noqa: E402

MAX_SECTION_WORDS = 6000     # cap pathological sections (anom audits: 34 sections >6k words)
MAX_DESC_WORDS = 2000        # description embed cap (p95 is 430 words)
MAX_CREATORS = 100
TOKENS_PER_WORD = 1.34       # measured on this corpus: 740 words ~= 991 tokens

_alpha = re.compile(r"[A-Za-z]")


def clean_text(s, max_words=None):
    """None-safe: strip, drop junk (<3 chars or <2 letters), optionally cap words."""
    if not s or not isinstance(s, str):
        return None
    s = s.replace("\x00", " ")          # PostgreSQL text cannot store NUL bytes
    s = " ".join(s.split())
    if len(s) < 3 or len(_alpha.findall(s)) < 2:
        return None
    if max_words:
        w = s.split()
        if len(w) > max_words:
            s = " ".join(w[:max_words])
    return s


def first_title(d):
    for t in d.get("titles") or []:
        if not isinstance(t, dict):
            continue
        v = clean_text(t.get("title"))
        if v:
            return v
    return None


def best_description(d):
    """Prefer the deposit Abstract (kept even for license-blocked records)."""
    descs = [x for x in (d.get("descriptions") or []) if isinstance(x, dict)]
    for pool in (
        [x for x in descs if x.get("descriptionType") == "Abstract"],
        descs,
    ):
        for x in pool:
            v = clean_text(x.get("description"))
            if v:
                return v
    return None


def doi_and_repo_id(d, fallback_stem):
    doi = repo_id = None
    for ident in d.get("identifiers") or []:
        if not isinstance(ident, dict):
            continue
        val = (ident.get("identifier") or "").strip()
        typ = ident.get("identifierType")
        if typ == "DOI" and val and not doi:
            doi = val
        elif typ == "Other" and val and not repo_id:
            repo_id = val
    return doi, repo_id or fallback_stem


def creators_fields(d):
    creators = [c for c in (d.get("creators") or []) if isinstance(c, dict)][:MAX_CREATORS]
    parts = []
    for c in creators:
        name = c.get("name") or " ".join(
            x for x in (c.get("givenName"), c.get("familyName")) if x
        )
        name = clean_text(name)
        if not name:
            continue
        affs = [a.get("name") for a in (c.get("affiliation") or []) if isinstance(a, dict)]
        affs = [a for a in (clean_text(a) for a in affs) if a]
        parts.append(f"{name} ({'; '.join(affs)})" if affs else name)
    return creators, ("; ".join(parts) or None)


def sections_text(d):
    """Sanitized 'Title: content' lines; returns (kept_count, joined_text)."""
    cont = d.get("content")
    secs = (cont.get("sections") or []) if isinstance(cont, dict) else []
    out = []
    for s in secs:
        if not isinstance(s, dict):
            continue
        body = clean_text(s.get("sectionContent"), max_words=MAX_SECTION_WORDS)
        if not body:
            continue
        head = clean_text(s.get("sectionTitle"))
        out.append(f"{head}: {body}" if head else body)
    return len(out), ("\n".join(out) or None)


def flatten_one(path, batch, source):
    d = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(d, dict):
        return None

    doi, repo_id = doi_and_repo_id(d, path.stem.removesuffix("_complete"))
    title = first_title(d)
    desc = best_description(d)
    subjects = [v for v in (clean_text(s.get("subject") if isinstance(s, dict) else s)
                            for s in d.get("subjects") or []) if v][:60]
    creators_raw, creators_text = creators_fields(d)
    conf = d.get("conference")
    if not isinstance(conf, dict):
        conf = {}
    conf_name = clean_text(conf.get("conferenceName"))
    n_sections, sec_text = sections_text(d)
    rights_list = d.get("rightsList")
    rights = "; ".join(
        v for v in ((e.get("rights") if isinstance(e, dict) else e)
                    for e in (rights_list or [])) if isinstance(v, str)
    ) or None

    parts = []
    if title:
        parts.append(title)
    if desc:
        parts.append(clean_text(desc, max_words=MAX_DESC_WORDS))
    if sec_text:
        parts.append(sec_text)                      # captions deliberately excluded (OCR junk)
    if subjects:
        parts.append("Keywords: " + ", ".join(subjects))
    if conf_name:
        y = conf.get("conferenceYear")
        parts.append(f"Conference: {conf_name}" + (f" {y}" if y else ""))
    embed_text = "\n".join(parts)
    if not embed_text:
        return None

    def to_int(v):
        try:
            return int(v)
        except (TypeError, ValueError):
            return None

    return {
        "poster_key": doi or f"{source}/{repo_id}",
        "doi": doi,
        "repo_id": str(repo_id),
        "source": source,
        "batch": batch,
        "title": title,
        "description": desc,
        "subjects": subjects or None,
        "creators": creators_raw or None,
        "creators_text": creators_text,
        "conference_name": conf_name,
        "conference_year": to_int(conf.get("conferenceYear")),
        "publication_year": to_int(d.get("publicationYear")),
        "research_field": clean_text(d.get("researchField")),
        "rights": rights,
        "license_class": classify_license(rights_list),   # allowed | blocked | unknown
        "license_blocked": bool(d.get("_license_blocked")),
        "n_sections": n_sections,
        "embed_tokens": int(len(embed_text.split()) * TOKENS_PER_WORD),
        "url": (f"https://doi.org/{doi}" if doi
                else f"https://zenodo.org/records/{repo_id}" if source == "zenodo" else None),
        "embed_text": embed_text,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--limit-per-dir", type=int, default=None)
    args = ap.parse_args()

    stats = {"read": 0, "written": 0, "errors": 0,
             "allowed": 0, "blocked": 0, "unknown": 0, "flag_blocked": 0}
    keys = set()
    tok = []
    with open(args.out, "w", encoding="utf-8") as out:
        for batch, source, dirpath in CANONICAL_DIRS:
            files = sorted(dirpath.glob("*_complete.json"))
            if args.limit_per_dir:
                step = max(1, len(files) // args.limit_per_dir)
                files = files[::step][: args.limit_per_dir]
            n_dir = 0
            for f in files:
                stats["read"] += 1
                try:
                    row = flatten_one(f, batch, source)
                except Exception as e:
                    stats["errors"] += 1
                    print(f"ERROR {f}: {e}", file=sys.stderr)
                    continue
                if row is None:
                    stats["errors"] += 1
                    continue
                if row["poster_key"] in keys:               # duplicate DOI guard
                    row["poster_key"] = f"{source}/{row['repo_id']}"
                keys.add(row["poster_key"])
                stats[row["license_class"]] += 1
                stats["flag_blocked"] += row["license_blocked"]
                tok.append(row["embed_tokens"])
                out.write(json.dumps(row, ensure_ascii=False) + "\n")
                stats["written"] += 1
                n_dir += 1
            print(f"{batch}/{source}: {n_dir} written (of {len(files)} scanned)")

    tok.sort()
    pct = lambda p: tok[min(len(tok) - 1, int(p * len(tok)))] if tok else 0
    print(f"\nstats: {stats}")
    print(f"embed_tokens est.: p50={pct(.5)} p95={pct(.95)} p99={pct(.99)} max={tok[-1] if tok else 0}")
    print(f"over 3072-token window: {sum(t > 3072 for t in tok)} posters (truncate)")


if __name__ == "__main__":
    main()
