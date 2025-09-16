import requests
import os
import yaml
import datetime
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse

app = FastAPI()

# CORS 설정
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 모든 origin 허용
    allow_credentials=True,
    allow_methods=["*"],  # 모든 HTTP 메소드 허용
    allow_headers=["*"],  # 모든 HTTP 헤더 허용
)

def get_api_key():
    with open("config.yaml", 'r') as stream:
        try:
            config = yaml.safe_load(stream)
            return config.get('api_key')
        except yaml.YAMLError as exc:
            print(exc)
            return None

def download_corp_code_zip_internal(save_directory: str = "downloads"):
    """
    OpenDART 기업개황정보 ZIP 파일을 다운로드하여 지정된 디렉토리에 저장합니다.
    """
    api_key = get_api_key()
    if not api_key:
        return None, "API 키를 config.yaml에서 찾을 수 없습니다."
    
    url = "https://opendart.fss.or.kr/api/corpCode.xml"
    params = {"crtfc_key": api_key}

    if not os.path.exists(save_directory):
        os.makedirs(save_directory)

    timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
    save_filename = f"corpCode_{timestamp}.zip"
    full_save_path = os.path.join(save_directory, save_filename)

    print(f"[{url}]에서 기업개황정보 ZIP 파일 다운로드를 시작합니다...")

    try:
        response = requests.get(url, params=params, stream=True)
        response.raise_for_status()

        with open(full_save_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        
        print(f"ZIP 파일이 성공적으로 다운로드되어 '{full_save_path}'에 저장되었습니다.")
        return full_save_path, None

    except requests.exceptions.RequestException as e:
        error_message = f"요청 중 오류가 발생했습니다: {e}"
        print(error_message)
        return None, error_message
    except IOError as e:
        error_message = f"파일 저장 중 오류가 발생했습니다: {e}"
        print(error_message)
        return None, error_message

@app.get("/", response_class=HTMLResponse)
def home():
    """
    기본 홈 페이지. 간단한 사용 안내를 제공합니다.
    """
    return """
    <h1>OpenDART 기업개황정보 다운로더. '/download-corp-code' 로 요청하세요.</h1>
    <h2>1. /download-corp-code</h2>
    <h2>2. get dividend data</h2>
    """

@app.get("/download-corp-code")
def trigger_download():
    """
    OpenDART 기업개황정보 ZIP 파일 다운로드를 트리거하는 엔드포인트.
    """
    save_dir = "downloads"
    file_path, error = download_corp_code_zip_internal(save_dir)

    if error:
        raise HTTPException(status_code=500, detail={"status": "error", "message": error})
    else:
        return {"status": "success", "message": f"ZIP 파일이 서버에 성공적으로 다운로드되었습니다: {file_path}"}

if __name__ == '__main__':
    # FastAPI 애플리케이션을 Uvicorn으로 실행합니다.
    # host='0.0.0.0'은 모든 네트워크 인터페이스에서 접속을 허용합니다.
    # port=8000은 FastAPI의 기본 포트입니다.
    uvicorn.run(app, host='0.0.0.0', port=8000)
