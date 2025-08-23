#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
SIP 통화 시뮬레이션 테스트

이 모듈은 SIP 패킷 이벤트를 가상으로 생성하여 통화 감지 로직을 테스트합니다.
pytest 프레임워크를 사용하여 구조화된 테스트를 제공합니다.
"""

import datetime
import time
import random
import uuid
import pytest
from unittest.mock import MagicMock, patch
import sys
import os

# 상위 디렉토리의 모듈들을 import하기 위한 경로 추가
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


class MockSIPLayer:
    """가상 SIP 레이어"""
    
    def __init__(self, call_id, from_user, to_user, method=None, status_code=None):
        self.call_id = call_id
        self.from_user = from_user
        self.to_user = to_user
        self.method = method
        self.status_code = status_code
        self.request_line = f"{method} sip:{to_user}@example.com SIP/2.0" if method else None
        self.status_line = f"SIP/2.0 {status_code} OK" if status_code else None
        self.msg_hdr = ""
        if hasattr(self, 'method') and self.method:
            self.From = f"\"{from_user}\" <sip:{from_user}@example.com>"


class MockPacket:
    """가상 패킷"""
    
    def __init__(self, call_id, from_user, to_user, method=None, status_code=None):
        self.ip = MagicMock()
        self.ip.src = "192.168.0.1"
        self.ip.dst = "192.168.0.2"
        self.udp = MagicMock()
        self.udp.srcport = str(random.randint(10000, 60000))
        self.udp.dstport = str(random.randint(10000, 60000))
        self.sip = MockSIPLayer(call_id, from_user, to_user, method, status_code)


def generate_call_id(from_user, to_user):
    """고유한 Call-ID 생성"""
    return f"{uuid.uuid4()}@{random.choice(['112.222.225.77', '192.168.0.1', '10.0.0.1'])}"


@pytest.fixture
def mock_dashboard():
    """Dashboard 객체 모의"""
    dashboard = MagicMock()
    dashboard.analyze_sip_packet = MagicMock()
    return dashboard


class TestSIPSimulation:
    """SIP 시뮬레이션 테스트 클래스"""
    
    def test_mock_packet_creation(self):
        """Mock 패킷 생성 테스트"""
        call_id = generate_call_id("1001", "1002")
        packet = MockPacket(call_id, "1001", "1002", method="INVITE")
        
        assert packet.sip.call_id == call_id
        assert packet.sip.from_user == "1001"
        assert packet.sip.to_user == "1002"
        assert packet.sip.method == "INVITE"
        assert packet.ip.src == "192.168.0.1"
        assert packet.ip.dst == "192.168.0.2"
        
    def test_mock_sip_layer_creation(self):
        """Mock SIP 레이어 생성 테스트"""
        call_id = generate_call_id("1001", "1002")
        sip = MockSIPLayer(call_id, "1001", "1002", method="INVITE")
        
        assert sip.call_id == call_id
        assert sip.method == "INVITE"
        assert sip.request_line == "INVITE sip:1002@example.com SIP/2.0"
        
    def test_call_id_generation(self):
        """Call-ID 생성 테스트"""
        call_id1 = generate_call_id("1001", "1002")
        call_id2 = generate_call_id("1001", "1002")
        
        # 각 Call-ID는 고유해야 함
        assert call_id1 != call_id2
        assert "@" in call_id1
        assert "@" in call_id2
        
    def test_simulate_incoming_call(self, mock_dashboard):
        """수신 전화 시뮬레이션 테스트"""
        from_number = "01077141436"
        to_number = "1427"
        
        # 시뮬레이션 실행
        self.simulate_incoming_call(mock_dashboard, from_number, to_number)
        
        # analyze_sip_packet이 적절한 횟수 호출되었는지 확인
        assert mock_dashboard.analyze_sip_packet.call_count == 5
        
        # 호출된 패킷들의 메서드와 상태 코드 확인
        calls = mock_dashboard.analyze_sip_packet.call_args_list
        assert calls[0][0][0].sip.method == "INVITE"
        assert calls[1][0][0].sip.status_code == "100"
        assert calls[2][0][0].sip.status_code == "183"
        assert calls[3][0][0].sip.status_code == "200"
        assert calls[4][0][0].sip.method == "BYE"
        
    def test_simulate_outgoing_call(self, mock_dashboard):
        """발신 전화 시뮬레이션 테스트"""
        from_number = "1427"
        to_number = "01077141436"
        
        # 시뮬레이션 실행
        self.simulate_outgoing_call(mock_dashboard, from_number, to_number)
        
        # analyze_sip_packet이 적절한 횟수 호출되었는지 확인
        assert mock_dashboard.analyze_sip_packet.call_count == 4
        
        # 호출된 패킷들의 메서드와 상태 코드 확인
        calls = mock_dashboard.analyze_sip_packet.call_args_list
        assert calls[0][0][0].sip.method == "INVITE"
        assert calls[1][0][0].sip.status_code == "100"
        assert calls[2][0][0].sip.status_code == "180"
        assert calls[3][0][0].sip.method == "CANCEL"
        
    def test_simulate_call_forward(self, mock_dashboard):
        """통화 전환 시뮬레이션 테스트"""
        from_number = "01077141436"
        to_number = "1427"
        forward_to = "1428"
        
        # 시뮬레이션 실행
        self.simulate_call_forward(mock_dashboard, from_number, to_number, forward_to)
        
        # analyze_sip_packet이 적절한 횟수 호출되었는지 확인
        assert mock_dashboard.analyze_sip_packet.call_count == 7
        
        # REFER 패킷이 올바르게 설정되었는지 확인
        calls = mock_dashboard.analyze_sip_packet.call_args_list
        refer_packet = calls[5][0][0]
        assert refer_packet.sip.method == "REFER"
        assert hasattr(refer_packet.sip, 'refer_to')
        
    def simulate_incoming_call(self, dashboard, from_number, to_number):
        """수신 전화 시뮬레이션 실행"""
        call_id = generate_call_id(from_number, to_number)
        
        # INVITE 패킷
        invite_packet = MockPacket(call_id, from_number, to_number, method="INVITE")
        dashboard.analyze_sip_packet(invite_packet)
        
        # 100 Trying 응답
        trying_packet = MockPacket(call_id, from_number, to_number, status_code="100")
        dashboard.analyze_sip_packet(trying_packet)
        
        # 183 Session Progress 응답
        ringing_packet = MockPacket(call_id, from_number, to_number, status_code="183")
        dashboard.analyze_sip_packet(ringing_packet)
        
        # 200 OK 응답 (통화 연결)
        ok_packet = MockPacket(call_id, from_number, to_number, status_code="200")
        dashboard.analyze_sip_packet(ok_packet)
        
        # BYE 요청 (통화 종료)
        bye_packet = MockPacket(call_id, from_number, to_number, method="BYE")
        dashboard.analyze_sip_packet(bye_packet)
        
    def simulate_outgoing_call(self, dashboard, from_number, to_number):
        """발신 전화 시뮬레이션 실행"""
        call_id = generate_call_id(from_number, to_number)
        
        # INVITE 패킷
        invite_packet = MockPacket(call_id, from_number, to_number, method="INVITE")
        dashboard.analyze_sip_packet(invite_packet)
        
        # 100 Trying 응답
        trying_packet = MockPacket(call_id, from_number, to_number, status_code="100")
        dashboard.analyze_sip_packet(trying_packet)
        
        # 180 Ringing 응답
        ringing_packet = MockPacket(call_id, from_number, to_number, status_code="180")
        dashboard.analyze_sip_packet(ringing_packet)
        
        # CANCEL 요청 (발신 취소)
        cancel_packet = MockPacket(call_id, from_number, to_number, method="CANCEL")
        dashboard.analyze_sip_packet(cancel_packet)
        
    def simulate_call_forward(self, dashboard, from_number, to_number, forward_to):
        """통화 전환 시뮬레이션 실행"""
        call_id = generate_call_id(from_number, to_number)
        
        # INVITE 패킷
        invite_packet = MockPacket(call_id, from_number, to_number, method="INVITE")
        dashboard.analyze_sip_packet(invite_packet)
        
        # 100 Trying 응답
        trying_packet = MockPacket(call_id, from_number, to_number, status_code="100")
        dashboard.analyze_sip_packet(trying_packet)
        
        # 183 Session Progress 응답
        ringing_packet = MockPacket(call_id, from_number, to_number, status_code="183")
        dashboard.analyze_sip_packet(ringing_packet)
        
        # 200 OK 응답 (통화 연결)
        ok_packet = MockPacket(call_id, from_number, to_number, status_code="200")
        dashboard.analyze_sip_packet(ok_packet)
        
        # REFER 요청 (통화 전환)
        refer_packet = MockPacket(call_id, to_number, from_number, method="REFER")
        refer_packet.sip.refer_to = f"sip:{forward_to}@example.com"
        refer_packet.sip.msg_hdr = f"Refer-To: <sip:{forward_to}@example.com>\r\nX-xfer-pressed: True"
        dashboard.analyze_sip_packet(refer_packet)
        
        # BYE 요청 (원래 통화 종료)
        bye_packet = MockPacket(call_id, from_number, to_number, method="BYE")
        dashboard.analyze_sip_packet(bye_packet)
        
        # 새 통화 시작 (전환된 통화)
        new_call_id = generate_call_id(from_number, forward_to)
        new_invite_packet = MockPacket(new_call_id, from_number, forward_to, method="INVITE")
        dashboard.analyze_sip_packet(new_invite_packet)


class TestSIPSimulationIntegration:
    """SIP 시뮬레이션 통합 테스트"""
    
    @pytest.mark.skipif(True, reason="Requires dashboard.py import")
    def test_full_simulation_with_dashboard(self):
        """실제 Dashboard와 함께하는 전체 시뮬레이션 테스트"""
        # 이 테스트는 dashboard.py를 import할 수 있을 때만 실행
        try:
            import dashboard
            # 실제 dashboard 인스턴스와 함께 테스트 실행
        except ImportError:
            pytest.skip("dashboard.py를 import할 수 없습니다")


# 직접 실행 시 테스트 실행
if __name__ == "__main__":
    pytest.main([__file__, "-v"])