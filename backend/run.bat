@echo off
cd /d "%~dp0"

if not exist .venv (
    python -m venv .venv
    .venv\Scripts\pip install -r requirements.txt
)

if not exist .env (
    copy .env.example .env
    echo .env 파일을 새로 만들었습니다. ORS_API_KEY를 채워주세요: %cd%\.env
    notepad .env
)

.venv\Scripts\uvicorn app.main:app --host 0.0.0.0 --port 8010 --reload

pause
