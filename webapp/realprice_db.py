# -*- coding: utf-8 -*-
"""실거래 DuckDB 캐시 — 시군구·월 단위로 PublicDataReader에서 받아 저장·재사용.
2조건(실거래 존재·시세)을 빠르게 판정하기 위한 로컬 캐시."""
import os, warnings, datetime, threading
warnings.filterwarnings('ignore')
import duckdb
from dotenv import load_dotenv
import PublicDataReader as pdr

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(ROOT, 'webapp', 'realprice_cache.duckdb')
load_dotenv(os.path.join(ROOT, '.env'))
KEY = os.getenv('PUBLIC_DATA_API_KEY') or os.getenv('PUBLIC_DATA_SERVICE_KEY')
_lock = threading.Lock()
_bdong = None

def _con():
    con = duckdb.connect(DB_PATH)
    con.execute("""CREATE TABLE IF NOT EXISTS trades(
        sigungu VARCHAR, ym VARCHAR, apt VARCHAR, dong VARCHAR,
        area DOUBLE, floor INTEGER, amount BIGINT)""")
    con.execute("""CREATE TABLE IF NOT EXISTS fetched(sigungu VARCHAR, ym VARCHAR)""")
    return con

def bdong():
    global _bdong
    if _bdong is None: _bdong = pdr.code_bdong()
    return _bdong

def sigungu_code(name):
    """시군구명(예: '구로구', '수원시 장안구', '평택시')으로 시군구코드 조회."""
    df = bdong()
    hit = df[df['시군구명'].astype(str) == name]['시군구코드']
    if len(hit) == 0:
        hit = df[df['시군구명'].astype(str).str.endswith(name)]['시군구코드']
    return str(hit.iloc[0]) if len(hit) else None

def recent_months(n=12):
    d = datetime.date.today().replace(day=1); out = []
    for _ in range(n):
        out.append(d.strftime('%Y%m')); d = (d - datetime.timedelta(days=1)).replace(day=1)
    return out

def _to_won(v):
    try: return int(str(v).replace(',', '').strip()) * 10000
    except: return None

def ensure(sigungu, months=None):
    """캐시에 없는 (시군구,월)만 API로 받아 적재."""
    months = months or recent_months(12)
    api = pdr.TransactionPrice(KEY)
    with _lock, _con() as con:
        done = set(r[0] for r in con.execute(
            "SELECT ym FROM fetched WHERE sigungu=?", [sigungu]).fetchall())
        for ym in months:
            if ym in done: continue
            rows = []
            try:
                df = api.get_data(property_type='아파트', trade_type='매매',
                                  sigungu_code=sigungu, year_month=ym, verbose=False)
            except Exception:
                df = None
            aptcol = None
            if df is not None and len(df):
                aptcol = ('단지명' if '단지명' in df.columns else
                          '아파트' if '아파트' in df.columns else
                          next((c for c in df.columns if '단지' in c or '아파트' in c), None))
            if aptcol:
                for _, r in df.iterrows():
                    won = _to_won(r.get('거래금액'))
                    try: area = float(r.get('전용면적'))
                    except: area = None
                    try: floor = int(r.get('층'))
                    except: floor = None
                    if won and area:
                        rows.append((sigungu, ym, str(r.get(aptcol, '')),
                                     str(r.get('법정동', '')), area, floor, won))
            if rows:
                con.executemany("INSERT INTO trades VALUES (?,?,?,?,?,?,?)", rows)
            con.execute("INSERT INTO fetched VALUES (?,?)", [sigungu, ym])

def trades_for(sigungu, apt_kw, area, tol=3.0):
    """단지 키워드 + 전용±tol 실거래 리스트(금액원). 캐시 자동 채움."""
    ensure(sigungu)
    with _lock, _con() as con:
        rows = con.execute(
            "SELECT amount, floor, area FROM trades WHERE sigungu=? AND apt LIKE ? "
            "AND abs(area-?)<=?", [sigungu, f'%{apt_kw}%', area, tol]).fetchall()
    return [r[0] for r in rows]
