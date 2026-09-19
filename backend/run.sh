#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"

if [ ! -d .venv ]; then
    python3 -m venv .venv
    .venv/bin/pip install -r requirements.txt
fi

if [ ! -f .env ]; then
    cp .env.example .env
    echo ".env 파일을 새로 만들었습니다. ORS_API_KEY를 채워주세요: $(pwd)/.env"
fi

.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8010 --reload
