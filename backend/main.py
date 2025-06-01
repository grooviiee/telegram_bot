import requests
import json
from datetime import datetime

def fetch_dividend_data(crtfc_key: str, corp_code: str, report_code: str) -> list:
    """
    DART API에서 지정된 기업의 연간 배당금 데이터를 가져옵니다.

    Args:
        crtfc_key (str): DART API 인증 키.
        corp_code (str): 기업 코드 (예: 삼성SDI는 '000660').
        report_code (str): 보고서 코드 (예: 사업보고서는 '11011').

    Returns:
        list: 각 연도별 배당금 정보를 담은 딕셔너리 리스트.
              각 딕셔너리는 'year' (datetime 객체)와 'dividend_amount' (float)를 포함합니다.
    """
    fetched_data = []
    current_year = datetime.now().year

    # 최근 5년간의 연간 배당 데이터를 가져오기 위해 각 연도별로 API 호출
    for i in range(5):
        bsns_year = current_year - i
        api_url = (
            f'https://opendart.fss.or.kr/api/alotMatter.json?'
            f'crtfc_key={crtfc_key}&corp_code={corp_code}&bsns_year={bsns_year}&reprt_code={report_code}'
        )

        try:
            response = requests.get(api_url)
            response.raise_for_status()  # HTTP 오류 발생 시 예외 발생

            response_body = response.json()

            if response_body.get('status') == '000':
                list_data = response_body.get('list', [])
                # '주당 현금배당금(원)' 항목을 찾고 '보통주' 기준 데이터 추출
                dividend_entry = next(
                    (
                        item for item in list_data
                        if item.get('se') == '주당 현금배당금(원)' and item.get('stock_knd') == '보통주'
                    ),
                    None,
                )

                if dividend_entry:
                    # 'thstrm' (당기) 배당금 파싱
                    thstrm_dividend_str = dividend_entry.get('thstrm', '0').replace(',', '')
                    dividend = float(thstrm_dividend_str) if thstrm_dividend_str and thstrm_dividend_str != '-' else 0.0

                    # 'stlm_dt' (결산일)을 연도로 사용
                    stlm_dt_str = dividend_entry.get('stlm_dt')
                    if stlm_dt_str:
                        dividend_year = datetime.strptime(stlm_dt_str, '%Y-%m-%d')
                        fetched_data.append({'year': dividend_year, 'dividend_amount': dividend})
                else:
                    print(f'Warning: Dividend data for year {bsns_year} not found or malformed.')
            else:
                print(f"API Error for {bsns_year}: {response_body.get('message', 'Unknown error')}")
        except requests.exceptions.RequestException as e:
            print(f'HTTP Error for {bsns_year}: {e}')
        except json.JSONDecodeError as e:
            print(f'JSON Decode Error for {bsns_year}: {e}')
        except Exception as e:
            print(f'An unexpected error occurred for {bsns_year}: {e}')

    # 연도별로 정렬 (오름차순)
    fetched_data.sort(key=lambda x: x['year'])

    return fetched_data

if __name__ == '__main__':

    save_path = '/Users/grooviiee2/Workspace/telegram_bot/aaa.zip'


    # 사용 예시: 실제 API 키와 삼성SDI 기업 코드를 사용하세요.
    api_key = 'aaf2ed404abd73c00ab27a6ba80476131e6f9a73'  # 실제 API 키로 대체하세요.
    samsung_sdi_corp_code = '000660'
    annual_report_code = '11011'

    api_url = (
        f'https://opendart.fss.or.kr/api/corpCode.xml?crtfc_key={api_key}'
    )
    try:
        # GET 요청을 보내고 스트리밍 방식으로 응답을 받습니다.
        # stream=True를 사용하여 큰 파일을 효율적으로 처리합니다.
        response = requests.get(api_url, stream=True)
        response.raise_for_status()  # HTTP 오류가 발생하면 예외를 발생시킵니다.

        # 응답이 성공적이면 (상태 코드 200) 파일을 저장합니다.
        if response.status_code == 200:
            with open(save_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    # 응답 내용을 청크 단위로 읽어 파일에 씁니다.
                    f.write(chunk)
            print(f"ZIP 파일이 성공적으로 다운로드되어 '{save_path}'에 저장되었습니다.")
            print("이제 이 ZIP 파일의 압축을 해제하여 내부의 XML 파일을 확인할 수 있습니다.")
        else:
            print(f"파일 다운로드에 실패했습니다. 상태 코드: {response.status_code}")
            print(f"응답 내용: {response.text}")

    except requests.exceptions.RequestException as e:
        print(f"요청 중 오류가 발생했습니다: {e}")
    except IOError as e:
        print(f"파일 저장 중 오류가 발생했습니다: {e}")

    print("Fetching dividend data for Samsung SDI...")
    dividend_data = fetch_dividend_data(api_key, samsung_sdi_corp_code, annual_report_code)

    if dividend_data:
        print("\nFetched Dividend Data:")
        for data in dividend_data:
            print(f"Year: {data['year'].year}, Dividend Amount: {data['dividend_amount']}")
    else:
        print("No dividend data fetched or an error occurred.")

