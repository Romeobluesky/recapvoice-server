# PacketWave 테스트 가이드

이 디렉토리는 PacketWave VoIP 모니터링 시스템의 테스트 코드를 포함합니다.

## 📁 디렉토리 구조

```
tests/
├── __init__.py                 # 테스트 패키지 초기화
├── conftest.py                 # pytest 공통 설정 및 fixture
├── test_sip_simulation.py      # SIP 통화 시뮬레이션 테스트
├── test_websocket.py          # WebSocket 클라이언트 테스트
└── README.md                  # 이 파일
```

## 🚀 테스트 실행 방법

### 1. 의존성 설치

```bash
# pytest 및 관련 패키지 설치
pip install pytest pytest-asyncio websockets

# 또는 requirements.txt가 있는 경우
pip install -r requirements.txt
```

### 2. 모든 테스트 실행

```bash
# 프로젝트 루트 디렉토리에서 실행
pytest

# 또는 더 자세한 출력을 원하는 경우
pytest -v
```

### 3. 특정 테스트 파일 실행

```bash
# SIP 시뮬레이션 테스트만 실행
pytest tests/test_sip_simulation.py

# WebSocket 테스트만 실행
pytest tests/test_websocket.py
```

### 4. 특정 테스트 함수 실행

```bash
# 특정 테스트 함수만 실행
pytest tests/test_sip_simulation.py::TestSIPSimulation::test_mock_packet_creation
```

### 5. 마커를 사용한 테스트 실행

```bash
# 단위 테스트만 실행
pytest -m unit

# WebSocket 관련 테스트만 실행
pytest -m websocket

# SIP 관련 테스트만 실행
pytest -m sip

# 느린 테스트 제외
pytest -m "not slow"
```

## 📋 테스트 종류

### SIP 시뮬레이션 테스트 (`test_sip_simulation.py`)

SIP 패킷 시뮬레이션 및 통화 플로우 테스트를 제공합니다.

**주요 테스트:**
- Mock 패킷 생성 테스트
- Call-ID 생성 테스트  
- 수신 전화 시뮬레이션 테스트
- 발신 전화 시뮬레이션 테스트
- 통화 전환 시뮬레이션 테스트

**실행 예시:**
```bash
# 모든 SIP 테스트 실행
pytest tests/test_sip_simulation.py -v

# 특정 시뮬레이션 테스트
pytest tests/test_sip_simulation.py::TestSIPSimulation::test_simulate_incoming_call -v
```

### WebSocket 테스트 (`test_websocket.py`)

WebSocket 서버와의 통신 테스트를 제공합니다.

**주요 테스트:**
- 클라이언트 초기화 테스트
- 서버 연결 및 등록 테스트
- 메시지 수신 처리 테스트
- 연결 실패 처리 테스트

**실행 예시:**
```bash
# 모든 WebSocket 테스트 실행
pytest tests/test_websocket.py -v

# 독립 모드로 실제 서버 테스트 (서버가 실행 중일 때)
python tests/test_websocket.py standalone 1234 8765
```

## 🔧 설정 파일

### `pytest.ini`
pytest의 기본 설정을 정의합니다:
- 테스트 파일 패턴
- 출력 형식
- 마커 정의
- 경고 필터링

### `conftest.py`
공통 fixture와 설정을 제공합니다:
- `mock_dashboard`: Dashboard 객체 모의
- `test_extensions`: 테스트용 내선번호
- `test_external_numbers`: 테스트용 외부번호
- `websocket_test_uri`: WebSocket 테스트 URI

## 🏃‍♂️ 독립 실행 모드

일부 테스트는 독립 실행 모드를 지원합니다.

### WebSocket 클라이언트 독립 실행
```bash
# 기본 설정으로 실행
python tests/test_websocket.py standalone

# 특정 내선번호와 포트 지정
python tests/test_websocket.py standalone 1001 8765
```

## 📊 테스트 커버리지

테스트 커버리지를 확인하려면:

```bash
# coverage 설치
pip install coverage pytest-cov

# 커버리지와 함께 테스트 실행
pytest --cov=. --cov-report=html

# HTML 리포트 확인 (htmlcov/index.html)
```

## 🐛 디버깅

### 상세한 출력으로 테스트 실행
```bash
pytest -v -s
```

### 특정 테스트에서 중단점 사용
```python
import pdb; pdb.set_trace()  # 테스트 코드에 추가
```

### 실패한 테스트만 재실행
```bash
pytest --lf  # last-failed
```

## ⚠️ 주의사항

1. **서버 의존성**: 일부 통합 테스트는 실제 WebSocket 서버가 실행 중이어야 합니다.

2. **네트워크 테스트**: WebSocket 테스트는 네트워크 연결이 필요할 수 있습니다.

3. **Mock 사용**: 대부분의 테스트는 Mock 객체를 사용하여 외부 의존성을 제거했습니다.

4. **async/await**: WebSocket 테스트는 비동기 코드를 사용하므로 `pytest-asyncio`가 필요합니다.

## 🤝 기여하기

새로운 테스트를 추가할 때:

1. 적절한 파일명 사용 (`test_*.py`)
2. 클래스와 함수에 대한 docstring 작성
3. 적절한 마커 사용 (`@pytest.mark.unit`, `@pytest.mark.integration` 등)
4. Mock 객체를 사용하여 외부 의존성 최소화
5. 테스트 이름은 명확하고 설명적으로 작성

## 📞 문의

테스트 관련 문의사항이 있으면 프로젝트 관리자에게 연락하세요.