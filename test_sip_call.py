#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
SIP 통화 시뮬레이션 테스트 스크립트
SIP 패킷 이벤트를 가상으로 생성하여 통화 감지 로직을 테스트합니다.
"""

import datetime
import time
import random
import threading
import uuid
from unittest.mock import MagicMock

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

def simulate_incoming_call(dashboard, from_number, to_number):
    """수신 전화 시뮬레이션"""
    call_id = generate_call_id(from_number, to_number)
    
    print(f"\n=== 수신 전화 시뮬레이션 시작 ===")
    print(f"발신: {from_number}")
    print(f"수신: {to_number}")
    print(f"Call-ID: {call_id}")
    
    # INVITE 패킷
    invite_packet = MockPacket(call_id, from_number, to_number, method="INVITE")
    print("1. INVITE 패킷 전송")
    dashboard.analyze_sip_packet(invite_packet)
    time.sleep(1)
    
    # 100 Trying 응답
    trying_packet = MockPacket(call_id, from_number, to_number, status_code="100")
    print("2. 100 Trying 응답 수신")
    dashboard.analyze_sip_packet(trying_packet)
    time.sleep(0.5)
    
    # 183 Session Progress 응답
    ringing_packet = MockPacket(call_id, from_number, to_number, status_code="183")
    print("3. 183 Session Progress 응답 수신")
    dashboard.analyze_sip_packet(ringing_packet)
    time.sleep(2)
    
    # 200 OK 응답 (통화 연결)
    ok_packet = MockPacket(call_id, from_number, to_number, status_code="200")
    print("4. 200 OK 응답 수신 (통화 연결)")
    dashboard.analyze_sip_packet(ok_packet)
    time.sleep(3)
    
    # 통화 중 상태 (가상의 RTP 패킷 교환)
    print("5. 통화 중 (RTP 패킷 교환)")
    time.sleep(5)
    
    # BYE 요청 (통화 종료)
    bye_packet = MockPacket(call_id, from_number, to_number, method="BYE")
    print("6. BYE 요청 전송 (통화 종료)")
    dashboard.analyze_sip_packet(bye_packet)
    
    print("=== 수신 전화 시뮬레이션 종료 ===\n")

def simulate_outgoing_call(dashboard, from_number, to_number):
    """발신 전화 시뮬레이션"""
    call_id = generate_call_id(from_number, to_number)
    
    print(f"\n=== 발신 전화 시뮬레이션 시작 ===")
    print(f"발신: {from_number}")
    print(f"수신: {to_number}")
    print(f"Call-ID: {call_id}")
    
    # INVITE 패킷
    invite_packet = MockPacket(call_id, from_number, to_number, method="INVITE")
    print("1. INVITE 패킷 전송")
    dashboard.analyze_sip_packet(invite_packet)
    time.sleep(1)
    
    # 100 Trying 응답
    trying_packet = MockPacket(call_id, from_number, to_number, status_code="100")
    print("2. 100 Trying 응답 수신")
    dashboard.analyze_sip_packet(trying_packet)
    time.sleep(0.5)
    
    # 180 Ringing 응답
    ringing_packet = MockPacket(call_id, from_number, to_number, status_code="180")
    print("3. 180 Ringing 응답 수신")
    dashboard.analyze_sip_packet(ringing_packet)
    time.sleep(2)
    
    # 응답 없음 - CANCEL 전송 (발신 취소)
    cancel_packet = MockPacket(call_id, from_number, to_number, method="CANCEL")
    print("4. CANCEL 요청 전송 (발신 취소)")
    dashboard.analyze_sip_packet(cancel_packet)
    
    print("=== 발신 전화 시뮬레이션 종료 ===\n")

def simulate_call_forward(dashboard, from_number, to_number, forward_to):
    """통화 전환 시뮬레이션"""
    call_id = generate_call_id(from_number, to_number)
    
    print(f"\n=== 통화 전환 시뮬레이션 시작 ===")
    print(f"발신: {from_number}")
    print(f"수신: {to_number}")
    print(f"전환: {forward_to}")
    print(f"Call-ID: {call_id}")
    
    # INVITE 패킷
    invite_packet = MockPacket(call_id, from_number, to_number, method="INVITE")
    print("1. INVITE 패킷 전송")
    dashboard.analyze_sip_packet(invite_packet)
    time.sleep(1)
    
    # 100 Trying 응답
    trying_packet = MockPacket(call_id, from_number, to_number, status_code="100")
    print("2. 100 Trying 응답 수신")
    dashboard.analyze_sip_packet(trying_packet)
    time.sleep(0.5)
    
    # 183 Session Progress 응답
    ringing_packet = MockPacket(call_id, from_number, to_number, status_code="183")
    print("3. 183 Session Progress 응답 수신")
    dashboard.analyze_sip_packet(ringing_packet)
    time.sleep(2)
    
    # 200 OK 응답 (통화 연결)
    ok_packet = MockPacket(call_id, from_number, to_number, status_code="200")
    print("4. 200 OK 응답 수신 (통화 연결)")
    dashboard.analyze_sip_packet(ok_packet)
    time.sleep(3)
    
    # 통화 중 상태 (가상의 RTP 패킷 교환)
    print("5. 통화 중 (RTP 패킷 교환)")
    time.sleep(2)
    
    # REFER 요청 (통화 전환)
    refer_packet = MockPacket(call_id, to_number, from_number, method="REFER")
    refer_packet.sip.refer_to = f"sip:{forward_to}@example.com"
    refer_packet.sip.msg_hdr = f"Refer-To: <sip:{forward_to}@example.com>\r\nX-xfer-pressed: True"
    print(f"6. REFER 요청 전송 (통화 전환 -> {forward_to})")
    dashboard.analyze_sip_packet(refer_packet)
    time.sleep(1)
    
    # BYE 요청 (원래 통화 종료)
    bye_packet = MockPacket(call_id, from_number, to_number, method="BYE")
    print("7. BYE 요청 전송 (원래 통화 종료)")
    dashboard.analyze_sip_packet(bye_packet)
    
    # 새 통화 시작 (전환된 통화)
    new_call_id = generate_call_id(from_number, forward_to)
    print(f"8. 새 통화 시작 (전환된 통화, Call-ID: {new_call_id})")
    new_invite_packet = MockPacket(new_call_id, from_number, forward_to, method="INVITE")
    dashboard.analyze_sip_packet(new_invite_packet)
    
    print("=== 통화 전환 시뮬레이션 종료 ===\n")

def simulate_sip_call(dashboard):
    """SIP 통화 시뮬레이션 실행"""
    print("\n" + "="*50)
    print("SIP 통화 시뮬레이션 시작")
    print("="*50)
    
    # 내선번호와 외부 번호 정의
    extensions = ["1427", "1001", "1234", "2001"]
    external_numbers = ["01077141436", "01012345678", "0212345678"]
    
    # 시뮬레이션 1: 내선번호로 수신 전화
    ext = random.choice(extensions)
    ext_num = random.choice(external_numbers)
    print(f"\n시뮬레이션 1: 내선번호 {ext}로 수신 전화 (발신: {ext_num})")
    simulate_incoming_call(dashboard, ext_num, ext)
    time.sleep(2)
    
    # 시뮬레이션 2: 내선번호에서 발신 전화 (응답 없음)
    ext = random.choice(extensions)
    ext_num = random.choice(external_numbers)
    print(f"\n시뮬레이션 2: 내선번호 {ext}에서 발신 전화 (수신: {ext_num}, 응답 없음)")
    simulate_outgoing_call(dashboard, ext, ext_num)
    time.sleep(2)
    
    # 시뮬레이션 3: 내선번호로 수신 후 다른 내선으로 전환
    ext1 = extensions[0]
    ext2 = extensions[1]
    ext_num = random.choice(external_numbers)
    print(f"\n시뮬레이션 3: 내선번호 {ext1}로 수신 후 내선 {ext2}로 전환 (발신: {ext_num})")
    simulate_call_forward(dashboard, ext_num, ext1, ext2)
    
    print("\n" + "="*50)
    print("SIP 통화 시뮬레이션 완료")
    print("="*50)

if __name__ == "__main__":
    print("이 스크립트는 직접 실행할 수 없습니다.")
    print("대시보드 애플리케이션의 --test 옵션을 사용하여 실행하세요.")
    print("예: python dashboard.py --test") 