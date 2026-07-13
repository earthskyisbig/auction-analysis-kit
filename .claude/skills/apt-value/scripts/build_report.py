# -*- coding: utf-8 -*-
"""complex_value.json -> report.html + report_artifact.html (단지 가치 분해 리포트)"""
import json, argparse, os
ap = argparse.ArgumentParser(); ap.add_argument('--workdir', default='.'); A = ap.parse_args()
W = A.workdir
D = json.load(open(os.path.join(W, 'complex_value.json'), encoding='utf-8'))
S = D['summary']; P = D.get('profile', {})
C_UP, C_DN, C_INK, C_MUT, GRID = '#c8fa46', 'rgba(230,230,225,.28)', '#f4f4f2', 'rgba(230,230,225,.58)', 'rgba(255,255,255,.1)'

def won(v):
    if v is None: return '-'
    return (f"{v/10000:.2f}억".replace('.00억', '억')) if v >= 10000 else f"{v:,}만"

def dev_bars(rows, key='dev', label='dong', width=880):
    """0 기준 발산 가로막대 (동/층 프리미엄)"""
    if not rows: return ''
    rh, gap, ml = 30, 8, 120; mid = ml + (width-ml-90)/2; half = (width-ml-90)/2
    vmax = max(abs(r[key]) for r in rows) * 1.15 or 1
    Ht = len(rows)*(rh+gap)+8
    p = [f'<svg viewBox="0 0 {width} {Ht}" class="chart" role="img" preserveAspectRatio="xMidYMid meet">']
    p.append(f'<line x1="{mid}" y1="4" x2="{mid}" y2="{Ht-4}" stroke="{C_MUT}" stroke-width="1"/>')
    for i, r in enumerate(rows):
        y = i*(rh+gap)+6; v = r[key]; w = abs(v)/vmax*half
        x = mid if v >= 0 else mid-w; col = C_UP if v >= 0 else C_DN
        nm = (r.get('dong','')+'동') if label == 'dong' else r.get('band','')
        p.append(f'<text x="{ml-12}" y="{y+rh/2+5:.0f}" text-anchor="end" class="lbl">{nm}</text>')
        p.append(f'<rect x="{x:.1f}" y="{y}" width="{w:.1f}" height="{rh}" rx="3" fill="{col}"/>')
        tx = mid+w+8 if v >= 0 else mid-w-8; anc = 'start' if v >= 0 else 'end'
        p.append(f'<text x="{tx:.1f}" y="{y+rh/2-2:.0f}" text-anchor="{anc}" class="lbl" fill="{col}">{v:+.1f}%</text>')
        p.append(f'<text x="{tx:.1f}" y="{y+rh/2+13:.0f}" text-anchor="{anc}" class="ax">{won(r["ppa"])}/평 · {r["n"]}건</text>')
    p.append('</svg>'); return '\n'.join(p)

# 프로파일 카드 항목(있는 것만)
def pf(label, val, suf=''):
    return f'<div class="pf"><div class="pk">{label}</div><div class="pv">{val}{suf}</div></div>' if val else ''
built = P.get('built_year') or S['built']
prof_cards = ''.join([
    pf('세대수', f"{int(P['households']):,}" if P.get('households') else None, '세대'),
    pf('동수', P.get('dong_cnt'), '개동'),
    pf('준공', built, '년'),
    pf('연식', f"{S['age']}", '년차'),
    pf('난방', P.get('heat')), pf('복도유형', P.get('corridor')),
    pf('지상주차', P.get('park_ground'), '대'), pf('지하주차', P.get('park_under'), '대'),
    pf('시공', P.get('builder')),
])
sub_line = ''
if P.get('subway_station'):
    sub_line = f"{P['subway_station']}역" + (f" 도보 {P['subway_time']}" if P.get('subway_time') else '')
addr = P.get('addr') or f"{S['district']}"

# 평형별 시세 표
size_rows = ''.join(
    f"<tr><td>{s['pyeong']}평 <span class='ax'>(전용 {s['area']}㎡)</span></td><td class='num'>{won(s['price_lo'])}</td>"
    f"<td class='num'><b>{won(s['price_mid'])}</b></td><td class='num'>{won(s['price_hi'])}</td>"
    f"<td class='num'>{won(s['ppa'])}</td><td class='num'>{s['n']}</td></tr>"
    for s in D['sizes'])

best_d = D['best']['dong']; best_f = D['best']['floor']; worst_d = D['worst']['dong']
best_line = ''
if best_d and best_f:
    best_line = (f"이 단지에서 가장 값이 세게 매겨지는 자리는 <span class='hi'>{best_d['dong']}동</span>"
                 f"(단지 평균 대비 {best_d['dev']:+.1f}%)의 <span class='hi'>{best_f['band']}</span>이고, "
                 f"가장 저평가된 자리는 {worst_d['dong']}동({worst_d['dev']:+.1f}%)입니다. "
                 f"같은 단지·같은 평형이라도 <b>동에 따라 {best_d['dev']-worst_d['dev']:.0f}%p</b>까지 벌어집니다.")

CSS = """*{margin:0;padding:0;box-sizing:border-box}
:root{--bg-0:#0b0b0d;--bg-1:#141417;--surface:rgba(255,255,255,.035);--surface-2:rgba(255,255,255,.06);--ink:#f4f4f2;--ink-2:#d9d9d4;--muted:rgba(230,230,225,.58);--line:rgba(255,255,255,.1);--lime:#c8fa46;--lime-2:#a6e800;--lime-soft:rgba(200,250,70,.12);--warn:#ffb454}
body{background:radial-gradient(circle at 18% -4%,rgba(200,250,70,.06),transparent 42%),linear-gradient(180deg,var(--bg-0),var(--bg-1));color:var(--ink-2);font-family:'Pretendard',-apple-system,BlinkMacSystemFont,'Segoe UI',system-ui,sans-serif;line-height:1.7;min-height:100vh;-webkit-font-smoothing:antialiased}
body::before{content:'';position:fixed;inset:0;pointer-events:none;background-image:linear-gradient(rgba(210,255,60,.045) 1px,transparent 1px),linear-gradient(90deg,rgba(210,255,60,.045) 1px,transparent 1px);background-size:46px 46px;mask-image:linear-gradient(180deg,rgba(0,0,0,.75),transparent 70%)}
h1,h2,h3,.eyebrow,.pk,.pv,.ax,.lbl,.vt th,.stat b,.num,.legend,.warn,footer{font-family:'Gilroy','Pretendard',-apple-system,BlinkMacSystemFont,'Segoe UI',system-ui,sans-serif}
.wrap{max-width:1000px;margin:0 auto;padding:0 24px;position:relative;z-index:1}
.eyebrow{font-size:12px;font-weight:800;letter-spacing:.12em;text-transform:uppercase;color:var(--lime);display:inline-flex;align-items:center;gap:8px}
.eyebrow::before{content:'';width:7px;height:7px;border-radius:50%;background:linear-gradient(100deg,var(--lime),var(--lime-2));box-shadow:0 0 18px var(--lime-soft)}
.hero{padding:78px 0 44px;border-bottom:1px solid var(--line);position:relative;overflow:hidden;background:linear-gradient(180deg,rgba(255,255,255,.025),transparent)}
.hero .blob{position:absolute;width:380px;height:380px;border-radius:50%;filter:blur(70px);opacity:.42;background:var(--lime-soft);top:-140px;right:-50px}
.hero .wrap{position:relative}
h1{font-size:clamp(36px,5.5vw,64px);font-weight:700;letter-spacing:-.045em;line-height:1.05;margin:16px 0 10px;color:var(--ink)}
.addr{color:var(--muted);font-size:17px;font-weight:600}
.profgrid{display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));gap:12px;margin-top:26px}
.pf{background:var(--surface);border:1px solid var(--line);border-radius:16px;padding:14px 16px;box-shadow:0 20px 55px rgba(0,0,0,.22)}
.pk{font-size:11px;color:var(--muted);font-weight:800;letter-spacing:.08em;text-transform:uppercase}.pv{font-size:20px;font-weight:700;letter-spacing:-.02em;margin-top:3px;color:var(--ink)}
section{padding:52px 0;border-top:1px solid var(--line)}section.soft{background:rgba(255,255,255,.025)}
h2{font-size:clamp(24px,3.4vw,34px);font-weight:700;letter-spacing:-.035em;margin:12px 0 8px;color:var(--ink)}
.sub{color:var(--muted);max-width:700px;margin-bottom:22px}
.chart{width:100%;height:auto;display:block;background:var(--surface);border:1px solid var(--line);border-radius:18px;padding:16px 10px;box-shadow:0 20px 55px rgba(0,0,0,.24)}
.ax{font-size:11px;fill:rgba(230,230,225,.58);color:var(--muted)}.lbl{font-size:12.5px;font-weight:700;fill:var(--ink)}
.vt{width:100%;border-collapse:collapse;background:var(--surface);border:1px solid var(--line);border-radius:14px;overflow:hidden;font-size:14px}
.vt th{background:var(--surface-2);font-size:12px;font-weight:800;padding:11px 12px;text-align:left;color:var(--muted);letter-spacing:.06em;text-transform:uppercase}
.vt th.num,.vt td.num{text-align:right;font-variant-numeric:tabular-nums}
.vt td{padding:10px 12px;border-top:1px solid var(--line);font-family:'Gilroy','Pretendard',-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif}.vt td:first-child{font-weight:700;color:var(--ink)}
.note{margin-top:20px;background:var(--surface);border:1px solid var(--line);border-left:3px solid var(--lime);border-radius:0 14px 14px 0;padding:16px 20px}
.note .t{font-weight:800;font-size:14px;margin-bottom:6px;color:var(--ink)}.note p{font-size:15px;color:var(--ink-2)}.note .hi{color:var(--lime);font-weight:800}
.legend{display:flex;gap:18px;margin:12px 2px 0;font-size:13px;color:var(--muted)}
.legend i{width:13px;height:4px;border-radius:2px;display:inline-block;margin-right:6px}
.warn{background:rgba(255,180,84,.1);border:1px solid rgba(255,180,84,.28);border-radius:14px;padding:14px 18px;margin-top:20px;font-size:13.5px;color:var(--ink-2);font-weight:600}
footer{padding:40px 0;border-top:1px solid var(--line);color:var(--muted);font-size:13px}footer b{color:var(--ink)}
@media print{body{background:#fff;color:#111}body::before,.hero .blob{display:none}.chart,.pf,.note,.vt{box-shadow:none;border-color:#ddd;background:#fff;color:#111}}
"""

BODY = f"""<div class="hero"><div class="blob"></div><div class="wrap">
<div class="eyebrow">단지 가치 분해 · 동 × 층 × 평형</div>
<h1>{S['name']}</h1>
<div class="addr">{addr}{(' · '+sub_line) if sub_line else ''}</div>
<div class="profgrid">{prof_cards}</div>
<div class="warn" style="margin-top:18px">최근 {S['period']} 실거래 {S['deals']}건 기준 · 평당가 중앙값 <b>{won(S['ppa_median'])}</b> (범위 {won(S['ppa_min'])}~{won(S['ppa_max'])}) · 향(방향)은 공공데이터에 없어 제외{'' if P else ' · 세대수·동수는 공동주택 API 활용신청 후 표시됩니다'}</div>
</div></div>

<section><div class="wrap"><div class="eyebrow">01 · 평형별 시세</div>
<h2>어떤 평형이 얼마에 거래되나</h2>
<p class="sub">전용면적별 실거래 가격대입니다. 낮은값~중앙값~높은값은 각 평형의 하위 10% · 중앙 · 상위 10% 거래입니다.</p>
<table class="vt"><thead><tr><th>평형</th><th class="num">낮은값</th><th class="num">중앙값</th><th class="num">높은값</th><th class="num">평당</th><th class="num">거래</th></tr></thead><tbody>{size_rows}</tbody></table>
</div></section>

<section class="soft"><div class="wrap"><div class="eyebrow">02 · 동의 가치</div>
<h2>같은 단지, 어느 동이 비싼가</h2>
<p class="sub">평형 차이를 걷어낸 뒤(같은 평형 평균 대비) 동별 프리미엄입니다. 양(+)은 단지 평균보다 비싸게, 음(−)은 싸게 거래된 동입니다.</p>
{dev_bars(D['dongs'], 'dev', 'dong')}
<div class="legend"><span><i style="background:{C_UP}"></i>단지 평균 대비 프리미엄(+)</span><span><i style="background:{C_DN}"></i>디스카운트(−)</span></div>
<div class="note"><div class="t">📖 쉽게 풀면</div><p>{best_line or '동별 표본이 부족합니다.'}</p></div>
</div></section>

<section><div class="wrap"><div class="eyebrow">03 · 층의 가치</div>
<h2>층에 따른 값 차이</h2>
<p class="sub">역시 평형 효과를 제거한 층대별 프리미엄입니다.</p>
{dev_bars(D['floors'], 'dev', 'floor')}
<div class="note"><div class="t">📖 쉽게 풀면</div><p>보통 저층이 할인되고 중·고층이 소폭 프리미엄을 받습니다. 다만 층 차이는 동 차이보다 작은 경우가 많아, <b>어느 동이냐가 층보다 값을 더 가르는</b> 단지가 흔합니다.</p></div>
</div></section>

<footer><div class="wrap"><b>{S['name']} 가치 분해</b> · 자료 국토교통부 실거래가{' + 공동주택 기본정보' if P else ''} · 분석기간 {S['period']}<br>
동·층 프리미엄은 같은 평형 평균 대비 편차의 평균입니다. 표본이 적은 동·층은 값이 흔들릴 수 있어 참고용이며, 투자 판단의 책임은 이용자 본인에게 있습니다.</div></footer>"""

FONTS = '<link rel="preconnect" href="https://cdn.jsdelivr.net"><link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard/dist/web/static/pretendard.css">'
open(os.path.join(W, 'report.html'), 'w', encoding='utf-8').write(
    f'<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{S["name"]} 가치 분해</title>{FONTS}<style>{CSS}</style></head><body>{BODY}</body></html>')
open(os.path.join(W, 'report_artifact.html'), 'w', encoding='utf-8').write(f'<style>{CSS}</style>{BODY}')
print(f'report.html · report_artifact.html 생성 ({S["name"]})')
