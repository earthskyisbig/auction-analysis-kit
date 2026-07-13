# 🏛️ 경매 스크리닝 웹앱 (로컬)

물건 조건을 입력하면 **1조건→2조건→3조건 퍼널**로 걸러 통과 물건만 비교분석하는 로컬 웹앱.

## 퍼널 3단계

| 단계 | 조건 | 방법 |
|------|------|------|
| **1조건** | 아파트 · 유찰횟수 · 전용면적 · 최저매각가 | court-search `collect_api.py` (서울=5개 법원 전량 크롤링) |
| **2조건** | 세대수 · 사용승인연도 · 실거래 존재 | 공동주택 기본정보 API(세대·연식) + 실거래 DuckDB 캐시(시세) |
| **3조건** | 매각물건명세서·현황조사·감정평가·문건송달 → 권리리스크 | rights `analyze_case.py` (**저감율 상위 N건만**, 느려서) |
| **최종** | 통과 물건 비교분석 | 입지(코드 4축)·실거래 시세·수익률(8대비용) |

> **왜 3조건은 상위 N건만?** 권리분석은 물건당 Playwright 스크래핑 ~40초로 느리다.
> 2조건 통과분 중 저감율(할인폭) 상위 N건(기본 3)만 돌려 실용 속도를 확보한다.

## 실행

```bash
cd auction-analysis-kit
pip install flask duckdb playwright "PublicDataReader>=1.1.1" python-dotenv pandas requests
python -m playwright install chromium
# .env 에 PUBLIC_DATA_API_KEY(실거래·공동주택) · KAKAO_REST_API_KEY(입지) 필요

python webapp/app.py
# → http://127.0.0.1:5000 접속, 폼 입력 후 "분석 시작"
```

첫 실행은 실거래 캐시(`webapp/realprice_cache.duckdb`)를 채우느라 느리고, 이후 재사용으로 빨라진다.
서울 전체는 5개 법원 크롤링 + 권리분석 상위 N건이라 수 분 소요(퍼널 카운트가 실시간 갱신됨).

## 구조
- `app.py` — Flask 라우트 + 백그라운드 잡 매니저(스레드) + 상태 폴링 API
- `pipeline.py` — 1/2/3조건 + 보고서(기존 스킬 스크립트 subprocess 재사용)
- `realprice_db.py` — 실거래 DuckDB 캐시(시군구·월 단위, PublicDataReader)
- `templates/index.html` — 폼 + 퍼널 + 비교표(단일 페이지, 2초 폴링)

## 한계
- **로컬 전용**(API 키·크롤링). 공개 배포는 별도 WSGI·큐 구성 필요.
- 단지 미매칭(등록명 불일치·소규모)은 2조건 탈락 처리 — "500세대 미만"으로 단정 아님.
- 시세·수익률·낙찰가는 추정. 입찰 전 등기부·전입세대열람·현장 검증 필수.
