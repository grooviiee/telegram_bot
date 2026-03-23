# main.py
# 필요한 라이브러리를 가져옵니다.
# ... (기존 라이브러리)
# aiohttp: 비동기 HTTP 요청을 위한 라이브러리 (Gemini API 호출용)
# json: JSON 데이터 처리를 위한 라이브러리

import os
import io
import asyncio
import zipfile
import requests
import uvicorn
import glob
import re
import json
import secrets
import aiohttp
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, BackgroundTasks, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from datetime import datetime, timedelta
from dotenv import load_dotenv
from bs4 import BeautifulSoup
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from telegram import Update

# --- 초기 설정 ---

# .env 파일에서 환경 변수를 로드합니다. (프로젝트 모듈 import 전에 실행)
load_dotenv(override=True)

import database
import bot as telegram_bot
from cache import (dividend_cache, financials_cache, dividend_json_cache, business_cache,
                   quarterly_financials_cache, quarterly_dividend_cache, valuation_cache,
                   report_cache, buffett_report_cache)
from services.valuation import fetch_valuation
from services.report import generate_report, generate_buffett_report
from services.chat import build_system_context, chat_with_gemini
from services.dart import (get_corp_code, fetch_dart_financials, fetch_dividend_per_share,
                            fetch_dart_financials_q, fetch_dividend_per_share_q,
                            fetch_business_overview, download_reports_logic)

# --- Lifespan (startup / shutdown) ---

@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Startup ──────────────────────────────────────────────────────
    await database.init_db()

    if bot_app and WEBHOOK_URL:
        await bot_app.initialize()
        webhook_endpoint = f"{WEBHOOK_URL.rstrip('/')}/webhook"
        try:
            await bot_app.bot.set_webhook(
                url=webhook_endpoint,
                secret_token=WEBHOOK_SECRET_TOKEN if WEBHOOK_SECRET_TOKEN else None,
            )
            print(f"[Bot] Webhook 등록 완료: {webhook_endpoint}")
        except Exception as e:
            print(f"[Bot] Webhook 등록 실패 (서버는 계속 기동됩니다): {e}")

        # 매일 오전 9시(KST) 즐겨찾기 알림
        scheduler.add_job(
            telegram_bot.send_daily_notification,
            CronTrigger(hour=9, minute=0),
            args=[bot_app.bot],
            id="daily_notification",
            replace_existing=True,
        )
        scheduler.start()
        print("[Scheduler] 일일 알림 스케줄 등록 완료 (매일 09:00 KST)")
    else:
        if not TELEGRAM_BOT_TOKEN:
            print("[Bot] TELEGRAM_BOT_TOKEN 미설정 — 봇 기능 비활성화")
        if not WEBHOOK_URL:
            print("[Bot] WEBHOOK_URL 미설정 — Webhook 등록 건너뜀")

    yield

    # ── Shutdown ─────────────────────────────────────────────────────
    if scheduler.running:
        scheduler.shutdown(wait=False)
    if bot_app:
        try:
            await bot_app.bot.delete_webhook()
        except Exception as e:
            print(f"[Bot] Webhook 해제 실패 (무시): {e}")
        await bot_app.shutdown()
        print("[Bot] 봇 종료")
    await telegram_bot.close_session()


# FastAPI 앱 인스턴스를 생성합니다.
app = FastAPI(
    title="DART Report Analyzer with Gemini",
    description="FastAPI와 Gemini API를 사용하여 DART 보고서를 다운로드하고, 배당금 추이를 분석하여 그래프로 시각화합니다.",
    version="1.3.0",
    lifespan=lifespan,
)

# --- 환경 변수 및 전역 설정 ---
DART_API_KEY = os.getenv("DART_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")  # Gemini API 키 추가
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")  # 예: https://yourdomain.com
WEBHOOK_SECRET_TOKEN = os.getenv("WEBHOOK_SECRET_TOKEN", "")
REPORTS_DIR = "dart_reports"
CORP_CODE_URL = "https://opendart.fss.or.kr/api/corpCode.xml"

# API 키들이 설정되지 않은 경우 오류를 발생시킵니다.
if not DART_API_KEY:
    raise ValueError("DART_API_KEY가 설정되지 않았습니다. .env 파일을 확인해주세요.")
if not GEMINI_API_KEY:
    raise ValueError("GEMINI_API_KEY가 설정되지 않았습니다. .env 파일을 확인해주세요.")

# 보고서 및 그래프를 저장할 디렉토리를 생성합니다.
os.makedirs(REPORTS_DIR, exist_ok=True)

# --- Telegram 봇 & 스케줄러 전역 인스턴스 ---
bot_app = telegram_bot.create_bot_application() if TELEGRAM_BOT_TOKEN else None
scheduler = AsyncIOScheduler(timezone="Asia/Seoul")

# CORS 미들웨어 설정 (프론트엔드 연동)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Matplotlib 한글 폰트 설정 (기존과 동일)
font_path = None
if os.name == 'posix':
    font_paths = fm.findSystemFonts(fontpaths=None, fontext='ttf')
    nanum_paths = [p for p in font_paths if 'NanumGothic' in p]
    if nanum_paths: font_path = nanum_paths[0]
elif os.name == 'nt':
    font_path = 'c:/Windows/Fonts/malgun.ttf'

if font_path and os.path.exists(font_path):
    font_name = fm.FontProperties(fname=font_path).get_name()
    plt.rc('font', family=font_name)
    plt.rc('axes', unicode_minus=False)
    print(f"Matplotlib 한글 폰트가 '{font_name}'으로 설정되었습니다.")
else:
    print("경고: 한글 폰트를 찾을 수 없습니다. 그래프의 한글이 깨질 수 있습니다.")



# --- Gemini API 연동 및 분석 함수 (신규/수정) ---

def extract_quarter_from_filename(filename: str) -> tuple[str, str] | None:
    """
    파일명에서 연도와 분기 정보를 추출합니다.

    파일명 형식: {company}_{report_name}_{YYYYMMDD}.zip

    반환: (year, quarter) 또는 None
    예: ("2024", "Q1"), ("2024", "Q4")

    분기 매핑:
    - 1분기보고서 → Q1
    - 반기보고서 → Q2
    - 3분기보고서 → Q3
    - 사업보고서 → Q4
    """
    try:
        # 파일명에서 .zip 제거
        base_name = filename.replace('.zip', '')

        # 마지막 언더스코어로 날짜 분리
        parts = base_name.rsplit('_', 1)
        if len(parts) != 2:
            return None

        date_str = parts[1]  # YYYYMMDD
        if len(date_str) != 8 or not date_str.isdigit():
            return None

        year = date_str[:4]  # YYYY

        # 보고서명 부분 추출 (회사명 제외)
        report_part = parts[0]  # company_report_name...
        report_name_parts = report_part.split('_')

        # 보고서명은 언더스코어로 연결되어 있음
        # report_name_parts = ['company', 'report', 'name', ...]
        # 회사명은 첫 부분이고, 보고서명은 나머지
        if len(report_name_parts) < 2:
            return None

        # 회사명 다음부터가 보고서명
        report_name = '_'.join(report_name_parts[1:])

        # 분기 판정
        quarter = None
        if '1분기' in report_name:
            quarter = 'Q1'
        elif '반기' in report_name:
            quarter = 'Q2'
        elif '3분기' in report_name:
            quarter = 'Q3'
        elif '사업보고서' in report_name:
            quarter = 'Q4'

        if quarter:
            return (year, quarter)
        else:
            return None

    except Exception as e:
        print(f"파일명 파싱 오류 ({filename}): {e}")
        return None


def extract_dividend_section(zip_path: str) -> str | None:
    """보고서 zip 파일에서 '배당에 관한 사항' 섹션의 텍스트만 추출합니다."""
    try:
        with zipfile.ZipFile(zip_path, 'r') as z:
            report_file = next((f for f in z.namelist() if f.endswith(('.xml', '.html'))), None)
            if not report_file: return None
            with z.open(report_file) as f:
                try:
                    content = f.read().decode('euc-kr')
                except UnicodeDecodeError:
                    f.seek(0); content = f.read().decode('utf-8')

                soup = BeautifulSoup(content, 'html.parser')
                # '배당에 관한 사항' 제목을 포함하는 태그를 찾습니다.
                header = soup.find(string=re.compile(r'배당에\s*관한\s*사항'))
                if not header: return None

                # 해당 섹션의 내용을 담고 있는 부모 태그를 찾아서 텍스트만 반환
                # 보고서마다 구조가 다르므로 여러 상위 태그를 탐색합니다.
                section = header.find_parent('div') or header.find_parent('p')
                if section:
                    # 너무 많은 텍스트를 보내지 않도록 5000자로 제한
                    return section.get_text(separator='\n', strip=True)[:5000]
    except Exception as e:
        print(f"보고서 섹션 추출 오류 ({os.path.basename(zip_path)}): {e}")
    return None


async def get_dividend_from_gemini(text_content: str) -> int | None:
    """Gemini API를 호출하여 텍스트에서 주당 배당금을 추출합니다."""
    api_url = f"https://generativelanguage.googleapis.com/v1/models/gemini-2.5-flash:generateContent?key={GEMINI_API_KEY}"

    prompt = f"""
    아래는 DART 공시 보고서의 '배당에 관한 사항' 텍스트입니다.
    이 내용에서 표를 분석하여, 가장 최근 사업연도의 '보통주'에 대한 '주당 현금배당금'을 찾아주세요.
    숫자만 간결하게 응답해주세요. 예를 들어 '1,444' 라면 '1444' 라고만 응답해주세요.
    만약 배당금 정보가 없거나 0원이면 '0' 이라고 응답해주세요.

    ---
    {text_content}
    ---
    """

    payload = {"contents": [{"parts": [{"text": prompt}]}]}

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(api_url, json=payload) as response:
                response.raise_for_status()
                result = await response.json()

                # Gemini 응답에서 텍스트 추출
                candidate = result.get('candidates', [{}])[0]
                content_part = candidate.get('content', {}).get('parts', [{}])[0]
                raw_text = content_part.get('text', '0')

                # 응답에서 숫자만 추출하고 정수로 변환
                dividend_str = ''.join(filter(str.isdigit, raw_text))
                return int(dividend_str) if dividend_str else 0

    except Exception as e:
        print(f"Gemini API 호출 오류: {e}")
        return None


def create_dividend_graph(dividend_data: list, company_name: str) -> str | None:
    """추출된 배당금 데이터로 그래프를 생성하고 이미지 파일로 저장합니다."""
    # 이 함수는 기존 코드와 동일하게 유지됩니다.
    if not dividend_data: return None
    dividend_data.sort(key=lambda x: x[0])
    dates = [datetime.strptime(d[0], '%Y%m%d') for d in dividend_data]
    dividends = [d[1] for d in dividend_data]
    plt.figure(figsize=(12, 6))
    plt.plot(dates, dividends, marker='o', linestyle='-')
    for i, txt in enumerate(dividends):
        plt.annotate(f'{txt:,}', (dates[i], dividends[i]), textcoords="offset points", xytext=(0, 10), ha='center')
    plt.title(f'{company_name} - 최근 5년간 배당금 추이 (Gemini 분석)', fontsize=16)
    plt.xlabel('보고서 접수일', fontsize=12)
    plt.ylabel('주당 현금배당금 (원)', fontsize=12)
    plt.grid(True, linestyle='--', alpha=0.6)
    plt.xticks(rotation=45)
    plt.tight_layout()
    graph_path = os.path.join(REPORTS_DIR, f"{company_name}_dividend_trend_gemini.png")
    plt.savefig(graph_path)
    plt.close()
    print(f"배당금 그래프가 '{graph_path}'에 저장되었습니다.")
    return graph_path


# --- FastAPI 엔드포인트 ---

class CompanyRequest(BaseModel):
    company_name: str


@app.post("/download-reports/", status_code=202)
async def trigger_download(request: CompanyRequest, background_tasks: BackgroundTasks):
    """보고서 다운로드 작업을 시작합니다."""
    try:
        corp_code = get_corp_code(request.company_name)
        background_tasks.add_task(download_reports_logic, request.company_name, corp_code)
        return {"message": f"'{request.company_name}'의 보고서 다운로드 작업이 시작되었습니다."}
    except HTTPException as e:
        raise e


@app.get("/analyze-dividends-json/{company_name}")
async def analyze_dividends_json(company_name: str):
    """
    다운로드된 보고서를 Gemini API로 분석하여 분기별 배당금 데이터를 JSON으로 반환합니다.
    최근 20개 조회 결과는 서버 메모리에 캐싱됩니다.
    """
    cached = dividend_json_cache.get(company_name)
    if cached is not None:
        print(f"[Cache] '{company_name}' Gemini 분석 결과 캐시 히트")
        return JSONResponse(content={**cached, 'cached': True})

    print(f"'{company_name}'의 분기별 배당금 분석을 시작합니다 (Gemini API 사용)...")
    report_files = glob.glob(os.path.join(REPORTS_DIR, f"{company_name}_*.zip"))
    if not report_files:
        raise HTTPException(status_code=404, detail=f"'{company_name}'의 다운로드된 보고서가 없습니다. 먼저 다운로드를 실행해주세요.")

    dividend_data = []
    for file_path in report_files:
        filename = os.path.basename(file_path)

        # 1. 파일명에서 분기 정보 추출
        result = extract_quarter_from_filename(filename)
        if not result:
            print(f" -> '{filename}'에서 분기 정보를 추출하지 못했습니다.")
            continue

        year, quarter = result

        # 2. 보고서에서 배당 관련 섹션 텍스트 추출
        dividend_section_text = extract_dividend_section(file_path)
        if not dividend_section_text:
            print(f" -> '{filename}'에서 배당 섹션을 찾지 못했습니다.")
            continue

        # 3. Gemini API로 배당금 정보 요청
        print(f" -> '{filename}' 분석을 위해 Gemini API 호출 ({year}-{quarter})...")
        dividend_amount = await get_dividend_from_gemini(dividend_section_text)

        # 4. 중복 확인 후 데이터 수집
        if dividend_amount is not None and dividend_amount > 0:
            # 같은 분기의 중복 데이터가 있는지 확인
            existing = next(
                (d for d in dividend_data
                 if d['year'] == int(year) and d['quarter'] == quarter),
                None
            )

            if not existing:
                dividend_data.append({
                    'year': int(year),
                    'quarter': quarter,
                    'dividend': dividend_amount,
                    'report_date': filename.split('_')[-1].replace('.zip', '')
                })
                print(f" -> Gemini 분석 결과: {dividend_amount}원 ({year}-{quarter})")
            else:
                print(f" -> {year}-{quarter} 분기는 이미 데이터가 있어 중복 스킵")
        else:
            print(f" -> Gemini 분석 결과: 배당금 정보 없음 또는 0원 ({year}-{quarter})")

    if not dividend_data:
        raise HTTPException(status_code=404, detail=f"'{company_name}'의 보고서에서 유효한 배당금 정보를 찾을 수 없습니다.")

    # 5. 데이터 정렬 (연도, 분기 순서)
    dividend_data.sort(key=lambda x: (x['year'],
                                      ['Q1', 'Q2', 'Q3', 'Q4'].index(x['quarter'])))

    # 6. 캐시 저장 후 JSON 응답 반환
    result = {'company_name': company_name, 'dividend_data': dividend_data}
    dividend_json_cache.set(company_name, result)
    print(f"[Cache] '{company_name}' Gemini 분석 결과 캐시 저장 (총 {dividend_json_cache.info()['size']}개)")

    return JSONResponse(content={**result, 'cached': False})


@app.get("/analyze-dividends/{company_name}", response_class=FileResponse)
async def analyze_dividends_with_gemini_endpoint(company_name: str):
    """
    [기존 호환성 유지] 다운로드된 보고서를 Gemini API로 분석하여 배당금 추이 그래프를 반환합니다.
    """
    print(f"'{company_name}'의 배당금 분석을 시작합니다 (Gemini API 사용)...")
    report_files = glob.glob(os.path.join(REPORTS_DIR, f"{company_name}_*.zip"))
    if not report_files:
        raise HTTPException(status_code=404, detail=f"'{company_name}'의 다운로드된 보고서가 없습니다. 먼저 다운로드를 실행해주세요.")

    dividend_data = []
    for file_path in report_files:
        filename = os.path.basename(file_path)

        # 파일명에서 분기 정보 추출 (호환성 유지)
        result = extract_quarter_from_filename(filename)
        if result:
            year, quarter = result
            label = f"{year}-{quarter}"
        else:
            label = filename.split('_')[-1].replace('.zip', '')

        # 보고서에서 배당 관련 섹션 텍스트 추출
        dividend_section_text = extract_dividend_section(file_path)
        if not dividend_section_text:
            print(f" -> '{filename}'에서 배당 섹션을 찾지 못했습니다.")
            continue

        # Gemini API로 배당금 정보 요청
        print(f" -> '{filename}' 분석을 위해 Gemini API 호출...")
        dividend_amount = await get_dividend_from_gemini(dividend_section_text)

        if dividend_amount is not None and dividend_amount > 0:
            dividend_data.append((label, dividend_amount))
            print(f" -> Gemini 분석 결과: {dividend_amount}원")
        else:
            print(" -> Gemini 분석 결과: 배당금 정보 없음 또는 0원")

    if not dividend_data:
        raise HTTPException(status_code=404, detail=f"'{company_name}'의 보고서에서 유효한 배당금 정보를 찾을 수 없습니다.")

    graph_path = create_dividend_graph(dividend_data, company_name)
    if graph_path and os.path.exists(graph_path):
        return FileResponse(graph_path, media_type='image/png')
    else:
        raise HTTPException(status_code=500, detail="그래프 파일 생성에 실패했습니다.")


@app.get("/dividend-data/{company_name}")
async def get_dividend_data(company_name: str):
    """
    기업명으로 최근 5년간 주당 현금배당금을 조회합니다.
    - requests 블로킹 호출을 asyncio.to_thread()로 스레드풀에서 실행
    - 연도별 조회를 asyncio.gather()로 병렬 처리
    - 최근 20개 조회 결과는 서버 메모리에 캐싱
    """
    cached = dividend_cache.get(company_name)
    if cached is not None:
        print(f"[Cache] '{company_name}' 배당금 데이터 캐시 히트")
        return JSONResponse(content={**cached, 'cached': True})

    # 블로킹 I/O를 스레드풀로 위임 → 이벤트 루프 비블로킹 유지
    corp_code = await asyncio.to_thread(get_corp_code, company_name)

    current_year = datetime.now().year
    candidate_years = [str(current_year - i) for i in range(1, 7)]

    # 6개년 동시 조회
    results = await asyncio.gather(
        *[asyncio.to_thread(fetch_dividend_per_share, corp_code, year) for year in candidate_years],
        return_exceptions=True,
    )

    dividend_data = []
    for year, amount in zip(candidate_years, results):
        if isinstance(amount, Exception) or amount is None:
            continue
        dividend_data.append({'year': int(year), 'dividend': amount})
        if len(dividend_data) >= 5:
            break

    if not dividend_data:
        raise HTTPException(status_code=404, detail=f"'{company_name}'의 배당금 정보를 찾을 수 없습니다. 회사명을 다시 확인해주세요.")

    dividend_data.sort(key=lambda x: x['year'])

    result = {'company_name': company_name, 'dividend_data': dividend_data}
    dividend_cache.set(company_name, result)
    print(f"[Cache] '{company_name}' 배당금 데이터 캐시 저장 (총 {dividend_cache.info()['size']}개)")

    return JSONResponse(content={**result, 'cached': False})


@app.get("/financials/{company_name}")
async def get_financials(company_name: str):
    """
    최근 5년간 수익성·성장성·재무건전성 지표를 DART 재무제표 API에서 조회합니다.
    - requests 블로킹 호출을 asyncio.to_thread()로 스레드풀에서 실행
    - 연도별 조회를 asyncio.gather()로 병렬 처리
    - 최근 20개 조회 결과는 서버 메모리에 캐싱
    """
    cached = financials_cache.get(company_name)
    if cached is not None:
        print(f"[Cache] '{company_name}' 재무 데이터 캐시 히트")
        return JSONResponse(content={**cached, 'cached': True})

    # 블로킹 I/O를 스레드풀로 위임
    corp_code = await asyncio.to_thread(get_corp_code, company_name)

    current_year = datetime.now().year
    # 사업보고서는 3~4월 제출이므로, 전년도부터 6개년 시도하여 5개년 확보
    candidate_years = [str(current_year - i) for i in range(1, 7)]

    # 6개년 동시 조회
    results = await asyncio.gather(
        *[asyncio.to_thread(fetch_dart_financials, corp_code, year) for year in candidate_years],
        return_exceptions=True,
    )

    financials = [r for r in results if r and not isinstance(r, Exception)][:5]

    if not financials:
        raise HTTPException(status_code=404, detail=f"'{company_name}'의 재무 데이터를 찾을 수 없습니다.")

    financials.sort(key=lambda x: x['year'])

    result = {'company_name': company_name, 'financials': financials}
    financials_cache.set(company_name, result)
    print(f"[Cache] '{company_name}' 재무 데이터 캐시 저장 (총 {financials_cache.info()['size']}개)")

    return JSONResponse(content={**result, 'cached': False})


@app.get("/business-overview/{company_name}")
async def get_business_overview(company_name: str):
    """
    최신 사업보고서의 '사업의 내용' 1~4항을 반환합니다.
    - 보고서 zip을 다운로드하여 HTML 파싱
    - 최근 20개 조회 결과는 캐시에 저장
    """
    cached = business_cache.get(company_name)
    if cached is not None:
        print(f"[Cache] '{company_name}' 사업개요 캐시 히트")
        return JSONResponse(content={**cached, 'cached': True})

    corp_code = await asyncio.to_thread(get_corp_code, company_name)
    result    = await asyncio.to_thread(fetch_business_overview, corp_code, company_name)

    business_cache.set(company_name, result)
    print(f"[Cache] '{company_name}' 사업개요 캐시 저장 (총 {business_cache.info()['size']}개)")
    return JSONResponse(content={**result, 'cached': False})


@app.get("/financials-quarterly/{company_name}")
async def get_financials_quarterly(company_name: str):
    """최근 5개년 분기별 재무 지표를 조회합니다."""
    cached = quarterly_financials_cache.get(company_name)
    if cached is not None:
        print(f"[Cache] '{company_name}' 분기 재무 데이터 캐시 히트")
        return JSONResponse(content={**cached, 'cached': True})

    corp_code = await asyncio.to_thread(get_corp_code, company_name)

    current_year = datetime.now().year
    targets = [
        (str(current_year - i), q)
        for i in range(5, 0, -1)
        for q in ['Q1', 'Q2', 'Q3', 'Q4']
    ]

    results = await asyncio.gather(
        *[asyncio.to_thread(fetch_dart_financials_q, corp_code, year, quarter)
          for year, quarter in targets],
        return_exceptions=True,
    )

    financials = [
        r for r in results
        if r is not None and not isinstance(r, Exception)
    ]

    if not financials:
        raise HTTPException(status_code=404, detail=f"'{company_name}'의 분기 재무 데이터를 찾을 수 없습니다.")

    financials.sort(key=lambda x: (x['year'], x.get('quarter', 'Q4')))

    result = {'company_name': company_name, 'period': 'quarterly', 'financials': financials}
    quarterly_financials_cache.set(company_name, result)
    print(f"[Cache] '{company_name}' 분기 재무 데이터 캐시 저장")
    return JSONResponse(content={**result, 'cached': False})


@app.get("/dividend-data-quarterly/{company_name}")
async def get_dividend_data_quarterly(company_name: str):
    """최근 5개년 분기별 배당금을 조회합니다."""
    cached = quarterly_dividend_cache.get(company_name)
    if cached is not None:
        print(f"[Cache] '{company_name}' 분기 배당 데이터 캐시 히트")
        return JSONResponse(content={**cached, 'cached': True})

    corp_code = await asyncio.to_thread(get_corp_code, company_name)

    current_year = datetime.now().year
    targets = [
        (str(current_year - i), q)
        for i in range(5, 0, -1)
        for q in ['Q1', 'Q2', 'Q3', 'Q4']
    ]

    results = await asyncio.gather(
        *[asyncio.to_thread(fetch_dividend_per_share_q, corp_code, year, quarter)
          for year, quarter in targets],
        return_exceptions=True,
    )

    dividend_data = []
    for (year, quarter), amount in zip(targets, results):
        if isinstance(amount, Exception) or amount is None or amount <= 0:
            continue
        dividend_data.append({
            'year': int(year),
            'quarter': quarter,
            'label': year[-2:] + quarter,
            'dividend': amount,
        })

    dividend_data.sort(key=lambda x: (x['year'], x['quarter']))

    result = {'company_name': company_name, 'period': 'quarterly', 'dividend_data': dividend_data}
    quarterly_dividend_cache.set(company_name, result)
    print(f"[Cache] '{company_name}' 분기 배당 데이터 캐시 저장")
    return JSONResponse(content={**result, 'cached': False})


@app.get("/valuation/{company_name}")
async def get_valuation(company_name: str):
    """현재 주가 기반 밸류에이션 지표를 반환합니다 (PER, PBR, PSR, EV/EBIT)."""
    cached = valuation_cache.get(company_name)
    if cached is not None:
        print(f"[Cache] '{company_name}' 밸류에이션 캐시 히트")
        return JSONResponse(content={**cached, 'cached': True})

    result = await asyncio.to_thread(fetch_valuation, company_name)
    valuation_cache.set(company_name, result)
    print(f"[Cache] '{company_name}' 밸류에이션 캐시 저장")
    return JSONResponse(content={**result, 'cached': False})


@app.get("/report/{company_name}")
async def get_report(company_name: str):
    """Gemini AI를 이용해 종합 투자 리포트를 생성합니다."""
    cached = report_cache.get(company_name)
    if cached is not None:
        print(f"[Cache] '{company_name}' 리포트 캐시 히트")
        return JSONResponse(content={**cached, 'cached': True})

    corp_code = await asyncio.to_thread(get_corp_code, company_name)
    current_year = datetime.now().year

    def fetch_filings_sync():
        res = requests.get(
            "https://opendart.fss.or.kr/api/list.json",
            params={
                'crtfc_key': DART_API_KEY, 'corp_code': corp_code,
                'bgn_de': f"{current_year - 1}0101",
                'end_de': f"{current_year}1231",
                'sort': 'date', 'sort_mth': 'desc', 'page_count': 10,
            },
            timeout=15,
        )
        data = res.json()
        return data.get('list', []) if data.get('status') == '000' else []

    biz_result, filings, fin_all = await asyncio.gather(
        asyncio.to_thread(fetch_business_overview, corp_code, company_name),
        asyncio.to_thread(fetch_filings_sync),
        asyncio.gather(
            *[asyncio.to_thread(fetch_dart_financials, corp_code, str(y))
              for y in range(current_year - 1, current_year - 6, -1)],
            return_exceptions=True,
        ),
        return_exceptions=True,
    )

    business_sections = biz_result.get('sections', []) if isinstance(biz_result, dict) else []
    recent_filings    = filings if isinstance(filings, list) else []
    financials        = [f for f in (fin_all if isinstance(fin_all, (list, tuple)) else []) if isinstance(f, dict)]
    dividends         = (dividend_cache.get(company_name) or {}).get('dividend_data', [])
    valuation         = valuation_cache.get(company_name)

    report_text = await generate_report(
        company_name, business_sections, financials, dividends, valuation, recent_filings
    )

    result = {'company_name': company_name, 'report': report_text}
    report_cache.set(company_name, result)
    print(f"[Cache] '{company_name}' 리포트 캐시 저장")
    return JSONResponse(content={**result, 'cached': False})


@app.get("/buffett-report/{company_name}")
async def get_buffett_report(company_name: str):
    """워렌 버핏 투자 철학을 적용한 종합 투자 리포트를 생성합니다.
    경제적 해자, 내재가치, 안전마진 관점에서 분석합니다."""
    cached = buffett_report_cache.get(company_name)
    if cached is not None:
        print(f"[Cache] '{company_name}' 버핏 리포트 캐시 히트")
        return JSONResponse(content={**cached, 'cached': True})

    corp_code = await asyncio.to_thread(get_corp_code, company_name)
    current_year = datetime.now().year

    def fetch_filings_sync():
        res = requests.get(
            "https://opendart.fss.or.kr/api/list.json",
            params={
                'crtfc_key': DART_API_KEY, 'corp_code': corp_code,
                'bgn_de': f"{current_year - 1}0101",
                'end_de': f"{current_year}1231",
                'sort': 'date', 'sort_mth': 'desc', 'page_count': 10,
            },
            timeout=15,
        )
        data = res.json()
        return data.get('list', []) if data.get('status') == '000' else []

    biz_result, filings, fin_all = await asyncio.gather(
        asyncio.to_thread(fetch_business_overview, corp_code, company_name),
        asyncio.to_thread(fetch_filings_sync),
        asyncio.gather(
            *[asyncio.to_thread(fetch_dart_financials, corp_code, str(y))
              for y in range(current_year - 1, current_year - 6, -1)],
            return_exceptions=True,
        ),
        return_exceptions=True,
    )

    business_sections = biz_result.get('sections', []) if isinstance(biz_result, dict) else []
    recent_filings    = filings if isinstance(filings, list) else []
    financials        = [f for f in (fin_all if isinstance(fin_all, (list, tuple)) else []) if isinstance(f, dict)]
    dividends         = (dividend_cache.get(company_name) or {}).get('dividend_data', [])
    valuation         = valuation_cache.get(company_name)

    report_text = await generate_buffett_report(
        company_name, business_sections, financials, dividends, valuation, recent_filings
    )

    result = {'company_name': company_name, 'report': report_text, 'mode': 'buffett'}
    buffett_report_cache.set(company_name, result)
    print(f"[Cache] '{company_name}' 버핏 리포트 캐시 저장")
    return JSONResponse(content={**result, 'cached': False})


class ChatRequest(BaseModel):
    message: str
    history: list[dict] = []
    mode: str = "general"   # "general" | "buffett"


@app.post("/chat/{company_name}")
async def chat(company_name: str, req: ChatRequest):
    """공시 데이터를 컨텍스트로 Gemini AI와 멀티턴 상담을 수행합니다.
    mode="buffett" 시 워렌 버핏 투자 철학 기반으로 답변합니다."""
    corp_code = await asyncio.to_thread(get_corp_code, company_name)
    current_year = datetime.now().year

    def fetch_filings_sync():
        res = requests.get(
            "https://opendart.fss.or.kr/api/list.json",
            params={
                'crtfc_key': DART_API_KEY, 'corp_code': corp_code,
                'bgn_de': f"{current_year - 1}0101",
                'end_de': f"{current_year}1231",
                'sort': 'date', 'sort_mth': 'desc', 'page_count': 10,
            },
            timeout=15,
        )
        data = res.json()
        return data.get('list', []) if data.get('status') == '000' else []

    # 캐시 우선 사용
    biz_cached = business_cache.get(company_name)
    fin_cached = financials_cache.get(company_name)

    tasks = []
    need_biz = biz_cached is None
    need_fin = fin_cached is None

    if need_biz:
        tasks.append(asyncio.to_thread(fetch_business_overview, corp_code, company_name))
    if need_fin:
        tasks.append(asyncio.gather(
            *[asyncio.to_thread(fetch_dart_financials, corp_code, str(y))
              for y in range(current_year - 1, current_year - 4, -1)],
            return_exceptions=True,
        ))
    tasks.append(asyncio.to_thread(fetch_filings_sync))

    results = await asyncio.gather(*tasks, return_exceptions=True)
    idx = 0
    if need_biz:
        biz_cached = results[idx] if isinstance(results[idx], dict) else {}
        idx += 1
    if need_fin:
        fin_all = results[idx] if isinstance(results[idx], (list, tuple)) else []
        fin_cached = {'financials': [f for f in fin_all if isinstance(f, dict)]}
        idx += 1
    filings = results[idx] if isinstance(results[idx], list) else []

    business_sections = (biz_cached or {}).get('sections', [])
    financials        = (fin_cached or {}).get('financials', [])
    dividends         = (dividend_cache.get(company_name) or {}).get('dividend_data', [])
    valuation         = valuation_cache.get(company_name)

    buffett_mode = req.mode == "buffett"
    system_context = build_system_context(
        company_name, business_sections, financials, dividends, valuation, filings,
        buffett_mode=buffett_mode,
    )
    answer = await chat_with_gemini(
        system_context, req.history, req.message, company_name,
        buffett_mode=buffett_mode,
    )
    return JSONResponse(content={"answer": answer, "mode": req.mode})


@app.get("/cache/status")
async def cache_status():
    """서버에 저장된 캐시 현황을 반환합니다."""
    return JSONResponse(content={
        "dividend_data": dividend_cache.info(),
        "financials": financials_cache.info(),
        "analyze_dividends_json": dividend_json_cache.info(),
        "business_overview": business_cache.info(),
        "quarterly_financials": quarterly_financials_cache.info(),
        "quarterly_dividend": quarterly_dividend_cache.info(),
        "valuation": valuation_cache.info(),
        "report": report_cache.info(),
        "buffett_report": buffett_report_cache.info(),
    })


@app.delete("/cache/clear")
async def cache_clear(company_name: str = None):
    """
    캐시를 초기화합니다.
    - company_name 파라미터 없음: 전체 캐시 삭제
    - company_name 지정: 해당 기업 캐시만 삭제
    """
    if company_name:
        removed = any([
            dividend_cache.clear(company_name),
            financials_cache.clear(company_name),
            dividend_json_cache.clear(company_name),
            business_cache.clear(company_name),
            report_cache.clear(company_name),
            buffett_report_cache.clear(company_name),
        ])
        if not removed:
            raise HTTPException(status_code=404, detail=f"'{company_name}'의 캐시 데이터가 없습니다.")
        return {"message": f"'{company_name}'의 캐시가 삭제되었습니다."}
    else:
        dividend_cache.clear()
        financials_cache.clear()
        dividend_json_cache.clear()
        business_cache.clear()
        report_cache.clear()
        buffett_report_cache.clear()
        return {"message": "전체 캐시가 삭제되었습니다."}


@app.post("/webhook", include_in_schema=False)
async def telegram_webhook(request: Request):
    """Telegram이 메시지를 밀어주는 Webhook 엔드포인트."""
    if WEBHOOK_SECRET_TOKEN:
        incoming = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
        if not secrets.compare_digest(incoming, WEBHOOK_SECRET_TOKEN):
            raise HTTPException(status_code=403, detail="Forbidden")
    if not bot_app:
        raise HTTPException(status_code=503, detail="봇이 비활성화 상태입니다.")
    data = await request.json()
    update = Update.de_json(data, bot_app.bot)
    await bot_app.process_update(update)
    return {"ok": True}


@app.get("/", include_in_schema=False)
async def root():
    return {"message": "DART Report Analyzer with Gemini. /docs 에서 API 문서를 확인하세요."}


# --- 서버 실행 ---
if __name__ == "__main__":
    # aiohttp 설치 확인
    try:
        import aiohttp
    except ImportError:
        print("`aiohttp` 라이브러리가 필요합니다. `pip install aiohttp` 명령어로 설치해주세요.")
        exit()

    print("서버를 시작합니다. http://127.0.0.1:8000/docs 에서 API 문서를 확인하세요.")
    uvicorn.run(app, host="127.0.0.1", port=8000)
