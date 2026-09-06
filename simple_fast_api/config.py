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
NAVER_CLIENT_ID: str = os.getenv("NAVER_CLIENT_ID", "")
NAVER_CLIENT_SECRET: str = os.getenv("NAVER_CLIENT_SECRET", "")
GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")

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

NAVER_NEWS_URL = "https://openapi.naver.com/v1/search/news.json"

GROQ_MODEL = "llama-3.3-70b-versatile"
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

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

# --- 분석 신뢰성 및 호출 정책 ---
CACHE_SCHEMA_VERSION = 2
DATA_CACHE_TTL_SECONDS = 24 * 60 * 60
MARKET_CACHE_TTL_SECONDS = 15 * 60
AI_CACHE_TTL_SECONDS = 24 * 60 * 60
NEWS_CACHE_TTL_SECONDS = 30 * 60
DART_VIEWER_URL = "https://dart.fss.or.kr/dsaf001/main.do?rcpNo="
ANALYSIS_POLICY_VERSION = "2026-09-reliability-v1"
SCORE_WEIGHTS = {
    "growth": 0.25, "profitability": 0.25, "financial_health": 0.20,
    "dividend": 0.10, "valuation": 0.20,
}
AI_EVIDENCE_RULES = """
신뢰성 규칙:
- 수치와 계산은 제공된 정량 결과를 사용하고 없는 값은 추정하지 마세요.
- 데이터 부족은 무배당, 0, 중립 평가를 의미하지 않습니다. 평가 불가라고 표시하세요.
- 공시 목록은 제목과 접수 정보뿐입니다. 본문을 읽은 것처럼 내용이나 영향을 단정하지 마세요.
- 출처, 재무 기준연도, 수집시각을 구분하세요. 수집시각은 시세 체결시각이 아닙니다.
- 동종업계 데이터가 없으면 업계 대비 우위/저평가를 단정하지 마세요.
- FCF는 오너이익의 근사치이며 유지보수 CapEx를 분리한 값이 아닙니다.
- 사실과 해석, 가정을 명확히 구분하고 데이터가 부족한 가격 추정은 하지 마세요.
"""

# --- 주요 사건 분석 ---
MAX_EVENTS = 8
NEWS_PAGE_SIZE = 100        # Naver 뉴스 검색 1회 호출당 최대 결과 수
NEWS_MAX_PAGES = 10         # date순 페이지네이션 최대 횟수 (API 상한 start<=1000까지 전부 사용)
NEWS_LOOKBACK_DAYS = 365    # 최근 1년 이내 기사만 사용
MAX_ARTICLES_FOR_PROMPT = 80  # Groq 무료 티어 분당 토큰 한도(TPM 12,000)를 넘기지 않도록 제한
SUMMARY_MAX_CHARS = 70      # 프롬프트용 기사 요약 길이 제한 (토큰 절약)
PRICE_WINDOW_BEFORE = 1     # 이벤트 날짜 기준 참고용 가격 변동 계산 구간(거래일)
PRICE_WINDOW_AFTER = 3

CATEGORY_OPTIONS = "실적/밸류에이션/산업뉴스/규제/공급망/경쟁사/신사업/기타"
