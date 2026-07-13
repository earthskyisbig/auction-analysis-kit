# -*- coding: utf-8 -*-
"""한 단지의 동별·층별·평형별 '가치'를 실거래로 분해. -> complex_value.json

사용: python analyze_value.py --workdir ./out --name 도곡렉슬 [--district 강남구] [--months 24]

방법론: 같은 단지라도 평형(전용면적)이 다르면 평당가가 다르다. 그래서 '평형 효과'를 먼저
제거한다 — 각 거래의 평당가를 (같은 면적대 평균 대비) 편차로 바꾼 뒤, 그 편차를 동/층으로
모으면 순수한 '동 프리미엄'·'층 프리미엄'이 남는다. 향(방향)은 공공데이터에 없어 제외한다.
"""
import warnings, json, argparse, os
warnings.filterwarnings('ignore')
import numpy as np, pandas as pd
PY = 3.3058
def num(s): return pd.to_numeric(s.astype(str).str.replace(',', '', regex=False).str.strip(), errors='coerce')

ap = argparse.ArgumentParser()
ap.add_argument('--workdir', default='.')
ap.add_argument('--name', required=True, help='단지명(부분일치 허용)')
ap.add_argument('--district', default='')
ap.add_argument('--months', type=int, default=24, help='최근 N개월 실거래만 사용')
args = ap.parse_args()

s = pd.read_csv(os.path.join(args.workdir, 'sale.csv'))
s['ym'] = s['계약년도'].astype(str) + s['계약월'].astype(str).str.zfill(2)
s['면적'] = num(s['전용면적']); s['금액'] = num(s['거래금액']); s['층N'] = num(s['층'])
s['평당'] = s['금액'] / (s['면적'] / PY); s['면적R'] = s['면적'].round(0)
s['건축'] = num(s['건축년도'])
months = sorted(s['ym'].unique())[-args.months:]

# 단지 필터(부분일치)
d = s[s['단지명'].astype(str).str.contains(args.name, na=False) & s['ym'].isin(months)].copy()
if len(d) < 10:
    raise SystemExit(f'"{args.name}" 최근 {args.months}개월 거래가 {len(d)}건뿐입니다. 이름/기간을 확인하세요.')
name_full = d['단지명'].value_counts().index[0]
d = d[d['단지명'] == name_full]
lo, hi = d['평당'].quantile([.02, .98]); d = d[(d['평당'] >= lo) & (d['평당'] <= hi)]

# 평형 효과 제거: 면적대 평균 대비 편차(%)
d['gmean'] = d.groupby('면적R')['평당'].transform('mean')
d['gn'] = d.groupby('면적R')['평당'].transform('size')
d['dev'] = (d['평당'] / d['gmean'] - 1) * 100

def eok(v): return round(v / 10000, 2) if v is not None and not pd.isna(v) else None

# ---- 단지 요약 ----
summary = {
    'name': name_full, 'district': args.district,
    'built': int(d['건축'].median()), 'age': int(d['계약년도'].median() - d['건축'].median()),
    'deals': int(len(d)), 'ppa_median': round(d['평당'].median()),
    'ppa_min': round(d['평당'].quantile(.05)), 'ppa_max': round(d['평당'].quantile(.95)),
    'price_min': int(d['금액'].min()), 'price_max': int(d['금액'].max()),
    'period': f"{months[0][:4]}.{months[0][4:]}~{months[-1][:4]}.{months[-1][4:]}",
}

# ---- 평형별 시세 ----
sizes = []
for a, g in d.groupby('면적R'):
    if len(g) < 3: continue
    sizes.append({'area': int(a), 'pyeong': round(a / PY, 1), 'n': int(len(g)),
                  'ppa': round(g['평당'].median()),
                  'price_lo': int(g['금액'].quantile(.1)), 'price_mid': int(g['금액'].median()),
                  'price_hi': int(g['금액'].quantile(.9))})
sizes.sort(key=lambda x: x['area'])

# ---- 동별 가치(평형 보정 편차) ----
# 실거래 '아파트동명'은 신고 누락이 있어 전체가 채워지지 않는다. 조용히 빼지 않고 커버리지를 기록한다.
dd = d[d['아파트동명'].notna()]
dong_missing = int(len(d) - len(dd))
dongs, dong_thin = [], []
for dong, g in dd.groupby('아파트동명'):
    if len(g) < 3:
        dong_thin.append({'dong': str(dong), 'n': int(len(g))}); continue
    dongs.append({'dong': str(dong), 'n': int(len(g)), 'dev': round(g['dev'].mean(), 1),
                  'ppa': round(g['평당'].median())})
dongs.sort(key=lambda x: -x['dev'])
dong_thin.sort(key=lambda x: -x['n'])
dong_coverage = {
    'total': int(len(d)), 'labeled': int(len(dd)), 'missing': dong_missing,
    'dong_cnt_labeled': int(dd['아파트동명'].nunique()),
    'dong_cnt_reported': len(dongs), 'thin': dong_thin,
}

# ---- 층별 가치 ----
def fb(f):
    if f <= 3: return '저층(1~3층)'
    if f <= 7: return '중층(4~7층)'
    if f <= 15: return '고층(8~15층)'
    return '초고층(16층~)'
d['층대'] = d['층N'].apply(fb)
order = ['저층(1~3층)', '중층(4~7층)', '고층(8~15층)', '초고층(16층~)']
floors = []
for fbn in order:
    g = d[d['층대'] == fbn]
    if len(g) < 3: continue
    floors.append({'band': fbn, 'n': int(len(g)), 'dev': round(g['dev'].mean(), 1),
                   'ppa': round(g['평당'].median())})

# ---- 최고/최저 조합 ----
best = {'dong': dongs[0] if dongs else None, 'floor': max(floors, key=lambda x: x['dev']) if floors else None}
worst = {'dong': dongs[-1] if dongs else None, 'floor': min(floors, key=lambda x: x['dev']) if floors else None}

# ---- 최근 6개월 실거래 점도표용 원자료 ----
# 평형 효과로 가격대가 통째로 갈라져 보이므로, 면적을 3분위(소/중/대)로 나눠 점 색을 구분한다.
recent = None
recent_months = sorted(d['ym'].unique())[-6:]
d6 = d[d['ym'].isin(recent_months)].dropna(subset=['면적', '금액', '계약일']).copy()
if len(d6) >= 5:
    try:
        _, edges = pd.qcut(d6['면적'], q=3, retbins=True, duplicates='drop')
        edges = sorted(set(edges.tolist()))
    except ValueError:
        edges = [d6['면적'].min(), d6['면적'].max()]
    def area_label(v, edges):
        for i in range(len(edges) - 1):
            lo, hi = edges[i], edges[i + 1]
            if v <= hi + 1e-9 or i == len(edges) - 2:
                if i == 0: return f'~{int(round(hi))}㎡'
                if i == len(edges) - 2: return f'{int(round(lo))+1}㎡~'
                return f'{int(round(lo))+1}~{int(round(hi))}㎡'
        return f'{int(round(v))}㎡'
    d6['area_bin'] = d6['면적'].apply(lambda v: area_label(v, edges))
    bins_order = sorted(d6['area_bin'].unique(), key=lambda b: d6.loc[d6['area_bin'] == b, '면적'].mean())
    points = [{
        'date': f"{int(r['계약년도'])}-{int(r['계약월']):02d}-{int(r['계약일']):02d}",
        'area': round(r['면적'], 1), 'area_bin': r['area_bin'],
        'floor': (int(r['층N']) if pd.notna(r['층N']) else None),
        'price': int(r['금액']),
    } for _, r in d6.iterrows()]
    recent = {
        'period': f"{recent_months[0][:4]}.{recent_months[0][4:]}~{recent_months[-1][:4]}.{recent_months[-1][4:]}",
        'n': len(points), 'points': points, 'bins': bins_order,
    }

out = {'summary': summary, 'sizes': sizes, 'dongs': dongs, 'floors': floors,
       'best': best, 'worst': worst, 'recent': recent, 'dong_coverage': dong_coverage}
# 공동주택 프로파일(있으면 병합)
cp = os.path.join(args.workdir, 'complex_profile.json')
if os.path.exists(cp):
    out['profile'] = json.load(open(cp, encoding='utf-8'))
json.dump(out, open(os.path.join(args.workdir, 'complex_value.json'), 'w', encoding='utf-8'),
          ensure_ascii=False, indent=1)
print(f"[{name_full}] 거래 {len(d)}건 · 평당 {summary['ppa_median']}만(범위 {summary['ppa_min']}~{summary['ppa_max']})")
print(f"  평형 {len(sizes)}종 · 동 {len(dongs)}개(동명거래 {len(dd)}/{len(d)}건, 동 미상 {dong_missing}건) · 층대 {len(floors)}")
if dong_thin: print(f"  표본부족 제외 동: " + ", ".join(f"{t['dong']}동({t['n']}건)" for t in dong_thin))
if dongs: print(f"  동 프리미엄 최고 {dongs[0]['dong']}동 {dongs[0]['dev']:+.1f}% / 최저 {dongs[-1]['dong']}동 {dongs[-1]['dev']:+.1f}%")
if floors: print(f"  층 프리미엄: " + " ".join(f"{f['band'][:2]}{f['dev']:+.0f}%" for f in floors))
