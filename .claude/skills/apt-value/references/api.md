# 공동주택 기본정보 API — 활용신청 · 엔드포인트 · 필드

세대수·동수·준공일·주차·난방 등 '단지 프로파일'은 국토교통부 공동주택 정보 API에서 온다.
실거래가 API와 **별개로 활용신청**이 필요하다(같은 서비스키를 쓰지만 서비스별로 승인이 걸림).
포맷은 **JSON**(`_type=json`), 엔드포인트는 **V4**를 쓴다.

## 활용신청 (사용자가 1회, 둘 다 자동승인)

data.go.kr 로그인 후 아래 두 개를 각각 활용신청:

1. **공동주택 기본 정보제공 서비스** — 세대수·동수 등  [필수]
   → https://www.data.go.kr/data/15058453/openapi.do  (AptBasisInfoServiceV4)
2. **공동주택 단지 목록제공 서비스** — 단지명→kaptCode 조회용  [이름 검색 시 필수]
   → https://www.data.go.kr/data/15057332/openapi.do  (AptListService3)

승인 후 몇 분~1시간이면 반영된다. 반영 전에는 `403 Forbidden`.
kaptCode를 이미 알면(예: k-apt.go.kr에서 확인) 2번 없이 `--kapt-code`로 바로 조회 가능.
`.env`의 `PUBLIC_DATA_SERVICE_KEY`(Decoding 키)를 그대로 사용.

## 흐름 (fetch_complex.py가 자동 수행)

1. `AptListService3/getSigunguAptList3(sigunguCode, pageNo, numOfRows)` — 시군구 공동주택 목록.
   `kaptName`을 단지명과 매칭해 `kaptCode` 획득(정확 일치 우선). ← `--kapt-code` 주면 생략.
2. `AptBasisInfoServiceV4/getAphusBassInfoV4(kaptCode)` — 기본정보.
3. `AptBasisInfoServiceV4/getAphusDtlInfoV4(kaptCode)` — 상세(주차·교통·부대시설).

베이스 URL: `https://apis.data.go.kr/1613000/AptListService3` ,
`https://apis.data.go.kr/1613000/AptBasisInfoServiceV4` . 응답은 JSON.

## 주요 필드 (getAphusBassInfoV4)

| 키 | 뜻 |
|---|---|
| `kaptdaCnt` | 세대수 |
| `kaptDongCnt` | 동수 |
| `kaptUsedate` | 사용승인일(YYYYMMDD) = 준공 |
| `hoCnt` | 호수 |
| `codeHeatNm` | 난방방식(지역/개별/중앙) |
| `codeHallNm` | 복도유형(계단식/복도식/혼합) |
| `codeMgrNm` | 관리방식 |
| `kaptBcompany` / `kaptAcompany` | 시공사 / 시행사 |
| `kaptTarea` | 연면적 |
| `kaptTopFloor` | 최고층 |
| `kaptMparea60/85/135/136` | 전용 60·85·135·136㎡ 구간 세대수(면적 구성) |

## 주요 필드 (getAphusDtlInfoV4)

| 키 | 뜻 |
|---|---|
| `kaptdPcnt` / `kaptdPcntu` | 지상 / 지하 주차대수 |
| `kaptdCccnt` | CCTV 대수 |
| `subwayStation` / `kaptdWtimesub` | 인근 지하철역 / 도보(분) |
| `welfareFacility` / `educationFacility` | 복리·교육 시설 |
| `groundElChargerCnt` | 전기차 충전기 |

## 한계

- **향(방향)은 어떤 API에도 없다.** 실거래가엔 층·동명만, 공동주택 정보는 단지 단위라 세대별 향이 없다.
  향 프리미엄이 꼭 필요하면 사용자가 동→향 매핑을 제공해야 한다(이 스킬 기본은 향 제외).
- 실거래 `아파트동명`은 약 2/3만 채워져 있어, 동별 분석은 동명이 있는 거래만 대상이다.
- kaptCode 매칭이 애매하면(재건축 전후 동일명 등) 여러 후보가 나올 수 있으니 주소로 확인한다.

## 🔴 목록 API 데이터 공백 함정 (실측)

- **일부 시군구는 `getSigunguAptList3` 가 `resultCode=00`인데 `totalCount=0`** 을 준다(오류 아님, 데이터 공백).
  **실측: 화성시(41590) → 0건.** `_type=json` 정상, 키도 정상인데 목록이 비어 이름검색이 안 된다.
- `fetch_complex.py`는 이때 **시도 전체 목록(`getSidoAptList3`, sidoCode=41)** 을 받아 `bjdCode` 앞 5자리로
  시군구를 재필터해 우회한다. 그래도 없으면(화성처럼 시도목록에도 누락) **kaptCode 직접 지정**만이 답이다.
- **대량 배치**로 여러 단지를 조회할 땐, 단지마다 `getSigunguAptList3` 를 때리지 말고
  **시도목록을 1회 받아 캐시**한 뒤 로컬 매칭하라(쓰로틀 회피 + 시군구 공백 우회). 매칭은 kaptName 정규화
  (공백·'아파트'·괄호 제거) 후 물건소재지에 substring 포함 여부 + as3(읍면동) 가산으로 한다.
- 미매칭 단지는 **소규모/나홀로이거나 등록명 불일치**일 뿐 "500세대 미만"으로 단정하지 말 것 —
  꼭 필요하면 k-apt.go.kr 로 수동 확인.
