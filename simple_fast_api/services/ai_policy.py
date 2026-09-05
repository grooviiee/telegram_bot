"""추론 요청만 AI에 전달하고 같은 입력의 중복 생성과 실패 캐싱을 방지합니다."""
from collections.abc import Awaitable, Callable
from fastapi import HTTPException
from cache import DiskCache
from config import GEMINI_API_KEY, GEMINI_MODEL, GEMINI_REPORT_CONFIG
from services.company_data import input_fingerprint


async def cached_inference(cache: DiskCache, company: str, inputs: dict,
                           generate: Callable[[], Awaitable[str]]) -> tuple[str, bool]:
    """입력이 동일하면 AI 결과를 재사용하며 실패 응답은 저장하지 않습니다."""
    fingerprint = input_fingerprint({'inputs': inputs, 'model': GEMINI_MODEL, 'generation': GEMINI_REPORT_CONFIG})
    async with cache.lock(company):
        cached = await cache.get(company)
        if cached and cached.get('input_fingerprint') == fingerprint:
            return cached['text'], True
        if not GEMINI_API_KEY:
            raise HTTPException(503, 'AI 분석 키가 설정되지 않았습니다. 정량 조회는 사용할 수 있습니다.')
        text = await generate()
        if not text or text.startswith('(AI 응답 생성 실패)'):
            raise HTTPException(502, 'AI 분석 생성에 실패했습니다. 다시 요청해주세요.')
        await cache.set(company, {'input_fingerprint': fingerprint, 'text': text})
        return text, False
