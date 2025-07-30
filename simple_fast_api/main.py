# main.py
# 필요한 라이브러리를 가져옵니다.
# ... (기존 라이브러리)
# aiohttp: 비동기 HTTP 요청을 위한 라이브러리 (Gemini API 호출용)
# json: JSON 데이터 처리를 위한 라이브러리

import os
import io
import zipfile
import requests
import uvicorn
import glob
import re
import json
import aiohttp
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse
from pydantic import BaseModel
from datetime import datetime, timedelta
from dotenv import load_dotenv
from bs4 import BeautifulSoup
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm

# --- 초기 설정 ---

# .env 파일에서 환경 변수를 로드합니다.
load_dotenv()

# FastAPI 앱 인스턴스를 생성합니다.
app = FastAPI(
    title="DART Report Analyzer with Gemini",
    description="FastAPI와 Gemini API를 사용하여 DART 보고서를 다운로드하고, 배당금 추이를 분석하여 그래프로 시각화합니다.",
    version="1.2.0"
)

# --- 환경 변수 및 전역 설정 ---
DART_API_KEY = os.getenv("DART_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")  # Gemini API 키 추가
REPORTS_DIR = "dart_reports"
CORP_CODE_URL = "https://opendart.fss.or.kr/api/corpCode.xml"

# API 키들이 설정되지 않은 경우 오류를 발생시킵니다.
if not DART_API_KEY:
    raise ValueError("DART_API_KEY가 설정되지 않았습니다. .env 파일을 확인해주세요.")
if not GEMINI_API_KEY:
    raise ValueError("GEMINI_API_KEY가 설정되지 않았습니다. .env 파일을 확인해주세요.")

# 보고서 및 그래프를 저장할 디렉토리를 생성합니다.
os.makedirs(REPORTS_DIR, exist_ok=True)

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


# --- DART API 헬퍼 함수 (기존과 동일) ---
def get_corp_code(company_name: str) -> str:
    """회사 이름을 기반으로 DART 고유의 회사 코드를 조회합니다."""
    corp_code_path = os.path.join(REPORTS_DIR, "corpCode.xml")
    if not os.path.exists(corp_code_path):
        try:
            res = requests.get(f"{CORP_CODE_URL}?crtfc_key={DART_API_KEY}")
            res.raise_for_status()
            with zipfile.ZipFile(io.BytesIO(res.content)) as z:
                z.extractall(REPORTS_DIR)
        except requests.exceptions.RequestException as e:
            raise HTTPException(status_code=500, detail=f"DART 회사 코드 목록 다운로드 실패: {e}")
    try:
        import xml.etree.ElementTree as ET
        root = ET.parse(corp_code_path).getroot()
        for item in root.findall('.//list'):
            if company_name == item.find('corp_name').text: return item.find('corp_code').text
    except ET.ParseError as e:
        raise HTTPException(status_code=500, detail=f"corpCode.xml 파싱 실패: {e}")
    raise HTTPException(status_code=404, detail=f"'{company_name}' 회사 코드를 찾을 수 없음.")


def download_reports_logic(company_name: str, corp_code: str):
    """주어진 회사 코드에 대해 최근 5년간의 보고서를 검색하고 다운로드합니다."""
    # 이 함수는 기존 코드와 동일하게 유지됩니다.
    print(f"'{company_name}'의 보고서 다운로드를 시작합니다...")
    end_date = datetime.now()
    start_date = end_date - timedelta(days=5 * 365)
    list_url = "https://opendart.fss.or.kr/api/list.json"
    params = {
        'crtfc_key': DART_API_KEY, 'corp_code': corp_code,
        'bgn_de': start_date.strftime('%Y%m%d'), 'end_de': end_date.strftime('%Y%m%d'),
        'pblntf_ty': 'A', 'pblntf_detail_ty': ['A001', 'A002', 'A003'],
        'page_no': 1, 'page_count': 100
    }
    try:
        res = requests.get(list_url, params=params)
        res.raise_for_status()
        data = res.json()
        if data.get('status') != '000' or not data.get('list'): return
        for report in data['list']:
            report_nm, rcept_no = report.get('report_nm', 'N/A'), report.get('rcept_no')
            if any(k in report_nm for k in ['사업보고서', '분기보고서', '반기보고서']):
                download_url = "https://opendart.fss.or.kr/api/document.xml"
                doc_res = requests.get(download_url, params={'crtfc_key': DART_API_KEY, 'rcept_no': rcept_no})
                doc_res.raise_for_status()
                file_name = f"{company_name}_{report_nm.replace(' ', '_')}_{report.get('rcept_dt')}.zip"
                with open(os.path.join(REPORTS_DIR, file_name), 'wb') as f: f.write(doc_res.content)
                print(f" -> 성공: '{file_name}' 저장 완료.")
    except Exception as e:
        print(f"보고서 다운로드 중 오류 발생: {e}")


# --- Gemini API 연동 및 분석 함수 (신규/수정) ---

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
    api_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-pro:generateContent?key={GEMINI_API_KEY}"

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


@app.get("/analyze-dividends/{company_name}", response_class=FileResponse)
async def analyze_dividends_with_gemini_endpoint(company_name: str):
    """
    다운로드된 보고서를 Gemini API로 분석하여 배당금 추이 그래프를 반환합니다.
    """
    print(f"'{company_name}'의 배당금 분석을 시작합니다 (Gemini API 사용)...")
    report_files = glob.glob(os.path.join(REPORTS_DIR, f"{company_name}_*.zip"))
    if not report_files:
        raise HTTPException(status_code=404, detail=f"'{company_name}'의 다운로드된 보고서가 없습니다. 먼저 다운로드를 실행해주세요.")

    dividend_data = []
    for file_path in report_files:
        # 보고서에서 배당 관련 섹션 텍스트 추출
        dividend_section_text = extract_dividend_section(file_path)
        if not dividend_section_text:
            print(f" -> '{os.path.basename(file_path)}'에서 배당 섹션을 찾지 못했습니다.")
            continue

        # Gemini API로 배당금 정보 요청
        print(f" -> '{os.path.basename(file_path)}' 분석을 위해 Gemini API 호출...")
        dividend_amount = await get_dividend_from_gemini(dividend_section_text)

        if dividend_amount is not None and dividend_amount > 0:
            report_date_str = os.path.basename(file_path).split('_')[-1].replace('.zip', '')
            dividend_data.append((report_date_str, dividend_amount))
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
