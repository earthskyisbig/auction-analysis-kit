# 경매물건 DuckDB 캐싱 설계

**작성일**: 2026-08-07
**배경**: auction-screening 웹앱(`webapp/`) 실행 시 1조건(경매물건 크롤링)이 법원마다 매번
라이브 크롤링(Playwright + API 페이징)으로 이뤄져, 서울/경기 전역 스크리닝이 20분 이상 걸린다.
이 문서는 세 가지 캐싱 개선(경매물건 → 아파트단지 정보 → 실거래 배치채움) 중 **첫 번째: 경매물건
캐싱**을 다룬다.

## 목표

- 서울·경기 전 법원의 아파트 경매물건을 DuckDB에 저장해두고, 스크리닝 시 조건(유찰·가격·면적)은
  라이브 크롤링이 아니라 DuckDB 쿼리로 즉시 필터링한다.
- 주 1회 배치로 캐시를 최신화한다.

## 비목표

- 아파트 외 용도(다세대·오피스텔 등) 캐싱 — 현재 파이프라인은 아파트만 다룸.
- 웹앱에서 수동 "지금 새로고침" 트리거 — 필요해지면 추후 추가.
- 클라우드 cron(Claude schedule 스킬) 연동 — 로컬 DuckDB 파일에 클라우드 cron이 접근 불가하므로
  범위 밖. Windows 작업 스케줄러로 로컬 실행.

## 아키텍처

```
Windows 작업 스케줄러 (주1회)
        │
        ▼
webapp/refresh_auctions.py  ──▶  webapp/auctions.duckdb (서울+경기 15개 법원, 아파트 전체)
        │  (court-search의 collect_api.py를 무필터로 법원별 subprocess 호출 → 파싱 → upsert)
        ▼
webapp/auction_db.py (쿼리 레이어)
        │
        ▼
webapp/pipeline.py stage1()  ──▶  DuckDB 쿼리로 즉시 필터링 (유찰·가격·면적)
                                    (캐시가 비어있으면 기존 라이브 크롤링으로 폴백)
```

## 데이터 모델 (`webapp/auction_db.py`)

```sql
CREATE TABLE IF NOT EXISTS auctions(
  court VARCHAR, case_no VARCHAR, location VARCHAR,
  area_sqm DOUBLE, appraisal_price BIGINT, min_price BIGINT,
  discount_rate INTEGER, fail_count INTEGER, sale_date VARCHAR,
  status VARCHAR,        -- 'active' | '마감'
  first_seen TIMESTAMP, last_seen TIMESTAMP,
  PRIMARY KEY (court, case_no, location)
)
```

- 숫자 필드(감정가·최저가·면적·유찰·저감율)는 문자열이 아니라 실제 숫자로 저장해 범위 쿼리를
  바로 지원한다. `collect_api.py`가 만드는 포맷된 문자열("376,000,000원", "70%", "59.5153㎡")은
  적재 시점에 파싱한다.
- PRIMARY KEY는 기존 `collect_api.py`의 dedup 키(사건번호+물건소재지)에 court를 더한 복합키.
  한 사건에 물건번호가 여러 개일 수 있어 사건번호 단독 키는 물건 손실을 일으킨다는 기존 주석의
  이유를 그대로 따른다.

### 함수

- `ensure()` — 테이블 없으면 생성.
- `upsert(court, rows)` — 이번 크롤링에서 얻은 row 리스트를 upsert(status='active',
  last_seen=now). court 스코프 내에서 이번에 안 보인 기존 active row는 status='마감'으로 전환
  (삭제하지 않고 이력 보존).
- `query(sido, flbd_min, flbd_max, price_min, price_max, area_min, area_max, status='active')`
  — `SIDO_COURTS`(pipeline.py에 이미 정의)로 court 목록을 구해 `WHERE court IN (...)`, 나머지
  조건은 숫자 컬럼 range 필터. 반환 형식은 기존 CSV 컬럼명(`사건번호`,`물건소재지`,`전용면적`,
  `감정가`,`최저가`,`저감율`,`유찰횟수`,`매각기일`,`_court`)과 동일한 dict 리스트로 맞춰
  하위 단계(stage2/stage3) 코드를 무수정으로 유지한다.
- `is_empty(sido)` — 폴백 판단용, 해당 시/도 court들에 대해 캐시 row가 하나도 없는지 확인.

## 배치 갱신 (`webapp/refresh_auctions.py`)

- 서울 5개 법원 + 경기 10개 법원(`pipeline.SIDO_COURTS`) 순회.
- 각 법원에 대해 `collect_api.py --court <법원> --scl 아파트 --flbd-min 전체
  --bid-days 60` (가격·면적 필터 없음)으로 subprocess 호출 → CSV 생성.
- CSV를 파싱해 숫자형으로 변환 후 `auction_db.upsert(court, rows)` 호출.
- 법원별 처리 후 진행 로그 출력(법원명, 신규/갱신/마감 건수).
- 예외 발생 법원은 스킵하고 계속 진행 + 마지막에 실패 법원 요약 출력(전체 배치가 한 법원 실패로
  중단되지 않도록).
- Windows 작업 스케줄러 등록은 스크립트가 직접 하지 않고, 실행 커맨드와 등록 절차를 스크립트
  상단 주석/README로 안내한다 (`schtasks /create ...` 예시 포함).

## 파이프라인 연동 (`webapp/pipeline.py`)

`stage1()`을 다음과 같이 변경한다:

```python
def stage1(job, p):
    if not auction_db.is_empty(p['sido']):
        job['msg'] = '1조건 캐시 조회'
        items = auction_db.query(p['sido'], p['flbd_min'], p['flbd_max'],
                                  p['price_min'], p['price_max'],
                                  p['area_min'], p['area_max'])
        job['s1_count'] = len(items); job['s1'] = items
        return items
    # 폴백: 캐시 없음 — 기존 라이브 크롤링 경로 유지
    job['msg'] = '⚠ 캐시 없음 — 라이브 크롤링으로 폴백 (refresh_auctions.py 먼저 실행 권장)'
    ... (기존 subprocess 루프 그대로)
```

- 캐시가 있으면 즉시 반환, 없으면 기존 로직 그대로 실행 — 첫 세팅 전이나 배치 실패 시에도
  파이프라인이 깨지지 않는다.
- stage2/stage3(`webapp/pipeline.py`)는 입력 dict 형식이 동일하므로 수정 불필요.

## 에러 처리

- 배치 스크립트: 법원 1곳 실패해도 나머지 계속, 실패 목록 로그.
- 쿼리 레이어: DuckDB 파일 없거나 테이블 없으면 `is_empty()`가 True를 반환해 자동 폴백.
- 크롤링 결과가 0건인 법원(정상적으로 물건이 없을 수도 있음)과 "크롤링 자체 실패"를 구분하기
  위해, subprocess 실패(non-zero exit) 시에는 해당 법원의 기존 캐시 row를 마감 처리하지 않는다
  (실패로 인한 오탐 마감 방지).

## 테스트 / 검증 계획

- `auction_db.py` 단위: 임시 DuckDB 파일에 upsert 2회(1회차 3건, 2회차 2건+신규1건) 후
  status 전환이 기대대로 되는지 확인.
- `refresh_auctions.py`: 법원 1곳만 대상으로 실행해 CSV→DuckDB 적재 확인(실제 API 호출,
  수동 실행).
- `pipeline.py` stage1: 캐시 채운 뒤 기존 auction-screening 요청으로 전체 파이프라인 재실행,
  이전 결과(이번 대화의 평택센트럴자이1단지·호수마을이편한세상3단지)와 동일 물건이 나오는지 비교.

## 후속 작업(범위 밖, 다음 단계)

- 아파트단지 정보(세대수·준공) DuckDB 캐싱 — 다음 설계.
- 실거래 데이터 경기·서울 전체 사전 배치 채움 — 그다음 설계.
