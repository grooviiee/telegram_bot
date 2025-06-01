import requests
import os
from flask import Flask, request, jsonify
import datetime # Add this import for timestamp

app = Flask(__name__)

# 이 함수는 OpenDART 기업개황정보 ZIP 파일을 다운로드하여 저장합니다.
# Flask 애플리케이션 내에서 사용될 것입니다.
def download_corp_code_zip_internal(api_key: str, save_directory: str = "downloads"):
    """
    OpenDART 기업개황정보 ZIP 파일을 다운로드하여 지정된 디렉토리에 저장합니다.

    Args:
        api_key (str): 발급받은 OpenDART API 인증키 (40자리).
        save_directory (str): ZIP 파일을 저장할 디렉토리 경로.

    Returns:
        tuple: (파일 저장 경로, 오류 메시지)
               성공 시 (저장된 파일의 전체 경로, None)
               실패 시 (None, 오류 메시지 문자열)
    """
    # 요청 URL
    url = "https://opendart.fss.or.kr/api/corpCode.xml"

    # 요청 인자 (API 인증키)
    params = {
        "crtfc_key": api_key
    }

    # 다운로드 디렉토리가 없으면 생성
    if not os.path.exists(save_directory):
        os.makedirs(save_directory)

    # 파일명에 타임스탬프를 추가하여 중복 방지
    timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
    save_filename = f"corpCode_{timestamp}.zip"
    full_save_path = os.path.join(save_directory, save_filename)

    print(f"[{url}]에서 기업개황정보 ZIP 파일 다운로드를 시작합니다...")

    try:
        response = requests.get(url, params=params, stream=True)
        response.raise_for_status()  # HTTP 오류가 발생하면 예외를 발생시킵니다.

        if response.status_code == 200:
            with open(full_save_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            print(f"ZIP 파일이 성공적으로 다운로드되어 '{full_save_path}'에 저장되었습니다.")
            return full_save_path, None
        else:
            error_message = f"파일 다운로드에 실패했습니다. 상태 코드: {response.status_code}, 응답 내용: {response.text}"
            print(error_message)
            return None, error_message

    except requests.exceptions.RequestException as e:
        error_message = f"요청 중 오류가 발생했습니다: {e}"
        print(error_message)
        return None, error_message
    except IOError as e:
        error_message = f"파일 저장 중 오류가 발생했습니다: {e}"
        print(error_message)
        return None, error_message

@app.route('/')
def home():
    """
    기본 홈 페이지. 간단한 사용 안내를 제공합니다.
    """
    return "OpenDART 기업개황정보 다운로더. '/download-corp-code?api_key=YOUR_API_KEY' 로 요청하세요."

@app.route('/download-corp-code', methods=['GET'])
def trigger_download():
    """
    OpenDART 기업개황정보 ZIP 파일 다운로드를 트리거하는 엔드포인트.
    API 키를 쿼리 파라미터 'api_key'로 받습니다.
    """
    api_key = request.args.get('api_key')

    if not api_key:
        return jsonify({"error": "API 키(api_key)가 필요합니다. 예: /download-corp-code?api_key=YOUR_API_KEY"}), 400

    # 실제 API 키를 사용하는 대신, 테스트를 위해 "YOUR_API_KEY"가 아닌지 확인합니다.
    if api_key == "YOUR_API_KEY":
        return jsonify({"warning": "테스트를 위해 'YOUR_API_KEY' 대신 실제 API 키를 사용해주세요."}), 400

    save_dir = "downloads" # 다운로드 파일을 저장할 디렉토리

    file_path, error = download_corp_code_zip_internal(api_key, save_dir)

    if error:
        return jsonify({"status": "error", "message": error}), 500
    else:
        return jsonify({"status": "success", "message": f"ZIP 파일이 서버에 성공적으로 다운로드되었습니다: {file_path}"}), 200

if __name__ == '__main__':
    # Flask 애플리케이션을 실행합니다.
    # debug=True는 개발 환경에서 유용하며, 코드 변경 시 서버가 자동으로 재시작됩니다.
    # 실제 운영 환경에서는 debug=False로 설정하고, Gunicorn과 같은 WSGI 서버를 사용해야 합니다.
    app.run(debug=True, host='0.0.0.0', port=5000)

