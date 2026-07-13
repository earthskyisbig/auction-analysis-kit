# -*- coding: utf-8 -*-
"""경매 스크리닝 웹앱 (로컬 전용).
폼 입력 → 백그라운드 파이프라인(1→2→3조건) → 퍼널 + 비교 보고서."""
import os, uuid, threading, datetime
from flask import Flask, request, jsonify, render_template, abort
import pipeline

app = Flask(__name__)
JOBS = {}

def new_job(p):
    jid = uuid.uuid4().hex[:8]
    job = {'id': jid, 'stage': 'queued', 'msg': '대기', 'params': p,
           's1_count': 0, 's2_count': 0, 's3_count': 0,
           's1': [], 's2': [], 's3': [], 'final': [], 'started': datetime.datetime.now().isoformat()}
    JOBS[jid] = job
    threading.Thread(target=pipeline.run, args=(job, p), daemon=True).start()
    return job

@app.route('/')
def index():
    return render_template('index.html')

@app.post('/api/run')
def api_run():
    f = request.get_json(silent=True) or request.form.to_dict() or {}
    def num(k, d):
        try: return type(d)(f.get(k, d))
        except: return d
    p = {
        'sido': f.get('sido', '서울'),
        'flbd_min': num('flbd_min', 1), 'flbd_max': num('flbd_max', 3),
        'area_min': num('area_min', 59.0), 'area_max': num('area_max', 85.0),
        'price_min': num('price_min', 50000000), 'price_max': num('price_max', 900000000),
        'bid_days': num('bid_days', 14),
        'hh_min': num('hh_min', 500), 'year_min': num('year_min', 2005),
        'top_n': num('top_n', 3),
    }
    job = new_job(p)
    return jsonify({'id': job['id']})

def _slim(r):
    return {k: r.get(k) for k in ('사건번호','물건소재지','전용면적','감정가','최저가','저감율','유찰횟수',
        '매각기일','단지명','세대수','준공','실거래건','시세','권리','인수','입지점수','입지축','수익','_court')}

@app.get('/api/status/<jid>')
def api_status(jid):
    job = JOBS.get(jid)
    if not job: abort(404)
    return jsonify({
        'stage': job['stage'], 'msg': job.get('msg',''), 'error': job.get('error'),
        's1_count': job.get('s1_count',0), 's2_count': job.get('s2_count',0), 's3_count': job.get('s3_count',0),
        's1_total': len(job.get('s1',[])),
        's2': [_slim(r) for r in job.get('s2',[])],
        'final': [_slim(r) for r in job.get('final',[])],
    })

if __name__ == '__main__':
    print('▶ http://127.0.0.1:5000  (Ctrl+C 종료)')
    app.run(debug=False, port=5000, threaded=True)
