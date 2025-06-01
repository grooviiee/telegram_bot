// App.js (간단한 예시)
import React, { useState } from 'react';

function App() {
  const [apiKey, setApiKey] = useState('');
  const [message, setMessage] = useState('');

  const handleDownload = async () => {
    if (!apiKey) {
      setMessage('API 키를 입력해주세요.');
      return;
    }
    setMessage('다운로드 요청 중...');
    try {
      // Flask 백엔드 URL (Flask 서버가 실행 중인 주소)
      const response = await fetch(`http://localhost:5000/download-corp-code?api_key=${apiKey}`);
      const data = await response.json();

      if (response.ok) {
        setMessage(`성공: ${data.message}`);
        // 필요하다면 여기서 다운로드된 파일에 대한 추가 작업을 수행할 수 있습니다.
      } else {
        setMessage(`오류: ${data.message}`);
      }
    } catch (error) {
      setMessage(`네트워크 오류: ${error.message}`);
    }
  };

  return (
    <div style={{ padding: '20px', fontFamily: 'sans-serif' }}>
      <h1>OpenDART 기업개황정보 다운로더</h1>
      <p>아래에 OpenDART API 키를 입력하고 다운로드 버튼을 클릭하세요.</p>
      <input
        type="text"
        placeholder="OpenDART API 키"
        value={apiKey}
        onChange={(e) => setApiKey(e.target.value)}
        style={{ padding: '8px', marginRight: '10px', borderRadius: '4px', border: '1px solid #ccc' }}
      />
      <button
        onClick={handleDownload}
        style={{ padding: '8px 15px', borderRadius: '4px', border: 'none', backgroundColor: '#007bff', color: 'white', cursor: 'pointer' }}
      >
        ZIP 파일 다운로드 요청
      </button>
      {message && <p style={{ marginTop: '15px', color: message.startsWith('오류') || message.startsWith('네트워크') ? 'red' : 'green' }}>{message}</p>}
    </div>
  );
}

export default App;