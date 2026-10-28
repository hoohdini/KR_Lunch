#!/usr/bin/env python3
"""서울시 실시간 도시데이터(실시간 인구)에서 권역 데이터를 받아 data/latest.json 을 갱신한다.

사용: SEOUL_API_KEY=... python3 scripts/fetch_seoul.py
- data/latest.json  : 페이지가 읽는 현재 값 + 12시간 예측
- data/history/YYYY-MM.csv : 집계 시각별 권역 인구 기록 (나중에 '평소 대비' 보정용)
"""
import csv
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
KEY = os.environ.get("SEOUL_API_KEY", "").strip()
CODES = ["POI006", "POI010", "POI003", "POI002"]  # 종로·청계, 보신각, 명동, 동대문
KST = timezone(timedelta(hours=9))


def fetch(code: str) -> dict:
    url = f"http://openapi.seoul.go.kr:8088/{KEY}/json/citydata_ppltn/1/5/{urllib.parse.quote(code)}"
    last = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(url, timeout=20) as r:
                j = json.load(r)
            rows = j.get("SeoulRtd.citydata_ppltn") or []
            if not rows:
                msg = (j.get("RESULT") or {}).get("RESULT.MESSAGE", "no rows")
                raise RuntimeError(f"{code}: {msg}")
            d = rows[0]
            return {
                "nm": d["AREA_NM"],
                "lvl": d["AREA_CONGEST_LVL"],
                "min": int(d["AREA_PPLTN_MIN"]),
                "max": int(d["AREA_PPLTN_MAX"]),
                "time": d["PPLTN_TIME"],
                "fcst": [
                    {
                        "t": f["FCST_TIME"],
                        "lvl": f["FCST_CONGEST_LVL"],
                        "min": int(f["FCST_PPLTN_MIN"]),
                        "max": int(f["FCST_PPLTN_MAX"]),
                    }
                    for f in (d.get("FCST_PPLTN") or [])
                ],
            }
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(3 * (attempt + 1))
    raise RuntimeError(f"{code} failed: {last}")


def is_weekday(dt: datetime) -> bool:
    return dt.weekday() < 5


def load_history() -> list[dict]:
    rows = []
    for p in sorted((ROOT / "data" / "history").glob("*.csv")):
        with p.open(encoding="utf-8", newline="") as f:
            for r in csv.DictReader(f):
                try:
                    dt = datetime.strptime(r["time"], "%Y-%m-%d %H:%M").replace(tzinfo=KST)
                    rows.append({"dt": dt, "code": r["code"], "mid": (int(r["min"]) + int(r["max"])) / 2})
                except (KeyError, ValueError):
                    continue
    return rows


def median(xs: list[float]) -> float:
    s = sorted(xs)
    n = len(s)
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2


def baseline_for(code: str, rows: list[dict], today: datetime) -> dict:
    """같은 요일 종류(평일/주말), 지난 날짜들의 시간대별 인구 중앙값.

    오늘 값은 제외한다(오늘이 평소보다 붐비는지 보려는 것이므로).
    시간대별로 먼저 날짜별 평균을 낸 뒤 날짜 간 중앙값을 취해, 10분 단위
    기록이 많은 날이 과대 반영되지 않게 한다.
    """
    kind = "weekday" if is_weekday(today) else "weekend"
    per_day_hour: dict[tuple[str, int], list[float]] = {}
    for r in rows:
        if r["code"] != code or r["dt"].date() == today.date():
            continue
        if (r["dt"].weekday() < 5) != (kind == "weekday"):
            continue
        per_day_hour.setdefault((r["dt"].strftime("%Y-%m-%d"), r["dt"].hour), []).append(r["mid"])
    by_hour: dict[int, list[float]] = {}
    days = set()
    for (day, hour), vals in per_day_hour.items():
        days.add(day)
        by_hour.setdefault(hour, []).append(sum(vals) / len(vals))
    return {
        "kind": kind,
        "n_days": len(days),
        "by_hour": {str(h): round(median(v)) for h, v in sorted(by_hour.items())},
    }


def main() -> int:
    if not KEY:
        print("SEOUL_API_KEY 가 없습니다.", file=sys.stderr)
        return 2

    areas = {}
    errors = []
    for c in CODES:
        try:
            areas[c] = fetch(c)
        except Exception as e:  # noqa: BLE001
            errors.append(str(e))

    if not areas:
        print("\n".join(errors), file=sys.stderr)
        return 1

    latest_path = ROOT / "data" / "latest.json"
    prev = {}
    if latest_path.exists():
        try:
            prev = json.loads(latest_path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            prev = {}

    # 일부 권역만 실패했으면 그 권역은 이전 값을 유지한다.
    merged = dict((prev.get("areas") or {}))
    merged.update(areas)

    # 집계 시각이 바뀐 권역만 기록 (같은 5분 집계를 중복 저장하지 않음)
    now = datetime.now(KST)
    hist = ROOT / "data" / "history" / f"{now:%Y-%m}.csv"
    hist.parent.mkdir(parents=True, exist_ok=True)
    seen = set()
    if hist.exists():
        with hist.open(encoding="utf-8", newline="") as f:
            for row in csv.DictReader(f):
                seen.add((row["time"], row["code"]))
    new_rows = [
        (a["time"], c, a["nm"], a["lvl"], a["min"], a["max"])
        for c, a in areas.items()
        if (a["time"], c) not in seen
    ]
    if new_rows:
        write_header = not hist.exists()
        with hist.open("a", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            if write_header:
                w.writerow(["time", "code", "name", "level", "min", "max"])
            w.writerows(new_rows)

    # 평소 대비 기준선 (기록이 쌓일수록 정확해진다; 페이지는 n_days >= 3 일 때만 사용)
    history = load_history()
    for c, a in merged.items():
        a["baseline"] = baseline_for(c, history, now)

    out = {"fetchedAt": int(time.time() * 1000), "areas": merged}
    latest_path.parent.mkdir(parents=True, exist_ok=True)
    latest_path.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    summary =", ".join(f"{a['nm'].replace(' 관광특구', '')} {a['lvl']}" for a in areas.values())
    print(f"{next(iter(areas.values()))['time']} 집계 — {summary}")
    if errors:
        print("일부 실패: " + " | ".join(errors), file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
