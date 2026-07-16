#!/usr/bin/env python3
"""Flatten a posters.science NDJSON platform export into embedding-ready JSONL.

The export is a directory of *.ndjson files; each line is
{id, posterUrl, imageUrl, publishedAt, posterJson}, where posterJson is the same
posters.science v0.2 record used elsewhere. Reuses the sanitization helpers from
flatten_posters.py so the embed text is built identically.

Usage:
  flatten_export.py --in /home/joneill/Downloads/posters-science-export \
                    --out /storage/posterbot/scratch/posters.jsonl
"""
import argparse
import glob
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import flatten_posters as fp   # clean_text, first_title, best_description, creators_fields, sections_text, consts


def source_of(pj):
    suf = (pj.get("suffix") or "")
    head = suf.split(".")[0] if suf else ""
    if head == "m9":
        return "figshare"          # figshare DOIs are 10.6084/m9.figshare.*
    if head == "zenodo":
        return "zenodo"
    return head or "other"


def to_int(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


_YEAR = re.compile(r"(\d{4})")


def best_year(record, pj):
    """The export's posterJson.publicationYear is uniformly (wrongly) 2026.
    Recover the real year: the DataCite Issued date, else the platform
    publishedAt timestamp, else the conference year. 100% coverage on this export."""
    for d in pj.get("dates") or []:
        if isinstance(d, dict) and d.get("dateType") == "Issued":
            m = _YEAR.match(d.get("date") or "")
            if m:
                return int(m.group(1))
    m = _YEAR.match(record.get("publishedAt") or "")
    if m:
        return int(m.group(1))
    conf = pj.get("conference")
    cy = conf.get("conferenceYear") if isinstance(conf, dict) else None
    return cy if isinstance(cy, int) else None


def build_row(record):
    pj = record.get("posterJson")
    if not isinstance(pj, dict):
        return None

    doi = fp.clean_text(pj.get("doi"))
    platform_id = str(record["id"])
    title = fp.first_title(pj)
    desc = fp.best_description(pj)
    subjects = [v for v in (fp.clean_text(s.get("subject") if isinstance(s, dict) else s)
                            for s in pj.get("subjects") or []) if v][:60]
    creators_raw, creators_text = fp.creators_fields(pj)
    conf = pj.get("conference")
    if not isinstance(conf, dict):
        conf = {}
    conf_name = fp.clean_text(conf.get("conferenceName"))
    n_sections, sec_text = fp.sections_text(pj)
    rights_list = pj.get("rightsList")
    rights = "; ".join(
        v for v in ((e.get("rights") if isinstance(e, dict) else e)
                    for e in (rights_list or [])) if isinstance(v, str)
    ) or None

    parts = []
    if title:
        parts.append(title)
    if desc:
        parts.append(fp.clean_text(desc, max_words=fp.MAX_DESC_WORDS))
    if sec_text:
        parts.append(sec_text)                    # captions excluded (OCR noise)
    if subjects:
        parts.append("Keywords: " + ", ".join(subjects))
    if conf_name:
        y = conf.get("conferenceYear")
        parts.append(f"Conference: {conf_name}" + (f" {y}" if y else ""))
    embed_text = "\n".join(p for p in parts if p)
    if not embed_text:
        return None

    return {
        "poster_key": doi or f"posters.science/{platform_id}",
        "doi": doi,
        "repo_id": platform_id,                   # posters.science platform id
        "source": source_of(pj),
        "title": title,
        "description": desc,
        "subjects": subjects or None,
        "creators": creators_raw or None,
        "creators_text": creators_text,
        "conference_name": conf_name,
        "conference_year": to_int(conf.get("conferenceYear")),
        "publication_year": best_year(record, pj),
        "research_field": fp.clean_text(pj.get("researchField")),
        "rights": rights,
        "license_class": fp.classify_license(rights_list),   # allowed | blocked | unknown
        "license_blocked": bool(pj.get("_license_blocked")),
        "n_sections": n_sections,
        "embed_tokens": int(len(embed_text.split()) * fp.TOKENS_PER_WORD),
        "url": record.get("posterUrl") or (f"https://doi.org/{doi}" if doi else None),
        "embed_text": embed_text,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", required=True, help="export dir of *.ndjson")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    files = sorted(glob.glob(str(Path(args.inp) / "*.ndjson")))
    stats = {"read": 0, "written": 0, "errors": 0,
             "allowed": 0, "blocked": 0, "unknown": 0, "flag_blocked": 0}
    keys = set()
    tok = []
    with open(args.out, "w", encoding="utf-8") as out:
        for f in files:
            for line in open(f, encoding="utf-8"):
                line = line.strip()
                if not line:
                    continue
                stats["read"] += 1
                try:
                    row = build_row(json.loads(line))
                except Exception as e:
                    stats["errors"] += 1
                    print(f"ERROR {f}: {e}", file=sys.stderr)
                    continue
                if row is None:
                    stats["errors"] += 1
                    continue
                if row["poster_key"] in keys:
                    row["poster_key"] = f"posters.science/{row['repo_id']}"
                keys.add(row["poster_key"])
                stats[row["license_class"]] += 1
                stats["flag_blocked"] += row["license_blocked"]
                tok.append(row["embed_tokens"])
                out.write(json.dumps(row, ensure_ascii=False) + "\n")
                stats["written"] += 1

    tok.sort()
    pct = lambda p: tok[min(len(tok) - 1, int(p * len(tok)))] if tok else 0
    print(f"stats: {stats}")
    print(f"embed_tokens: p50={pct(.5)} p95={pct(.95)} p99={pct(.99)} "
          f"max={tok[-1] if tok else 0} | >3072: {sum(t > 3072 for t in tok)}")


if __name__ == "__main__":
    main()
