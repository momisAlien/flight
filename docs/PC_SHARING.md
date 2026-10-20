# Vercel 접속 + 집 PC 검색

Vercel은 공유 비밀번호를 확인하고 HTTPS 요청을 PC 터널로 전달합니다.
Chrome, 조회 작업, 결과 DB는 PC에서만 실행됩니다. PC 전원·인터넷·로그인 세션을 유지하고 절전을 해제해야 합니다.
공유 화면은 같은 DB와 검색 기록을 함께 사용하는 소규모 공유 공간입니다. 개별 회원의 기록을 분리하는 서비스는 아닙니다.

## 준비

- Python 3.12, Chrome, Node.js 24(개발 테스트용), Git.
- [Cloudflare 공식 cloudflared](https://developers.cloudflare.com/tunnel/downloads/) 설치.
- `flight-github`의 기존 개인 DB를 복사하지 마세요. 공유 서버는 `.shared/shared.db`를 새로 만듭니다.
- 마이리얼트립을 사용하려면 이 프로젝트의 `.env`에 `MYREALTRIP_API_KEY`를 설정하세요. Vercel에 저장된 키가 PC로 자동 복사되지는 않습니다.

## Windows PowerShell

현재 작업 폴더에서 최초 설치:

```powershell
cd "C:\Users\unico\OneDrive\Documents\ChatGPT\NEW 2\flight-github"
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-browser.txt
New-Item -ItemType Directory -Force .tools | Out-Null
Invoke-WebRequest -Uri "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe" -OutFile ".tools/cloudflared.exe"
.\.venv\Scripts\python.exe tools/share_pc.py
```

이미 설치했다면 `cd` 후 마지막 실행 명령만 사용합니다.
이 컴퓨터에서 개발 검증에 사용한 기존 Python 실행 파일로도 실행할 수 있습니다:

```powershell
cd "C:\Users\unico\OneDrive\Documents\ChatGPT\NEW 2\flight-github"
..\flexible-flights\.venv\Scripts\python.exe tools/share_pc.py
```

## macOS/Linux

```bash
git clone --branch codex/pc-share https://github.com/momisAlien/flight.git flight-pc
cd flight-pc
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-browser.txt
```

macOS (Homebrew 사용):

```bash
brew install cloudflared
.venv/bin/python tools/share_pc.py
```

Linux x86-64:

```bash
mkdir -p .tools
curl -fL https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 -o .tools/cloudflared
chmod +x .tools/cloudflared
.venv/bin/python tools/share_pc.py --cloudflared "$PWD/.tools/cloudflared"
```

Linux ARM은 공식 배포 페이지에서 맞는 바이너리를 선택하세요. macOS/Linux 실제 구동은 이번 Windows 검증에 포함되지 않았습니다.

## Vercel 연결 (환경 변수 등록 후 배포)

실행 프로그램은 `.env.vercel-pc`를 만듭니다. 이 파일은 **서버 설정용 비밀 파일**이며 친구에게 보내거나 GitHub에 올리지 않습니다.

Vercel `flight` 프로젝트 → Settings → Environment Variables에서 아래 네 값을 등록합니다.

| 이름 | 역할 |
| --- | --- |
| `FLIGHT_SHARE_USER` | 친구에게 알려줄 공유 로그인 아이디 |
| `FLIGHT_SHARE_PASSWORD` | 친구에게만 알려줄 공유 비밀번호 |
| `FLIGHT_BRIDGE_TOKEN` | Vercel↔PC 내부 인증키. 친구에게 주지 않음 |
| `FLIGHT_PC_URL` | 현재 실행 중인 임시 Cloudflare 주소 |

Production과 PC 공유 브랜치 Preview에 등록합니다. 비밀번호/인증키는 Secret으로 저장합니다.
등록·변경 뒤 재배포가 필요합니다. `deploy/pc/vercel.json`이 이 방식의 배포 설정이며 PC 공유 브랜치에서는 루트 `vercel.json`으로 적용합니다.
기존 cloud 브랜치의 네이버/Google Vercel Chrome 실행 API와 별개입니다.

Preview는 Vercel 계정 보호가 남아 있으므로 친구에게 공유할 최종 주소는 Production
`https://flight-beta-ten.vercel.app/`입니다. **환경 변수 등록·새 코드 Production 배포·접속 확인 후** 공유하세요.

터널을 다시 켜면 주소가 달라질 수 있습니다. 다시 생성된 파일에서 `FLIGHT_PC_URL`을 업데이트하고 Vercel을 재배포하세요.
아이디/비밀번호/내부키는 `.shared/credentials.json`에 유지됩니다.
Quick Tunnel은 테스트·개발용이며 서비스 가동 보장은 없습니다. 무료 요금제의 사용량 제한도 적용됩니다.

## 동작과 종료

- 로그인 후 검색 시작 요청은 바로 작업 번호를 반환합니다. 실제 검색은 PC에서 계속되므로 Vercel의 요청 시간 제한 동안 Chrome을 붙잡지 않습니다.
- 통합 검색은 한 건씩 FIFO로 실행되며 최대 5건이 대기합니다. 한 검색 안에서는 네이버·Google·마이리얼트립이 병렬 실행됩니다.
- 대기 작업도 취소 가능. PC 재시작 시 실행 중/대기 작업은 중단 상태로 남으며 몰래 다시 실행하지 않습니다.
- 공유 모드에서는 별도의 개별 공급사 검색/상세 조회 시작을 제한해 대기열과 충돌하지 않게 합니다.
- 개인 로컬 앱은 기존 `python -m flightcore.server`, 주소 `http://127.0.0.1:8000` 그대로 사용합니다.
- 공유용 8001 포트와 터널은 내부 인증키 없이는 접속되지 않습니다. 친구는 Vercel 주소를 사용합니다.
- 공유 종료: `share_pc.py`를 실행한 터미널에서 **Ctrl+C**. PC 서버와 터널이 함께 종료됩니다. 친구에게 PC 연결 불가가 표시됩니다.
- 개인 로컬 앱 종료는 해당 터미널에서 별도로 **Ctrl+C**.

## 검증

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_pc_bridge tests.test_combined_jobs
node --test tests/test_pc_relay.mjs
npm ci
npm run test:ui
```

macOS/Linux는 위 Python 실행 경로를 `.venv/bin/python`으로 바꿉니다.
미인증 차단, 원본 서버 인증키, CSRF 유지, 다른 출처 거절, 임의 서버로의 중계 거절,
PC 오프라인 오류, 대기열 순서/취소/재시작 복구를 검사합니다.

### 2026-10-20 PC 연결 검증

- 실제 Quick Tunnel에서 인증키 없는 `/api/config`는 401, 인증된 `/healthz`와 `/api/config`는 200 확인.
- 터널로 통합 검색을 시작하고 집 PC의 기존 Chrome 수집기로 ICN→NRT, 2027-01-18~01-24 왕복을 조회.
- 네이버 1/1, Google 1/1조건 성공. 왕복 관찰 후보 233개. 당시 네이버 최저 관찰 표시가 375,111원, Google 385,814원. 최종 결제금액이나 시장 전체 최저가를 뜻하지 않음.
- 중계 코드→실제 터널→PC→결과 표시를 로컬 통합 검증 화면(8082)에서 확인. 이 주소는 개발 검증용이며 공유 주소가 아님.
- 마이리얼트립은 PC 버전의 하루 출발일 조건 제한으로 이 검증에서 실행하지 않음. 공유 프로젝트의 키도 별도 설정 필요.
- Python 7개, Node 중계 3개, UI 33개 테스트 통과.
- Vercel 환경 변수 등록과 PC 공유 브랜치 실제 배포 접속은 별도 확인 필요. 위 로컬 중계 검증을 Vercel 배포 완료로 간주하지 않음.
