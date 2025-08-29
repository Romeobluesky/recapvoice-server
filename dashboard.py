#!/mvenv/Scripts/activate
# -*- coding: utf-8 -*-
import asyncio
import atexit
import configparser
import datetime
import gc
import os
import platform
import psutil
import re
import socket
import subprocess
import sys
import threading
import traceback
import win32con
import win32gui
import win32process
import time
import argparse

# 서드파티 라이브러리
from enum import Enum, auto
import pyshark
import requests
# import websockets  # 제거: 직접 사용하지 않음, WebSocketServer에서 사용
import json
from pydub import AudioSegment
from pymongo import MongoClient
from extension_recording_manager import get_recording_manager
from PySide6.QtCore import *
from PySide6.QtGui import *
from PySide6.QtNetwork import *
from PySide6.QtWidgets import *

# 로컬 모듈
from config_loader import load_config, get_wireshark_path
from settings_popup import SettingsPopup
from wav_merger import WavMerger
from flow_layout import FlowLayout
from callstate_machine import CallStateMachine
from callstate_machine import CallState
from websocketserver import WebSocketServer

def resource_path(relative_path):
		"""리소스 파일의 절대 경로를 반환"""
		if hasattr(sys, '_MEIPASS'):
				return os.path.join(sys._MEIPASS, relative_path)
		return os.path.join(os.path.abspath('.'), relative_path)

def remove_ansi_codes(text):
		"""ANSI 색상 코드 제거"""
		import re
		ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
		return ansi_escape.sub('', text)

def is_extension(number):
		return len(str(number)) == 4 and str(number)[0] in '123456789'

class Dashboard(QMainWindow):
		# Signal: 내선번호, 상태, 수신번호 전달
		block_creation_signal = Signal(str)
		block_update_signal = Signal(str, str, str)
		extension_update_signal = Signal(str)  # 내선번호 업데이트 Signal
		start_led_timer_signal = Signal(object)  # LED 타이머 시작 Signal
		sip_packet_signal = Signal(object)  # SIP 패킷 분석 Signal
		safe_log_signal = Signal(str, str)  # 스레드 안전 로깅 Signal

		_instance = None  # 클래스 변수로 인스턴스 추적

		def get_work_directory(self):
				"""작업 디렉토리를 결정합니다 (개발/프로덕션 모드에 따라)"""
				try:
						# 설정 파일이 존재하는지 확인
						if os.path.exists('settings.ini'):
								config = configparser.ConfigParser()
								config.read('settings.ini', encoding='utf-8')

								# 모드 확인
								mode = config.get('Environment', 'mode', fallback='development')

								if mode == 'production':
										# 프로덕션 모드: ProgramFiles(x86) 사용
										return os.path.join(os.environ.get('ProgramFiles(x86)', 'C:\\Program Files (x86)'), 'Recap Voice')
								else:
										# 개발 모드: 설정 파일의 dir_path 사용
										return config.get('DefaultDirectory', 'dir_path', fallback=os.getcwd())
						else:
								# 설정 파일이 없으면 현재 디렉토리 사용
								return os.getcwd()
				except Exception:
						# 오류 발생 시 현재 디렉토리 사용
						return os.getcwd()

		def __init__(self):
				try:
						super().__init__()
						Dashboard._instance = self
						self.setup_single_instance()
						self.cleanup_existing_dumpcap()  # 프로그램 시작 시 기존 Dumpcap 프로세스 정리

						# 명령줄 인수에서 로그 레벨 가져오기
						parser = argparse.ArgumentParser()
						parser.add_argument("--log-level", choices=["debug", "info", "warning", "error"], default="info")
						args, _ = parser.parse_known_args()
						self.log_level = args.log_level

						# 작업 디렉토리 설정
						self.work_dir = self.get_work_directory()

						# 필수 디렉토리 확인 및 생성 (작업 디렉토리 기준)
						required_dirs = ['images', 'logs']
						for dir_name in required_dirs:
								try:
										full_path = os.path.join(self.work_dir, dir_name)
										if not os.path.exists(full_path):
												os.makedirs(full_path, exist_ok=True)
								except PermissionError:
										# 권한 문제 시 임시 디렉토리 사용
										import tempfile
										temp_dir = tempfile.gettempdir()
										fallback_path = os.path.join(temp_dir, 'PacketWave', dir_name)
										try:
												os.makedirs(fallback_path, exist_ok=True)
												print(f"권한 문제로 임시 디렉토리 사용: {fallback_path}")
												# 작업 디렉토리를 임시 디렉토리로 변경
												self.work_dir = os.path.join(temp_dir, 'PacketWave')
										except Exception as fallback_error:
												print(f"임시 디렉토리 생성도 실패: {fallback_error}")
												raise
								except Exception as e:
										print(f"디렉토리 생성 실패: {dir_name} - {e}")
										raise

						# 설정 파일 확인 (work_dir 기준)
						settings_path = os.path.join(self.work_dir, 'settings.ini')
						if not os.path.exists(settings_path):
								print(f"settings.ini 파일이 없습니다: {settings_path}")
								raise FileNotFoundError(f"settings.ini 파일이 필요합니다: {settings_path}")

						# 로그 파일 초기화
						try:
								self.initialize_log_file()
						except Exception as e:
								print(f"로그 파일 초기화 실패: {e}")
								raise

						# 메인 윈도우 바로 초기화
						self.initialize_main_window()

				except Exception as e:
						self.log_error("대시보드 초기화 실패", e)
						raise

		def initialize_log_file(self):
				"""로그 파일을 초기화합니다."""
				try:
						# 로그 디렉토리 확인 (work_dir 기준)
						log_dir = os.path.join(self.work_dir, 'logs')
						if not os.path.exists(log_dir):
								try:
										os.makedirs(log_dir, exist_ok=True)
								except PermissionError:
										# 권한 문제 시 임시 디렉토리 사용
										import tempfile
										log_dir = os.path.join(tempfile.gettempdir(), 'PacketWave', 'logs')
										os.makedirs(log_dir, exist_ok=True)
										print(f"권한 문제로 로그를 임시 디렉토리에 생성: {log_dir}")
										# work_dir 업데이트
										self.work_dir = os.path.join(tempfile.gettempdir(), 'PacketWave')

						# 오늘 날짜로 로그 파일 이름 생성
						today = datetime.datetime.now().strftime("%Y%m%d")
						log_file_path = os.path.join(log_dir, f'voip_monitor_{today}.log')

						# 현재 로그 파일로 심볼릭 링크 생성
						current_log_path = os.path.join(self.work_dir, 'logs', 'voip_monitor.log')
						if os.path.exists(current_log_path):
								if os.path.islink(current_log_path):
										os.remove(current_log_path)
								else:
										# 기존 파일이 있으면 백업
										backup_path = f"{current_log_path}.bak"
										if os.path.exists(backup_path):
												os.remove(backup_path)
										os.rename(current_log_path, backup_path)

						# 윈도우에서는 심볼릭 링크 대신 하드 링크 사용
						if os.name == 'nt':
								# 로그 파일 직접 생성
								with open(log_file_path, 'a', encoding='utf-8') as f:
										f.write(f"\n=== 프로그램 시작: {datetime.datetime.now()} ===\n")

								# voip_monitor.log 파일도 직접 생성
								with open(current_log_path, 'w', encoding='utf-8') as f:
										f.write(f"\n=== 프로그램 시작: {datetime.datetime.now()} ===\n")
						else:
								# Unix 시스템에서는 심볼릭 링크 사용
								with open(log_file_path, 'a', encoding='utf-8') as f:
										f.write(f"\n=== 프로그램 시작: {datetime.datetime.now()} ===\n")
								os.symlink(log_file_path, current_log_path)

						self.log_error("로그 파일 초기화 완료", level="info")
				except Exception as e:
						print(f"로그 파일 초기화 중 오류: {e}")
						raise

		def setup_single_instance(self):
				"""단일 인스턴스 관리 설정"""
				try:
						self.instance_server = QLocalServer(self)
						self.instance_client = QLocalSocket(self)

						# 기존 서버 정리
						QLocalServer.removeServer("RecapVoiceInstance")

						# 서버 시작
						self.instance_server.listen("RecapVoiceInstance")
						self.instance_server.newConnection.connect(self.handle_instance_connection)

				except Exception as e:
						self.log_error("단일 인스턴스 설정 실패", e)

		def handle_instance_connection(self):
				"""새로운 인스턴스 연결 처리"""
				try:
						socket = self.instance_server.nextPendingConnection()
						if socket.waitForReadyRead(1000):
								if socket.read(4) == b"show":
										self.restore_window()
				except Exception as e:
						self.log_error("인스턴스 연결 처리 실패", e)

		def restore_window(self):
				"""창 복원 통합 메서드"""
				try:
						if self.isMinimized():
								self.setWindowState(self.windowState() & ~Qt.WindowMinimized)
						self.show()
						self.activateWindow()
						self.raise_()
				except Exception as e:
						self.log_error("창 복원 실패", e)


		def initialize_main_window(self):
				try:


						# 전체 화면 해제 및 창 설정 복원
						try:
								self.setWindowFlag(Qt.FramelessWindowHint, False)
								self.setWindowState(Qt.WindowMaximized)  # 미리 최대화 상태로 설정
						except Exception as e:
								self.log_error("창 상태 설정 실패", e)

						# 기존 초기화 코드 실행
						try:
								self.setWindowIcon(QIcon(resource_path("images/recapvoice_squere.ico")))
								self.setWindowTitle("Recap Voice")
								self.setAttribute(Qt.WA_QuitOnClose, False)
								# Signal 연결 - 메인 스레드에서 안전하게 실행되도록 QueuedConnection 사용
								self.extension_update_signal.connect(self.update_extension_in_main_thread, Qt.QueuedConnection)
								self.start_led_timer_signal.connect(self.start_led_timer_in_main_thread, Qt.QueuedConnection)
								self.sip_packet_signal.connect(self.analyze_sip_packet_in_main_thread, Qt.QueuedConnection)

								# 스레드 안전 로깅을 위한 시그널 연결
								self.safe_log_signal.connect(self.log_to_sip_console, Qt.QueuedConnection)
								self.settings_popup = SettingsPopup()
								self.active_calls_lock = threading.RLock()
								self.active_calls = {}
								self.active_streams = set()  # active_streams 속성 추가
								self.call_state_machines = {}
								self.capture_thread = None

								# 타이머 설정
								self.voip_timer = QTimer()
								self.voip_timer.timeout.connect(self.update_voip_status)
								self.voip_timer.start(1000)

								self.streams = {}
								self.packet_timer = QTimer()
								self.packet_timer.timeout.connect(self.update_packet_status)
								self.packet_timer.start(1000)

								# 리소스 모니터링 타이머 설정
								self.resource_timer = QTimer()
								self.resource_timer.timeout.connect(self.monitor_system_resources)
								self.resource_timer.start(30000)  # 30초마다 체크

								self.sip_registrations = {}
								self.sip_extensions = set()  # SIP 내선번호 집합
								self.first_registration = False
								
								# RTP 패킷 카운터 시스템
								self.rtp_counters = {}  # 연결별 패킷 카운터 저장
								self.rtp_display_lines = {}  # 각 연결의 콘솔 표시 관리
								self.packet_get = 0
								# 토글 기능 제거 - 관련 변수들 제거

								# 통화별 녹음 관리자 초기화
								self.recording_manager = get_recording_manager(logger=self, dashboard_instance=self)

								# 녹음 상태 모니터링 타이머 설정
								self.recording_status_timer = QTimer()
								self.recording_status_timer.timeout.connect(self.update_recording_status_display)
								self.recording_status_timer.start(10000)  # 10초마다 업데이트

								# 메모리 캐시 초기화
								gc.collect()

						except Exception as e:
								self.log_error("기본 설정 초기화 실패", e)
								raise

						try:
								self._init_ui()
						except Exception as e:
								self.log_error("UI 초기화 실패", e)
								raise

						try:
								self.selected_interface = None
								self.load_network_interfaces()
								# SIP 패킷 캡처는 웹서비스 완료 후 시작
								# QTimer.singleShot(1000, self.start_packet_capture)  # 제거
						except Exception as e:
								self.log_error("네트워크 인터페이스 초기화 실패", e)

						try:
								self.duration_timer = QTimer()
								self.duration_timer.timeout.connect(self.update_call_duration)
								self.duration_timer.start(1000)
								self.wav_merger = WavMerger()
						except Exception as e:
								self.log_error("타이머 및 유틸리티 초기화 실패", e)

						# MongoDB 연결 (타임아웃 설정 포함)
						try:
								# MongoDB 설정 읽기
								config = load_config()
								mongo_host = config.get('MongoDB', 'host', fallback='localhost')
								mongo_port = config.getint('MongoDB', 'port', fallback=27017)
								mongo_database = config.get('MongoDB', 'database', fallback='packetwave')
								mongo_username = config.get('MongoDB', 'username', fallback='')
								mongo_password = config.get('MongoDB', 'password', fallback='')

								# MongoDB 연결 문자열 생성
								if mongo_username and mongo_password:
										mongo_uri = f"mongodb://{mongo_username}:{mongo_password}@{mongo_host}:{mongo_port}/"
								else:
										mongo_uri = f"mongodb://{mongo_host}:{mongo_port}/"

								self.log_error(f"MongoDB 연결 시도: {mongo_uri}", level="info")

								# 타임아웃 증가로 연결 안정성 향상
								self.mongo_client = MongoClient(
										mongo_uri,
										serverSelectionTimeoutMS=10000,  # 10초 타임아웃
										connectTimeoutMS=10000,
										socketTimeoutMS=10000
								)
								self.db = self.mongo_client[mongo_database]
								self.members = self.db['members']
								self.filesinfo = self.db['filesinfo']
								self.internalnumber = self.db['internalnumber']

								# 연결 테스트
								self.mongo_client.admin.command('ping')
								self.log_error("MongoDB 연결 성공", level="info")

						except Exception as e:
								# 초기 연결 실패는 로그에 남기지 않음 (재시도에서 해결될 가능성 높음)
								# MongoDB 없이도 프로그램이 계속 실행되도록 설정
								self.mongo_client = None
								self.db = None
								self.members = None
								self.filesinfo = None
								self.internalnumber = None

								# 5초 후 재시도
								QTimer.singleShot(5000, self.retry_mongodb_connection)

						config = load_config()
						if config.get('Environment', 'mode') == 'production':
								try:
										wireshark_path = get_wireshark_path()
										def hide_wireshark_windows():
												try:
														for proc in psutil.process_iter(['pid', 'name', 'exe']):
																if proc.info['name'] in ['dumpcap.exe', 'tshark.exe']:
																		if proc.info['exe'] and wireshark_path in proc.info['exe']:
																				def enum_windows_callback(hwnd, _):
																						try:
																								_, pid = win32process.GetWindowThreadProcessId(hwnd)
																								if pid == proc.info['pid']:
																										style = win32gui.GetWindowLong(hwnd, win32con.GWL_STYLE)
																										style &= ~win32con.WS_VISIBLE
																										win32gui.SetWindowLong(hwnd, win32con.GWL_STYLE, style)
																										win32gui.ShowWindow(hwnd, win32con.SW_HIDE)
																						except Exception as callback_error:
																								self.log_error("윈도우 콜백 처리 실패", callback_error)
																						return True
																				win32gui.EnumWindows(enum_windows_callback, None)
												except Exception as hide_error:
														self.log_error("Wireshark 윈도우 숨기기 실패", hide_error)

										self.hide_console_timer = QTimer()
										self.hide_console_timer.timeout.connect(hide_wireshark_windows)
										self.hide_console_timer.start(100)
								except Exception as e:
										self.log_error("Wireshark 설정 실패", e)

						try:
								self.setup_tray_icon()
						except Exception as e:
								self.log_error("트레이 아이콘 설정 실패", e)

						try:
								# 클라이언트 서비스를 즉시 시작 (논블로킹)
								self._start_client_services()
								print("클라이언트 서버가 백그라운드에서 시작되었습니다.")
						except Exception as e:
								self.log_error("클라이언트 서버 시작 실패", e)

						try:
								atexit.register(self.cleanup)

								# 리소스 모니터링 타이머 설정
								self.resource_timer = QTimer()
								self.resource_timer.timeout.connect(self.monitor_system_resources)
								self.resource_timer.start(10000)  # 10초마다 체크

								# 스레드 관리를 위한 변수 추가
								self.active_threads = set()
								self.thread_lock = threading.Lock()

								# 의존성 및 시스템 제한 체크
								self.check_system_limits()
						except Exception as e:
								self.log_error("시스템 모니터링 설정 실패", e)

						# UI가 완전히 준비된 후 창 표시
						try:
								QTimer.singleShot(100, self.show_maximized_window)
						except Exception as e:
								self.log_error("창 표시 실패", e)

						# WebSocket 서버 시작
						try:
								websocket_port = 8765  # 기본 포트
								max_retry = 3
								retry_count = 0

								while retry_count < max_retry:
										try:
												print(f"WebSocket 서버 시작 시도 (포트: {websocket_port})...")
												self.websocket_server = WebSocketServer(port=websocket_port, log_callback=self.log_error)
												self.websocket_thread = threading.Thread(target=self.websocket_server.run_in_thread, daemon=True)
												self.websocket_thread.start()
												print(f"WebSocket 서버가 포트 {websocket_port}에서 시작되었습니다.")
												break
										except OSError as e:
												if "Address already in use" in str(e) or "각 소켓 주소" in str(e):
														retry_count += 1
														websocket_port += 1
														print(f"포트 {websocket_port-1}가 이미 사용 중입니다. 포트 {websocket_port}로 재시도합니다.")
												else:
														self.log_error("WebSocket 서버 시작 실패", e)
														break
										except Exception as e:
												self.log_error("WebSocket 서버 시작 실패", e)
												break

								if retry_count >= max_retry:
										self.log_error(f"WebSocket 서버 시작 실패: 최대 재시도 횟수 ({max_retry})를 초과했습니다.")
						except Exception as e:
								self.log_error("WebSocket 서버 시작 중 예외 발생", e)

				except Exception as e:
						self.log_error("메인 윈도우 초기화 중 심각한 오류", e)
						raise

		def show_maximized_window(self):
				"""최대화된 상태로 창을 표시"""
				self.showMaximized()  # show() 대신 showMaximized() 사용
				self.raise_()
				self.activateWindow()

		def retry_mongodb_connection(self):
				"""MongoDB 재연결 시도"""
				try:
						# MongoDB 설정 읽기
						config = load_config()
						mongo_host = config.get('MongoDB', 'host', fallback='localhost')
						mongo_port = config.getint('MongoDB', 'port', fallback=27017)
						mongo_database = config.get('MongoDB', 'database', fallback='packetwave')
						mongo_username = config.get('MongoDB', 'username', fallback='')
						mongo_password = config.get('MongoDB', 'password', fallback='')

						# MongoDB 연결 문자열 생성
						if mongo_username and mongo_password:
								mongo_uri = f"mongodb://{mongo_username}:{mongo_password}@{mongo_host}:{mongo_port}/"
						else:
								mongo_uri = f"mongodb://{mongo_host}:{mongo_port}/"

						# 재시도 로그는 간단하게만
						# self.log_error("MongoDB 재연결 시도", level="info")

						# 타임아웃 증가로 연결 안정성 향상
						self.mongo_client = MongoClient(
								mongo_uri,
								serverSelectionTimeoutMS=10000,  # 10초 타임아웃
								connectTimeoutMS=10000,
								socketTimeoutMS=10000
						)
						self.db = self.mongo_client[mongo_database]
						self.members = self.db['members']
						self.filesinfo = self.db['filesinfo']
						self.internalnumber = self.db['internalnumber']

						# 연결 테스트
						self.mongo_client.admin.command('ping')
						self.log_error("MongoDB 연결 성공", level="info")

				except Exception as e:
						# 재시도도 실패한 경우에만 로그 기록
						self.log_error("MongoDB 연결 최종 실패", e)
						# 연결이 계속 실패하면 MongoDB 없이 동작
						self.mongo_client = None
						self.db = None
						self.members = None
						self.filesinfo = None
						self.internalnumber = None

		def cleanup(self):
				# 모든 타이머 정리
				try:
						# 기본 타이머들 정리
						for timer_name in ['voip_timer', 'packet_timer', 'resource_timer', 'duration_timer', 'hide_console_timer']:
								if hasattr(self, timer_name):
										timer = getattr(self, timer_name)
										if timer and hasattr(timer, 'stop'):
												timer.stop()
												timer.deleteLater()

						# LED 타이머들 정리
						if hasattr(self, 'extension_list_container'):
								self.cleanup_led_timers(self.extension_list_container)
						
						# RTP 카운터 정리
						if hasattr(self, 'rtp_counters'):
								self.rtp_counters.clear()
						if hasattr(self, 'rtp_display_lines'):
								self.rtp_display_lines.clear()

						print("타이머 정리 완료")
				except Exception as e:
						print(f"타이머 정리 중 오류: {e}")

				# 기존 cleanup 코드
				if hasattr(self, 'capture') and self.capture:
						try:
								if hasattr(self, 'loop') and self.loop and self.loop.is_running():
										self.loop.run_until_complete(self.capture.close_async())
								else:
										self.capture.close()
						except Exception as e:
								print(f"Cleanup error: {e}")

				# tshark와 dumpcap 프로세스 정리
				try:
						self.stop_wireshark_processes()
				except Exception as e:
						print(f"Wireshark 프로세스 정리 중 오류: {e}")

				# WebSocket 서버 정리
				if hasattr(self, 'websocket_server') and self.websocket_server:
						try:
								if self.websocket_server.running:
										asyncio.run(self.websocket_server.stop_server())
										print("WebSocket 서버가 종료되었습니다.")
						except Exception as e:
								print(f"WebSocket server cleanup error: {e}")

		def _init_ui(self):
				main_widget = QWidget()
				self.setCentralWidget(main_widget)
				layout = QHBoxLayout(main_widget)
				layout.setContentsMargins(0, 0, 0, 0)
				layout.setSpacing(0)
				self.sidebar = self._create_sidebar()
				layout.addWidget(self.sidebar)
				content = QWidget()
				content_layout = QVBoxLayout(content)
				content_layout.setContentsMargins(20, 20, 20, 20)
				content_layout.setSpacing(20)
				layout.addWidget(content)
				header = self._create_header()
				content_layout.addWidget(header)
				status_section = self._create_status_section()
				content_layout.addLayout(status_section)
				log_list = self._create_log_list()
				content_layout.addWidget(log_list, 60)  # 비율 조정

				# SIP 콘솔 로그 레이어 추가
				sip_console = self._create_sip_console_log()
				content_layout.addWidget(sip_console, 40)  # 비율 조정

				content_layout.setStretch(2, 60)  # LOG LIST 비율
				content_layout.setStretch(3, 40)  # SIP CONSOLE LOG 비율
				self._apply_styles()
				self.resize(1400, 900)
				self.settings_popup.settings_changed.connect(self.update_dashboard_settings)
				self.settings_popup.path_changed.connect(self.update_storage_path)
				self.settings_popup.network_ip_changed.connect(self.on_network_ip_changed)

				# calls_layout을 빈 레이아웃으로 초기화 (전화연결상태 블록 대신)
				self.calls_layout = QVBoxLayout()
				self.calls_container = QWidget()

				# 내선번호 표시 업데이트 (약간의 지연 후)
				QTimer.singleShot(100, self.update_extension_display)

				# SIP 콘솔 초기화 메시지
				QTimer.singleShot(500, self.init_sip_console_welcome)


		def load_network_interfaces(self):
				try:
						# 모든 네트워크 인터페이스 정보 수집
						all_interfaces = psutil.net_if_addrs()
						active_interfaces = []

						print("=== 네트워크 인터페이스 분석 ===")
						self.log_to_sip_console("네트워크 인터페이스 분석 시작", "DEBUG")

						for interface_name, addresses in all_interfaces.items():
								try:
										# 인터페이스 상태 확인
										if_stats = psutil.net_if_stats().get(interface_name)
										if not if_stats or not if_stats.isup:
												continue

										# IP 주소 확인
										has_ip = False
										ip_address = None
										for addr in addresses:
												if addr.family == socket.AF_INET:  # IPv4
														ip_address = addr.address
														if ip_address != '127.0.0.1':  # 루프백 제외
																has_ip = True
																break

										if has_ip:
												active_interfaces.append({
														'name': interface_name,
														'ip': ip_address,
														'stats': if_stats
												})
												print(f"활성 인터페이스: {interface_name} (IP: {ip_address})")
												self.log_to_sip_console(f"활성 인터페이스 발견: {interface_name} (IP: {ip_address})", "DEBUG")
								except Exception as e:
										print(f"인터페이스 {interface_name} 분석 중 오류: {e}")

						# 포트미러링에 적합한 인터페이스 선택
						selected_interface = self.select_best_interface(active_interfaces)

						# 설정 파일에서 저장된 인터페이스 확인
						config = load_config()
						saved_interface = config.get('Network', 'interface', fallback='')

						# 저장된 인터페이스가 활성 상태라면 우선 사용
						if saved_interface and any(iface['name'] == saved_interface for iface in active_interfaces):
								selected_interface = saved_interface
								print(f"저장된 인터페이스 사용: {saved_interface}")
								self.log_to_sip_console(f"저장된 인터페이스 사용: {saved_interface}", "INFO")
						else:
								print(f"자동 선택된 인터페이스: {selected_interface}")
								self.log_to_sip_console(f"자동 선택된 인터페이스: {selected_interface}", "INFO")

						self.selected_interface = selected_interface
						self.active_interfaces = active_interfaces  # 나중에 설정에서 선택할 수 있도록 저장

						# 자동 선택된 인터페이스를 settings.ini에 저장
						if selected_interface and not saved_interface:
								self.save_interface_to_config(selected_interface)

				except Exception as e:
						print(f"네트워크 인터페이스 로드 실패: {e}")
						self.log_error("네트워크 인터페이스 로드 실패", e)

		def select_best_interface(self, active_interfaces):
				"""포트미러링에 최적인 네트워크 인터페이스 선택"""
				if not active_interfaces:
						print("활성 인터페이스가 없음")
						return None

				print("=== 최적 인터페이스 선택 ===")

				# 우선순위 기반 선택
				# 1. 이더넷 인터페이스 우선 (Wi-Fi보다 안정적)
				ethernet_interfaces = []
				wifi_interfaces = []
				other_interfaces = []

				for iface in active_interfaces:
						name = iface['name'].lower()
						if 'ethernet' in name or '이더넷' in name:
								ethernet_interfaces.append(iface)
						elif 'wi-fi' in name or 'wifi' in name or 'wireless' in name:
								wifi_interfaces.append(iface)
						else:
								other_interfaces.append(iface)

				# 2. 이더넷 인터페이스가 있다면 우선 선택
				if ethernet_interfaces:
						# 이더넷 중에서도 가장 적절한 것 선택
						best_ethernet = self.find_best_ethernet_interface(ethernet_interfaces)
						print(f"이더넷 인터페이스 선택: {best_ethernet['name']}")
						self.log_to_sip_console(f"이더넷 인터페이스 선택: {best_ethernet['name']}", "INFO")
						return best_ethernet['name']

				# 3. 이더넷이 없다면 Wi-Fi 또는 기타 인터페이스
				all_remaining = wifi_interfaces + other_interfaces
				if all_remaining:
						selected = all_remaining[0]
						print(f"대체 인터페이스 선택: {selected['name']}")
						self.log_to_sip_console(f"대체 인터페이스 선택: {selected['name']}", "INFO")
						return selected['name']

				return active_interfaces[0]['name'] if active_interfaces else None

		def find_best_ethernet_interface(self, ethernet_interfaces):
				"""이더넷 인터페이스 중 최적 선택"""
				if len(ethernet_interfaces) == 1:
						return ethernet_interfaces[0]

				print(f"이더넷 인터페이스 {len(ethernet_interfaces)}개 발견, 최적 선택 중...")

				# 포트미러링 IP와 같은 대역의 인터페이스 우선 선택
				try:
						config = load_config()
						target_ip = config.get('Network', 'ip', fallback=None)

						if target_ip:
								target_network = target_ip.rsplit('.', 1)[0]  # 예: 1.1.1.2 -> 1.1.1
								print(f"포트미러링 IP 대역: {target_network}")

								for iface in ethernet_interfaces:
										iface_network = iface['ip'].rsplit('.', 1)[0]
										print(f"인터페이스 {iface['name']}: {iface['ip']} (대역: {iface_network})")

										if iface_network == target_network:
												print(f"포트미러링 IP와 같은 대역 인터페이스 발견: {iface['name']}")
												self.log_to_sip_console(f"포트미러링 IP와 같은 대역 인터페이스: {iface['name']}", "INFO")
												return iface
				except Exception as e:
						print(f"IP 대역 비교 중 오류: {e}")

				# 같은 대역이 없다면 가장 활성화된 인터페이스 선택
				# (바이트 송수신이 많은 인터페이스)
				best_interface = ethernet_interfaces[0]
				try:
						for iface in ethernet_interfaces:
								stats = iface['stats']
								if stats.bytes_sent + stats.bytes_recv > best_interface['stats'].bytes_sent + best_interface['stats'].bytes_recv:
										best_interface = iface
				except Exception as e:
						print(f"인터페이스 통계 비교 중 오류: {e}")

				print(f"최종 선택된 이더넷 인터페이스: {best_interface['name']}")
				return best_interface

		def save_interface_to_config(self, interface_name):
				"""선택된 인터페이스를 settings.ini에 저장"""
				try:
						config = configparser.ConfigParser()
						config.read('settings.ini', encoding='utf-8')

						if 'Network' not in config:
								config['Network'] = {}

						config['Network']['interface'] = interface_name

						with open('settings.ini', 'w', encoding='utf-8') as configfile:
								config.write(configfile)

						print(f"인터페이스 설정 저장: {interface_name}")
						self.log_to_sip_console(f"인터페이스 설정 저장: {interface_name}", "INFO")

				except Exception as e:
						print(f"인터페이스 설정 저장 실패: {e}")
						self.log_error("인터페이스 설정 저장 실패", e)

		def change_network_interface(self, new_interface_name):
				"""네트워크 인터페이스를 수동으로 변경"""
				try:
						print(f"=== 네트워크 인터페이스 수동 변경: {new_interface_name} ===")
						self.log_to_sip_console(f"네트워크 인터페이스 변경: {new_interface_name}", "INFO")

						# 새 인터페이스가 활성 상태인지 확인
						if hasattr(self, 'active_interfaces'):
								active_names = [iface['name'] for iface in self.active_interfaces]
								if new_interface_name not in active_names:
										print(f"경고: 인터페이스 '{new_interface_name}'가 활성 상태가 아닙니다")
										self.log_to_sip_console(f"경고: 인터페이스 '{new_interface_name}'가 활성 상태가 아닙니다", "WARNING")

						# 현재 인터페이스와 다른 경우에만 재시작
						if self.selected_interface != new_interface_name:
								old_interface = self.selected_interface
								self.selected_interface = new_interface_name

								# settings.ini에 저장
								self.save_interface_to_config(new_interface_name)

								# 패킷 캡처 재시작
								success = self.restart_packet_capture()

								if success:
										print(f"인터페이스 변경 완료: {old_interface} → {new_interface_name}")
										self.log_to_sip_console(f"인터페이스 변경 완료: {old_interface} → {new_interface_name}", "INFO")
								else:
										print(f"인터페이스 변경 실패, 이전 설정으로 복원")
										self.selected_interface = old_interface
										self.log_to_sip_console("인터페이스 변경 실패, 이전 설정으로 복원", "ERROR")

								return success
						else:
								print("동일한 인터페이스입니다")
								return True

				except Exception as e:
						print(f"네트워크 인터페이스 변경 중 오류: {e}")
						self.log_error("네트워크 인터페이스 변경 실패", e)
						return False

		def show_available_interfaces(self):
				"""사용 가능한 네트워크 인터페이스 목록 출력"""
				try:
						print("\n=== 사용 가능한 네트워크 인터페이스 ===")
						self.log_to_sip_console("사용 가능한 네트워크 인터페이스 조회", "INFO")

						if hasattr(self, 'active_interfaces') and self.active_interfaces:
								for i, iface in enumerate(self.active_interfaces, 1):
										status = "✓ 현재 사용중" if iface['name'] == self.selected_interface else ""
										print(f"{i}. {iface['name']} (IP: {iface['ip']}) {status}")
										self.log_to_sip_console(f"인터페이스 {i}: {iface['name']} (IP: {iface['ip']}) {status}", "INFO")
						else:
								print("활성 인터페이스 정보가 없습니다")
								self.load_network_interfaces()  # 다시 로드 시도

						print(f"\n현재 선택된 인터페이스: {self.selected_interface}")
						print("인터페이스 변경 방법:")
						print("  dashboard.change_network_interface('이더넷 3')")
						print("또는 SIP 콘솔에서 확인하세요.")

				except Exception as e:
						print(f"인터페이스 목록 조회 중 오류: {e}")
						self.log_error("인터페이스 목록 조회 실패", e)

		def start_packet_capture(self):
				"""패킷 캡처 시작"""
				try:
						if not self.selected_interface:
								self.log_error("선택된 네트워크 인터페이스가 없습니다")
								return

						if hasattr(self, 'capture_thread') and self.capture_thread and self.capture_thread.is_alive():
								self.log_error("패킷 캡처가 이미 실행 중입니다")
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
										self.log_error("시스템 리소스 부족", additional_info=resource_info, level="warning", console_output=False)
										# 리소스가 부족해도 계속 진행 - 종료하지 않음
						except Exception as e:
								self.log_error("시스템 리소스 체크 실패", e, console_output=False)
								# 실패해도 계속 진행

						# Wireshark 경로 확인
						config = load_config()
						if not config:
								self.log_error("설정 파일을 로드할 수 없습니다")
								return

						wireshark_path = get_wireshark_path()
						if not os.path.exists(wireshark_path):
								self.log_error("Wireshark가 설치되어 있지 않습니다")
								return

						# tshark와 dumpcap 실행 확인 및 시작 (비활성화)
						# self.start_wireshark_processes()  # ExtensionRecordingManager가 통화별 dumpcap 관리
						self.log_error("통화별 녹음 시스템 활성화 - 별도 Wireshark 프로세스 실행 생략", level="info")

						# 캡처 스레드 시작
						self.capture_thread = threading.Thread(
								target=self.capture_packets,
								args=(self.selected_interface,),
								daemon=True
						)
						self.capture_thread.start()
						self.log_error("패킷 캡처 시작됨", additional_info={"interface": self.selected_interface})

				except Exception as e:
						self.log_error("패킷 캡처 시작 실패", e)

		def start_wireshark_processes(self):
				"""tshark와 dumpcap 프로세스 직접 실행"""
				try:
						wireshark_path = get_wireshark_path()
						tshark_path = os.path.join(wireshark_path, "tshark.exe")
						dumpcap_path = os.path.join(wireshark_path, "dumpcap.exe")

						config = load_config()
						target_ip = config.get('Network', 'ip', fallback=None)

						# 1. tshark 프로세스 실행
						if os.path.exists(tshark_path):
								try:
										# 인터페이스 번호 찾기
										interface_cmd = [tshark_path, "-D"]
										result = subprocess.run(interface_cmd, capture_output=True, text=True, timeout=10)
										if result.returncode == 0:
												self.log_error(f"tshark 인터페이스 목록 조회 성공", additional_info={"output": result.stdout[:200]})

												# 선택된 인터페이스의 번호 찾기
												interface_number = self.get_interface_number(result.stdout, self.selected_interface)

												if interface_number:
														# tshark 실행 명령어 구성
														if target_ip:
																capture_filter = f"host {target_ip} or port 5060"
														else:
																capture_filter = "port 5060"

														tshark_cmd = [
																tshark_path,
																"-i", str(interface_number),
																"-f", capture_filter,
																"-l"  # 실시간 출력
														]

														# tshark 프로세스 시작 (백그라운드)
														self.tshark_process = subprocess.Popen(
																tshark_cmd,
																stdout=subprocess.PIPE,
																stderr=subprocess.PIPE,
																creationflags=subprocess.CREATE_NO_WINDOW
														)
														self.log_error("tshark 프로세스 시작됨", additional_info={"pid": self.tshark_process.pid})
												else:
														self.log_error(f"인터페이스 '{self.selected_interface}' 번호를 찾을 수 없습니다")
								except Exception as e:
										self.log_error(f"tshark 실행 실패: {e}")
						else:
								self.log_error(f"tshark.exe를 찾을 수 없습니다: {tshark_path}")

						# 2. dumpcap 프로세스 실행 (제거됨)
						# ExtensionRecordingManager가 통화별 dumpcap을 관리하므로 전역 dumpcap 불필요
						self.log_error("통화별 녹음 시스템 활성화됨 - 전역 dumpcap 비활성화", level="info")

				except Exception as e:
						self.log_error(f"Wireshark 프로세스 시작 실패: {e}")

		def get_interface_number(self, interface_list, interface_name):
				"""인터페이스 목록에서 선택된 인터페이스의 번호 찾기"""
				try:
						lines = interface_list.strip().split('\n')
						for line in lines:
								if interface_name in line:
										parts = line.split('.')
										if len(parts) > 0 and parts[0].strip().isdigit():
												return int(parts[0].strip())
						return None
				except Exception as e:
						self.log_error(f"인터페이스 번호 추출 실패: {e}")
						return None

		def stop_wireshark_processes(self):
				"""tshark와 dumpcap 프로세스 종료"""
				try:
						# tshark 프로세스 종료
						if hasattr(self, 'tshark_process') and self.tshark_process:
								try:
										self.tshark_process.terminate()
										self.tshark_process.wait(timeout=5)
										self.log_error("tshark 프로세스 종료됨")
								except subprocess.TimeoutExpired:
										self.tshark_process.kill()
										self.log_error("tshark 프로세스 강제 종료됨")
								except Exception as e:
										self.log_error(f"tshark 프로세스 종료 실패: {e}")
								finally:
										self.tshark_process = None

						# dumpcap 프로세스 종료 (제거됨)
						# ExtensionRecordingManager가 통화별 dumpcap을 관리하므로 전역 dumpcap 정리 불필요

						# 임시 캡처 파일 정리 (제거됨)
						# 통화별 녹음 시스템에서 임시 파일을 자체 관리

				except Exception as e:
						self.log_error(f"Wireshark 프로세스 종료 실패: {e}")

		def restart_packet_capture(self, new_ip=None):
				"""패킷 캡처 재시작 (Network IP 변경 시 사용)"""
				try:
						self.log_to_sip_console("패킷 캡처 재시작 시작...", "INFO")
						print("=== 패킷 캡처 재시작 ===")

						# 1. 기존 캡처 중지
						if hasattr(self, 'capture_thread') and self.capture_thread and self.capture_thread.is_alive():
								print("기존 캡처 스레드 종료 중...")
								self.log_to_sip_console("기존 패킷 캡처 종료 중...", "INFO")

								# capture 객체가 있으면 종료 요청
								if hasattr(self, 'capture') and self.capture:
										try:
												# capture 종료 플래그 설정 (나중에 capture_packets에서 확인)
												self.capture_stop_requested = True
												self.capture = None

												# tshark와 dumpcap 프로세스 종료
												self.stop_wireshark_processes()
										except Exception as e:
												print(f"캡처 객체 종료 중 오류: {e}")

								# 스레드 종료 대기 (최대 3초)
								try:
										self.capture_thread.join(timeout=3.0)
										if self.capture_thread.is_alive():
												print("캡처 스레드가 정상적으로 종료되지 않음")
												self.log_to_sip_console("기존 캡처 스레드 강제 종료", "WARNING")
										else:
												print("기존 캡처 스레드 정상 종료")
												self.log_to_sip_console("기존 캡처 스레드 정상 종료", "INFO")
								except Exception as e:
										print(f"스레드 종료 대기 중 오류: {e}")

						# 2. 잠시 대기 (리소스 정리 시간)
						import time
						time.sleep(0.5)

						# 3. 새로운 IP 설정 확인
						if new_ip:
								print(f"새 포트미러링 IP로 재시작: {new_ip}")
								self.log_to_sip_console(f"새 포트미러링 IP로 재시작: {new_ip}", "INFO")

						# 4. 새 캡처 시작
						if not self.selected_interface:
								self.log_error("선택된 네트워크 인터페이스가 없습니다")
								return False

						# capture_stop_requested 플래그 초기화
						self.capture_stop_requested = False

						# 새 캡처 스레드 시작
						self.capture_thread = threading.Thread(
								target=self.capture_packets,
								args=(self.selected_interface,),
								daemon=True
						)
						self.capture_thread.start()

						print("새 패킷 캡처 스레드 시작됨")
						self.log_to_sip_console("패킷 캡처 재시작 완료", "INFO")
						self.log_error("패킷 캡처 재시작 완료", additional_info={
								"interface": self.selected_interface,
								"new_ip": new_ip
						})

						return True

				except Exception as e:
						print(f"패킷 캡처 재시작 실패: {e}")
						self.log_error("패킷 캡처 재시작 실패", e)
						self.log_to_sip_console(f"패킷 캡처 재시작 실패: {e}", "ERROR")
						return False

		def capture_packets(self, interface):
				"""패킷 캡처 실행"""
				if not interface:
						self.log_error("유효하지 않은 인터페이스")
						return

				capture = None
				loop = None

				try:
						# 캡처 중지 플래그 초기화 (필요시)
						if not hasattr(self, 'capture_stop_requested'):
								self.capture_stop_requested = False

						# 이벤트 루프 설정
						loop = asyncio.new_event_loop()
						asyncio.set_event_loop(loop)

						# settings.ini에서 포트미러링 대상 IP 가져오기
						config = load_config()
						target_ip = config.get('Network', 'ip', fallback=None)

						# 포트미러링 환경을 위한 캡처 필터 설정 (단순화)
						if target_ip:
								# Wireshark와 동일한 단순 필터
								display_filter = f'(host {target_ip}) and (sip or udp)'
								self.safe_log(f"포트미러링 필터 적용: {display_filter}", "INFO")
								print(f"사용중인 필터: {display_filter}")
						else:
								# 모든 SIP 패킷 캡처 (테스트용)
								display_filter = 'sip'
								self.safe_log(f"SIP 전용 필터 적용: {display_filter}", "INFO")
								print(f"사용중인 필터: {display_filter}")

						# 개선된 필터링 및 디버깅 모드
						debug_mode = False  # 디버깅 모드 활성화 여부

						if debug_mode:
								print("🔍 디버깅 모드: 모든 패킷 캡처 시작")
								self.safe_log("디버깅 모드: 모든 패킷 캡처", "INFO")
								capture = pyshark.LiveCapture(interface=interface)  # 필터 없음
						else:
								# 개선된 필터: 더 넓은 범위로 SIP 패킷 캡처
								if target_ip:
										# IP 기반 필터를 더 관대하게 변경
										fallback_filter = f'host {target_ip} or sip or (udp and port 5060)'
										print(f"폴백 필터: {fallback_filter}")
								else:
										# SIP 및 RTP 패킷을 모두 캡처
										fallback_filter = 'sip or (udp and portrange 5060-5080) or (udp and portrange 10000-20000)'

								try:
										# 먼저 필터 없이 시도 (가장 안정적)
										print("필터 없이 모든 패킷 캡처 시도...")
										capture = pyshark.LiveCapture(interface=interface)
										self.safe_log("필터 없는 패킷 캡처로 시작", "INFO")
								except Exception as filter_error:
										print(f"LiveCapture 생성 실패: {filter_error}")
										self.safe_log(f"캡처 객체 생성 실패: {filter_error}", "ERROR")
										return

						# 전역 변수로 capture 객체 저장 (재시작 시 사용)
						self.capture = capture

						# 패킷 캡처 시작
						self.safe_log(f"패킷 캡처 시작 - 인터페이스: {interface}", "INFO")

						# tshark 프로세스 실행 테스트 및 강제 실행
						tshark_path = os.path.join(get_wireshark_path(), "tshark.exe")
						self.safe_log(f"tshark 경로: {tshark_path}", "INFO")

						# tshark 직접 실행 테스트
						try:
								test_cmd = [tshark_path, "-D"]
								result = subprocess.run(test_cmd, capture_output=True, text=True, timeout=10, encoding='utf-8', errors='replace')
								if result.returncode == 0:
										self.safe_log("tshark 실행 가능 확인", "INFO")
								else:
										error_msg = result.stderr
										self.safe_log(f"tshark 실행 실패: {error_msg}", "ERROR")
										return
						except Exception as e:
								error_str = str(e)
								self.safe_log(f"tshark 테스트 실패: {error_str}", "ERROR")
								return

						# pyshark 캡처 프로세스 강제 시작
						try:
								self.safe_log("패킷 캡처 시작 중...", "INFO")

								# 실제로 dumpcap/tshark를 시작하려면 패킷을 읽어야 함
								packet_iter = iter(capture.sniff_continuously())

								# 첫 패킷 시도 (5초 타임아웃)
								import time
								import threading

								first_packet = None

								def get_first_packet():
										nonlocal first_packet
										try:
												first_packet = next(packet_iter)
												self.safe_log("✅ 첫 패킷 획득 성공 - tshark/dumpcap 실행됨", "INFO")
										except Exception as e:
												self.safe_log(f"첫 패킷 획득 실패: {e}", "ERROR")

								# 별도 스레드에서 첫 패킷 시도
								packet_thread = threading.Thread(target=get_first_packet, daemon=True)
								packet_thread.start()
								packet_thread.join(timeout=5)

								if packet_thread.is_alive():
										self.safe_log("⚠️ SIP 패킷 캡처 타임아웃 - 더 넓은 필터로 재시도", "WARNING")
										# SIP 필터를 제거하고 모든 UDP 패킷 캡처
										capture = pyshark.LiveCapture(interface=interface, bpf_filter="udp")
										packet_iter = iter(capture.sniff_continuously())

										packet_thread = threading.Thread(target=get_first_packet, daemon=True)
										packet_thread.start()
										packet_thread.join(timeout=3)

										if packet_thread.is_alive():
												self.safe_log("❌ 패킷 캡처 완전 실패 - tshark/dumpcap 시작 안됨", "ERROR")
												return
										else:
												self.safe_log("✅ UDP 패킷 캡처 시작됨 - tshark/dumpcap 실행됨", "INFO")

								packet_count = 1 if first_packet else 0

						except Exception as e:
								self.safe_log(f"패킷 캡처 시작 실패: {e}", "ERROR")
								return

						# 계속해서 패킷 처리
						for packet in packet_iter:
								try:
										# 캡처 중지 요청 확인
										if hasattr(self, 'capture_stop_requested') and self.capture_stop_requested:
												print("패킷 캡처 중지 요청 감지됨")
												self.safe_log("패킷 캡처 중지 요청으로 종료", "INFO")
												break

										packet_count += 1
										# 패킷 개수 로깅 제거 (너무 많음)

										# 처음 5개 패킷만 기본 정보 로깅
										if packet_count <= 5:
												try:
														src_ip = getattr(packet.ip, 'src', 'unknown') if hasattr(packet, 'ip') else 'no_ip'
														dst_ip = getattr(packet.ip, 'dst', 'unknown') if hasattr(packet, 'ip') else 'no_ip'
														protocol = packet.highest_layer
														print(f"패킷 #{packet_count}: {src_ip} → {dst_ip}, 프로토콜: {protocol}")
												except Exception as e:
														print(f"패킷 정보 추출 오류: {e}")

										# 메모리 사용량 모니터링
										process = psutil.Process()
										memory_percent = process.memory_percent()
										if memory_percent > 80:
												self.safe_log(f"높은 메모리 사용량: {memory_percent}%", "WARNING")

										# SIP 패킷 처리 - 메인 스레드로 Signal 발송
										if hasattr(packet, 'sip'):
												print(f"★★★ SIP 패킷 발견! (#{packet_count}) ★★★")
												self.safe_log(f"★ SIP 패킷 감지됨! (#{packet_count})", "SIP")
												# 백그라운드 스레드에서 메인 스레드로 SIP 패킷 분석 요청
												self.sip_packet_signal.emit(packet)
										elif hasattr(packet, 'udp'):
												if self.is_rtp_packet(packet):
														self.log_rtp_with_counter(packet)
														self.handle_rtp_packet(packet)

								except Exception as packet_error:
										self.safe_log(f"패킷 처리 중 오류: {packet_error}", "ERROR")
										# 중지 요청이 있으면 오류 상황에서도 종료
										if hasattr(self, 'capture_stop_requested') and self.capture_stop_requested:
												break
										continue

				except KeyboardInterrupt:
						self.safe_log("사용자에 의한 캡처 중단", "INFO")
				except Exception as capture_error:
						self.safe_log(f"캡처 프로세스 오류: {capture_error}", "ERROR")

				finally:
						try:
								if capture:
										if loop and not loop.is_closed():
												loop.run_until_complete(capture.close_async())
										else:
												capture.close()
								else:
										self.safe_log("캡처 프로세스가 초기화되지 않았습니다", "ERROR")
						except Exception as close_error:
								self.safe_log(f"캡처 종료 실패: {close_error}", "ERROR")

						try:
								if loop and not loop.is_closed():
										loop.close()
								else:
										self.safe_log("이벤트 루프가 초기화되지 않았습니다", "ERROR")
						except Exception as loop_error:
								self.safe_log(f"이벤트 루프 종료 실패: {loop_error}", "ERROR")

						# self.cleanup_existing_dumpcap()  # 캡처 종료 후 프로세스 정리

		def _create_header(self):
				header = QWidget()
				header_layout = QHBoxLayout(header)
				header_layout.setContentsMargins(10, 5, 10, 5)
				phone_section = QWidget()
				phone_layout = QHBoxLayout(phone_section)
				phone_layout.setAlignment(Qt.AlignLeft)
				phone_layout.setContentsMargins(0, 0, 0, 0)
				phone_text = QLabel("대표번호 | ")
				self.phone_number = QLabel()
				config = configparser.ConfigParser()
				config.read('settings.ini', encoding='utf-8')
				self.phone_number.setText(config.get('Extension', 'rep_number', fallback=''))
				phone_layout.addWidget(phone_text)
				phone_layout.addWidget(self.phone_number)
				license_section = QWidget()
				license_layout = QHBoxLayout(license_section)
				license_layout.setAlignment(Qt.AlignRight)
				license_layout.setContentsMargins(0, 0, 0, 0)
				license_text = QLabel("라이선스 NO. | ")
				self.license_number = QLabel()
				self.license_number.setText(config.get('Extension', 'license_no', fallback=''))
				license_layout.addWidget(license_text)
				license_layout.addWidget(self.license_number)

				header_layout.addWidget(phone_section, 1)
				header_layout.addWidget(license_section, 1)
				return header

		def _create_sidebar(self):
				sidebar = QWidget()
				sidebar.setObjectName("sidebar")
				sidebar.setFixedWidth(200)
				layout = QVBoxLayout(sidebar)
				layout.setContentsMargins(0, 0, 0, 0)
				layout.setSpacing(0)
				logo_container = QWidget()
				logo_container_layout = QVBoxLayout(logo_container)
				logo_container_layout.setContentsMargins(0, 30, 0, 30)
				logo_container_layout.setSpacing(0)
				logo_label = QLabel()
				logo_label.setAlignment(Qt.AlignCenter)
				logo_pixmap = QPixmap(resource_path("images/recapvoice_squere_w.png"))
				if not logo_pixmap.isNull():
						aspect_ratio = logo_pixmap.height() / logo_pixmap.width()
						target_width = 120
						target_height = int(target_width * aspect_ratio)
						scaled_logo = logo_pixmap.scaled(
								target_width,
								target_height,
								Qt.KeepAspectRatio,
								Qt.SmoothTransformation
						)
						logo_label.setPixmap(scaled_logo)
				logo_container_layout.addWidget(logo_label)
				layout.addWidget(logo_container)

				# SIP 내선번호 표시 박스 추가
				print("=== Extension box를 사이드바에 추가 중 ===")
				extension_box = self._create_extension_box()
				layout.addWidget(extension_box)
				print(f"Extension box가 사이드바에 추가됨: {extension_box}")
				print(f"사이드바 레이아웃 내 위젯 개수: {layout.count()}")

				menu_container = QWidget()
				menu_layout = QVBoxLayout(menu_container)
				menu_layout.setContentsMargins(0, 0, 0, 0)
				menu_layout.setSpacing(5)
				menu_layout.addStretch()
				layout.addWidget(menu_container)
				return sidebar

		def _create_menu_button(self, text, icon_path):
				btn = QPushButton()
				btn.setObjectName("menu_button")
				btn.setFixedHeight(50)
				btn.setCursor(Qt.PointingHandCursor)
				layout = QHBoxLayout(btn)
				layout.setContentsMargins(15, 0, 15, 0)
				layout.setSpacing(0)
				icon_label = QLabel()
				icon_label.setFixedSize(24, 24)
				icon_pixmap = QPixmap(icon_path)
				if not icon_pixmap.isNull():
						scaled_icon = icon_pixmap.scaled(16, 16, Qt.KeepAspectRatio, Qt.SmoothTransformation)
						icon_label.setPixmap(scaled_icon)
				layout.addWidget(icon_label)
				text_label = QLabel(text)
				text_label.setStyleSheet("color: #2d2d2d;")
				layout.addWidget(text_label)
				layout.addStretch()
				return btn

		def _create_extension_box(self):
				"""SIP 내선번호 표시 박스 생성"""
				# 메인 컨테이너 (둥근 박스)
				extension_container = QWidget()
				extension_container.setObjectName("extension_container")
				extension_container.setFixedSize(200, 700)
				extension_container.setStyleSheet("""
					QWidget#extension_container {
						background-color: #2c3e50;
						border: 1px solid #34495e;
						border-radius: 5px;
						margin: 10px;
					}
				""")

				main_layout = QVBoxLayout(extension_container)
				main_layout.setContentsMargins(10, 10, 10, 10)
				main_layout.setSpacing(5)

				# 헤더 영역 (타이틀만)
				title_label = QLabel("내선번호")
				title_label.setAlignment(Qt.AlignCenter)
				title_label.setFixedHeight(28)
				title_label.setObjectName("extension_title")
				title_label.setStyleSheet("""
					QLabel#extension_title {
						background-color: transparent;
						border: none;
						color: white;
						font-size: 12px;
						font-weight: bold;
						padding-top: 5px;
					}
				""")
				main_layout.addWidget(title_label)

				# 스크롤 영역
				scroll_area = QScrollArea()
				scroll_area.setWidgetResizable(True)
				scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
				scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
				scroll_area.setStyleSheet("""
					QScrollArea {
						border: none;
						background-color: #2c3e50;
					}
					QScrollBar:vertical {
						background-color: rgba(255, 255, 255, 0.1);
						width: 8px;
						border-radius: 4px;
					}
					QScrollBar::handle:vertical {
						background-color: rgba(255, 255, 255, 0.3);
						border-radius: 4px;
						min-height: 20px;
					}
					QScrollBar::handle:vertical:hover {
						background-color: rgba(255, 255, 255, 0.5);
					}
				""")

				# 내선번호 리스트 위젯
				self.extension_list_widget = QWidget()
				self.extension_list_widget.setStyleSheet("""
					QWidget {
						background-color: #364F86;
						border: none;
					}
				""")
				self.extension_list_layout = QVBoxLayout(self.extension_list_widget)
				self.extension_list_layout.setContentsMargins(5, 5, 5, 5)
				self.extension_list_layout.setSpacing(3)
				self.extension_list_layout.setAlignment(Qt.AlignTop)

				scroll_area.setWidget(self.extension_list_widget)
				main_layout.addWidget(scroll_area)

				# 위젯들 강제 표시 및 업데이트
				extension_container.show()
				scroll_area.show()
				self.extension_list_widget.show()

				# 강제 업데이트
				extension_container.update()
				scroll_area.update()
				self.extension_list_widget.update()

				# 최소 크기 설정 (700px 컨테이너에 맞게)
				extension_container.setMinimumSize(200, 700)
				scroll_area.setMinimumSize(180, 650)  # 헤더와 여백 제외한 크기

				print(f"Extension box 위젯 생성 완료")
				print(f"Container 표시 상태: {extension_container.isVisible()}")
				print(f"Container 크기: {extension_container.size()}")
				print(f"Scroll area 표시 상태: {scroll_area.isVisible()}")
				print(f"Scroll area 크기: {scroll_area.size()}")
				print(f"List widget 표시 상태: {self.extension_list_widget.isVisible()}")
				print(f"List widget 크기: {self.extension_list_widget.size()}")

				return extension_container

		# 토글 기능 제거됨 - 고정된 상태로 유지

		def toggle_led_color(self, led_indicator):
				"""LED 색상을 노란색과 녹색 사이에서 토글"""
				try:
						# 메인 스레드에서 실행되는지 확인
						from PySide6.QtCore import QThread
						if QThread.currentThread() != self.thread():
								# 메인 스레드가 아닌 경우 QTimer.singleShot으로 메인 스레드에 전달
								self.safe_log("내선번호 LED 깜박임 - 메인 스레드로 전달", "INFO")
								# QTimer를 백그라운드 스레드에서 사용하면 안됨 - 무시
								return

						# 실제 LED 토글 로직은 별도 메서드로 분리
						self.toggle_led_color_safe(led_indicator)
				except Exception as e:
						print(f"LED 토글 중 오류: {e}")

		def toggle_led_color_safe(self, led_indicator):
				"""메인 스레드에서 안전하게 LED 색상을 토글"""
				try:
						# LED가 표시되지 않거나 삭제된 경우 타이머 정지
						if not led_indicator.isVisible() or led_indicator.parent() is None:
								if hasattr(led_indicator, 'led_timer') and led_indicator.led_timer:
										led_indicator.led_timer.stop()
										led_indicator.led_timer.deleteLater()
										led_indicator.led_timer = None
								return

						if hasattr(led_indicator, 'is_yellow'):
								if led_indicator.is_yellow:
										# 녹색으로 변경
										led_indicator.setStyleSheet("""
											QLabel {
												background-color: transparent;
												border: none;
												color: #32CD32;
												font-size: 12px;
												font-weight: bold;
											}
										""")
										led_indicator.is_yellow = False
								else:
										# 노란색으로 변경
										led_indicator.setStyleSheet("""
											QLabel {
												background-color: transparent;
												border: none;
												color: #FFD700;
												font-size: 12px;
												font-weight: bold;
											}
										""")
										led_indicator.is_yellow = True
				except (RuntimeError, AttributeError):
						# C++ 객체가 삭제된 경우 타이머 정리
						if hasattr(led_indicator, 'led_timer') and led_indicator.led_timer:
								try:
										led_indicator.led_timer.stop()
										led_indicator.led_timer.deleteLater()
										led_indicator.led_timer = None
								except:
										pass

		def cleanup_led_timers(self, widget):
				"""위젯 내의 LED 타이머들을 정리"""
				try:
						# 위젯의 모든 자식 위젯을 확인
						for child in widget.findChildren(QLabel):
								if hasattr(child, 'led_timer') and child.led_timer is not None:
										try:
												child.led_timer.stop()
												child.led_timer.deleteLater()
												child.led_timer = None
										except (RuntimeError, AttributeError):
												pass
								if hasattr(child, 'is_yellow'):
										try:
												delattr(child, 'is_yellow')
										except AttributeError:
												pass
				except Exception as e:
						print(f"LED 타이머 정리 중 오류: {e}")
						pass

		def start_led_timer_in_main_thread(self, led_indicator):
				"""메인 스레드에서 LED 타이머 시작"""
				try:
						# 메인 스레드에서 실행되는지 확인
						from PySide6.QtCore import QThread
						if QThread.currentThread() != self.thread():
								# 메인 스레드가 아닌 경우 시그널을 통해 메인 스레드로 전달
								self.safe_log("내선번호 LED 타이머 시작 - 메인 스레드로 전달", "INFO")
								self.start_led_timer_signal.emit(led_indicator)
								return

						# 기존 타이머가 있다면 정리
						if hasattr(led_indicator, 'led_timer') and led_indicator.led_timer is not None:
								led_indicator.led_timer.stop()
								led_indicator.led_timer.deleteLater()
								led_indicator.led_timer = None

						led_timer = QTimer(self)  # 메인 윈도우를 부모로 설정하여 메인 스레드에서 실행 보장
						led_timer.setInterval(750)
						led_timer.timeout.connect(lambda: self.toggle_led_color(led_indicator))
						led_timer.start()

						# LED 타이머를 LED 인디케이터에 연결하여 나중에 정리할 수 있도록
						led_indicator.led_timer = led_timer
				except Exception as e:
						print(f"LED 타이머 생성 중 오류: {e}")

		def add_extension(self, extension):
				"""새 내선번호 추가"""
				if extension and extension not in self.sip_extensions:
					self.sip_extensions.add(extension)
					self.update_extension_display()


		def refresh_extension_list_with_register(self, extension):
				"""SIP REGISTER로 감지된 내선번호로 목록을 갱신 (Signal을 통해 메인 스레드에서 처리)"""
				if extension:
					print(f"SIP REGISTER 감지: 내선번호 {extension} 등록 요청")
					self.log_to_sip_console(f"SIP REGISTER 감지: 내선번호 {extension} 등록 요청", "SIP")
					print(f"Signal 발송 준비: extension_update_signal.emit({extension})")
					# 메인 스레드에서 처리하도록 Signal 발신
					self.extension_update_signal.emit(extension)
					print(f"Signal 발송 완료: {extension}")
				else:
					print("REGISTER에서 내선번호 추출 실패")
					self.log_to_sip_console("REGISTER에서 내선번호 추출 실패", "WARNING")

		def update_extension_in_main_thread(self, extension):
				"""메인 스레드에서 내선번호 업데이트 처리"""
				print(f"메인 스레드에서 내선번호 처리 시작: {extension}")
				self.log_to_sip_console(f"메인 스레드에서 내선번호 처리: {extension}", "SIP")

				# 현재 내선번호 목록 상태 출력 (간소화)
				print(f"현재 내선번호 목록: {self.sip_extensions}")

				# 실제 등록된 내선번호 추가
				if extension and extension not in self.sip_extensions:
						self.sip_extensions.add(extension)
						print(f"내선번호 {extension}를 목록에 추가")
						self.log_to_sip_console(f"내선번호 {extension} 추가됨", "SIP")

						# UI 업데이트
						print("UI 업데이트 시작...")
						self.update_extension_display()
						print("UI 업데이트 완료")
						self.log_to_sip_console(f"내선번호 {extension} UI 업데이트 완료", "SIP")
				else:
						if not extension:
								print("빈 내선번호")
								self.log_to_sip_console("빈 내선번호", "WARNING")
						else:
								print(f"내선번호 {extension}는 이미 등록됨")
								self.log_to_sip_console(f"내선번호 {extension}는 이미 등록됨", "INFO")

		def update_extension_display(self):
				"""내선번호 표시 업데이트 - 왼쪽 사이드바 박스"""
				print(f"내선번호 UI 업데이트: {len(self.sip_extensions)}개")
				self.log_to_sip_console(f"내선번호 UI 업데이트: {len(self.sip_extensions)}개", "SIP")

				# extension_list_layout 존재 확인
				if not hasattr(self, 'extension_list_layout'):
						print("extension_list_layout이 없습니다!")
						self.log_to_sip_console("extension_list_layout이 없습니다!", "ERROR")
						return

				# 기존 위젯들 제거 (타이머도 함께 정리)
				while self.extension_list_layout.count():
					child = self.extension_list_layout.takeAt(0)
					if child.widget():
						widget = child.widget()
						# LED 타이머 정리
						self.cleanup_led_timers(widget)
						widget.deleteLater()

				# 내선번호들을 정렬하여 세로로 표시
				sorted_extensions = sorted(self.sip_extensions)

				if not sorted_extensions:
					# 등록된 내선번호가 없을 때 안내 메시지 표시
					no_ext_label = QLabel("SIP Connection Waiting...")
					no_ext_label.setStyleSheet("""
						QLabel {
							color: rgba(255, 255, 255, 0.6);
							font-size: 12px;
							padding: 5px 8px;
							text-align: center;
						}
					""")
					no_ext_label.setAlignment(Qt.AlignCenter)
					self.extension_list_layout.addWidget(no_ext_label)
				else:
					print(f"내선번호 위젯 생성: {sorted_extensions}")
					for extension in sorted_extensions:
						# 각 내선번호별 컨테이너 위젯 생성
						ext_container = QWidget()
						ext_layout = QHBoxLayout(ext_container)
						ext_layout.setContentsMargins(0, 0, 0, 0)
						ext_layout.setSpacing(5)

						# 내선번호 래이블과 LED를 포함한 컨테이너
						extension_container = QWidget()
						extension_container.setStyleSheet("""
							QWidget {
								background-color: #2c3e50;
								border: 1px solid #34495e;
								border-radius: 5px;
								margin: 2px;
							}
						""")

						# 내선번호 컸테이너 내부 레이아웃
						extension_inner_layout = QHBoxLayout(extension_container)
						extension_inner_layout.setContentsMargins(8, 5, 8, 5)
						extension_inner_layout.setSpacing(5)

						# 내선번호 레이블
						extension_label = QLabel(extension)
						extension_label.setStyleSheet("""
							QLabel {
								color: #ffffff;
								font-size: 13px;
								font-weight: bold;
								background-color: transparent;
								border: none;
							}
						""")

						# 원형 LED 인디케이터 (QLabel로 변경)
						led_indicator = QLabel("●")  # 원형 LED 이모지
						led_indicator.setObjectName(f"led_indicator_{extension}")
						led_indicator.setFixedSize(12, 12)  # 작은 원형 LED
						led_indicator.setAlignment(Qt.AlignCenter)
						led_indicator.setStyleSheet("""
							QLabel {
								background-color: transparent;
								border: none;
								color: #FFD700;
								font-size: 12px;
								font-weight: bold;
							}
						""")

						# LED 깜박임 애니메이션 효과 (Signal 사용하여 메인 스레드에서 실행)
						self.start_led_timer_signal.emit(led_indicator)

						# LED 상태 초기화
						led_indicator.is_yellow = True  # 노란색 상태 추적

						# 내선번호 컸테이너 내부에 레이블과 LED 배치
						extension_inner_layout.addWidget(extension_label)
						extension_inner_layout.addStretch()  # 공간 채우기
						extension_inner_layout.addWidget(led_indicator)

						# 메인 레이아웃에 전체 컸테이너 추가
						ext_layout.addWidget(extension_container)

						self.extension_list_layout.addWidget(ext_container)

						# 위젯 표시
						ext_container.show()
						extension_container.show()
						extension_label.show()
						led_indicator.show()

				print(f"내선번호 UI 업데이트 완료: {len(sorted_extensions)}개")
				self.log_to_sip_console(f"내선번호 UI 업데이트 완료: {len(sorted_extensions)}개", "SIP")

		def get_public_ip(self):
				try:
						response = requests.get('https://api64.ipify.org/?format=json')
						ip = response.json().get('ip')
						return ip
				except requests.RequestException as e:
						print(f"An error occurred: {e}")
						return None

		def _create_status_section(self):
				layout = QVBoxLayout()
				top_layout = QHBoxLayout()
				top_layout.setSpacing(15)
				network_group = self._create_info_group("네트워크 IP", self.get_public_ip())
				top_layout.addWidget(network_group, 25)
				config = configparser.ConfigParser()
				config.read('settings.ini', encoding='utf-8')
				port_mirror_ip = config.get('Network', 'ip', fallback='127.0.0.1')
				port_group = self._create_info_group("포트미러링 IP", port_mirror_ip)
				top_layout.addWidget(port_group, 25)
				client_start = self._create_client_start_group()
				top_layout.addWidget(client_start, 25)
				record_start = self._create_toggle_group("환경설정 / 관리사이트")
				top_layout.addWidget(record_start, 25)
				layout.addLayout(top_layout)
				bottom_layout = QHBoxLayout()
				bottom_layout.setSpacing(15)
				config.read('settings.ini', encoding='utf-8')
				storage_path = config.get('Recording', 'save_path', fallback='C:\\')
				drive_letter = storage_path.split(':')[0]
				disk_group = QGroupBox('디스크 정보')
				disk_layout = QHBoxLayout()
				self.disk_label = QLabel(f'녹취드라이버 ( {drive_letter} : ) 사용률:')
				self.progress_bar = QProgressBar()
				self.progress_bar.setFixedHeight(18)
				self.progress_bar.setStyleSheet("""
						QProgressBar {
								text-align: center;
								border: 1px solid #ccc;
								border-radius: 2px;
								background-color: #f0f0f0;
						}
						QProgressBar::chunk {
								background-color: #18508F;
						}
				""")
				self.progress_bar.setMinimum(0)
				self.progress_bar.setMaximum(100)
				self.disk_usage_label = QLabel()
				disk_layout.addWidget(self.disk_label)
				disk_layout.addWidget(self.progress_bar)
				disk_layout.addWidget(self.disk_usage_label)
				disk_group.setLayout(disk_layout)
				bottom_layout.addWidget(disk_group, 80)
				led_group = QGroupBox('회선 상태')
				led_layout = QHBoxLayout()
				led_layout.addWidget(self._create_led_with_text('회선 연결 ', 'yellow'))
				led_layout.addWidget(self._create_led_with_text('대 기 중 ', 'blue'))
				led_layout.addWidget(self._create_led_with_text('녹 취 중 ', 'green'))
				led_group.setLayout(led_layout)
				bottom_layout.addWidget(led_group, 20)
				layout.addLayout(bottom_layout)
				self.timer = QTimer(self)
				self.timer.timeout.connect(self.update_disk_usage)
				self.timer.start(600000)
				self.update_disk_usage()
				return layout

		def _create_info_group(self, title, value):
				group = QGroupBox(title)
				layout = QVBoxLayout(group)
				layout.setContentsMargins(15, 20, 15, 15)
				if title == "네트워크 IP":
						self.ip_value = QLabel(value)
						value_label = self.ip_value
				elif title == "포트미러링 IP":
						self.mirror_ip_value = QLabel(value)
						value_label = self.mirror_ip_value
				else:
						value_label = QLabel(value)
				value_label.setObjectName("statusLabel")
				value_label.setAlignment(Qt.AlignCenter)
				value_label.setStyleSheet("""
						color: #3e5063;
						font-size: 14px;
						font-weight: bold;
				""")
				layout.addWidget(value_label)
				return group

		def _create_toggle_group(self, title):
				group = QGroupBox(title)
				layout = QHBoxLayout(group)
				layout.setContentsMargins(15, 15, 15, 15)
				layout.setSpacing(2)
				button_container = QWidget()
				button_layout = QHBoxLayout(button_container)
				button_layout.setContentsMargins(0, 0, 0, 0)
				button_layout.setSpacing(2)
				settings_btn = QPushButton("환경설정")
				settings_btn.setObjectName("toggleOn")
				settings_btn.setCursor(Qt.PointingHandCursor)
				settings_btn.clicked.connect(self.show_settings)
				admin_btn = QPushButton("관리사이트이동")
				admin_btn.setObjectName("toggleOff")
				admin_btn.setCursor(Qt.PointingHandCursor)
				admin_btn.clicked.connect(self.open_admin_site)
				button_layout.addWidget(settings_btn, 1)
				button_layout.addWidget(admin_btn, 1)
				layout.addWidget(button_container)
				return group

		def _create_line_list(self):
				group = QGroupBox("전화연결 상태")
				group.setObjectName("line_list")
				group.setMaximumHeight(400)
				group.setStyleSheet("""
						QGroupBox {
								background-color: #2d2d2d !important;
								border: 1px solid #3a3a3a;
								border-radius: 4px;
								margin-top: 10px;
								padding: 10px;
								color: white;
								font-weight: bold;
						}
						QScrollArea {
								background-color: #2d2d2d !important;
						}
						QWidget#scrollContents {
								background-color: #2d2d2d !important;
						}
				""")
				layout = QVBoxLayout(group)
				layout.setContentsMargins(15, 15, 15, 15)
				layout.setSpacing(0)
				scroll = QScrollArea()
				scroll.setWidgetResizable(True)
				scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
				scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
				self.calls_container = QWidget()
				self.calls_container.setObjectName("scrollContents")
				self.calls_layout = FlowLayout(self.calls_container, margin=0, spacing=20)
				scroll.setWidget(self.calls_container)
				layout.addWidget(scroll)
				self.active_extensions = {}
				return group

		def _create_call_block(self, internal_number, received_number, duration, status):
				block = QWidget()
				block.setFixedSize(200, 150)
				block.setObjectName("callBlock")
				layout = QVBoxLayout(block)
				layout.setContentsMargins(15, 15, 15, 15)
				layout.setSpacing(0)
				layout.setAlignment(Qt.AlignTop)
				top_container = QWidget()
				top_layout = QVBoxLayout(top_container)
				top_layout.setContentsMargins(0, 0, 0, 0)
				top_layout.setSpacing(4)
				top_layout.setAlignment(Qt.AlignTop)
				led_container = QWidget()
				led_layout = QHBoxLayout(led_container)
				led_layout.setContentsMargins(0, 0, 0, 0)
				led_layout.setSpacing(4)
				led_layout.setAlignment(Qt.AlignRight)
				if status != "대기중" and received_number:
						led_states = ["회선 연결", "녹취중"]
				else:
						led_states = ["회선 연결", "대기중"]
				for state in led_states:
						led = self._create_led("", self._get_led_color(state))
						led_layout.addWidget(led)
				top_layout.addWidget(led_container)
				info_layout = QGridLayout()
				info_layout.setSpacing(4)
				info_layout.setContentsMargins(0, 0, 0, 0)
				# 내선번호 레이블은 "extensionLabel", 통화 시간 레이블은 "durationLabel"
				if status != "대기중" and received_number:
						labels = [
								("수신:", received_number),
								("상태:", status),
								("시간:", duration)
						]
				else:
						labels = [
								("상태:", status)
						]
				for idx, (title, value) in enumerate(labels):
						title_label = QLabel(title)
						title_label.setObjectName("blockTitle")
						title_label.setStyleSheet("color: #888888; font-size: 12px;")
						value_label = QLabel(value)
						# objectName 지정
						if title.strip() == "시간:":
								value_label.setObjectName("durationLabel")
						else:
								value_label.setObjectName("blockValue")
						value_label.setStyleSheet("color: white; font-size: 12px; font-weight: bold; margin-left: 4px;")
						info_layout.addWidget(title_label, idx, 0)
						info_layout.addWidget(value_label, idx, 1)
				top_layout.addLayout(info_layout)
				layout.addWidget(top_container)
				base_style = """
						QWidget#callBlock {
								border-radius: 4px;
								background-color: #2A2A2A;
								border: 1px solid #383838;
						}
						QLabel#blockTitle {
								color: #888888;
								font-size: 12px;
								font-weight: normal;
						}
						QLabel#blockValue, QLabel#extensionLabel {
								font-size: 12px;
								font-weight: bold;
								margin-left: 4px;
						}
				"""
				if status == "대기중":
						block.setStyleSheet(base_style + """
								QWidget#callBlock {
										background-color: #2A2A2A;
										border: 1px solid #383838;
								}
								QLabel#blockValue, QLabel#extensionLabel {
										color: #888888;
								}
						""")
						effect = QGraphicsOpacityEffect()
						effect.setOpacity(0.6)
						block.setGraphicsEffect(effect)
				else:
						block.setStyleSheet(base_style + """
								QWidget#callBlock {
										background-color: #2A2A2A;
										border: 2px solid #18508F;
								}
								QLabel#blockValue, QLabel#extensionLabel {
										color: #FFFFFF;
								}
						""")
						shadow = QGraphicsDropShadowEffect()
						shadow.setBlurRadius(10)
						shadow.setColor(QColor("#18508F"))
						shadow.setOffset(0, 0)
						block.setGraphicsEffect(shadow)
				return block

		def _get_led_color(self, state):
				colors = {
						"회선 연결": "yellow",
						"대기중": "blue",
						"녹취중": "green",
				}
				return colors.get(state, "yellow")

		def _create_log_list(self):
				group = QGroupBox("LOG LIST")
				group.setMinimumHeight(200)
				layout = QVBoxLayout(group)
				layout.setContentsMargins(15, 15, 15, 15)
				table = QTableWidget()
				table.setObjectName("log_list_table")
				table.setColumnCount(7)
				table.setHorizontalHeaderLabels([
						'시간', '통화 방향', '발신번호', '수신번호', '상태', '결과', 'Call-ID'
				])
				table.setStyleSheet("""
						QTableWidget {
								background-color: #2D2A2A;
								color: white;
								gridline-color: #444444;
						}
						QHeaderView::section {
								background-color: #1E1E1E;
								color: white;
								padding: 5px;
								border: 1px solid #444444;
						}
						QTableWidget::item {
								border: 1px solid #444444;
						}
						QTableWidget::item:selected {
								background-color: #4A90E2;
								color: white;
						}
				""")
				table.setColumnWidth(0, 150)
				table.setColumnWidth(1, 80)
				table.setColumnWidth(2, 120)
				table.setColumnWidth(3, 120)
				table.setColumnWidth(4, 80)
				table.setColumnWidth(5, 80)
				table.setColumnWidth(6, 400)
				table.setSelectionBehavior(QTableWidget.SelectRows)
				table.setSelectionMode(QTableWidget.SingleSelection)
				table.setSortingEnabled(True)
				table.horizontalHeader().setStretchLastSection(True)
				layout.addWidget(table)
				return group

		def _create_sip_console_log(self):
				"""SIP 콘솔 로그 레이어 생성"""
				group = QGroupBox("SIP CONSOLE LOG")
				group.setMinimumHeight(200)  # 최소 높이만 설정하여 비율 조정 가능
				layout = QVBoxLayout(group)
				layout.setContentsMargins(15, 15, 15, 15)

				# 텍스트 에디터 (읽기 전용)
				console_text = QTextEdit()
				console_text.setObjectName("sip_console_text")
				console_text.setReadOnly(True)
				console_text.setStyleSheet("""
					QTextEdit {
						background-color: #1E1E1E;
						color: #00FF00;
						font-family: 'Consolas', 'Courier New', monospace;
						font-size: 11px;
						border: 1px solid #444444;
						padding: 5px;
					}
				""")

				# 툴바 추가
				toolbar_layout = QHBoxLayout()

				# 클리어 버튼
				clear_btn = QPushButton("Clear")
				clear_btn.setFixedSize(60, 25)
				clear_btn.setStyleSheet("""
					QPushButton {
						background-color: #444444;
						color: white;
						border: 1px solid #666666;
						border-radius: 3px;
						font-size: 9px;
					}
					QPushButton:hover {
						background-color: #555555;
					}
					QPushButton:pressed {
						background-color: #333333;
					}
				""")
				clear_btn.clicked.connect(lambda: console_text.clear())

				# 자동 스크롤 체크박스
				auto_scroll_cb = QCheckBox("Auto Scroll")
				auto_scroll_cb.setChecked(True)
				auto_scroll_cb.setObjectName("auto_scroll_checkbox")
				auto_scroll_cb.setStyleSheet("""
					QCheckBox {
						color: white;
						font-size: 9px;
					}
					QCheckBox::indicator {
						width: 12px;
						height: 12px;
					}
					QCheckBox::indicator:unchecked {
						background-color: #2D2A2A;
						border: 1px solid #666666;
					}
					QCheckBox::indicator:checked {
						background-color: #4A90E2;
						border: 1px solid #4A90E2;
					}
				""")

				toolbar_layout.addWidget(clear_btn)
				toolbar_layout.addWidget(auto_scroll_cb)
				toolbar_layout.addStretch()

				layout.addLayout(toolbar_layout)
				layout.addWidget(console_text)

				# 콘솔 텍스트 위젯을 인스턴스 변수로 저장
				self.sip_console_text = console_text
				self.auto_scroll_checkbox = auto_scroll_cb

				return group

		def log_to_sip_console(self, message, level="INFO"):
				"""SIP 콘솔에 로그 메시지 추가"""
				try:
						if not hasattr(self, 'sip_console_text') or self.sip_console_text is None:
								return

						# 타임스탬프 추가
						timestamp = datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]

						# 레벨에 따른 색상 설정
						color_map = {
								"INFO": "#00FF00",    # 녹색
								"DEBUG": "#00FFFF",   # 시안색
								"WARNING": "#FFFF00", # 노란색
								"ERROR": "#FF0000",   # 빨간색
								"SIP": "#FF00FF"      # 마젠타색
						}
						color = color_map.get(level, "#00FF00")

						# HTML 형식으로 메시지 포맷
						formatted_message = f'<span style="color: {color};">[{timestamp}] [{level}] {message}</span>'

						# 메인 스레드에서 실행되도록 보장
						QMetaObject.invokeMethod(
								self, "_append_to_console",
								Qt.QueuedConnection,
								Q_ARG(str, formatted_message)
						)
				except Exception as e:
						print(f"SIP 콘솔 로그 오류: {e}")

		@Slot(str)
		def _append_to_console(self, message):
				"""콘솔에 메시지 추가 (메인 스레드에서 실행)"""
				try:
						if not hasattr(self, 'sip_console_text') or self.sip_console_text is None:
								return

						# 메시지 추가
						self.sip_console_text.append(message)

						# 자동 스크롤 체크
						if hasattr(self, 'auto_scroll_checkbox') and self.auto_scroll_checkbox.isChecked():
								scrollbar = self.sip_console_text.verticalScrollBar()
								scrollbar.setValue(scrollbar.maximum())

						# 최대 라인 수 제한 (성능을 위해)
						max_lines = 1000
						document = self.sip_console_text.document()
						if document.blockCount() > max_lines:
								cursor = QTextCursor(document)
								cursor.movePosition(QTextCursor.Start)
								cursor.movePosition(QTextCursor.Down, QTextCursor.KeepAnchor, 100)
								cursor.removeSelectedText()
				except Exception as e:
						print(f"콘솔 메시지 추가 오류: {e}")

		def init_sip_console_welcome(self):
				"""SIP 콘솔 초기화 환영 메시지"""
				try:
						self.log_to_sip_console("PacketWave SIP Console Log 시작", "INFO")
						self.log_to_sip_console("개발 모드와 배포 모드에서 SIP 관련 로그를 확인할 수 있습니다", "INFO")
						self.log_to_sip_console("패킷 모니터링 준비 완료", "INFO")
				except Exception as e:
						print(f"SIP 콘솔 초기화 오류: {e}")

		def _apply_styles(self):
				self.setStyleSheet("""
						QMainWindow {
								background-color: #2d2d2d;
						}
						QWidget#sidebar {
								background-color: #0F3B7C;
						}
						QWidget {
								font-family: 'Segoe UI', sans-serif;
								color: white;
						}
						QPushButton#menu_button {
								background-color: #48c9b0;
								border: none;
								text-align: left;
								padding: 10px 15px;
						}
						QPushButton#menu_button:hover {
								background-color: rgba(255, 255, 255, 0.5);
						}
						QPushButton#menu_button QLabel {
								color: black;
								font-weight: bold;
						}
						QGroupBox {
								border: 1px solid #3a3a3a;
								border-radius: 4px;
								margin-top: 10px;
								padding: 10px;
								color: white;
								font-weight: bold;
						}
						#statusLabel {
								background-color: #48c9b0;
								padding: 5px;
								border-radius: 4px;
						}
						#toggleOff, #toggleOn {
								min-height: 35px;
								border: none;
								border-radius: 4px;
						}
						#toggleOff {
								background-color: #34495e;
								color: white;
						}
						#toggleOff:hover {
								background-color: black;
						}
						#toggleOn {
								background-color: #8e44ad;
								color: white;
						}
						#toggleOn:hover {
								background-color: black;
						}
						QTableWidget {
								background-color: #2A2A2A;
								border: none;
								gridline-color: #3a3a3a;
						}
						QTableWidget::item {
								padding: 5px;
						}
						QHeaderView::section {
								background-color: #2A2A2A;
								padding: 5px;
								border: none;
						}
						QWidget#callBlock {
								color: white;
								padding: 10px;
						}
						QWidget#callBlock QLabel {
								color: white;
								font-size: 12px;
						}
				""")

		def _create_led_with_text(self, text, color):
				widget = QWidget()
				layout = QHBoxLayout()
				layout.setAlignment(Qt.AlignLeft)
				layout.setContentsMargins(0, 0, 0, 0)
				led = QLabel()
				led.setObjectName("led_indicator")
				led.setFixedSize(8, 8)
				led.setStyleSheet(f'#led_indicator {{ background-color: {color}; border-radius: 4px; border: 1px solid rgba(0, 0, 0, 0.2); }}')
				shadow = QGraphicsDropShadowEffect()
				shadow.setBlurRadius(0)
				shadow.setColor(QColor(color))
				shadow.setOffset(0, 0)
				led.setGraphicsEffect(shadow)
				text_label = QLabel(text)
				text_label.setStyleSheet("color: white; font-size: 12px;")
				layout.addWidget(led)
				layout.addWidget(text_label)
				widget.setLayout(layout)
				return widget

		def _create_led(self, label, color):
				widget = QWidget()
				layout = QHBoxLayout()
				layout.setAlignment(Qt.AlignCenter)
				layout.setContentsMargins(0, 0, 0, 0)
				led = QLabel()
				led.setObjectName("led_indicator")
				led.setFixedSize(8, 8)
				led.setStyleSheet(f'#led_indicator {{ background-color: {color}; border-radius: 4px; border: 1px solid rgba(0, 0, 0, 0.2); }}')
				shadow = QGraphicsDropShadowEffect()
				shadow.setBlurRadius(3)
				shadow.setColor(QColor(color))
				shadow.setOffset(0, 0)
				led.setGraphicsEffect(shadow)
				layout.addWidget(led)
				widget.setLayout(layout)
				return widget

		def update_disk_usage(self):
				try:
						config = configparser.ConfigParser()
						config.read('settings.ini', encoding='utf-8')
						storage_path = config.get('Recording', 'save_path', fallback='D:\\')
						drive_letter = storage_path.replace('\\', '/').split('/')[0].split(':')[0]
						disk_usage = psutil.disk_usage(f"{drive_letter}:")
						total_gb = disk_usage.total / (1024**3)
						used_gb = disk_usage.used / (1024**3)
						free_gb = disk_usage.free / (1024**3)
						percent = int(disk_usage.percent)
						self.disk_label.setText(f'녹취드라이버( {drive_letter}: )')
						self.progress_bar.setValue(percent)
						self.disk_usage_label.setText(f'전체: {total_gb:.1f}GB | 사용중: {used_gb:.1f}GB | 남은용량: {free_gb:.1f}GB')
				except Exception as e:
						print(f"Error updating disk info: {e}")
						self.disk_usage_label.setText(f'{drive_letter}드라이브 정보를 읽을 수 없습니다')

		def show_settings(self):
				try:
						self.settings_popup = SettingsPopup(self)
						self.settings_popup.settings_changed.connect(self.update_dashboard_settings)
						self.settings_popup.path_changed.connect(self.update_storage_path)
						self.settings_popup.network_ip_changed.connect(self.on_network_ip_changed)
						self.settings_popup.exec()
				except Exception as e:
						print(f"설정 창 표시 중 오류: {e}")
						QMessageBox.warning(self, "오류", "Settings를 열 수 없습니다.")

		def update_dashboard_settings(self, settings_data):
				try:
						if 'Extension' in settings_data:
								self.phone_number.setText(settings_data['Extension']['rep_number'])
								if 'license_no' in settings_data['Extension']:
										self.license_number.setText(settings_data['Extension']['license_no'])
						if 'Network' in settings_data:
								self.ip_value.setText(settings_data['Network']['ap_ip'])
								self.mirror_ip_value.setText(settings_data['Network']['ip'])
						if 'Recording' in settings_data:
								drive_letter = settings_data['Recording']['save_path'].split(':')[0]
								self.disk_label.setText(f'녹취드라이버 ( {drive_letter} : ) 사용률:')
						self.update_disk_usage()
				except Exception as e:
						print(f"Error updating dashboard settings: {e}")
						QMessageBox.warning(self, "오류", "대시보드 업데이트 중 오류가 발생했습니다.")

		def update_storage_path(self, new_path):
				try:
						config = configparser.ConfigParser()
						config.read('settings.ini', encoding='utf-8')
						if 'Recording' not in config:
								config['Recording'] = {}
						config['Recording']['save_path'] = new_path
						self.update_disk_usage()
				except Exception as e:
						print(f"Error updating storage path: {e}")
						QMessageBox.warning(self, "오류", "저장 경로 업데이트 중 오류가 발생했습니다.")

		@Slot(str)
		def on_network_ip_changed(self, new_ip):
				"""Network IP 변경 시 패킷 캡처 재시작"""
				try:
						print(f"=== Network IP 변경 감지: {new_ip} ===")
						self.log_to_sip_console(f"Network IP 변경 감지: {new_ip}", "INFO")

						# 패킷 캡처 재시작
						success = self.restart_packet_capture(new_ip)

						if success:
								self.log_to_sip_console(f"새 포트미러링 IP ({new_ip})로 패킷 캡처 재시작 완료", "INFO")
								print(f"패킷 캡처 재시작 성공: {new_ip}")
						else:
								self.log_to_sip_console(f"패킷 캡처 재시작 실패", "ERROR")
								print("패킷 캡처 재시작 실패")

				except Exception as e:
						print(f"Network IP 변경 처리 중 오류: {e}")
						self.log_error("Network IP 변경 처리 오류", e)
						self.log_to_sip_console(f"IP 변경 처리 오류: {e}", "ERROR")

		TABLE_STYLE = """
				QTableWidget::item:selected {
						background-color: #18508F;
						color: white;
				}
		"""

		def _set_table_style(self, table: QTableWidget) -> None:
				table.setSelectionBehavior(QTableWidget.SelectRows)
				table.setSelectionMode(QTableWidget.SingleSelection)
				table.setStyleSheet(self.TABLE_STYLE)

		@Slot(str)
		def create_waiting_block(self, extension):
				try:
						if not self.block_exists(extension):
								block = self._create_call_block(
										internal_number=extension,
										received_number="",
										duration="00:00:00",
										status="대기중"
								)
								self.calls_layout.addWidget(block)
				except Exception as e:
						print(f"대기중 블록 생성 중 오류: {e}")

		def log_error(self, message, error=None, additional_info=None, level="error", console_output=True):
				"""로그 메시지를 파일에 기록하고 콘솔에 출력합니다."""
				try:
						# 로그 레벨 확인
						log_levels = {
								"debug": 0,
								"info": 1,
								"warning": 2,
								"error": 3
						}

						current_level = log_levels.get(level.lower(), 0)
						min_level = log_levels.get(getattr(self, "log_level", "info").lower(), 1)

						# 설정된 최소 레벨보다 낮은 로그는 무시
						if current_level < min_level:
								return

						timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

						# 콘솔 출력 (console_output이 True인 경우에만)
						if console_output:
								level_prefix = {
										"debug": "[디버그]",
										"info": "[정보]",
										"warning": "[경고]",
										"error": "[오류]"
								}.get(level.lower(), "[정보]")

								print(f"\n[{timestamp}] {level_prefix} {message}")

								if additional_info:
										print(f"추가 정보: {additional_info}")
								if error:
										print(f"에러 메시지: {str(error)}")

						# 파일 로깅
						log_file_path = os.path.join(getattr(self, 'work_dir', os.getcwd()), 'logs', 'voip_monitor.log')

						# 로그 디렉토리가 없으면 생성
						log_dir = os.path.dirname(log_file_path)
						if not os.path.exists(log_dir):
								try:
										os.makedirs(log_dir, exist_ok=True)
								except PermissionError:
										# 권한 문제 시 임시 디렉토리 사용
										import tempfile
										temp_log_dir = os.path.join(tempfile.gettempdir(), 'PacketWave', 'logs')
										os.makedirs(temp_log_dir, exist_ok=True)
										log_file_path = os.path.join(temp_log_dir, 'voip_monitor.log')

						with open(log_file_path, 'a', encoding='utf-8', buffering=1) as log_file:  # buffering=1: 라인 버퍼링
								log_file.write(f"\n[{timestamp}] {message}\n")
								if additional_info:
										log_file.write(f"추가 정보: {additional_info}\n")
								if error:
										log_file.write(f"에러 메시지: {str(error)}\n")
										log_file.write("스택 트레이스:\n")
										log_file.write(traceback.format_exc())
								log_file.write("\n")
								log_file.flush()  # 강제로 디스크에 쓰기
								os.fsync(log_file.fileno())  # 운영체제 버퍼도 비우기
				except Exception as e:
						print(f"로깅 중 오류 발생: {e}")
						sys.stderr.write(f"Critical logging error: {e}\n")
						sys.stderr.flush()

		def log_rtp_with_counter(self, packet):
				"""RTP 패킷을 카운터 기반으로 로깅 (터미널 스팸 방지)"""
				try:
						# 연결 식별키 생성 (양방향 구분)
						connection_key = f"{packet.ip.src}:{packet.udp.srcport}→{packet.ip.dst}:{packet.udp.dstport}"
						
						# 카운터 초기화 또는 증가
						if connection_key not in self.rtp_counters:
								# 새로운 연결 - 새 라인에 시작
								self.rtp_counters[connection_key] = 1
								try:
										print(f"[1] ♪ RTP 패킷 감지됨 - {packet.ip.src}:{packet.udp.srcport} → {packet.ip.dst}:{packet.udp.dstport}")
								except UnicodeEncodeError:
										print(f"[1] RTP 패킷 감지됨 - {packet.ip.src}:{packet.udp.srcport} → {packet.ip.dst}:{packet.udp.dstport}")
								sys.stdout.flush()
						else:
								# 기존 연결 - 같은 라인에서 카운터 업데이트
								self.rtp_counters[connection_key] += 1
								try:
										print(f"\r[{self.rtp_counters[connection_key]}] ♪ RTP 패킷 감지됨 - {packet.ip.src}:{packet.udp.srcport} → {packet.ip.dst}:{packet.udp.dstport}", end='', flush=True)
								except UnicodeEncodeError:
										print(f"\r[{self.rtp_counters[connection_key]}] RTP 패킷 감지됨 - {packet.ip.src}:{packet.udp.srcport} → {packet.ip.dst}:{packet.udp.dstport}", end='', flush=True)
								
				except Exception as e:
						# 오류 발생 시 기본 로깅으로 대체
						self.log_error(f"RTP 카운터 로깅 오류: {e}", level="warning")
						self.log_error(f"🎵 RTP 패킷 감지됨 - {packet.ip.src}:{packet.udp.srcport} → {packet.ip.dst}:{packet.udp.dstport}", level="info")

		def cleanup_rtp_counters_for_call(self, call_id):
				"""통화 종료 시 해당 통화의 RTP 카운터 정리"""
				try:
						with self.active_calls_lock:
								if call_id not in self.active_calls:
										return
								
								call_info = self.active_calls[call_id]
								# 통화 관련 IP/포트 정보로 카운터 정리
								if 'media_endpoints' in call_info:
										for endpoint in call_info['media_endpoints']:
												# 양방향 연결키 생성하여 정리
												src_key_pattern = f"{endpoint.get('src_ip')}:{endpoint.get('src_port')}"
												dst_key_pattern = f"{endpoint.get('dst_ip')}:{endpoint.get('dst_port')}"
												
												# 관련 카운터 찾아서 제거
												keys_to_remove = []
												for key in self.rtp_counters:
														if src_key_pattern in key or dst_key_pattern in key:
																keys_to_remove.append(key)
												
												for key in keys_to_remove:
														del self.rtp_counters[key]
														if key in self.rtp_display_lines:
																del self.rtp_display_lines[key]
								
								# 통화 종료 시 새 줄 출력 (다음 로그와 구분)
								print("\n")
								sys.stdout.flush()
								
				except Exception as e:
						self.log_error(f"RTP 카운터 정리 중 오류: {e}", level="warning")

		def analyze_sip_packet_in_main_thread(self, packet):
				"""메인 스레드에서 안전하게 SIP 패킷 분석"""
				try:
						# 메인 스레드에서 실행되는지 확인
						from PySide6.QtCore import QThread
						if QThread.currentThread() != self.thread():
								print("경고: SIP 패킷 분석이 메인 스레드가 아닌 곳에서 호출됨")
								# 메인 스레드가 아닌 경우 무시 (이미 시그널을 통해 호출되었으므로)
								self.safe_log("메인 스레드가 아닌 곳에서 호출된 SIP 패킷 분석 무시", "WARNING")
								return
						else:
								print("메인 스레드에서 SIP 패킷 분석 시작")
								self.log_to_sip_console("메인 스레드에서 SIP 패킷 분석 시작", "INFO")

						# 실제 SIP 패킷 분석 수행
						self.analyze_sip_packet(packet)
				except Exception as e:
						print(f"SIP 패킷 분석 중 오류: {e}")
						self.log_error("SIP 패킷 분석 오류", e)

		def analyze_sip_packet(self, packet):
				print(f"\n=== SIP 패킷 분석 시작 ===")
				self.log_to_sip_console("SIP 패킷 분석 시작", "SIP")

				# 포트미러링 환경에서 패킷 정보 추가 출력
				src_ip = None
				dst_ip = None
				if hasattr(packet, 'ip'):
						src_ip = getattr(packet.ip, 'src', 'unknown')
						dst_ip = getattr(packet.ip, 'dst', 'unknown')
						print(f"IP 정보 - Source: {src_ip}, Destination: {dst_ip}")
						self.log_to_sip_console(f"패킷 IP - 송신: {src_ip}, 수신: {dst_ip}", "SIP")

				# UDP 포트 정보 출력
				if hasattr(packet, 'udp'):
						try:
								src_port = packet.udp.srcport
								dst_port = packet.udp.dstport
								print(f"UDP 포트 - Source: {src_port}, Destination: {dst_port}")
								self.log_to_sip_console(f"UDP 포트 - 송신: {src_port}, 수신: {dst_port}", "SIP")
						except Exception as e:
								print(f"UDP 포트 정보 추출 오류: {e}")

				if not hasattr(packet, 'sip'):
						print("SIP 레이어가 없는 패킷")
						self.log_to_sip_console("SIP 레이어가 없는 패킷", "WARNING")
						self.log_error("SIP 레이어가 없는 패킷")
						return

				try:
						sip_layer = packet.sip
						print(f"SIP 패킷 감지됨")
						self.log_to_sip_console("SIP 패킷 감지됨", "SIP")

						# SIP 레이어 기본 정보만 출력 (상세 로그 제거)
						sip_method = getattr(sip_layer, 'method', getattr(sip_layer, 'status_line', 'unknown'))
						print(f"SIP 메서드/상태: {sip_method}")
						self.log_to_sip_console(f"SIP 메서드: {sip_method}", "SIP")

						if not hasattr(sip_layer, 'call_id'):
								print("Call-ID가 없는 SIP 패킷")
								self.log_to_sip_console("Call-ID가 없는 SIP 패킷", "WARNING")
								# Call-ID가 없어도 계속 진행 (다른 정보 확인)
								call_id = "no_call_id"
						else:
								call_id = sip_layer.call_id
								print(f"Call-ID: {call_id}")
								self.log_to_sip_console(f"Call-ID: {call_id}", "SIP")

						# 내선번호 추출 로직...
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
								self.log_error("내선번호 추출 실패", e)
								internal_number = sip_layer.from_user

						try:
								if hasattr(sip_layer, 'request_line'):
										request_line = str(sip_layer.request_line)

										# INVITE 처리
										if 'INVITE' in request_line:
												try:
														if not hasattr(sip_layer, 'from_user') or not hasattr(sip_layer, 'to_user'):
																self.log_error("필수 SIP 헤더 누락", additional_info={
																		"call_id": call_id,
																		"request_line": request_line
																})
																return

														from_number = self.extract_full_number(sip_layer.from_user)
														to_number = self.extract_full_number(sip_layer.to_user)

														if not from_number or not to_number:
															self.log_error("유효하지 않은 전화번호", additional_info={
																		"from_user": str(sip_layer.from_user),
																		"to_user": str(sip_layer.to_user)
															})
															return

														# SDP에서 RTP 포트 정보 추출 및 ExtensionRecordingManager에 전달
														self._extract_and_update_sdp_info(sip_layer, call_id, from_number, to_number)

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
																		if hasattr(self, 'websocket_server') and self.db is not None:
																				print(f"SIP 패킷 분석: 내선번호 {to_number}로 전화 수신 (발신: {from_number})")
																				self.log_to_sip_console(f"내선번호 {to_number}로 전화 수신 (발신: {from_number})", "SIP")
																				# 비동기 알림 전송을 위한 helper 함수
																				async def send_notification():
																						print(f"알림 전송 시작: 내선번호 {to_number}에 전화 수신 알림 (발신: {from_number})")
																						await self.websocket_server.notify_client(to_number, from_number, call_id, self)
																						print(f"알림 전송 완료: 내선번호 {to_number}")

																				# 별도 스레드에서 비동기 함수 실행
																				notification_thread = threading.Thread(
																						target=lambda: asyncio.run(send_notification()),
																						daemon=True
																				)
																				notification_thread.start()
																				print(f"알림 전송 스레드 시작: {to_number}")
																				self.log_error("클라이언트 알림 전송 시작", additional_info={
																						"to": to_number,
																						"from": from_number,
																						"call_id": call_id
																				})
																except Exception as notify_error:
																		print(f"클라이언트 알림 전송 실패: {str(notify_error)}")
																		self.log_error("클라이언트 알림 전송 실패", notify_error)

														# 통화 정보 저장 및 상태 전이
														with self.active_calls_lock:
																try:
																		before_state = dict(self.active_calls) if call_id in self.active_calls else None

																		# 상태 머신 관리
																		if call_id in self.call_state_machines:
																				current_state = self.call_state_machines[call_id].state
																				# TERMINATED 상태에서만 IDLE로 리셋
																				if current_state == CallState.TERMINATED:
																						self.call_state_machines[call_id] = CallStateMachine()
																		else:
																				# 새로운 상태 머신 생성
																				self.call_state_machines[call_id] = CallStateMachine()

																		current_state = self.call_state_machines[call_id].state
																		# IDLE 상태에서만 TRYING으로 전이 허용
																		if current_state == CallState.IDLE:
																				self.call_state_machines[call_id].update_state(CallState.TRYING)
																				self.log_error("상태 전이 성공", level="info", additional_info={
																						"call_id": call_id,
																						"from_state": "IDLE",
																						"to_state": "TRYING"
																				})
																		else:
																				self.log_error("잘못된 상태 전이 시도 무시", level="info", additional_info={
																						"call_id": call_id,
																						"current_state": current_state.name,
																						"attempted_state": "TRYING"
																				})

																		self.active_calls[call_id] = {
																				'start_time': datetime.datetime.now(),
																				'status': '시도중',
																				'from_number': from_number,
																				'to_number': to_number,
																				'direction': '수신' if to_number.startswith(('1','2','3','4','5','6','7','8','9')) else '발신',
																				'media_endpoints': [],
																				'packet': packet
																		}

																except Exception as state_error:
																		self.log_error("통화 상태 업데이트 실패", state_error)
																		return

														self.update_call_status(call_id, '시도중')

												except Exception as invite_error:
														self.log_error("INVITE 처리 중 오류", invite_error)
														return

										# REFER 처리
										elif 'REFER' in request_line:
												try:
														self._handle_refer_request(sip_layer, call_id, request_line)
												except Exception as refer_error:
														self.log_error("REFER 처리 중 오류", refer_error)
														return

										# BYE 처리
										elif 'BYE' in request_line:
												try:
														self._handle_bye_request(call_id)
												except Exception as bye_error:
														self.log_error("BYE 처리 중 오류", bye_error)
														return

										# CANCEL 처리
										elif 'CANCEL' in request_line:
												try:
														self._handle_cancel_request(call_id)
												except Exception as cancel_error:
														self.log_error("CANCEL 처리 중 오류", cancel_error)
														return

										# REGISTER 처리
										elif 'REGISTER' in request_line:
												try:
														self._handle_register_request(sip_layer, call_id, request_line, src_ip, dst_ip)
												except Exception as register_error:
														self.log_error("REGISTER 처리 중 오류", register_error)
														return

								# 응답 처리
								elif hasattr(sip_layer, 'status_line'):
										try:
												self._handle_sip_response(sip_layer, call_id)
										except Exception as response_error:
												self.log_error("SIP 응답 처리 중 오류", response_error)
												return

						except Exception as method_error:
								self.log_error("SIP 메소드 처리 중 오류", method_error)
								return

				except Exception as e:
						self.log_error("SIP 패킷 분석 중 심각한 오류", e)
						self.log_error("상세 오류 정보", level="info", additional_info={"traceback": traceback.format_exc()})

		def _handle_refer_request(self, sip_layer, call_id, request_line):
				"""REFER 요청 처리를 위한 헬퍼 메소드"""
				with open('voip_monitor.log', 'a', encoding='utf-8') as log_file:
						log_file.write("\n=== 돌려주기 요청 감지 ===\n")
						log_file.write(f"시간: {datetime.datetime.now()}\n")
						log_file.write(f"Call-ID: {call_id}\n")
						log_file.write(f"Request Line: {request_line}\n")

						with self.active_calls_lock:
								if call_id not in self.active_calls:
										log_file.write(f"[오류] 해당 Call-ID를 찾을 수 없음: {call_id}\n")
										return

								original_call = dict(self.active_calls[call_id])
								log_file.write(f"현재 통화 정보: {original_call}\n")

								if not all(k in original_call for k in ['to_number', 'from_number']):
										log_file.write("[오류] 필수 통화 정보 누락\n")
										return

								if not hasattr(sip_layer, 'refer_to'):
										log_file.write("[오류] REFER-TO 헤더 누락\n")
										return

								refer_to = str(sip_layer.refer_to)
								forwarded_ext = self.extract_full_number(refer_to.split('@')[0])

								if not forwarded_ext:
										log_file.write("[오류] 유효하지 않은 Refer-To 번호\n")
										return

								self._update_call_for_refer(call_id, original_call, forwarded_ext, log_file)

		def _handle_bye_request(self, call_id):
				"""BYE 요청 처리를 위한 헬퍼 메소드"""
				with self.active_calls_lock:
						if call_id in self.active_calls:
								before_state = dict(self.active_calls[call_id])
								from_number = self.active_calls[call_id].get('from_number', '')
								to_number = self.active_calls[call_id].get('to_number', '')

								# 상태 머신 업데이트 - IN_CALL 상태에서만 TERMINATED로 전이 허용
								if call_id in self.call_state_machines:
										current_state = self.call_state_machines[call_id].state
										if current_state == CallState.IN_CALL:
												self.call_state_machines[call_id].update_state(CallState.TERMINATED)
												self.log_error("상태 전이 성공", level="info", additional_info={
														"call_id": call_id,
														"from_state": "IN_CALL",
														"to_state": "TERMINATED"
												})

												# 통화 종료 시 녹음 종료 훅
												self._on_call_terminated(call_id)
										else:
												self.log_error("잘못된 상태 전이 시도 무시", level="info", additional_info={
														"call_id": call_id,
														"current_state": current_state.name,
														"attempted_state": "TERMINATED"
												})
												return

								# 내선번호로 BYE 알림 전송
								if is_extension(to_number):
										try:
												# WebSocket 서버가 있고 MongoDB가 연결되어 있는 경우에만 실행
												if hasattr(self, 'websocket_server') and self.db is not None:
														print(f"BYE 패킷 분석: 내선번호 {to_number}로 통화 종료 알림 (발신: {from_number})")
														# 비동기 알림 전송을 위한 helper 함수
														async def send_bye_notification():
																print(f"BYE 알림 전송 시작: 내선번호 {to_number}에 통화 종료 알림 (발신: {from_number})")
																await self.websocket_server.notify_client_call_end(to_number, from_number, call_id, "BYE")
																print(f"BYE 알림 전송 완료: 내선번호 {to_number}")

														# 별도 스레드에서 비동기 함수 실행
														notification_thread = threading.Thread(
																target=lambda: asyncio.run(send_bye_notification()),
																daemon=True
														)
														notification_thread.start()
														print(f"BYE 알림 전송 스레드 시작: {to_number}")
														self.log_error("BYE 클라이언트 알림 전송 시작", additional_info={
																"to": to_number,
																"from": from_number,
																"call_id": call_id,
																"method": "BYE"
														})
										except Exception as notify_error:
												print(f"BYE 클라이언트 알림 전송 실패: {str(notify_error)}")
												self.log_error("BYE 클라이언트 알림 전송 실패", notify_error)

								self.update_call_status(call_id, '통화종료', '정상종료')
								extension = self.get_extension_from_call(call_id)
								after_state = dict(self.active_calls[call_id])
								self.log_error("BYE 처리", level="info", additional_info={
										"extension": extension,
										"before_state": before_state,
										"after_state": after_state,
										"state_machine": self.call_state_machines[call_id].state.name if call_id in self.call_state_machines else "UNKNOWN"
								})
								if extension:
										pass  # 통화 시에는 내선번호를 사이드바에 추가하지 않음

		def _handle_cancel_request(self, call_id):
				"""CANCEL 요청 처리를 위한 헬퍼 메소드"""
				with self.active_calls_lock:
						if call_id in self.active_calls:
								before_state = dict(self.active_calls[call_id])
								from_number = self.active_calls[call_id].get('from_number', '')
								to_number = self.active_calls[call_id].get('to_number', '')

								# 내선번호로 CANCEL 알림 전송
								if is_extension(to_number):
										try:
												# WebSocket 서버가 있고 MongoDB가 연결되어 있는 경우에만 실행
												if hasattr(self, 'websocket_server') and self.db is not None:
														print(f"CANCEL 패킷 분석: 내선번호 {to_number}로 통화 취소 알림 (발신: {from_number})")
														# 비동기 알림 전송을 위한 helper 함수
														async def send_cancel_notification():
																print(f"CANCEL 알림 전송 시작: 내선번호 {to_number}에 통화 취소 알림 (발신: {from_number})")
																await self.websocket_server.notify_client_call_end(to_number, from_number, call_id, "CANCEL")
																print(f"CANCEL 알림 전송 완료: 내선번호 {to_number}")

														# 별도 스레드에서 비동기 함수 실행
														notification_thread = threading.Thread(
																target=lambda: asyncio.run(send_cancel_notification()),
																daemon=True
														)
														notification_thread.start()
														print(f"CANCEL 알림 전송 스레드 시작: {to_number}")
														self.log_error("CANCEL 클라이언트 알림 전송 시작", additional_info={
																"to": to_number,
																"from": from_number,
																"call_id": call_id,
																"method": "CANCEL"
														})
										except Exception as notify_error:
												print(f"CANCEL 클라이언트 알림 전송 실패: {str(notify_error)}")
												self.log_error("CANCEL 클라이언트 알림 전송 실패", notify_error)

								self.update_call_status(call_id, '통화종료', '발신취소')
								extension = self.get_extension_from_call(call_id)
								after_state = dict(self.active_calls[call_id])
								self.log_error("CANCEL 처리", level="info", additional_info={
										"extension": extension,
										"before_state": before_state,
										"after_state": after_state
								})
								if extension:
										pass  # 통화 시에는 내선번호를 사이드바에 추가하지 않음

		def _handle_register_request(self, sip_layer, call_id, request_line, src_ip=None, dst_ip=None):
				"""REGISTER 요청 처리를 위한 헬퍼 메소드"""
				try:
						print(f"=== SIP REGISTER 감지 ===")
						print(f"Request Line: {request_line}")
						print(f"IP 정보 - Source: {src_ip}, Destination: {dst_ip}")
						self.log_to_sip_console(f"SIP REGISTER 감지 - {request_line}", "SIP")
						self.log_to_sip_console(f"IP 정보 - 송신: {src_ip}, 수신: {dst_ip}", "SIP")

						# 포트미러링 환경에서 더 많은 헤더 정보 확인
						extension = None

						# 1. From 헤더에서 내선번호 추출 시도
						if hasattr(sip_layer, 'from_user'):
								from_user = str(sip_layer.from_user)
								print(f"From User: {from_user}")
								extension = self.extract_number(from_user)

						# 2. To 헤더에서도 확인 (포트미러링에서는 방향이 바뀔 수 있음)
						if not extension and hasattr(sip_layer, 'to_user'):
								to_user = str(sip_layer.to_user)
								print(f"To User: {to_user}")
								extension = self.extract_number(to_user)

						# 3. Contact 헤더에서 확인
						if not extension and hasattr(sip_layer, 'contact'):
								contact = str(sip_layer.contact)
								print(f"Contact: {contact}")
								# Contact 헤더에서 sip:1234@domain 형태 추출
								import re
								contact_match = re.search(r'sip:(\d{4})@', contact)
								if contact_match:
										extension = contact_match.group(1)

						# 4. Authorization 헤더에서 username 확인
						if not extension and hasattr(sip_layer, 'authorization'):
								auth_header = str(sip_layer.authorization)
								print(f"Authorization: {auth_header}")
								# username="1234" 형태 추출
								auth_match = re.search(r'username="?(\d{4})"?', auth_header)
								if auth_match:
										extension = auth_match.group(1)

						# 5. 모든 SIP 헤더 출력 (디버깅용)
						if not extension:
								print("=== 모든 SIP 헤더 확인 ===")
								for field_name in dir(sip_layer):
										if not field_name.startswith('_'):
												try:
														field_value = getattr(sip_layer, field_name)
														if field_value and str(field_value) != '<bound method':
																print(f"{field_name}: {field_value}")
																# 4자리 숫자 패턴 검색
																digit_match = re.search(r'\b(\d{4})\b', str(field_value))
																if digit_match and digit_match.group(1)[0] in ['1','2','3','4','5','6','7','8','9']:
																		extension = digit_match.group(1)
																		print(f"헤더 {field_name}에서 내선번호 발견: {extension}")
																		break
												except Exception:
														continue

						print(f"최종 추출된 내선번호: {extension}")

						if extension and len(extension) == 4 and extension[0] in ['1','2','3','4','5','6','7','8','9']:
								# SIP 등록된 내선번호를 사이드바에 추가
								self.refresh_extension_list_with_register(extension)
								
								# 내선-IP 매핑을 ExtensionRecordingManager에 전달
								if hasattr(self, 'recording_manager') and self.recording_manager:
										# 192.168 대역의 IP를 내선 IP로 판단
										extension_ip = None
										if src_ip and src_ip.startswith('192.168.'):
												extension_ip = src_ip
										elif dst_ip and dst_ip.startswith('192.168.'):
												extension_ip = dst_ip
										
										if extension_ip:
												self.recording_manager.update_extension_ip_mapping(extension, extension_ip)
												print(f"📍 내선-IP 매핑 등록: {extension} → {extension_ip}")
												self.log_to_sip_console(f"내선-IP 매핑 등록: {extension} → {extension_ip}", "SIP")
										else:
												print(f"⚠️ 내선 {extension}의 IP 정보를 찾을 수 없음 (src: {src_ip}, dst: {dst_ip})")
								
								self.log_to_sip_console(f"내선번호 {extension} 등록 완료", "SIP")
								self.log_error("SIP REGISTER 처리 완료", level="info", additional_info={
										"extension": extension,
										"call_id": call_id,
										"method": "REGISTER",
										"extension_ip": extension_ip if 'extension_ip' in locals() else None
								})
						else:
								print(f"유효하지 않은 내선번호: {extension}")
								self.log_to_sip_console(f"유효하지 않은 내선번호 또는 내선번호 추출 실패: {extension}", "WARNING")
				except Exception as e:
						print(f"REGISTER 처리 중 오류: {e}")
						self.log_error("REGISTER 요청 처리 중 오류", e)

		def _extract_and_update_sdp_info(self, sip_layer, call_id, from_number, to_number):
				"""SIP INVITE에서 SDP 정보를 추출하여 ExtensionRecordingManager에 전달"""
				try:
						if not hasattr(self, 'recording_manager') or not self.recording_manager:
								return
								
						# SDP 정보 추출
						sdp_info = {}
						rtp_ports = []
						
						# SIP 메시지 본문에서 SDP 찾기
						if hasattr(sip_layer, 'msg_body'):
								sdp_body = str(sip_layer.msg_body)
								print(f"🎵 SDP 본문 감지: {sdp_body[:200]}..." if len(sdp_body) > 200 else f"🎵 SDP 본문: {sdp_body}")
								
								# m=audio 포트 추출
								import re
								audio_matches = re.findall(r'm=audio (\d+) RTP', sdp_body)
								for port_str in audio_matches:
										try:
												port = int(port_str)
												if 1024 <= port <= 65535:
														rtp_ports.append(port)
														rtp_ports.append(port + 1)  # RTCP 포트도 포함
										except ValueError:
												continue
								
								if rtp_ports:
										print(f"📡 RTP 포트 추출됨: {rtp_ports}")
										self.log_to_sip_console(f"RTP 포트 추출: {rtp_ports}", "SIP")
										
										# SDP 정보 구성
										sdp_info = {
												'rtp_ports': list(set(rtp_ports)),  # 중복 제거
												'from_number': from_number,
												'to_number': to_number,
												'sdp_body': sdp_body[:500]  # 처음 500자만 저장
										}
										
										# ExtensionRecordingManager에 SIP 정보 업데이트
										self.recording_manager.update_call_sip_info(call_id, sdp_info)
								else:
										print("⚠️ SDP에서 RTP 포트를 찾을 수 없음")
						else:
								print("⚠️ SIP INVITE에 SDP 본문이 없음")
								
				except Exception as e:
						self.log_error(f"SDP 정보 추출 실패: {e}")
						print(f"SDP 추출 오류: {e}")

		def _handle_sip_response(self, sip_layer, call_id):
				"""SIP 응답 처리를 위한 헬퍼 메소드"""
				status_code = sip_layer.status_code
				if status_code == '100':
						extension = self.extract_number(sip_layer.from_user)
						if extension and len(extension) == 4 and extension[0] in ['1','2','3','4','5','6','7','8','9']:
								pass  # 통화 시에는 내선번호를 사이드바에 추가하지 않음

				with self.active_calls_lock:
						if call_id in self.active_calls:
								if status_code == '183':
										self.update_call_status(call_id, '벨울림')
										extension = self.get_extension_from_call(call_id)
										if extension:
												received_number = self.active_calls[call_id]['to_number']
												# 전화연결상태 블록 대신 사이드바에만 내선번호 추가
												self.add_extension(extension)
								elif status_code == '200':
										if self.active_calls[call_id]['status'] != '통화종료':
												# 상태 머신 업데이트 - TRYING 상태에서만 IN_CALL로 전이 허용
												if call_id in self.call_state_machines:
														current_state = self.call_state_machines[call_id].state
														if current_state == CallState.TRYING:
																self.call_state_machines[call_id].update_state(CallState.IN_CALL)
																self.log_error("상태 전이 성공", level="info", additional_info={
																		"call_id": call_id,
																		"from_state": "TRYING",
																		"to_state": "IN_CALL"
																})

																# 통화 시작 시 녹음 시작 훅
																self._on_call_started(call_id)
														else:
																self.log_error("잘못된 상태 전이 시도 무시", level="info", additional_info={
																		"call_id": call_id,
																		"current_state": current_state.name,
																		"attempted_state": "IN_CALL"
																})
																return

												self.update_call_status(call_id, '통화중')
												extension = self.get_extension_from_call(call_id)
												if extension:
														received_number = self.active_calls[call_id]['to_number']
														pass  # 통화 시에는 내선번호를 사이드바에 추가하지 않음

		def _update_call_for_refer(self, call_id, original_call, forwarded_ext, log_file):
				"""REFER 요청에 대한 통화 상태 업데이트"""
				external_number = original_call['to_number']
				forwarding_ext = original_call['from_number']

				log_file.write(f"발신번호(유지): {external_number}\n")
				log_file.write(f"수신번호(유지): {forwarding_ext}\n")
				log_file.write(f"돌려받을 내선: {forwarded_ext}\n")

				update_info = {
						'status': '통화중',
						'is_forwarded': True,
						'forward_to': forwarded_ext,
						'result': '돌려주기',
						'from_number': external_number,
						'to_number': forwarding_ext
				}

				with self.active_calls_lock:
						if call_id in self.active_calls:
								before_update = dict(self.active_calls[call_id])
								self.active_calls[call_id].update(update_info)
								after_update = dict(self.active_calls[call_id])
								log_file.write("통화 상태 업데이트:\n")
								log_file.write(f"업데이트 전: {before_update}\n")
								log_file.write(f"업데이트 후: {after_update}\n")

								# 발신번호가 내선이 아닐 경우에만 발,수신번호 크로스 변경경
								if not is_extension(external_number):
									for active_call_id, call_info in self.active_calls.items():
											if (call_info.get('from_number') == forwarding_ext and
													call_info.get('to_number') == forwarding_ext):
													before_related = dict(call_info)
													call_info.update({
															'status': '통화중',
															'result': '돌려주기'
													})
													after_related = dict(call_info)
													log_file.write(f"관련 통화 업데이트 (Call-ID: {active_call_id}):\n")
													log_file.write(f"업데이트 전: {before_related}\n")
													log_file.write(f"업데이트 후: {after_related}\n")

				log_file.write("=== 돌려주기 처리 완료 ===\n\n")

		def handle_new_call(self, sip_layer, call_id):
				try:
						print(f"새로운 통화 처리 시작 - Call-ID: {call_id}")
						from_number = self.extract_full_number(sip_layer.from_user)
						to_number = self.extract_full_number(sip_layer.to_user)
						print(f"발신번호: {from_number}")
						print(f"수신번호: {to_number}")
						with self.active_calls_lock:
								self.active_calls[call_id] = {
										'start_time': datetime.datetime.now(),
										'status': '시도중',
										'from_number': from_number,
										'to_number': to_number,
										'direction': '수신' if to_number.startswith(('1','2','3','4','5','6','7','8','9')) else '발신',
										'media_endpoints': []
								}
								self.call_state_machines[call_id] = CallStateMachine()
								self.call_state_machines[call_id].update_state(CallState.TRYING)
						print(f"통화 정보 저장 완료: {self.active_calls[call_id]}")
				except Exception as e:
						print(f"새 통화 처리 중 오류: {e}")

		def handle_call_end(self, sip_layer, call_id):
				with self.active_calls_lock:
						if call_id in self.active_calls:
								self.active_calls[call_id].update({
										'status': '통화종료',
										'end_time': datetime.datetime.now(),
										'result': '정상종료'
								})
				
				# RTP 카운터 정리
				self.cleanup_rtp_counters_for_call(call_id)
				
				self.update_voip_status()
				extension = self.get_extension_from_call(call_id)
				if extension:
						QMetaObject.invokeMethod(self, "update_block_to_waiting", Qt.QueuedConnection, Q_ARG(str, extension))
						print(f"통화 종료 처리: {extension}")

		def get_extension_from_call(self, call_id):
				with self.active_calls_lock:
						if call_id in self.active_calls:
								call_info = self.active_calls[call_id]
								from_number = call_info['from_number']
								to_number = call_info['to_number']
								is_extension = lambda num: num.startswith(('1', '2', '3', '4', '5', '6', '7', '8', '9')) and len(num) == 4
								return from_number if is_extension(from_number) else to_number if is_extension(to_number) else None
				return None

		def handle_call_cancel(self, call_id):
				with self.active_calls_lock:
						if call_id in self.active_calls:
								self.active_calls[call_id].update({
										'status': '통화종료',
										'end_time': datetime.datetime.now(),
										'result': '발신취소'
								})

		def update_voip_status(self):
				# UI 업데이트를 별도 스레드에서 처리
				QTimer.singleShot(0, self._update_voip_status_internal)

		def _update_voip_status_internal(self):
				try:
						table = self.findChild(QTableWidget, "log_list_table")
						if not table:
								return

						with self.active_calls_lock:
								# 유효한 통화 데이터만 필터링
								valid_calls = [
										(call_id, call_info)
										for call_id, call_info in self.active_calls.items()
										if call_info and all(
												call_info.get(key) is not None
												for key in ['start_time', 'direction', 'from_number', 'to_number', 'status']
										)
								]

								# 시간 순으로 정렬
								sorted_calls = sorted(
										valid_calls,
										key=lambda x: x[1]['start_time'],
										reverse=True
								)[:100]  # 최근 100개만 표시

						if sorted_calls:
								table.setRowCount(len(sorted_calls))
								for row, (call_id, call_info) in enumerate(sorted_calls):
										try:
												# 시간
												time_item = QTableWidgetItem(call_info['start_time'].strftime('%Y-%m-%d %H:%M:%S'))
												table.setItem(row, 0, time_item)

												# 통화 방향
												direction_item = QTableWidgetItem(str(call_info.get('direction', '')))
												table.setItem(row, 1, direction_item)

												# 발신번호
												from_item = QTableWidgetItem(str(call_info.get('from_number', '')))
												table.setItem(row, 2, from_item)

												# 수신번호
												to_item = QTableWidgetItem(str(call_info.get('to_number', '')))
												table.setItem(row, 3, to_item)

												# 상태
												status_item = QTableWidgetItem(str(call_info.get('status', '')))
												table.setItem(row, 4, status_item)

												# 결과
												result_item = QTableWidgetItem(str(call_info.get('result', '')))
												table.setItem(row, 5, result_item)

												# Call-ID
												callid_item = QTableWidgetItem(str(call_id))
												table.setItem(row, 6, callid_item)

												# 각 셀을 가운데 정렬
												for col in range(7):
														item = table.item(row, col)
														if item:
																item.setTextAlignment(Qt.AlignCenter)
										except Exception as cell_error:
												print(f"셀 업데이트 중 오류: {cell_error}")
												continue

						table.viewport().update()

				except Exception as e:
						print(f"통화 상태 업데이트 중 오류: {e}")
						print(traceback.format_exc())

		def update_packet_status(self):
				try:
						with self.active_calls_lock:
								for call_id, call_info in self.active_calls.items():
										if call_info.get('status_changed', False):
												extension = self.get_extension_from_call(call_id)
												if extension:
														self.create_waiting_block(extension)
												call_info['status_changed'] = False
				except Exception as e:
						print(f"패킷 상태 업데이트 중 오류: {e}")

		def calculate_duration(self, call_info):
				if 'start_time' in call_info:
						if 'end_time' in call_info:
								duration = call_info['end_time'] - call_info['start_time']
						else:
								duration = datetime.datetime.now() - call_info['start_time']
						return str(duration).split('.')[0]
				return "00:00:00"

		def is_rtp_packet(self, packet):
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
						# 오디오 Payload Type 범위 확장 (0-127 중 일반적인 오디오 타입들)
						# 0=PCMU, 8=PCMA, 9=G722, 18=G729 등 포함
						audio_payload_types = [0, 8, 9, 10, 11, 18, 96, 97, 98, 99, 100, 101, 102, 103]
						return payload_type in audio_payload_types or (96 <= payload_type <= 127)
				except Exception as e:
						print(f"RTP 패킷 확인 중 오류: {e}")
						return False

		def determine_stream_direction(self, packet, call_id):
				try:
						if call_id not in self.active_calls:
								return None
						call_info = self.active_calls[call_id]
						if 'media_endpoints' not in call_info:
								call_info['media_endpoints'] = []
						if 'media_endpoints_set' not in call_info:
								call_info['media_endpoints_set'] = {'local': set(), 'remote': set()}
						src_ip = packet.ip.src
						dst_ip = packet.ip.dst
						try:
								pbx_ip = call_id.split('@')[1].split(';')[0].split(':')[0]
						except:
								print(f"PBX IP 추출 실패 - Call-ID: {call_id}")
								return None
						src_endpoint = f"{src_ip}:{packet.udp.srcport}"
						dst_endpoint = f"{dst_ip}:{packet.udp.dstport}"
						if src_ip == pbx_ip:
								endpoint_info = {"ip": src_ip, "port": packet.udp.srcport}
								if endpoint_info not in call_info['media_endpoints']:
										call_info['media_endpoints'].append(endpoint_info)
								call_info['media_endpoints_set']['local'].add(src_endpoint)
								call_info['media_endpoints_set']['remote'].add(dst_endpoint)
								#print(f"OUT 패킷: {src_endpoint} -> {dst_endpoint}")
								return "OUT"
						elif dst_ip == pbx_ip:
								endpoint_info = {"ip": dst_ip, "port": packet.udp.dstport}
								if endpoint_info not in call_info['media_endpoints']:
										call_info['media_endpoints'].append(endpoint_info)
								call_info['media_endpoints_set']['local'].add(dst_endpoint)
								call_info['media_endpoints_set']['remote'].add(src_endpoint)
								#print(f"IN 패킷: {src_endpoint} -> {dst_endpoint}")
								return "IN"
						if src_endpoint in call_info['media_endpoints_set']['local']:
								return "OUT"
						elif src_endpoint in call_info['media_endpoints_set']['remote']:
								return "IN"
						elif dst_endpoint in call_info['media_endpoints_set']['local']:
								return "IN"
						elif dst_endpoint in call_info['media_endpoints_set']['remote']:
								return "OUT"
						return None
				except Exception as e:
						print(f"방향 결정 중 오류: {e}")
						print(traceback.format_exc())
						return None

		def extract_number(self, sip_user):
				try:
						if not sip_user:
								return ''
						sip_user = str(sip_user)
						print(f"내선번호 추출 시도: {sip_user}")

						# 여러 패턴으로 내선번호 추출 시도
						patterns = [
								# 1. sip:1234@domain 형태
								r'sip:(\d{4})@',
								# 2. <sip:1234@domain> 형태
								r'<sip:(\d{4})@',
								# 3. "Display Name" <sip:1234@domain> 형태
								r'"[^"]*"\s*<sip:(\d{4})@',
								# 4. 1234@domain 형태
								r'(\d{4})@',
								# 5. 단순히 4자리 숫자 (첫 번째가 1-9)
								r'\b([1-9]\d{3})\b',
								# 6. tel:+821234 형태에서 뒤 4자리
								r'tel:\+\d*(\d{4})',
								# 7. 109로 시작하는 특수 케이스
								r'109.*?([1-9]\d{3})'
						]

						for pattern in patterns:
								match = re.search(pattern, sip_user)
								if match:
										extension = match.group(1)
										if len(extension) == 4 and extension[0] in ['1','2','3','4','5','6','7','8','9']:
												print(f"패턴 '{pattern}'으로 내선번호 추출 성공: {extension}")
												return extension

						# 모든 패턴 실패 시 숫자만 추출 (레거시)
						digits_only = ''.join(c for c in sip_user if c.isdigit())
						if len(digits_only) >= 4:
								# 끝에서 4자리 또는 처음 4자리 중 유효한 것
								for candidate in [digits_only[-4:], digits_only[:4]]:
										if len(candidate) == 4 and candidate[0] in ['1','2','3','4','5','6','7','8','9']:
												print(f"숫자 추출으로 내선번호 발견: {candidate}")
												return candidate

						print(f"내선번호 추출 실패: {sip_user}")
						return ''
				except Exception as e:
						print(f"전화번호 추출 중 오류: {e}")
						return ''

		def extract_full_number(self, sip_user):
				"""전체 전화번호 추출 - 알파벳이 포함된 경우만 내선번호로 처리, 나머지는 전체 번호 표시"""
				try:
						if not sip_user:
								return ''
						sip_user = str(sip_user)
						print(f"전체 번호 추출 시도: {sip_user}")

						# 알파벳이 포함되어 있으면 내선번호 추출 (알파벳 뒤 4자리)
						if re.search(r'[a-zA-Z]', sip_user):
								print("알파벳 포함됨 - 내선번호 추출 시도")

								# 1. 먼저 기존 SIP URI 패턴 확인
								sip_patterns = [
										r'sip:([1-9]\d{3})@',
										r'<sip:([1-9]\d{3})@',
										r'"[^"]*"\s*<sip:([1-9]\d{3})@',
										r'([1-9]\d{3})@'
								]

								for pattern in sip_patterns:
										match = re.search(pattern, sip_user)
										if match:
												extension = match.group(1)
												if len(extension) == 4 and extension[0] in '123456789':
														print(f"SIP URI에서 내선번호 추출 성공: {extension}")
														return extension

								# 2. 알파벳 뒤의 4자리 패턴 확인 (예: 109J7422 → 7422)
								alpha_pattern = re.search(r'[a-zA-Z]([1-9]\d{3})', sip_user)
								if alpha_pattern:
										extension = alpha_pattern.group(1)
										if len(extension) == 4 and extension[0] in '123456789':
												print(f"알파벳 뒤 내선번호 추출 성공: {extension}")
												return extension

						# 알파벳이 없으면 전체 번호 추출
						else:
								print("알파벳 없음 - 전체 번호 추출")
								# 모든 숫자 추출
								digits_only = ''.join(c for c in sip_user if c.isdigit())
								if digits_only:
										print(f"전체 번호 추출 성공: {digits_only}")
										return digits_only

						print(f"번호 추출 실패: {sip_user}")
						return ''
				except Exception as e:
						print(f"전체 번호 추출 중 오류: {e}")
						return ''

		def get_call_id_from_rtp(self, packet):
				try:
						src_ip = packet.ip.src
						dst_ip = packet.ip.dst
						src_port = int(packet.udp.srcport)
						dst_port = int(packet.udp.dstport)
						src_endpoint = f"{src_ip}:{src_port}"
						dst_endpoint = f"{dst_ip}:{dst_port}"
						with self.active_calls_lock:
								for call_id, call_info in self.active_calls.items():
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

		def handle_sip_response(self, status_code, call_id, sip_layer):
				try:
						if hasattr(sip_layer, 'from'):
								ip = None
								if '@' in call_id:
										ip = call_id.split('@')[1]
								if ip:
										extension = self.extract_number(sip_layer.from_user)
										if ip not in self.sip_registrations:
												self.sip_registrations[ip] = {'status': [], 'extension': extension}
										self.sip_registrations[ip]['status'].append(status_code)
										if len(self.sip_registrations[ip]['status']) >= 3:
												recent_status = self.sip_registrations[ip]['status'][-3:]
												if '100' in recent_status and '401' in recent_status and '200' in recent_status:
														QMetaObject.invokeMethod(self, "create_waiting_block", Qt.QueuedConnection, Q_ARG(str, extension))
														self.handle_first_registration()
						with self.active_calls_lock:
								if call_id in self.active_calls:
										if status_code == '200':
												self.active_calls[call_id]['status'] = '통화중'
										elif status_code == '180':
												self.active_calls[call_id]['status'] = '벨울림'
										extension = self.get_extension_from_call(call_id)
										received_number = self.active_calls[call_id].get('to_number', "")
										pass  # 통화 시에는 내선번호를 사이드바에 추가하지 않음
				except Exception as e:
						print(f"SIP 응답 처리 중 오류: {e}")

		def create_or_update_block(self, extension):
				pass  # 통화 시에는 내선번호를 사이드바에 추가하지 않음

		def block_exists(self, extension):
				try:
						for i in range(self.calls_layout.count()):
								block = self.calls_layout.itemAt(i).widget()
								if block:
										for label in block.findChildren(QLabel):
												if label.objectName() == "extensionLabel" and label.text() == extension:
														return True
						return False
				except Exception as e:
						print(f"블록 존재 여부 확인 중 오류: {e}")
						return False

		@Slot(str)
		def create_block_in_main_thread(self, extension):
				"""메인 스레드에서 블록을 생성하는 메서드"""
				try:
						if not self.block_exists(extension):
								block = self._create_call_block(
										internal_number=extension,
										received_number="",
										duration="00:00:00",
										status="대기중"
								)
								self.calls_layout.addWidget(block)
								self.log_error("블록 생성 완료", additional_info={"extension": extension})
				except Exception as e:
						self.log_error("블록 생성 중 오류", e)

		def update_block_to_waiting(self, extension):
				try:
						for i in range(self.calls_layout.count()-1, -1, -1):
								block = self.calls_layout.itemAt(i).widget()
								if block:
										for child in block.findChildren(QLabel):
												if child.objectName() == "extensionLabel" and child.text() == extension:
														self.calls_layout.removeWidget(block)
														block.deleteLater()
						new_block = self._create_call_block(
								internal_number=extension,
								received_number="",
								duration="00:00:00",
								status="대기중"
						)
						self.calls_layout.addWidget(new_block)
						self.calls_layout.update()
						self.calls_container.update()
						print(f"블록 강제 업데이트 완료: {extension} -> 대기중")
						self.update_voip_status()
				except Exception as e:
						print(f"블록 강제 업데이트 오류: {e}")

		def update_block_in_main_thread(self, extension, status, received_number):
				try:
						for i in range(self.calls_layout.count()-1, -1, -1):
								block = self.calls_layout.itemAt(i).widget()
								if block:
										for child in block.findChildren(QLabel):
												if child.objectName() == "extensionLabel" and child.text() == extension:
														self.calls_layout.removeWidget(block)
														block.deleteLater()
						call_id = None
						with self.active_calls_lock:
								for cid, call_info in self.active_calls.items():
										if self.get_extension_from_call(cid) == extension:
												call_id = cid
												break
						duration = "00:00:00"
						if call_id and status == "통화중":
								duration = self.calculate_duration(self.active_calls[call_id])
						new_block = self._create_call_block(
								internal_number=extension,
								received_number=received_number,
								duration=duration,
								status=status
						)
						self.calls_layout.addWidget(new_block)
						self.calls_layout.update()
						self.calls_container.update()
				except Exception as e:
						print(f"블록 업데이트 중 오류: {e}")

		def update_call_status(self, call_id, new_status, result=''):
				try:
						with self.active_calls_lock:
								if call_id in self.active_calls:
										self.active_calls[call_id].update({
												'status': new_status,
												'result': result
										})
										if new_status == '통화종료':
												self.active_calls[call_id]['end_time'] = datetime.datetime.now()
												# RTPStreamManager 완전 제거됨 - ExtensionRecordingManager가 통화 녹음 처리
												# 통화 종료 시 ExtensionRecordingManager가 자동으로 변환 및 저장 처리함

										extension = self.get_extension_from_call(call_id)
										received_number = self.active_calls[call_id].get('to_number', "")
										pass  # 통화 시에는 내선번호를 사이드바에 추가하지 않음
						self.update_voip_status()
				except Exception as e:
						print(f"통화 상태 업데이트 중 오류: {e}")

		@Slot()
		def handle_first_registration(self):
				try:
						if not self.first_registration:
								self.first_registration = True
								print("첫 번째 SIP 등록 완료")
				except Exception as e:
						print(f"첫 번째 등록 처리 중 오류: {e}")

		def safe_log(self, message, level="INFO"):
				"""스레드 안전한 로깅 함수 - QTimer 대신 시그널 사용"""
				try:
						if hasattr(self, 'safe_log_signal'):
								self.safe_log_signal.emit(message, level)
						else:
								# 시그널이 없는 경우 직접 호출 (메인 스레드에서만)
								from PySide6.QtCore import QThread
								if QThread.currentThread() == self.thread():
										self.log_to_sip_console(message, level)
								else:
										print(f"[{level}] {message}")  # 워커 스레드에서는 콘솔 출력만
				except Exception as e:
						print(f"safe_log 오류: {e}")

		def cleanup_existing_dumpcap(self):
				"""기존 Dumpcap 프로세스 정리"""
				try:
						# ExtensionRecordingManager가 통화별 dumpcap을 관리하므로
						# 전역 dumpcap 정리는 선택적으로만 수행
						dumpcap_count = 0
						for proc in psutil.process_iter(['pid', 'name']):
								if proc.info['name'] and 'dumpcap' in proc.info['name'].lower():
										dumpcap_count += 1

						if dumpcap_count > 0:
								self.log_error(f"기존 dumpcap 프로세스 {dumpcap_count}개 감지됨 - ExtensionRecordingManager가 관리", level="info")
				except Exception as e:
						self.log_error("Dumpcap 프로세스 확인 중 오류", e)

		def handle_rtp_packet(self, packet):
				try:
						# RTPStreamManager 완전 제거 - ExtensionRecordingManager가 녹음 처리
						pass

						# SIP 정보 확인 및 처리
						if hasattr(packet, 'sip'):
								self.analyze_sip_packet(packet)
								return

						# UDP 페이로드가 없으면 처리하지 않음
						if not hasattr(packet, 'udp') or not hasattr(packet.udp, 'payload'):
								return

						active_calls = []
						with self.active_calls_lock:
								# 상태가 '통화중'인 통화만 필터링
								for cid, info in self.active_calls.items():
										if info.get('status') == '통화중':  # '벨울림' 상태는 제외
												active_calls.append((cid, info))

						if not active_calls:
								return

						#멀티 전화 통화 처리
						for call_id, call_info in active_calls:
								try:
										# 파일 경로 생성 전에 phone_ip 유효성 검사
										if '@' not in call_id:
												self.log_error("유효하지 않은 call_id 형식", additional_info={"call_id": call_id})
												continue

										phone_ip = call_id.split('@')[1].split(';')[0].split(':')[0]

										if not phone_ip:
												self.log_error("phone_ip를 추출할 수 없음", additional_info={"call_id": call_id})
												continue

										direction = self.determine_stream_direction(packet, call_id)

										if not direction:
												continue

										# SIP 정보가 있는 경우 로그 기록
										if 'packet' in call_info and hasattr(call_info['packet'], 'sip'):
												sip_info = call_info['packet'].sip
												from_user = getattr(sip_info, 'from_user', 'unknown')
												to_user = getattr(sip_info, 'to_user', 'unknown')

												if(len(from_user) > 4):
														# 정규식 분할 결과가 비어있을 수 있으므로 안전하게 처리
														from_user = re.split(r'[a-zA-Z]+', from_user)
												if(len(to_user) > 4):
														to_user = re.split(r'[a-zA-Z]+', to_user)

												#내선 간 통화인 경우
												if is_extension(to_user):
														# mongodb 찾기
														internalnumber_doc = self.internalnumber.find_one({"internal_number": to_user})
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

												# RTPStreamManager 완전 제거 - ExtensionRecordingManager가 녹음 처리
												pass

										except Exception as payload_error:
												self.log_error("페이로드 분석 오류", payload_error)
												continue
								except Exception as call_error:
										self.log_error("통화별 RTP 처리 오류", call_error, {"call_id": call_id})
										continue

				except Exception as e:
						self.log_error("RTP 패킷 처리 중 심각한 오류", e)
						self.log_error("상세 오류 정보", additional_info={"traceback": traceback.format_exc()})


		def update_call_duration(self):
				try:
						with self.active_calls_lock:
								for call_id, call_info in self.active_calls.items():
										if call_info.get('status') == '통화중':
												extension = self.get_extension_from_call(call_id)
												if extension:
														duration = self.calculate_duration(call_info)
														pass  # 통화 시에는 내선번호를 사이드바에 추가하지 않음
														for i in range(self.calls_layout.count()):
																block = self.calls_layout.itemAt(i).widget()
																if block:
																		found = False
																		for child in block.findChildren(QLabel):
																				if child.objectName() == "extensionLabel" and child.text() == extension:
																						found = True
																						break
																		if found:
																				for label in block.findChildren(QLabel):
																						if label.objectName() == "durationLabel":
																								label.setText(duration)
																								break
				except Exception as e:
						print(f"통화 시간 업데이트 중 오류: {e}")

		def _create_client_start_group(self):
				group = QGroupBox("클라이언트서버")
				layout = QHBoxLayout(group)
				layout.setContentsMargins(15, 20, 15, 15)
				layout.setSpacing(2)
				button_container = QWidget()
				button_layout = QHBoxLayout(button_container)
				button_layout.setContentsMargins(0, 0, 0, 0)
				button_layout.setSpacing(2)
				self.on_btn = QPushButton("ON")
				self.on_btn.setObjectName("toggleOn")
				self.on_btn.setCursor(Qt.PointingHandCursor)
				self.on_btn.clicked.connect(self.start_client)
				self.off_btn = QPushButton("OFF")
				self.off_btn.setObjectName("toggleOff")
				self.off_btn.setCursor(Qt.PointingHandCursor)
				self.off_btn.clicked.connect(self.stop_client)
				button_layout.addWidget(self.on_btn, 1)
				button_layout.addWidget(self.off_btn, 1)
				layout.addWidget(button_container)
				return group

		def start_client(self):
				try:
						self._start_client_services()
				except Exception as e:
						print(f"클라이언트 시작 중 오류: {e}")
						self.log_error("수동 클라이언트 서버 시작 실패", e)

		def _start_client_services(self):
				"""클라이언트 서비스를 즉시 시작 (UI 스레드용)"""
				try:
						# 필수 디렉토리 확인 및 생성
						required_dirs = [
								'mongodb/log',
								'mongodb/data/db',
								'logs',
								'temp',
								'temp/client_body_temp'
						]

						for dir_path in required_dirs:
								try:
										if not os.path.exists(dir_path):
												os.makedirs(dir_path, exist_ok=True)
												print(f"디렉토리 생성: {dir_path}")
								except Exception as dir_error:
										print(f"디렉토리 생성 실패: {dir_path} - {dir_error}")

						# 백그라운드에서 서비스 시작
						import threading
						service_thread = threading.Thread(target=self._start_client_services_background, daemon=True)
						service_thread.start()
						print("클라이언트 서비스 시작 명령이 전송되었습니다.")

				except Exception as e:
						print(f"클라이언트 서비스 시작 실패: {str(e)}")
						self.log_error("클라이언트 서비스 시작 실패", e)

		def _start_client_services_background(self):
				"""클라이언트 서비스를 단계별로 시작하고 안정화하는 헬퍼 메서드"""
				try:
						# 웹서비스 단계별 시작
						self.log_to_sip_console("웹 서비스 단계별 시작...", "INFO")

						# 1단계: 기존 서비스 정리
						self._cleanup_existing_services()

						# 2단계: Nginx 시작 및 확인
						if not self._start_and_verify_nginx():
								self.log_to_sip_console("Nginx 시작 실패", "ERROR")
								return False

						# 3단계: MongoDB 시작 및 확인
						if not self._start_and_verify_mongodb():
								self.log_to_sip_console("MongoDB 시작 실패", "ERROR")
								return False

						# 4단계: NestJS 시작 및 확인
						if not self._start_and_verify_nestjs():
								self.log_to_sip_console("NestJS 시작 실패", "ERROR")
								return False

						# 5단계: 전체 서비스 최종 검증
						if self._verify_all_services():
								self.log_to_sip_console("모든 웹 서비스 정상 동작 확인!", "INFO")
								self._show_service_urls()

								# 6단계: 웹서비스 안정화 완료 후 SIP 패킷 캡처 시작
								self.log_to_sip_console("📡 SIP 패킷 모니터링 시작...", "INFO")
								self.start_packet_capture()  # SIP 시작

								return True
						else:
								self.log_to_sip_console("일부 서비스에 문제가 있습니다", "ERROR")
								return False

				except Exception as e:
						print(f"웹 서비스 시작 실패: {str(e)}")
						self.log_error("웹 서비스 시작 실패", e)
						self.log_to_sip_console("웹 서비스 시작 실패", "ERROR")
						return False

		def _cleanup_existing_services(self):
				"""기존 서비스 정리"""
				try:
						self.log_to_sip_console("🧹 기존 서비스 정리 중...", "INFO")
						processes_to_kill = ['nginx.exe', 'mongod.exe', 'node.exe']
						for process in processes_to_kill:
								try:
										os.system(f'taskkill /f /im {process} >nul 2>&1')
								except:
										pass
						import time
						time.sleep(2)  # 프로세스 정리 대기
						self.log_to_sip_console("기존 서비스 정리 완료", "INFO")
				except Exception as e:
						self.log_to_sip_console(f"기존 서비스 정리 중 오류: {str(e)}", "WARNING")

		def _start_and_verify_nginx(self, retry_count=2):
				"""Nginx 시작 및 상태 확인 (재시도 로직 포함)"""
				for attempt in range(retry_count + 1):
						try:
								if attempt > 0:
										self.log_to_sip_console(f"Nginx 재시도 {attempt}/{retry_count}", "INFO")
								else:
										self.log_to_sip_console("Nginx 웹서버 시작 중...", "INFO")

								# 기존 Nginx 프로세스 정리
								os.system('taskkill /f /im nginx.exe >nul 2>&1')
								import time
								time.sleep(1)

								# Nginx 시작
								import configparser
								config = configparser.ConfigParser()
								config.read('settings.ini', encoding='utf-8')
								mode = config.get('General', 'mode', fallback='development')

								if mode == 'development':
										work_dir = config.get('General', 'dir_path', fallback=os.getcwd())
								else:
										work_dir = os.path.join(os.environ.get('ProgramFiles(x86)', 'C:\\Program Files (x86)'), 'Recap Voice')

								nginx_path = os.path.join(work_dir, 'nginx', 'nginx.exe')
								nginx_conf = os.path.join(work_dir, 'nginx', 'conf', 'nginx.conf')

								if not os.path.exists(nginx_path):
										self.log_to_sip_console(f"Nginx 실행파일을 찾을 수 없음: {nginx_path}", "ERROR")
										return False

								subprocess.Popen([nginx_path, '-c', nginx_conf],
																creationflags=subprocess.CREATE_NO_WINDOW)

								# Nginx 시작 대기 및 확인
								time.sleep(3)

								if self._check_process_running('nginx.exe'):
										self.log_to_sip_console("Nginx 웹서버 정상 시작", "INFO")
										return True
								else:
										if attempt < retry_count:
												self.log_to_sip_console("Nginx 시작 실패, 재시도 중...", "WARNING")
												time.sleep(2)
										else:
												self.log_to_sip_console("Nginx 프로세스 시작 실패", "ERROR")

						except Exception as e:
								if attempt < retry_count:
										self.log_to_sip_console(f"Nginx 시작 중 오류, 재시도 중: {str(e)}", "WARNING")
										time.sleep(2)
								else:
										self.log_to_sip_console(f"Nginx 시작 중 오류: {str(e)}", "ERROR")

				return False

		def _start_and_verify_mongodb(self, retry_count=2):
				"""MongoDB 시작 및 상태 확인 (재시도 로직 포함)"""
				for attempt in range(retry_count + 1):
						try:
								if attempt > 0:
										self.log_to_sip_console(f"MongoDB 재시도 {attempt}/{retry_count}", "INFO")
								else:
										self.log_to_sip_console("MongoDB 데이터베이스 시작 중...", "INFO")

								# 기존 MongoDB 프로세스 정리
								os.system('taskkill /f /im mongod.exe >nul 2>&1')
								import time
								time.sleep(2)

								# MongoDB 설정 읽기
								import configparser
								config = configparser.ConfigParser()
								config.read('settings.ini', encoding='utf-8')
								mode = config.get('General', 'mode', fallback='development')
								mongodb_host = config.get('Network', 'host', fallback='127.0.0.1')

								if mode == 'development':
										work_dir = config.get('General', 'dir_path', fallback=os.getcwd())
								else:
										work_dir = os.path.join(os.environ.get('ProgramFiles(x86)', 'C:\\Program Files (x86)'), 'Recap Voice')

								mongod_path = os.path.join(work_dir, 'mongodb', 'bin', 'mongod.exe')
								db_path = os.path.join(work_dir, 'mongodb', 'data', 'db')
								log_path = os.path.join(work_dir, 'mongodb', 'log', 'mongodb.log')

								if not os.path.exists(mongod_path):
										self.log_to_sip_console(f"MongoDB 실행파일을 찾을 수 없음: {mongod_path}", "ERROR")
										return False

								# 필요한 디렉토리 생성
								os.makedirs(db_path, exist_ok=True)
								os.makedirs(os.path.dirname(log_path), exist_ok=True)

								# MongoDB 시작
								subprocess.Popen([
										mongod_path,
										'--dbpath', db_path,
										'--logpath', log_path,
										'--logappend',
										'--port', '27017',
										'--bind_ip', f'0.0.0.0,{mongodb_host}'
								], creationflags=subprocess.CREATE_NO_WINDOW)

								# MongoDB 시작 대기 및 확인
								for i in range(15):  # 최대 15초 대기
										time.sleep(1)
										if self._check_mongodb_connection():
												self.log_to_sip_console("MongoDB 데이터베이스 정상 시작", "INFO")
												return True
										if i < 14:  # 마지막 시도가 아닌 경우만 메시지 출력
												self.log_to_sip_console(f"⏳ MongoDB 연결 대기 중... ({i+1}/15)", "INFO")

								if attempt < retry_count:
										self.log_to_sip_console("MongoDB 연결 실패, 재시도 중...", "WARNING")
										time.sleep(3)
								else:
										self.log_to_sip_console("MongoDB 연결 실패", "ERROR")

						except Exception as e:
								if attempt < retry_count:
										self.log_to_sip_console(f"MongoDB 시작 중 오류, 재시도 중: {str(e)}", "WARNING")
										time.sleep(3)
								else:
										self.log_to_sip_console(f"MongoDB 시작 중 오류: {str(e)}", "ERROR")

				return False

		def _start_and_verify_nestjs(self, retry_count=2):
				"""NestJS 시작 및 상태 확인 (재시도 로직 포함)"""
				for attempt in range(retry_count + 1):
						try:
								if attempt > 0:
										self.log_to_sip_console(f"NestJS 재시도 {attempt}/{retry_count}", "INFO")
								else:
										self.log_to_sip_console("⚡ NestJS 애플리케이션 시작 중...", "INFO")

								# 기존 Node.js 프로세스 정리
								os.system('taskkill /f /im node.exe >nul 2>&1')
								import time
								time.sleep(2)

								# 설정 읽기
								import configparser
								config = configparser.ConfigParser()
								config.read('settings.ini', encoding='utf-8')
								mode = config.get('Environment', 'mode', fallback='development')

								if mode == 'development':
										work_dir = config.get('DefaultDirectory', 'dir_path', fallback=os.getcwd())
								else:
										work_dir = os.path.join(os.environ.get('ProgramFiles(x86)', 'C:\\Program Files (x86)'), 'Recap Voice')

								client_dir = os.path.join(work_dir, 'packetwave_client')
								log_path = os.path.join(work_dir, 'logs', 'nestjs.log')

								if not os.path.exists(client_dir):
										self.log_to_sip_console(f"NestJS 프로젝트 디렉토리를 찾을 수 없음: {client_dir}", "ERROR")
										return False

								# 로그 디렉토리 생성
								os.makedirs(os.path.dirname(log_path), exist_ok=True)

								# NestJS 시작
								if mode == 'development':
										cmd = 'npm run start:dev'
								else:
										cmd = 'npm run start'

								subprocess.Popen(
										f'cmd /c "cd /d "{client_dir}" && {cmd} > "{log_path}" 2>&1"',
										shell=True,
										creationflags=subprocess.CREATE_NO_WINDOW
								)

								# NestJS 로그 모니터링 시작 (첫 번째 시도에서만)
								if attempt == 0:
										self._start_nestjs_log_monitoring()

								# NestJS 시작 대기 및 확인
								for i in range(20):  # 최대 20초 대기
										time.sleep(1)
										if self._check_nestjs_connection():
												self.log_to_sip_console("NestJS 애플리케이션 정상 시작", "INFO")
												return True
										if i < 19:  # 마지막 시도가 아닌 경우만 메시지 출력
												self.log_to_sip_console(f"⏳ NestJS 시작 대기 중... ({i+1}/20)", "INFO")

								if attempt < retry_count:
										self.log_to_sip_console("NestJS 시작 실패, 재시도 중...", "WARNING")
										time.sleep(5)
								else:
										self.log_to_sip_console("NestJS 시작 실패", "ERROR")

						except Exception as e:
								if attempt < retry_count:
										self.log_to_sip_console(f"NestJS 시작 중 오류, 재시도 중: {str(e)}", "WARNING")
										time.sleep(5)
								else:
										self.log_to_sip_console(f"NestJS 시작 중 오류: {str(e)}", "ERROR")

				return False

		def _check_process_running(self, process_name):
				"""프로세스 실행 상태 확인"""
				try:
						import subprocess
						result = subprocess.run(['tasklist', '/FI', f'IMAGENAME eq {process_name}'], capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
						return process_name.lower() in result.stdout.lower()
				except:
						return False

		def _check_mongodb_connection(self):
				"""MongoDB 연결 상태 확인"""
				try:
						from pymongo import MongoClient
						client = MongoClient('mongodb://127.0.0.1:27017/', serverSelectionTimeoutMS=5000)
						client.server_info()
						client.close()
						return True
				except:
						return False

		def _check_nestjs_connection(self):
				"""NestJS 연결 상태 확인"""
				try:
						import requests
						response = requests.get('http://localhost:3000', timeout=3)
						return response.status_code == 200
				except:
						return False

		def _verify_all_services(self):
				"""모든 서비스 최종 검증"""
				try:
						nginx_ok = self._check_process_running('nginx.exe')
						mongodb_ok = self._check_mongodb_connection()
						nestjs_ok = self._check_nestjs_connection()

						self.log_to_sip_console("서비스 상태 검증:", "INFO")
						self.log_to_sip_console(f"  • Nginx: {'' if nginx_ok else ''}", "INFO")
						self.log_to_sip_console(f"  • MongoDB: {'' if mongodb_ok else ''}", "INFO")
						self.log_to_sip_console(f"  • NestJS: {'' if nestjs_ok else ''}", "INFO")

						return nginx_ok and mongodb_ok and nestjs_ok
				except Exception as e:
						self.log_to_sip_console(f"서비스 검증 중 오류: {str(e)}", "ERROR")
						return False

		def _show_service_urls(self):
				"""서비스 URL 표시"""
				try:
						import configparser
						config = configparser.ConfigParser()
						config.read('settings.ini', encoding='utf-8')
						web_ip = config.get('Network', 'ip', fallback='127.0.0.1')
						web_port = config.get('Network', 'port', fallback='8080')
						self.log_to_sip_console(f"웹 인터페이스: http://{web_ip}:{web_port}/login", "INFO")
						self.log_to_sip_console(f"⚡ NestJS API: http://localhost:3000", "INFO")
				except Exception as e:
						self.log_to_sip_console("웹 인터페이스: http://127.0.0.1:8080/login", "INFO")


		def _start_nestjs_log_monitoring(self):
				"""NestJS 로그를 실시간으로 모니터링하여 SIP 콘솔에 표시"""
				try:
						import os
						log_file_path = os.path.join(os.getcwd(), 'logs', 'nestjs.log')

						def monitor_log():
								try:
										if os.path.exists(log_file_path):
												with open(log_file_path, 'r', encoding='utf-8', errors='ignore') as f:
														f.seek(0, 2)  # 파일 끝으로 이동
														while True:
																line = f.readline()
																if line:
																		# NestJS 로그를 터미널 형식으로 SIP 콘솔에 표시
																		clean_line = line.strip()
																		if clean_line:
																				# ANSI 색상 코드 제거
																				clean_text = remove_ansi_codes(clean_line)
																				if 'Starting Nest application' in clean_text:
																						self.log_to_sip_console("NestJS 애플리케이션 시작", "NESTJS")
																				elif 'Nest application successfully started' in clean_text:
																						self.log_to_sip_console("NestJS 애플리케이션 시작 완료", "NESTJS")
																						# 서비스 상태 검증 실행
																						threading.Thread(target=self._verify_nestjs_status, daemon=True).start()
																				elif 'Application is running on' in clean_text:
																						self.log_to_sip_console("NestJS 서버 실행 중: localhost:3000", "NESTJS")
																				elif 'ERROR' in clean_text.upper():
																						self.log_to_sip_console(f"{remove_ansi_codes(clean_line)}", "ERROR")
																				else:
																						# 중요한 로그만 표시 (노이즈 감소)
																						if any(keyword in clean_text for keyword in ['dependencies initialized', 'route', 'Controller']):
																								self.log_to_sip_console(f"📡 {remove_ansi_codes(clean_line)}", "NESTJS")
																				time.sleep(0.1)
										else:
												time.sleep(1)  # 로그 파일이 생성될 때까지 대기
								except Exception as e:
										self.log_to_sip_console(f"로그 모니터링 오류: {str(e)}", "ERROR")

						# 별도 스레드에서 로그 모니터링 실행
						log_thread = threading.Thread(target=monitor_log, daemon=True)
						log_thread.start()
						self.log_to_sip_console("NestJS 로그 모니터링 시작", "INFO")

				except Exception as e:
						self.log_to_sip_console(f"로그 모니터링 시작 실패: {str(e)}", "ERROR")

		def _verify_nestjs_status(self):
				"""NestJS 서비스 상태 확인"""
				try:
						import requests
						import time
						time.sleep(2)  # NestJS 완전 시작 대기
						response = requests.get('http://localhost:3000', timeout=10)
						if response.status_code == 200:
								self.log_to_sip_console("NestJS 서비스 정상 동작 확인", "NESTJS")
								return True
						else:
								self.log_to_sip_console(f"NestJS 서비스 응답 오류: {response.status_code}", "WARNING")
								return False
				except requests.exceptions.ConnectionError:
						self.log_to_sip_console("NestJS 서비스 연결 실패 - 서비스가 아직 시작 중일 수 있습니다", "WARNING")
						return False
				except requests.exceptions.Timeout:
						self.log_to_sip_console("NestJS 서비스 응답 시간 초과", "WARNING")
						return False
				except Exception as e:
						self.log_to_sip_console(f"NestJS 서비스 상태 확인 오류: {str(e)}", "WARNING")
						return False

				# UI 버튼 스타일 업데이트
				if hasattr(self, 'on_btn'):
						self.on_btn.setStyleSheet("""
								QPushButton {
										background-color: #FF0000;
										color: white;
										border: none;
										border-radius: 4px;
										min-height: 35px;
								}
								QPushButton:hover {
										background-color: #CC0000;
								}
						""")

		def stop_client(self):
				try:
						processes_to_kill = ['nginx.exe', 'mongod.exe', 'node.exe']
						for process in processes_to_kill:
								os.system(f'taskkill /f /im {process}')
								print(f"프로세스 종료 시도: {process}")
						self.on_btn.setStyleSheet("""
								QPushButton {
										background-color: #8e44ad;
										color: white;
										border: none;
										border-radius: 4px;
										min-height: 35px;
								}
								QPushButton:hover {
										background-color: black;
								}
						""")
				except Exception as e:
						print(f"클라이언트 중지 중 오류: {e}")

		def extract_ip_from_callid(self, call_id):
				try:
						ip_part = call_id.split('@')[1]
						ip_part = ip_part.split(';')[0]
						ip_part = ip_part.replace('[', '').replace(']', '')
						ip_part = ip_part.split(':')[0]
						if self.is_valid_ip(ip_part):
								return ip_part
						else:
								print(f"유효하지 않은 IP 주소 형식: {ip_part}")
								return "unknown"
				except Exception as e:
						print(f"IP 주소 추출 실패. Call-ID: {call_id}, 오류: {e}")
						return "unknown"

		def is_valid_ip(self, ip):
				try:
						parts = ip.split('.')
						if len(parts) != 4:
								return False
						return all(0 <= int(part) <= 255 for part in parts)
				except:
						return False

		def open_admin_site(self):
				try:
						config = configparser.ConfigParser()
						config.read('settings.ini', encoding='utf-8')
						ip_address = config.get('MongoDB', 'host', fallback='127.0.0.1')
						port = 8080
						url = f"http://{ip_address}:{port}"
						print(f"관리사이트 열기: {url}")
						QDesktopServices.openUrl(QUrl(url))
				except Exception as e:
						print(f"관리사이트 열기 실패: {e}")
						QMessageBox.warning(self, "오류", "관리사이트를 열 수 없습니다.")

		def _save_to_mongodb(self, merged_file, html_file, local_num, remote_num, call_id, packet):
				try:
						max_id_doc = self.filesinfo.find_one(sort=[("id", -1)])
						next_id = 1 if max_id_doc is None else max_id_doc["id"] + 1
						now_kst = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9)))
						audio = AudioSegment.from_wav(merged_file)
						duration_seconds = int(len(audio) / 1000.0)
						hours = duration_seconds // 3600
						minutes = (duration_seconds % 3600) // 60
						seconds = duration_seconds % 60
						duration_formatted = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
						filesize = os.path.getsize(merged_file)

						# per_lv8, per_lv9 값 가져오기
						per_lv8 = ""
						per_lv9 = ""
						per_lv8_update = ""
						per_lv9_update = ""

						# packet이 None인 경우 안전 처리
						sip_layer = None
						if packet and hasattr(packet, 'sip'):
								sip_layer = packet.sip
						# 통화 유형에 따른 권한 설정
						# packet이 없는 경우 기본 권한 설정 (ExtensionRecordingManager에서 호출시)
						if packet is None:
								# 내선번호를 기반으로 기본 권한 설정
								if is_extension(local_num):
										member_doc = self.members.find_one({"extension_num": local_num})
										if member_doc:
												per_lv8 = member_doc.get('per_lv8', '')
												per_lv9 = member_doc.get('per_lv9', '')
								elif is_extension(remote_num):
										member_doc = self.members.find_one({"extension_num": remote_num})
										if member_doc:
												per_lv8 = member_doc.get('per_lv8', '')
												per_lv9 = member_doc.get('per_lv9', '')

						# 내선 간 통화인 경우 (packet이 있는 경우만)
						elif is_extension(local_num) and is_extension(remote_num):
								if packet and hasattr(packet, 'sip'):
										if hasattr(sip_layer, 'method') and sip_layer.method == 'INVITE':

												 if hasattr(sip_layer, 'msg_hdr'):
															msg_hdr = sip_layer.msg_hdr

															# X-xfer-pressed: True 찾기
															if 'X-xfer-pressed: True' in msg_hdr:
																	# 내선 -> 내선 통화일때때 데이타베이스 수신내선,발신내선,파일명 같은 데이타 찾기
																	file_path_str = merged_file
																	file_name_str = os.path.basename(file_path_str)
																	# wav 파일명만 추출
																	fileinfo_doc = self.filesinfo.find_one({"from_number": local_num, "to_number": remote_num, "filename": {"$regex": file_name_str}})

																	if fileinfo_doc:
																			member_doc_update = self.members.find_one({"extension_num": local_num})
																			if member_doc_update:
																					per_lv8_update = member_doc_update.get('per_lv8', '')
																					per_lv9_update = member_doc_update.get('per_lv9', '')

																					result = self.filesinfo.update_one({"from_number": local_num, "to_number": remote_num, "filename": {"$regex": file_name_str}}, {"$set": {"per_lv8": per_lv8_update, "per_lv9": per_lv9_update}})

																			member_doc = self.members.find_one({"extension_num": remote_num})
																			if member_doc:
																					if member_doc_update:
																						per_lv8 = member_doc.get('per_lv8', '')
																						per_lv9 = member_doc.get('per_lv9', '')

																			# 로깅 추가
																			self.log_error("SIP 메시지 헤더 확인3", level="info", additional_info={
																					"msg_hdr": msg_hdr,
																					"from_number": local_num,
																					"to_number": remote_num,
																					"filename": {"$regex": file_name_str},
																					"per_lv8_update": per_lv8_update,
																					"per_lv9_update": per_lv9_update,
																					"per_lv8": per_lv8,
																					"per_lv9": per_lv9
																			})

						elif is_extension(remote_num) and not is_extension(local_num):
								# 외부 -> 내선 통화
								if packet and hasattr(packet, 'sip'):
										if hasattr(sip_layer, 'method') and sip_layer.method == 'REFER':
												# 외부에서 온 전화를 돌려주기
												if len(sip_layer.from_user) > 4 and len(sip_layer.from_user) < 9:
														local_num_str = re.split(r'[a-zA-Z]+', sip_layer.from_user)
														remote_num_str = re.split(r'[a-zA-Z]+', sip_layer.to_user)

														if hasattr(sip_layer, 'msg_hdr'):
																msg_hdr = sip_layer.msg_hdr

																member_doc = self.members.find_one({"extension_num": remote_num_str})
																if member_doc:
																		per_lv8 = member_doc.get('per_lv8', '')
																		per_lv9 = member_doc.get('per_lv9', '')
																		local_num = local_num_str
																		remote_num = remote_num_str
												# 로깅 추가
												self.log_error("SIP 메시지 헤더 확인4", level="info", additional_info={
														"msg_hdr": msg_hdr,
														"from_number": local_num,
														"to_number": remote_num,
														"per_lv8": per_lv8,
														"per_lv9": per_lv9
												})
										else:
												member_doc = self.members.find_one({"extension_num": remote_num})
												if member_doc:
														per_lv8 = member_doc.get('per_lv8', '')
														per_lv9 = member_doc.get('per_lv9', '')

						elif is_extension(local_num) and not is_extension(remote_num):
								if packet and hasattr(packet, 'sip'):
										if hasattr(sip_layer, 'method') and sip_layer.method == 'REFER':
										# 내선 -> 외부 통화
												if len(sip_layer.to_user) > 9 and len(sip_layer.to_user) < 12:
														# 내부에서 온 전화를 돌려주기
														# "07086661427,1427" 형식에서 콤마 뒤의 내선번호 추출
														local_num_str = sip_layer.from_user.split(',')[1].split('"')[0]
														# <sip:01077141436@112.222.225.104:5060> 형식에서 01077141436 추출
														remote_num_str = re.findall(r'<sip:(\d+)@', sip_layer.to_user)

														if hasattr(sip_layer, 'msg_hdr'):
																msg_hdr = sip_layer.msg_hdr
																member_doc = self.members.find_one({"extension_num": local_num_str})
																if member_doc:
																		per_lv8 = member_doc.get('per_lv8', '')
																		per_lv9 = member_doc.get('per_lv9', '')
																		local_num = remote_num_str
																		remote_num = local_num_str
												# 로깅 추가
												self.log_error("SIP 메시지 헤더 확인5", level="info", additional_info={
														"msg_hdr": msg_hdr,
														"from_number": local_num,
														"to_number": remote_num,
														"per_lv8": per_lv8,
														"per_lv9": per_lv9
												})
										else:
												member_doc = self.members.find_one({"extension_num": local_num})
												if member_doc:
														per_lv8 = member_doc.get('per_lv8', '')
														per_lv9 = member_doc.get('per_lv9', '')

						doc = {
								"id": next_id,
								"user_id": local_num,
								"filename": merged_file,
								"from_number": local_num,
								"to_number": remote_num,
								"filesize": str(filesize),
								"filestype": "wav",
								"files_text": html_file,
								"down_count": 0,
								"created_at": now_kst,
								"playtime": duration_formatted,
								"per_lv10": "admin",
								"per_lv8": per_lv8,
								"per_lv9": per_lv9,
								"call_id": call_id,
						}

						result = self.filesinfo.insert_one(doc)
						print(f"MongoDB 저장 완료: {result.inserted_id} (재생시간: {duration_formatted})")

				except Exception as e:
						print(f"MongoDB 저장 중 오류: {e}")
						print(traceback.format_exc())

		def setup_tray_icon(self):
				try:
						self.tray_icon = QSystemTrayIcon(self)
						app_icon = QIcon()

						app_icon.addFile(resource_path("images/recapvoice_squere.ico"), QSize(16, 16))
						app_icon.addFile(resource_path("images/recapvoice_squere.ico"), QSize(24, 24))
						app_icon.addFile(resource_path("images/recapvoice_squere.ico"), QSize(32, 32))
						app_icon.addFile(resource_path("images/recapvoice_squere.ico"), QSize(48, 48))
						if app_icon.isNull():
								app_icon = QApplication.style().standardIcon(QStyle.SP_ComputerIcon)
								print("아이콘 파일을 찾을 수 없습니다: images/recapvoice_squere.ico")
						self.tray_icon.setIcon(app_icon)
						self.setWindowIcon(app_icon)
						tray_menu = QMenu()
						open_action = QAction("Recap Voice 열기", self)
						open_action.triggered.connect(self.show_window)
						tray_menu.addAction(open_action)
						settings_action = QAction("환경 설정", self)
						settings_action.triggered.connect(self.show_settings)
						tray_menu.addAction(settings_action)
						tray_menu.addSeparator()
						quit_action = QAction("종료", self)
						quit_action.triggered.connect(self.quit_application)
						tray_menu.addAction(quit_action)
						self.tray_icon.setContextMenu(tray_menu)
						self.tray_icon.setToolTip("Recap Voice")
						self.tray_icon.show()
						self.tray_icon.activated.connect(self.tray_icon_activated)
				except Exception as e:
						print(f"트레이 아이콘 설정 중 오류: {e}")
						print(traceback.format_exc())

		def closeEvent(self, event):
				try:
						if self.tray_icon and self.tray_icon.isVisible():
								# 창 숨기기 전에 현재 상태 저장
								self.was_maximized = self.isMaximized()

								# 창을 숨기기만 하고 종료하지 않음
								self.hide()

								# 이벤트 무시 (프로그램 종료 방지)
								event.ignore()
						else:
								# 트레이 아이콘이 없는 경우에만 완전 종료
								self.cleanup()
								event.accept()
				except Exception as e:
						self.log_error("창 닫기 처리 중 오류", e)
						event.accept()

		def show_window(self):
				try:
						if self.was_maximized:
								self.showMaximized()
						else:
								self.showNormal()

						self.activateWindow()
						self.raise_()
				except Exception as e:
						self.log_error("창 복원 중 오류", e)

		def show_settings(self):
				try:
						self.settings_popup = SettingsPopup(self)
						self.settings_popup.settings_changed.connect(self.update_dashboard_settings)
						self.settings_popup.path_changed.connect(self.update_storage_path)
						self.settings_popup.network_ip_changed.connect(self.on_network_ip_changed)
						self.settings_popup.exec()
				except Exception as e:
						print(f"설정 창 표시 중 오류: {e}")
						QMessageBox.warning(self, "오류", "Settings를 열 수 없습니다.")

		def quit_application(self):
				try:
						# 타이머와 리소스 정리
						self.cleanup()

						# 통화별 녹음 관리자 정리
						if hasattr(self, 'recording_manager') and self.recording_manager:
								try:
										self.recording_manager.cleanup_all_recordings()
										print("통화별 녹음 프로세스 정리 완료")
								except Exception as e:
										print(f"녹음 프로세스 정리 실패: {e}")

						# WebSocket 서버 종료
						if hasattr(self, 'websocket_server') and self.websocket_server:
								try:
										if self.websocket_server.running:
												asyncio.run(self.websocket_server.stop_server())
												print("WebSocket 서버가 종료되었습니다.")
								except Exception as e:
										print(f"WebSocket server shutdown error: {e}")

						# 외부 프로세스 종료
						processes_to_kill = ['nginx.exe', 'mongod.exe', 'node.exe', 'Dumpcap.exe']
						for process in processes_to_kill:
								os.system(f'taskkill /f /im {process}')
								print(f"프로세스 종료 시도: {process}")

						# voip_monitor.log 파일을 0바이트로 초기화
						try:
								with open('voip_monitor.log', 'w') as f:
										f.truncate(0)
						except Exception as log_error:
								print(f"로그 파일 초기화 중 오류: {log_error}")

						self.tray_icon.hide()
						QApplication.quit()
				except Exception as e:
						print(f"프로그램 종료 중 오류: {e}")

		def tray_icon_activated(self, reason):
				if reason == QSystemTrayIcon.DoubleClick:
						self.show_window()

		def monitor_system_resources(self):
				try:
						cpu_percent = psutil.cpu_percent()
						memory_info = psutil.Process().memory_info()
						memory_percent = psutil.Process().memory_percent()

						# 로그 파일에만 기록하고 콘솔에는 출력하지 않음
						with open('voip_monitor.log', 'a', encoding='utf-8', buffering=1) as log_file:
								timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
								log_file.write(f"\n[{timestamp}] 시스템 리소스 상태\n")
								log_info = {
										"cpu_percent": f"{cpu_percent}%",
										"memory_used": f"{memory_info.rss / (1024 * 1024):.2f}MB",
										"memory_percent": f"{memory_percent}%",
										"active_calls": len(self.active_calls),
										"active_streams": len(self.active_streams)
								}
								log_file.write(f"추가 정보: {log_info}\n\n")
								log_file.flush()
								os.fsync(log_file.fileno())

				except Exception as e:
						# 오류는 기존 log_error 함수를 통해 기록하되, 콘솔 출력 없이
						self.log_error("리소스 모니터링 오류", e, level="error", console_output=False)

		def start_new_thread(self, target, name=None):
				"""스레드 생성 및 관리"""
				try:
						with self.thread_lock:
								# 죽은 스레드 정리
								self.active_threads = {t for t in self.active_threads if t.is_alive()}

								if len(self.active_threads) > 50:  # 스레드 수 제한
										self.log_error("스레드 수 초과", additional_info={
												"active_threads": len(self.active_threads)
										})
										return None

								thread = threading.Thread(target=target, name=name)
								thread.daemon = True  # 메인 프로세스 종료시 함께 종료
								thread.start()
								self.active_threads.add(thread)
								return thread

				except Exception as e:
						self.log_error("스레드 생성 오류", e)
						return None

		def check_system_limits(self):
				try:
						# Windows 환경에서는 psutil을 사용하여 시스템 리소스 정보 확인
						process = psutil.Process()
						resource_info = {
								"max_processes": len(process.children(recursive=True)),
								"python_bits": platform.architecture()[0],
								"python_version": sys.version,
								"memory_info": {
										"rss": f"{process.memory_info().rss / (1024 * 1024):.2f} MB",
										"vms": f"{process.memory_info().vms / (1024 * 1024):.2f} MB"
								},
								"cpu_percent": f"{process.cpu_percent()}%",
								"open_files": len(process.open_files())
						}

						# 콘솔에 출력하지 않고 로그 파일에만 기록
						self.log_error("시스템 리소스 제한", additional_info=resource_info, level="info", console_output=False)
				except Exception as e:
						# 오류도 콘솔에 출력하지 않음
						self.log_error("시스템 리소스 확인 중 오류", e, level="error", console_output=False)

def main():
		try:
					app = QApplication(sys.argv)
					app.setApplicationName("Recap Voice")

					# 명령줄 인수 처리
					parser = argparse.ArgumentParser(description="Recap Voice - VoIP SIP 신호 감지 및 클라이언트 알림 시스템")
					parser.add_argument("--log-level", choices=["debug", "info", "warning", "error"], default="info", help="로그 레벨 설정")
					args = parser.parse_args()

					# 단일 인스턴스 확인
					client = QLocalSocket()
					client.connectToServer("RecapVoiceInstance")

					if client.waitForConnected(500):
							# 이미 실행 중인 경우
							client.write(b"show")
							client.disconnectFromServer()
							app.quit()
							sys.exit(0)

					# 새 인스턴스 시작
					window = Dashboard()


					# 일반 모드로 실행
					window.show()
					app.setQuitOnLastWindowClosed(False)
					app.exec()

		except Exception as e:
				traceback.print_exc()
				with open('voip_monitor.log', 'a', encoding='utf-8') as f:
						f.write(f"\n=== 프로그램 시작 실패 ===\n")
						f.write(f"시간: {datetime.datetime.now()}\n")
						f.write(f"오류: {str(e)}\n")
						f.write(traceback.format_exc())
						f.write("\n")
				sys.exit(1)

# ============ 통화별 녹음 관리 메서드 ============

def _on_call_started(self, call_id: str):
	"""통화 시작 시 호출되는 훅 메서드 (CallState.TRYING → IN_CALL)"""
	try:
		if call_id not in self.active_calls:
			self.log_error(f"통화 정보 없음: {call_id}")
			return

		call_info = self.active_calls[call_id]
		extension = self.get_extension_from_call(call_id)
		from_number = call_info.get('from_number', '')
		to_number = call_info.get('to_number', '')

		if not extension:
			self.log_error(f"내선번호 정보 없음: {call_id}")
			return

		# 통화별 녹음 시작
		success = self.recording_manager.start_call_recording(
			call_id=call_id,
			extension=extension,
			from_number=from_number,
			to_number=to_number
		)

		if success:
			self.log_error(f"통화 녹음 시작: {call_id} (내선: {extension})", level="info")
		else:
			self.log_error(f"통화 녹음 시작 실패: {call_id}")

	except Exception as e:
		self.log_error(f"통화 시작 훅 오류: {e}")

def _on_call_terminated(self, call_id: str):
	"""통화 종료 시 호출되는 훅 메서드 (CallState.IN_CALL → TERMINATED)"""
	try:
		# 통화별 녹음 종료
		recording_info = self.recording_manager.stop_call_recording(call_id)

		if recording_info:
			# 별도 스레드에서 변환 및 저장
			conversion_thread = threading.Thread(
				target=self._handle_recording_conversion,
				args=(recording_info,),
				daemon=True
			)
			conversion_thread.start()

			extension = recording_info.get('extension', 'unknown')
			self.log_error(f"통화 녹음 종료: {call_id} (내선: {extension})", level="info")

			# 녹음 상태 즉시 업데이트 (UI 반영)
			QTimer.singleShot(100, self.update_recording_status_display)
		else:
			self.log_error(f"통화 녹음 정보 없음: {call_id}")

		# 녹음 종료 후 상태 업데이트 (지연 실행으로 확실한 반영)
		QTimer.singleShot(500, self.update_recording_status_display)

	except Exception as e:
		self.log_error(f"통화 종료 훅 오류: {e}")

def _handle_recording_conversion(self, recording_info: dict):
	"""녹음 파일 변환 및 저장 처리 (별도 스레드)"""
	try:
		success = self.recording_manager.convert_and_save(recording_info)

		if success:
			extension = recording_info.get('extension', 'unknown')
			self.log_error(f"녹음 파일 변환 시작: 내선 {extension}", level="info")
		else:
			self.log_error("녹음 파일 변환 실패")

	except Exception as e:
		self.log_error(f"녹음 변환 처리 오류: {e}")

def get_active_recordings_status(self) -> str:
	"""현재 진행 중인 녹음 상태 반환"""
	try:
		active_recordings = self.recording_manager.get_active_recordings()
		count = len(active_recordings)

		if count == 0:
			return "녹음 중인 통화 없음"
		else:
			extensions = [info.get('extension', 'unknown') for info in active_recordings.values()]
			return f"녹음 중: {count}개 통화 (내선: {', '.join(extensions)})"

	except Exception as e:
		self.log_error(f"녹음 상태 조회 오류: {e}")
		return "녹음 상태 조회 실패"

def update_recording_status_display(self):
	"""녹음 상태를 UI에 표시 (타이머 콜백)"""
	try:
		if not hasattr(self, 'recording_manager') or not self.recording_manager:
			return

		# 현재 녹음 상태 조회
		active_recordings = self.recording_manager.get_active_recordings()
		count = len(active_recordings)

		# 이전 상태와 다르면 로그 출력
		current_count = getattr(self, '_last_recording_count', -1)

		if count > 0:
			# 진행 중인 녹음이 있는 경우
			extensions_info = []
			for call_id, info in active_recordings.items():
				extension = info.get('extension', 'unknown')
				start_time = info.get('start_time')
				if start_time:
					duration = (datetime.datetime.now() - start_time).total_seconds()
					duration_str = f"{int(duration//60)}:{int(duration%60):02d}"
					extensions_info.append(f"{extension}({duration_str})")
				else:
					extensions_info.append(extension)

			# 첫 시작이거나 카운트가 변경되었을 때만 로그 출력
			if current_count != count:
				if current_count == -1:
					# 첫 시작
					status_msg = f"🎙️ 녹음 시작: {count}개 통화 - {', '.join(extensions_info)}"
				else:
					# 녹음 추가
					status_msg = f"🎙️ 녹음 추가: {count}개 통화 - {', '.join(extensions_info)}"
				self.log_to_sip_console(status_msg, "RECORDING")

		# 녹음 종료 확인 - 녹음 개수가 감소한 경우
		if current_count != count and current_count != -1:  # -1은 첫 시작 상태
			if count == 0 and current_count > 0:
				self.log_to_sip_console("🎙️ 모든 녹음 완료", "RECORDING")
			elif count < current_count and current_count > 0:
				# 일부 녹음 종료
				ended_count = current_count - count
				self.log_to_sip_console(f"🎙️ {ended_count}개 통화 녹음 완료 (현재: {count}개)", "RECORDING")

				# 디버깅을 위한 상세 로그 추가
				self.log_error(f"녹음 상태 변경 감지: {current_count} → {count} (감소: {ended_count}개)", level="info")

		# 상태 저장 (항상 업데이트)
		self._last_recording_count = count

	except Exception as e:
		self.log_error(f"녹음 상태 표시 오류: {e}")

# Dashboard 클래스에 메서드 추가 (실제로는 위 메서드들을 Dashboard 클래스 내부로 이동해야 함)
Dashboard._on_call_started = _on_call_started
Dashboard._on_call_terminated = _on_call_terminated
Dashboard._handle_recording_conversion = _handle_recording_conversion
Dashboard.get_active_recordings_status = get_active_recordings_status
Dashboard.update_recording_status_display = update_recording_status_display

if __name__ == "__main__":
		main()