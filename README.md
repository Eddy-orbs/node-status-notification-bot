# node-status-notification-bot

Python 기반 텔레그램 모니터링 앱입니다. 유저가 등록한 Ethereum 주소의 `Boyar` 상태를 주기적으로 확인하고, 상태가 `Green -> Yellow`로 변경될 때만 알림을 보냅니다.

## 기능 요약

- `/start`: 봇 소개 및 주소 등록 방법 안내
- `/set address <ethereum_address>`:
  - 주소 유효성 검사 (`0x` + 40 hex)
  - 내부 저장/JSON 조회용 주소는 `0x` 제거 + lowercase normalize
  - 주소 저장 + 모니터링 활성화
  - 현재 상태를 baseline(`last_status`)으로 저장
  - 등록 직후 즉시 알림 없음
- `/stop`: 해당 유저 모니터링 비활성화
- `/status`: 현재 등록 주소, 모니터링 ON/OFF, 마지막 상태 조회
- `/resume`: 기존 등록 주소 기준으로 모니터링 재시작 + baseline 재설정
- `/monitorAll on|off`:
  - `on`: AllRegisteredNodes 전체 manager 감시 (single 설정은 DB에 보존, manager가 우선)
  - `off`: manager 종료 후 저장된 single 주소가 있으면 JSON에 존재할 때만 single 감시 재개
- 주기 작업:
  - 기본 1800초(30분) 간격으로 실행
  - `STATUS_JSON_URL`을 주기마다 1회만 fetch
  - 모든 활성 유저에 대해 주소별 상태 판독
  - `Green -> Yellow`에서만 텔레그램 알림
  - 그 외 변화는 알림 없이 `last_status` 갱신
  - 경로 누락/주소 누락은 `UNKNOWN`으로 안전 처리

## 프로젝트 구조

- `app/main.py`: 앱 부트스트랩, polling 실행, 스케줄러 등록
- `app/bot_handlers.py`: `/start`, `/set`, `/stop`, `/status`, `/resume`, `/monitorAll` 핸들러
- `app/monitor_service.py`: JSON fetch + 상태 판독 + 알림 규칙
- `app/storage.py`: SQLite 스키마/쿼리
- `app/config.py`: `.env` 로딩 및 설정
- `app/models.py`: 상수/검증 유틸
- `main.py`: 엔트리포인트
- `Dockerfile`
- `docker-compose.yml`
- `.env.example`

## .env 설정

1. 예시 파일 복사:

```bash
cp .env.example .env
```

2. `.env` 수정:

```env
TELEGRAM_BOT_TOKEN=your_real_telegram_bot_token
STATUS_JSON_URL=https://status.orbs.network/json
CHECK_INTERVAL_SECONDS=1800
SQLITE_DB_PATH=/app/data/app.db
LOG_LEVEL=INFO
```

## 로컬 개발 실행 방법

> 로컬과 서버 모두 Docker Compose 기준으로 동일하게 실행하는 것을 권장합니다.

```bash
docker compose up --build
```

백그라운드 실행:

```bash
docker compose up -d --build
```

로그 확인:

```bash
docker compose logs -f app
```

중지:

```bash
docker compose down
```

## Docker Compose 실행 방식

- `app` 컨테이너 1개
- `.env`를 `env_file`로 주입
- 호스트 `./data`를 컨테이너 `/app/data`에 마운트
- `restart: unless-stopped`
- 로그는 stdout/stderr 출력

## 데이터 저장 위치

- SQLite 파일 경로(컨테이너 내부): `/app/data/app.db`
- 실제 저장 위치(호스트): `./data/app.db`
- 컨테이너 재생성 후에도 `./data`가 유지되므로 DB가 보존됩니다.

## 서버(Ubuntu) 배포 절차 예시

```bash
# 1) 서버에 프로젝트 배치
# git clone 또는 rsync

# 2) 환경변수 파일 준비
cp .env.example .env
# .env에서 TELEGRAM_BOT_TOKEN 수정

# 3) 실행
docker compose up -d --build

# 4) 상태/로그 점검
docker compose ps
docker compose logs -f app
```

## 자주 쓰는 명령어

```bash
# 컨테이너 재빌드/재시작
docker compose up -d --build

# 앱 로그 실시간 확인
docker compose logs -f app

# 앱 중지
docker compose down

# 앱 재시작
docker compose restart app
```
