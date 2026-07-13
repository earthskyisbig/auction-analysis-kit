# -*- coding: utf-8 -*-
"""국토교통부 공동주택 기본정보(V4, JSON)로 단지 프로파일 조회 -> complex_profile.json

사용:
  # 이름으로 찾기(목록 서비스 활용신청 필요)
  python fetch_complex.py --name 도곡렉슬 --district 강남구 --workdir ./out
  # kaptCode를 이미 알면 목록 서비스 없이 바로
  python fetch_complex.py --kapt-code A13586103 --workdir ./out

두 개의 data.go.kr 서비스를 쓴다(둘 다 같은 PUBLIC_DATA_SERVICE_KEY):
  · 공동주택 기본 정보제공 서비스 V4 (AptBasisInfoServiceV4) — 세대수·동수·준공 등  [필수]
  · 공동주택 단지 목록제공 서비스   (AptListService3)        — 단지명→kaptCode      [이름검색시]
활용신청·엔드포인트·필드는 references/api.md 참고. 미신청이면 403.
"""
import os, sys, argparse, warnings, json
warnings.filterwarnings('ignore')
import requests, urllib3
from dotenv import load_dotenv, find_dotenv
urllib3.disable_warnings()

INFO = 'https://apis.data.go.kr/1613000/AptBasisInfoServiceV4'
LIST = 'https://apis.data.go.kr/1613000/AptListService3'

def get_key():
    load_dotenv(find_dotenv(usecwd=True))
    for c in ('.env', os.path.join(os.getcwd(), '.env')):
        if os.path.exists(c): load_dotenv(c)
    # 키트 통합: PUBLIC_DATA_SERVICE_KEY 우선, 없으면 실거래용 PUBLIC_DATA_API_KEY 폴백
    # (data.go.kr 인증키는 계정당 1개로 활용신청된 모든 서비스에 공통 사용 가능)
    k = os.getenv('PUBLIC_DATA_SERVICE_KEY') or os.getenv('PUBLIC_DATA_API_KEY')
    if not k: sys.exit('.env 의 PUBLIC_DATA_SERVICE_KEY(또는 PUBLIC_DATA_API_KEY) 를 설정하세요.')
    return k

def call(url, params, service_hint):
    params = {**params, '_type': 'json'}
    r = requests.get(url, params=params, verify=False, timeout=20)
    if r.status_code == 403:
        sys.exit(f'403 Forbidden — "{service_hint}" 활용신청이 안 됐습니다.\n'
                 '  data.go.kr 에서 해당 서비스를 활용신청(보통 즉시 승인)한 뒤 다시 실행하세요.\n'
                 '  references/api.md 참고.')
    try:
        return r.json()
    except Exception:
        sys.exit(f'JSON 파싱 실패 (status {r.status_code}): {r.text[:200]}')

def item_of(doc):
    return ((doc.get('response') or {}).get('body') or {}).get('item') or {}

def items_of(doc):
    its = ((doc.get('response') or {}).get('body') or {}).get('items') or {}
    its = its.get('item') if isinstance(its, dict) else its
    if its is None: return []
    return its if isinstance(its, list) else [its]

def resolve_sigungu(district):
    import PublicDataReader as pdr
    df = pdr.code_bdong()
    hit = df[df['시군구명'].astype(str) == district]['시군구코드']
    if len(hit) == 0:
        hit = df[df['시군구명'].astype(str).str.contains(district, na=False)]['시군구코드']
    if len(hit) == 0: sys.exit(f'시군구 "{district}" 를 못 찾음. --sigungu-code 로 직접 지정.')
    return str(hit.iloc[0])

def _match(items, name):
    """items 리스트에서 정확일치 우선, 없으면 부분일치(fuzzy) 반환."""
    fuzzy = None
    for it in items:
        nm = str(it.get('kaptName', ''))
        if nm == name: return it['kaptCode'], nm
        if (name in nm or nm in name) and fuzzy is None: fuzzy = (it['kaptCode'], nm)
    return fuzzy

def _page_list(key, method, id_key, id_val):
    out, page = [], 1
    while page <= 30:
        doc = call(f'{LIST}/{method}',
                   {'serviceKey': key, id_key: id_val, 'pageNo': page, 'numOfRows': 500},
                   '공동주택 단지 목록제공 서비스')
        its = items_of(doc)
        if not its: break
        out.extend(its)
        if len(its) < 500: break
        page += 1
    return out

def find_kapt(key, sgg, name):
    # 1차: 시군구 목록
    items = _page_list(key, 'getSigunguAptList3', 'sigunguCode', sgg)
    hit = _match(items, name)
    if hit: return hit
    # 2차: 시군구 목록이 비었거나(일부 시군구는 total=0으로 데이터 공백) 이름 불일치 →
    #       시도 전체 목록에서 bjdCode 앞 5자리(=시군구)로 걸러 재시도. (화성시 등 시군구쿼리 공백 우회)
    sido_items = _page_list(key, 'getSidoAptList3', 'sidoCode', str(sgg)[:2])
    scoped = [it for it in sido_items if str(it.get('bjdCode', ''))[:5] == str(sgg)]
    hit = _match(scoped, name)
    if hit: return hit
    # 3차: 그래도 없으면 데이터 공백(예: 화성시 일부) → kaptCode 직접 지정 안내
    sys.exit(f'"{name}" 을(를) 목록에서 못 찾음(시군구쿼리 {len(items)}건·시도쿼리 {len(scoped)}건). '
             f'\n  일부 시군구(예: 화성시)는 공동주택 목록 API에 데이터가 누락돼 이름검색이 불가능합니다.'
             f'\n  → k-apt.go.kr 에서 kaptCode 를 확인해 --kapt-code 로 직접 지정하세요.')

def g(d, k):
    v = d.get(k); return None if v in (None, '', ' ', 'null') else v

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--name'); ap.add_argument('--district', default='')
    ap.add_argument('--sigungu-code', default=''); ap.add_argument('--kapt-code', default='')
    ap.add_argument('--workdir', default='.')
    a = ap.parse_args()
    key = get_key()

    if a.kapt_code:
        kapt_code, kapt_name = a.kapt_code, a.name or ''
    else:
        if not a.name: sys.exit('--name 또는 --kapt-code 중 하나는 필요합니다.')
        sgg = a.sigungu_code or resolve_sigungu(a.district)
        kapt_code, kapt_name = find_kapt(key, sgg, a.name)
    print(f'조회: {kapt_name or kapt_code} (kaptCode={kapt_code})', flush=True)

    base = item_of(call(f'{INFO}/getAphusBassInfoV4', {'serviceKey': key, 'kaptCode': kapt_code},
                        '공동주택 기본 정보제공 서비스'))
    if not g(base, 'kaptCode'):
        sys.exit(f'kaptCode {kapt_code} 로 기본정보가 비어 옵니다. 코드가 맞는지 확인하세요.')
    dtl = item_of(call(f'{INFO}/getAphusDtlInfoV4', {'serviceKey': key, 'kaptCode': kapt_code},
                       '공동주택 기본 정보제공 서비스'))
    ud = g(base, 'kaptUsedate')
    profile = {
        'kaptCode': kapt_code, 'name': g(base, 'kaptName'),
        'addr': g(base, 'doroJuso') or g(base, 'kaptAddr'),
        'households': g(base, 'kaptdaCnt'), 'dong_cnt': g(base, 'kaptDongCnt'),
        'used_date': ud, 'built_year': (ud[:4] if ud else None),
        'top_floor': g(base, 'kaptTopFloor'), 'ho_cnt': g(base, 'hoCnt'),
        'floor_area': g(base, 'kaptTarea'), 'sale_type': g(base, 'codeSaleNm'),
        'heat': g(base, 'codeHeatNm'), 'corridor': g(base, 'codeHallNm'),
        'manage': g(base, 'codeMgrNm'), 'builder': g(base, 'kaptBcompany'),
        'developer': g(base, 'kaptAcompany'),
        # 전용면적 구간별 세대수(단지 면적 구성)
        'ho60': g(base, 'kaptMparea60'), 'ho85': g(base, 'kaptMparea85'),
        'ho135': g(base, 'kaptMparea135'), 'ho136': g(base, 'kaptMparea136'),
        'park_ground': g(dtl, 'kaptdPcnt'), 'park_under': g(dtl, 'kaptdPcntu'),
        'elevator': g(dtl, 'kaptdEcnt'), 'cctv': g(dtl, 'kaptdCccnt'),
        'ev_charger': g(dtl, 'groundElChargerCnt'),
        'subway_station': g(dtl, 'subwayStation'), 'subway_time': g(dtl, 'kaptdWtimesub'),
        'welfare': g(dtl, 'welfareFacility'), 'edu': g(dtl, 'educationFacility'),
    }
    os.makedirs(a.workdir, exist_ok=True)
    json.dump(profile, open(os.path.join(a.workdir, 'complex_profile.json'), 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)
    print(f"세대수 {profile['households']} · {profile['dong_cnt']}개동 · {profile['built_year']}년 준공 "
          f"· 최고 {profile['top_floor']}층 · 난방 {profile['heat']} · 복도 {profile['corridor']}")
    print('complex_profile.json 저장')

if __name__ == '__main__':
    main()
