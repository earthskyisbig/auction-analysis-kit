#!/usr/bin/env python3
"""
입지 정량지표 계산기 (카카오 로컬/모빌리티 API)

물건 주소·단지명을 좌표로 변환한 뒤, 4개 정량축을 결정론적으로 계산한다:
  교통(전철역) · 직주근접(자동차 통근) · 학군(초품아·학원·중학) · 생활인프라

공급물량(15%)·호재(10%) 2축은 API가 없어 여기서 계산하지 않는다(에이전트 조사 몫).
따라서 이 스크립트의 총점은 '코드 4축(가중치 합 75%)'을 100점 만점으로 재정규화한 값이며,
최종 6축 종합점수는 location-analyst 에이전트가 공급물량·호재를 채워 산출한다.

사용:
  python location_metrics.py --complex 양주푸르지오아파트 --address "경기도 양주시 덕계동 852" -o loc.json
  python location_metrics.py --address "경기도 양주시 덕계동 852 양주푸르지오아파트 102동 902호"

.env(상위 경로 탐색)의 KAKAO_REST_API_KEY 필요. 카카오개발자: REST키 + 카카오맵/로컬 + 카카오내비(길찾기) 활성화.
"""
import argparse, json, os, re, sys, time, urllib.parse, urllib.request

LOCAL = "https://dapi.kakao.com/v2/local/search"
NAVI = "https://apis-navi.kakaomobility.com/v1/directions"

# 주요 업무지구 (경도,위도)
JOB_CENTERS = {
    "강남역":       (127.0276, 37.4979),
    "판교역":       (127.1112, 37.3948),
    "여의도역":     (126.9245, 37.5215),
    "광화문":       (126.9769, 37.5759),
    "구로디지털단지": (126.9017, 37.4853),
}

# 6축 가중치
WEIGHTS = {"transport": 25, "job_access": 20, "school": 20,
           "supply_risk": 15, "infra": 10, "catalyst": 10}
CODE_AXES = ["transport", "job_access", "school", "infra"]  # 코드로 계산하는 축


def load_key():
    # cwd 상위로 .env 탐색
    d = os.getcwd()
    for _ in range(6):
        p = os.path.join(d, ".env")
        if os.path.isfile(p):
            for line in open(p, encoding="utf-8"):
                if line.startswith("KAKAO_REST_API_KEY="):
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
        d = os.path.dirname(d)
    k = os.environ.get("KAKAO_REST_API_KEY")
    if k:
        return k
    sys.exit("❌ KAKAO_REST_API_KEY 없음 — .env(키트 루트)에 설정하거나 export 하세요.")


def api(url, params, key):
    q = urllib.parse.urlencode(params)
    req = urllib.request.Request(url + "?" + q, headers={"Authorization": f"KakaoAK {key}"})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=12) as r:
                return json.load(r)
        except Exception as e:
            if attempt == 2:
                return {"_error": str(e)}
            time.sleep(1.5)


def geocode(address, complex_name, key):
    """단지명 키워드 검색 우선 → 지번 주소검색 폴백. (lon, lat, matched)"""
    tries = []
    if complex_name:
        # 동 이름이 있으면 함께
        m = re.search(r'([가-힣]+[동리읍면])', address or "")
        tries.append(f"{m.group(1)} {complex_name}" if m else complex_name)
        tries.append(complex_name)
    if address:
        # 동/호 제거한 지번까지
        base = re.split(r'\s+제?\d+동|\s+\d+동|\s+제?\d+층', address)[0]
        tries.append(base)
        tries.append(address)
    for q in tries:
        d = api(f"{LOCAL}/keyword.json", {"query": q}, key)
        docs = d.get("documents", [])
        if docs:
            x = docs[0]
            return float(x["x"]), float(x["y"]), x.get("place_name") or q
    # 주소검색 폴백
    if address:
        base = re.split(r'\s+제?\d+동|\s+\d+동', address)[0]
        d = api(f"{LOCAL}/address.json", {"query": base}, key)
        docs = d.get("documents", [])
        if docs:
            return float(docs[0]["x"]), float(docs[0]["y"]), docs[0].get("address_name")
    return None, None, None


def cat_search(code, lon, lat, key, radius=1000, query=None):
    url = f"{LOCAL}/keyword.json" if query else f"{LOCAL}/category.json"
    p = {"x": lon, "y": lat, "radius": radius, "sort": "distance", "size": 15}
    if query:
        p["query"] = query
    else:
        p["category_group_code"] = code
    d = api(url, p, key)
    return d.get("documents", [])


def car_minutes(lon, lat, dest, key):
    d = api(NAVI, {"origin": f"{lon},{lat}", "destination": f"{dest[0]},{dest[1]}"}, key)
    r = d.get("routes", [])
    if r and r[0].get("result_code") == 0:
        return round(r[0]["summary"]["duration"] / 60)
    return None


# ── 채점 함수 (0~100) ─────────────────────────────────────────
def score_band(v, bands):
    """bands = [(임계, 점수), ...] 오름차순 임계. v<=임계면 해당 점수."""
    for thr, sc in bands:
        if v <= thr:
            return sc
    return bands[-1][1]


def calc_transport(lon, lat, key):
    st = cat_search("SW8", lon, lat, key, radius=3000)
    if not st:
        return {"score": 8, "nearest_station": None, "distance_m": None, "stations_1km": 0}
    nearest = st[0]
    dist = int(nearest["distance"])
    sc = score_band(dist, [(300,100),(500,90),(800,78),(1200,62),(2000,45),(3000,28)])
    within1k = [s for s in st if int(s["distance"]) <= 1000]
    if len(within1k) >= 2:
        sc = min(100, sc + 5)  # 복수노선/환승 근접 가점
    return {"score": sc, "nearest_station": nearest["place_name"],
            "distance_m": dist, "stations_1km": len(within1k)}


def calc_job(lon, lat, key):
    times = {}
    for name, coord in JOB_CENTERS.items():
        t = car_minutes(lon, lat, coord, key)
        if t is not None:
            times[name] = t
        time.sleep(0.2)
    if not times:
        return {"score": None, "best_center": None, "minutes": None, "all": {}}
    best = min(times, key=times.get)
    m = times[best]
    sc = score_band(m, [(20,100),(30,88),(40,74),(50,60),(60,46),(75,32),(999,18)])
    return {"score": sc, "best_center": best, "minutes": m, "all": times}


def calc_school(lon, lat, key):
    # 초품아: 초등학교
    schools = cat_search("SC4", lon, lat, key, radius=2000)
    elem = [s for s in schools if "초등학교" in s["place_name"]]
    mid = [s for s in schools if "중학교" in s["place_name"]]
    elem_m = int(elem[0]["distance"]) if elem else None
    mid_m = int(mid[0]["distance"]) if mid else None
    # 학원 밀집 (1km)
    acad = cat_search("AC5", lon, lat, key, radius=1000)
    ac_cnt = len(acad)  # size 상한 15 → 15+ 는 "매우 많음"
    ac_more = api(f"{LOCAL}/category.json",
                  {"category_group_code":"AC5","x":lon,"y":lat,"radius":1000,"size":1}, key)
    total_ac = int(ac_more.get("meta",{}).get("total_count", ac_cnt))
    s_elem = score_band(elem_m if elem_m is not None else 9999, [(300,100),(500,85),(800,60),(1200,35),(9999,15)])
    s_acad = score_band(-total_ac, [(-50,100),(-25,85),(-12,68),(-5,50),(-1,32),(0,10)])
    s_mid = score_band(mid_m if mid_m is not None else 9999, [(500,100),(1000,75),(1500,50),(9999,25)])
    score = round(s_elem*0.5 + s_acad*0.3 + s_mid*0.2)
    return {"score": score, "elem_nearest_m": elem_m, "elem_name": elem[0]["place_name"] if elem else None,
            "academy_count_1km": total_ac, "mid_nearest_m": mid_m}


def calc_infra(lon, lat, key):
    def total(code=None, q=None):
        p = {"x":lon,"y":lat,"radius":1000,"size":1}
        if q: p["query"]=q; url=f"{LOCAL}/keyword.json"
        else: p["category_group_code"]=code; url=f"{LOCAL}/category.json"
        return int(api(url, p, key).get("meta",{}).get("total_count",0))
    mart = total("MT1"); hosp = total("HP8"); cvs = total("CS2"); park = total(q="공원")
    sc = 0
    sc += 30 if mart >= 1 else 0
    sc += score_band(-hosp, [(-10,30),(-5,22),(-1,12),(0,0)])
    sc += 20 if park >= 1 else 0
    sc += score_band(-cvs, [(-10,20),(-5,12),(-1,6),(0,0)])
    return {"score": min(100, sc), "mart_1km": mart, "hospital_1km": hosp,
            "park_1km": park, "cvs_1km": cvs}


def main():
    ap = argparse.ArgumentParser(description="입지 정량지표 계산기 (카카오)")
    ap.add_argument("--address", help="물건 주소(지번/도로명)")
    ap.add_argument("--complex", dest="complex_name", help="단지명(키워드 지오코딩 우선)")
    ap.add_argument("--lat", type=float); ap.add_argument("--lon", type=float)
    ap.add_argument("--label", default="")
    ap.add_argument("-o", "--output")
    args = ap.parse_args()
    key = load_key()

    if args.lat and args.lon:
        lon, lat, matched = args.lon, args.lat, "(좌표 직접입력)"
    else:
        lon, lat, matched = geocode(args.address or "", args.complex_name, key)
        if lon is None:
            sys.exit(f"❌ 지오코딩 실패: {args.complex_name or args.address}")

    print(f"▶ 좌표 확보: {matched}  (x={lon}, y={lat})")
    axes = {}
    print("  · 교통…");   axes["transport"] = calc_transport(lon, lat, key)
    print("  · 직주근접(자동차)…"); axes["job_access"] = calc_job(lon, lat, key)
    print("  · 학군…");   axes["school"] = calc_school(lon, lat, key)
    print("  · 인프라…"); axes["infra"] = calc_infra(lon, lat, key)
    axes["supply_risk"] = {"score": None, "note": "에이전트 조사 필요(향후 2~3년 생활권 입주물량)"}
    axes["catalyst"]    = {"score": None, "note": "에이전트 조사 필요(GTX·재개발·기업이전, 일정·출처 검증)"}

    # 코드 4축 가중 소계 (합 75%를 100점으로 재정규화)
    wsum = sum(WEIGHTS[a] for a in CODE_AXES)
    got = sum(axes[a]["score"] * WEIGHTS[a] for a in CODE_AXES if axes[a]["score"] is not None)
    code_subtotal = round(got / wsum, 1)

    result = {
        "label": args.label, "address": args.address, "complex": args.complex_name,
        "matched": matched, "coord": {"lon": lon, "lat": lat},
        "weights": WEIGHTS, "axes": axes,
        "code_subtotal_0_100": code_subtotal,
        "note": "supply_risk·catalyst 2축은 location-analyst 에이전트가 조사해 채운 뒤 6축 종합점수를 산출한다.",
    }

    print("\n── 코드 4축 결과 ──")
    t=axes["transport"]; print(f"  교통 {t['score']}: {t['nearest_station']} {t['distance_m']}m (1km내 역 {t['stations_1km']})")
    j=axes["job_access"]; print(f"  직주 {j['score']}: 최단 {j['best_center']} 자동차 {j['minutes']}분")
    s=axes["school"]; print(f"  학군 {s['score']}: 초품아 {s['elem_nearest_m']}m, 학원 {s['academy_count_1km']}개, 중학 {s['mid_nearest_m']}m")
    i=axes["infra"]; print(f"  인프라 {i['score']}: 마트 {i['mart_1km']} 병원 {i['hospital_1km']} 공원 {i['park_1km']} 편의점 {i['cvs_1km']}")
    print(f"  ▶ 코드 4축 소계: {code_subtotal}/100  (공급물량·호재는 에이전트가 추가)")

    if args.output:
        json.dump(result, open(args.output, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        print(f"✅ 저장 → {args.output}")
    else:
        print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
