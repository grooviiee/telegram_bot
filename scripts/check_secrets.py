"""추적 파일의 비밀값을 출력하지 않고 알려진 credential 형식을 검사합니다."""
import re
import subprocess
import sys

PATTERNS = {
    'Google API key': rb'AIza[0-9A-Za-z_-]{30,}',
    'Telegram token': rb'\b\d{6,12}:[A-Za-z0-9_-]{30,}\b',
    'GitHub token': rb'(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,})',
    'OpenAI key': rb'\bsk-(?:proj-|svcacct-)?[A-Za-z0-9_-]{30,}',
    'private key': rb'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----',
    'DART key': rb'(?i)(?:api[_-]?key|dart_api)\s*[=:]\s*[\"\']?[0-9a-f]{40}\b',
}


def main() -> int:
    """현재 작업 트리의 추적 텍스트 파일에서 비밀값 패턴을 확인합니다."""
    from pathlib import Path
    root = Path(subprocess.check_output(['git', 'rev-parse', '--show-toplevel']).decode().strip())
    paths = subprocess.check_output(['git', 'ls-files', '-z'], cwd=root).decode().split('\0')
    failed = False
    for name in filter(None, paths):
        path = root / name
        if not path.is_file():
            continue
        data = path.read_bytes()
        if '\x00'.encode() in data:  # 이미지 등 바이너리의 우연한 패턴은 제외합니다.
            continue
        if Path(name).name == '.env':
            print(f'{name}: 추적 중인 .env 파일')
            failed = True
        for kind, pattern in PATTERNS.items():
            for match in re.finditer(pattern, data):
                line = data[:match.start()].count(b'\n') + 1
                print(f'{name}:{line}: {kind} 패턴 발견 (값 비공개)')
                failed = True
    if not failed:
        print('추적 텍스트 파일: 알려진 credential 패턴 없음')
    return int(failed)


if __name__ == '__main__':
    sys.exit(main())
