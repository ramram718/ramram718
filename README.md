# 대한항공 보너스 좌석 조회 프로토타입 (ICN ↔ CDG, 프레스티지)

Playwright로 [보너스 좌석 조회 페이지](https://www.koreanair.com/booking/book-and-manage/award-seat-availability)를
열어 조회 시 오가는 XHR/Fetch JSON을 저장하고, 그 안에서 날짜별 좌석 유무 필드를 찾아
가는 날/오는 날 가능 날짜와 7~14박 왕복 조합을 출력합니다.

## 확인된 API (실제 HAR 캡처 기준)
- `POST https://www.koreanair.com/api/hmp/bonusSeatView/bonusSeatView` — **로그인 필요**
- 요청: `{"arrivalAirport":"CDG","departureAirport":"ICN","departureDate":"20270801"}` → 해당 월 전체, 한 방향
- 응답: `flightList[].departureDate` × `flightDetailList[]{flightNumber, departureTime, availableSeat, bookingClass, frontBookingClass}`
- 좌석 등급 `frontBookingClass` (페이지 범례): `E` 일반석 보너스, `R` 프리미엄석 보너스, `G` 프리미엄석 좌석승급, `P` **프레스티지석 보너스**, `U` 프레스티지석 좌석승급, `F` 일등석 보너스/좌석승급
- 상세: `kal_award/bonusseat.py`

> ⚠️ (이전 메모) 아래 자동 캡처 방식은 클라우드 환경에서 검증되지 않았습니다. 개발용 클라우드 환경에서는 사이트(Akamai)가
> `Access Denied`를 반환해 접속하지 못했습니다. 아래 1~3단계를 **본인 PC(가정용 IP, 실제 브라우저 창)**에서
> 실행해 실제 필드를 확인해야 합니다. 테스트(`tests/`)는 임의로 만든 가상 응답으로 로직만 검증합니다.

## Windows에서 가장 쉬운 사용법
- 처음 한 번: `setup.bat` 더블클릭 (패키지와 브라우저 설치)
- 매번: `run.bat` 더블클릭 → (git으로 받은 폴더면 최신 버전 자동 업데이트) → 조회 → 결과 출력
- 다른 달: 명령창에서 `run.bat --out-month 2027-09 --in-month 2027-10`

## 화면 조작 방식 (권장) ★
```bash
pip install -r requirements.txt
python -m playwright install chromium
python -m kal_award ui                                   # ICN↔CDG, 2027-09, 프레스티지석 보너스
python -m kal_award ui --out-month 2027-09 --in-month 2027-10
```
1. 로딩("잠시만 기다려 주세요")이 끝나 **보너스 좌석 조회** 제목이 보일 때까지 대기
2. From 출발지 → `ICN` → "서울/인천, 대한민국 ICN" / To 도착지 → `CDG` → "파리/샤를 드 골, 프랑스 CDG"
3. 탑승월 → 2027 그룹의 9월(가는 달), 9월(오는 달) → 선택 → 조회 (`kds-button_1`이라 force 클릭)
4. 페이지가 보내는 `bonusSeatView` 응답 2건(가는 편/오는 편)을 가로채 `captures/<시각>-ui/`에 저장
5. 응답 구조, **프레스티지석 보너스(P)** 가능 날짜(좌석승급 U 제외), 7~14박 왕복 조합 출력
6. 화면의 날짜 버튼 라벨("…프레스티지석 보너스…")과 API 결과를 대조해 일치 여부 출력

로그인이 안 되어 있으면 안내가 나옵니다. 브라우저 창에서 로그인한 뒤 터미널에서 Enter → 자동 재조회.
로그인은 `.browser_profile/`에 저장되어 다음부터는 생략됩니다.

## 월별 API 자동 조회 (대안)
```bash
pip install -r requirements.txt
python -m playwright install chromium
python -m kal_award auto
```
- 브라우저 창이 열립니다. **처음 한 번만 SKYPASS 로그인** → 이후 자동으로 가는 편·오는 편을 월별로 조회
  (2027-08부터 예약 가능 마지막 날까지, 요청 간격 2초)하고 결과를 바로 출력합니다.
- 로그인은 `.browser_profile/`에 남아서 다음 실행부터는 명령 한 줄이면 끝납니다.
- 옵션: `--origin ICN --dest CDG --from 2027-08-01 --min-stay 7 --max-stay 14 --cabin P --delay 2`

### 자동화 브라우저가 막힐 때: 콘솔 스니펫 (평소 쓰는 크롬)
1. 평소 크롬으로 보너스 좌석 조회 페이지에 로그인
2. F12 → **Console** 탭 → `kal_award/console_snippet.js` 내용 전체를 붙여넣고 Enter
   (크롬이 붙여넣기를 막으면 `allow pasting` 입력 후 Enter, 다시 붙여넣기)
3. 안내대로 페이지의 [조회]를 한 번 누르면 나머지 달은 자동 조회 → `kal_bonus_*.json` 다운로드
4. `python -m kal_award import kal_bonus_....json` → 결과 출력

## 설치
```bash
pip install -r requirements.txt
python -m playwright install chromium
```

## 1. 캡처 (브라우저 창이 열림, 기본 headless=False)
```bash
python -m kal_award capture
```
- 프로필은 `.browser_profile/`에 저장됩니다. 처음 한 번 SKYPASS에 직접 로그인하면 다음 실행부터 재사용됩니다.
- 출발/도착/등급 자동 입력을 시도하지만, 사이트 DOM을 확인하지 못한 상태라 실패할 수 있습니다. 그 경우 창에서 직접 입력하세요.
- **ICN→CDG, 프레스티지, 성인 1명**으로 조회한 뒤 달력을 **2027년 8월부터 조회 가능한 마지막 달까지**
  넘기고(가는 편·오는 편 모두), 터미널에서 Enter를 누릅니다.
- 응답은 `captures/<시각>/NNN.json`에 `{url, method, request_post_data, response_json}` 형태로 저장됩니다.

## 1-B. (자동화 브라우저에서 조회 결과가 안 나올 때) 평소 쓰는 크롬에서 HAR 저장
자동화된 브라우저에서는 사이트가 조회 결과를 보여 주지 않을 수 있습니다. 그럴 때는:
1. 평소 쓰는 크롬으로 보너스 좌석 조회 페이지를 열고 로그인
2. **F12** → **Network** 탭 → 왼쪽 위 ⦸(Clear) 클릭, **Preserve log** 체크
3. ICN→CDG, 프레스티지, 성인 1명으로 조회하고 달력을 2027년 8월 ~ 마지막 달까지 넘기기 (가는 편·오는 편)
4. Network 목록 아무 줄에서 오른쪽 클릭 → **Save all as HAR with content** → 프로그램 폴더에 `kal.har`로 저장
5. `python -m kal_award har kal.har`

HAR 파일에는 로그인 쿠키 등 개인정보가 들어 있으니 다른 사람에게 공유하지 마세요.

## 2. 구조 분석
```bash
python -m kal_award analyze            # 폴더 생략 시 가장 최근 캡처
```
날짜 값이 많은 응답 순으로 엔드포인트, 요청 본문, 응답 구조 트리를 출력하고,
`날짜 키 / 가용성 키 / 등급 키 / 출발·도착 키`를 자동 추정해 근거(값 분포, 샘플 레코드)와 함께 보여 줍니다.

## 3. 날짜 출력 + 왕복 매칭
```bash
python -m kal_award dates --from 2027-08-01 --min-stay 7 --max-stay 14
```
자동 추정이 맞는지 확인했으면 `field_map.example.json`을 복사해 실제 키 이름으로 고친 뒤
`--map field_map.json`으로 고정하세요. 그러면 추정 없이 그 필드만 읽습니다.

## 테스트
```bash
python -m pytest -q
```
