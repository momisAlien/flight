# 여정노트 — 유연한 일정 항공권 비교

## Vercel 클라우드 버전 (2026-10-19)

이 브랜치(`codex/vercel-runtime-check`)는 [로그인 보호된 클라우드 검색](https://flight-git-codex-vercel-ru-a8ac2f-dream30billion-5016s-projects.vercel.app/)을 배포합니다. **PC 서버 없이 Google 왕복·편도 실제 조회가 검증됐습니다.** 네이버 가격 서버는 503이며, 마이리얼트립은 Preview 환경 변수 설정 후 검증해야 합니다. 세 서비스 전체 완성을 뜻하지 않습니다.

클라우드의 조건·설치·실행·제한은 [CLOUD_USAGE.md](docs/CLOUD_USAGE.md)를 참고하세요. 아래 설명은 보존된 **로컬 FastAPI 버전**입니다. Production 주소는 아직 이전 실패 배포이며, 위 보호된 주소를 사용하세요. 검색 API는 Production에서 의도적으로 비활성화됩니다.

한국어 개인용 항공권 비교 앱입니다. FastAPI·SQLite·HTML/JavaScript와 일반 Selenium Chrome을 사용합니다.

## 현재 기능

- 전 세계 공항 검색과 복수 출발·도착 공항 선택을 지원합니다. 출발일 범위·박수 또는 가는 날·오는 날을 지정합니다.
- 목적지 도시별 탭에서 왕복 20개와 편도 조합 20개를 각각 비교합니다. 도쿄(NRT/HND), 오사카(KIX/UKB) 등 같은 여행 권역의 공항을 묶습니다.
- 가는 편·오는 편의 현지 출발 시간대를 지정할 수 있습니다. 시간대 밖 또는 시각 미확인 후보는 순위에서 제외하고 건수를 표시합니다.
- 네이버·Google 검색 표시가와 마이리얼트립 **저장 왕복 참고가**를 함께 조회합니다.
- 왕복 상위 20개 / 편도 조합 상위 20개를 나눠 표시합니다. 편도는 네이버·Google 간 교차 조합도 비교합니다.
- 검색 중단, 받은 결과 보존, 최근 검색 기록 복원, 저장 조건으로 새 검색을 지원합니다.
- 할인 조건·출처·관찰 시각을 표시합니다. 수하물·좌석 확인은 비교 대상에서 제외합니다.

## 실행

Python 3.12와 Chrome이 필요합니다. 마이리얼트립을 사용하려면 `.env.example`을 `.env`로 복사하고 `MYREALTRIP_API_KEY`를 서버에 설정하세요. 키 없이도 다른 서비스는 조회할 수 있으며 마이리얼트립은 설정 필요 상태로 표시됩니다.

Windows PowerShell:

```powershell
git clone https://github.com/momisAlien/flight.git
cd flight
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-browser.txt
Copy-Item .env.example .env
# .env에 본인의 키 입력
.\.venv\Scripts\python.exe -m flightcore.server
```

macOS/Linux (해당 OS 실제 구동은 미검증):

```bash
git clone https://github.com/momisAlien/flight.git
cd flight
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-browser.txt
cp .env.example .env
# .env에 본인의 키 입력
.venv/bin/python -m flightcore.server
```

기존 `.env`가 있으면 복사 명령을 생략하세요. 접속은 **http://127.0.0.1:8000**입니다. 종료는 화면에서 통합 검색을 중단한 뒤 서버 터미널에서 **Ctrl+C**를 누릅니다.

## 제한 및 다음 단계

- 현재는 **로컬 실행용**이며 Vercel 배포 설정·배포는 아직 하지 않았습니다.
- 로컬 Chrome 수집기, SQLite 파일, 프로세스 내부 백그라운드 스레드를 사용합니다. 다음 배포 단계에서 웹/API·수집 작업·영구 저장소의 실행 위치를 검토해야 합니다.
- 로그인·CAPTCHA·접근 제한을 우회하지 않습니다. Bright Data와 Travelpayouts는 사용하지 않습니다.
- 현재 로드된 카드의 가격을 비교하므로 전체 시장 최저가나 결제 직전 가격을 보장하지 않습니다. 직항 필터는 통합 가격 순위에 적용되지 않습니다. 시간대 필터는 수집된 카드에 적용하며, 시각이 확인되지 않은 항공편은 제외합니다.
- 마이리얼트립은 2~6박, 출발일 범위 2일 이상에서 저장 왕복 참고가를 조회합니다. 하루 출발일 지정은 현재 연동에서 지원하지 않습니다. 시각 정보가 없어 시간대 필터 지정 시 순위에서 제외됩니다.
- Google 일부 조건 실패가 남아 있습니다. [검증 기록](docs/VALIDATION.md)을 참고하세요.

## 테스트

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m unittest discover -s tests
```

UI 테스트는 호환되는 최신 Node.js에서 `npm ci` 후 `npm run test:ui`를 실행합니다. `tools/`의 실조회 도구는 외부 요청을 발생시키며, 일부 재생·패키징 도구는 로컬에 보관된 검증 산출물이 필요합니다. 개인 DB·키·원시 가격 덤프·스크린샷은 저장소에 포함하지 않았습니다.

## 최근 검증 (2026-10-17)

도시별 상위 20개, 출발 시간대, 통합 검색 Python 테스트 15개와 UI 테스트 32개 통과. 저장된 검색 결과로 1440px·390px 화면과 도쿄/오사카 탭 전환을 검증했습니다. 이번 변경 검증에서 새로운 외부 항공권 검색은 실행하지 않았습니다.
