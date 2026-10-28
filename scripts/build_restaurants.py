#!/usr/bin/env python3
"""서울시 일반음식점 인허가 정보(LOCALDATA_072404)에서 을지로·종각 일대 영업 중인 식당을 추려
data/restaurants.json 을 만든다. 한 달에 한 번 정도 돌리면 충분하다.

사용: SEOUL_API_KEY=... python3 scripts/build_restaurants.py
필요: pip install pyproj   (X,Y 가 EPSG:5174 중부원점 TM 이라 WGS84 로 변환)
"""
import json
import os
import sys
import time
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path

from pyproj import Transformer

ROOT = Path(__file__).resolve().parent.parent
KEY = os.environ.get("SEOUL_API_KEY", "").strip()
SERVICE = "LOCALDATA_072404"
PAGE = 1000
KST = timezone(timedelta(hours=9))

# 범위: 서쪽 시청·을지로입구 ~ 동쪽 을지로4가, 남쪽 명동 북단 ~ 북쪽 종로3가
BBOX = {"minLat": 37.5610, "maxLat": 37.5760, "minLng": 126.9750, "maxLng": 127.0030}

# 점심 식당으로 보기 어려운 업태
EXCLUDE = {
    "정종/대포집/소주방", "호프/통닭", "감성주점", "라이브카페", "까페", "전통찻집", "키즈카페",
    "출장조리", "이동조리", "관광호텔", "기타 휴게음식점", "룸살롱", "단란주점", "유흥주점",
}

to_wgs = Transformer.from_crs("EPSG:5174", "EPSG:4326", always_xy=True)


def fetch_page(start: int, end: int) -> dict:
    # 세 번째 경로 인자가 영업상태(01 = 영업/정상). 두 번째는 비워 둔다.
    url = f"http://openapi.seoul.go.kr:8088/{KEY}/json/{SERVICE}/{start}/{end}/%20/01"
    last = None
    for attempt in range(4):
        try:
            with urllib.request.urlopen(url, timeout=60) as r:
                j = json.load(r)
            s = j.get(SERVICE)
            if not s:
                raise RuntimeError((j.get("RESULT") or {}).get("MESSAGE", "no body"))
            return s
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"page {start}-{end} failed: {last}")


def clean(s: str) -> str:
    return (s or "").strip()


def main() -> int:
    if not KEY:
        print("SEOUL_API_KEY 가 없습니다.", file=sys.stderr)
        return 2

    first = fetch_page(1, 1)
    total = int(first.get("list_total_count") or 0)
    print(f"영업 중 일반음식점 {total:,}건, {PAGE}건씩 조회")

    items = {}
    seen_uptae = {}
    start = 1
    while start <= total:
        end = min(start + PAGE - 1, total)
        rows = fetch_page(start, end).get("row") or []
        for x in rows:
            try:
                X, Y = float(clean(x.get("X"))), float(clean(x.get("Y")))
            except ValueError:
                continue
            lng, lat = to_wgs.transform(X, Y)
            if not (BBOX["minLat"] <= lat <= BBOX["maxLat"] and BBOX["minLng"] <= lng <= BBOX["maxLng"]):
                continue
            cat = clean(x.get("UPTAENM")) or "기타"
            seen_uptae[cat] = seen_uptae.get(cat, 0) + 1
            if cat in EXCLUDE:
                continue
            addr = clean(x.get("RDNWHLADDR")) or clean(x.get("SITEWHLADDR"))
            addr = addr.replace("서울특별시 ", "")
            mgt = clean(x.get("MGTNO"))
            items[mgt] = {
                "id": mgt,
                "n": clean(x.get("BPLCNM")),
                "c": cat,
                "a": addr,
                "lat": round(lat, 5),
                "lng": round(lng, 5),
            }
        print(f"  {end:,}/{total:,}  누적 {len(items)}곳", flush=True)
        start = end + 1

    out = {
        "builtAt": datetime.now(KST).strftime("%Y-%m-%d %H:%M"),
        "source": "서울시 일반음식점 인허가 정보 (영업/정상), EPSG:5174→WGS84",
        "bbox": BBOX,
        "count": len(items),
        "items": sorted(items.values(), key=lambda r: r["n"]),
    }
    path = ROOT / "data" / "restaurants.json"
    path.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"저장: {path} ({len(items)}곳)")
    print("업태 분포(범위 내):", dict(sorted(seen_uptae.items(), key=lambda kv: -kv[1])))
    return 0


if __name__ == "__main__":
    sys.exit(main())
