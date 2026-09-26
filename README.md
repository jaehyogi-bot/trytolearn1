# KIS Semiconductor Scanner

한국투자증권 Open API로 국내 반도체 소재·부품·장비 유니버스를 자동 수집하는 프로젝트입니다.

## 유니버스 원칙

- 유니버스 개수는 47개로 고정하지 않습니다.
- 기존 47개는 `core_seed=1`인 시작점/앵커일 뿐이며 전체 후보군의 상한이 아닙니다.
- 매번 0부터 6개 묶음 전체를 훑고 새 후보를 계속 추가합니다.
- 현재 `universe.csv`에는 core seed와 추가 발굴 후보를 함께 저장합니다.
- `source=discovered` 후보는 이후 웹/공시/리포트 스캔에서 계속 추가·삭제·재분류할 수 있습니다.
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
- 휴장일 중복 데이터 저장 방지
- GitHub Actions 자동 실행
  - 15:40 KST
  - 16:05 KST
- `data/latest_1540.csv`, `data/latest_close.csv` 생성
- `status JSON`의 `universe_count / success_count / failure_count / coverage_ok`로 현재 가변 유니버스의 수집 성공 여부 확인

## 최초 1회 설정

GitHub 저장소에서 다음 두 Secret을 등록하세요.

`Settings → Secrets and variables → Actions → New repository secret`

- `KIS_APP_KEY`
- `KIS_APP_SECRET`

키 값은 코드나 CSV에 절대 직접 적지 않습니다.

## 첫 테스트

`Actions → KIS Semiconductor Scan → Run workflow`

처음에는 `manual`을 선택해 실행합니다.

정상 실행되면 `data/latest_manual.csv`와 `data/latest_manual_status.json`이 저장됩니다.

## 자동 실행 시각

GitHub cron은 UTC 기준이라 아래처럼 설정되어 있습니다.

- `06:40 UTC = 15:40 KST`
- `07:05 UTC = 16:05 KST`

GitHub Actions 특성상 예약 실행은 수 분 지연될 수 있습니다.

## ChatGPT에서 사용할 파일

장중/이상징후 비교:

- `data/latest_1540.csv`

장마감 최종 분석:

- `data/latest_close.csv`

커버리지 확인:

- `data/latest_1540_status.json`
- `data/latest_close_status.json`

`coverage_ok=false`이면 전체 스캔 완료라고 표현하지 않고 실패 종목을 먼저 확인합니다.

## 다음 단계

1. 유니버스 자동 발굴 레이어 추가: 거래대금·거래량 이상징후와 업종/사업 분류로 신규 후보 생성
2. 거래대금의 20일 평균 및 전일비 배수 추가
3. 시가총액 대비 거래대금/회전율 추가
4. 공매도·대차 데이터 추가
5. 15:40 → 마감 유지율 자동 비교
6. A / B-D / B-W / B-X 점수 계산 레이어 추가
7. DART/뉴스/리포트 기반 Revision·CAPEX·수주 레이어 결합
