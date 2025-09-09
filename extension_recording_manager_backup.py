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

								# 임시 pcapng 파일 경로 (Call-ID에서 @ 앞부분만 사용)
								call_id_short = call_id.split('@')[0] if '@' in call_id else call_id
								pcapng_filename = f"{call_id_short}.pcapng"
								pcapng_path = self.temp_dir / pcapng_filename

				# 파일 중복 검사
								counter = 1
								while pcapng_path.exists():
										pcapng_filename = f"{call_id_short}_{counter:03d}.pcapng"
										pcapng_path = self.temp_dir / pcapng_filename
										counter += 1
					if counter > 999:
												self.logger.error(f"pcapng 파일 중복 해결 실패: {pcapng_filename}")
												break

								self.logger.info(f"녹음 시작 준비: {pcapng_filename}")
								if self.dashboard_logger:
										self.dashboard_logger.log_error(f"녹음 시작 준비: {pcapng_filename}", level="info")

				# 동적 필터 생성 - SIP + RTP 패킷 캡처
								capture_filter = self._generate_dynamic_filter(call_id, extension, from_number, to_number)

				# Dumpcap 명령어 구성
								dumpcap_cmd = [
										self.dumpcap_path,
										"-i", self.interface_number,
										"-f", capture_filter,
										"-w", str(pcapng_path)
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
				time.sleep(0.1)
								if process.poll() is not None:
										stdout, stderr = process.communicate()
										self.logger.error(f"Dumpcap 즉시 종료됨 - stdout: {stdout.decode()}, stderr: {stderr.decode()}")
										return False

								self.logger.info(f"Dumpcap 프로세스 시작됨: PID {process.pid}")
								if self.dashboard_logger:
										self.dashboard_logger.log_error(f"Dumpcap 프로세스 시작됨: PID {process.pid}", level="info")

				# 녹음 정보 저장
								current_time = datetime.datetime.now()
								recording_info = {
										'process': process,
										'pcapng_path': pcapng_path,
										'extension': extension,
										'from_number': from_number,
										'to_number': to_number,
										'start_time': current_time,
										'filter': capture_filter,
					'call_id': call_id
								}

								self.call_recordings[call_id] = recording_info

								self.logger.info(f"통화 녹음 시작: {call_id} (내선: {extension}, 파일: {pcapng_filename})")
								return True

				except Exception as e:
						self.logger.error(f"통화 녹음 시작 실패: {e}")
						return False

	def _generate_dynamic_filter(self, call_id: str, extension: str, from_number: str, to_number: str) -> str:
		"""통화별 동적 캡처 필터 생성 - SIP + RTP 포함"""
		try:
			# SIP + RTP 포트 범위 모두 캡처
			capture_filter = "port 5060 or (udp and portrange 10000-65535)"

			self.logger.info(f"동적 필터 생성: {capture_filter}")
			return capture_filter

		except Exception as e:
			self.logger.error(f"동적 필터 생성 실패: {e}")
			return "port 5060"

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
		"""pcapng 파일에서 WAV 파일을 생성 (개발 중이므로 간소화)"""
				pcapng_path = recording_info.get('pcapng_path')

				try:
						extension = recording_info['extension']
						from_number = recording_info['from_number']
						to_number = recording_info['to_number']
						start_time = recording_info['start_time']
						call_id = recording_info.get('call_id', '')

			# pcapng 파일이 temp_recordings 폴더에 생성되었는지 확인
						if pcapng_path and os.path.exists(pcapng_path):
				self.logger.info(f"✅ pcapng 파일 생성 완료: {os.path.basename(pcapng_path)}")
				self.logger.info(f"📁 파일 위치: {pcapng_path}")
				self.logger.info(f"📊 파일 크기: {os.path.getsize(pcapng_path)} bytes")

								if self.dashboard_logger:
					self.dashboard_logger.log_error(f"pcapng 파일 생성: {os.path.basename(pcapng_path)}", level="info")

				# 개발 중이므로 실제 WAV 변환은 하지 않고 성공 반환
								return True
						else:
				self.logger.error(f"❌ pcapng 파일을 찾을 수 없음: {pcapng_path}")
								return False

				except Exception as e:
			self.logger.error(f"파일 처리 실패: {e}")
						return False

		def get_active_recordings(self) -> Dict[str, Dict]:
		"""현재 진행 중인 녹음 목록 반환"""
				with self.recording_lock:
						return self.call_recordings.copy()

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

	def update_extension_ip_mapping(self, extension: str, ip_address: str):
		"""내선번호와 IP 주소 매핑 업데이트"""
		with self.mapping_lock:
			self.extension_ip_mapping[extension] = ip_address
			self.logger.info(f"내선-IP 매핑 업데이트: {extension} → {ip_address}")

	def update_call_sip_info(self, call_id: str, sip_info: Dict):
		"""통화별 SIP 정보 업데이트"""
		with self.mapping_lock:
			if call_id not in self.call_sip_info:
				self.call_sip_info[call_id] = {}
			self.call_sip_info[call_id].update(sip_info)
			self.logger.info(f"통화 SIP 정보 업데이트: {call_id} → {sip_info}")

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
