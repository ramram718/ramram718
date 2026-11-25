# 대한항공 보너스 좌석 조회 프로토타입 (ICN ↔ CDG, 프레스티지)

Playwright로 [보너스 좌석 조회 페이지](https://www.koreanair.com/booking/book-and-manage/award-seat-availability)를
열어 조회 시 오가는 XHR/Fetch JSON을 저장하고, 그 안에서 날짜별 좌석 유무 필드를 찾아
가는 날/오는 날 가능 날짜와 7~14박 왕복 조합을 출력합니다.

> ⚠️ 실제 응답 스키마는 아직 검증되지 않았습니다. 개발용 클라우드 환경에서는 사이트(Akamai)가
> `Access Denied`를 반환해 접속하지 못했습니다. 아래 1~3단계를 **본인 PC(가정용 IP, 실제 브라우저 창)**에서
> 실행해 실제 필드를 확인해야 합니다. 테스트(`tests/`)는 임의로 만든 가상 응답으로 로직만 검증합니다.

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

## 2. 구조 분석
```bash
python -m kal_award analyze captures/<시각>
```
날짜 값이 많은 응답 순으로 엔드포인트, 요청 본문, 응답 구조 트리를 출력하고,
`날짜 키 / 가용성 키 / 등급 키 / 출발·도착 키`를 자동 추정해 근거(값 분포, 샘플 레코드)와 함께 보여 줍니다.

## 3. 날짜 출력 + 왕복 매칭
```bash
python -m kal_award dates captures/<시각> --from 2027-08-01 --min-stay 7 --max-stay 14
```
자동 추정이 맞는지 확인했으면 `field_map.example.json`을 복사해 실제 키 이름으로 고친 뒤
`--map field_map.json`으로 고정하세요. 그러면 추정 없이 그 필드만 읽습니다.

## 테스트
```bash
python -m pytest -q
```
