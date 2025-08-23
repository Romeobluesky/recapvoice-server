# -*- coding: utf-8 -*-
"""
pytest 설정 파일

이 파일은 PacketWave 테스트를 위한 pytest 설정과 공통 fixture를 제공합니다.
"""

import pytest
import sys
import os
from unittest.mock import MagicMock

# 상위 디렉토리의 모듈들을 import하기 위한 경로 추가
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


@pytest.fixture(scope="session")
def test_extensions():
    """테스트용 내선번호 리스트"""
    return ["1427", "1428", "1001", "1234", "2001"]


@pytest.fixture(scope="session")
def test_external_numbers():
    """테스트용 외부 번호 리스트"""
    return ["01077141436", "01012345678", "0212345678", "0419312641"]


@pytest.fixture(scope="session")
def test_server_ips():
    """테스트용 서버 IP 리스트"""
    return ["112.222.225.77", "192.168.0.54", "192.168.0.55", "192.168.0.1", "10.0.0.1"]


@pytest.fixture
def mock_dashboard():
    """Dashboard 객체 모의 (함수 스코프)"""
    dashboard = MagicMock()
    dashboard.analyze_sip_packet = MagicMock()
    dashboard.log_error = MagicMock()
    dashboard.log_to_sip_console = MagicMock()
    return dashboard


@pytest.fixture(scope="session")
def websocket_test_uri():
    """WebSocket 테스트용 URI"""
    return "ws://localhost:8765"


@pytest.fixture
def temp_directory(tmp_path):
    """임시 디렉토리 fixture"""
    return tmp_path


# pytest 마커 정의
def pytest_configure(config):
    """pytest 설정"""
    config.addinivalue_line("markers", "slow: 느린 테스트로 표시")
    config.addinivalue_line("markers", "integration: 통합 테스트로 표시")
    config.addinivalue_line("markers", "unit: 단위 테스트로 표시")
    config.addinivalue_line("markers", "websocket: WebSocket 테스트로 표시")
    config.addinivalue_line("markers", "sip: SIP 관련 테스트로 표시")


# 테스트 수집 설정
def pytest_collection_modifyitems(config, items):
    """테스트 아이템 수정"""
    for item in items:
        # asyncio 관련 테스트에 대한 설정
        if "asyncio" in item.fixturenames:
            item.add_marker(pytest.mark.asyncio)
            
        # 파일명 기반 마커 추가
        if "websocket" in item.nodeid:
            item.add_marker(pytest.mark.websocket)
        if "sip" in item.nodeid:
            item.add_marker(pytest.mark.sip)


# 테스트 실행 전 설정
@pytest.fixture(autouse=True)
def setup_test_environment():
    """각 테스트 실행 전 환경 설정"""
    # 테스트 시작 전 실행할 코드
    yield
    # 테스트 종료 후 실행할 코드 (cleanup)
    pass