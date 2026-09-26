# KIS Semiconductor Scanner

한국투자증권 Open API로 국내 반도체 소재·부품·장비 분석용 **원데이터 레이어**를 자동 수집하는 프로젝트입니다.

중요: 이 저장소는 A / B-D / B-W / B-X를 자동으로 결정하는 모델이 아닙니다. KIS는 가격·거래량·거래대금·수급·공매도·대차 등 객관 데이터 공급을 담당하고, 최종 모델 판단은 ChatGPT에서 리비전·실적·수주·CAPEX·고객투자·신규제품 자료와 결합해 수행합니다.

## 유니버스 원칙

- 유니버스 개수는 특정 숫자로 고정하지 않습니다.
- 기존 core seed는 시작점/앵커일 뿐이며 전체 후보군의 상한이 아닙니다.
- 매번 0부터 6개 묶음 전체를 훑고 새 후보를 계속 추가합니다.
- `universe.csv`에는 core seed와 추가 발굴 후보를 함께 저장합니다.
- 기존 TOP10이나 보유종목은 새 점수 계산의 입력값으로 사용하지 않습니다.
- 전체 계산이 끝난 뒤에만 직전 순위와 비교합니다.

6개 묶음:

1. 전공정 장비
2. 후공정·패키징
3. 테스트·검사·인터페이스
4. 공정부품·소모품
5. 소재·케미컬
6. 기판·PCB

## KIS에서 자동 수집하는 데이터

등록 유니버스 전체에 대해 다음을 수집/계산합니다.

- 현재가, 등락률, 시가·고가·저가
- 거래량, 전일 거래량, 전일비 거래량 배수
- 20일 평균 거래량, 20일 평균 대비 배수
- 거래대금 원필드
- 전일 거래대금, 20일 평균 거래대금
- 전일비 거래대금 배수, 20일 평균 대비 거래대금 배수
- 상장주식수, 추정 시가총액
- 가중평균가×거래량 기반 거래대금 추정치와 시총대비 거래대금 비율
- KIS 제공 거래량 회전율
- 종가의 당일 고가·저가 범위 내 위치, 윗꼬리
- 5일/20일 수익률
- 외국인·기관 당일/5일/20일 순매수 수량
- 외국인·기관 당일/5일 순매수 대금 원필드
- 외국인·기관 연속 순매수 일수
- 프로그램매매 당일 순매수 수량
- 공매도 당일 비중/수량/대금, 5일·20일 누적
- 대차 당일 증감, 5일·20일 증감, 잔고 수량/금액
- PER/PBR/EPS/BPS 등 KIS 기본 밸류 필드

KIS 공식 API 중 `주식현재가 시세`, `주식현재가 시세2`, `국내주식기간별시세`, `종목별 투자자매매동향(일별)`, `국내주식 공매도 일별추이`, `종목별 일별 대차거래추이`를 사용합니다.

## 시장 전체 신규후보 발굴

`market_discovery.py`는 KRX 전체 보통주를 대상으로 KIS 순위 API를 별도 조회합니다.

- 거래량 증가율 상위
- 거래회전율 상위
- 거래대금 상위
- 거래대금 회전율 상위
- 신규 후보 시총 3,000억원 미만 기본 제외

처음 보는 종목은 `pending_review`로 저장하며 자동으로 반도체 TOP10에 넣지 않습니다. ChatGPT가 웹/공시/리포트로 실제 반도체 소부장 여부, 흑자 여부, 사업 비중 등을 확인한 뒤 편입합니다.

## 15:40 → 장마감 재검증

장마감 실행 시 `compare_snapshots.py`가 같은 거래일의 `latest_1540.csv`와 `latest_close.csv`를 비교합니다.

자동 비교 항목:

- 가격 유지율
- 15:40 이후 거래량 유입
- 15:40 이후 거래대금 유입
- 종가 위치 변화
- 윗꼬리 변화
- 20일 평균 대비 거래량/거래대금 신호 변화
- 외인·기관·프로그램 수급 변화
- `maintained / neutral / failed` 보조 플래그

이 플래그는 B-D 점수를 자동 결정하지 않습니다. 최종 판단용 참고 데이터입니다.

## 생성 파일

15:40:

- `data/latest_1540.csv`
- `data/latest_1540_status.json`
- `data/latest_1540_market_discovery.csv`
- `data/latest_1540_review_queue.csv`

장마감:

- `data/latest_close.csv`
- `data/latest_close_status.json`
- `data/latest_close_market_discovery.csv`
- `data/latest_close_review_queue.csv`
- `data/latest_close_vs_1540.csv`
- `data/latest_close_vs_1540_status.json`

`status.json`에는 `core_coverage_ok`와 `full_field_coverage_ok`가 따로 저장됩니다. **'전체 스캔 완료'라는 표현은 `full_field_coverage_ok=true`일 때만 사용합니다.** 보조 API가 하나라도 실패하면 숫자를 만들지 않고 `aux_missing`과 `aux_failures`에 기록합니다.

## ChatGPT 장마감 TOP10 흐름

1. KIS 장마감 데이터와 15:40 비교 파일을 읽음
2. 시장 전체 `review_queue`에서 신규 반도체 후보 확인
3. 웹/공시/리포트에서 1W/1M 12M Fwd 매출·OP·EPS 리비전 확인
4. 2026→2027→가능하면 2028 이익 추정 변화 확인
5. 신규 커버리지 / 실제 리비전 / TP만 변경을 분리
6. Beat/Miss·마진, 수주·수주잔고·계약부채, 고객 CAPEX·PO·신규라인·신규고객/제품 확인
7. 가격이 안 오른 우량 후보와 Bottom revision도 별도 확인
8. 그 후 모델 A, B-D, B-W를 독립 계산
9. B-X = B-D 원점수 50% + B-W 원점수 50%
10. 마지막에만 직전 장중/마감 TOP10과 비교

즉 **KIS 데이터가 모델을 대체하는 게 아니라 웹 기반 펀더멘털 분석의 정확도를 높이는 입력 레이어**입니다.

## 최초 1회 설정

GitHub 저장소에서:

`Settings → Secrets and variables → Actions → New repository secret`

- `KIS_APP_KEY`
- `KIS_APP_SECRET`

키 값은 코드나 CSV에 직접 적지 않습니다.

## 실행

`Actions → KIS Semiconductor Scan → Run workflow`

테스트는 `manual`, 자동 실행은 평일 기준:

- `06:40 UTC = 15:40 KST`
- `07:05 UTC = 16:05 KST`

GitHub Actions 예약 실행은 수 분 지연될 수 있습니다.

## 다음 단계

- 프로그램매매의 과거 일별 지속성 추가
- KIS 추정실적/투자의견 API를 보조 레이어로 추가
- DART CAPEX·수주 공시 자동 수집 보조
- ChatGPT가 읽기 쉬운 일별 요약 manifest 생성
