# -*- coding: utf-8 -*-
"""
패킷 처리 모듈
Dashboard 클래스에서 패킷 캡처 및 처리 관련 기능을 분리
"""

import asyncio
import datetime
import os
import psutil
import pyshark
import re
import threading
import traceback
from config_loader import load_config, get_wireshark_path
from rtpstream_manager import RTPStreamManager
from utils.helpers import is_extension


class PacketProcessor:
    """패킷 캡처 및 처리 관련 유틸리티 함수들"""
    
    def __init__(self, dashboard_instance):
        self.dashboard = dashboard_instance
        self.stream_manager = None
    
    def start_packet_capture(self):
        """패킷 캡처 시작"""
        try:
            if not self.dashboard.selected_interface:
                self.dashboard.log_error("선택된 네트워크 인터페이스가 없습니다")
                return

            if hasattr(self.dashboard, 'capture_thread') and self.dashboard.capture_thread and self.dashboard.capture_thread.is_alive():
                self.dashboard.log_error("패킷 캡처가 이미 실행 중입니다")
                return

            # 시스템 리소스 체크
            try:
                cpu_percent = psutil.cpu_percent()
                memory = psutil.virtual_memory()

                # 리소스가 부족한 경우 로그만 남기고 진행
                if cpu_percent > 80 or memory.percent > 80:
                    resource_info = {
                        "cpu": f"{cpu_percent}%",
                        "memory": f"{memory.percent}%"
                    }
                    self.dashboard.log_error("시스템 리소스 부족", additional_info=resource_info, level="warning", console_output=False)
            except Exception as e:
                self.dashboard.log_error("시스템 리소스 체크 실패", e, console_output=False)

            # Wireshark 경로 확인
            config = load_config()
            if not config:
                self.dashboard.log_error("설정 파일을 로드할 수 없습니다")
                return

            wireshark_path = get_wireshark_path()
            if not os.path.exists(wireshark_path):
                self.dashboard.log_error("Wireshark가 설치되어 있지 않습니다")
                return

            # 캡처 스레드 시작
            self.dashboard.capture_thread = threading.Thread(
                target=self.capture_packets,
                args=(self.dashboard.selected_interface,),
                daemon=True
            )
            self.dashboard.capture_thread.start()
            self.dashboard.log_error("패킷 캡처 시작됨", additional_info={"interface": self.dashboard.selected_interface})

        except Exception as e:
            self.dashboard.log_error("패킷 캡처 시작 실패", e)

    def capture_packets(self, interface):
        """패킷 캡처 실행"""
        if not interface:
            self.dashboard.log_error("유효하지 않은 인터페이스")
            return

        capture = None
        loop = None

        try:
            # 이벤트 루프 설정
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            # 캡처 필터 설정
            capture = pyshark.LiveCapture(
                interface=interface,
                display_filter='sip or (udp and (udp.port >= 1024 and udp.port <= 65535))'
            )

            # 패킷 캡처 시작
            for packet in capture.sniff_continuously():
                try:
                    # 메모리 사용량 모니터링
                    process = psutil.Process()
                    memory_percent = process.memory_percent()
                    if memory_percent > 80:
                        self.dashboard.log_error("높은 메모리 사용량", additional_info={"memory_percent": memory_percent})

                    if hasattr(packet, 'sip'):
                        self.dashboard.analyze_sip_packet(packet)
                    elif hasattr(packet, 'udp') and self.is_rtp_packet(packet):
                        self.handle_rtp_packet(packet)

                except Exception as packet_error:
                    self.dashboard.log_error("패킷 처리 중 오류", packet_error)
                    continue

        except KeyboardInterrupt:
            self.dashboard.log_error("사용자에 의한 캡처 중단")
        except Exception as capture_error:
            self.dashboard.log_error("캡처 프로세스 오류", capture_error)

        finally:
            try:
                if capture:
                    if loop and not loop.is_closed():
                        loop.run_until_complete(capture.close_async())
                    else:
                        capture.close()
                else:
                    self.dashboard.log_error("캡처 프로세스가 초기화되지 않았습니다")
            except Exception as close_error:
                self.dashboard.log_error("캡처 종료 실패", close_error)

            try:
                if loop and not loop.is_closed():
                    loop.close()
                else:
                    self.dashboard.log_error("이벤트 루프가 초기화되지 않았습니다")
            except Exception as loop_error:
                self.dashboard.log_error("이벤트 루프 종료 실패", loop_error)

    def update_packet_status(self):
        """패킷 상태 업데이트"""
        try:
            with self.dashboard.active_calls_lock:
                for call_id, call_info in self.dashboard.active_calls.items():
                    if call_info.get('status_changed', False):
                        extension = self.dashboard.get_extension_from_call(call_id)
                        if extension:
                            self.dashboard.create_waiting_block(extension)
                        call_info['status_changed'] = False
        except Exception as e:
            print(f"패킷 상태 업데이트 중 오류: {e}")

    def is_rtp_packet(self, packet):
        """RTP 패킷인지 확인"""
        try:
            if not hasattr(packet, 'udp') or not hasattr(packet.udp, 'payload'):
                return False
            payload_hex = packet.udp.payload.replace(':', '')
            try:
                payload = bytes.fromhex(payload_hex)
            except ValueError:
                return False
            if len(payload) < 12:
                return False
            version = (payload[0] >> 6) & 0x03
            if version != 2:
                return False
            payload_type = payload[1] & 0x7F
            return payload_type in [0, 8]
        except Exception as e:
            print(f"RTP 패킷 확인 중 오류: {e}")
            return False

    def determine_stream_direction(self, packet, call_id):
        """스트림 방향 결정"""
        try:
            if call_id not in self.dashboard.active_calls:
                return None
            call_info = self.dashboard.active_calls[call_id]
            if 'media_endpoints' not in call_info:
                call_info['media_endpoints'] = []
            if 'media_endpoints_set' not in call_info:
                call_info['media_endpoints_set'] = {'local': set(), 'remote': set()}

            src_ip = packet.ip.src
            dst_ip = packet.ip.dst
            src_port = int(packet.udp.srcport)
            dst_port = int(packet.udp.dstport)

            src_endpoint = f"{src_ip}:{src_port}"
            dst_endpoint = f"{dst_ip}:{dst_port}"

            # 엔드포인트 세트에서 확인
            if src_endpoint in call_info['media_endpoints_set']['local'] or dst_endpoint in call_info['media_endpoints_set']['remote']:
                return 'out'
            elif src_endpoint in call_info['media_endpoints_set']['remote'] or dst_endpoint in call_info['media_endpoints_set']['local']:
                return 'in'

            # 기존 리스트에서 확인
            for endpoint in call_info['media_endpoints']:
                if (src_ip == endpoint.get('ip') and src_port == endpoint.get('port')):
                    return 'out'
                elif (dst_ip == endpoint.get('ip') and dst_port == endpoint.get('port')):
                    return 'in'

            return None
        except Exception as e:
            print(f"스트림 방향 결정 중 오류: {e}")
            return None

    def get_call_id_from_rtp(self, packet):
        """RTP 패킷에서 Call ID 추출"""
        try:
            src_ip = packet.ip.src
            dst_ip = packet.ip.dst
            src_port = int(packet.udp.srcport)
            dst_port = int(packet.udp.dstport)
            src_endpoint = f"{src_ip}:{src_port}"
            dst_endpoint = f"{dst_ip}:{dst_port}"
            
            with self.dashboard.active_calls_lock:
                for call_id, call_info in self.dashboard.active_calls.items():
                    if "media_endpoints_set" in call_info:
                        if (src_endpoint in call_info["media_endpoints_set"]["local"] or
                            src_endpoint in call_info["media_endpoints_set"]["remote"] or
                            dst_endpoint in call_info["media_endpoints_set"]["local"] or
                            dst_endpoint in call_info["media_endpoints_set"]["remote"]):
                            return call_id
                    elif "media_endpoints" in call_info:
                        for endpoint in call_info["media_endpoints"]:
                            if (src_ip == endpoint.get("ip") and src_port == endpoint.get("port")) or \
                               (dst_ip == endpoint.get("ip") and dst_port == endpoint.get("port")):
                                return call_id
            return None
        except Exception as e:
            print(f"RTP Call-ID 매칭 오류: {e}")
            print(traceback.format_exc())
            return None

    def handle_rtp_packet(self, packet):
        """RTP 패킷 처리"""
        try:
            if not hasattr(self, 'stream_manager') or not self.stream_manager:
                self.stream_manager = RTPStreamManager()
                self.dashboard.log_error("RTP 스트림 매니저 생성", level="info")

            # SIP 정보 확인 및 처리
            if hasattr(packet, 'sip'):
                self.dashboard.analyze_sip_packet(packet)
                return

            # UDP 페이로드가 없으면 처리하지 않음
            if not hasattr(packet, 'udp') or not hasattr(packet.udp, 'payload'):
                return

            active_calls = []
            with self.dashboard.active_calls_lock:
                # 상태가 '통화중'인 통화만 필터링
                for cid, info in self.dashboard.active_calls.items():
                    if info.get('status') == '통화중':  # '벨울림' 상태는 제외
                        active_calls.append((cid, info))

            if not active_calls:
                return

            # 멀티 전화 통화 처리
            for call_id, call_info in active_calls:
                try:
                    # 파일 경로 생성 전에 phone_ip 유효성 검사
                    if '@' not in call_id:
                        self.dashboard.log_error("유효하지 않은 call_id 형식", additional_info={"call_id": call_id})
                        continue

                    phone_ip = call_id.split('@')[1].split(';')[0].split(':')[0]

                    if not phone_ip:
                        self.dashboard.log_error("phone_ip를 추출할 수 없음", additional_info={"call_id": call_id})
                        continue

                    direction = self.determine_stream_direction(packet, call_id)

                    if not direction:
                        continue

                    # SIP 정보가 있는 경우 로그 기록
                    if 'packet' in call_info and hasattr(call_info['packet'], 'sip'):
                        sip_info = call_info['packet'].sip
                        from_user = getattr(sip_info, 'from_user', 'unknown')
                        to_user = getattr(sip_info, 'to_user', 'unknown')

                        if len(from_user) > 4:
                            # 정규식 분할 결과가 비어있을 수 있으므로 안전하게 처리
                            from_user = re.split(r'[a-zA-Z]+', from_user)
                        if len(to_user) > 4:
                            to_user = re.split(r'[a-zA-Z]+', to_user)

                        # 내선 간 통화인 경우
                        if is_extension(to_user):
                            # mongodb 찾기
                            internalnumber_doc = self.dashboard.internalnumber.find_one({"internal_number": to_user})
                            if internalnumber_doc:
                                phone_ip_str = internalnumber_doc.get('ip_address', '')
                            else:
                                phone_ip_str = phone_ip
                        # 내부 외부 간 통화인 경우
                        else:
                            phone_ip_str = phone_ip

                    payload_hex = packet.udp.payload.replace(':', '')
                    try:
                        payload = bytes.fromhex(payload_hex)
                        version = (payload[0] >> 6) & 0x03
                        payload_type = payload[1] & 0x7F
                        sequence = int.from_bytes(payload[2:4], byteorder='big')
                        audio_data = payload[12:]

                        if len(audio_data) == 0:
                            continue

                        stream_key = self.stream_manager.create_stream(
                            call_id, direction, call_info, phone_ip_str
                        )

                        if stream_key:
                            self.stream_manager.process_packet(
                                stream_key, audio_data, sequence, payload_type
                            )

                    except Exception as payload_error:
                        self.dashboard.log_error("페이로드 분석 오류", payload_error)
                        continue
                except Exception as call_error:
                    self.dashboard.log_error("통화별 RTP 처리 오류", call_error, {"call_id": call_id})
                    continue

        except Exception as e:
            self.dashboard.log_error("RTP 패킷 처리 중 심각한 오류", e)
            self.dashboard.log_error("상세 오류 정보", additional_info={"traceback": traceback.format_exc()})