# -*- coding: utf-8 -*-
"""웹앱 파이프라인: 1조건(크롤링)→2조건(세대수·연식·실거래)→3조건(상위N 권리)→보고서.
기존 스킬 스크립트를 subprocess로 재사용하고, 공동주택 목록/실거래는 로컬에서 매칭·캐시."""
import os, re, sys, csv, json, subprocess, statistics as st, warnings
warnings.filterwarnings('ignore')
import requests, urllib3
from dotenv import load_dotenv
urllib3.disable_warnings()
import realprice_db as rp

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORK = os.path.join(ROOT, 'webapp', '_work')
os.makedirs(WORK, exist_ok=True)
load_dotenv(os.path.join(ROOT, '.env'))
KEY = os.getenv('PUBLIC_DATA_API_KEY') or os.getenv('PUBLIC_DATA_SERVICE_KEY')
PY = sys.executable

COLLECT = os.path.join(ROOT, '.claude/skills/court-search/scripts/collect_api.py')
ANALYZE = os.path.join(ROOT, 'scripts/analyze_case.py')
LOCMET  = os.path.join(ROOT, '.claude/skills/location-metrics/scripts/location_metrics.py')
INFO = 'https://apis.data.go.kr/1613000/AptBasisInfoServiceV4'
LIST = 'https://apis.data.go.kr/1613000/AptListService3'

SIDO_COURTS = {
    '서울': ['서울중앙지방법원','서울동부지방법원','서울남부지방법원','서울북부지방법원','서울서부지방법원'],
    '경기': ['수원지방법원','성남지원','여주지원','평택지원','안산지원','안양지원',
             '의정부지방법원','고양지원','남양주지원','부천지원'],
}
SIDO_CODE = {'서울': '11', '경기': '41'}

def _norm(s): return re.sub(r'[^0-9가-힣]', '', str(s or ''))
def _won(s):
    try: return int(re.sub(r'[^0-9]', '', str(s)))
    except: return 0
def _rate(s):
    m = re.search(r'(\d+)', str(s or '')); return int(m.group(1)) if m else 100
def _sgg(addr):
    """시군구 추출 — 서울/광역시는 '구', 도는 '시/군(+구)'. as2·실거래코드 공용."""
    m = re.search(r'(?:특별시|광역시)\s*(\S+구)', addr)
    if m: return m.group(1)
    m = re.search(r'도\s+(\S+?[시군])(?:\s+(\S+구))?', addr)
    if m: return f"{m.group(1)} {m.group(2)}" if m.group(2) else m.group(1)
    return None

# ── 공동주택 시도목록 캐시(세대수·연식 매칭용) ──
_aptlist = {}
def apt_index(sido_code):
    if sido_code in _aptlist: return _aptlist[sido_code]
    out, page = [], 1
    while page <= 40:
        try:
            r = requests.get(f'{LIST}/getSidoAptList3',
                params={'serviceKey': KEY, 'sidoCode': sido_code, 'pageNo': page,
                        'numOfRows': 500, '_type': 'json'}, verify=False, timeout=30)
            its = (((r.json().get('response') or {}).get('body') or {}).get('items')) or []
        except Exception:
            its = []
        if isinstance(its, dict): its = its.get('item', [])
        if not its: break
        out.extend(its)
        if len(its) < 500: break
        page += 1
    _aptlist[sido_code] = out
    return out

_basis = {}
def basis(kapt):
    if kapt in _basis: return _basis[kapt]
    try:
        r = requests.get(f'{INFO}/getAphusBassInfoV4',
            params={'serviceKey': KEY, 'kaptCode': kapt, '_type': 'json'}, verify=False, timeout=30)
        item = (((r.json().get('response') or {}).get('body') or {}).get('item')) or {}
    except Exception:
        item = {}
    _basis[kapt] = item
    return item

def cand_name(addr):
    """소재지에서 단지명 후보 추출: 괄호 안(동명,단지명) 우선 → 지번/도로명 뒤 한글덩어리."""
    m = re.search(r'\(([^)]*)\)', addr)
    if m:
        return m.group(1).split(',')[-1].strip()
    m = re.search(r'\d+(?:-\d+)?\s+([가-힣0-9]+(?:\s?[가-힣0-9]+)*?)\s*제?\d*동', addr)
    return m.group(1) if m else ''

def match_kapt(addr, index):
    na = _norm(addr); na2 = na.replace('아파트', '')
    sgg = _sgg(addr) or ''; base = sgg.split()[0] if sgg else ''
    cand = _norm(cand_name(addr)).replace('아파트', '')
    best = None
    for it in index:
        as2 = it.get('as2') or ''
        if base and base not in as2: continue
        kn = _norm(it.get('kaptName')); kn2 = kn.replace('아파트', '')
        if len(kn2) < 3: continue
        ok, score = False, 0
        if kn in na or kn2 in na2:                       # 등록명 ⊂ 소재지 (강매칭)
            ok, score = True, len(kn2) + 50
        elif cand and len(cand) >= 4:                    # 소재지 단지명 ↔ 등록명 (양방향·접두)
            cp = len(os.path.commonprefix([cand, kn2]))
            if cand in kn2 or kn2 in cand or cp >= 4:
                ok, score = True, cp
        if ok:
            if it.get('as3') and it['as3'] in addr: score += 100
            if best is None or score > best[0]: best = (score, it)
    return best[1] if best else None

# ── 1조건: 크롤링 ──
def stage1(job, p):
    courts = SIDO_COURTS.get(p['sido'], [p['sido']])
    items, seen = [], set()
    for i, court in enumerate(courts):
        job['msg'] = f"1조건 크롤링 {i+1}/{len(courts)} — {court}"
        out = os.path.join(WORK, f"{job['id']}_c{i}.csv")
        cmd = [PY, COLLECT, '--court', court, '--scl', '아파트',
               '--flbd-min', f"{p['flbd_min']}회", '--flbd-max', str(p['flbd_max']),
               '--min-price', str(p['price_min']), '--max-price', str(p['price_max']),
               '--area-min', str(p['area_min']), '--area-max', str(p['area_max']),
               '--bid-days', str(p['bid_days']), '-o', out]
        try:
            subprocess.run(cmd, cwd=ROOT, timeout=300, capture_output=True)
        except Exception:
            continue
        if os.path.exists(out):
            with open(out, encoding='utf-8-sig') as f:
                for r in csv.DictReader(f):
                    k = (r['사건번호'], r['물건소재지'])
                    if k in seen: continue
                    seen.add(k); r['_court'] = court; items.append(r)
        job['s1_count'] = len(items)
    job['s1'] = items
    return items

# ── 2조건: 세대수·연식·실거래 ──
def stage2(job, p):
    idx = apt_index(SIDO_CODE.get(p['sido'], '11'))
    job['msg'] = f"2조건 판정 — 공동주택 {len(idx)}단지 인덱스"
    passed = []
    for n, r in enumerate(job['s1']):
        job['msg'] = f"2조건 판정 {n+1}/{len(job['s1'])}"
        addr = r['물건소재지']; sgg = _sgg(addr)
        it = match_kapt(addr, idx)
        r['단지명'] = r['세대수'] = r['준공'] = ''; r['시세'] = 0; r['실거래건'] = 0
        if not it or not sgg:
            continue
        b = basis(it['kaptCode']); ud = b.get('kaptUsedate') or ''
        try: hh = int(float(b.get('kaptdaCnt') or 0))
        except: hh = 0
        yr = int(ud[:4]) if ud[:4].isdigit() else 0
        r['단지명'] = it.get('kaptName'); r['세대수'] = hh; r['준공'] = yr
        # 실거래
        code = rp.sigungu_code(sgg)
        area = _won_area(r.get('전용면적'))
        trades = []
        if code and area:
            kw = _norm(it.get('kaptName')).replace('아파트', '')[:6]
            trades = rp.trades_for(code, kw, area)
        r['실거래건'] = len(trades)
        r['시세'] = int(st.median(trades)) if trades else 0
        if hh >= p['hh_min'] and yr >= p['year_min'] and len(trades) >= 1:
            passed.append(r)
        job['s2_count'] = len(passed)
    job['s2'] = passed
    return passed

def _won_area(s):
    m = re.search(r'([\d.]+)', str(s or '')); return float(m.group(1)) if m else None

# ── 3조건: 상위 N건 권리분석 ──
def stage3(job, p):
    cand = sorted(job['s2'], key=lambda r: _rate(r.get('저감율')))[:p['top_n']]
    final = []
    for n, r in enumerate(cand):
        court = r.get('_court', ''); case = re.search(r'(\d{4}타경\d+)', r['사건번호'])
        job['msg'] = f"3조건 권리분석 {n+1}/{len(cand)} — {r['사건번호'][:20]}"
        r['권리'] = '미판정'; r['인수'] = None
        if not case: continue
        out = os.path.join(WORK, f"{job['id']}_r{n}.json")
        try:
            subprocess.run([PY, ANALYZE, '--court', court, '--case', case.group(1), '-o', out],
                           cwd=ROOT, timeout=180, capture_output=True)
        except Exception:
            continue
        risk = _rights_risk(out)
        r.update(risk)
        if risk['pass']: final.append(r)
    job['s3'] = final; job['s3_count'] = len(final)
    return final

def _find(d, key):
    """중첩 dict/list에서 key 첫 값 재귀 탐색."""
    if isinstance(d, dict):
        if key in d: return d[key]
        for v in d.values():
            r = _find(v, key)
            if r is not None: return r
    elif isinstance(d, list):
        for v in d:
            r = _find(v, key)
            if r is not None: return r
    return None

def _rights_risk(path):
    """analyze_case가 계산한 구조화 필드로 판정 — 인수보증금(투자분석)과
    명세서 비고 원문(ndstrcRghCtt)만 본다. HUG 대항력포기는 비고에 있을 때만 인정.
    (JSON 전체 텍스트에서 '대항력'+'포기'를 찾으면 문건송달·인근사례에 걸려 오탐)."""
    res = {'권리': '수집실패', '인수': None, 'pass': False, '비고': ''}
    if not os.path.exists(path): return res
    try:
        j = json.load(open(path, encoding='utf-8'))
    except Exception:
        return res
    amt = _find(j, '인수보증금')
    try: amt = int(str(amt).replace(',', '')) if amt is not None else None
    except: amt = None
    risk_flag = _find(j, '인수위험')
    bigo = str(_find(j, 'ndstrcRghCtt') or _find(j, '비고') or '')
    hug = bool(re.search(r'대항력[을은]?\s*포기|대항력포기|인수조건변경확약', bigo))
    if amt == 0:
        res.update(권리='안전(인수 0)', 인수=0, **{'pass': True})
    elif hug:
        res.update(권리='안전(HUG 대항력포기)', 인수=0, **{'pass': True}, 비고='대항력포기확약서')
    elif amt and amt > 0:
        label = f'인수위험 {amt//100000000}억+' if amt >= 100000000 else f'인수위험 {amt//10000:,}만'
        res.update(권리=label, 인수=amt, **{'pass': False})
    elif risk_flag:
        res.update(권리='인수위험(금액미상)', **{'pass': False})
    else:
        res.update(권리='임차인 없음(추정)', 인수=0, **{'pass': True})
    return res

# ── 입지(코드 4축) ──
def loc_metrics(complex_name, addr):
    out = os.path.join(WORK, f"loc_{_norm(complex_name)[:8]}.json")
    try:
        subprocess.run([PY, LOCMET, '--complex', complex_name, '--address', addr,
                        '--label', complex_name, '-o', out], cwd=ROOT, timeout=90, capture_output=True)
        j = json.load(open(out, encoding='utf-8'))
        return j
    except Exception:
        return {}

# ── 수익 계산(간이 8대비용) ──
def profit(low, sese, area, year):
    if not sese: return None
    repair = 6_000_000 if year < 2010 else (3_000_000 if year < 2018 else 1_500_000)
    tax = round(low * 0.011); legal = 600_000
    evict = round(area/3.3)*100_000; mgmt = 1_000_000
    broker = round(sese * 0.004)
    cost = low + tax + legal + evict + mgmt + repair
    return dict(세전=sese - cost - broker, roi=(sese - cost - broker)/cost, 원가=cost)

def run(job, p):
    try:
        job['stage'] = '1'; stage1(job, p)
        job['stage'] = '2'; stage2(job, p)
        job['stage'] = '3'; stage3(job, p)
        job['stage'] = 'report'; job['msg'] = '보고서 생성'
        _finalize(job, p)
        job['stage'] = 'done'; job['msg'] = '완료'
    except Exception as e:
        job['stage'] = 'error'; job['error'] = f'{type(e).__name__}: {e}'

def _finalize(job, p):
    for r in job.get('s3', []):
        loc = loc_metrics(r.get('단지명') or '', r['물건소재지'])
        r['입지점수'] = loc.get('code_subtotal_0_100')
        r['입지축'] = {k: (v or {}).get('score') for k, v in (loc.get('axes') or {}).items()}
        pr = profit(_won(r['최저가']), r.get('시세', 0), _won_area(r['전용면적']) or 60, r.get('준공') or 2000)
        r['수익'] = pr
    job['final'] = job.get('s3', [])
