"""레거시 Gemini 기반 보고서 파일 분석 라우트."""
import os
import re
import glob
import zipfile
import aiohttp

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from datetime import datetime
from bs4 import BeautifulSoup
import matplotlib.pyplot as plt

from config import GEMINI_API_KEY, REPORTS_DIR
from cache import dividend_json_cache

router = APIRouter()


# ── 유틸리티 함수 ────────────────────────────────────────────────────────────

def extract_quarter_from_filename(filename: str) -> tuple[str, str] | None:
    """파일명에서 연도와 분기 정보를 추출합니다."""
    try:
        base_name = filename.replace('.zip', '')
        parts = base_name.rsplit('_', 1)
        if len(parts) != 2:
            return None

        date_str = parts[1]
        if len(date_str) != 8 or not date_str.isdigit():
            return None

        year = date_str[:4]
        report_name_parts = parts[0].split('_')
        if len(report_name_parts) < 2:
            return None

        report_name = '_'.join(report_name_parts[1:])

        quarter = None
        if '1분기' in report_name:
            quarter = 'Q1'
        elif '반기' in report_name:
            quarter = 'Q2'
        elif '3분기' in report_name:
            quarter = 'Q3'
        elif '사업보고서' in report_name:
            quarter = 'Q4'

        return (year, quarter) if quarter else None
    except Exception as e:
        print(f"파일명 파싱 오류 ({filename}): {e}")
        return None


def extract_dividend_section(zip_path: str) -> str | None:
    """보고서 zip 파일에서 '배당에 관한 사항' 섹션의 텍스트만 추출합니다."""
    try:
        with zipfile.ZipFile(zip_path, 'r') as z:
            report_file = next((f for f in z.namelist() if f.endswith(('.xml', '.html'))), None)
            if not report_file:
                return None
            with z.open(report_file) as f:
                try:
                    content = f.read().decode('euc-kr')
                except UnicodeDecodeError:
                    f.seek(0)
                    content = f.read().decode('utf-8')

                soup = BeautifulSoup(content, 'html.parser')
                header = soup.find(string=re.compile(r'배당에\s*관한\s*사항'))
                if not header:
                    return None

                section = header.find_parent('div') or header.find_parent('p')
                if section:
                    return section.get_text(separator='\n', strip=True)[:5000]
    except Exception as e:
        print(f"보고서 섹션 추출 오류 ({os.path.basename(zip_path)}): {e}")
    return None


async def get_dividend_from_gemini(text_content: str) -> int | None:
    """Gemini API를 호출하여 텍스트에서 주당 배당금을 추출합니다."""
    api_url = (
        f"https://generativelanguage.googleapis.com/v1/models/gemini-2.5-flash"
        f":generateContent?key={GEMINI_API_KEY}"
    )

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
                candidate = result.get('candidates', [{}])[0]
                content_part = candidate.get('content', {}).get('parts', [{}])[0]
                raw_text = content_part.get('text', '0')
                dividend_str = ''.join(filter(str.isdigit, raw_text))
                return int(dividend_str) if dividend_str else 0
    except Exception as e:
        print(f"Gemini API 호출 오류: {e}")
        return None


def create_dividend_graph(dividend_data: list, company_name: str) -> str | None:
    """추출된 배당금 데이터로 그래프를 생성하고 이미지 파일로 저장합니다."""
    if not dividend_data:
        return None
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
    return graph_path


# ── 라우트 ────────────────────────────────────────────────────────────────────

@router.get("/analyze-dividends-json/{company_name}")
async def analyze_dividends_json(company_name: str):
    """다운로드된 보고서를 Gemini API로 분석하여 분기별 배당금 데이터를 반환합니다."""
    cached = await dividend_json_cache.get(company_name)
    if cached is not None:
        return JSONResponse(content={**cached, 'cached': True})

    report_files = glob.glob(os.path.join(REPORTS_DIR, f"{company_name}_*.zip"))
    if not report_files:
        raise HTTPException(status_code=404, detail=f"'{company_name}'의 다운로드된 보고서가 없습니다.")

    dividend_data = []
    for file_path in report_files:
        filename = os.path.basename(file_path)
        result = extract_quarter_from_filename(filename)
        if not result:
            continue

        year, quarter = result
        dividend_section_text = extract_dividend_section(file_path)
        if not dividend_section_text:
            continue

        dividend_amount = await get_dividend_from_gemini(dividend_section_text)

        if dividend_amount is not None and dividend_amount > 0:
            existing = next(
                (d for d in dividend_data if d['year'] == int(year) and d['quarter'] == quarter),
                None,
            )
            if not existing:
                dividend_data.append({
                    'year': int(year), 'quarter': quarter,
                    'dividend': dividend_amount,
                    'report_date': filename.split('_')[-1].replace('.zip', ''),
                })

    if not dividend_data:
        raise HTTPException(status_code=404, detail=f"'{company_name}'의 보고서에서 유효한 배당금 정보를 찾을 수 없습니다.")

    dividend_data.sort(key=lambda x: (x['year'], ['Q1', 'Q2', 'Q3', 'Q4'].index(x['quarter'])))
    result = {'company_name': company_name, 'dividend_data': dividend_data}
    await dividend_json_cache.set(company_name, result)
    return JSONResponse(content={**result, 'cached': False})


@router.get("/analyze-dividends/{company_name}", response_class=FileResponse)
async def analyze_dividends_with_gemini_endpoint(company_name: str):
    """[레거시] 다운로드된 보고서를 Gemini API로 분석하여 배당금 추이 그래프를 반환합니다."""
    report_files = glob.glob(os.path.join(REPORTS_DIR, f"{company_name}_*.zip"))
    if not report_files:
        raise HTTPException(status_code=404, detail=f"'{company_name}'의 다운로드된 보고서가 없습니다.")

    dividend_data = []
    for file_path in report_files:
        filename = os.path.basename(file_path)
        result = extract_quarter_from_filename(filename)
        label = f"{result[0]}-{result[1]}" if result else filename.split('_')[-1].replace('.zip', '')

        dividend_section_text = extract_dividend_section(file_path)
        if not dividend_section_text:
            continue

        dividend_amount = await get_dividend_from_gemini(dividend_section_text)
        if dividend_amount is not None and dividend_amount > 0:
            dividend_data.append((label, dividend_amount))

    if not dividend_data:
        raise HTTPException(status_code=404, detail=f"'{company_name}'의 보고서에서 유효한 배당금 정보를 찾을 수 없습니다.")

    graph_path = create_dividend_graph(dividend_data, company_name)
    if graph_path and os.path.exists(graph_path):
        return FileResponse(graph_path, media_type='image/png')
    raise HTTPException(status_code=500, detail="그래프 파일 생성에 실패했습니다.")
