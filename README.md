# 🏛️ 경매 분석 키트 (auction-analysis-kit)

법원경매 **크롤링 → 권리분석 → 수익성분석 → 종합보고서**까지, Claude Code로 한 번에 돌리는 학습용 키트.
이 저장소 하나만 clone하면 전체 파이프라인이 준비됩니다.

> ⚠️ 본 키트의 분석·수익률은 **추정**입니다. 실제 입찰 전 등기사항증명서·전입세대열람·현장확인·세무상담으로 검증하세요.

---

## 5분 퀵스타트

### 0) 준비물
- [Claude Code](https://claude.com/claude-code) 설치
- Python 3.10+
- 국토부 실거래가 API 키 ([data.go.kr](https://www.data.go.kr) "아파트 매매 실거래가" 활용신청 → **디코딩키**) — 시세 조회용(선택)

### 1) 설치
```bash
git clone https://github.com/<사용자명>/auction-analysis-kit
cd auction-analysis-kit
pip install playwright duckdb && python -m playwright install chromium
cp .env.example .env   # .env에 PUBLIC_DATA_API_KEY 입력 (시세 조회용)
```

### 2) Claude Code 실행 후 한 줄
```
/경매분석 수원 권선구 아파트 3억~10억 유찰1~3회 59~85㎡
```
→ 크롤링 → 후보 목록 → 물건 선택 → 권리·수익 분석 → HTML 보고서까지 자동.

### 개별 단계로 쓰고 싶으면
```bash
# ① 크롤링
python .claude/skills/court-search/scripts/collect_api.py \
  --court 수원지방법원 --sgg 권선구 --scl 아파트 \
  --flbd-min 1회 --flbd-max 3 --min-price 300000000 --max-price 1000000000 \
  --area-min 59 --area-max 85 --bid-days 180 -o out.csv

# ② 권리분석
python scripts/analyze_case.py --court 수원지방법원 --case 2025타경55979 -o case.json
```
그 다음 Claude Code에서 "이 물건 수익률 분석해줘", "보고서 만들어줘" 라고 하면 ③④ 진행.

---

## 구조

```
auction-analysis-kit/
├── README.md                     ← 지금 이 문서
├── .env.example                  ← 실거래가 API 키
├── .claude/
│   ├── commands/경매분석.md       ← 원샷 오케스트레이터 (/경매분석)
│   └── skills/
│       ├── court-search/         ① 법원경매 크롤링 (collect_api.py)
│       ├── rights-analysis/      ② 권리분석 (말소기준·대항력·인수)
│       ├── profit-analysis/      ③ 수익성 (실거래+8대비용)
│       └── report-builder/       ④ 종합보고서 HTML + 배포
├── scripts/analyze_case.py       공용: 단일사건 상세수집
├── knowledge/                    세금·권리 지식베이스
├── templates/report-template.html 보고서 디자인 뼈대
└── examples/                     완성 보고서 예시 2건
```

## 4단계 파이프라인

| 단계 | 스킬 | 하는 일 | 핵심 도구 |
|------|------|---------|-----------|
| ① 크롤링 | court-search | 조건별 물건 목록 전량 수집(CSV) | collect_api.py (API 페이징·정합성검증) |
| ② 권리분석 | rights-analysis | 명세서·현황·감정 수집→말소기준·인수 판정 | analyze_case.py |
| ③ 수익성 | profit-analysis | 실거래 시세 + 8대 비용 손익 | real-estate MCP + 8대비용 규칙 |
| ④ 보고서 | report-builder | 표준 HTML 보고서 + GitHub Pages 배포 | templates/ + examples/ |

## 왜 collect_api.py 인가 (중요)
법원경매 사이트는 **UI 페이지버튼 클릭으로는 물건이 대량 누락**된다(WebSquare 지연). 이 키트는 검색 API를 `pageNo`로 직접 페이징하고 **수집 건수==사이트 총건수**를 검증한다. (실측: UI방식 328건 중 113건만 → API방식 328/328)

## 라이선스 / 책임
학습·연구용. 투자 판단과 그 결과의 책임은 이용자 본인에게 있습니다.
