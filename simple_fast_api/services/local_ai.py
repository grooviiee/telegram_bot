"""Ollama 로컬 모델 호출과 도구 실행을 외부 AI 폴백 없이 처리합니다."""
import asyncio
import json
import logging
import re
from urllib.parse import urlparse

import aiohttp
from async_timeout import timeout

from config import (OLLAMA_BASE_URL, OLLAMA_MODEL, OLLAMA_NUM_CTX, OLLAMA_NUM_BATCH,
                    OLLAMA_MAX_INPUT_CHARS, OLLAMA_MAX_OUTPUT_TOKENS,
                    OLLAMA_MAX_TOOL_ROUNDS, OLLAMA_REQUEST_TIMEOUT,
                    OLLAMA_KEEP_ALIVE, OLLAMA_SYSTEM_RULES)

FAILURE = '(AI 응답 생성 실패)'
_inference_slot = asyncio.Semaphore(1)


def _validate_local_endpoint() -> None:
    """로컬 전용 주소와 로컬 모델만 허용해 외부 과금 경로를 차단합니다."""
    parsed = urlparse(OLLAMA_BASE_URL)
    if parsed.scheme != 'http' or parsed.hostname not in ('127.0.0.1', 'localhost', '::1') or parsed.username or parsed.password:
        raise ValueError('Ollama는 인증정보가 없는 로컬 HTTP 주소만 허용합니다.')
    if 'cloud' in OLLAMA_MODEL.lower():
        raise ValueError('클라우드 모델은 로컬 모드에서 사용할 수 없습니다.')


def _clip(text: str, limit: int) -> str:
    """긴 자료는 앞뒤를 보존하고 생략 여부를 명시합니다."""
    if len(text) <= limit:
        return text
    marker = '\n[길이 제한으로 일부 자료 생략: 제외된 자료는 해석하지 마세요.]\n'
    if limit <= len(marker):
        return marker[:max(0, limit)]
    keep = limit - len(marker)
    return text[:keep // 2] + marker + text[-(keep - keep // 2):]


def prepare_messages(prompt: str, system_instruction: str | None,
                     contents: list[dict] | None, reserve: int = 0) -> tuple[list[dict], bool]:
    """Gemini 형식의 대화를 로컬 문맥 예산 안의 메시지로 변환합니다."""
    source = []
    for content in contents or []:
        text = '\n'.join(part['text'] for part in content.get('parts', []) if isinstance(part.get('text'), str))
        if text:
            source.append({'role': 'assistant' if content.get('role') == 'model' else 'user', 'content': text})
    if not source:
        source = [{'role': 'user', 'content': prompt}]
    budget = OLLAMA_MAX_INPUT_CHARS - len(OLLAMA_SYSTEM_RULES) - reserve
    system = system_instruction or ''
    system_limit = budget * 2 // 3 if system else 0
    clipped_system = _clip(system, system_limit) if system else ''
    remaining = budget - len(clipped_system)
    last = dict(source[-1])
    last['content'] = _clip(last['content'], remaining)
    remaining -= len(last['content'])
    history = []
    for message in reversed(source[:-1]):
        if len(message['content']) > remaining:
            break
        history.insert(0, message)
        remaining -= len(message['content'])
    truncated = clipped_system != system or last != source[-1] or len(history) != len(source) - 1
    messages = [{'role': 'system', 'content': OLLAMA_SYSTEM_RULES + '\n' + clipped_system}, *history, last]
    return messages, truncated


def extract_answer(message: dict, done_reason: str | None) -> str:
    """추론 텍스트와 미완성 응답을 제외하고 최종 답변만 반환합니다."""
    content = message.get('content', '')
    if not isinstance(content, str) or done_reason == 'length':
        return FAILURE
    if '</think>' in content:
        content = content.rsplit('</think>', 1)[-1]
    content = re.sub(r'<think>.*?</think>', '', content, flags=re.DOTALL).strip()
    if '<think>' in content or not content:
        return FAILURE
    return content


async def call_ollama(prompt: str = '', *, system_instruction: str | None = None,
                      contents: list[dict] | None = None, generation_config: dict | None = None,
                      tools: list[dict] | None = None, tool_executor=None) -> str:
    """로컬 모델에 요청하고 허용된 읽기 도구만 제한 횟수로 실행합니다."""
    try:
        _validate_local_endpoint()
        messages, truncated = prepare_messages(prompt, system_instruction, contents,
                                               reserve=OLLAMA_MAX_INPUT_CHARS // 2 if tools else 0)
        generation = generation_config or {}
        limit = min(generation.get('maxOutputTokens', OLLAMA_MAX_OUTPUT_TOKENS), OLLAMA_MAX_OUTPUT_TOKENS)
        functions = {tool['name']: tool for tool in tools or []}
        local_tools = [{'type': 'function', 'function': definition} for definition in functions.values()]
        async with timeout(OLLAMA_REQUEST_TIMEOUT):
            async with _inference_slot:
                async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=OLLAMA_REQUEST_TIMEOUT)) as session:
                    for round_index in range(OLLAMA_MAX_TOOL_ROUNDS + 1):
                        payload = {
                            'model': OLLAMA_MODEL, 'messages': messages, 'stream': False, 'think': False,
                            'keep_alive': OLLAMA_KEEP_ALIVE,
                            'options': {'num_ctx': OLLAMA_NUM_CTX, 'num_batch': OLLAMA_NUM_BATCH, 'num_predict': limit,
                                        'temperature': generation.get('temperature', .3), 'num_gpu': 99},
                        }
                        if local_tools and round_index < OLLAMA_MAX_TOOL_ROUNDS:
                            payload['tools'] = local_tools
                        async with session.post(f'{OLLAMA_BASE_URL}/api/chat', json=payload) as response:
                            if response.status != 200:
                                logging.getLogger(__name__).warning('Ollama 호출 실패 HTTP %s', response.status)
                                return FAILURE
                            data = await response.json()
                        if not data.get('done') or data.get('done_reason') == 'length':
                            return FAILURE
                        message = data.get('message', {})
                        calls = message.get('tool_calls', [])
                        if not calls:
                            answer = extract_answer(message, data.get('done_reason'))
                            if truncated and answer != FAILURE:
                                answer = '[일부 자료·이전 대화는 문맥 길이 제한으로 제외되었습니다.]\n' + answer
                            return answer
                        if tool_executor is None or round_index == OLLAMA_MAX_TOOL_ROUNDS or len(calls) > OLLAMA_MAX_TOOL_ROUNDS:
                            return FAILURE
                        messages.append(message)
                        for call in calls:
                            function = call.get('function', {})
                            name, args = function.get('name'), function.get('arguments', {})
                            if name not in functions or not isinstance(args, dict):
                                return FAILURE
                            try:
                                result = await tool_executor(name, args)
                            except Exception:
                                result = {'error': '요청한 추가 자료를 확인하지 못했습니다.'}
                            text = json.dumps(result, ensure_ascii=False)
                            remaining = OLLAMA_MAX_INPUT_CHARS - sum(len(json.dumps(m, ensure_ascii=False)) for m in messages)
                            if remaining < 500:
                                return FAILURE
                            clipped = _clip(text, min(remaining, OLLAMA_MAX_INPUT_CHARS // 4))
                            truncated = truncated or clipped != text
                            messages.append({'role': 'tool', 'tool_name': name, 'content': clipped})
                    return FAILURE
    except Exception as exc:
        logging.getLogger(__name__).warning('로컬 AI 호출 실패 (%s)', type(exc).__name__)
        return FAILURE


async def ollama_status() -> dict:
    """모델 설치와 GPU 메모리 적재 상태를 읽기 전용으로 확인합니다."""
    _validate_local_endpoint()
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=5)) as session:
            async with session.get(f'{OLLAMA_BASE_URL}/api/tags') as response:
                response.raise_for_status()
                installed = await response.json()
            async with session.get(f'{OLLAMA_BASE_URL}/api/ps') as response:
                response.raise_for_status()
                running = await response.json()
        loaded = next((r for r in running.get('models', []) if r.get('name') == OLLAMA_MODEL), None)
        return {'provider': 'ollama', 'model': OLLAMA_MODEL, 'available': True,
                'installed': any(r.get('name') == OLLAMA_MODEL for r in installed.get('models', [])),
                'loaded': loaded is not None, 'gpu_bytes': loaded.get('size_vram', 0) if loaded else 0,
                'model_bytes': loaded.get('size', 0) if loaded else 0}
    except Exception:
        return {'provider': 'ollama', 'model': OLLAMA_MODEL, 'available': False,
                'installed': False, 'loaded': False, 'gpu_bytes': 0, 'model_bytes': 0}
