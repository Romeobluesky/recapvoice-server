# SIP RTP 프로세스 로직 분석 보고서

## 개요
backup 폴더의 5개 pcapng 파일(1.pcapng ~ 5.pcapng)을 분석하여 SIP RTP 프로세스의 로직 차이점을 정리한 문서입니다.

## 분석 대상 파일
- **1.pcapng**: 2025-03-19 13:20:32 ~ 13:21:14 (약 42초)
- **2.pcapng**: 2025-03-19 13:23:02 ~ 13:23:53 (약 51초)
- **3.pcapng**: 2025-03-19 13:24:42 ~ 13:25:10 (약 28초)
- **4.pcapng**: 2025-03-19 13:28:52 ~ 13:29:26 (약 34초)
- **5.pcapng**: 2025-03-19 13:31:22 ~ 13:34:21 (약 3분)

## 공통 네트워크 구성
- **SIP 서버**: 112.222.225.104
- **클라이언트 A**: 192.168.0.54
- **클라이언트 B**: 192.168.0.55

## SIP 프로세스 로직 차이점 분석

### 1. 일반 통화 시나리오 (@backup\1.pcapng)
```
시퀀스: REGISTER → INVITE → 200 OK → ACK → BYE
특징: 단순한 양자간 통화
```

**로직 흐름**:
- 두 클라이언트 모두 REGISTER (401 → 200 OK 인증)
- 서버에서 192.168.0.55로 INVITE
- 정상 통화 설정 (180 Ringing → 200 OK → ACK)
- 192.168.0.55가 BYE로 통화 종료

### 2. 돌려주기 시나리오 (@backup\2.pcapng)
```
시퀀스: REGISTER → INVITE → 200 OK → RE-INVITE → REFER → NOTIFY → 새로운 INVITE → BYE
특징: 통화 전송(Transfer) 기능, 고급 SIP 기능 사용 (REFER, NOTIFY)
```

**로직 흐름**:
- 초기 통화 설정 (서버 → 192.168.0.55)
- **RE-INVITE**: 192.168.0.55가 통화 중 재협상
- **REFER**: 192.168.0.55가 통화 전송 요청 (돌려주기)
- **NOTIFY**: 서버가 전송 상태 알림
- **새로운 INVITE**: 서버 → 192.168.0.54 (전송된 통화)
- 다중 BYE로 모든 세션 정리

### 3. 당겨받기 시나리오 (@backup\3.pcapng)
```
시퀀스: REGISTER → INVITE → 407 인증 → 새로운 INVITE → CANCEL → 487 종료
특징: 프록시 인증 및 호출 취소, 다른 단말기에서 통화 가로채기
```

**로직 흐름**:
- 서버에서 192.168.0.55로 INVITE (180 Ringing 응답)
- 192.168.0.54가 별도 INVITE 시도 (당겨받기)
- **407 Proxy Authentication Required**: 프록시 인증 실패
- 인증 후 새로운 INVITE 성공
- **CANCEL**: 서버가 첫 번째 INVITE 취소
- **487 Request Terminated**: 취소된 요청에 대한 응답

#### **당겨받기 특수번호 분석**
- **사용된 특수번호**: `*8` (Call Pickup 기능코드)
- **실제 시나리오**:
  - 원본 통화: `01077141436` → `109Q1427` (192.168.0.55)
  - 당겨받기: `109Q1428` (192.168.0.54) → `INVITE sip:*8@112.222.225.104:5060`
  - 결과: 통화가 192.168.0.54로 전환됨

#### **`*8` 번호의 의미**
- **VoIP 표준 기능코드**: PBX/Centrex 시스템의 Call Pickup 특수번호
- **기술적 구현**: 실제 발신자 번호 대신 시스템 내부 라우팅용 특수코드 사용
- **SIP 헤더 특징**: `X-xfer-pressed: True` (전환 버튼 활성화 표시)

#### **PacketWave 처리 시 고려사항**
**문제점**: 통화 기록 시 발신자가 `*8`로 저장되어 실제 발신자 추적 불가

**해결 방안**:
- **Context 기반 매핑**: RINGING 상태 통화에서 실제 발신자 번호 추출
- **Call-ID 연결**: 원본 통화와 당겨받기 통화 간 연관성 추적
- **실시간 치환**: `*8` 감지 시 진행중인 통화의 실제 발신자로 대체
- **구현 위치**: `dashboard.py`의 `analyze_sip_packet()` 함수에서 처리

### 4. 3자통화 시나리오 (@backup\4.pcapng)
```
시퀀스: REGISTER → INVITE → 200 OK → ACK → RE-INVITE → 새로운 INVITE → 3방향 동시 통화 → BYE
특징: 3자간 동시 통화, 복잡한 다중 세션 관리, Conference Call 구현
```

**로직 흐름**:

#### **Phase 1: 단말기 등록 (13:28:52)**
- 192.168.0.54 (109Q1428) 등록: 401 → 인증 → 200 OK
- 192.168.0.55 (109Q1427) 등록: 401 → 인증 → 200 OK

#### **Phase 2: 초기 2자 통화 설정 (13:28:55 - 13:28:58)**
```
13:28:55.736 - 서버 → 192.168.0.55: INVITE
               From: "01077141436"
               To: sip:109Q1427@192.168.0.55:5060
               Call-ID: 3749d4615995b7dd49e372fb68e7e0175cf17532@112.222.225.77

13:28:55.810 - 192.168.0.55 → 서버: 180 Ringing
13:28:58.638 - 192.168.0.55 → 서버: 200 OK (통화 연결)
13:28:58.642 - 서버 → 192.168.0.55: ACK
```

#### **Phase 3: 통화 중 Hold 상태 전환 (13:29:00)**
```
13:29:00.932 - 192.168.0.55 → 서버: RE-INVITE
               (기존 통화를 Hold 상태로 전환)
13:29:00.936 - 서버: 200 OK
13:29:00.960 - 192.168.0.55: ACK
```

#### **Phase 4: 3번째 참가자 초대 (13:29:08)**
```
13:29:08.152 - 192.168.0.55 → 서버: INVITE sip:1428@112.222.225.104:5060
               From: "07086661427,1427"
               Call-ID: e513679c03fd1e63f526dbef61d0f119@192.168.0.55
               X-xfer-pressed: True

13:29:08.157 - 서버: 407 Proxy Authentication Required
13:29:08.176 - 192.168.0.55: ACK
13:29:08.180 - 192.168.0.55: 재인증된 INVITE
```

#### **Phase 5: 동시 다중 세션 처리 (13:29:08)**
```
13:29:08.186 - 서버: 100 Trying
13:29:08.190 - 서버 → 192.168.0.54: INVITE
               From: "1427"
               Call-ID: 3994c646417274495d9f25853d409d2a51cac25d@112.222.225.77

13:29:08.190 - 서버 → 192.168.0.55: 183 Session Progress
13:29:08.223 - 192.168.0.54: 100 Trying
13:29:08.273 - 192.168.0.54: 180 Ringing
```

#### **Phase 6: 3자통화 완전 연결 (13:29:09)**
```
13:29:09.496 - 192.168.0.54: 200 OK (두 번째 참가자 연결)
13:29:09.500 - 서버: ACK
13:29:09.519 - 서버 → 192.168.0.55: 200 OK (3번째 참가자 연결 완료)
13:29:09.550 - 192.168.0.55: ACK
```

#### **Phase 7: Hold 해제 및 Conference 활성화 (13:29:13)**
```
13:29:13.192 - 192.168.0.55: RE-INVITE (Hold 해제, 3자통화 활성화)
13:29:13.197 - 서버: 200 OK
13:29:13.222 - 192.168.0.55: ACK
```

#### **Phase 8: 3자통화 종료 (13:29:26)**
```
13:29:26.706 - 192.168.0.54: BYE (1428번 종료)
13:29:26.710 - 서버: BYE → 192.168.0.55 (Conference 해제)
13:29:26.938 - 192.168.0.55: BYE (원본 통화 종료)
```

#### **3자통화 핵심 특징**

**다중 Call-ID 관리**:
- **원본 통화**: `3749d4615995b7dd...@112.222.225.77` (01077141436 ↔ 1427)
- **Conference 세션**: `e513679c03fd1e63...@192.168.0.55` (1427 ↔ 1428)
- **Bridge 세션**: `3994c646417274...@112.222.225.77` (1427 ↔ 1428)

**Conference Bridge 구현**:
- 서버가 중앙 Conference Bridge 역할
- Hold/Resume 메커니즘으로 통화 전환
- RE-INVITE를 통한 미디어 경로 재설정

**미디어 경로**:
```
01077141436 ← → Server ← → 192.168.0.55 (1427)
                  ↕
             192.168.0.54 (1428)
```

#### **PacketWave 처리 시 고려사항**

**복잡성**:
- **3개의 독립적인 Call-ID** 동시 관리 필요
- **Hold/Resume** 상태 변화 추적
- **Conference Bridge** 세션 연관성 파악

**녹음 처리 방안**:
- **Multi-Stream Recording**: 3개 미디어 스트림 동시 녹음
- **Conference Mixing**: 3자 음성 믹싱 후 단일 파일 생성
- **Individual Tracks**: 각 참가자별 개별 트랙 생성

**Call-ID 연관 관계 추적**:
```python
# Conference 세션 관리 예시
conference_sessions = {
    "master_call_id": "3749d4615995b7dd...@112.222.225.77",
    "participants": [
        {"call_id": "e513679c03fd1e63...@192.168.0.55", "extension": "1427"},
        {"call_id": "3994c646417274...@112.222.225.77", "extension": "1428"}
    ],
    "status": "active_conference"
}
```

### 5. 순차착신 시나리오 (@backup\5.pcapng)
```
시퀀스: REGISTER → INVITE → 200 OK → 새로운 INVITE → 486 Busy → 통화 전환
특징: 통화 중 상태 및 자동 라우팅, 순차적 착신 처리
```

**로직 흐름**:
- 긴 등록 주기 (3분간)
- 첫 번째 통화 성공 (서버 → 192.168.0.55)
- **486 Busy Here**: 두 번째 INVITE에 대한 통화 중 응답
- **자동 라우팅**: 서버가 192.168.0.54로 순차 재시도
- 순차적 통화 종료

## 주요 로직 차이점 요약

### 1. 인증 메커니즘
- **기본**: 401 Unauthorized 후 재시도
- **고급**: 407 Proxy Authentication Required (프록시 인증)

### 2. 세션 관리
- **단순**: INVITE → ACK → BYE
- **복잡**: RE-INVITE, REFER, NOTIFY를 통한 동적 세션 변경

### 3. 에러 처리
- **180 Ringing**: 정상 호출 대기
- **183 Session Progress**: 세션 협상 진행 중
- **486 Busy Here**: 통화 중 상태
- **487 Request Terminated**: 요청 취소

### 4. 고급 SIP 기능
- **REFER/NOTIFY**: 통화 전송 기능
- **CANCEL**: 진행 중인 INVITE 취소
- **RE-INVITE**: 기존 세션 재협상

### 5. 네트워크 프로토콜 분포
- **파일 1**: UDP 85.25%, TCP 14.75%
- **파일 2**: UDP 79.22%, TCP 20.78%

## 결론

각 pcapng 파일은 서로 다른 SIP 통화 시나리오를 보여줍니다:
1. **일반 통화**: 가장 단순한 P2P 통화
2. **돌려주기**: REFER/NOTIFY를 이용한 통화 전송 기능
3. **당겨받기**: CANCEL을 이용한 통화 가로채기
4. **3자통화**: 복잡한 다자간 세션 관리
5. **순차착신**: Busy 상태 처리 및 자동 순차 라우팅

이러한 분석을 통해 VoIP 시스템의 다양한 통화 시나리오와 SIP 프로토콜의 복잡성을 이해할 수 있습니다.

---
*분석 일시: 2025-08-28*
*도구: Wireshark tshark*
*분석 대상: PacketWave 백업 폴더의 pcapng 파일*

## SIP 패킷 분석 로직 - 간단한 조건문 구조

```python
# SIP 패킷 분석 메인 로직
def analyze_sip_packet_logic(sip_layer, call_id):

    # 1. 당겨받기 감지 (*8 특수번호)
    if (sip_layer.to_user == "*8" and
        hasattr(sip_layer, 'X-xfer-pressed') and
        sip_layer.method == "INVITE"):
        # 당겨받기 시나리오 처리
        # - RINGING 상태 통화에서 실제 발신자 번호 추출
        # - *8을 실제 발신자로 치환
        # - 원본 통화 CANCEL 처리
        handle_call_pickup_scenario(sip_layer, call_id)

    # 2. 3자통화 감지 (다중 Call-ID + Conference 패턴)
    elif (is_conference_invite(sip_layer) and
          has_active_call_session() and
          sip_layer.method == "INVITE" and
          hasattr(sip_layer, 'X-xfer-pressed')):
        # 3자통화 시나리오 처리
        # - 기존 통화 Hold 상태 확인
        # - 새로운 참가자 초대
        # - Conference Bridge 세션 생성
        handle_conference_call_scenario(sip_layer, call_id)

    # 3. 돌려주기 감지 (REFER/NOTIFY 패턴)
    elif (sip_layer.method == "REFER" and
          hasattr(sip_layer, 'refer_to') and
          is_active_call_session(call_id)):
        # 돌려주기 시나리오 처리
        # - REFER 대상 추출
        # - 새로운 INVITE 생성
        # - 기존 세션 정리
        handle_call_transfer_scenario(sip_layer, call_id)

    # 4. 순차착신 감지 (486 Busy + 자동 라우팅)
    elif (sip_layer.status_code == "486" and
          has_alternative_extension() and
          is_sequential_routing_enabled()):
        # 순차착신 시나리오 처리
        # - Busy 상태 확인
        # - 다음 내선으로 자동 라우팅
        # - 순차적 INVITE 시도
        handle_sequential_routing_scenario(sip_layer, call_id)

    # 5. 일반 통화 시작 (단순 INVITE)
    elif (sip_layer.method == "INVITE" and
          is_simple_two_party_call(sip_layer)):
        # 일반 통화 시나리오 처리
        # - 기본 2자 통화
        # - 단순한 INVITE → 200 OK → ACK → BYE
        handle_normal_call_scenario(sip_layer, call_id)

    # 6. 통화 종료 (BYE)
    elif sip_layer.method == "BYE":
        # 통화 종료 처리
        # - 단일 세션 vs Conference 세션 구분
        # - 녹음 파일 완료 처리
        handle_call_termination(sip_layer, call_id)

    # 7. 응답 코드 처리
    elif hasattr(sip_layer, 'status_code'):
        if sip_layer.status_code == "100":
            # Trying - 처리 중
            handle_trying_response(call_id)
        elif sip_layer.status_code == "180":
            # Ringing - 벨소리
            handle_ringing_response(call_id)
        elif sip_layer.status_code == "200":
            # OK - 연결 성공
            handle_ok_response(call_id)
        elif sip_layer.status_code == "407":
            # Proxy Authentication Required
            handle_auth_required(call_id)
        elif sip_layer.status_code == "487":
            # Request Terminated
            handle_request_terminated(call_id)
        else:
            # 기타 응답 코드
            handle_other_response(sip_layer, call_id)

    # 8. 기타 SIP 메소드
    elif sip_layer.method == "REGISTER":
        # 등록 처리
        handle_registration(sip_layer)
    elif sip_layer.method == "ACK":
        # 확인 응답
        handle_ack_response(call_id)
    elif sip_layer.method == "CANCEL":
        # 취소 요청
        handle_cancel_request(call_id)
    elif sip_layer.method == "NOTIFY":
        # 알림 (Transfer 상태 등)
        handle_notify_message(sip_layer, call_id)
    else:
        # 알 수 없는 패킷
        handle_unknown_sip_packet(sip_layer, call_id)

# 보조 함수들
def is_conference_invite(sip_layer):
    """3자통화 INVITE 패턴 감지"""
    return (sip_layer.to_user in ['1427', '1428'] and
            has_active_external_call())

def has_active_call_session():
    """활성화된 통화 세션 확인"""
    return len(active_calls) > 0

def is_simple_two_party_call(sip_layer):
    """단순 2자 통화 패턴 확인"""
    return (not sip_layer.to_user.startswith('*') and
            not has_active_call_session())

def has_alternative_extension():
    """순차착신용 대체 내선 존재 확인"""
    return True  # 설정에서 확인

def is_sequential_routing_enabled():
    """순차착신 기능 활성화 확인"""
    return True  # 설정에서 확인
```

## 핵심 판별 기준

### **당겨받기 (*8) 감지**
```python
if sip_layer.to_user == "*8" and sip_layer.method == "INVITE":
    # X-xfer-pressed: True 헤더 확인
    # RINGING 상태 통화에서 실제 발신자 추출
```

### **3자통화 감지**
```python
elif (기존_통화_존재 and 새로운_INVITE and X-xfer-pressed):
    # Hold 상태 + 새 참가자 초대 패턴
    # 다중 Call-ID 관리 시작
```

### **돌려주기 감지**
```python
elif sip_layer.method == "REFER":
    # REFER → NOTIFY → 새로운 INVITE 패턴
    # refer_to 헤더에서 전송 대상 추출
```

### **순차착신 감지**
```python
elif sip_layer.status_code == "486":  # Busy Here
    # 자동으로 다음 내선 시도
```

### **일반 통화**
```python
else:
    # 단순 INVITE → 200 OK → ACK → BYE
```
