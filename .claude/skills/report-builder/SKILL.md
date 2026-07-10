---
name: report-builder
description: 경매 물건 분석 결과를 종합 HTML 보고서로 만들고 GitHub Pages로 배포한다. 사용자가 "보고서 만들어", "리포트로 정리", "HTML로 뽑아줘", "배포해줘", "비교표로" 등을 요청하면 이 스킬을 읽어라. court-search·rights-analysis·profit-analysis 결과를 하나로 묶는 4단계(마지막).
---

# ④ 종합 보고서 + 배포 (report-builder)

①~③ 결과를 **표준 디자인 HTML 보고서**로 합치고 공개 사이트로 배포하는 마지막 단계.

## 디자인 표준 (반드시 준수)
`templates/report-template.html` 의 CSS/구조를 그대로 사용한다. 예시는 `examples/`.
- 다크 네비(`--nav-bg:#1e293b`), 화이트 콘텐츠, 섹션별 색상 코딩
- 구성요소: 결과 배너 · 요약 카드 · 섹션 헤더 · info-table · data-table · 타임라인 · 콜아웃 · Council 카드 · 비교표
- CSS 변수: `--green:#16a34a --accent:#3b82f6 --red:#dc2626 --yellow:#d97706 --purple:#7c3aed`

## 보고서 필수 구성 (순서)
1. **고객 요구조건** — 주택수·취득구조(개인/매매사업자/법인)·투자목적·가용자금·투자지역·물건유형
2. **핵심 지표 배너** — 감정가·최저가·추정시세·인수위험
3. **물건 개요** + 매각 기일 타임라인
4. **권리분석** (②결과) — 말소기준·임차인·인수·확인사항 콜아웃
5. **입지분석** (③결과) — 6축 점수 레이더 + 등급 배지 + 축별 근거(교통·직주·학군·공급·인프라·호재)
6. **실거래 시세** (④결과) — 동일단지/유사물건 비교표 + 보수/중립/낙관
7. **수익 분석** (④결과) — 낙찰가 시나리오별 8대 비용 손익표 + 권장 낙찰상한
8. **종합 판단** — 권리/입지/수익/리스크 Council 카드 → GO/조건부/보류
9. **입찰 전 체크리스트** — 등기부·전입세대열람·관리비·현장·수리
10. **부록** — 사용 리소스 + 분석 메트릭(소요시간·추정 토큰·추정비용 입력$3/출력$15 per 1M, 환율 1,400원) + 면책

> 여러 물건 비교는 `examples/example-report-compare.html` 구조(우선순위 배너 + 비교표 + 물건카드) 사용.
> **입지 레이더**는 외부 라이브러리 없이 순수 인라인 SVG로 그린다(6각형 축 라벨: 교통·직주·학군·공급·인프라·호재, 값 0~100). location-analyst의 6축 점수를 꼭짓점으로.

## 파일 위치 & 이름
- 상세: `report-<사건번호>-<지역>.html` (예: report-2025ta580-siheung.html)
- 비교: `report-compare-<n>.html`

## 배포 (GitHub Pages)
보고서는 **공개 저장소 `auction-reports`** 에만 올린다(개인 저장소와 분리).
```bash
cp report-*.html /path/to/auction-reports/
cd /path/to/auction-reports && git add report-*.html && git commit -m "add report" && git push
# index.html(랜딩)에 새 보고서 링크 카드 추가하는 것 잊지 말 것
```
- 사이트: `https://<사용자명>.github.io/auction-reports/`
- Pages가 이미 켜져 있으면 push만 하면 자동 반영.
- ⚠️ 보고서에 API 키·개인정보가 없는지 배포 전 확인. 공개 데이터 분석만 담을 것.

## 면책 (모든 보고서 하단 필수)
"시세·수익률·낙찰가는 추정입니다. 입찰 전 등기사항증명서·전입세대열람·현장확인·세무상담으로 검증하세요."
