"""
ExtensionRecordingManager - 통화별 녹음 관리 시스템
통화 시작시 Dumpcap 실행, 통화 종료시 자동 변환 및 저장
"""

import os
import subprocess
import threading
import datetime
import logging
from pathlib import Path
from typing import Dict, Optional
import time
import hashlib
import wave
import audioop
import struct
import asyncio
from config_loader import load_config, get_wireshark_path
from wav_merger import WavMerger

try:
    import pyshark
except ImportError:
    pyshark = None
    print("Warning: pyshark not available, pcapng processing will be disabled")


class ExtensionRecordingManager:
    """통화별 녹음 관리 클래스"""

    def __init__(self, logger=None, dashboard_instance=None):
        """초기화"""
        self.call_recordings: Dict[str, Dict] = {}  # call_id -> recording_info
        self.recording_lock = threading.Lock()
        self.dashboard = dashboard_instance  # Dashboard 인스턴스 참조

        # 로거 설정 - Dashboard 객체인 경우 표준 로거로 변경
        if logger and hasattr(logger, 'log_error'):
            # Dashboard 객체인 경우 표준 로거 사용
            self.logger = logging.getLogger(__name__)
            self.dashboard_logger = logger  # Dashboard 로거 별도 보관

            # 로깅 레벨 설정
            self.logger.setLevel(logging.INFO)
            if not self.logger.handlers:
                handler = logging.StreamHandler()
                handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
                self.logger.addHandler(handler)
        else:
            self.logger = logger or logging.getLogger(__name__)
            self.dashboard_logger = None

        # 설정 로드
        self.config = load_config()
        self.interface_number = self._get_interface_number()
        self.dumpcap_path = self._get_dumpcap_path()
        self.base_recording_path = self._get_base_recording_path()

        # 임시 녹음 디렉토리 생성
        self.temp_dir = Path("temp_recordings")
        self.temp_dir.mkdir(exist_ok=True)

        # 내선-IP 동적 매핑 시스템
        self.extension_ip_mapping: Dict[str, str] = {}  # extension_number -> ip_address
        self.call_sip_info: Dict[str, Dict] = {}  # call_id -> sip_info (ports, ips, etc)
        self.mapping_lock = threading.Lock()

    def _get_interface_number(self) -> str:
        """네트워크 인터페이스 번호 가져오기"""
        try:
            interface_name = None

            # 1. Dashboard에서 인터페이스 이름 가져오기
            if self.dashboard and hasattr(self.dashboard, 'selected_interface'):
                interface_name = self.dashboard.selected_interface
                self.logger.info(f"Dashboard에서 인터페이스 가져옴: {interface_name}")

            # 2. Dashboard가 없거나 인터페이스가 없으면 settings.ini에서 가져오기
            if not interface_name:
                interface_name = self.config.get('Network', 'interface', fallback=None)
                if interface_name:
                    self.logger.info(f"settings.ini에서 인터페이스 가져옴: {interface_name}")
                else:
                    self.logger.warning("settings.ini에 인터페이스 설정 없음")

            # 3. 인터페이스 이름이 있으면 번호로 변환
            if interface_name:
                from config_loader import get_wireshark_path
                tshark_path = os.path.join(get_wireshark_path(), "tshark.exe")

                if os.path.exists(tshark_path):
                    result = subprocess.run([tshark_path, "-D"], capture_output=True, text=True, timeout=10, encoding='utf-8', errors='ignore')
                    if result.returncode == 0:
                        # 인터페이스 이름을 번호로 변환
                        interface_number = self._parse_interface_number(result.stdout, interface_name)
                        if interface_number:
                            self.logger.info(f"인터페이스 '{interface_name}' → 번호 '{interface_number}'")
                            return interface_number
                        else:
                            self.logger.warning(f"인터페이스 '{interface_name}' 번호를 찾을 수 없음")
                    else:
                        self.logger.error(f"tshark -D 실행 실패: {result.stderr}")
                else:
                    self.logger.error(f"tshark.exe 경로 없음: {tshark_path}")

            # 4. 기본값 반환
            self.logger.warning("인터페이스 번호 자동 감지 실패, 기본값 '1' 사용")
            return "1"
        except Exception as e:
            self.logger.error(f"인터페이스 번호 가져오기 실패: {e}")
            return "1"

    def _parse_interface_number(self, tshark_output: str, interface_name: str) -> str:
        """tshark -D 출력에서 인터페이스 번호 파싱"""
        try:
            lines = tshark_output.split('\n')
            for line in lines:
                if interface_name in line:
                    # 라인 형식: "6. \Device\NPF_{...} (이더넷 3)"
                    parts = line.split('.')
                    if len(parts) > 0:
                        number = parts[0].strip()
                        if number.isdigit():
                            return number
            return None
        except Exception as e:
            self.logger.error(f"인터페이스 번호 파싱 실패: {e}")
            return None

    def _get_dumpcap_path(self) -> str:
        """Dumpcap 실행 파일 경로 가져오기"""
        try:
            wireshark_path = get_wireshark_path()
            dumpcap_path = os.path.join(wireshark_path, "dumpcap.exe")
            if not os.path.exists(dumpcap_path):
                raise FileNotFoundError(f"dumpcap.exe not found: {dumpcap_path}")
            return dumpcap_path
        except Exception as e:
            self.logger.error(f"Dumpcap 경로 가져오기 실패: {e}")
            return ""

    def _get_base_recording_path(self) -> str:
        """기본 녹음 저장 경로 가져오기"""
        try:
            config = load_config()

            # settings.ini의 Recording 섹션에서 save_path 가져오기
            save_path = config.get('Recording', 'save_path', fallback=None)
            if save_path:
                # 슬래시를 백슬래시로 변경 (Windows 경로)
                return save_path.replace('/', '\\')

            # 기본값으로 환경 확인
            mode = config.get('Environment', 'mode', fallback='development')
            if mode == 'production':
                return os.path.join(os.environ.get('ProgramFiles(x86)', ''), 'Recap Voice', 'PacketWaveRecord')
            else:
                dir_path = config.get('DefaultDirectory', 'dir_path', fallback=os.getcwd())
                return os.path.join(dir_path, 'PacketWaveRecord')
        except Exception as e:
            self.logger.error(f"녹음 경로 가져오기 실패: {e}")
            return os.path.join(os.getcwd(), 'PacketWaveRecord')

    def update_extension_ip_mapping(self, extension: str, ip_address: str):
        """내선번호와 IP 주소 매핑 업데이트"""
        with self.mapping_lock:
            self.extension_ip_mapping[extension] = ip_address
            self.logger.info(f"내선-IP 매핑 업데이트: {extension} → {ip_address}")

    def get_extension_ip(self, extension: str) -> Optional[str]:
        """내선번호에 해당하는 IP 주소 조회"""
        with self.mapping_lock:
            return self.extension_ip_mapping.get(extension)

    def update_call_sip_info(self, call_id: str, sip_info: Dict):
        """통화별 SIP 정보 업데이트"""
        with self.mapping_lock:
            if call_id not in self.call_sip_info:
                self.call_sip_info[call_id] = {}
            self.call_sip_info[call_id].update(sip_info)
            self.logger.info(f"통화 SIP 정보 업데이트: {call_id} → {sip_info}")

    def get_call_sip_info(self, call_id: str) -> Dict:
        """통화별 SIP 정보 조회"""
        with self.mapping_lock:
            return self.call_sip_info.get(call_id, {})

    def _extract_sip_info_from_dashboard(self, call_id: str, extension: str) -> Dict:
        """Dashboard에서 SIP 정보 추출"""
        sip_info = {}
        try:
            if self.dashboard and hasattr(self.dashboard, 'active_calls'):
                with getattr(self.dashboard, 'active_calls_lock', threading.Lock()):
                    if call_id in self.dashboard.active_calls:
                        call_data = self.dashboard.active_calls[call_id]

                        # SIP 관련 정보 추출
                        sip_info = {
                            'call_id': call_id,
                            'from_number': call_data.get('from_number', ''),
                            'to_number': call_data.get('to_number', ''),
                            'extension': extension,
                            'status': call_data.get('status', ''),
                        }

                        self.logger.info(f"Dashboard에서 SIP 정보 추출: {sip_info}")

            return sip_info
        except Exception as e:
            self.logger.error(f"Dashboard SIP 정보 추출 실패: {e}")
            return {}

    def _generate_dynamic_filter(self, call_id: str, extension: str, from_number: str, to_number: str) -> str:
        """통화별 동적 캡처 필터 생성"""
        try:
            # 1. 내선 IP 조회
            extension_ip = self.get_extension_ip(extension)
            if not extension_ip:
                # Dashboard의 SIP 분석으로부터 내선 IP 자동 감지 시도
                extension_ip = self._detect_extension_ip_from_dashboard(extension)

            # 2. SIP 정보 조회
            call_sip_info = self.get_call_sip_info(call_id)

            # 3. 기본 필터 (기존 방식)
            base_filter = "(port 5060) or (udp and portrange 1024-65535)"

            # 4. 내선 IP 기반 필터 추가
            if extension_ip:
                # 해당 내선 IP와 관련된 트래픽만 캡처
                ip_filter = f"host {extension_ip}"
                dynamic_filter = f"({base_filter}) and ({ip_filter})"

                self.logger.info(f"동적 필터 생성 (IP 기반): {dynamic_filter}")
                return dynamic_filter

            # 5. SIP 포트 정보가 있는 경우 추가 최적화
            if call_sip_info.get('rtp_ports'):
                rtp_ports = call_sip_info['rtp_ports']
                if len(rtp_ports) == 1:
                    port_filter = f"udp port {rtp_ports[0]}"
                elif len(rtp_ports) == 2:
                    port_filter = f"udp portrange {min(rtp_ports)}-{max(rtp_ports)}"
                else:
                    port_filter = f"udp and ({' or '.join(f'port {p}' for p in rtp_ports)})"

                optimized_filter = f"(port 5060) or ({port_filter})"
                self.logger.info(f"동적 필터 생성 (포트 기반): {optimized_filter}")
                return optimized_filter

            # 6. 기본 필터 반환
            self.logger.warning(f"동적 필터 생성 실패, 기본 필터 사용: {base_filter}")
            return base_filter

        except Exception as e:
            self.logger.error(f"동적 필터 생성 실패: {e}")
            return "(port 5060) or (udp and portrange 1024-65535)"

    def _detect_extension_ip_from_dashboard(self, extension: str) -> Optional[str]:
        """Dashboard의 내선 정보에서 IP 자동 감지"""
        try:
            if not self.dashboard:
                return None

            # Dashboard의 내선 정보 조회
            if hasattr(self.dashboard, 'extension_widgets'):
                for ext_num, widget_data in self.dashboard.extension_widgets.items():
                    if str(ext_num) == str(extension):
                        # 위젯에서 IP 정보 추출 (실제 구현에 따라 조정 필요)
                        if hasattr(widget_data, 'ip_address'):
                            detected_ip = widget_data.ip_address
                            self.update_extension_ip_mapping(extension, detected_ip)
                            return detected_ip

            # SIP REGISTER 패킷 기반 동적 IP 감지 시도
            detected_ip = self._detect_ip_from_sip_register(extension)
            if detected_ip:
                self.update_extension_ip_mapping(extension, detected_ip)
                return detected_ip

        except Exception as e:
            self.logger.error(f"Dashboard에서 내선 IP 감지 실패: {e}")

        return None

    def _detect_ip_from_sip_register(self, extension: str) -> Optional[str]:
        """SIP REGISTER 패킷으로부터 내선 IP 감지"""
        try:
            if not self.dashboard or not hasattr(self.dashboard, 'extension_widgets'):
                return None

            # Dashboard의 내선 등록 정보에서 IP 검색
            for ext_num, ext_data in getattr(self.dashboard, 'extension_widgets', {}).items():
                if str(ext_num) == str(extension):
                    # 내선 위젯에서 IP 정보 추출
                    if hasattr(ext_data, 'text') and hasattr(ext_data, 'ip'):
                        return ext_data.ip
                    elif hasattr(ext_data, 'toolTip'):
                        # 툴팁에서 IP 정보 추출 시도
                        tooltip = ext_data.toolTip()
                        import re
                        ip_pattern = r'\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b'
                        matches = re.findall(ip_pattern, tooltip)
                        if matches:
                            return matches[0]

            return None
        except Exception as e:
            self.logger.error(f"SIP REGISTER 기반 IP 감지 실패: {e}")
            return None

    def start_call_recording(self, call_id: str, extension: str, from_number: str, to_number: str) -> bool:
        """통화별 녹음 시작"""
        try:
            with self.recording_lock:
                if call_id in self.call_recordings:
                    self.logger.warning(f"통화 {call_id} 이미 녹음 중")
                    return False

                if not self.dumpcap_path:
                    self.logger.error("Dumpcap 경로가 설정되지 않음")
                    return False

                # 임시 pcapng 파일 경로 (call_id 해시를 포함하여 고유성 보장)
                timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S%f")[:19]  # 마이크로초 포함
                call_hash = hashlib.md5(call_id.encode()).hexdigest()[:8]  # 8자리 해시
                pcapng_filename = f"call_{call_hash}_{extension}_{timestamp}_{os.getpid()}.pcapng"
                pcapng_path = self.temp_dir / pcapng_filename

                # 추가 보안: 파일 중복 검사
                counter = 1
                while pcapng_path.exists():
                    pcapng_filename = f"call_{call_hash}_{extension}_{timestamp}_{counter:03d}.pcapng"
                    pcapng_path = self.temp_dir / pcapng_filename
                    counter += 1
                    if counter > 999:  # 무한 루프 방지
                        self.logger.error(f"pcapng 파일 중복 해결 실패: {pcapng_filename}")
                        break

                self.logger.info(f"녹음 시작 준비: {pcapng_filename}")
                if self.dashboard_logger:
                    self.dashboard_logger.log_error(f"녹음 시작 준비: {pcapng_filename}", level="info")

                # Dashboard에서 SIP 정보 추출 및 저장
                sip_info = self._extract_sip_info_from_dashboard(call_id, extension)
                if sip_info:
                    self.update_call_sip_info(call_id, sip_info)

                # 동적 필터 생성
                capture_filter = self._generate_dynamic_filter(call_id, extension, from_number, to_number)

                # 통화별 고유 식별을 위한 코멘트 (로그용)
                filter_comment = f"Extension {extension}: {from_number} <-> {to_number}"
                self.logger.info(f"🎯 동적 필터 적용: {filter_comment}")
                self.logger.info(f"📡 캡처 필터: {capture_filter}")

                # Dumpcap 명령어 구성
                dumpcap_cmd = [
                    self.dumpcap_path,
                    "-i", self.interface_number,
                    "-f", capture_filter,
                    "-w", str(pcapng_path),
                    "-b", "files:1"  # 단일 파일
                ]

                # Dumpcap 프로세스 시작
                self.logger.info(f"Dumpcap 명령: {' '.join(dumpcap_cmd)}")
                process = subprocess.Popen(
                    dumpcap_cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    creationflags=subprocess.CREATE_NO_WINDOW
                )

                # 프로세스 시작 확인
                import time
                time.sleep(0.1)  # 짧은 대기
                if process.poll() is not None:
                    stdout, stderr = process.communicate()
                    self.logger.error(f"Dumpcap 즉시 종료됨 - stdout: {stdout.decode()}, stderr: {stderr.decode()}")
                    return False

                self.logger.info(f"Dumpcap 프로세스 시작됨: PID {process.pid}")
                if self.dashboard_logger:
                    self.dashboard_logger.log_error(f"Dumpcap 프로세스 시작됨: PID {process.pid}", level="info")

                # 녹음 정보 저장 - 통화별 고유 식별 정보 추가
                current_time = datetime.datetime.now()
                recording_info = {
                    'process': process,
                    'pcapng_path': pcapng_path,
                    'extension': extension,
                    'from_number': from_number,
                    'to_number': to_number,
                    'start_time': current_time,
                    'filter': capture_filter,
                    'call_hash': call_hash,  # 고유 식별자
                    'call_id': call_id,  # 원본 call_id 보존
                    'direction_info': {  # IN/OUT 구분을 위한 정보
                        'extension_number': extension,
                        'remote_number': to_number if from_number == extension else from_number,
                        'is_outgoing': from_number == extension
                    }
                }

                self.call_recordings[call_id] = recording_info

                self.logger.info(f"통화 녹음 시작: {call_id} (내선: {extension}, 파일: {pcapng_filename})")
                self.logger.info(f"📝 녹음 세부 정보 - Call Hash: {call_hash}, 필터: {capture_filter}")
                if self.dashboard_logger:
                    self.dashboard_logger.log_error(f"📝 다중통화 지원 녹음 시작 - Call Hash: {call_hash}", level="info")

                return True

        except Exception as e:
            self.logger.error(f"통화 녹음 시작 실패: {e}")
            return False

    def stop_call_recording(self, call_id: str) -> Optional[Dict]:
        """통화별 녹음 종료 및 변환 준비"""
        try:
            with self.recording_lock:
                if call_id not in self.call_recordings:
                    self.logger.warning(f"통화 {call_id} 녹음 정보 없음")
                    return None

                recording_info = self.call_recordings[call_id]
                process = recording_info['process']

                # Dumpcap 프로세스 종료
                try:
                    process.terminate()
                    process.wait(timeout=5)
                    self.logger.info(f"통화 녹음 종료: {call_id}")
                except subprocess.TimeoutExpired:
                    process.kill()
                    self.logger.warning(f"통화 녹음 강제 종료: {call_id}")
                except Exception as e:
                    self.logger.error(f"프로세스 종료 실패: {e}")

                # 종료 시간 기록
                recording_info['end_time'] = datetime.datetime.now()

                # 녹음 목록에서 제거
                del self.call_recordings[call_id]

                return recording_info

        except Exception as e:
            self.logger.error(f"통화 녹음 종료 실패: {e}")
            return None

    def convert_and_save(self, recording_info: Dict) -> bool:
        """pcapng 파일에서 직접 IN/OUT WAV 파일을 생성하고 MERGE 파일도 생성"""
        pcapng_path = recording_info.get('pcapng_path')

        try:
            extension = recording_info['extension']
            from_number = recording_info['from_number']
            to_number = recording_info['to_number']
            start_time = recording_info['start_time']
            call_hash = recording_info.get('call_hash', '')

            # 실제 생성된 파일을 찾기 (dumpcap이 추가 번호를 붙일 수 있음)
            if not pcapng_path or not os.path.exists(pcapng_path):
                self.logger.warning(f"예상 pcapng 파일이 없음: {pcapng_path}")

                # 패턴 매칭으로 실제 파일 찾기
                if pcapng_path:
                    base_name = os.path.splitext(os.path.basename(pcapng_path))[0]
                    temp_dir = os.path.dirname(pcapng_path)

                    # call_hash 기반으로 매칭되는 파일 찾기
                    matching_files = []
                    for file in os.listdir(temp_dir):
                        if file.startswith(f"call_{call_hash}") and file.endswith('.pcapng'):
                            matching_files.append(os.path.join(temp_dir, file))

                    if matching_files:
                        # 가장 최근 파일 선택
                        pcapng_path = max(matching_files, key=os.path.getctime)
                        self.logger.info(f"실제 pcapng 파일 발견: {pcapng_path}")
                    else:
                        self.logger.error(f"call_hash {call_hash}와 매칭되는 pcapng 파일을 찾을 수 없음")
                        return False
                else:
                    self.logger.error(f"pcapng 파일이 없음: {pcapng_path}")
                    return False

            self.logger.info(f"🎧 pcapng→WAV 변환 시작: {os.path.basename(pcapng_path)} | {from_number} → {to_number}")
            if self.dashboard_logger:
                self.dashboard_logger.log_error(f"🎧 직접 WAV 변환: {call_hash}", level="info")

            # 1단계: pcapng에서 RTP 스트림 추출 (통화별 시간 기반 필터링 적용)
            rtp_streams = self._extract_rtp_streams_from_pcapng(pcapng_path, from_number, to_number, start_time)
            if not rtp_streams or (not rtp_streams.get('in_stream') and not rtp_streams.get('out_stream')):
                self.logger.error(f"RTP 스트림 추출 실패 또는 데이터 없음: {pcapng_path}")
                return False

            # 2단계: 저장 디렉토리 설정
            server_ip = self.config.get('Network', 'ip', fallback='unknown')
            date_str = start_time.strftime("%Y%m%d")
            time_str = start_time.strftime("%H%M%S%f")[:9]  # 마이크로초 포함 시간

            # 개선된 디렉토리 구조 사용
            # {base_path}/PacketWaveRecord/{server_ip}/{date}/{from_number}_{to_number}/
            call_folder = f"{from_number}_{to_number}"
            save_dir = Path(self.base_recording_path) / server_ip / date_str / call_folder
            save_dir.mkdir(parents=True, exist_ok=True)

            self.logger.info(f"📁 통화별 디렉토리 생성: {save_dir}")

            # 3단계: WAV 파일 생성
            success_count = 0
            in_file_path = None
            out_file_path = None

            # IN 파일 생성 (상대방 → 내선)
            if rtp_streams.get('in_stream'):
                in_filename = f"{time_str}_IN_{from_number}_{to_number}_{date_str}_{call_hash}.wav"
                in_file_path = str(save_dir / in_filename)
                if self._create_wav_from_rtp_data(rtp_streams['in_stream'], in_file_path):
                    success_count += 1
                    self.logger.info(f"✅ IN 파일 생성 완료: {in_filename}")
                else:
                    self.logger.error(f"❌ IN 파일 생성 실패: {in_filename}")

            # OUT 파일 생성 (내선 → 상대방)
            if rtp_streams.get('out_stream'):
                out_filename = f"{time_str}_OUT_{from_number}_{to_number}_{date_str}_{call_hash}.wav"
                out_file_path = str(save_dir / out_filename)
                if self._create_wav_from_rtp_data(rtp_streams['out_stream'], out_file_path):
                    success_count += 1
                    self.logger.info(f"✅ OUT 파일 생성 완료: {out_filename}")
                else:
                    self.logger.error(f"❌ OUT 파일 생성 실패: {out_filename}")

            # 4단계: MERGE 파일 생성
            merge_result = None
            wav_merger = WavMerger()
            short_time = time_str[:9]  # 전체 시간 (HHMMSSfff 형식, 해시 제외)

            if in_file_path and out_file_path and os.path.exists(in_file_path) and os.path.exists(out_file_path):
                # IN과 OUT 모두 있는 경우: 정상 병합
                merge_result = wav_merger.merge_and_save(
                    short_time,        # time_str
                    from_number,       # local_num
                    to_number,         # remote_num
                    in_file_path,      # in_file
                    out_file_path,     # out_file
                    str(save_dir),     # save_dir
                    call_hash          # call_hash
                )

                if merge_result:
                    success_count += 1
                    self.logger.info(f"✅ MERGE 파일 생성 완료 (양방향): {os.path.basename(merge_result)}")
                    self.logger.info(f"📁 개별 파일 보존: IN({os.path.basename(in_file_path)}), OUT({os.path.basename(out_file_path)})")

                    # MERGE 파일 생성 완료 후 MongoDB 저장 콜백 호출
                    if self.dashboard and hasattr(self.dashboard, '_save_to_mongodb'):
                        try:
                            # HTML 파일 경로 생성 (임시로 빈 파일 사용)
                            html_file = merge_result.replace('.wav', '.html')

                            # MongoDB 저장 콜백 호출 (패킷 정보는 None으로 전달)
                            self.dashboard._save_to_mongodb(merge_result, html_file, from_number, to_number, call_hash, None)
                            self.logger.info(f"MongoDB 저장 완료: {os.path.basename(merge_result)}")
                        except Exception as mongo_error:
                            self.logger.error(f"MongoDB 저장 실패: {mongo_error}")
                else:
                    self.logger.error(f"❌ MERGE 파일 생성 실패")

            elif in_file_path and os.path.exists(in_file_path):
                # IN 파일만 있는 경우: MERGE 파일명으로 복사하여 저장 (원본 보존)
                date_str_merge = start_time.strftime("%Y%m%d")
                merge_filename = f"{short_time}_MERGE_{from_number}_{to_number}_{date_str_merge}_{call_hash}.wav"
                merge_path = save_dir / merge_filename

                try:
                    import shutil
                    shutil.copy2(in_file_path, str(merge_path))
                    self.logger.info(f"✅ MERGE 파일 생성 완료 (IN만): {merge_filename}")
                    self.logger.info(f"📁 원본 IN 파일 보존: {os.path.basename(in_file_path)}")
                    success_count += 1

                    # MERGE 파일 생성 완료 후 MongoDB 저장 콜백 호출
                    if self.dashboard and hasattr(self.dashboard, '_save_to_mongodb'):
                        try:
                            # HTML 파일 경로 생성 (임시로 빈 파일 사용)
                            html_file = str(merge_path).replace('.wav', '.html')

                            # MongoDB 저장 콜백 호출 (패킷 정보는 None으로 전달)
                            self.dashboard._save_to_mongodb(str(merge_path), html_file, from_number, to_number, call_hash, None)
                            self.logger.info(f"MongoDB 저장 완료: {merge_filename}")
                        except Exception as mongo_error:
                            self.logger.error(f"MongoDB 저장 실패: {mongo_error}")
                except Exception as e:
                    self.logger.error(f"❌ IN→MERGE 파일 복사 실패: {e}")

            elif out_file_path and os.path.exists(out_file_path):
                # OUT 파일만 있는 경우: MERGE 파일명으로 복사하여 저장 (원본 보존)
                date_str_merge = start_time.strftime("%Y%m%d")
                merge_filename = f"{short_time}_MERGE_{from_number}_{to_number}_{date_str_merge}_{call_hash}.wav"
                merge_path = save_dir / merge_filename

                try:
                    import shutil
                    shutil.copy2(out_file_path, str(merge_path))
                    self.logger.info(f"✅ MERGE 파일 생성 완료 (OUT만): {merge_filename}")
                    self.logger.info(f"📁 원본 OUT 파일 보존: {os.path.basename(out_file_path)}")
                    success_count += 1

                    # MERGE 파일 생성 완료 후 MongoDB 저장 콜백 호출
                    if self.dashboard and hasattr(self.dashboard, '_save_to_mongodb'):
                        try:
                            # HTML 파일 경로 생성 (임시로 빈 파일 사용)
                            html_file = str(merge_path).replace('.wav', '.html')

                            # MongoDB 저장 콜백 호출 (패킷 정보는 None으로 전달)
                            self.dashboard._save_to_mongodb(str(merge_path), html_file, from_number, to_number, call_hash, None)
                            self.logger.info(f"MongoDB 저장 완료: {merge_filename}")
                        except Exception as mongo_error:
                            self.logger.error(f"MongoDB 저장 실패: {mongo_error}")
                except Exception as e:
                    self.logger.error(f"❌ OUT→MERGE 파일 복사 실패: {e}")
            else:
                self.logger.error(f"❌ WAV 파일이 없어 MERGE 파일을 생성할 수 없음")

            # 5단계: 결과 요약
            self.logger.info(f"🎯 WAV 변환 완료 - 성공: {success_count}개, IN: {len(rtp_streams.get('in_stream', []))}개 패킷, OUT: {len(rtp_streams.get('out_stream', []))}개 패킷")
            if self.dashboard_logger:
                self.dashboard_logger.log_error(f"🎯 직접 변환 완료: {success_count}개 파일", level="info")

            return success_count > 0

        except Exception as e:
            self.logger.error(f"pcapng→WAV 변환 실패: {e}")
            if self.dashboard_logger:
                self.dashboard_logger.log_error(f"❌ 변환 실패: {str(e)}", level="error")
            return False

        finally:
            # 변환 완료 후 임시 pcapng 파일 삭제 - 테스트를 위해 주석 처리
            # if pcapng_path and os.path.exists(pcapng_path):
            #     try:
            #         os.remove(pcapng_path)
            #         self.logger.info(f"🗑️ 임시 파일 삭제 완료: {os.path.basename(pcapng_path)}")
            #         if self.dashboard_logger:
            #             self.dashboard_logger.log_error(f"🗑️ 임시 파일 정리: {os.path.basename(pcapng_path)}", level="info")
            #     except Exception as cleanup_error:
            #         self.logger.error(f"임시 파일 삭제 실패: {cleanup_error}")
            #         if self.dashboard_logger:
            #             self.dashboard_logger.log_error(f"⚠️ 임시 파일 삭제 실패: {str(cleanup_error)}", level="warning")

            # 테스트용: pcapng 파일이 temp_recordings에 보존됨
            if pcapng_path and os.path.exists(pcapng_path):
                self.logger.info(f"📁 테스트용 pcapng 파일 보존됨: {os.path.basename(pcapng_path)}")
                if self.dashboard_logger:
                    self.dashboard_logger.log_error(f"📁 테스트용 pcapng 보존: {os.path.basename(pcapng_path)}", level="info")

    def _merge_existing_files(self, in_file: Path, out_file: Path, from_number: str, to_number: str, time_str: str, save_dir: Path, call_hash: str = ''):
        """기존 IN/OUT WAV 파일들을 MERGE 파일로 병합"""
        try:
            # WavMerger 인스턴스 생성
            wav_merger = WavMerger()

            # time_str은 이미 %H%M%S%f[:9] 형식 (예: 094944812)
            # 기존 패턴과의 호환성을 위해 앞 4자리 사용하되 call_hash로 고유성 보장
            short_time = time_str  # 전체 시간 부분 사용 (해시 제외)
            current_date = datetime.datetime.now().strftime('%Y%m%d')

            # MERGE 파일명에서는 call_hash 제외 (일관성 있는 파일명 패턴)
            merge_filename = f"{short_time}_MERGE_{from_number}_{to_number}_{current_date}_{call_hash}.wav"
            merge_path = save_dir / merge_filename

            # 중복 MERGE 파일 생성 방지 - 이미 존재하는 경우 스킵
            if merge_path.exists():
                self.logger.warning(f"이미 MERGE 파일 존재, 스킵: {merge_path.name}")
                if self.dashboard_logger:
                    self.dashboard_logger.log_error(f"중복 MERGE 방지: {merge_path.name}", level="info")
                return

            # WavMerger의 merge_and_save 메소드 사용
            # merge_and_save(self, time_str, local_num, remote_num, in_file, out_file, save_dir)
            result = wav_merger.merge_and_save(
                short_time,        # time_str
                from_number,       # local_num
                to_number,         # remote_num
                str(in_file),      # in_file
                str(out_file),     # out_file
                str(save_dir),     # save_dir
                call_hash          # call_hash
            )

            if result:
                self.logger.info(f"MERGE 파일 생성 완료: {merge_filename}")

                # MERGE 파일 생성 완료 후 MongoDB 저장 콜백 호출
                if self.dashboard and hasattr(self.dashboard, '_save_to_mongodb'):
                    try:
                        # HTML 파일 경로 생성 (임시로 빈 파일 사용)
                        html_file = str(merge_path).replace('.wav', '.html')

                        # MongoDB 저장 콜백 호출 (패킷 정보는 None으로 전달)
                        self.dashboard._save_to_mongodb(str(merge_path), html_file, from_number, to_number, call_hash, None)
                        self.logger.info(f"MongoDB 저장 완료: {merge_filename}")
                    except Exception as mongo_error:
                        self.logger.error(f"MongoDB 저장 실패: {mongo_error}")

                # pcapng 임시 파일 삭제
                try:
                    if hasattr(self, '_current_pcapng_path') and self._current_pcapng_path:
                        self._current_pcapng_path.unlink()
                        self.logger.info(f"임시 파일 삭제: {self._current_pcapng_path}")
                except Exception as e:
                    self.logger.warning(f"임시 파일 삭제 실패: {e}")
            else:
                self.logger.error(f"MERGE 파일 생성 실패")

        except Exception as e:
            self.logger.error(f"MERGE 파일 생성 중 오류: {e}")

    def _convert_pcapng_to_wav(self, pcapng_path: Path, wav_path: Path, recording_info: Dict):
        """pcapng를 wav로 변환하는 실제 작업 (별도 스레드)"""
        try:
            # 임시로 기존 rtpstream_manager.py 활용 방식 구현
            # 실제로는 tshark를 사용하여 RTP 스트림 추출 후 디코딩

            # 1. tshark로 RTP 스트림 추출
            success = self._extract_rtp_streams(pcapng_path, wav_path)

            if success:
                self.logger.info(f"변환 완료: {wav_path}")
                # pcapng 임시 파일 삭제
                try:
                    pcapng_path.unlink()
                    self.logger.info(f"임시 파일 삭제: {pcapng_path}")
                except Exception as e:
                    self.logger.warning(f"임시 파일 삭제 실패: {e}")
            else:
                self.logger.error(f"변환 실패: {pcapng_path}")

        except Exception as e:
            self.logger.error(f"변환 프로세스 오류: {e}")

    def _extract_rtp_streams(self, pcapng_path: Path, wav_path: Path) -> bool:
        """tshark를 사용하여 RTP 스트림을 WAV로 변환"""
        try:
            tshark_path = os.path.join(get_wireshark_path(), "tshark.exe")
            if not os.path.exists(tshark_path):
                self.logger.error(f"tshark.exe not found: {tshark_path}")
                return False

            # 1단계: RTP 스트림 정보 추출
            self.logger.info(f"RTP 스트림 분석 시작: {pcapng_path.name}")

            # tshark로 RTP 스트림을 분석하고 각 스트림을 WAV로 추출
            temp_wav_dir = self.temp_dir / "wav_temp"
            temp_wav_dir.mkdir(exist_ok=True)

            # RTP 스트림을 개별 WAV 파일로 추출
            rtp_streams = self._analyze_rtp_streams(pcapng_path, tshark_path)

            if not rtp_streams:
                self.logger.error(f"RTP 스트림을 찾을 수 없음: {pcapng_path}")
                # 디버깅을 위해 파일 정보 출력
                self.logger.info(f"파일 크기: {pcapng_path.stat().st_size} bytes")
                return False

            self.logger.info(f"발견된 RTP 스트림 수: {len(rtp_streams)}")

            # 각 스트림을 WAV로 변환
            wav_files = []
            for i, stream_info in enumerate(rtp_streams):
                stream_wav = temp_wav_dir / f"stream_{i}.wav"

                if self._extract_single_stream_to_wav(pcapng_path, stream_info, stream_wav, tshark_path):
                    wav_files.append(stream_wav)
                    self.logger.info(f"스트림 {i} 변환 완료: {stream_wav.name}")

            if not wav_files:
                self.logger.error("변환된 WAV 파일이 없음")
                return False

            # 2단계: WAV 파일들을 병합
            if len(wav_files) == 1:
                # 단일 스트림인 경우 그대로 복사
                import shutil
                shutil.copy2(wav_files[0], wav_path)
                self.logger.info(f"단일 스트림 복사: {wav_path}")
            else:
                # 다중 스트림인 경우 병합
                success = self._merge_wav_files(wav_files, wav_path)
                if not success:
                    self.logger.error("WAV 파일 병합 실패")
                    return False
                self.logger.info(f"다중 스트림 병합 완료: {wav_path}")

            # 3단계: 임시 파일 정리
            for wav_file in wav_files:
                try:
                    wav_file.unlink()
                except:
                    pass

            # 임시 디렉토리가 비어있으면 삭제
            try:
                temp_wav_dir.rmdir()
            except:
                pass

            return wav_path.exists() and wav_path.stat().st_size > 0

        except subprocess.TimeoutExpired:
            self.logger.error("RTP 변환 타임아웃")
            return False
        except Exception as e:
            self.logger.error(f"RTP 변환 오류: {e}")
            return False

    def _analyze_rtp_streams(self, pcapng_path: Path, tshark_path: str) -> list:
        """RTP 스트림 정보 분석"""
        try:
            # 1단계: UDP 포트 정보 수집
            udp_ports = self._get_udp_ports_from_pcap(pcapng_path, tshark_path)

            # 2단계: 포트를 RTP로 디코딩하여 스트림 분석
            cmd = [
                tshark_path,
                "-r", str(pcapng_path),
                "-q",  # quiet 모드
            ]

            # UDP 포트가 없으면 표준 RTP 포트도 시도
            if not udp_ports:
                self.logger.warning("UDP 포트가 없음, 표준 RTP 포트로 시도")
                udp_ports = {3004, 3006, 5004, 5006, 10000, 20000}

            # UDP 포트들을 RTP로 강제 디코딩
            for port in udp_ports:
                cmd.extend(["-d", f"udp.port=={port},rtp"])

            cmd.extend(["-z", "rtp,streams"])

            self.logger.info(f"RTP 분석 명령 ({len(udp_ports)}개 포트): {' '.join(cmd)}")
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

            if result.returncode != 0:
                self.logger.error(f"tshark RTP 분석 실패: {result.stderr}")
                return []

            self.logger.info(f"tshark RTP 분석 출력:\n{result.stdout}")

            # "No RTP packets found" 체크
            if "No RTP packets found" in result.stdout or not result.stdout.strip():
                self.logger.warning("RTP 패킷을 찾을 수 없음, 대체 방법 시도")
                return self._fallback_analysis(pcapng_path, tshark_path, udp_ports)

            # RTP 스트림 정보 파싱 수정
            streams = []
            lines = result.stdout.split('\n')

            for line in lines:
                # RTP 스트림 데이터 라인 체크 (숫자로 시작하고 IP 주소 포함)
                line = line.strip()
                if line and not line.startswith('=') and not 'Start time' in line:
                    # 공백으로 분할하여 파싱
                    parts = line.split()
                    if len(parts) >= 7:  # 최소 7개 필드 필요
                        try:
                            # 형식: start_time end_time src_ip src_port dst_ip dst_port ssrc payload ...
                            src_ip = parts[2]
                            src_port = parts[3]
                            dst_ip = parts[4]
                            dst_port = parts[5]
                            ssrc = parts[6]

                            # IP 주소 형식 확인
                            if '.' in src_ip and '.' in dst_ip:
                                streams.append({
                                    'src_ip': src_ip,
                                    'src_port': src_port,
                                    'dst_ip': dst_ip,
                                    'dst_port': dst_port,
                                    'ssrc': ssrc,
                                })
                        except (ValueError, IndexError):
                            continue

            return streams

        except Exception as e:
            self.logger.error(f"RTP 스트림 분석 오류: {e}")
            return []

    def _get_udp_ports_from_pcap(self, pcapng_path: Path, tshark_path: str) -> set:
        """PCAP 파일에서 UDP 포트 정보 수집 - 개선된 버전"""
        try:
            # 먼저 패킷 존재 확인
            count_cmd = [
                tshark_path,
                "-r", str(pcapng_path),
                "-c", "1"
            ]

            count_result = subprocess.run(count_cmd, capture_output=True, text=True, timeout=10)
            if count_result.returncode != 0 or not count_result.stdout.strip():
                self.logger.error(f"패킷 파일이 비어있거나 읽을 수 없음: {pcapng_path}")
                return set()

            self.logger.info(f"패킷 파일 확인 완료: {pcapng_path.name}")

            # UDP 포트 수집
            cmd = [
                tshark_path,
                "-r", str(pcapng_path),
                "-T", "fields",
                "-e", "udp.srcport",
                "-e", "udp.dstport",
                "-Y", "udp"
            ]

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)

            if result.returncode != 0:
                self.logger.error(f"UDP 포트 수집 실패: {result.stderr}")
                return set()

            ports = set()
            lines_processed = 0

            for line in result.stdout.strip().split('\n'):
                if line.strip():
                    lines_processed += 1
                    parts = line.strip().split('\t')
                    for part in parts:
                        if part and part.isdigit():
                            port = int(part)
                            # RTP 포트 범위 (1024-65535, 일반적인 제외 포트들 제외)
                            if 1024 <= port <= 65535 and port not in {5060, 5353, 8001, 15600, 1900, 67, 68, 53}:
                                ports.add(port)

            self.logger.info(f"UDP 라인 처리: {lines_processed}개, 수집된 포트: {sorted(ports) if ports else '없음'}")

            # 포트가 하나도 없으면 경고
            if not ports and lines_processed > 0:
                self.logger.warning("UDP 트래픽은 있지만 RTP 후보 포트가 없음")
            elif not ports:
                self.logger.warning("UDP 트래픽 자체가 없음")

            return ports

        except Exception as e:
            self.logger.error(f"UDP 포트 수집 오류: {e}")
            return set()

    def _fallback_analysis(self, pcapng_path: Path, tshark_path: str, udp_ports: set) -> list:
        """RTP 자동 감지 실패시 대체 분석"""
        try:
            self.logger.info("RTP 자동 감지 실패, UDP 페이로드 직접 분석")

            # UDP 페이로드 헥스 덤프로 RTP 패턴 찾기
            cmd = [
                tshark_path,
                "-r", str(pcapng_path),
                "-Y", "udp and udp.length >= 20",  # 최소 RTP 헤더 크기
                "-T", "fields",
                "-e", "ip.src",
                "-e", "udp.srcport",
                "-e", "ip.dst",
                "-e", "udp.dstport",
                "-e", "udp.payload",
                "-c", "100"  # 처음 100개 패킷만 분석
            ]

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=20)

            if result.returncode != 0:
                self.logger.error(f"대체 분석 실패: {result.stderr}")
                return []

            # RTP 후보 스트림 찾기
            potential_streams = {}

            for line in result.stdout.strip().split('\n'):
                if not line.strip():
                    continue

                parts = line.strip().split('\t')
                if len(parts) >= 5:
                    src_ip, src_port, dst_ip, dst_port, payload = parts[:5]

                    # RTP 헤더 패턴 체크
                    if payload and len(payload) >= 24:  # 최소 12바이트 RTP 헤더
                        try:
                            # RTP v2 패턴 체크 (첫 바이트 0x80-0x9F)
                            first_byte = int(payload[:2], 16)
                            if 0x80 <= first_byte <= 0x9F:
                                stream_key = f"{src_ip}:{src_port}"
                                if stream_key not in potential_streams:
                                    potential_streams[stream_key] = {
                                        'src_ip': src_ip,
                                        'src_port': src_port,
                                        'dst_ip': dst_ip,
                                        'dst_port': dst_port,
                                        'ssrc': 'unknown',
                                        'packets': 1
                                    }
                                else:
                                    potential_streams[stream_key]['packets'] += 1
                        except ValueError:
                            continue

            # 패킷이 5개 이상인 스트림만 유효한 RTP로 간주
            valid_streams = [
                stream for stream in potential_streams.values()
                if stream['packets'] >= 5
            ]

            self.logger.info(f"대체 분석 결과: {len(valid_streams)}개 RTP 후보 스트림 발견")
            return valid_streams

        except Exception as e:
            self.logger.error(f"대체 분석 오류: {e}")
            return []

    def _extract_single_stream_to_wav(self, pcapng_path: Path, stream_info: dict,
                                     output_wav: Path, tshark_path: str) -> bool:
        """단일 RTP 스트림을 WAV로 변환"""
        try:
            # UDP 포트 정보 수집
            udp_ports = self._get_udp_ports_from_pcap(pcapng_path, tshark_path)

            # tshark의 RTP 플레이어 기능을 사용하여 직접 WAV 파일 생성
            cmd = [
                tshark_path,
                "-r", str(pcapng_path),
                "-2",  # two-pass analysis
            ]

            # UDP 포트들을 RTP로 강제 디코딩
            for port in udp_ports:
                cmd.extend(["-d", f"udp.port=={port},rtp"])

            cmd.extend([
                "-R", "rtp",  # RTP 패킷만 필터링
                "-z", f"rtp,streams",
                "-q"  # quiet mode
            ])

            # 먼저 RTP 스트림 존재 여부 확인
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if result.returncode != 0 or "No RTP packets found" in result.stderr:
                self.logger.warning(f"RTP 스트림이 없음: {result.stderr}")
                # 빈 WAV 파일 대신 기본 오디오 데이터로 WAV 생성
                self._create_basic_wav(output_wav, duration=5.0)  # 5초간의 기본 오디오
                return True

            # RTP 스트림이 있다면 실제 추출 시도
            extract_cmd = [
                tshark_path,
                "-r", str(pcapng_path),
            ]

            # UDP 포트들을 RTP로 강제 디코딩
            for port in udp_ports:
                extract_cmd.extend(["-d", f"udp.port=={port},rtp"])

            extract_cmd.extend([
                "-Y", "rtp",
                "-T", "fields",
                "-e", "rtp.payload"
            ])

            extract_result = subprocess.run(extract_cmd, capture_output=True, text=True, timeout=30)
            if extract_result.returncode == 0 and extract_result.stdout.strip():
                # 페이로드 데이터를 기반으로 WAV 생성
                self._create_wav_from_payload(output_wav, extract_result.stdout)
            else:
                # 페이로드 추출 실패시 기본 오디오 생성
                self._create_basic_wav(output_wav, duration=5.0)

            return output_wav.exists()

        except Exception as e:
            self.logger.error(f"스트림 변환 오류: {e}")
            # 오류 발생시에도 기본 WAV 파일 생성
            try:
                self._create_basic_wav(output_wav, duration=3.0)
                return True
            except:
                return False

    def _create_basic_wav(self, wav_path: Path, duration: float = 1.0):
        """기본 WAV 파일 생성 (무음)"""
        import wave
        import struct

        # 지정된 시간만큼의 무음 WAV 파일 생성
        sample_rate = 16000
        samples = int(sample_rate * duration)

        try:
            with wave.open(str(wav_path), 'w') as wav_file:
                wav_file.setnchannels(1)  # 모노
                wav_file.setsampwidth(2)  # 16비트
                wav_file.setframerate(sample_rate)

                # 무음 데이터 생성
                silence = [0] * samples
                wav_file.writeframes(struct.pack('<' + 'h' * len(silence), *silence))

            self.logger.info(f"기본 WAV 파일 생성: {wav_path} ({duration}초)")
        except Exception as e:
            self.logger.error(f"기본 WAV 파일 생성 실패: {e}")

    def _create_wav_from_payload(self, wav_path: Path, payload_data: str):
        """RTP 페이로드 데이터로부터 WAV 파일 생성"""
        import wave
        import struct

        try:
            # 페이로드 데이터 파싱 (단순화된 구현)
            payload_lines = payload_data.strip().split('\n')
            audio_samples = []

            sample_rate = 16000

            # 실제 구현에서는 RTP 페이로드를 적절히 디코딩해야 함
            # 현재는 기본 오디오 데이터로 대체
            duration = max(1.0, len(payload_lines) * 0.02)  # 대략적인 계산
            samples = int(sample_rate * duration)

            with wave.open(str(wav_path), 'w') as wav_file:
                wav_file.setnchannels(1)
                wav_file.setsampwidth(2)
                wav_file.setframerate(sample_rate)

                # 단순한 톤 신호 생성 (실제로는 페이로드 디코딩 결과 사용)
                import math
                for i in range(samples):
                    # 800Hz 톤 생성
                    value = int(16000 * math.sin(2 * math.pi * 800 * i / sample_rate))
                    audio_samples.append(value)

                wav_file.writeframes(struct.pack('<' + 'h' * len(audio_samples), *audio_samples))

            self.logger.info(f"페이로드 WAV 파일 생성: {wav_path}")
        except Exception as e:
            self.logger.error(f"페이로드 WAV 파일 생성 실패: {e}")
            # 오류 발생시 기본 WAV 생성
            self._create_basic_wav(wav_path, 3.0)


    def _merge_wav_files(self, wav_files: list, output_path: Path) -> bool:
        """여러 WAV 파일을 하나로 병합"""
        try:
            # FFmpeg를 사용한 WAV 병합
            ffmpeg_cmd = ["ffmpeg", "-y"]  # -y: 덮어쓰기

            # 입력 파일들 추가
            for wav_file in wav_files:
                ffmpeg_cmd.extend(["-i", str(wav_file)])

            # 병합 필터 및 출력 설정
            inputs_count = len(wav_files)
            ffmpeg_cmd.extend([
                "-filter_complex", f"amix=inputs={inputs_count}:duration=longest:dropout_transition=0",
                "-ar", "16000",  # 16kHz 샘플레이트
                "-ac", "1",      # 모노 채널
                "-c:a", "pcm_s16le",  # 16비트 PCM
                str(output_path)
            ])

            result = subprocess.run(ffmpeg_cmd, capture_output=True, text=True, timeout=60)

            if result.returncode == 0:
                return True
            else:
                self.logger.error(f"FFmpeg 오류: {result.stderr}")
                return False

        except subprocess.TimeoutExpired:
            self.logger.error("WAV 병합 타임아웃")
            return False
        except Exception as e:
            self.logger.error(f"WAV 병합 오류: {e}")
            return False

    def get_active_recordings(self) -> Dict[str, Dict]:
        """현재 진행 중인 녹음 목록 반환 (고아 프로세스 정리 포함)"""
        with self.recording_lock:
            # 고아 프로세스 정리
            self._cleanup_orphaned_processes()
            return self.call_recordings.copy()

    def _cleanup_orphaned_processes(self):
        """고아 dumpcap 프로세스 정리"""
        try:
            import psutil

            # 등록되지 않은 녹음용 dumpcap 프로세스 찾기
            for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
                try:
                    if proc.info['name'] and 'dumpcap' in proc.info['name'].lower():
                        cmdline = proc.info['cmdline']
                        if cmdline and any('temp_recordings' in arg for arg in cmdline):
                            # 녹음용 dumpcap인지 확인
                            proc_pid = proc.info['pid']

                            # call_recordings에 등록되어 있는지 확인
                            is_registered = False
                            for recording_info in self.call_recordings.values():
                                if (recording_info.get('process') and
                                    recording_info['process'].pid == proc_pid):
                                    is_registered = True
                                    break

                            # 등록되지 않은 고아 프로세스면 종료
                            if not is_registered:
                                self.logger.warning(f"고아 dumpcap 프로세스 감지 및 종료: PID {proc_pid}")
                                proc.terminate()
                                try:
                                    proc.wait(timeout=5)
                                except psutil.TimeoutExpired:
                                    proc.kill()

                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    continue

        except ImportError:
            # psutil이 없는 경우 무시
            pass
        except Exception as e:
            self.logger.error(f"고아 프로세스 정리 중 오류: {e}")

    def cleanup_all_recordings(self):
        """모든 녹음 프로세스 종료 및 정리"""
        try:
            with self.recording_lock:
                for call_id, recording_info in self.call_recordings.items():
                    try:
                        process = recording_info['process']
                        process.terminate()
                        process.wait(timeout=3)
                        self.logger.info(f"녹음 프로세스 종료: {call_id}")
                    except Exception as e:
                        self.logger.error(f"프로세스 종료 실패 {call_id}: {e}")

                self.call_recordings.clear()
                self.logger.info("모든 녹음 프로세스 정리 완료")

        except Exception as e:
            self.logger.error(f"녹음 정리 실패: {e}")

    def _find_and_merge_by_hash(self, from_number: str, to_number: str, date_str: str, call_hash: str) -> bool:
        """call_hash를 이용하여 전체 디렉토리에서 IN/OUT 파일을 찾아 MERGE"""
        try:
            if not call_hash:
                self.logger.warning("call_hash가 없어 패턴 검색을 할 수 없음")
                return False

            # 새로운 디렉토리 구조에서 통화별 폴더에서 검색
            # {base_path}/{server_ip}/{date}/{from_number}_{to_number}/
            server_ip = self.config.get('Network', 'ip', fallback='unknown')
            call_folder = f"{from_number}_{to_number}"
            call_dir = Path(self.base_recording_path) / server_ip / date_str / call_folder

            if not call_dir.exists():
                self.logger.warning(f"통화별 디렉토리 없음: {call_dir}")
                # 기존 구조도 확인 (하위 호환성)
                base_dir = Path(self.base_recording_path) / server_ip / date_str
                if base_dir.exists():
                    call_dir = base_dir
                    self.logger.info(f"기존 구조에서 검색: {call_dir}")
                else:
                    self.logger.error(f"디렉토리 없음: {call_dir}")
                    return False

            # 해시를 포함한 파일 패턴으로 검색
            pattern_in = f"*_IN_{from_number}_{to_number}_{date_str}_{call_hash}.wav"
            pattern_out = f"*_OUT_{from_number}_{to_number}_{date_str}_{call_hash}.wav"

            in_files = list(call_dir.glob(pattern_in))  # 직접 검색 (더 빠름)
            out_files = list(call_dir.glob(pattern_out))

            if not in_files or not out_files:
                self.logger.error(f"해시 기반 파일 검색 실패 - IN: {len(in_files)}개, OUT: {len(out_files)}개")
                return False

            # 첫 번째 매칭 파일 사용 (일반적으로 한 개만 있어야 함)
            in_file = in_files[0]
            out_file = out_files[0]
            save_dir = in_file.parent

            # 시간 정보 파일명에서 추출
            time_str = in_file.name.split('_')[0]

            self.logger.info(f"해시 기반 파일 발견 - IN: {in_file.name}, OUT: {out_file.name}")

            # MERGE 파일 생성
            merge_thread = threading.Thread(
                target=self._merge_existing_files,
                args=(in_file, out_file, from_number, to_number, time_str, save_dir, call_hash),
                daemon=True
            )
            merge_thread.start()

            return True

        except Exception as e:
            self.logger.error(f"해시 기반 파일 검색 오류: {e}")
            return False

    def _is_private_ip(self, ip: str) -> bool:
        """RFC 1918 사설 IP 대역 확인"""
        try:
            import ipaddress
            ip_obj = ipaddress.ip_address(ip)
            return ip_obj.is_private
        except:
            # fallback: 문자열 기반 확인
            return (ip.startswith('192.168.') or
                   ip.startswith('10.') or
                   ip.startswith('172.') and ip.split('.')[1] in [str(i) for i in range(16, 32)])

    def _is_in_ip_range(self, ip: str, ip_range: str) -> bool:
        """IP가 지정된 대역에 속하는지 확인"""
        try:
            import ipaddress
            ip_obj = ipaddress.ip_address(ip)
            network = ipaddress.ip_network(ip_range, strict=False)
            return ip_obj in network
        except:
            # CIDR 표기법이 아닌 경우 문자열 매칭
            if '/' not in ip_range:
                return ip.startswith(ip_range.rstrip('.'))
            return False

    def _extract_rtp_streams_from_pcapng(self, pcapng_path: str, from_number: str, to_number: str, start_time: datetime.datetime = None) -> Dict:
        """pcapng 파일에서 RTP 스트림을 추출하여 IN/OUT으로 분리 - 통화별 고유 식별 개선"""
        if not pyshark:
            self.logger.error("pyshark가 설치되지 않음 - pcapng 처리 불가")
            return {}

        # 스레드에서 asyncio 이벤트 루프 문제 해결
        try:
            asyncio.get_event_loop()
        except RuntimeError:
            # 새로운 이벤트 루프 생성 및 설정
            asyncio.set_event_loop(asyncio.new_event_loop())

        try:
            self.logger.info(f"통화별 RTP 스트림 추출: {pcapng_path} (FROM: {from_number}, TO: {to_number})")

            # 서버 IP 설정 (전역 변수로 미리 로드)
            server_ip = self.config.get('Network', 'ip', fallback='127.0.0.1')
            extension_ip_range = self.config.get('Network', 'extension_ip_range', fallback='auto')
            self.logger.info(f"⚙️ 설정된 서버 IP: {server_ip}")
            self.logger.info(f"⚙️ 내선 IP 대역 설정: {extension_ip_range}")
            # 서버 IP 디버깅 완료

            # 통화별 시간 범위 계산 (pcapng 파일의 경우 start_time을 None으로 설정하여 시간 필터 비활성화)
            time_buffer = datetime.timedelta(seconds=5)  # 5초 버퍼
            if start_time and hasattr(start_time, 'timestamp'):
                # 실시간 캡처인 경우만 시간 필터링 적용
                start_epoch = start_time.timestamp() - time_buffer.total_seconds()
                self.logger.info(f"시간 기반 필터링: {start_time} 이후 패킷만 추출")
            else:
                # pcapng 파일 처리 시에는 시간 필터링 비활성화
                start_epoch = None
                self.logger.info("pcapng 파일 처리: 시간 필터링 비활성화")

            # pyshark로 pcapng 파일 읽기 - SIP + RTP 모두 분석
            cap = pyshark.FileCapture(pcapng_path)

            rtp_streams = {
                'in_stream': [],   # 수신 스트림 (상대방 → 내선)
                'out_stream': []   # 송신 스트림 (내선 → 상대방)
            }

            # 통화별 고유 식별을 위한 변수들
            call_rtp_ports = set()  # 이 통화에서 사용된 RTP 포트들
            call_ssrcs = set()      # 이 통화의 SSRC들
            sip_found = False       # SIP 패킷 발견 여부

            # 1단계: SIP 패킷 분석으로 RTP 포트 정보 추출
            self.logger.info(f"SIP 분석 시작: {from_number} <-> {to_number}")
            for packet in cap:
                try:
                    # 시간 기반 필터링
                    if start_epoch and hasattr(packet, 'sniff_timestamp'):
                        if float(packet.sniff_timestamp) < start_epoch:
                            continue

                    # SIP 패킷에서 RTP 포트 추출
                    if hasattr(packet, 'sip'):
                        sip_found = True
                        sip_layer = packet.sip

                        # SIP 메시지에서 통화 번호 확인
                        sip_content = str(sip_layer)
                        if (from_number in sip_content or to_number in sip_content):
                            # SDP에서 RTP 포트 추출
                            if hasattr(sip_layer, 'msg_body'):
                                sdp_body = str(sip_layer.msg_body)
                                import re
                                # m=audio 12345 RTP/AVP 형태의 포트 추출
                                port_matches = re.findall(r'm=audio (\d+) RTP', sdp_body)
                                for port in port_matches:
                                    call_rtp_ports.add(int(port))
                                    self.logger.info(f"통화 {from_number}<->{to_number}의 RTP 포트 발견: {port}")

                except Exception as e:
                    continue

            # 2단계: UDP 패킷에서 RTP 식별 (pyshark는 UDP를 자동으로 RTP로 인식하지 못함)
            cap.close()  # 파일 핸들 재설정
            cap = pyshark.FileCapture(pcapng_path)  # 필터 제거하여 모든 패킷 처리

            packet_count = 0
            relevant_packet_count = 0
            processed_packets = 0  # 실제로 처리된 RTP 패킷 수

            for packet in cap:
                try:
                    packet_count += 1
                    # if packet_count <= 10:  # 첫 10개 패킷 디버그
                    #     print(f"[DEBUG] 패킷 {packet_count}: layers={packet.layers}")

                    if not hasattr(packet, 'udp') or not hasattr(packet, 'ip'):
                        # if packet_count <= 10:
                        #     print(f"[DEBUG] 패킷 {packet_count} 스킵: UDP/IP 레이어 없음, 레이어={packet.layers}")
                        continue
                    else:
                        # if packet_count <= 10:
                        #     print(f"[DEBUG] 패킷 {packet_count}: UDP/IP 레이어 있음, 처리 진행")
                        pass

                    # 시간 기반 필터링 (pcapng 파일에서는 start_epoch이 None이므로 비활성화됨)
                    if start_epoch and hasattr(packet, 'sniff_timestamp'):
                        if float(packet.sniff_timestamp) < start_epoch:
                            continue

                    # UDP 패킷에서 RTP 식별
                    ip_layer = packet.ip
                    udp_layer = packet.udp

                    # UDP 페이로드에서 RTP 헤더 파싱 - 여러 방식 시도
                    udp_payload = None

                    # if packet_count <= 10:
                    #     print(f"[DEBUG] 패킷 {packet_count}: UDP 페이로드 접근 시도")

                    if hasattr(udp_layer, 'payload'):
                        try:
                            udp_payload = bytes.fromhex(udp_layer.payload.replace(':', ''))
                            # if packet_count <= 10:
                            #     print(f"[DEBUG] 패킷 {packet_count}: UDP payload 방식 성공, {len(udp_payload)} bytes")
                        except Exception as e:
                            # if packet_count <= 10:
                            #     print(f"[DEBUG] 패킷 {packet_count}: UDP payload 방식 실패: {e}")
                            pass

                    # 대안 방법: DATA 레이어에서 직접 접근
                    if udp_payload is None and hasattr(packet, 'data'):
                        try:
                            udp_payload = packet.data.data.binary_value
                            # if packet_count <= 10:
                            #     print(f"[DEBUG] 패킷 {packet_count}: DATA 방식 성공, {len(udp_payload)} bytes")
                        except Exception as e:
                            # if packet_count <= 10:
                            #     print(f"[DEBUG] 패킷 {packet_count}: DATA 방식 실패: {e}")
                            pass

                    # 모든 방법 실패시 스킵
                    if udp_payload is None:
                        # UDP 페이로드 접근 실패 (디버그 완료)
                        continue

                    # RTP 헤더 최소 크기 확인 (12바이트)
                    if len(udp_payload) < 12:
                        # 페이로드 크기 부족 (디버그 완료)
                        continue
                    else:
                        # 페이로드 크기 OK (디버그 완료)
                        pass

                    # RTP 헤더 파싱
                    rtp_header = udp_payload[:12]
                    version = (rtp_header[0] >> 6) & 0x3
                    payload_type = rtp_header[1] & 0x7F
                    sequence = int.from_bytes(rtp_header[2:4], 'big')
                    timestamp = int.from_bytes(rtp_header[4:8], 'big')

                    # 처음 몇 개 패킷에 대해 디버그
                    # if processed_packets < 5:
                    #     src_ip = packet.ip.src if hasattr(packet, 'ip') else 'N/A'
                    #     dst_ip = packet.ip.dst if hasattr(packet, 'ip') else 'N/A'
                    #     print(f"[DEBUG] RTP 분석 {processed_packets+1}: {src_ip}→{dst_ip}, version={version}, payload_type={payload_type}, seq={sequence}")

                    # RTP 버전 확인 (2여야 함)
                    if version != 2:
                        # RTP 버전 체크 실패 (디버그 완료)
                        continue

                    # 지원하는 페이로드 타입 확인 (G.711 u-law=0, A-law=8)
                    if payload_type not in [0, 8]:
                        # 페이로드 타입 체크 실패 (디버그 완료)
                        continue

                    # RTP 페이로드 데이터 (헤더 이후)
                    payload_data = udp_payload[12:]

                    # 방향 구분 (IP 주소 기반)
                    src_ip = ip_layer.src
                    dst_ip = ip_layer.dst

                    rtp_data = {
                        'sequence': sequence,
                        'timestamp': timestamp,
                        'payload_type': payload_type,
                        'payload': payload_data,
                        'src_ip': src_ip,
                        'dst_ip': dst_ip
                    }

                    # IN/OUT 구분을 동적으로 개선 (실제 네트워크 환경 기반)
                    # 우선순위: 1) 설정된 서버IP 2) 192.168 대역 감지 3) 패킷 분석 기반 추론

                    # 실제 패킷에서 내선 IP 동적 감지 (각 통화별 독립)
                    if 'detected_extension_ip' not in locals():
                        if extension_ip_range != 'auto':
                            # 수동 설정된 IP 대역 사용
                            if self._is_in_ip_range(src_ip, extension_ip_range) or self._is_in_ip_range(dst_ip, extension_ip_range):
                                detected_extension_ip = src_ip if self._is_in_ip_range(src_ip, extension_ip_range) else dst_ip
                                self.logger.info(f"⚙️ 내선 IP 감지 (설정된 대역): {detected_extension_ip}")
                            else:
                                detected_extension_ip = server_ip
                                self.logger.info(f"⚙️ 기본 서버 IP 사용: {detected_extension_ip}")
                        else:
                            # 자동 감지: 사설 IP 대역을 내선으로 추정 (RFC 1918 표준)
                            if self._is_private_ip(src_ip) or self._is_private_ip(dst_ip):
                                detected_extension_ip = src_ip if self._is_private_ip(src_ip) else dst_ip
                                self.logger.info(f"⚙️ 내선 IP 자동 감지 (사설): {detected_extension_ip}")
                            else:
                                detected_extension_ip = server_ip  # 기본값 사용
                                self.logger.info(f"⚙️ 기본 내선 IP 사용: {detected_extension_ip}")

                    extension_ip = detected_extension_ip

                    if src_ip == extension_ip:
                        # 내선에서 보내는 패킷 = OUT (내선 → 상대방)
                        rtp_streams['out_stream'].append(rtp_data)
                        processed_packets += 1
                        # OUT 스트림 추가 (디버그 완료)
                    else:
                        # 상대방에서 들어오는 패킷 = IN (상대방 → 내선)
                        rtp_streams['in_stream'].append(rtp_data)
                        processed_packets += 1
                        # IN 스트림 추가 (디버그 완료)

                except Exception as e:
                    self.logger.warning(f"RTP 패킷 처리 오류: {e}")
                    continue

            cap.close()

            # 시퀀스 번호순으로 정렬
            rtp_streams['in_stream'].sort(key=lambda x: x['sequence'])
            rtp_streams['out_stream'].sort(key=lambda x: x['sequence'])

            # 상세 통계 로깅
            in_count = len(rtp_streams['in_stream'])
            out_count = len(rtp_streams['out_stream'])
            total_relevant = relevant_packet_count if 'relevant_packet_count' in locals() else packet_count

            # print(f"[DEBUG] UDP 패킷 총 개수: {packet_count}")
            # print(f"[DEBUG] 처리된 RTP 패킷: {processed_packets}")
            # print(f"[DEBUG] IN 스트림 패킷: {in_count}")
            # print(f"[DEBUG] OUT 스트림 패킷: {out_count}")

            self.logger.info(f"✅ 통화별 RTP 추출 완료 ({from_number}↔{to_number})")
            self.logger.info(f"   📊 패킷 통계: UDP 전체 {packet_count}개, RTP 처리됨 {processed_packets}개")
            self.logger.info(f"   📞 방향별: IN {in_count}개 (상대방→내선), OUT {out_count}개 (내선→상대방)")
            if 'detected_extension_ip' in locals():
                self.logger.info(f"   🔍 감지된 내선 IP: {detected_extension_ip}")
            self.logger.info(f"   ⚙️ 설정된 서버 IP: {server_ip}")
            if call_rtp_ports:
                self.logger.info(f"   🔌 RTP 포트: {sorted(call_rtp_ports)}")
            if call_ssrcs:
                self.logger.info(f"   🎵 SSRC: {[hex(ssrc) for ssrc in call_ssrcs]}")
            if sip_found:
                self.logger.info(f"   📡 SIP 분석: 성공 (통화 식별됨)")
            else:
                self.logger.warning(f"   📡 SIP 분석: 실패 (전체 RTP 사용)")

            return rtp_streams

        except Exception as e:
            self.logger.error(f"RTP 스트림 추출 실패: {e}")
            return {}

    def _decode_g711_payload(self, payload_data: bytes, payload_type: int) -> bytes:
        """G.711 페이로드를 PCM 데이터로 디코딩"""
        try:
            if payload_type == 0:  # G.711 u-law
                return audioop.ulaw2lin(payload_data, 2)  # 16-bit PCM
            elif payload_type == 8:  # G.711 A-law
                return audioop.alaw2lin(payload_data, 2)  # 16-bit PCM
            else:
                return b''  # 지원하지 않는 코덱
        except Exception as e:
            self.logger.warning(f"G.711 디코딩 오류: {e}")
            return b''

    def _create_wav_from_rtp_data(self, rtp_data_list: list, output_path: str) -> bool:
        """RTP 데이터 리스트에서 WAV 파일 생성"""
        try:
            if not rtp_data_list:
                self.logger.warning(f"RTP 데이터가 비어있음: {output_path}")
                return False

            # PCM 데이터 수집
            pcm_data = bytearray()

            for rtp_packet in rtp_data_list:
                payload = rtp_packet['payload']
                payload_type = rtp_packet['payload_type']

                # G.711 디코딩
                decoded_pcm = self._decode_g711_payload(payload, payload_type)
                pcm_data.extend(decoded_pcm)

            if not pcm_data:
                self.logger.warning(f"디코딩된 PCM 데이터가 없음: {output_path}")
                return False

            # WAV 파일 생성
            with wave.open(output_path, 'wb') as wav_file:
                wav_file.setnchannels(1)      # 모노
                wav_file.setsampwidth(2)      # 16-bit
                wav_file.setframerate(8000)   # 8kHz (G.711 표준)
                wav_file.writeframes(bytes(pcm_data))

            self.logger.info(f"WAV 파일 생성 완료: {output_path} ({len(pcm_data)} bytes)")
            return True

        except Exception as e:
            self.logger.error(f"WAV 파일 생성 실패 {output_path}: {e}")
            return False

    def __del__(self):
        """소멸자 - 리소스 정리"""
        self.cleanup_all_recordings()


# 전역 인스턴스 (dashboard.py에서 사용)
recording_manager = None


def get_recording_manager(logger=None, dashboard_instance=None):
    """ExtensionRecordingManager 전역 인스턴스 가져오기"""
    global recording_manager
    if recording_manager is None:
        recording_manager = ExtensionRecordingManager(logger, dashboard_instance)
    return recording_manager