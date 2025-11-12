# 🧠 AI 주식 자동매매 시스템

## 개요
Python 3.x 및 PyQt5 기반의 AI 자동매매 플랫폼으로, Kiwoom OpenAPI+ REST/COM 인터페이스를 통해 멀티타임프레임 캔들 데이터(틱~6시간), 수급 지표(외인, 기관, 대차잔고), 시장지수를 수집·학습하여 종목을 선별하고 강건한 매수/매도/홀딩 결정을 수행합니다. 감독학습으로 종목을 추천하고, 강화학습으로 포지션 전환을 제어하며, 실계좌와 모의계좌를 안전 스위치로 전환할 수 있습니다.

## 주요 기능
- 멀티타임프레임 시세·수급 병합 파이프라인과 특성 엔지니어링 자동화
- 감독학습 기반 종목 랭킹 모델(피처 중요도/설명력 로그 포함)
- PPO/SAC 등 RL 정책으로 포지션 제어, 과매매 방지 리스크 펜스
- PyQt5 트레이딩 데스크: 실시간 체결 현황, 포트폴리오, 모델 신뢰도 시각화
- 모의/실계좌 토글, 최대 손실·호가 호가단위 제한 등 안전 매매 가드
- 전략 백테스트·워크플로 리플레이, 알림 웹훅/텔레그램 통합

## 시스템 아키텍처
```
데이터 소스 (시세/수급/지수)
        │
        ▼
ETL & 피처 엔진 ──► 시계열 피처 스토어 ──► 감독학습 모델 서비스
        │                                       │
        └────────────► 강화학습 환경 ──► 정책 네트워크
                                            │
PyQt5 GUI ──► 전략 오케스트레이터 ──► 주문 게이트웨이(Kiwoom REST)
                                            │
                               실계좌 / 모의계좌 안전 스위치
```
- **데이터 계층**: `src/data_pipeline`이 멀티타임프레임 캔들·수급 데이터를 수집해 Parquet/InfluxDB 등에 적재.
- **AI 계층**: `src/models/supervised`가 종목 점수화를, `src/models/rl`이 포지션 정책을 담당.
- **전략/주문 계층**: `src/core/strategy`는 추천·정책을 융합, `src/api/kiwoom_client`가 REST 호출, `src/risk`가 리스크 규칙을 검증.
- **UI & 서비스 계층**: `src/ui` PyQt5 대시보드가 실행 상태·알림을 제공, `src/services`는 스케줄러/백테스트/로깅을 관리.

## 설치 방법
1. Python 3.10 이상 및 Kiwoom OpenAPI+ 사전 설치.
2. 저장소 클론 후 가상환경 구성:
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # Windows PowerShell: .\.venv\Scripts\Activate.ps1
   pip install --upgrade pip
   pip install -r requirements.txt
   ```
3. 환경 변수 설정(`.env`):
   ```bash
   KIWOOM_APP_KEY=...
   KIWOOM_APP_SECRET=...
   ACCOUNT_NO=1234567890
   MODE=paper   # paper 또는 live
   ```
4. PyQt5 실행을 위해 OS 별 Qt 런타임(Windows VC++ 재배포 등) 준비.

## 프로젝트 폴더 구조
```
MLStock/
├── README.md
├── requirements.txt
├── data/
│   ├── raw/                  # 원천 캔들·수급 CSV/Parquet
│   └── processed/            # 정제·스케일링 결과
├── notebooks/                # EDA, 피처 검증, 전략 실험
├── logs/
│   ├── app/                  # 실행 로그
│   └── trades/               # 체결·리스크 이벤트
├── saved_models/
│   ├── supervised/           # 종목 선택 모델 체크포인트
│   └── rl/                   # 정책 네트워크
├── configs/
│   ├── data_sources.yaml
│   ├── features.yaml
│   └── risk.yaml
├── src/
│   ├── api/
│   │   └── kiwoom_client.py  # REST/COM 래퍼, 재시도 로직
│   ├── core/
│   │   ├── scheduler.py      # 스케줄링, 장중 이벤트 핸들링
│   │   └── strategy.py       # 종목 추천 + RL 정책 융합
│   ├── data_pipeline/
│   │   ├── collectors/       # 멀티타임프레임 수집기
│   │   └── feature_store.py  # 피처 캐싱, 레이크 관리
│   ├── models/
│   │   ├── supervised/       # LightGBM/TabNet 등
│   │   └── rl/               # PPO/SAC 정책, 환경 정의
│   ├── risk/
│   │   └── guardrails.py     # 손실 한도, 체결 속도 제한
│   ├── services/
│   │   ├── backtester.py
│   │   └── notifier.py       # Slack/Telegram/Webhook
│   ├── ui/
│   │   ├── main_window.py    # PyQt5 진입점
│   │   └── components/       # 차트, 포지션 패널
│   └── main.py               # 애플리케이션 부트스트랩
└── tests/
    ├── unit/
    └── integration/
```

## 사용법 (버튼별 기능 설명 포함)
1. **데이터 동기화**
   ```bash
   python -m src.data_pipeline.sync --timeframes tick,1m,15m,6h
   ```
   - 수급/지수 소스는 `configs/data_sources.yaml`에 정의.
2. **감독학습 모델 학습 & 평가**
   ```bash
   python -m src.models.supervised.train --config configs/features.yaml
   python -m src.models.supervised.evaluate --metric f1 --holdout 2024Q4
   ```
   - SHAP/Permutation 중요도 리포트가 `reports/supervised/`에 생성.
3. **강화학습 정책 학습**
   ```bash
   python -m src.models.rl.train --algo ppo --env trading-v1 --episodes 5000
   python -m src.models.rl.backtest --policy saved_models/rl/latest.pt
   ```
   - 환경은 멀티계좌·거래비용·슬리피지 파라미터를 포함.
4. **PyQt5 GUI 실행**
   ```bash
   python -m src.main --mode paper
   ```
   - `--mode live` 사용 시 이중 확인 팝업과 OTP 검증이 요구됨.

**GUI 버튼 안내**
- `데이터 동기화`: 최신 캔들·수급 데이터 다운로드 후 캐시 갱신.
- `모델 업데이트`: 최신 학습 파일을 로드하고 성능 리포트를 갱신.
- `백테스트 실행`: 선택한 기간·전략 세트로 워크플로 리플레이.
- `자동매매 시작/정지`: 전략 오케스트레이터 시작/중지, 모의/실계좌 상태 표시.
- `리스크 한도 설정`: 일손실·종목별 비중 한도 입력, 변경 즉시 리스크 엔진으로 전파.
- `로그 & 알림`: 체결·경고·오류 로그를 필터링, 알림 채널 토글.

**안전 메커니즘**
- 모의/실계좌 전환 시 다중 확인, OTP, 일시적 쿨다운.
- 주문 전 `risk.guardrails` 검증(최대 체결 수, 슬리피지, 과매매 쿨다운).
- 실시간 PnL 드로우다운 감지 시 정책 강제 중단, 해제는 관리자 암호 필요.

## 개발 단계 및 로드맵
1. **Phase 0 – 인프라 준비**
   - 데이터 소스 커넥터, 기본 DB/스토리지, 로깅/알림 프레임 구성.
2. **Phase 1 – 데이터 & 특성 엔진**
   - 멀티타임프레임 수집 안정화, 이상치/결측 처리, 피처 설정 YAML화.
3. **Phase 2 – 모델링**
   - 감독학습 파이프라인(MLOps, 자동 튜닝), RL 환경/알고리즘 실험, 모델 레지스트리 구축.
4. **Phase 3 – 백테스트 & 시뮬레이션**
   - 이벤트 드리븐 백테스터, 거래비용·슬리피지 모델링, 리포트 자동화.
5. **Phase 4 – GUI & 오케스트레이션**
   - PyQt5 대시보드, 전략 스케줄러, 실시간 모니터링 패널.
6. **Phase 5 – 안전한 실계좌 전환**
   - 이중 인증, 리스크 한도, 모니터링 대시보드, 장애 자동 복구 시나리오.
7. **Phase 6 – 고도화**
   - 온라인 학습, AutoML 특성 탐색, 다중 브로커 지원, 클라우드 배포(쿠버네티스/서버리스).

각 단계마다 테스트(단위·통합·회귀)와 문서화를 병행하여 유지보수성과 신뢰도를 확보합니다.
