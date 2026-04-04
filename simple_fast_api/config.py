"""중앙화된 설정 모듈. 환경변수, API URL, 상수를 한 곳에서 관리합니다."""
import os
from dotenv import load_dotenv

load_dotenv(override=True)

# --- API Keys ---
DART_API_KEY: str = os.getenv("DART_API_KEY", "")
GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
WEBHOOK_URL: str = os.getenv("WEBHOOK_URL", "")
WEBHOOK_SECRET_TOKEN: str = os.getenv("WEBHOOK_SECRET_TOKEN", "")

# --- External API URLs ---
DART_BASE_URL = "https://opendart.fss.or.kr/api"
DART_CORP_CODE_URL = f"{DART_BASE_URL}/corpCode.xml"
DART_LIST_URL = f"{DART_BASE_URL}/list.json"
DART_FINANCIALS_URL = f"{DART_BASE_URL}/fnlttSinglAcntAll.json"
DART_DIVIDEND_URL = f"{DART_BASE_URL}/alotMatter.json"
DART_ELESTOCK_URL = f"{DART_BASE_URL}/elestock.json"
DART_DOCUMENT_URL = f"{DART_BASE_URL}/document.xml"

GEMINI_MODEL = "gemini-2.5-flash"
GEMINI_URL = (
    f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}"
    f":generateContent?key={GEMINI_API_KEY}"
)

# --- DART 상수 ---
FS_DIV_ORDER = ["CFS", "OFS"]  # 연결 → 개별 순
QUARTER_REPRT_CODE = {
    "Q1": "11013",
    "Q2": "11012",
    "Q3": "11014",
    "Q4": "11011",
}
ANNUAL_REPRT_CODE = "11011"

# --- 텔레그램 상수 ---
TELEGRAM_MSG_LIMIT = 4000  # 안전 마진 포함한 최대 메시지 길이

# --- 파일 경로 ---
BASE_DIR = os.path.dirname(__file__)
REPORTS_DIR = os.path.join(BASE_DIR, "dart_reports")
DB_PATH = os.path.join(BASE_DIR, "bot_data.db")
os.makedirs(REPORTS_DIR, exist_ok=True)

# --- Gemini 생성 파라미터 ---
GEMINI_CHAT_CONFIG = {
    "temperature": 0.3,
    "topP": 0.85,
    "topK": 40,
    "maxOutputTokens": 16384,
    "thinkingConfig": {"thinkingBudget": 8192},
}
GEMINI_REPORT_CONFIG = {
    "temperature": 0.4,
    "maxOutputTokens": 8192,
    "thinkingConfig": {"thinkingBudget": 4096},
}
GEMINI_SUMMARY_CONFIG = {
    "temperature": 0.3,
    "maxOutputTokens": 600,
}

# --- Function Calling 최대 반복 횟수 ---
GEMINI_MAX_TOOL_ROUNDS = 3

# --- 공시 알림 대상 키워드 ---
IMPORTANT_FILING_KEYWORDS = [
    "사업보고서", "분기보고서", "반기보고서",
    "주요사항보고", "유상증자", "무상증자", "자기주식",
    "합병", "분할", "영업양수도", "임원변경",
    "배당", "주식매수선택권", "전환사채", "신주인수권",
    "감사보고서", "연결재무제표", "최대주주변경",
]

# --- 연도 범위 ---
YEAR_RANGE = 5  # 최근 N개년 재무 데이터 조회
