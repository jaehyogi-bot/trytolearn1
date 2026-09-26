# KIS Semiconductor Scanner

한국투자증권 Open API로 국내 반도체 소재·부품·장비 유니버스를 자동 수집하는 프로젝트입니다.

## 유니버스 원칙

- 유니버스 개수는 특정 숫자로 고정하지 않습니다.
- 기존 core seed는 시작점/앵커일 뿐이며 전체 후보군의 상한이 아닙니다.
- 매번 0부터 6개 묶음 전체를 훑고 새 후보를 계속 추가합니다.
- `universe.csv`에는 core seed와 추가 발굴 후보를 함께 저장합니다.
- 최종 TOP10 계산에는 기존 TOP10이나 보유종목을 입력값으로 사용하지 않습니다.
- 전체 후보군의 시세/수급 계산이 끝난 뒤에만 직전 순위와 비교합니다.

6개 묶음:

1. 전공정 장비
2. 후공정·패키징
3. 테스트·검사·인터페이스
4. 공정부품·소모품
5. 소재·케미컬
6. 기판·PCB

## 현재 구현

### 1) 등록 반도체 후보군 전체 수집

- 고정 숫자가 아닌 가변형 `universe.csv`
- 주식현재가 시세2
- 최근 30거래일 일봉
- 종목별 투자자매매동향(일별)
- 자동 계산
  - 등락률
  - 거래량 / 전일 거래량 배수
  - 20일 평균 거래량 / 20일 평균 대비 배수
  - 5일 / 20일 수익률
  - 당일 고가 대비 종가 위치
  - 윗꼬리 비율
  - 외국인·기관 당일 / 5일 / 20일 순매수
  - 외국인·기관 연속 순매수 일수

### 2) 시장 전체 신규후보 발굴

`market_discovery.py`가 KRX 전체 보통주를 대상으로 KIS 순위 API를 별도로 조회합니다.

- 거래량 증가율 상위
- 거래회전율 상위
- 거래대금 상위
- 거래대금 회전율 상위
- 시가총액 약 3,000억원 미만 신규후보는 기본 제외
- 기존 `universe.csv`와 겹치면 `registered_semiconductor`
- 처음 보는 종목은 `pending_review`

중요: 시장 순위에 잡힌 처음 보는 종목을 이름만 보고 반도체주로 자동 판정하지 않습니다. `pending_review`는 ChatGPT/웹/공시로 실제 반도체 소부장 여부, 적자 여부, 사업부 비중 등을 확인한 뒤 유니버스에 편입합니다. 따라서 신규후보 발굴은 자동화하지만 잘못된 업종 분류가 TOP10 점수에 바로 들어가는 것은 막습니다.

KIS 거래량순위 API의 정렬 기준은 `FID_BLNG_CLS_CODE`로 구분하며, 현재 1=거래증가율, 2=평균거래회전율, 3=거래금액순, 4=평균거래금액회전율을 사용합니다.

## 생성 파일

장중 15:40:

- `data/latest_1540.csv` — 등록 반도체 후보 전체 상세 데이터
- `data/latest_1540_market_discovery.csv` — 시장 전체 이상징후 후보
- `data/latest_1540_review_queue.csv` — 아직 반도체 여부를 검토해야 하는 신규 후보
- `data/latest_1540_discovery_status.json`

장마감:

- `data/latest_close.csv`
- `data/latest_close_market_discovery.csv`
- `data/latest_close_review_queue.csv`
- `data/latest_close_discovery_status.json`

수집 커버리지:

- `data/latest_1540_status.json`
- `data/latest_close_status.json`

`coverage_ok=false`이면 등록 유니버스 전체 스캔 완료라고 표현하지 않습니다. 또한 `market_discovery`는 KIS의 시장 순위 API 기반 신규발굴이므로, 이것만으로 KRX의 모든 반도체 관련 기업을 완전 분류했다고 표현하지 않습니다.

## 최초 1회 설정

GitHub 저장소에서 다음 두 Secret을 등록하세요.

`Settings → Secrets and variables → Actions → New repository secret`

- `KIS_APP_KEY`
- `KIS_APP_SECRET`

키 값은 코드나 CSV에 직접 적지 않습니다.

## 첫 테스트

`Actions → KIS Semiconductor Scan → Run workflow`

처음에는 `manual`을 선택해 실행합니다.

정상 실행되면 기존 상세 CSV와 함께 다음 파일도 생성됩니다.

- `data/latest_manual_market_discovery.csv`
- `data/latest_manual_review_queue.csv`
- `data/latest_manual_discovery_status.json`

## 자동 실행 시각

GitHub cron은 UTC 기준입니다.

- `06:40 UTC = 15:40 KST`
- `07:05 UTC = 16:05 KST`

GitHub Actions 예약 실행은 수 분 지연될 수 있습니다.

## 설정

`scanner_config.json`

- `min_market_cap_won`: 신규후보 최소 시가총액
- `discovery_sort_codes`: 시장 신규후보 발굴에 사용할 KIS 순위 기준
- `required_groups`: 최종 반도체 스캔에서 유지할 6개 묶음

## 다음 단계

1. `review_queue` 신규 종목의 반도체 업종/적자 여부 자동 보조분류
2. 거래대금의 20일 평균 및 전일비 배수 추가
3. 시가총액 대비 거래대금/회전율 추가
4. 공매도·대차 데이터 추가
5. 15:40 → 마감 유지율 자동 비교
6. A / B-D / B-W / B-X 점수 계산 레이어 추가
7. DART/뉴스/리포트 기반 Revision·CAPEX·수주 레이어 결합
