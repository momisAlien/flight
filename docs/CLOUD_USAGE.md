# 클라우드 이용과 검증 — 2026-10-19

## 접속

정식 접속: https://flight-beta-ten.vercel.app/

위 주소는 HTTP 307로 아래 로그인 보호 검색 화면에 연결됩니다(2026-10-19 응답 확인).

https://flight-git-codex-vercel-ru-a8ac2f-dream30billion-5016s-projects.vercel.app/

Vercel 프로젝트 소유자 계정으로 로그인합니다. PC의 Python 서버나 Chrome을 켤 필요가 없습니다. 휴대폰/다른 컴퓨터의 브라우저에서 위 주소를 열 수 있습니다. 팀 로그인 보호를 끄거나 보호된 Preview를 그대로 공개 Production으로 승격하지 마세요. Production 환경에서는 검색 API가 403으로 거절하도록 구현했습니다. 기존 flight-ruddy-nine.vercel.app은 현재 프로젝트 도메인에 연결돼 있지 않아 사용하지 않습니다. main에는 클라우드 배포 설정을 반영했으며 로컬 실행 소스도 보존했습니다.

## 작동 범위

- 전 세계 공항 목록, 한국어 도시별 복수 공항 선택, 복수 출발 공항.
- 출발일 범위와 박수 또는 정확한 가는 날/오는 날.
- Google/Naver는 별도 Vercel 함수에서 동시에 시작. 각 서비스 내부 조건은 순차 실행.
- 왕복 표시가와 편도 두 장 합계 분리. 도시별 상위 20개. 서로 다른 도시의 편도는 섞지 않음.
- 현지 출발 시각 필터. 알 수 없는 시각 제외. Google 왕복 귀국 시각은 미확인이므로 귀국 시간 필터 적용 시 왕복 후보 제외.
- 조회 진행률, 서비스별 미확인 조건 수, 중단, 미조회 조건 이어서, 최근 1회 검색 복원.
- 마이리얼트립 저장 참고가는 별도 영역. 실시간 왕복 순위에 섞지 않음.

브라우저 탭이 조회 순서를 관리합니다. 탭을 닫으면 다음 조건을 보내지 않습니다. 기록은 해당 브라우저 localStorage에 저장하며 기기 간 동기화하지 않습니다. 중단 시 클라우드의 이미 진행 중인 요청은 최대 90초 내 종료되고, 95초 후 이어서 검색할 수 있습니다. 서버의 상시 백그라운드 작업은 아닙니다.

출발일 범위 최대 31일, 숙박 1~60박, 전체 요청 최대 120개입니다. 초과 시 전체 계획을 거절하며 일부 날짜를 몰래 생략하지 않습니다. 무료 계정 월 한도를 보장하는 전역 할당량 관리 기능은 없습니다. 한도 소진 시 플랫폼에서 실행이 중단될 수 있습니다. 유료 업그레이드/외부 프록시는 사용하지 않았습니다.

## 실제 검증

2026-10-19 18:34~18:35 KST, ICN→NRT, 2027-01-18~2027-01-24, 성인 1명 일반석.

- Google: 왕복/가는 편/오는 편 **3/3조건** 가격 수집. 화면에 왕복 20개+편도 조합 20개 표시. 당시 왕복 최저 관찰 385,950원, 편도 조합 최저 관찰 385,951원. 테스트 이후 가격 변동 가능.
- 왕복은 Google의 ‘최저 ~원’ 표시값. 귀국 세부 항공편과 최종 결제가격은 검증하지 않음. 전체 재고를 수집한 것이 아님.
- 네이버: 가격 서버 5xx 재현. 첫 실패 후 나머지 조건은 보내지 않음. 0/3조건 확인으로 표시. CAPTCHA/차단 우회 없음.
- 마이리얼트립: 최초 실행은 키 미설정. 사용자 Preview 키 등록 후 23:39 KST 재검증에서 도쿄/오사카 **2/2조건 정상 응답**. 당시 저장 참고가 도쿄 599,500원, 오사카 451,000원. 실시간 가격과 구분하여 별도 표시.
- 같은 재검증에서 Google 도쿄/오사카 **2/2조건** 가격 확인 및 도시 탭 전환 확인. 오사카 최저 관찰 왕복 표시가 301,700원. 네이버는 가격 서버 5xx 재현으로 0/2조건.
- 23:45경 일반 브라우저의 네이버 동일 조건 페이지에서는 실제 가격 카드가 표시됨을 확인. 전체 서비스 장애로 단정할 수 없으며 Vercel 환경에서의 실패 원인은 미확정. 자동 수집 실패 상태를 유지하고, 조건별 네이버 원본 링크를 제공. 이 링크를 자동 검색 성공으로 계산하지 않음.
- 새로고침→최근 검색으로 가격 카드 40개 복원 확인. 이 복원은 새 가격 조회가 아님.
- Node 백엔드/비교 테스트 18개, DOM 테스트 3개 통과. 병렬 시작·중단·정리 대기·날짜 유효성·도시 분리·잘못된 편도 조합 방지·시간 필터·인증 거절·키 없이 외부 호출하지 않음·기록 복원을 검사.
- 데스크톱 배포 화면 확인. 모바일 대응 CSS는 구현했으나 브라우저 도구의 390px viewport 설정이 실제 화면에 적용되지 않아 이번 모바일 실측 검증은 미완료.

## 마이리얼트립 설정

Vercel 프로젝트 → Settings → Environment Variables:

- Type: Secret
- Key: `MYREALTRIP_API_KEY` (변수 이름)
- Value: 발급받은 실제 API 키
- Environments: **Preview**

저장 후 Preview를 재배포해야 기존 함수에 적용됩니다. 키를 코드·GitHub·채팅에 넣지 않습니다. 이 연동은 2~6박 저장 캘린더 참고가이며, API에 이틀 범위를 요청한 후 사용자가 지정한 출발일만 남깁니다. 출발일 하나도 조회 가능하며 실제 응답으로 검증했습니다. 사용자가 저장한 소문자 `myrealtrip_api_key` 이름도 지원합니다.

## Windows PowerShell — 코드 설치와 검증

아래 명령은 새 폴더에 클라우드 브랜치를 받습니다. 실제 서비스 사용에는 설치가 필요 없습니다. Node.js 24가 필요합니다.

```powershell
git clone --branch codex/vercel-runtime-check https://github.com/momisAlien/flight.git flight-cloud
cd flight-cloud
npm.cmd ci --prefix deploy/vercel-probe
npm.cmd ci
npm.cmd test --prefix deploy/vercel-probe
node --test tests/test_cloud_ui.cjs
node tools/build_vercel_probe.cjs
py -m http.server 8080 --directory probe-dist --bind 127.0.0.1
```

## macOS/Linux — 코드 설치와 검증

```bash
git clone --branch codex/vercel-runtime-check https://github.com/momisAlien/flight.git flight-cloud
cd flight-cloud
npm ci --prefix deploy/vercel-probe
npm ci
npm test --prefix deploy/vercel-probe
node --test tests/test_cloud_ui.cjs
node tools/build_vercel_probe.cjs
python3 -m http.server 8080 --directory probe-dist --bind 127.0.0.1
```

정적 화면 확인 주소: http://127.0.0.1:8080 . 이 정적 서버는 Vercel API를 실행하지 않으므로 항공권 검색은 위 클라우드 주소에서만 합니다. 정적 서버 종료: Ctrl+C. 클라우드 이용 종료: 검색 중단 후 탭 닫기. macOS/Linux 실제 설치는 이번 Windows 환경에서 검증하지 않았습니다.

기존 로컬 전체 앱은 README의 Python 실행 방법으로 그대로 사용합니다. 로컬 소스·DB·.env는 클라우드 화면과 분리돼 있습니다.
