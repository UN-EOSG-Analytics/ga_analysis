"""Build the self-contained UNGA AI dashboard from a completed analysis run.

The analysis run is read, never modified. Dashboard-only rules (AI status
resolution, theme groups, the USA regional assignment and the UN mechanism
adjudication) live in dashboard/config/ and are documented in dashboard/README.md.

    python dashboard/build_dashboard.py [--run-id 982ee8fb3de51100]
"""
from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HERE = Path(__file__).resolve().parent
CONFIG = HERE / "config"
DEFAULT_RUN = "982ee8fb3de51100"
YEARS = list(range(2017, 2027))
GROUPS = [
    "African States",
    "Asia-Pacific States",
    "Eastern European States",
    "Latin American and Caribbean States",
    "Western European and other States",
]
MECHANISMS = ["Dialogue", "Panel", "Fund"]
POSITIONS = ["Support", "Request", "Reservation", "Mention", "Excluded"]
AI_TERM = re.compile(r"[^.?!]*\b(artificial intelligence|AI)\b[^.?!]*[.?!]?")


def read_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def pdf_symbol(origin_file: str) -> str | None:
    """A_72_PV_20_EN.pdf -> A/72/PV.20"""
    match = re.search(r"A_(\d+)_PV_(\d+)", origin_file or "")
    return f"A/{match.group(1)}/PV.{match.group(2)}" if match else None


def locate(locator: dict) -> str:
    if "pdf_page" in locator:
        return f"page {locator['pdf_page']}, paragraph {locator.get('paragraph')}"
    if "start" in locator:
        seconds = int(float(locator["start"]))
        return f"at {seconds // 3600}:{seconds % 3600 // 60:02d}:{seconds % 60:02d} in the recording"
    if "line_start" in locator:
        return f"transcript lines {locator['line_start']}-{locator['line_end']}"
    return ""


def speech_meta(year: int, iso3: str) -> dict:
    path = ROOT / "data" / "analysis_ready_en" / str(year) / f"{year}_{iso3}.json"
    data = read_json(path)
    title = data.get("speaker_title") or ""
    symbol = pdf_symbol(data.get("origin_file", ""))
    return {
        "speaker": data.get("speaker_name") or "",
        "title": title if len(title) <= 80 else "",
        "date": data.get("speech_date") or "",
        "type": "Official record" if data.get("source_type") == "official_transcript" else "Automatic transcript (unofficial)",
        "record": symbol,
        "url": f"https://undocs.org/en/{symbol}" if symbol else data.get("source_url"),
        "audio": data.get("audio_url"),
    }


def build(run_id: str) -> dict:
    run = ROOT / "output" / "analysis" / "runs" / run_id
    taxonomy = read_json(run / "taxonomy.json")["codes"]
    labels = {code: body["label"] for code, body in taxonomy.items()}
    theme_groups = read_json(CONFIG / "theme_groups.json")["groups"]
    grouped = [code for group in theme_groups for code in group["codes"]]
    assert sorted(grouped) == sorted(labels), "theme_groups.json must assign every taxonomy code exactly once"

    # Countries and regions: USA joins WEOG for the dashboard only.
    countries = {}
    for row in read_csv(ROOT / "config" / "un_regional_groups.csv"):
        group = row["analytical_group"]
        if row["iso3"] == "USA":
            group = "Western European and other States"
        assert group in GROUPS, row
        countries[row["iso3"]] = {"name": row["country"], "group": group}

    overrides = {row["speech_id"]: row for row in read_csv(CONFIG / "ai_status_overrides.csv")}
    reviewed_passages = Counter()
    passages = {}
    with (run / "passage_ai_review.jsonl").open(encoding="utf-8") as handle:
        for line in handle:
            passage = json.loads(line)
            if passage.get("ai_status") in ("Yes", "Uncertain"):
                reviewed_passages[passage["speech_id"]] += 1
            passages[passage["passage_id"]] = passage

    # Speech records: unselected speeches (no AI passage reviewed) become No.
    records, meta = [], {}
    pending_to_no = 0
    for row in read_csv(run / "country_year_theme_matrix.csv"):
        sid, status = row["speech_id"], row["ai_status"]
        codes = {code: row[code] for code in labels}
        override = overrides.get(sid)
        if override:
            assert status == "Uncertain", f"override for {sid} targets a resolved speech"
            status = override["ai_status"]
            codes = {code: ("1" if code == override["theme_code"] else "0") for code in labels} if status == "Yes" else {}
        elif status == "Uncertain":
            assert not reviewed_passages[sid], f"{sid} has reviewed AI passages but no override"
            status, codes = "No", {}
            pending_to_no += 1
        flags = []
        for group in theme_groups:
            values = [codes.get(code, "") for code in group["codes"]] if status == "Yes" else []
            if "1" in values:
                flags.append(1)
            elif values and all(value == "0" for value in values):
                flags.append(0)
            else:
                flags.append(None)
        year, iso3 = int(row["year"]), row["country_iso3"]
        records.append({"id": sid, "y": year, "c": iso3, "ai": status == "Yes", "t": flags})
        meta[sid] = speech_meta(year, iso3)
        if override:
            meta[sid]["override"] = override["rationale"]

    # Evidence quotes behind each AI-positive speech.
    evidence = {}
    quotes = {}
    for row in read_csv(run / "evidence_register.csv"):
        locator = json.loads(row["locator"])
        quotes[row["evidence_id"]] = {"q": row["quote"], "at": locate(locator)}
        themes = [labels[code] for code, value in json.loads(row["themes"]).items() if value == "Yes"]
        evidence.setdefault(row["speech_id"], []).append({"e": row["evidence_id"], "q": row["quote"], "at": locate(locator), "th": themes})
    for sid, override in overrides.items():
        if override["ai_status"] != "Yes":
            continue
        passage = passages[override["passage_id"]]
        sentence = next(m.group(0).strip() for m in AI_TERM.finditer(passage["text"]))
        evidence[sid] = [{"e": override["passage_id"], "q": sentence, "at": locate(passage["locator"]), "th": [labels[override["theme_code"]]]}]

    # UN mechanisms: every Dialogue/Panel/Fund row in the run must be adjudicated.
    stances = {(row["evidence_id"], row["mechanism"]): row for row in read_csv(run / "institution_stances.csv")}
    for row in stances.values():
        quotes.setdefault(row["evidence_id"], {"q": row["quote"], "at": locate(json.loads(row["locator"]))})
    positions = []
    for row in read_csv(CONFIG / "un_mechanism_positions.csv"):
        assert row["position"] in POSITIONS and row["mechanism"] in MECHANISMS, row
        source = stances.get((row["evidence_id"], row["mechanism"]))
        assert source and source["iso3"] == row["iso3"] and source["year"] == row["year"], row
        positions.append({"y": int(row["year"]), "c": row["iso3"], "e": row["evidence_id"], "m": row["mechanism"],
                          "p": row["position"], "k": row["commitment"] == "Yes", "n": row["note"]})
    covered = {(p["e"], p["m"]) for p in positions}
    missing = [key for key in stances if key[1] in MECHANISMS and key not in covered]
    assert not missing, f"unadjudicated mechanism rows: {missing}"

    request_rules = {row["evidence_id"]: row for row in read_csv(CONFIG / "un_requests.csv")}
    requests, seen = [], set()
    for row in stances.values():
        explicit = json.loads(row["stances"])["request"] and row["un_role"] == "explicit"
        rule = request_rules.get(row["evidence_id"], {}).get("decision")
        if (explicit and rule != "exclude") or rule == "include":
            if row["evidence_id"] in seen:
                continue
            seen.add(row["evidence_id"])
            requests.append({"y": int(row["year"]), "c": row["iso3"], "e": row["evidence_id"],
                             "f": json.loads(row["requested_functions"])})

    def curated(name: str, fields: dict) -> list[dict]:
        out = []
        for row in read_csv(CONFIG / name):
            assert row["evidence_id"] in quotes, row
            out.append({"y": int(row["year"]), "c": row["iso3"], "e": row["evidence_id"], **{k: row[v] for k, v in fields.items()}})
        return out

    models = curated("institutional_models.csv", {"cat": "category", "p": "proposal"})
    venues = curated("other_venues.csv", {"v": "venue"})
    used = {item["e"] for item in positions + requests + models + venues}

    return {
        "run": run_id,
        "years": YEARS,
        "groups": GROUPS,
        "themes": [group["name"] for group in theme_groups],
        "themeCodes": {group["name"]: [labels[code] for code in group["codes"]] for group in theme_groups},
        "countries": countries,
        "records": records,
        "meta": meta,
        "evidence": evidence,
        "quotes": {key: value for key, value in quotes.items() if key in used},
        "positions": positions,
        "requests": sorted(requests, key=lambda r: (r["y"], r["c"])),
        "models": models,
        "venues": venues,
        "implications": read_json(CONFIG / "implications.json")["items"],
        "pendingToNo": pending_to_no,
    }


def check(data: dict) -> dict:
    """Headline figures, printed so every rebuild can be compared with the brief."""
    groups = {iso: c["group"] for iso, c in data["countries"].items()}
    r26 = [r for r in data["records"] if r["y"] == 2026]
    weog = [r for r in r26 if groups[r["c"]] == "Western European and other States"]
    support = {m: len({p["c"] for p in data["positions"] if p["y"] == 2026 and p["m"] == m and p["p"] == "Support"}) for m in MECHANISMS}
    return {
        "2026 AI references": f"{sum(r['ai'] for r in r26)}/{len(r26)}",
        "2026 WEOG incl. USA": f"{sum(r['ai'] for r in weog)}/{len(weog)}",
        "2026 supporters": support,
        "unselected speeches set to No": data["pendingToNo"],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--run-id", default=DEFAULT_RUN)
    parser.add_argument("--out", default=str(HERE / "UNGA_AI_Dashboard.html"))
    args = parser.parse_args()
    data = build(args.run_id)
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    html = (HERE / "template.html").read_text(encoding="utf-8").replace("__DASHBOARD_DATA__", payload)
    Path(args.out).write_text(html, encoding="utf-8")
    print(json.dumps(check(data), indent=2))
    print(f"Wrote {args.out}")


if __name__ == "__main__":
    main()
