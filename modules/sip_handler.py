# -*- coding: utf-8 -*-
"""
SIP 패킷 처리 모듈
Dashboard 클래스에서 SIP 관련 기능을 분리
"""

import datetime
import asyncio
import threading
import traceback
from callstate_machine import CallState, CallStateMachine
from utils.helpers import is_extension


class SipHandler:
    """SIP 패킷 처리 관련 유틸리티 함수들"""
    
    def __init__(self, dashboard_instance):
        self.dashboard = dashboard_instance
    
    def analyze_sip_packet(self, packet):
        """SIP 패킷을 분석하고 처리"""
        print(f"=== SIP 패킷 분석 시작 ===")
        self.dashboard.log_to_sip_console("SIP 패킷 분석 시작", "DEBUG")
        if not hasattr(packet, 'sip'):
            print("SIP 레이어가 없는 패킷")
            self.dashboard.log_to_sip_console("SIP 레이어가 없는 패킷", "WARNING")
            self.dashboard.log_error("SIP 레이어가 없는 패킷")
            return

        try:
            sip_layer = packet.sip
            print(f"SIP 패킷 감지됨")
            self.dashboard.log_to_sip_console("SIP 패킷 감지됨", "INFO")
            if not hasattr(sip_layer, 'call_id'):
                print("Call-ID가 없는 SIP 패킷")
                self.dashboard.log_to_sip_console("Call-ID가 없는 SIP 패킷", "WARNING")
                self.dashboard.log_error("Call-ID가 없는 SIP 패킷")
                return

            call_id = sip_layer.call_id

            # 내선번호 추출 로직
            try:
                if hasattr(sip_layer, 'from'):
                    from_header = str(sip_layer.From)
                    if ',' in from_header:
                        internal_number = from_header.split(',')[1].split('"')[0]
                    else:
                        internal_number = sip_layer.from_user
                else:
                    internal_number = sip_layer.from_user
            except Exception as e:
                self.dashboard.log_error("내선번호 추출 실패", e)
                internal_number = sip_layer.from_user

            try:
                if hasattr(sip_layer, 'request_line'):
                    request_line = str(sip_layer.request_line)

                    # INVITE 처리
                    if 'INVITE' in request_line:
                        self._handle_invite_request(sip_layer, call_id, request_line, packet)
                    # REFER 처리
                    elif 'REFER' in request_line:
                        self._handle_refer_request(sip_layer, call_id, request_line)
                    # BYE 처리
                    elif 'BYE' in request_line:
                        self._handle_bye_request(call_id)
                    # CANCEL 처리
                    elif 'CANCEL' in request_line:
                        self._handle_cancel_request(call_id)
                    # REGISTER 처리
                    elif 'REGISTER' in request_line:
                        self._handle_register_request(sip_layer, call_id, request_line)

                # 응답 처리
                elif hasattr(sip_layer, 'status_line'):
                    self._handle_sip_response(sip_layer, call_id)

            except Exception as method_error:
                self.dashboard.log_error("SIP 메소드 처리 중 오류", method_error)
                return

        except Exception as e:
            self.dashboard.log_error("SIP 패킷 분석 중 심각한 오류", e)
            self.dashboard.log_error("상세 오류 정보", level="info", additional_info={"traceback": traceback.format_exc()})

    def _handle_invite_request(self, sip_layer, call_id, request_line, packet):
        """INVITE 요청 처리"""
        try:
            if not hasattr(sip_layer, 'from_user') or not hasattr(sip_layer, 'to_user'):
                self.dashboard.log_error("필수 SIP 헤더 누락", additional_info={
                    "call_id": call_id,
                    "request_line": request_line
                })
                return

            from_number = self.extract_number(sip_layer.from_user)
            to_number = self.extract_number(sip_layer.to_user)

            if not from_number or not to_number:
                self.dashboard.log_error("유효하지 않은 전화번호", additional_info={
                    "from_user": str(sip_layer.from_user),
                    "to_user": str(sip_layer.to_user)
                })
                return

            # 내선번호 확인
            extension = None
            if len(from_number) == 4 and from_number[0] in '123456789':
                extension = from_number
            elif len(to_number) == 4 and to_number[0] in '123456789':
                extension = to_number

            # 내선번호로 전화가 왔을 때 WebSocket을 통해 클라이언트에 알림
            if is_extension(to_number):
                try:
                    # WebSocket 서버가 있고 MongoDB가 연결되어 있는 경우에만 실행
                    if hasattr(self.dashboard, 'websocket_server') and self.dashboard.db is not None:
                        print(f"SIP 패킷 분석: 내선번호 {to_number}로 전화 수신 (발신: {from_number})")
                        self.dashboard.log_to_sip_console(f"내선번호 {to_number}로 전화 수신 (발신: {from_number})", "SIP")
                        
                        # 비동기 알림 전송을 위한 helper 함수
                        async def send_notification():
                            print(f"알림 전송 시작: 내선번호 {to_number}에 전화 수신 알림 (발신: {from_number})")
                            await self.dashboard.websocket_server.notify_client(to_number, from_number, call_id)
                            print(f"알림 전송 완료: 내선번호 {to_number}")

                        # 별도 스레드에서 비동기 함수 실행
                        notification_thread = threading.Thread(
                            target=lambda: asyncio.run(send_notification()),
                            daemon=True
                        )
                        notification_thread.start()
                        print(f"알림 전송 스레드 시작: {to_number}")
                        self.dashboard.log_error("클라이언트 알림 전송 시작", additional_info={
                            "to": to_number,
                            "from": from_number,
                            "call_id": call_id
                        })
                except Exception as notify_error:
                    print(f"클라이언트 알림 전송 실패: {str(notify_error)}")
                    self.dashboard.log_error("클라이언트 알림 전송 실패", notify_error)

            # 통화 정보 저장 및 상태 전이
            with self.dashboard.active_calls_lock:
                try:
                    before_state = dict(self.dashboard.active_calls) if call_id in self.dashboard.active_calls else None

                    # 상태 머신 관리
                    if call_id in self.dashboard.call_state_machines:
                        current_state = self.dashboard.call_state_machines[call_id].state
                        # TERMINATED 상태에서만 IDLE로 리셋
                        if current_state == CallState.TERMINATED:
                            self.dashboard.call_state_machines[call_id] = CallStateMachine()
                    else:
                        # 새로운 상태 머신 생성
                        self.dashboard.call_state_machines[call_id] = CallStateMachine()

                    current_state = self.dashboard.call_state_machines[call_id].state
                    # IDLE 상태에서만 TRYING으로 전이 허용
                    if current_state == CallState.IDLE:
                        self.dashboard.call_state_machines[call_id].update_state(CallState.TRYING)
                        self.dashboard.log_error("상태 전이 성공", level="info", additional_info={
                            "call_id": call_id,
                            "from_state": "IDLE",
                            "to_state": "TRYING"
                        })
                    else:
                        self.dashboard.log_error("잘못된 상태 전이 시도 무시", level="info", additional_info={
                            "call_id": call_id,
                            "current_state": current_state.name,
                            "attempted_state": "TRYING"
                        })

                    self.dashboard.active_calls[call_id] = {
                        'start_time': datetime.datetime.now(),
                        'status': '시도중',
                        'from_number': from_number,
                        'to_number': to_number,
                        'direction': '수신' if to_number.startswith(('1','2','3','4','5','6','7','8','9')) else '발신',
                        'media_endpoints': [],
                        'packet': packet
                    }

                except Exception as state_error:
                    self.dashboard.log_error("통화 상태 업데이트 실패", state_error)
                    return

            self.dashboard.update_call_status(call_id, '시도중')

        except Exception as invite_error:
            self.dashboard.log_error("INVITE 처리 중 오류", invite_error)

    def _handle_refer_request(self, sip_layer, call_id, request_line):
        """REFER 요청 처리를 위한 헬퍼 메소드"""
        with open('voip_monitor.log', 'a', encoding='utf-8') as log_file:
            log_file.write("\n=== 돌려주기 요청 감지 ===\n")
            log_file.write(f"시간: {datetime.datetime.now()}\n")
            log_file.write(f"Call-ID: {call_id}\n")
            log_file.write(f"Request Line: {request_line}\n")

            with self.dashboard.active_calls_lock:
                if call_id not in self.dashboard.active_calls:
                    log_file.write(f"[오류] 해당 Call-ID를 찾을 수 없음: {call_id}\n")
                    return

                original_call = dict(self.dashboard.active_calls[call_id])
                log_file.write(f"현재 통화 정보: {original_call}\n")

                if not all(k in original_call for k in ['to_number', 'from_number']):
                    log_file.write("[오류] 필수 통화 정보 누락\n")
                    return

                if not hasattr(sip_layer, 'refer_to'):
                    log_file.write("[오류] REFER-TO 헤더 누락\n")
                    return

                refer_to = str(sip_layer.refer_to)
                forwarded_ext = self.extract_number(refer_to.split('@')[0])

                if not forwarded_ext:
                    log_file.write("[오류] 유효하지 않은 Refer-To 번호\n")
                    return

                self.dashboard._update_call_for_refer(call_id, original_call, forwarded_ext, log_file)

    def _handle_bye_request(self, call_id):
        """BYE 요청 처리를 위한 헬퍼 메소드"""
        with self.dashboard.active_calls_lock:
            if call_id in self.dashboard.active_calls:
                before_state = dict(self.dashboard.active_calls[call_id])
                from_number = self.dashboard.active_calls[call_id].get('from_number', '')
                to_number = self.dashboard.active_calls[call_id].get('to_number', '')

                # 상태 머신 업데이트 - IN_CALL 상태에서만 TERMINATED로 전이 허용
                if call_id in self.dashboard.call_state_machines:
                    current_state = self.dashboard.call_state_machines[call_id].state
                    if current_state == CallState.IN_CALL:
                        self.dashboard.call_state_machines[call_id].update_state(CallState.TERMINATED)
                        self.dashboard.log_error("상태 전이 성공", level="info", additional_info={
                            "call_id": call_id,
                            "from_state": "IN_CALL",
                            "to_state": "TERMINATED"
                        })
                    else:
                        self.dashboard.log_error("잘못된 상태 전이 시도 무시", level="info", additional_info={
                            "call_id": call_id,
                            "current_state": current_state.name,
                            "attempted_state": "TERMINATED"
                        })
                        return

                # 내선번호로 BYE 알림 전송
                if is_extension(to_number):
                    try:
                        # WebSocket 서버가 있고 MongoDB가 연결되어 있는 경우에만 실행
                        if hasattr(self.dashboard, 'websocket_server') and self.dashboard.db is not None:
                            print(f"BYE 패킷 분석: 내선번호 {to_number}로 통화 종료 알림 (발신: {from_number})")
                            
                            # 비동기 알림 전송을 위한 helper 함수
                            async def send_bye_notification():
                                print(f"BYE 알림 전송 시작: 내선번호 {to_number}에 통화 종료 알림 (발신: {from_number})")
                                await self.dashboard.websocket_server.notify_client_call_end(to_number, from_number, call_id, "BYE")
                                print(f"BYE 알림 전송 완료: 내선번호 {to_number}")

                            # 별도 스레드에서 비동기 함수 실행
                            notification_thread = threading.Thread(
                                target=lambda: asyncio.run(send_bye_notification()),
                                daemon=True
                            )
                            notification_thread.start()
                            print(f"BYE 알림 전송 스레드 시작: {to_number}")
                            self.dashboard.log_error("BYE 클라이언트 알림 전송 시작", additional_info={
                                "to": to_number,
                                "from": from_number,
                                "call_id": call_id,
                                "method": "BYE"
                            })
                    except Exception as notify_error:
                        print(f"BYE 클라이언트 알림 전송 실패: {str(notify_error)}")
                        self.dashboard.log_error("BYE 클라이언트 알림 전송 실패", notify_error)

                self.dashboard.update_call_status(call_id, '통화종료', '정상종료')
                extension = self.dashboard.get_extension_from_call(call_id)
                after_state = dict(self.dashboard.active_calls[call_id])
                self.dashboard.log_error("BYE 처리", level="info", additional_info={
                    "extension": extension,
                    "before_state": before_state,
                    "after_state": after_state,
                    "state_machine": self.dashboard.call_state_machines[call_id].state.name if call_id in self.dashboard.call_state_machines else "UNKNOWN"
                })

    def _handle_cancel_request(self, call_id):
        """CANCEL 요청 처리를 위한 헬퍼 메소드"""
        # Dashboard 클래스의 해당 메소드 호출
        if hasattr(self.dashboard, '_handle_cancel_request'):
            self.dashboard._handle_cancel_request(call_id)

    def _handle_register_request(self, sip_layer, call_id, request_line):
        """REGISTER 요청 처리를 위한 헬퍼 메소드"""
        try:
            print(f"=== SIP REGISTER 감지 ===")
            print(f"Request Line: {request_line}")
            self.dashboard.log_to_sip_console(f"SIP REGISTER 감지 - {request_line}", "SIP")

            # SIP REGISTER에서 내선번호 추출
            if hasattr(sip_layer, 'from_user'):
                from_user = str(sip_layer.from_user)
                print(f"From User: {from_user}")

                extension = self.extract_number(from_user)
                print(f"추출된 내선번호: {extension}")

                if extension and len(extension) == 4 and extension[0] in ['1','2','3','4','5','6','7','8','9']:
                    # SIP 등록된 내선번호를 사이드바에 추가
                    self.dashboard.refresh_extension_list_with_register(extension)
                    self.dashboard.log_error("SIP REGISTER 처리 완료", level="info", additional_info={
                        "extension": extension,
                        "call_id": call_id,
                        "from_user": from_user
                    })
                else:
                    print(f"유효하지 않은 내선번호: {extension}")
            else:
                print("from_user 필드가 없음")
        except Exception as e:
            print(f"REGISTER 처리 중 오류: {e}")
            self.dashboard.log_error("REGISTER 요청 처리 중 오류", e)

    def _handle_sip_response(self, sip_layer, call_id):
        """SIP 응답 처리를 위한 헬퍼 메소드"""
        status_code = sip_layer.status_code
        if status_code == '100':
            extension = self.extract_number(sip_layer.from_user)
            if extension and len(extension) == 4 and extension[0] in ['1','2','3','4','5','6','7','8','9']:
                pass  # 통화 시에는 내선번호를 사이드바에 추가하지 않음

        with self.dashboard.active_calls_lock:
            if call_id in self.dashboard.active_calls:
                if status_code == '183':
                    self.dashboard.update_call_status(call_id, '벨울림')
                    extension = self.dashboard.get_extension_from_call(call_id)
                    if extension:
                        received_number = self.dashboard.active_calls[call_id]['to_number']
                        # 전화연결상태 블록 대신 사이드바에만 내선번호 추가
                        self.dashboard.add_extension(extension)
                elif status_code == '200':
                    if self.dashboard.active_calls[call_id]['status'] != '통화종료':
                        self.dashboard.handle_sip_response(status_code, call_id, sip_layer)

    def extract_number(self, sip_user):
        """SIP 사용자에서 번호 추출"""
        import re
        
        if not sip_user:
            return None
        
        sip_user_str = str(sip_user)
        # sip:1234@192.168.0.1 형태에서 숫자 부분만 추출
        match = re.search(r'(\d+)', sip_user_str)
        if match:
            return match.group(1)
        return None

    def handle_sip_response(self, status_code, call_id, sip_layer):
        """SIP 응답 코드 처리"""
        # Dashboard 클래스의 해당 메소드 호출
        if hasattr(self.dashboard, 'handle_sip_response'):
            self.dashboard.handle_sip_response(status_code, call_id, sip_layer)