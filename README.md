# 을지로·종각 점심줄

을지로3가·종각역 일대 점심 식당 29곳의 예상 혼잡도를, 서울시 **실시간 도시데이터**(SKT·KT 기지국 신호 기반 권역 인구)로 보정해 보여주는 정적 웹앱입니다. GitHub Pages로 서빙하고, GitHub Actions가 평일 낮 10분마다 데이터를 갱신합니다.

## 구조

```
index.html                  # 페이지 전체 (HTML·CSS·JS 한 파일)
data/latest.json            # 페이지가 읽는 현재 권역 값 + 12시간 예측 (Actions가 갱신)
data/history/YYYY-MM.csv    # 집계 시각별 권역 인구 기록 ('평소 대비' 보정용)
data/restaurants.json       # 범위 안 영업 중인 일반음식점 전수 목록 (월 1회 갱신)
scripts/fetch_seoul.py      # 실시간 인구 API 호출 → latest.json / history 갱신
scripts/build_restaurants.py# 일반음식점 인허가 API → restaurants.json (EPSG:5174→WGS84)
.github/workflows/fetch.yml             # 평일 09:00–18:59 KST 10분마다
.github/workflows/build_restaurants.yml # 매월 2일 03:10 KST, 수동 실행 가능
```

## 처음 한 번 설정

1. **시크릿 등록** — Settings → Secrets and variables → Actions → *New repository secret*
   - Name: `SEOUL_API_KEY`
   - Value: 서울 열린데이터광장에서 발급받은 인증키
2. **Pages 켜기** — Settings → Pages → Source: *Deploy from a branch*, Branch: `main` / `/ (root)` → Save
3. **첫 실행** — Actions 탭 → *권역 인구 갱신* → *Run workflow*. 성공하면 `data/latest.json`이 커밋되고 1~2분 뒤 페이지에 반영됩니다.
4. **식당 전수 목록** — Actions 탭 → *식당 전수 목록 갱신* → *Run workflow*. 영업 중인 일반음식점 12만 건을 훑어 범위 안의 가게만 `data/restaurants.json`에 남깁니다(3~5분). 이후 매월 자동 갱신됩니다.

이후에는 손댈 것이 없습니다. Actions의 cron은 바쁜 시간대에 몇 분 늦게 돌 수 있습니다.

## 숫자가 나오는 방식

- **기본 예상**: 직장가 점심 패턴(11:40 첫 물결, 12:10 정점, 12:50 두 번째 물결)에 식당별 인기도·회전율을 곱한 0~100 추정치. 측정값이 아닙니다.
- **권역 보정**: 식당마다 가까운 권역 2곳의 혼잡 등급을 거리 비중으로 섞어 곱합니다.
  여유 ×0.85 · 보통 ×1.0 · 약간 붐빔 ×1.15 · 붐빔 ×1.3
  - 종각: 보신각 0.6 + 종로·청계 관광특구 0.4
  - 을지로3가: 종로·청계 0.5 + 명동 관광특구 0.5 (을지로 전용 권역이 없음)
  - 을지로4가: 종로·청계 0.6 + 동대문 관광특구 0.4
- **시간 미리보기**: 서울시가 주는 시간대별 예측 등급을 씁니다.
- **평소 대비**: `data/history`에 같은 요일 종류(평일/주말)의 기록이 3일 이상 쌓이면, 등급 대신 "지금 인구 ÷ 같은 시간대 지난 날짜 중앙값" 비율로 보정합니다(+20% → 약 ×1.16, 범위 ×0.7~1.45).
- **전수 목록의 식당**: 영업시간·인기도 정보가 없으므로 식당별 대기 예측 없이, 가까운 역 기준 구역의 권역 보정 계수만으로 "주변 여유/보통/붐빔"을 표시합니다. 확인된 식당(`R` 배열)과 상호가 같으면 서로 연결되고, 좌표는 인허가 값으로 덮어씁니다.
- 서울시 값은 5분 집계에 15~30분 지연이므로, 화면 값은 그만큼 전 상황입니다.

보정 계수와 권역 비중은 `index.html` 상단의 `AREA_SRC`, `LVL_FACTOR`에 있습니다. 식당 목록은 같은 파일의 `R` 배열입니다.

## 다음 단계 (예정)

- 줄 상황 제보: Supabase 테이블 하나로 사용자 제보를 받아 최근 40분 제보를 예상치보다 우선 반영

## 데이터 출처

- 서울 열린데이터광장, 서울 실시간 도시데이터(실시간 인구) — https://data.seoul.go.kr/dataVisual/seoul/guide.do
