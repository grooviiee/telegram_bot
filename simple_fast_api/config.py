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

# --- 챗봇 대화 이력 ---
# Gemini는 매 턴 전체 이력을 다시 입력 토큰으로 받으므로, 유지 길이가 곧 비용이다.
# 문맥 연속성이 부족하면 이 값을 늘리면 된다 (user/model 메시지 합산 개수).
CHAT_HISTORY_MAX_MESSAGES = 12

# --- 캐시 크기 · TTL(초) ---
_DAY = 86400
CACHE_SIZE_DART = 100        # DART 원본 데이터 (배당·재무·사업개요)
CACHE_SIZE_REPORT = 100      # AI 리포트 — LRU 축출은 곧 LLM 재호출이므로 넉넉히 잡는다
CACHE_SIZE_INSIDER = 50
CACHE_SIZE_EVENTS = 50

CACHE_TTL_DART = 30 * _DAY       # 연·분기 공시 주기를 고려한 갱신 주기
CACHE_TTL_VALUATION = 12 * 3600  # 주가 기반 지표 — 하루 안에는 갱신되어야 한다
CACHE_TTL_REPORT = 180 * _DAY    # 실제 무효화는 공시 지문(fingerprint)이 담당, TTL은 안전장치
CACHE_TTL_INSIDER = _DAY
CACHE_TTL_EVENTS = 7 * _DAY

# --- 공시 알림 요약 템플릿 ---
# 공시명 키워드 → 정형 요약. LLM에 넘길 수 있는 정보가 (회사명, 공시명, 접수일)뿐이라
# 모델이 제목만 보고 일반론을 생성하던 것을 정적 템플릿으로 대체했다. 30분 주기
# 스케줄러가 유일한 무인(無人) LLM 과금원이었으므로 비용 효과가 가장 크다.
# 키 순서 = 매칭 우선순위. 구체적인 사건을 먼저 두고 일반 보고서류를 뒤에 둔다
# (예: "주요사항보고서(유상증자결정)"은 '유상증자'로 매칭되어야 한다).
FILING_SUMMARY_TEMPLATES: dict[str, dict[str, str]] = {
    "유상증자": {
        "summary": "새 주식을 발행해 외부에서 자금을 조달합니다.",
        "view": "주식 수가 늘어 기존 주주의 지분율과 주당순이익(EPS)이 희석됩니다. 시설투자·신사업 목적이면 성장 투자로, 채무상환·운영자금 목적이면 자금 사정 악화 신호로 읽히는 경우가 많습니다.",
        "caution": "발행 규모, 발행가 할인율, 자금 사용 목적, 제3자 배정 여부를 원문에서 확인하세요.",
    },
    "무상증자": {
        "summary": "잉여금을 자본으로 전환해 주주에게 무상으로 신주를 배정합니다.",
        "view": "기업의 실질 가치나 시가총액은 변하지 않고 주식 수만 늘어납니다. 주당 가격이 낮아져 유동성이 개선되며, 통상 재무 여력에 대한 자신감의 신호로 해석됩니다.",
        "caution": "배정 비율과 권리락 기준일을 확인하세요. 실적 개선 없는 무상증자는 단기 재료에 그칠 수 있습니다.",
    },
    "전환사채": {
        "summary": "주식으로 전환할 수 있는 사채(CB)를 발행합니다.",
        "view": "당장은 부채지만 전환 시 주식 수가 늘어 지분이 희석됩니다. 전환가액이 낮게 설정되거나 리픽싱 조항이 있으면 희석 규모가 커질 수 있습니다.",
        "caution": "발행 규모, 전환가액, 리픽싱 조항, 인수 대상자를 원문에서 확인하세요.",
    },
    "신주인수권": {
        "summary": "신주를 인수할 권리가 붙은 사채(BW) 또는 신주인수권 관련 결정입니다.",
        "view": "전환사채와 마찬가지로 향후 주식 수 증가에 따른 지분 희석 가능성이 있습니다.",
        "caution": "행사가액과 행사 가능 기간, 인수 대상자를 확인하세요.",
    },
    "자기주식": {
        "summary": "회사가 자사 주식을 취득하거나 처분·소각합니다.",
        "view": "취득·소각은 유통 주식 수를 줄여 주당 가치를 높이는 주주환원으로, 처분은 반대로 물량 부담으로 작용합니다. 취득인지 처분인지에 따라 방향이 정반대입니다.",
        "caution": "취득·처분·소각 중 어느 것인지, 규모와 기간을 반드시 원문에서 구분하세요.",
    },
    "최대주주변경": {
        "summary": "회사의 최대주주가 변경되었습니다.",
        "view": "지배구조와 경영 방향이 바뀔 수 있는 중대 변화입니다. 인수 주체의 성격(전략적 투자자 vs 재무적 투자자)에 따라 향후 사업 전략과 자본 배분이 달라집니다.",
        "caution": "변경 사유, 신규 최대주주의 정체와 취득 자금 출처를 확인하세요.",
    },
    "분할": {
        "summary": "회사를 둘 이상으로 나누는 분할(인적·물적) 관련 결정입니다.",
        "view": "물적분할 후 자회사 상장은 모회사 주주가치 훼손 논란이 큰 사안이고, 인적분할은 기존 주주가 분할 회사 지분을 그대로 받습니다. 사업부 가치 재평가의 계기가 되기도 합니다.",
        "caution": "인적분할인지 물적분할인지, 분할되는 사업부와 분할 비율을 원문에서 확인하세요.",
    },
    "합병": {
        "summary": "다른 회사와의 합병 관련 결정입니다.",
        "view": "사업 규모와 지배구조가 바뀝니다. 합병 비율이 주주가치에 직접 영향을 주며, 시너지 실현 여부가 중장기 성과를 가릅니다.",
        "caution": "합병 비율, 합병 상대방, 주식매수청구권 행사 조건과 기간을 확인하세요.",
    },
    "영업양수도": {
        "summary": "주요 사업이나 자산을 사거나 파는 결정입니다.",
        "view": "양수는 사업 확장, 양도는 사업 재편이나 유동성 확보 신호입니다. 거래 규모가 자산총액 대비 클수록 실적 구조가 크게 바뀝니다.",
        "caution": "양수인지 양도인지, 거래 금액과 대상 사업의 매출 기여도를 확인하세요.",
    },
    "주식매수선택권": {
        "summary": "임직원에게 스톡옵션을 부여하거나 관련 사항을 결정했습니다.",
        "view": "인재 확보와 성과 연동이라는 긍정적 측면이 있지만, 행사 시 주식 수가 늘어 지분이 희석됩니다.",
        "caution": "부여 규모(발행주식 대비 비율), 행사가액, 행사 조건을 확인하세요.",
    },
    "배당": {
        "summary": "현금 또는 현물 배당이 결정되었습니다.",
        "view": "주주환원 정책의 직접적인 지표입니다. 전년 대비 배당금 변화와 배당성향이 이익 성장 및 현금창출력과 부합하는지가 핵심입니다.",
        "caution": "주당 배당금, 배당기준일, 시가배당률을 확인하세요. 이익 대비 과도한 배당은 지속 가능성을 점검할 필요가 있습니다.",
    },
    "임원변경": {
        "summary": "임원 선임·해임 등 경영진 변동 사항입니다.",
        "view": "대표이사나 핵심 경영진 교체는 전략 변화의 신호일 수 있으나, 정기 주총에 따른 통상적 변경인 경우가 대부분입니다.",
        "caution": "변경 대상이 대표이사·CFO 등 핵심 직위인지, 사임인지 임기만료인지 확인하세요.",
    },
    "감사보고서": {
        "summary": "외부감사인의 감사 결과가 제출되었습니다.",
        "view": "감사의견이 '적정'이 아닌 경우(한정·부적정·의견거절)는 상장폐지 사유가 될 수 있는 중대 사안입니다.",
        "caution": "감사의견과 '강조사항', '핵심감사사항(KAM)'을 반드시 확인하세요.",
    },
    "연결재무제표": {
        "summary": "연결 기준 재무제표가 제출되었습니다.",
        "view": "종속회사를 포함한 그룹 전체의 실적입니다. 별도 재무제표와 차이가 클수록 자회사 기여도가 큽니다.",
        "caution": "/financials 명령으로 최근 5개년 추세와 함께 확인하세요.",
    },
    "사업보고서": {
        "summary": "연간 사업보고서가 제출되었습니다.",
        "view": "한 해 실적과 사업 현황이 확정되는 가장 중요한 정기 공시입니다. 매출·영업이익·재무구조의 연간 추세를 갱신할 시점입니다.",
        "caution": "/financials, /report 명령으로 갱신된 수치를 확인하세요.",
    },
    "반기보고서": {
        "summary": "반기(상반기) 실적 보고서가 제출되었습니다.",
        "view": "연간 실적의 중간 점검 지점입니다. 전년 동기 대비 성장률과 연간 가이던스 달성 속도를 가늠할 수 있습니다.",
        "caution": "/financials-quarterly 명령으로 분기 추세를 확인하세요.",
    },
    "분기보고서": {
        "summary": "분기 실적 보고서가 제출되었습니다.",
        "view": "실적 흐름을 가장 빠르게 확인할 수 있는 공시입니다. 전분기·전년동기 대비 방향성이 중요합니다.",
        "caution": "/financials-quarterly 명령으로 분기 추세를 확인하세요.",
    },
    "주요사항보고": {
        "summary": "회사 경영에 중요한 영향을 주는 사항이 보고되었습니다.",
        "view": "증자·사채 발행·합병·소송 등 주가에 직접 영향을 줄 수 있는 사안이 담깁니다.",
        "caution": "구체적인 내용은 DART 원문에서 확인하세요.",
    },
}

# 알림 대상 판별은 템플릿 키로 통일한다 (키워드 목록과 템플릿의 불일치 방지).
IMPORTANT_FILING_KEYWORDS = list(FILING_SUMMARY_TEMPLATES)

# 키워드에 걸렸지만 개별 템플릿이 없는 경우의 기본 문구
FILING_SUMMARY_FALLBACK: dict[str, str] = {
    "summary": "투자 판단에 영향을 줄 수 있는 공시가 접수되었습니다.",
    "view": "공시 유형에 따라 실적·지배구조·주주가치에 영향을 줄 수 있습니다.",
    "caution": "구체적인 내용은 DART 원문에서 확인하세요.",
}

# --- 연도 범위 ---
YEAR_RANGE = 5  # 최근 N개년 재무 데이터 조회
