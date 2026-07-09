#!/usr/bin/env python3
"""
법원경매 물건 수집기 v3 — API 직접 페이징 방식 (courtauction.go.kr)

기존 scrape_auction_filtered.py 의 UI 페이지버튼 클릭 방식은 WebSquare 파이프라인 지연으로
'다음 그룹' 이동이 씹혀 같은 페이지를 반복 수집 → 328건 중 113건만 수집되는 버그가 있었다.

이 버전은:
  1) 검색 폼을 UI로 세팅(용도코드 등 자동생성) 후 검색 1회 실행 → 세션 확보 + 요청 본문 캡처
  2) 캡처한 본문의 dma_pageInfo.pageNo 를 1..N 으로 올리며 in-page fetch(credentials:'include')로
     searchControllerMain.on 을 직접 호출 → totalCnt 만큼 전량 수집 (결정론적)
  3) 사건번호 dedup → 시군구/최저가 사후 필터 → CSV

검증: 수집 고유건수 == totalCnt 를 최종 assert. 미달 시 명시적 경고 + WARNING 파일.
"""
import argparse, csv, json, math, os, re, time
from playwright.sync_api import sync_playwright

TARGET_URL = "https://www.courtauction.go.kr/pgj/index.on?w2xPath=/pgj/ui/pgj100/PGJ151F00.xml"
API_URL = "https://www.courtauction.go.kr/pgj/pgjsearch/searchControllerMain.on"
COLUMNS = ['사건번호', '물건소재지', '전용면적', '감정가', '최저가', '저감율', '유찰횟수', '매각기일']
AREA_RE = re.compile(r'([\d,]+(?:\.\d+)?)\s*㎡')
PAGE_SIZE = 40  # CLAUDE.md: pageSize ≤ 40 (초과 시 서버 500)

STEALTH_ARGS = ['--no-sandbox', '--disable-blink-features=AutomationControlled',
                '--disable-features=site-per-process', '--lang=ko-KR']
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

FETCH_JS = """
async ([url, bodyObj]) => {
  const res = await fetch(url, {method:'POST', credentials:'include',
    headers:{'Content-Type':'application/json;charset=UTF-8','Accept':'application/json'},
    body: JSON.stringify(bodyObj)});
  const txt = await res.text();
  let j = null; try { j = JSON.parse(txt); } catch(e) {}
  return {status: res.status, json: j, text: j ? null : txt.slice(0, 300)};
}
"""


def parse_args():
    ap = argparse.ArgumentParser(description='법원경매 수집기 v3 (API 페이징)')
    ap.add_argument('--court', required=True, help='법원명 (드롭다운 표기)')
    ap.add_argument('--sido', default=None, help='시/도 (예: 서울특별시)')
    ap.add_argument('--sgg', default=None, help='시/군/구 사후필터 (예: 금천구)')
    ap.add_argument('--emd', default=None, help='읍/면/동 사후필터 (예: 시흥동)')
    ap.add_argument('--lcl', default='건물')
    ap.add_argument('--mcl', default='주거용건물')
    ap.add_argument('--scl', default='다세대주택', help='"전체"면 소분류 생략')
    ap.add_argument('--flbd-min', default='1회', dest='flbd_min', help='"전체"면 조건 없음')
    ap.add_argument('--flbd-max', type=int, default=None, dest='flbd_max', help='유찰횟수 상한(회)')
    ap.add_argument('--max-price', type=int, default=None, help='최저가 상한(원) — API 서버필터')
    ap.add_argument('--min-price', type=int, default=None, help='최저가 하한(원) — API 서버필터')
    ap.add_argument('--area-min', type=float, default=None, dest='area_min', help='전용면적 하한(㎡) — API 서버필터')
    ap.add_argument('--area-max', type=float, default=None, dest='area_max', help='전용면적 상한(㎡) — API 서버필터')
    ap.add_argument('--bid-days', type=int, default=None, help='입찰종료일을 오늘+N일로 확장(기본: 사이트 기본 2주)')
    ap.add_argument('-o', '--output', default=None)
    return ap.parse_args()


def set_select(page, el_id, value):
    return page.evaluate(f"""() => {{const s=document.getElementById('{el_id}'); if(!s)return false;
        const o=Array.from(s.options).find(o=>o.value==='{value}'||o.text==='{value}'||o.text.includes('{value}'));
        if(!o)return false; s.value=o.value; s.dispatchEvent(new Event('change',{{bubbles:true}})); return true;}}""")


def fmt_money(v):
    try: return f"{int(v):,}원"
    except Exception: return str(v)


def build_case_no(item):
    p = item.get('printCsNo', '')
    if p: return ' '.join(p.replace('<br/>', ' ').split())
    court = item.get('jiwonNm', '').strip(); case = item.get('srnSaNo', '').strip()
    return f"{court} {case}".strip() if court else case or str(item.get('saNo', ''))


def low_price(item):
    v = item.get('notifyMinmaePrice1') or item.get('minmaePrice') or 0
    try: return int(v)
    except (TypeError, ValueError): return 0


def parse_area(item):
    src = ' '.join(str(item.get(k, '') or '') for k in ('convAddr', 'areaList', 'pjbBuldList'))
    vals = [float(m.replace(',', '')) for m in AREA_RE.findall(src)]
    return max(vals) if vals else None


def fmt_giil(v):
    s = str(v or ''); return f"{s[:4]}.{s[4:6]}.{s[6:]}" if len(s) == 8 else s


def convert_item(item):
    rate = item.get('notifyMinmaePriceRate1', ''); area = parse_area(item)
    return {
        '사건번호': build_case_no(item),
        '물건소재지': (item.get('printSt', '') or '').strip(),
        '전용면적': f"{area:g}㎡" if area else '',
        '감정가': fmt_money(item.get('gamevalAmt', '')),
        '최저가': fmt_money(low_price(item)),
        '저감율': f"{rate}%" if rate not in (None, '') else '',
        '유찰횟수': str(item.get('yuchalCnt', '')),
        '매각기일': fmt_giil(item.get('maeGiil', '')),
    }


def main():
    args = parse_args()
    captured = {}

    def on_request(req):
        if 'searchControllerMain' in req.url and req.post_data:
            captured['body'] = req.post_data

    all_items = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=STEALTH_ARGS)
        context = browser.new_context(user_agent=UA, locale="ko-KR", viewport={"width":1280,"height":900})
        context.add_init_script("Object.defineProperty(navigator,'webdriver',{get:()=>undefined});"
                                "Object.defineProperty(navigator,'plugins',{get:()=>[1,2,3,4,5]});"
                                "window.chrome={runtime:{}};")
        page = context.new_page()
        page.on("request", on_request)

        # 1) 폼 세팅 + 검색 1회 (세션 확보 + 요청본문 캡처)
        page.goto(TARGET_URL, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_function("() => !!document.getElementById('mf_wfm_mainFrame_btn_gdsDtlSrch')", timeout=60000)
        time.sleep(2)
        print(f"▶ 폼 세팅: {args.court} / {args.lcl}>{args.mcl}>{args.scl} / 유찰 {args.flbd_min}")
        set_select(page, 'mf_wfm_mainFrame_sbx_rletCortOfc', args.court)
        if args.flbd_min != '전체':
            set_select(page, 'mf_wfm_mainFrame_sbx_rletFlbdCntMin', args.flbd_min)
        time.sleep(1)
        set_select(page, 'mf_wfm_mainFrame_sbx_rletLclLst', args.lcl); time.sleep(3)
        set_select(page, 'mf_wfm_mainFrame_sbx_rletMclLst', args.mcl); time.sleep(3)
        if args.scl != '전체':
            set_select(page, 'mf_wfm_mainFrame_sbx_rletSclLst', args.scl)
        time.sleep(1)
        page.evaluate("() => { document.getElementById('mf_wfm_mainFrame_btn_gdsDtlSrch').click(); }")
        time.sleep(6)

        if 'body' not in captured:
            print("❌ 검색 요청 본문 캡처 실패 — 중단"); browser.close(); return
        base_body = json.loads(captured['body'])

        # 입찰기간 확장 옵션
        if args.bid_days is not None:
            import datetime
            today = datetime.date.today()
            end = today + datetime.timedelta(days=args.bid_days)
            base_body['dma_srchGdsDtlSrchInfo']['bidBgngYmd'] = today.strftime('%Y%m%d')
            base_body['dma_srchGdsDtlSrchInfo']['bidEndYmd'] = end.strftime('%Y%m%d')
            print(f"▶ 입찰기간 확장: {today:%Y%m%d} ~ {end:%Y%m%d}")

        srch = base_body['dma_srchGdsDtlSrchInfo']
        # 서버사이드 범위 필터 주입 (유찰상한·최저가범위·면적범위)
        if args.flbd_max is not None:  srch['flbdNcntMax'] = str(args.flbd_max)
        if args.min_price is not None: srch['lwsDspslPrcMin'] = str(args.min_price)
        if args.max_price is not None: srch['lwsDspslPrcMax'] = str(args.max_price)
        if args.area_min is not None:  srch['objctArDtsMin'] = str(args.area_min)
        if args.area_max is not None:  srch['objctArDtsMax'] = str(args.area_max)
        print(f"  필터코드: cortOfcCd={srch.get('cortOfcCd')} scl={srch.get('sclDspslGdsLstUsgCd')} "
              f"flbd={srch.get('flbdNcntMin')}~{srch.get('flbdNcntMax') or '∞'} "
              f"가격={srch.get('lwsDspslPrcMin') or '0'}~{srch.get('lwsDspslPrcMax') or '∞'} "
              f"면적={srch.get('objctArDtsMin') or '0'}~{srch.get('objctArDtsMax') or '∞'} "
              f"bid={srch.get('bidBgngYmd')}~{srch.get('bidEndYmd')}")

        # 2) API 직접 페이징 (pageNo 1..N, pageSize=40)
        def fetch_page(page_no):
            body = json.loads(json.dumps(base_body))  # deep copy
            body['dma_pageInfo'] = {"pageNo": page_no, "pageSize": PAGE_SIZE, "bfPageNo": "",
                                    "startRowNo": "", "totalCnt": "", "totalYn": "Y", "groupTotalCount": ""}
            for attempt in range(1, 4):
                res = page.evaluate(FETCH_JS, [API_URL, body])
                if res.get('json'):
                    return res['json']
                print(f"    [재시도 {attempt}/3] pageNo={page_no} status={res.get('status')} text={res.get('text')}")
                time.sleep(2)
            return None

        first = fetch_page(1)
        if not first:
            print("❌ 1페이지 조회 실패 — 중단"); browser.close(); return
        data = first.get('data', {})
        total = int(data.get('dma_pageInfo', {}).get('totalCnt') or 0)
        items = data.get('dlt_srchResult', [])
        all_items.extend(items)
        pages = max(1, math.ceil(total / PAGE_SIZE))
        print(f"▶ 사이트 총건수(totalCnt): {total} → {pages}페이지 (pageSize={PAGE_SIZE})")
        print(f"  [p1] +{len(items)} 누적 {len(all_items)}")

        for pno in range(2, pages + 1):
            j = fetch_page(pno)
            if not j:
                print(f"  [p{pno}] 조회 실패 — 스킵"); continue
            its = j.get('data', {}).get('dlt_srchResult', [])
            all_items.extend(its)
            print(f"  [p{pno}] +{len(its)} 누적 {len(all_items)}")
            time.sleep(0.3)

        browser.close()

    # dedup — 사건번호+소재지 복합키 (한 사건에 여러 물건번호가 있을 수 있어 사건번호 단독 키는 물건 손실)
    seen, deduped = set(), []
    for it in all_items:
        k = (build_case_no(it), (it.get('printSt', '') or '').strip())
        if k[0] and k in seen: continue
        seen.add(k); deduped.append(it)
    all_items = deduped
    unique = len(all_items)

    print(f"\n▶ 수집 고유건수: {unique} / 사이트 총건수: {total}")
    ok = unique >= total
    if ok:
        print(f"✅ 정합성 검증 통과 ({unique}/{total})")
    else:
        print(f"❌ 정합성 검증 실패 — {total - unique}건 누락 (수집 {unique}/{total})")

    # 사후 필터
    filtered = all_items
    if args.sgg:
        b = len(filtered); filtered = [i for i in filtered if args.sgg in i.get('hjguSigu', '')]
        print(f"  시/군/구 필터: {b} → {len(filtered)} ({args.sgg})")
    if args.emd:
        b = len(filtered); filtered = [i for i in filtered
                                       if args.emd in (i.get('hjguDong','') + i.get('printSt',''))]
        print(f"  읍/면/동 필터: {b} → {len(filtered)} ({args.emd})")
    if args.max_price:
        b = len(filtered); filtered = [i for i in filtered if low_price(i) <= args.max_price]
        print(f"  최저가 필터: {b} → {len(filtered)} (≤ {args.max_price:,})")

    output = args.output or f"auction_{args.court.replace('지방법원','')}_{args.sgg or ''}_{args.scl}.csv"
    rows = [convert_item(it) for it in filtered]
    with open(output, 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS); w.writeheader(); w.writerows(rows)
    print(f"✅ {len(rows)}행 → {output}")

    if not ok:
        wp = output.rsplit('.', 1)[0] + '.WARNING.txt'
        with open(wp, 'w', encoding='utf-8') as f:
            f.write(f"정합성 검증 실패: 수집 {unique}/{total}건 (누락 {total-unique})\n")
        print(f"⚠️  경고 파일: {wp}")

    print("\n[미리보기]")
    for i, r in enumerate(rows[:20], 1):
        print(f"  [{i:02d}] {r['사건번호']} | {r['물건소재지']}")
        print(f"       감정 {r['감정가']} / 최저 {r['최저가']}({r['저감율']}) / 유찰 {r['유찰횟수']} / 매각 {r['매각기일']}")


if __name__ == '__main__':
    main()
