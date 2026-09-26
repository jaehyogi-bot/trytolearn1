# KIS Semiconductor Scanner

한국투자증권 Open API로 국내 반도체 소재·부품·장비 47개 필수 유니버스를 자동 수집하는 프로젝트입니다.

## 현재 구현

- 47개 필수 종목 유니버스
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
- 47/47 성공 여부를 status JSON으로 별도 저장

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

1. 거래대금의 20일 평균 및 전일비 배수 추가
2. 시가총액 대비 거래대금/회전율 추가
3. 공매도·대차 데이터 추가
4. 15:40 → 마감 유지율 자동 비교
5. A / B-D / B-W / B-X 점수 계산 레이어 추가
6. DART/뉴스/리포트 기반 Revision·CAPEX·수주 레이어 결합
