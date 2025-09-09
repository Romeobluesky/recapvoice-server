import os
import subprocess
import logging
from pathlib import Path
from typing import Dict, List
import re
from datetime import datetime
import wave
import audioop
import configparser
import shutil
import threading
import time
import glob


class SipRtpSessionGrouper:
    def __init__(self, dashboard_instance=None):
        self.dashboard = dashboard_instance
        self.logger = logging.getLogger(__name__)
        if not self.logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)
            self.logger.setLevel(logging.INFO)

        self.temp_dir = Path("temp_recordings")
        self.temp_dir.mkdir(exist_ok=True)
        self.refer_mapping = {}

        # ExtensionRecordingManager 기능 통합
        self.recordings = {}  # call_id별 녹음 정보 저장

        # 설정 파일 로드
        self._load_settings()
        self.logger.info("통합된 SipRtpSessionGrouper 초기화 완료")

    def set_refer_mapping(self, call_id: str, from_number: str):
        """REFER 메소드 처리 시 Call-ID와 실제 발신번호 매핑 설정"""
        self.refer_mapping[call_id] = from_number
        self.logger.info(f"REFER 매핑 설정: {call_id} → {from_number}")

    def clear_refer_mapping(self, call_id: str = None):
        """REFER 매핑 정리 (특정 Call-ID 또는 전체)"""
        if call_id:
            if call_id in self.refer_mapping:
                del self.refer_mapping[call_id]
                self.logger.info(f"REFER 매핑 정리: {call_id}")
        else:
            count = len(self.refer_mapping)
            self.refer_mapping.clear()
            self.logger.info(f"전체 REFER 매핑 정리: {count}개 항목")

    def _load_settings(self):
        """settings.ini에서 하드코딩된 값들을 로드"""
        try:
            config = configparser.ConfigParser()
            config.read('settings.ini', encoding='utf-8')

            # Wireshark 설정
            wireshark_path = config.get('Wireshark', 'path', fallback='C:/Program Files/Wireshark')
            tshark_exe = config.get('Wireshark', 'tshark_exe', fallback='tshark.exe')
            self.tshark_path = str(Path(wireshark_path) / tshark_exe)

            # VoIP 설정
            self.extension_ip_prefixes = config.get('VoIP', 'extension_ip_prefixes', fallback='192.168.').split(',')
            self.extension_ip_prefixes = [prefix.strip() for prefix in self.extension_ip_prefixes]
            self.sample_rate = config.getint('VoIP', 'sample_rate', fallback=8000)

            # FFmpeg 설정 (이후에 사용)
            ffmpeg_paths = config.get('FFmpeg', 'paths', fallback='ffmpeg.exe').split(',')
            self.ffmpeg_paths = [path.strip() for path in ffmpeg_paths]
            ffprobe_paths = config.get('FFmpeg', 'ffprobe_paths', fallback='ffprobe.exe').split(',')
            self.ffprobe_paths = [path.strip() for path in ffprobe_paths]

            self.logger.info(f"설정 로드 완료 - tshark: {self.tshark_path}, 내선 IP: {self.extension_ip_prefixes}")

        except Exception as e:
            self.logger.error(f"설정 파일 로드 실패: {e}")
            # 기본값 사용
            self.tshark_path = "C:/Program Files/Wireshark/tshark.exe"
            self.extension_ip_prefixes = ['192.168.']
            self.sample_rate = 8000
            self.ffmpeg_paths = ['ffmpeg.exe']
            self.ffprobe_paths = ['ffprobe.exe']

    def _is_extension_ip(self, ip: str) -> bool:
        """IP가 내선 IP 대역에 속하는지 확인"""
        if not ip:
            return False
        for prefix in self.extension_ip_prefixes:
            if ip.startswith(prefix):
                return True
        return False

    def process_captured_pcap(self, input_pcap: str, active_calls_data: dict = None, latest_terminated_call_id: str = None) -> List[Dict]:
        processed_calls = []
        try:
            self.logger.info(f"pcap 파일 처리 시작: {input_pcap}")
            self.logger.info(f"최신 종료 Call-ID 받음: {latest_terminated_call_id}")
            self.logger.info(f"현재 REFER 매핑: {dict(self.refer_mapping)}")
            
            if not os.path.exists(input_pcap):
                self.logger.error(f"입력 pcap 파일이 존재하지 않음: {input_pcap}")
                return processed_calls

            tshark_fields = ["sip.Call-ID", "sip.from.user", "sip.to.user", "sdp.connection_info.address", "sdp.media.port"]
            tshark_cmd = [self.tshark_path, "-r", input_pcap, "-Y", "sip or sdp", "-T", "fields"] + [item for field in tshark_fields for item in ["-e", field]]
            result = subprocess.run(tshark_cmd, capture_output=True, text=True, timeout=60)

            if result.returncode != 0:
                self.logger.error(f"tshark SIP 추출 실패: {result.stderr}")
                return processed_calls

            # tshark 출력 디버깅
            self.logger.info(f"tshark 원본 출력:\n{result.stdout}")
            sessions = self._parse_sip_sessions(result.stdout)
            self.logger.info(f"추출된 SIP 세션 수: {len(sessions)}")

            # active_calls 데이터가 있으면 endpoints 정보 보강
            if active_calls_data:
                self._enhance_sessions_with_active_calls(sessions, active_calls_data)

            # 각 세션 상세 정보 로깅
            for call_id, info in sessions.items():
                self.logger.info(f"세션 {call_id}: endpoints={len(info['endpoints'])}, 값={list(info['endpoints'])}")

            for call_id, info in sessions.items():
                try:
                    from_num = info["from"] or "unknown"
                    to_num = info["to"] or "unknown"
                    endpoints = list(info["endpoints"])

                    if len(endpoints) < 2:
                        self.logger.warning(f"유효하지 않은 세션 스킵: {call_id} (endpoints: {len(endpoints)})")
                        continue

                    # REFER 매핑은 최신 종료된 Call-ID에만 적용 (돌려주기 폴더 생성용)
                    self.logger.info(f"REFER 매핑 체크: call_id={call_id}, in_refer_mapping={call_id in self.refer_mapping}, latest_terminated={latest_terminated_call_id}, is_match={call_id == latest_terminated_call_id}")
                    
                    if (call_id in self.refer_mapping and 
                        latest_terminated_call_id and 
                        call_id == latest_terminated_call_id):
                        original_from = from_num
                        from_num = self.refer_mapping[call_id]
                        self.logger.info(f"✅ 최신 Call-ID REFER 매핑 적용: {call_id}, {original_from} → {from_num}")
                    else:
                        self.logger.info(f"❌ REFER 매핑 적용 안함: call_id={call_id}, from_num={from_num}")

                    safe_call_id = re.sub(r'[<>:"/\\|?*@]', '_', call_id)
                    pcapng_filename = f"{safe_call_id}.pcapng"
                    pcapng_path = self.temp_dir / pcapng_filename

                    # 기존 파일이 있으면 덮어쓰기 (동일한 Call-ID는 같은 내용이므로)
                    if pcapng_path.exists():
                        self.logger.info(f"기존 pcapng 파일 덮어쓰기: {pcapng_filename}")
                        try:
                            pcapng_path.unlink()
                        except Exception as e:
                            self.logger.warning(f"기존 pcapng 파일 삭제 실패: {e}")

                    # Call-ID + 내선 RTP 포트 필터링 (완전한 패킷 추출)
                    call_id_prefix = call_id.split('@')[0]
                    call_id_filter = f'sip.Call-ID contains "{call_id_prefix}"'

                    # RTP 포트 필터 추가 (올바른 구문 사용)
                    port_filters = []
                    for endpoint in endpoints:
                        if ":" in endpoint:
                            ip, port = endpoint.split(":")
                            if self._is_extension_ip(ip):
                                # tshark에서 올바른 필터 구문 사용
                                port_filters.append(f"(ip.addr == {ip} and udp.port == {port})")

                    if port_filters:
                        rtp_filter = " or ".join(port_filters)
                        combined_filter = f'({call_id_filter}) or ({rtp_filter})'
                        self.logger.info(f"Call-ID + RTP 포트 필터: {combined_filter}")
                    else:
                        combined_filter = call_id_filter
                        self.logger.info(f"Call-ID만 필터: {combined_filter}")

                    extract_cmd = [self.tshark_path, "-r", input_pcap, "-Y", combined_filter, "-w", str(pcapng_path)]
                    try:
                        result = subprocess.run(extract_cmd, capture_output=True, text=True, timeout=30)
                        if result.returncode != 0:
                            self.logger.error(f"tshark 추출 실패: {result.stderr}")
                            # 간단한 Call-ID만 필터로 재시도
                            simple_filter = call_id_filter
                            self.logger.info(f"단순 필터로 재시도: {simple_filter}")
                            extract_cmd = [self.tshark_path, "-r", input_pcap, "-Y", simple_filter, "-w", str(pcapng_path)]
                            subprocess.run(extract_cmd, check=True)
                    except subprocess.TimeoutExpired:
                        self.logger.error(f"tshark 실행 타임아웃: {call_id}")
                        continue

                    if pcapng_path.exists() and os.path.getsize(pcapng_path) > 0:
                        self.logger.info(f"pcapng 추출 성공: {pcapng_filename} ({os.path.getsize(pcapng_path)} bytes)")
                        call_info = {'call_id': call_id, 'from_number': from_num, 'to_number': to_num, 'pcapng_path': str(pcapng_path)}

                        # WAV 변환 시도
                        wav_success = self._convert_to_wav(call_info)
                        if wav_success:
                            call_info['wav_converted'] = True
                            self.logger.info(f"WAV 변환 성공: {call_id}")
                        else:
                            call_info['wav_converted'] = False
                            self.logger.warning(f"WAV 변환 실패하지만 pcapng는 보존: {call_id}")

                        # pcapng 정보는 항상 processed_calls에 추가 (WAV 변환 성공 여부 관계없이)
                        processed_calls.append(call_info)
                        self.logger.info(f"pcapng 파일 보존됨: {pcapng_path}")

                        # 콜 처리 완료 후 해당 Call-ID의 REFER 매핑 정리
                        if call_id in self.refer_mapping:
                            self.clear_refer_mapping(call_id)
                            self.logger.info(f"콜 처리 완료로 REFER 매핑 자동 정리: {call_id}")
                    else:
                        self.logger.warning(f"pcapng 파일 생성 실패: {pcapng_filename}")

                except subprocess.CalledProcessError as e:
                    self.logger.error(f"pcapng 추출 실패: {call_id} - {e}")
                    # 실패한 경우에도 REFER 매핑 정리
                    if call_id in self.refer_mapping:
                        self.clear_refer_mapping(call_id)
                        self.logger.info(f"pcapng 추출 실패로 REFER 매핑 정리: {call_id}")
                except Exception as e:
                    self.logger.error(f"세션 처리 중 오류: {call_id} - {e}")
                    # 예외 발생 시에도 REFER 매핑 정리
                    if call_id in self.refer_mapping:
                        self.clear_refer_mapping(call_id)
                        self.logger.info(f"세션 처리 오류로 REFER 매핑 정리: {call_id}")

            return processed_calls
        except Exception as e:
            self.logger.error(f"pcap 처리 중 오류 발생: {e}")
            return processed_calls

    def _convert_to_wav(self, call_info: Dict) -> bool:
        try:
            pcapng_path = Path(call_info['pcapng_path'])
            from_number = call_info['from_number']
            to_number = call_info['to_number']

            if not pcapng_path.exists():
                self.logger.error(f"pcapng 파일이 존재하지 않음: {pcapng_path}")
                return False

            # RTP 스트림을 실제로 WAV로 변환
            return self._extract_rtp_to_wav(pcapng_path, from_number, to_number, call_info.get('call_id', 'unknown'))

        except Exception as e:
            self.logger.error(f"WAV 변환 중 오류: {e}")
            return False

    def _extract_rtp_streams_from_pcapng(self, pcapng_path: Path) -> List[Dict]:
        try:
            tshark_cmd = [self.tshark_path, "-r", str(pcapng_path), "-Y", "rtp", "-T", "fields", "-e", "ip.src", "-e", "ip.dst", "-e", "udp.srcport", "-e", "udp.dstport", "-e", "rtp.ssrc", "-e", "rtp.p_type", "-e", "rtp.timestamp"]
            result = subprocess.run(tshark_cmd, capture_output=True, text=True, timeout=30)

            if result.returncode != 0:
                return []

            streams = []
            lines = result.stdout.strip().split('\n')
            for line in lines:
                if line.strip():
                    fields = line.split('\t')
                    if len(fields) >= 7:
                        streams.append({'src_ip': fields[0], 'dst_ip': fields[1], 'src_port': fields[2], 'dst_port': fields[3]})

            return streams
        except Exception:
            return []

    def _extract_extension_number(self, number: str) -> str:
        """내선번호에서 알파벳 뒤의 숫자 부분만 추출 (109Q1427 -> 1427)"""
        if not number:
            return "unknown"

        import re
        number_str = str(number)

        # 순수 숫자인 경우 그대로 반환
        if number_str.isdigit():
            return number_str

        # 알파벳 1개 뒤의 숫자를 추출 (109Q1427 -> 1427)
        match = re.search(r'[A-Za-z](\d+)', number_str)
        if match:
            return match.group(1)

        # 알파벳이 없으면 원본 반환
        return number_str

    def _get_final_recording_path(self, from_number: str, to_number: str) -> Path:
        try:
            # settings.ini에서 save_path 읽기
            config = configparser.ConfigParser()
            config.read('settings.ini', encoding='utf-8')
            base_recording_path = Path(config.get('Recording', 'save_path', fallback='D:/PacketWaveRecord'))

            # 날짜 폴더 생성 (YYYY-MM-DD 형식)
            date_folder = datetime.now().strftime("%Y-%m-%d")

            # 내선번호에서 숫자 부분만 추출
            extracted_from = self._extract_extension_number(from_number)
            extracted_to = self._extract_extension_number(to_number)

            safe_from = extracted_from.replace('/', '_').replace('\\', '_').replace(':', '_')
            safe_to = extracted_to.replace('/', '_').replace('\\', '_').replace(':', '_')
            call_folder = f"{safe_from}_{safe_to}"

            # 경로 구조: base_path/YYYY-MM-DD/from_to/
            final_path = base_recording_path / date_folder / call_folder
            final_path.mkdir(parents=True, exist_ok=True)
            self.logger.info(f"녹음 디렉토리 생성: {final_path} (원본: {from_number}_{to_number} → 추출: {extracted_from}_{extracted_to})")
            return final_path
        except Exception as e:
            self.logger.error(f"녹음 경로 생성 오류: {e}")
            return None

    def _parse_sip_sessions(self, tshark_output: str) -> Dict:
        sessions = {}
        lines = tshark_output.strip().split('\n')

        for line in lines:
            if line.strip():
                fields = line.split('\t')
                if len(fields) >= 5:
                    call_id = fields[0]
                    from_user = fields[1]
                    to_user = fields[2]
                    rtp_ip = fields[3]
                    rtp_port = fields[4]

                    if call_id not in sessions:
                        sessions[call_id] = {'from': from_user, 'to': to_user, 'endpoints': set()}

                    if rtp_ip and rtp_port:
                        sessions[call_id]['endpoints'].add(f"{rtp_ip}:{rtp_port}")

        return sessions

    def _enhance_sessions_with_active_calls(self, sessions: Dict, active_calls_data: Dict):
        """active_calls 데이터로 sessions의 endpoints 정보 보강"""
        for call_id, call_info in active_calls_data.items():
            if call_id in sessions:
                # media_endpoints_set에서 내선 IP만 추출
                if 'media_endpoints_set' in call_info:
                    endpoints_set = call_info['media_endpoints_set']
                    for endpoint_type in ['local', 'remote']:
                        if endpoint_type in endpoints_set:
                            for endpoint in endpoints_set[endpoint_type]:
                                # 내선 IP만 추가
                                if ':' in endpoint:
                                    ip, port = endpoint.split(':')
                                    if self._is_extension_ip(ip):
                                        sessions[call_id]['endpoints'].add(endpoint)
                                        self.logger.info(f"Active calls에서 endpoint 추가: {call_id} → {endpoint}")

                # media_endpoints에서도 추출
                if 'media_endpoints' in call_info:
                    for endpoint_info in call_info['media_endpoints']:
                        if 'ip' in endpoint_info and 'port' in endpoint_info:
                            ip = endpoint_info['ip']
                            port = endpoint_info['port']
                            # 내선 IP만 추가
                            if self._is_extension_ip(ip):
                                endpoint_str = f"{ip}:{port}"
                                sessions[call_id]['endpoints'].add(endpoint_str)
                                self.logger.info(f"Media endpoints에서 endpoint 추가: {call_id} → {endpoint_str}")

    def _extract_rtp_to_wav(self, pcapng_path: Path, from_number: str, to_number: str, call_id: str) -> bool:
        """FFmpeg을 사용하여 pcapng 파일에서 RTP 스트림을 추출하여 IN/OUT/MERGE WAV 파일로 변환"""
        try:
            # 최종 녹음 경로 생성
            final_recording_path = self._get_final_recording_path(from_number, to_number)
            if not final_recording_path:
                return False

            # 안전한 call_id 생성 (파일명용)
            safe_call_id = re.sub(r'[<>:"/\\|?*@]', '_', call_id)[:20]
            
            # 날짜만 포함 (시분초 제외)
            date_only = datetime.now().strftime('%Y%m%d')
            
            # 내선번호에서 숫자 부분만 추출
            extracted_from = self._extract_extension_number(from_number)
            extracted_to = self._extract_extension_number(to_number)

            # IN/OUT/MERGE WAV 파일 경로 생성 (시분초만 제거, 날짜+Call-ID 해시 유지)
            in_wav_path = final_recording_path / f"{date_only}_IN_{extracted_from}_{extracted_to}_{safe_call_id}.wav"
            out_wav_path = final_recording_path / f"{date_only}_OUT_{extracted_from}_{extracted_to}_{safe_call_id}.wav"
            merge_wav_path = final_recording_path / f"{date_only}_MERGE_{extracted_from}_{extracted_to}_{safe_call_id}.wav"

            self.logger.info(f"RTP 스트림 분석 시작: {pcapng_path}")

            # FFmpeg을 사용하여 RTP 스트림 분석 및 추출
            rtp_streams = self._analyze_rtp_streams_with_ffmpeg(pcapng_path)
            if not rtp_streams:
                self.logger.warning("FFmpeg으로 RTP 스트림을 찾을 수 없음")
                return False

            self.logger.info(f"발견된 RTP 스트림 수: {len(rtp_streams)}")

            success = False

            # 각 RTP 스트림을 방향별로 분류하여 추출
            in_streams = []
            out_streams = []

            for stream in rtp_streams:
                src_ip = stream.get('src_ip', '')
                dst_ip = stream.get('dst_ip', '')

                # 방향 판별: 내선 vs 외부
                if self._is_extension_ip(src_ip) and not self._is_extension_ip(dst_ip):
                    out_streams.append(stream)  # 내선 -> 외부 (OUT)
                elif not self._is_extension_ip(src_ip) and self._is_extension_ip(dst_ip):
                    in_streams.append(stream)   # 외부 -> 내선 (IN)
                else:
                    # 방향이 명확하지 않은 경우 첫 번째 스트림을 IN으로 처리
                    if len(in_streams) == 0:
                        in_streams.append(stream)
                    else:
                        out_streams.append(stream)

            # IN 방향 RTP 추출
            if in_streams:
                in_success = self._extract_rtp_stream_with_ffmpeg(pcapng_path, in_streams[0], in_wav_path, "IN")
                if in_success:
                    self.logger.info(f"IN 스트림 생성 성공: {in_wav_path.name}")
                    success = True
            else:
                self.logger.warning("IN 방향 RTP 스트림을 찾을 수 없음")
                in_success = False

            # OUT 방향 RTP 추출
            if out_streams:
                out_success = self._extract_rtp_stream_with_ffmpeg(pcapng_path, out_streams[0], out_wav_path, "OUT")
                if out_success:
                    self.logger.info(f"OUT 스트림 생성 성공: {out_wav_path.name}")
                    success = True
            else:
                self.logger.warning("OUT 방향 RTP 스트림을 찾을 수 없음")
                out_success = False

            # MERGE 파일 생성 (FFmpeg을 사용한 믹싱)
            if (in_success and in_wav_path.exists()) or (out_success and out_wav_path.exists()):
                merge_success = self._create_merge_wav_with_ffmpeg(
                    in_wav_path if in_success and in_wav_path.exists() else None,
                    out_wav_path if out_success and out_wav_path.exists() else None,
                    merge_wav_path
                )
                if merge_success:
                    self.logger.info(f"MERGE 파일 생성 성공: {merge_wav_path.name}")
                    success = True

            return success

        except Exception as e:
            self.logger.error(f"RTP to WAV 변환 중 오류: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
            return False

    def _extract_rtp_stream_by_direction(self, pcapng_path: Path, wav_path: Path, direction: str, from_number: str, to_number: str) -> bool:
        """방향별 RTP 스트림 추출"""
        try:
            # 먼저 RTP 패킷이 있는지 확인
            check_cmd = [
                "C:/Program Files/Wireshark/tshark.exe",
                "-r", str(pcapng_path),
                "-Y", "rtp",
                "-c", "1"  # 첫 번째 RTP 패킷만 확인
            ]

            check_result = subprocess.run(check_cmd, capture_output=True, text=True, timeout=10)
            if check_result.returncode != 0 or not check_result.stdout.strip():
                self.logger.warning(f"{direction} 방향 RTP 패킷이 전혀 없음")
                return False

            # RTP 페이로드 추출 (더 포괄적인 필터 사용)
            rtp_filter = "rtp and rtp.payload"  # 페이로드가 있는 RTP 패킷만

            extract_cmd = [
                "C:/Program Files/Wireshark/tshark.exe",
                "-r", str(pcapng_path),
                "-Y", rtp_filter,
                "-T", "fields",
                "-e", "rtp.payload",
                "-e", "ip.src",
                "-e", "ip.dst",
                "-e", "rtp.p_type",
                "-e", "udp.srcport",
                "-e", "udp.dstport"
            ]

            result = subprocess.run(extract_cmd, capture_output=True, text=True, timeout=30)
            if result.returncode != 0:
                self.logger.error(f"{direction} RTP 페이로드 추출 실패: {result.stderr}")
                return False

            lines = [line.strip() for line in result.stdout.strip().split('\n') if line.strip()]

            if not lines:
                self.logger.warning(f"{direction} 방향 RTP 페이로드가 없음")
                return False

            self.logger.info(f"{direction} 방향 RTP 라인 수: {len(lines)}")

            # 첫 몇 줄 샘플 로깅
            for i, line in enumerate(lines[:3]):
                self.logger.info(f"{direction} RTP 샘플 {i+1}: {line[:100]}...")  # 처음 100문자만

            # 방향별로 패킷 필터링 및 오디오 데이터 수집
            audio_data = bytearray()
            packet_count = 0
            direction_filtered_count = 0

            for line in lines:
                try:
                    fields = line.split('\t')
                    if len(fields) >= 6:
                        payload = fields[0]
                        src_ip = fields[1]
                        dst_ip = fields[2]
                        p_type = fields[3]
                        src_port = fields[4]
                        dst_port = fields[5]

                        # 방향 판별 (더 정확한 로직)
                        is_internal_src = self._is_extension_ip(src_ip)
                        is_internal_dst = self._is_extension_ip(dst_ip)

                        include_packet = False
                        if direction == "IN":
                            # 외부 -> 내선: 외부 IP에서 내선 IP로
                            include_packet = not is_internal_src and is_internal_dst
                        else:  # OUT
                            # 내선 -> 외부: 내선 IP에서 외부 IP로
                            include_packet = is_internal_src and not is_internal_dst

                        # 양방향 모두 수집하는 옵션 (debugging을 위해)
                        if not include_packet:
                            # 방향이 애매한 경우 모든 RTP 페이로드를 수집
                            if payload and len(audio_data) < 1000:  # 처음 몇 패킷은 방향 무관하게 수집
                                include_packet = True
                                direction_filtered_count += 1

                        if include_packet and payload:
                            try:
                                hex_values = payload.replace(':', '').replace(' ', '')
                                if len(hex_values) >= 2 and len(hex_values) % 2 == 0:
                                    audio_data.extend(bytes.fromhex(hex_values))
                                    packet_count += 1

                                    # 디버그 정보 (처음 3개 패킷만)
                                    if packet_count <= 3:
                                        self.logger.info(f"{direction} 패킷 {packet_count}: {src_ip}:{src_port} -> {dst_ip}:{dst_port}, 페이로드: {len(hex_values)} chars")

                            except ValueError as hex_error:
                                self.logger.warning(f"Hex 변환 실패: {hex_error}")
                                continue

                except Exception as e:
                    self.logger.warning(f"RTP 라인 파싱 실패: {e}")
                    continue

            self.logger.info(f"{direction} 방향 - 총 RTP 라인: {len(lines)}, 방향 필터 적용: {direction_filtered_count}, 실제 수집: {packet_count}")
            self.logger.info(f"{direction} 방향 오디오 데이터 크기: {len(audio_data)} bytes")

            if len(audio_data) < 160:  # 최소 160바이트 (20ms @ 8kHz)
                self.logger.warning(f"{direction} 방향 오디오 데이터가 너무 작음: {len(audio_data)} bytes")
                return False

            # WAV 파일 생성
            return self._create_wav_file(audio_data, wav_path, from_number, to_number)

        except Exception as e:
            self.logger.error(f"{direction} 방향 RTP 추출 중 오류: {e}")
            return False

    def _create_merge_wav(self, in_wav_path: Path, out_wav_path: Path, merge_wav_path: Path) -> bool:
        """IN과 OUT WAV 파일을 합성하여 MERGE 파일 생성"""
        try:
            # 먼저 pydub 사용 시도
            try:
                from pydub import AudioSegment
                return self._create_merge_wav_pydub(in_wav_path, out_wav_path, merge_wav_path)
            except ImportError:
                # pydub가 없으면 간단한 wave 라이브러리 사용
                return self._create_merge_wav_simple(in_wav_path, out_wav_path, merge_wav_path)

        except Exception as e:
            self.logger.error(f"MERGE 파일 생성 중 오류: {e}")
            return False

    def _create_merge_wav_pydub(self, in_wav_path: Path, out_wav_path: Path, merge_wav_path: Path) -> bool:
        """pydub를 사용한 MERGE 파일 생성"""
        from pydub import AudioSegment

        audio_segments = []

        # IN 파일 로드
        if in_wav_path and in_wav_path.exists():
            in_audio = AudioSegment.from_wav(str(in_wav_path))
            audio_segments.append(in_audio)
            self.logger.info(f"IN 오디오 로드: {len(in_audio)}ms")

        # OUT 파일 로드
        if out_wav_path and out_wav_path.exists():
            out_audio = AudioSegment.from_wav(str(out_wav_path))
            audio_segments.append(out_audio)
            self.logger.info(f"OUT 오디오 로드: {len(out_audio)}ms")

        if not audio_segments:
            self.logger.warning("합성할 오디오 파일이 없음")
            return False

        # 오디오 합성 (겹치기)
        if len(audio_segments) == 1:
            merged_audio = audio_segments[0]
        else:
            merged_audio = audio_segments[0].overlay(audio_segments[1])

        # MERGE 파일 저장
        merged_audio.export(str(merge_wav_path), format="wav")

        if merge_wav_path.exists():
            file_size = merge_wav_path.stat().st_size
            self.logger.info(f"MERGE 파일 생성 성공: {merge_wav_path.name} ({file_size} bytes)")
            return True
        else:
            self.logger.error("MERGE 파일 생성 실패")
            return False

    def _create_merge_wav_simple(self, in_wav_path: Path, out_wav_path: Path, merge_wav_path: Path) -> bool:
        """wave 라이브러리를 사용한 간단한 MERGE 파일 생성"""
        try:
            # 단순하게 가장 큰 파일을 MERGE로 복사
            files_to_check = []
            if in_wav_path and in_wav_path.exists():
                files_to_check.append(in_wav_path)
            if out_wav_path and out_wav_path.exists():
                files_to_check.append(out_wav_path)

            if not files_to_check:
                self.logger.warning("합성할 오디오 파일이 없음")
                return False

            # 가장 큰 파일을 선택
            largest_file = max(files_to_check, key=lambda x: x.stat().st_size)

            # 파일 복사
            import shutil
            shutil.copy2(str(largest_file), str(merge_wav_path))

            if merge_wav_path.exists():
                file_size = merge_wav_path.stat().st_size
                self.logger.info(f"MERGE 파일 생성 성공 (단순 복사): {merge_wav_path.name} ({file_size} bytes)")
                return True
            else:
                self.logger.error("MERGE 파일 생성 실패")
                return False

        except Exception as e:
            self.logger.error(f"간단한 MERGE 파일 생성 중 오류: {e}")
            return False

    def _analyze_rtp_streams_with_ffmpeg(self, pcapng_path: Path) -> List[Dict]:
        """FFmpeg을 사용하여 pcapng 파일에서 RTP 스트림 정보를 분석"""
        try:
            # FFmpeg이 설치되어 있는지 확인
            ffmpeg_path = self._get_ffmpeg_path()
            if not ffmpeg_path:
                self.logger.error("FFmpeg을 찾을 수 없음")
                return []

            # ffprobe 경로 확인 (실제로는 tshark 사용할 예정이므로 주석 처리)
            # ffprobe_path = self._get_ffprobe_path()
            # if not ffprobe_path:
            #     self.logger.warning("ffprobe를 찾을 수 없음, tshark로 대체")
            #     # ffprobe가 없어도 tshark로 진행 가능

            # tshark으로 RTP 스트림 정보를 먼저 추출
            tshark_cmd = [
                "C:/Program Files/Wireshark/tshark.exe",
                "-r", str(pcapng_path),
                "-Y", "rtp",
                "-T", "fields",
                "-e", "ip.src",
                "-e", "ip.dst",
                "-e", "udp.srcport",
                "-e", "udp.dstport",
                "-e", "rtp.ssrc",
                "-e", "rtp.p_type"
            ]

            result = subprocess.run(tshark_cmd, capture_output=True, text=True, timeout=30)
            if result.returncode != 0:
                self.logger.error(f"tshark RTP 분석 실패: {result.stderr}")
                return []

            # RTP 스트림 정보 파싱
            streams = []
            lines = result.stdout.strip().split('\n')
            stream_map = {}  # SSRC별로 스트림 정보 수집

            for line in lines:
                if line.strip():
                    fields = line.split('\t')
                    if len(fields) >= 6:
                        src_ip = fields[0]
                        dst_ip = fields[1]
                        src_port = fields[2]
                        dst_port = fields[3]
                        ssrc = fields[4]
                        payload_type = fields[5]

                        if ssrc and ssrc not in stream_map:
                            stream_map[ssrc] = {
                                'ssrc': ssrc,
                                'src_ip': src_ip,
                                'dst_ip': dst_ip,
                                'src_port': src_port,
                                'dst_port': dst_port,
                                'payload_type': payload_type,
                                'packet_count': 1
                            }
                        elif ssrc in stream_map:
                            stream_map[ssrc]['packet_count'] += 1

            # 패킷 수가 10개 이상인 스트림만 유효한 것으로 간주
            valid_streams = [stream for stream in stream_map.values() if stream['packet_count'] >= 10]

            self.logger.info(f"유효한 RTP 스트림 발견: {len(valid_streams)}개")
            for stream in valid_streams:
                self.logger.info(f"스트림 SSRC {stream['ssrc']}: {stream['src_ip']}:{stream['src_port']} -> {stream['dst_ip']}:{stream['dst_port']} (패킷: {stream['packet_count']}개)")

            return valid_streams

        except Exception as e:
            self.logger.error(f"RTP 스트림 분석 중 오류: {e}")
            return []

    def _extract_rtp_stream_with_ffmpeg(self, pcapng_path: Path, stream_info: Dict, wav_path: Path, direction: str) -> bool:
        """FFmpeg을 사용하여 특정 RTP 스트림을 WAV 파일로 추출"""
        try:
            ffmpeg_path = self._get_ffmpeg_path()
            if not ffmpeg_path:
                return False

            src_ip = stream_info['src_ip']
            dst_ip = stream_info['dst_ip']
            src_port = stream_info['src_port']
            dst_port = stream_info['dst_port']

            self.logger.info(f"{direction} 스트림 추출 시작: {src_ip}:{src_port} -> {dst_ip}:{dst_port}")

            # 임시 raw RTP 파일 생성 (tshark 사용)
            temp_rtp_file = wav_path.parent / f"temp_rtp_{direction}_{stream_info['ssrc']}.rtp"

            # tshark로 특정 RTP 스트림 추출
            rtp_filter = f"(ip.src == {src_ip} and ip.dst == {dst_ip} and udp.srcport == {src_port} and udp.dstport == {dst_port} and rtp)"

            extract_cmd = [
                "C:/Program Files/Wireshark/tshark.exe",
                "-r", str(pcapng_path),
                "-Y", rtp_filter,
                "-w", str(temp_rtp_file)
            ]

            result = subprocess.run(extract_cmd, capture_output=True, text=True, timeout=30)
            if result.returncode != 0:
                self.logger.error(f"tshark RTP 추출 실패: {result.stderr}")
                return False

            if not temp_rtp_file.exists() or temp_rtp_file.stat().st_size == 0:
                self.logger.warning(f"RTP 파일이 생성되지 않음: {temp_rtp_file}")
                return False

            # FFmpeg으로 RTP를 WAV로 변환 (Whisper 최적화: 16kHz, 노이즈 감소, 음량 정규화)
            ffmpeg_cmd = [
                ffmpeg_path,
                "-f", "pcap",  # 입력 형식
                "-i", str(temp_rtp_file),
                "-vn",  # 비디오 스트림 무시
                "-af", "highpass=f=300,lowpass=f=3400,volume=2.0,dynaudnorm=f=500:g=31",  # Whisper 최적화 필터
                "-acodec", "pcm_s16le",  # 16-bit PCM
                "-ar", "16000",  # Whisper 권장 샘플레이트
                "-ac", "1",  # 모노
                "-b:a", "128k",  # 음성 인식에 충분한 비트레이트
                "-y",  # 덮어쓰기
                str(wav_path)
            ]

            self.logger.info(f"FFmpeg 명령 실행: {' '.join(ffmpeg_cmd)}")

            result = subprocess.run(ffmpeg_cmd, capture_output=True, text=True, timeout=60)

            # 임시 파일 정리
            try:
                if temp_rtp_file.exists():
                    temp_rtp_file.unlink()
            except:
                pass

            if result.returncode != 0:
                self.logger.error(f"FFmpeg 변환 실패: {result.stderr}")
                # 다른 방법으로 시도 (RTP 페이로드 직접 추출)
                return self._extract_rtp_payload_fallback(pcapng_path, stream_info, wav_path, direction)

            if wav_path.exists() and wav_path.stat().st_size > 0:
                file_size = wav_path.stat().st_size
                self.logger.info(f"{direction} WAV 파일 생성 성공: {wav_path.name} ({file_size} bytes)")
                return True
            else:
                self.logger.warning(f"{direction} WAV 파일 생성 실패")
                return False

        except Exception as e:
            self.logger.error(f"FFmpeg RTP 추출 중 오류: {e}")
            return False

    def _extract_rtp_payload_fallback(self, pcapng_path: Path, stream_info: Dict, wav_path: Path, direction: str) -> bool:
        """FFmpeg 실패 시 tshark으로 RTP 페이로드를 직접 추출하여 WAV 생성"""
        try:
            src_ip = stream_info['src_ip']
            dst_ip = stream_info['dst_ip']
            src_port = stream_info['src_port']
            dst_port = stream_info['dst_port']

            self.logger.info(f"{direction} 스트림 폴백 방법 시도: {src_ip}:{src_port} -> {dst_ip}:{dst_port}")

            # tshark로 RTP 페이로드만 추출
            rtp_filter = f"(ip.src == {src_ip} and ip.dst == {dst_ip} and udp.srcport == {src_port} and udp.dstport == {dst_port} and rtp and rtp.payload)"

            extract_cmd = [
                "C:/Program Files/Wireshark/tshark.exe",
                "-r", str(pcapng_path),
                "-Y", rtp_filter,
                "-T", "fields",
                "-e", "rtp.payload"
            ]

            result = subprocess.run(extract_cmd, capture_output=True, text=True, timeout=30)
            if result.returncode != 0:
                self.logger.error(f"RTP 페이로드 추출 실패: {result.stderr}")
                return False

            lines = [line.strip() for line in result.stdout.strip().split('\n') if line.strip()]

            if not lines:
                self.logger.warning(f"{direction} RTP 페이로드가 없음")
                return False

            # 페이로드를 바이너리로 변환
            audio_data = bytearray()
            for line in lines:
                try:
                    hex_values = line.replace(':', '').replace(' ', '')
                    if len(hex_values) >= 2 and len(hex_values) % 2 == 0:
                        audio_data.extend(bytes.fromhex(hex_values))
                except ValueError:
                    continue

            if len(audio_data) < 160:
                self.logger.warning(f"{direction} 오디오 데이터가 너무 작음: {len(audio_data)} bytes")
                return False

            # WAV 파일 생성
            return self._create_wav_file_from_payload(audio_data, wav_path, direction)

        except Exception as e:
            self.logger.error(f"RTP 페이로드 폴백 추출 중 오류: {e}")
            return False

    def _create_merge_wav_with_ffmpeg(self, in_wav_path: Path, out_wav_path: Path, merge_wav_path: Path) -> bool:
        """FFmpeg을 사용하여 IN과 OUT WAV 파일을 합성"""
        try:
            ffmpeg_path = self._get_ffmpeg_path()
            if not ffmpeg_path:
                # FFmpeg이 없으면 기존 방법 사용
                return self._create_merge_wav_simple(in_wav_path, out_wav_path, merge_wav_path)

            input_files = []
            if in_wav_path and in_wav_path.exists():
                input_files.append(str(in_wav_path))
            if out_wav_path and out_wav_path.exists():
                input_files.append(str(out_wav_path))

            if not input_files:
                self.logger.warning("합성할 오디오 파일이 없음")
                return False

            if len(input_files) == 1:
                # 파일이 하나만 있으면 복사
                shutil.copy2(input_files[0], str(merge_wav_path))
                self.logger.info(f"MERGE 파일 생성 (단일 파일): {merge_wav_path.name}")
                return True

            # FFmpeg으로 오디오 믹싱 (Whisper 최적화: 16kHz, 노이즈 감소, 음량 정규화)
            ffmpeg_cmd = [
                ffmpeg_path,
                "-i", input_files[0],
                "-i", input_files[1],
                "-filter_complex",
                "[0:a][1:a]amix=inputs=2:duration=longest,highpass=f=300,lowpass=f=3400,volume=2.0,dynaudnorm=f=500:g=31[out]",
                "-map", "[out]",
                "-acodec", "pcm_s16le",
                "-ar", "16000",  # Whisper 권장 샘플레이트
                "-ac", "1",
                "-b:a", "128k",  # 음성 인식에 충분한 비트레이트
                "-y",
                str(merge_wav_path)
            ]

            self.logger.info(f"FFmpeg 믹싱 명령: {' '.join(ffmpeg_cmd)}")

            result = subprocess.run(ffmpeg_cmd, capture_output=True, text=True, timeout=60)

            if result.returncode != 0:
                self.logger.error(f"FFmpeg 믹싱 실패: {result.stderr}")
                # 폴백: 단순 복사
                return self._create_merge_wav_simple(in_wav_path, out_wav_path, merge_wav_path)

            if merge_wav_path.exists() and merge_wav_path.stat().st_size > 0:
                file_size = merge_wav_path.stat().st_size
                self.logger.info(f"MERGE 파일 생성 성공 (FFmpeg): {merge_wav_path.name} ({file_size} bytes)")
                return True
            else:
                self.logger.error("MERGE 파일 생성 실패")
                return False

        except Exception as e:
            self.logger.error(f"FFmpeg MERGE 생성 중 오류: {e}")
            # 폴백: 기존 방법 사용
            return self._create_merge_wav_simple(in_wav_path, out_wav_path, merge_wav_path)

    def _get_ffmpeg_path(self) -> str:
        """FFmpeg 실행 파일 경로를 찾아서 반환"""
        possible_paths = [
            "ffmpeg.exe",  # PATH에 있는 경우
            "ffmpeg",      # Unix-style PATH
            "C:/ffmpeg/bin/ffmpeg.exe",
            "C:/Program Files/ffmpeg/bin/ffmpeg.exe",
            "C:/Program Files (x86)/ffmpeg/bin/ffmpeg.exe",
            "./ffmpeg/bin/ffmpeg.exe",  # 로컬 설치
        ]

        for path in possible_paths:
            try:
                # 실행 가능한지 테스트
                result = subprocess.run([path, "-version"], capture_output=True, text=True, timeout=5)
                if result.returncode == 0:
                    self.logger.info(f"FFmpeg 발견: {path}")
                    return path
            except (subprocess.TimeoutExpired, FileNotFoundError, subprocess.SubprocessError):
                continue

        self.logger.warning("FFmpeg을 찾을 수 없음. 설치가 필요합니다.")
        return None

    def _get_ffprobe_path(self) -> str:
        """ffprobe 실행 파일 경로를 찾아서 반환"""
        possible_paths = [
            "ffprobe.exe",  # PATH에 있는 경우
            "ffprobe",      # Unix-style PATH
            "C:/ffmpeg/bin/ffprobe.exe",
            "C:/Program Files/ffmpeg/bin/ffprobe.exe",
            "C:/Program Files (x86)/ffmpeg/bin/ffprobe.exe",
            "./ffmpeg/bin/ffprobe.exe",  # 로컬 설치
        ]

        for path in possible_paths:
            try:
                # 실행 가능한지 테스트
                result = subprocess.run([path, "-version"], capture_output=True, text=True, timeout=5)
                if result.returncode == 0:
                    self.logger.info(f"ffprobe 발견: {path}")
                    return path
            except (subprocess.TimeoutExpired, FileNotFoundError, subprocess.SubprocessError):
                continue

        self.logger.warning("ffprobe를 찾을 수 없음")
        return None

    def _create_wav_file_from_payload(self, audio_data: bytearray, wav_path: Path, direction: str) -> bool:
        """RTP 페이로드로부터 WAV 파일 생성 (개선된 버전)"""
        try:
            import wave
            import audioop

            self.logger.info(f"{direction} WAV 파일 생성 시작: {wav_path}, 원본 데이터: {len(audio_data)} bytes")

            if len(audio_data) < 160:
                self.logger.error(f"오디오 데이터가 너무 작음: {len(audio_data)} bytes")
                return False

            decoded_audio = None
            codec_type = "Unknown"

            # 일반적인 VoIP 코덱 시도 순서 (G.711 A-law, μ-law 우선)
            codecs_to_try = [
                ("PCMA (A-law)", lambda data: audioop.alaw2lin(bytes(data), 2)),
                ("PCMU (μ-law)", lambda data: audioop.ulaw2lin(bytes(data), 2)),
                ("Linear PCM 16-bit", lambda data: bytes(data)),
                ("Linear PCM 8-bit", lambda data: audioop.lin2lin(bytes(data), 1, 2))
            ]

            for codec_name, decode_func in codecs_to_try:
                try:
                    decoded_audio = decode_func(audio_data)
                    codec_type = codec_name
                    self.logger.info(f"{direction} 오디오 디코딩 성공: {codec_type}")
                    break
                except (audioop.error, ValueError) as e:
                    self.logger.debug(f"{direction} {codec_name} 디코딩 실패: {e}")
                    continue

            if decoded_audio is None:
                self.logger.error(f"{direction} 모든 코덱 디코딩 실패")
                return False

            if len(decoded_audio) < 160:
                self.logger.error(f"{direction} 디코딩된 데이터가 너무 작음: {len(decoded_audio)} bytes")
                return False

            self.logger.info(f"{direction} 디코딩 완료: {codec_type}, 원본: {len(audio_data)} -> 디코딩: {len(decoded_audio)} bytes")

            # WAV 파일 생성
            with wave.open(str(wav_path), 'wb') as wav_file:
                wav_file.setnchannels(1)          # 모노
                wav_file.setsampwidth(2)          # 16-bit
                wav_file.setframerate(self.sample_rate)       # 설정된 샘플레이트
                wav_file.writeframes(decoded_audio)

            if wav_path.exists() and wav_path.stat().st_size > 0:
                file_size = wav_path.stat().st_size
                duration = len(decoded_audio) / (self.sample_rate * 2)
                self.logger.info(f"{direction} WAV 파일 생성 성공: {wav_path.name} ({file_size} bytes, {duration:.2f}초)")
                return True
            else:
                self.logger.error(f"{direction} WAV 파일이 생성되지 않음")
                return False

        except Exception as e:
            self.logger.error(f"{direction} WAV 파일 생성 중 오류: {e}")
            return False

    def _create_wav_file(self, audio_data: bytearray, wav_path: Path, from_number: str, to_number: str) -> bool:
        """오디오 데이터를 WAV 파일로 생성"""
        try:
            import wave
            import audioop

            self.logger.info(f"WAV 파일 생성 시작: {wav_path}, 원본 데이터: {len(audio_data)} bytes")

            # 데이터가 너무 작으면 실패
            if len(audio_data) < 160:
                self.logger.error(f"오디오 데이터가 너무 작음: {len(audio_data)} bytes")
                return False

            decoded_audio = None
            codec_type = "Unknown"

            # 여러 코덱 시도
            codecs_to_try = [
                ("PCMA (A-law)", lambda data: audioop.alaw2lin(bytes(data), 2)),
                ("PCMU (μ-law)", lambda data: audioop.ulaw2lin(bytes(data), 2)),
                ("Linear PCM 16-bit", lambda data: bytes(data)),  # 이미 PCM인 경우
                ("Linear PCM 8-bit", lambda data: audioop.lin2lin(bytes(data), 1, 2))  # 8비트를 16비트로 확장
            ]

            for codec_name, decode_func in codecs_to_try:
                try:
                    decoded_audio = decode_func(audio_data)
                    codec_type = codec_name
                    self.logger.info(f"오디오 디코딩 성공: {codec_type}")
                    break
                except (audioop.error, ValueError) as e:
                    self.logger.debug(f"{codec_name} 디코딩 실패: {e}")
                    continue

            if decoded_audio is None:
                self.logger.error("모든 코덱 디코딩 실패")
                return False

            # 데이터 검증
            if len(decoded_audio) < 160:
                self.logger.error(f"디코딩된 데이터가 너무 작음: {len(decoded_audio)} bytes")
                return False

            self.logger.info(f"디코딩 완료: {codec_type}, 원본: {len(audio_data)} -> 디코딩: {len(decoded_audio)} bytes")

            # 볼륨 증폭 (1.5배로 조정)
            try:
                amplified_audio = audioop.mul(decoded_audio, 2, 1.5)
            except audioop.error:
                # 증폭 실패 시 원본 사용
                amplified_audio = decoded_audio
                self.logger.warning("볼륨 증폭 실패, 원본 데이터 사용")

            # WAV 파일 생성
            with wave.open(str(wav_path), 'wb') as wav_file:
                wav_file.setnchannels(1)          # 모노
                wav_file.setsampwidth(2)          # 16-bit
                wav_file.setframerate(self.sample_rate)       # 설정된 샘플레이트
                wav_file.writeframes(amplified_audio)

            # 생성된 파일 확인
            if wav_path.exists():
                file_size = wav_path.stat().st_size
                duration = len(amplified_audio) / (self.sample_rate * 2)  # 초 단위
                self.logger.info(f"WAV 파일 생성 성공: {wav_path.name}")
                self.logger.info(f"파일 크기: {file_size} bytes, 재생 시간: {duration:.2f}초, 코덱: {codec_type}")

                if file_size < 100:
                    self.logger.warning("생성된 WAV 파일이 너무 작음")
                    return False

                return True
            else:
                self.logger.error("WAV 파일이 생성되지 않음")
                return False

        except Exception as e:
            self.logger.error(f"WAV 파일 생성 중 오류: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
            return False

    # ExtensionRecordingManager 통합 메소드들
    def start_call_recording(self, call_id, extension=None, from_number=None, to_number=None):
        """통화 녹음 시작"""
        try:
            if call_id in self.recordings:
                self.logger.warning(f"이미 녹음 중인 통화: {call_id}")
                return True  # 이미 녹음 중이므로 성공으로 처리

            # 현재 시간으로 녹음 정보 초기화
            recording_info = {
                'call_id': call_id,
                'start_time': datetime.now(),
                'extension': extension,
                'from_number': from_number,
                'to_number': to_number,
                'pcapng_path': f"temp_recordings/{call_id}.pcapng"
            }

            self.recordings[call_id] = recording_info
            self.logger.info(f"통화 녹음 시작: {call_id} (내선: {extension})")
            return True  # 성공

        except Exception as e:
            self.logger.error(f"녹음 시작 오류: {e}")
            return False  # 실패

    def stop_call_recording(self, call_id):
        """통화 녹음 중지"""
        try:
            if call_id not in self.recordings:
                self.logger.warning(f"통화 녹음 정보 없음: {call_id}")
                return

            recording_info = self.recordings[call_id]
            self.logger.info(f"통화 녹음 중지: {call_id}")

            # 별도 스레드에서 WAV 변환 처리 (1초 지연)
            conversion_thread = threading.Thread(
                target=self.delayed_wav_conversion,
                args=(recording_info,),
                daemon=True
            )
            conversion_thread.start()

            # 녹음 정보 정리 (변환 스레드 시작 후)
            del self.recordings[call_id]
            self.logger.info(f"통화 녹음 정보 정리 완료: {call_id}")

        except Exception as e:
            self.logger.error(f"녹음 중지 오류: {e}")

    def delayed_wav_conversion(self, call_info):
        """지연된 WAV 변환 (별도 스레드에서 실행)"""
        try:
            # 1초 대기 (pcapng 파일 안정화)
            time.sleep(1)

            # temp_capture 파일 찾기
            temp_capture_file = None

            # 1. dashboard에서 temp_capture_file 확인
            if self.dashboard and hasattr(self.dashboard, 'temp_capture_file'):
                temp_capture_file = self.dashboard.temp_capture_file
                self.logger.info(f"Dashboard에서 temp_capture_file 확인: {temp_capture_file}")

            # 2. 기본 경로 확인 (회전된 파일명도 포함)
            if not temp_capture_file:
                # 회전된 파일들 찾기
                pattern = "temp_captures/temp_capture*.pcapng"
                capture_files = glob.glob(pattern)
                if capture_files:
                    # 가장 최근 파일 사용
                    temp_capture_file = max(capture_files, key=os.path.getmtime)
                    self.logger.info(f"회전된 temp_capture_file 발견: {temp_capture_file}")
                else:
                    temp_capture_file = "temp_captures/temp_capture.pcapng"
                    self.logger.info(f"기본 temp_capture_file 사용: {temp_capture_file}")

            # 3. temp_captures 디렉토리 확인 및 생성
            temp_captures_dir = "temp_captures"
            if not os.path.exists(temp_captures_dir):
                os.makedirs(temp_captures_dir)
                self.logger.info(f"temp_captures 디렉토리 생성: {temp_captures_dir}")

            # 4. 파일 존재 확인 및 처리
            if os.path.exists(temp_capture_file):
                file_size = os.path.getsize(temp_capture_file)
                self.logger.info(f"전역 캡처 파일 발견: {temp_capture_file} ({file_size} bytes)")

                if file_size > 0:
                    # Dashboard에서 active_calls 및 최신 Call-ID 정보 가져오기
                    active_calls_data = None
                    latest_terminated_call_id = None
                    
                    if self.dashboard and hasattr(self.dashboard, 'active_calls'):
                        active_calls_data = dict(self.dashboard.active_calls)
                        self.logger.info(f"Active calls 데이터 전달: {len(active_calls_data)}개 세션")
                    
                    self.logger.info(f"Dashboard 연결 상태: dashboard={self.dashboard is not None}")
                    if self.dashboard:
                        self.logger.info(f"Dashboard 속성 체크: has_latest_terminated_call_id={hasattr(self.dashboard, 'latest_terminated_call_id')}")
                        if hasattr(self.dashboard, 'latest_terminated_call_id'):
                            latest_terminated_call_id = self.dashboard.latest_terminated_call_id
                            self.logger.info(f"✅ 최신 종료 Call-ID 전달: {latest_terminated_call_id}")
                        else:
                            self.logger.warning("❌ Dashboard에 latest_terminated_call_id 속성이 없음")
                    else:
                        self.logger.warning("❌ Dashboard가 연결되지 않음")

                    # process_captured_pcap으로 Call-ID별 분리 및 WAV 변환 (최신 Call-ID 정보 포함)
                    self.process_captured_pcap(temp_capture_file, active_calls_data, latest_terminated_call_id)
                else:
                    self.logger.warning(f"전역 캡처 파일이 비어있음: {temp_capture_file}")
            else:
                self.logger.warning(f"전역 캡처 파일 없음: {temp_capture_file}")

        except Exception as e:
            self.logger.error(f"WAV 변환 중 오류: {e}")

    def convert_and_save(self, call_info):
        """WAV 변환 및 저장 (호환성을 위한 메서드)"""
        # 실제로는 delayed_wav_conversion에서 처리됨
        pass

    def cleanup_all_recordings(self):
        """모든 녹음 정리"""
        try:
            count = len(self.recordings)
            self.recordings.clear()
            self.logger.info(f"녹음 정리: {count}개 항목")
            self.logger.info("모든 녹음 정리 완료")
        except Exception as e:
            self.logger.error(f"전체 녹음 정리 오류: {e}")

    def get_active_recordings(self):
        """활성 녹음 목록 반환 (호환성)"""
        return dict(self.recordings)


# 전역 인스턴스 관리 (ExtensionRecordingManager 호환성)
_recording_manager_instance = None

def get_recording_manager(dashboard_instance=None):
    """SipRtpSessionGrouper 인스턴스를 반환하는 팩토리 함수 (ExtensionRecordingManager 호환성)"""
    global _recording_manager_instance
    if _recording_manager_instance is None:
        _recording_manager_instance = SipRtpSessionGrouper(dashboard_instance)
        if dashboard_instance:
            _recording_manager_instance.logger.info(f"새 SipRtpSessionGrouper 생성, Dashboard 연결: {dashboard_instance is not None}")
    elif dashboard_instance and _recording_manager_instance.dashboard != dashboard_instance:
        # Dashboard가 변경되었거나 처음 연결되는 경우
        _recording_manager_instance.dashboard = dashboard_instance
        _recording_manager_instance.logger.info("Dashboard 인스턴스 연결됨 (기존 인스턴스 업데이트)")
    elif dashboard_instance is None and _recording_manager_instance.dashboard is not None:
        _recording_manager_instance.logger.warning("Dashboard 인스턴스가 None으로 변경됨")
    
    # 현재 상태 로그
    _recording_manager_instance.logger.info(f"Recording Manager 상태: Dashboard 연결={_recording_manager_instance.dashboard is not None}")
    return _recording_manager_instance
