@echo off
cd /d "%~dp0"

if not exist js\config.js (
    copy js\config.example.js js\config.js
    echo js\config.js 파일을 새로 만들었습니다. KAKAO_JS_KEY를 채워주세요: %cd%\js\config.js
    notepad js\config.js
)

python -m http.server 5500
