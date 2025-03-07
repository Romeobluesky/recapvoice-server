#!/mvenv/Scripts/activate
# -*- coding: utf-8 -*-
import asyncio
import atexit
import audioop
import configparser
import datetime
import gc
import os
import platform
import psutil
import re
import subprocess
import sys
import threading
import time
import traceback
import wave

# 서드파티 라이브러리
from enum import Enum, auto
import pyshark
import requests
from pydub import AudioSegment
from pymongo import MongoClient
from PySide6.QtCore import *
from PySide6.QtGui import *
from PySide6.QtMultimedia import QMediaPlayer
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtNetwork import *
from PySide6.QtWidgets import *
import win32con
import win32gui
import win32process

# 로컬 모듈
from config_loader import load_config, get_wireshark_path
from packet_monitor import PacketMonitor
from settings_popup import SettingsPopup
from voip_monitor import VoipMonitor
from wav_merger import WavMerger


def resource_path(relative_path):
		"""리소스 파일의 절대 경로를 반환"""
		if hasattr(sys, '_MEIPASS'):
				return os.path.join(sys._MEIPASS, relative_path)
		return os.path.join(os.path.abspath('.'), relative_path)

def is_extension(number):
		return len(str(number)) == 4 and str(number)[0] in '123456789'
		
# -------------------------------------------------------------------
# 상태 전이 관리를 위한 FSM 클래스 (예시)

class CallState(Enum):
		IDLE = auto()         # 대기중
		TRYING = auto()       # 시도중
		IN_CALL = auto()      # 통화중
		TERMINATED = auto()   # 통화종료

class CallStateMachine:
		def __init__(self):
				self.state = CallState.IDLE

		def update_state(self, new_state):
				if self.is_valid_transition(new_state):
						print(f"상태 전이: {self.state.name} -> {new_state.name}")
						self.state = new_state
				else:
						print(f"잘못된 상태 전이 시도: {self.state.name} -> {new_state.name}")

		def is_valid_transition(self, new_state):
				valid_transitions = {
						CallState.IDLE: [CallState.TRYING],
						CallState.TRYING: [CallState.IN_CALL, CallState.TERMINATED],
						CallState.IN_CALL: [CallState.TERMINATED],
						CallState.TERMINATED: [CallState.IDLE]
				}
				return new_state in valid_transitions.get(self.state, [])
# -------------------------------------------------------------------

class PacketFlowWidget(QWidget):
		def __init__(self):
				super().__init__()
				self.setMinimumHeight(100)
				self.packets = []
				self.timer = QTimer(self)
				self.timer.timeout.connect(self.update)
				self.timer.start(1000)

		def paintEvent(self, event):
				painter = QPainter(self)
				painter.setRenderHint(QPainter.Antialiasing)
				painter.fillRect(self.rect(), QColor("#2d2d2d"))
				y_offset = 10
				for packet in self.packets:
						if y_offset >= self.height() - 10:
								break
						painter.setPen(Qt.white)
						painter.drawText(10, y_offset + 15, packet["time"])
						painter.setPen(QPen(QColor("#18508F"), 2))
						painter.drawLine(200, y_offset + 15, self.width() - 200, y_offset + 15)
						painter.setPen(Qt.white)
						painter.drawText(self.width() // 2 - 50, y_offset + 10, packet["type"])
						y_offset += 30

class Dashboard(QMainWindow):
		# Signal: 내선번호, 상태, 수신번호 전달
		block_creation_signal = Signal(str)
		block_update_signal = Signal(str, str, str)

		_instance = None  # 클래스 변수로 인스턴스 추적

		def __init__(self):
				try:
						super().__init__()
						Dashboard._instance = self
						self.setup_single_instance()
						self.cleanup_existing_dumpcap()  # 프로그램 시작 시 기존 Dumpcap 프로세스 정리
						
						# 필수 디렉토리 확인 및 생성
						required_dirs = ['images', 'logs']
						for dir_name in required_dirs:
								try:
										if not os.path.exists(dir_name):
												os.makedirs(dir_name)
								except PermissionError:
										self.log_error(f"디렉토리 생성 권한 없음: {dir_name}")
										raise
								except Exception as e:
										self.log_error(f"디렉토리 생성 실패: {dir_name}", e)
										raise
						
						# 설정 파일 확인
						if not os.path.exists('settings.ini'):
								self.log_error("settings.ini 파일이 없습니다")
								raise FileNotFoundError("settings.ini 파일이 필요합니다")
						
						# 로그 파일 초기화
						try:
								with open('voip_monitor.log', 'a', encoding='utf-8') as f:
										f.write(f"\n=== 프로그램 시작: {datetime.datetime.now()} ===\n")
						except Exception as e:
								self.log_error("로그 파일 초기화 실패", e)
								raise
						
						# 인트로 비디오 재생
						try:
								self.play_intro_video()
						except Exception as e:
								self.log_error("인트로 비디오 재생 실패", e)
								self.initialize_main_window()
						
				except Exception as e:
						self.log_error("대시보드 초기화 실패", e)
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

		def play_intro_video(self):
				try:
						# 비디오 위젯 생성
						self.video_widget = QVideoWidget()
						self.setCentralWidget(self.video_widget)
						
						# 미디어 플레이어 설정
						self.media_player = QMediaPlayer()
						self.media_player.setVideoOutput(self.video_widget)
						
						# 비디오 파일 경로 설정
						video_path = resource_path("images/recapvoicelogo.mp4")
						self.media_player.setSource(QUrl.fromLocalFile(video_path))
						
						# 창 테두리 제거 및 전체 화면 설정
						self.setWindowFlag(Qt.FramelessWindowHint)
						self.showFullScreen()
						
						# 비디오 재생 완료 시그널 연결
						self.media_player.mediaStatusChanged.connect(self.handle_media_status)
						
						# 비디오 재생 시작
						self.media_player.play()
						
				except Exception as e:
						print(f"인트로 비디오 재생 중 오류: {e}")
						self.initialize_main_window()

		def handle_media_status(self, status):
				if status == QMediaPlayer.MediaStatus.EndOfMedia:
						# 비디오 재생이 끝나면 메인 창 초기화
						self.initialize_main_window()

		def initialize_main_window(self):
				try:
						# 기존 비디오 위젯 제거
						if hasattr(self, 'video_widget'):
								try:
										self.video_widget.deleteLater()
								except Exception as e:
										self.log_error("비디오 위젯 제거 실패", e)
								
						if hasattr(self, 'media_player'):
								try:
										self.media_player.deleteLater()
								except Exception as e:
										self.log_error("미디어 플레이어 제거 실패", e)

						# 메인 창 초기화 전에 숨기기
						try:
								self.hide()
						except Exception as e:
								self.log_error("창 숨기기 실패", e)
				
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
								self.block_creation_signal.connect(self.create_block_in_main_thread)
								self.block_update_signal.connect(self.update_block_in_main_thread)
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
								self.first_registration = False
								self.packet_get = 0
								
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
								QTimer.singleShot(1000, self.start_packet_capture)
						except Exception as e:
								self.log_error("네트워크 인터페이스 초기화 실패", e)

						try:
								self.duration_timer = QTimer()
								self.duration_timer.timeout.connect(self.update_call_duration)
								self.duration_timer.start(1000)
								self.wav_merger = WavMerger()
						except Exception as e:
								self.log_error("타이머 및 유틸리티 초기화 실패", e)

						try:
								self.mongo_client = MongoClient('mongodb://localhost:27017/')
								self.db = self.mongo_client['packetwave']
								self.members = self.db['members']
								self.filesinfo = self.db['filesinfo']
								self.internalnumber = self.db['internalnumber']
						except Exception as e:
								self.log_error("MongoDB 연결 실패", e)

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
								subprocess.Popen(['start.bat'], shell=True)
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
								print("클라이언트 서버가 자동으로 시작되었습니다.")
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
						
				except Exception as e:
						self.log_error("메인 윈도우 초기화 중 심각한 오류", e)
						raise

		def show_maximized_window(self):
				"""최대화된 상태로 창을 표시"""
				self.showMaximized()  # show() 대신 showMaximized() 사용
				self.raise_()
				self.activateWindow()

		def cleanup(self):
				if hasattr(self, 'capture') and self.capture:
						try:
								if hasattr(self, 'loop') and self.loop and self.loop.is_running():
										self.loop.run_until_complete(self.capture.close_async())
								else:
										self.capture.close()
						except Exception as e:
								print(f"Cleanup error: {e}")

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
				line_list = self._create_line_list()
				log_list = self._create_log_list()
				content_layout.addWidget(line_list, 80)
				content_layout.addWidget(log_list, 20)
				content_layout.setStretch(2, 80)
				content_layout.setStretch(3, 20)
				self._apply_styles()
				self.resize(1400, 900)
				self.settings_popup.settings_changed.connect(self.update_dashboard_settings)
				self.settings_popup.path_changed.connect(self.update_storage_path)

		def load_network_interfaces(self):
				try:
						interfaces = list(psutil.net_if_addrs().keys())
						config = load_config()
						default_interface = config.get('Network', 'interface', fallback=interfaces[0])
						self.selected_interface = default_interface
				except Exception as e:
						print(f"네트워크 인터페이스 로드 실패: {e}")

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
								if cpu_percent > 80 or memory.percent > 80:
										self.log_error("시스템 리소스 부족", additional_info={
												"cpu": f"{cpu_percent}%",
												"memory": f"{memory.percent}%"
										})
										return
						except Exception as e:
								self.log_error("시스템 리소스 체크 실패", e)
								return
						
						# Wireshark 경로 확인
						config = load_config()
						if not config:
								self.log_error("설정 파일을 로드할 수 없습니다")
								return
						
						wireshark_path = get_wireshark_path()
						if not os.path.exists(wireshark_path):
								self.log_error("Wireshark가 설치되어 있지 않습니다")
								return
						
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

		def capture_packets(self, interface):
				"""패킷 캡처 실행"""
				if not interface:
						self.log_error("유효하지 않은 인터페이스")
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
								display_filter='sip or (udp and (udp.port >= 10000 and udp.port <= 20000))'
						)
						
						# 패킷 캡처 시작
						for packet in capture.sniff_continuously():
								try:
										# 메모리 사용량 모니터링
										process = psutil.Process()
										memory_percent = process.memory_percent()
										if memory_percent > 80:
												self.log_error("높은 메모리 사용량", additional_info={"memory_percent": memory_percent})
												
										if hasattr(packet, 'sip'):
												self.analyze_sip_packet(packet)
										elif hasattr(packet, 'udp') and self.is_rtp_packet(packet):
												self.handle_rtp_packet(packet)
												
								except Exception as packet_error:
										self.log_error("패킷 처리 중 오류", packet_error)
										continue
										
				except KeyboardInterrupt:
						self.log_error("사용자에 의한 캡처 중단")
				except Exception as capture_error:
						self.log_error("캡처 프로세스 오류", capture_error)
						
				finally:
						try:
								if capture:
										if loop and not loop.is_closed():
												loop.run_until_complete(capture.close_async())
										else:
												capture.close()
								else:
										self.log_error("캡처 프로세스가 초기화되지 않았습니다")
						except Exception as close_error:
								self.log_error("캡처 종료 실패", close_error)
								
						try:
								if loop and not loop.is_closed():
										loop.close()
								else:
										self.log_error("이벤트 루프가 초기화되지 않았습니다")
						except Exception as loop_error:
								self.log_error("이벤트 루프 종료 실패", loop_error)
								
						self.cleanup_existing_dumpcap()  # 캡처 종료 후 프로세스 정리

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
				menu_container = QWidget()
				menu_layout = QVBoxLayout(menu_container)
				menu_layout.setContentsMargins(0, 0, 0, 0)
				menu_layout.setSpacing(5)
				voip_btn = self._create_menu_button("VOIP MONITOR", "images/voip_icon.png")
				voip_btn.clicked.connect(self.show_voip_monitor)
				packet_btn = self._create_menu_button("PACKET MONITOR", "images/packet_icon.png")
				packet_btn.clicked.connect(self.show_packet_monitor)
				menu_layout.addWidget(voip_btn)
				menu_layout.addWidget(packet_btn)
				menu_layout.addStretch()
				layout.addWidget(menu_container)
				return sidebar

		def _create_menu_button(self, text, icon_path):
				btn = QPushButton()
				btn.setObjectName("menu_button")
				btn.setFixedHeight(40)
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
								("내선:", internal_number),
								("수신:", received_number),
								("상태:", status),
								("시간:", duration)
						]
				else:
						labels = [
								("내선:", internal_number),
								("상태:", status)
						]
				for idx, (title, value) in enumerate(labels):
						title_label = QLabel(title)
						title_label.setObjectName("blockTitle")
						title_label.setStyleSheet("color: #888888; font-size: 12px;")
						value_label = QLabel(value)
						# objectName 지정
						if title.strip() == "내선:":
								value_label.setObjectName("extensionLabel")
						elif title.strip() == "시간:":
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

		def _apply_styles(self):
				self.setStyleSheet("""
						QMainWindow {
								background-color: #2d2d2d;
						}
						QWidget#sidebar {
								background-color: #38ab89;
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

		def show_voip_monitor(self):
				try:
						self.voip_window = VoipMonitor()
						self.voip_window.setWindowFlags(Qt.Window)
						self.voip_window.setAttribute(Qt.WA_QuitOnClose, False)
						self.voip_window.show()
						config = load_config()
						if config.get('Environment', 'mode') == 'production':
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
																				except:
																						pass
																				return True
																		win32gui.EnumWindows(enum_windows_callback, None)
										except Exception as e:
												print(f"Error hiding windows: {e}")
								self.hide_console_timer = QTimer()
								self.hide_console_timer.timeout.connect(hide_wireshark_windows)
								self.hide_console_timer.start(100)
				except Exception as e:
						print(f"Error opening VOIP Monitor: {e}")
						QMessageBox.warning(self, "오류", "VOIP Monitor를 열 수 없습니다.")

		def show_packet_monitor(self):
				try:
						self.packet_monitor = PacketMonitor()
						self.packet_monitor.setWindowFlags(Qt.Window)
						self.packet_monitor.setAttribute(Qt.WA_QuitOnClose, False)
						self.packet_monitor.show()
						config = load_config()
						if config.get('Environment', 'mode') == 'production':
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
																				except:
																						pass
																				return True
																		win32gui.EnumWindows(enum_windows_callback, None)
										except Exception as e:
												print(f"Error hiding windows: {e}")
								self.hide_console_timer = QTimer()
								self.hide_console_timer.timeout.connect(hide_wireshark_windows)
								self.hide_console_timer.start(100)
				except Exception as e:
						print(f"Error opening Packet Monitor: {e}")
						QMessageBox.warning(self, "오류", "Packet Monitor를 열 수 없습니다.")

		def show_settings(self):
				try:
						self.settings_popup = SettingsPopup(self)
						self.settings_popup.settings_changed.connect(self.update_dashboard_settings)
						self.settings_popup.path_changed.connect(self.update_storage_path)
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

		def log_error(self, message, error=None, additional_info=None):
				try:
						with open('voip_monitor.log', 'a', encoding='utf-8', buffering=1) as log_file:  # buffering=1: 라인 버퍼링
								timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
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

		def analyze_sip_packet(self, packet):
				if not hasattr(packet, 'sip'):
						self.log_error("SIP 레이어가 없는 패킷")
						return

				try:
						sip_layer = packet.sip
						if not hasattr(sip_layer, 'call_id'):
								self.log_error("Call-ID가 없는 SIP 패킷")
								return

						call_id = sip_layer.call_id
						#내선번호만 추출
						try:
								if hasattr(sip_layer, 'from'):
										from_header = str(sip_layer.From)
										# "07086661427,1427" 형식에서 콤마 뒤의 내선번호 추출
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
										#self.log_error("SIP 패킷 분석", additional_info={
												#"request_line": request_line,
												#"call_id": call_id,
												#"internal_number": internal_number
										#})
										# 내선번호가 4자리 숫자인 경우 데이타베이스 업데이트
										if(is_extension(internal_number)):
												_number = internal_number
												ip_address = call_id.split('@')[1]

												# mongodb interalnumber 에서 내선번호 정보 확인 
												number_doc = self.internalnumber.find_one({'internal_number': _number})
												if number_doc:
														# 있으면 업데이트
														self.internalnumber.update_one(
																{'internal_number': _number},
																{'$set': {'ip_address': ip_address}}
														)
												else:
													# 없으면 등록
														number_docs = {
																'internal_number': _number,
																'ip_address': ip_address
														}
														self.internalnumber.insert_one(number_docs)
											
										# INVITE 처리
										if 'INVITE' in request_line:
												try:
														if not hasattr(sip_layer, 'from_user') or not hasattr(sip_layer, 'to_user'):
																self.log_error("필수 SIP 헤더 누락", additional_info={
																		"call_id": call_id,
																		"request_line": request_line
																})
																return
																	
														from_number = self.extract_number(sip_layer.from_user)
														to_number = self.extract_number(sip_layer.to_user)
														
														if not from_number or not to_number:
																self.log_error("유효하지 않은 전화번호", additional_info={
																		"from_user": str(sip_layer.from_user),
																		"to_user": str(sip_layer.to_user)
																})
																return
														
														# 내선번호 확인 및 블록 생성
														extension = None
														if len(from_number) == 4 and from_number[0] in '123456789':
																extension = from_number
														elif len(to_number) == 4 and to_number[0] in '123456789':
																extension = to_number
														
														if extension:
																self.log_error("내선 블록 생성 시도", additional_info={
																		"extension": extension,
																		"from_number": from_number,
																		"to_number": to_number
																})
																self.block_creation_signal.emit(extension)
														
														# 통화 정보 저장
														with self.active_calls_lock:
																try:
																		before_state = dict(self.active_calls) if call_id in self.active_calls else None
																		self.active_calls[call_id] = {
																				'start_time': datetime.datetime.now(),
																				'status': '시도중',
																				'from_number': from_number,
																				'to_number': to_number,
																				'direction': '수신' if to_number.startswith(('1','2','3','4','5','6','7','8','9')) else '발신',
																				'media_endpoints': [],
																				'packet': packet  # 패킷 정보 저장
																		}
																		after_state = dict(self.active_calls[call_id])
																		self.log_error("통화 상태 업데이트", additional_info={
																				"before": before_state,
																				"after": after_state
																		})
																		
																		self.call_state_machines[call_id] = CallStateMachine()
																		self.call_state_machines[call_id].update_state(CallState.TRYING)
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
						self.log_error("상세 오류 정보", additional_info={"traceback": traceback.format_exc()})

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
								forwarded_ext = self.extract_number(refer_to.split('@')[0])
								
								if not forwarded_ext:
										log_file.write("[오류] 유효하지 않은 Refer-To 번호\n")
										return
										
								self._update_call_for_refer(call_id, original_call, forwarded_ext, log_file)

		def _handle_bye_request(self, call_id):
				"""BYE 요청 처리를 위한 헬퍼 메소드"""
				with self.active_calls_lock:
						if call_id in self.active_calls:
								before_state = dict(self.active_calls[call_id])
								self.update_call_status(call_id, '통화종료', '정상종료')
								extension = self.get_extension_from_call(call_id)
								after_state = dict(self.active_calls[call_id])
								self.log_error("BYE 처리", additional_info={
										"extension": extension,
										"before_state": before_state,
										"after_state": after_state
								})
								if extension:
										self.block_update_signal.emit(extension, "대기중", "")

		def _handle_cancel_request(self, call_id):
				"""CANCEL 요청 처리를 위한 헬퍼 메소드"""
				with self.active_calls_lock:
						if call_id in self.active_calls:
								before_state = dict(self.active_calls[call_id])
								self.update_call_status(call_id, '통화종료', '발신취소')
								extension = self.get_extension_from_call(call_id)
								after_state = dict(self.active_calls[call_id])
								self.log_error("CANCEL 처리", additional_info={
										"extension": extension,
										"before_state": before_state,
										"after_state": after_state
								})
								if extension:
										self.block_update_signal.emit(extension, "대기중", "")

		def _handle_sip_response(self, sip_layer, call_id):
				"""SIP 응답 처리를 위한 헬퍼 메소드"""
				status_code = sip_layer.status_code
				if status_code == '100':
						extension = self.extract_number(sip_layer.from_user)
						if extension and len(extension) == 4 and extension[0] in ['1','2','3','4','5','6','7','8','9']:
								self.block_update_signal.emit(extension, "대기중", "")
								
				with self.active_calls_lock:
						if call_id in self.active_calls:
								if status_code == '183':
										self.update_call_status(call_id, '벨울림')
										extension = self.get_extension_from_call(call_id)
										if extension:
												received_number = self.active_calls[call_id]['to_number']
												self.block_update_signal.emit(extension, "벨울림", received_number)
								elif status_code == '200':
										if self.active_calls[call_id]['status'] != '통화종료':
												self.update_call_status(call_id, '통화중')
												extension = self.get_extension_from_call(call_id)
												if extension:
														received_number = self.active_calls[call_id]['to_number']
														self.block_update_signal.emit(extension, "통화중", received_number)

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
						from_number = self.extract_number(sip_layer.from_user)
						to_number = self.extract_number(sip_layer.to_user)
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
						return payload_type in [0, 8]
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
						if 'sip:' in sip_user:
								number = sip_user.split('sip:')[1].split('@')[0]
								return ''.join(c for c in number if c.isdigit())
						if '109' in sip_user:
								for i, char in enumerate(sip_user):
										if i > sip_user.index('109') + 2 and char.isalpha():
												return sip_user[i+1:]
						return ''.join(c for c in sip_user if c.isdigit())
				except Exception as e:
						print(f"전화번호 추출 중 오류: {e}")
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
										self.block_update_signal.emit(extension, self.active_calls[call_id]['status'], received_number)
				except Exception as e:
						print(f"SIP 응답 처리 중 오류: {e}")

		def create_or_update_block(self, extension):
				self.block_creation_signal.emit(extension)

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
												if hasattr(self, 'stream_manager'):
														stream_info_in = None
														stream_info_out = None
														in_key = f"{call_id}_IN"
														if in_key in self.stream_manager.active_streams:
																stream_info_in = self.stream_manager.finalize_stream(in_key)
														out_key = f"{call_id}_OUT"
														if out_key in self.stream_manager.active_streams:
																stream_info_out = self.stream_manager.finalize_stream(out_key)
														if stream_info_in and stream_info_out:
																try:
																		# 파일 경로에서 파일명 뒷자리 제거
																		file_dir = stream_info_in['file_dir']
																		timestamp = os.path.basename(file_dir)[:-2]
																		local_num = self.active_calls[call_id]['from_number']
																		remote_num = self.active_calls[call_id]['to_number']

																		merged_file = self.wav_merger.merge_and_save(
																				timestamp,
																				local_num,
																				remote_num,
																				stream_info_in['filepath'],
																				stream_info_out['filepath'],
																				file_dir
																		)
																		html_file = None
																		if merged_file:
																				# active_calls에서 저장된 packet 정보 가져오기
																				packet = self.active_calls[call_id].get('packet', None)
																				self._save_to_mongodb(
																						merged_file, html_file, 
																						local_num, remote_num, call_id, packet
																				)
																				
																		# 파일 삭제
																		try:
																				if os.path.exists(stream_info_in['filepath']):
																						os.remove(stream_info_in['filepath'])
																				if os.path.exists(stream_info_out['filepath']):
																						os.remove(stream_info_out['filepath'])
																		except Exception as e:
																				print(f"파일 삭제 중 오류: {e}")
																except Exception as e:
																		print(f"파일 처리 중 오류: {e}")

										extension = self.get_extension_from_call(call_id)
										received_number = self.active_calls[call_id].get('to_number', "")
										self.block_update_signal.emit(extension, new_status, received_number)
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

		def cleanup_existing_dumpcap(self):
				"""기존 Dumpcap 프로세스 정리"""
				try:
						for proc in psutil.process_iter(['pid', 'name']):
								if proc.info['name'] and 'dumpcap' in proc.info['name'].lower():
										try:
												proc.kill()
												self.log_error("기존 Dumpcap 프로세스 종료", additional_info={"pid": proc.info['pid']})
										except Exception as e:
												self.log_error("Dumpcap 프로세스 종료 실패", e)
				except Exception as e:
						self.log_error("Dumpcap 프로세스 정리 중 오류", e)

		def handle_rtp_packet(self, packet):
				try:
						if not hasattr(self, 'stream_manager'):
								self.stream_manager = RTPStreamManager()
								self.log_error("RTP 스트림 매니저 생성")
						
						# SIP 정보 확인 및 처리
						if hasattr(packet, 'sip'):
								self.analyze_sip_packet(packet)
								return

						# UDP 페이로드가 없으면 처리하지 않음
						if not hasattr(packet, 'udp') or not hasattr(packet.udp, 'payload'):
								return

						active_calls = []
						with self.active_calls_lock:
								for cid, info in self.active_calls.items():
										if info.get('status') == '통화중':
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
														
												stream_key = self.stream_manager.create_stream(
														call_id, direction, call_info, phone_ip_str
												)
												
												if stream_key:
														self.stream_manager.process_packet(
																stream_key, audio_data, sequence, payload_type
														)

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
														self.block_update_signal.emit(extension, "통화중", call_info['to_number'])
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
						subprocess.Popen(['start.bat'], shell=True)
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
				except Exception as e:
						print(f"클라이언트 시작 중 오류: {e}")

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
						ip_address = config.get('Network', 'ip', fallback='127.0.0.1')
						url = f"http://{ip_address}:3000"
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

						sip_layer = packet.sip
						# 통화 유형에 따른 권한 설정
						# 내선 간 통화인 경우
						if is_extension(local_num) and is_extension(remote_num):
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
																			self.log_error("SIP 메시지 헤더 확인3", additional_info={
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
												self.log_error("SIP 메시지 헤더 확인4", additional_info={
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
												self.log_error("SIP 메시지 헤더 확인5", additional_info={
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
						self.settings_popup.exec()
				except Exception as e:
						print(f"설정 창 표시 중 오류: {e}")
						QMessageBox.warning(self, "오류", "Settings를 열 수 없습니다.")

		def quit_application(self):
				try:
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
						
						self.log_error("시스템 리소스 상태", additional_info={
								"cpu_percent": f"{cpu_percent}%",
								"memory_used": f"{memory_info.rss / (1024 * 1024):.2f}MB",
								"memory_percent": f"{memory_percent}%",
								"active_calls": len(self.active_calls),
								"active_streams": len(self.active_streams)
						})
						
				except Exception as e:
						self.log_error("리소스 모니터링 오류", e)

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
						self.log_error("시스템 리소스 제한", additional_info={
								"max_processes": len(process.children(recursive=True)),
								"python_bits": platform.architecture()[0],
								"python_version": sys.version,
								"memory_info": {
										"rss": f"{process.memory_info().rss / (1024 * 1024):.2f} MB",
										"vms": f"{process.memory_info().vms / (1024 * 1024):.2f} MB"
								},
								"cpu_percent": f"{process.cpu_percent()}%",
								"open_files": len(process.open_files())
						})
				except Exception as e:
						self.log_error("시스템 리소스 확인 중 오류", e)

class FlowLayout(QLayout):
		def __init__(self, parent=None, margin=0, spacing=-1):
				super().__init__(parent)
				self._items = []
				self.setContentsMargins(margin, margin, margin, margin)
				self.setSpacing(spacing)

		def addItem(self, item):
				self._items.append(item)

		def count(self):
				return len(self._items)

		def itemAt(self, index):
				if 0 <= index < len(self._items):
						return self._items[index]
				return None

		def takeAt(self, index):
				if 0 <= index < len(self._items):
						return self._items.pop(index)
				return None

		def expandingDirections(self):
				return Qt.Orientations()

		def hasHeightForWidth(self):
				return True

		def heightForWidth(self, width):
				height = self._doLayout(QRect(0, 0, width, 0), True)
				return height

		def setGeometry(self, rect):
				super().setGeometry(rect)
				self._doLayout(rect, False)

		def sizeHint(self):
				return self.minimumSize()

		def minimumSize(self):
				size = QSize()
				for item in self._items:
						size = size.expandedTo(item.minimumSize())
				margin = self.contentsMargins()
				size += QSize(2 * margin.top(), 2 * margin.bottom())
				return size

		def _doLayout(self, rect, testOnly):
				x = rect.x()
				y = rect.y()
				lineHeight = 0
				spacing = self.spacing()
				for item in self._items:
						widget = item.widget()
						spaceX = spacing
						spaceY = spacing
						nextX = x + item.sizeHint().width() + spaceX
						if nextX - spaceX > rect.right() and lineHeight > 0:
								x = rect.x()
								y = y + lineHeight + spaceY
								nextX = x + item.sizeHint().width() + spaceX
								lineHeight = 0
						if not testOnly:
								item.setGeometry(QRect(QPoint(x, y), item.sizeHint()))
						x = nextX
						lineHeight = max(lineHeight, item.sizeHint().height())
				return y + lineHeight - rect.y()

# RTPStreamManager 클래스 (기존 코드 기반)
class RTPStreamManager:
		def __init__(self):
				self.active_streams = {}
				self.stream_locks = {}
				self.file_locks = {}
				self.min_buffer_size = 4000
				self.max_buffer_size = 16000
				self.buffer_adjust_threshold = 0.8
				
		def get_stream_key(self, call_id, direction):
				return f"{call_id}_{direction}"
				
		def create_stream(self, call_id, direction, call_info, phone_ip):
				try:
						stream_key = self.get_stream_key(call_id, direction)
						if stream_key not in self.active_streams:
								self.stream_locks[stream_key] = threading.Lock()
								self.file_locks[stream_key] = threading.Lock()
								
								config = configparser.ConfigParser()
								config.read('settings.ini', encoding='utf-8')
								base_path = config.get('Recording', 'save_path', fallback='C:/Program Files (x86)/Recap Voice/RecapVoiceRecord')
								
								today = datetime.datetime.now().strftime("%Y%m%d")
								
								# 통화별 시간 저장을 위한 딕셔너리가 없으면 생성
								if not hasattr(self, 'call_start_times'):
										self.call_start_times = {}
								
								# call_id에 대한 시간이 없으면 새로 생성
								if call_id not in self.call_start_times:
										if 'start_time' in call_info:
												self.call_start_times[call_id] = call_info['start_time'].strftime("%H%M%S")
										else:
												self.call_start_times[call_id] = datetime.datetime.now().strftime("%H%M%S")
								
								# 저장된 시간 사용
								time_str = self.call_start_times[call_id]
								
								# 디렉토리 경로 생성 및 확인
								file_dir = os.path.join(base_path, today, phone_ip, time_str)
								if not os.path.exists(file_dir):
										try:
												os.makedirs(file_dir)
										except Exception as e:
												print(f"디렉토리 생성 실패: {e}")
												return None
												
								# 파일명 생성
								filename = f"{time_str}_{direction}_{call_info['from_number']}_{call_info['to_number']}_{today}.wav"
								filepath = os.path.join(file_dir, filename)
								
								try:
										with wave.open(filepath, 'wb') as wav_file:
												wav_file.setnchannels(1)
												wav_file.setsampwidth(2)
												wav_file.setframerate(8000)
								except Exception as e:
										print(f"WAV 파일 초기화 실패: {e}")
										return None
										
								self.active_streams[stream_key] = {
										'call_id': call_id,
										'direction': direction,
										'call_info': call_info,
										'phone_ip': phone_ip,
										'file_dir': file_dir,
										'filepath': filepath,
										'audio_data': bytearray(),
										'sequence': 0,
										'saved': False,
										'wav_file': None,
										'current_buffer_size': 8000,
										'packet_count': 0,
										'last_write_time': time.time(),
										'packet_rate': 0,
										'is_internal_call': self._is_internal_call(call_info)
								}
								
						return stream_key
				except Exception as e:
						print(f"스트림 생성 중 오류: {e}")
						return None

		def _is_internal_call(self, call_info):
				from_number = str(call_info['from_number'])
				to_number = str(call_info['to_number'])
				return (len(from_number) == 4 and from_number[0] in '123456789' and
								len(to_number) == 4 and to_number[0] in '123456789')

		def _adjust_buffer_size(self, stream_info):
				try:
						current_time = time.time()
						time_diff = current_time - stream_info['last_write_time']
						if time_diff > 0:
								current_rate = stream_info['packet_count'] / time_diff
								alpha = 0.3
								stream_info['packet_rate'] = (alpha * current_rate + (1 - alpha) * stream_info['packet_rate'])
								if stream_info['is_internal_call']:
										target_size = min(int(stream_info['packet_rate'] * 0.8 * 1000), self.max_buffer_size // 2)
								else:
										target_size = min(int(stream_info['packet_rate'] * 1.2 * 1000), self.max_buffer_size)
								target_size = max(self.min_buffer_size, min(target_size, self.max_buffer_size))
								if abs(target_size - stream_info['current_buffer_size']) > self.min_buffer_size:
										if target_size > stream_info['current_buffer_size']:
												stream_info['current_buffer_size'] += self.min_buffer_size
										else:
												stream_info['current_buffer_size'] -= self.min_buffer_size
								stream_info['packet_count'] = 0
								stream_info['last_write_time'] = current_time
								print(f"버퍼 크기 조정: {stream_info['current_buffer_size']} bytes")
				except Exception as e:
						print(f"버퍼 크기 조정 중 오류: {e}")

		def process_packet(self, stream_key, audio_data, sequence, payload_type):
				if not stream_key or not audio_data:
						print("유효하지 않은 스트림 키 또는 오디오 데이터")
						return

				if stream_key not in self.stream_locks:
						print(f"스트림 락이 존재하지 않음: {stream_key}")
						return

				try:
						with self.stream_locks[stream_key]:
								if stream_key not in self.active_streams:
										print(f"활성 스트림이 존재하지 않음: {stream_key}")
										return

								stream_info = self.active_streams[stream_key]
								
								if stream_info['saved']:
										print("이미 저장된 스트림")
										return

								try:
										print(f"패킷 수신 - 시퀀스: {sequence}, 크기: {len(audio_data)} bytes")
										
										# 시퀀스 번호 검증
										if stream_info['sequence'] > 0:
												expected_sequence = (stream_info['sequence'] + 1) % 65536
												if sequence != expected_sequence:
														print(f"시퀀스 불연속 감지: 예상={expected_sequence}, 실제={sequence}")
														# 시퀀스 불연속 로깅
														self._log_sequence_discontinuity(stream_key, expected_sequence, sequence)
										
										# 중복 패킷 체크
										if sequence <= stream_info['sequence']:
												print(f"중복 패킷 무시: 현재={stream_info['sequence']}, 수신={sequence}")
												return

										# 메모리 사용량 체크
										current_memory = len(stream_info['audio_data'])
										if current_memory > self.max_buffer_size * 2:
												print(f"경고: 버퍼 크기 초과 - {current_memory} bytes")
												self._handle_buffer_overflow(stream_key)
												return

										# 오디오 데이터 추가
										try:
												stream_info['audio_data'].extend(audio_data)
										except Exception as extend_error:
												print(f"오디오 데이터 추가 실패: {extend_error}")
												return

										stream_info['sequence'] = sequence
										stream_info['packet_count'] += 1

										print(f"버퍼 상태 - 현재크기: {len(stream_info['audio_data'])}, "
													f"목표크기: {stream_info['current_buffer_size']}, "
													f"내선통화: {stream_info['is_internal_call']}")

										# 버퍼 크기 체크 및 WAV 파일 쓰기
										if len(stream_info['audio_data']) >= stream_info['current_buffer_size']:
												try:
														self._write_to_wav(stream_key, payload_type)
												except Exception as write_error:
														print(f"WAV 파일 쓰기 실패: {write_error}")
														return

												try:
														self._adjust_buffer_size(stream_info)
												except Exception as adjust_error:
														print(f"버퍼 크기 조정 실패: {adjust_error}")

								except Exception as process_error:
										print(f"패킷 처리 중 오류: {process_error}")
										print(traceback.format_exc())

				except Exception as lock_error:
						print(f"스트림 락 획득 실패: {lock_error}")
						print(traceback.format_exc())

		def _log_sequence_discontinuity(self, stream_key, expected, actual):
				try:
						with open('sequence_errors.log', 'a') as f:
								timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
								f.write(f"[{timestamp}] 스트림: {stream_key}, 예상: {expected}, 실제: {actual}\n")
				except Exception as e:
						print(f"시퀀스 오류 로깅 실패: {e}")

		def _handle_buffer_overflow(self, stream_key):
				try:
						stream_info = self.active_streams[stream_key]
						# 버퍼의 후반부만 유지
						stream_info['audio_data'] = stream_info['audio_data'][-self.max_buffer_size:]
						print(f"버퍼 오버플로우 처리 완료 - 새 크기: {len(stream_info['audio_data'])} bytes")
				except Exception as e:
						print(f"버퍼 오버플로우 처리 실패: {e}")

		def _write_to_wav(self, stream_key, payload_type):
				try:
						with self.file_locks[stream_key]:
								stream_info = self.active_streams[stream_key]
								if not stream_info['audio_data']:
										return
								print(f"WAV 쓰기 시작 - 데이터크기: {len(stream_info['audio_data'])} bytes")
								if payload_type == 8:
										decoded = audioop.alaw2lin(bytes(stream_info['audio_data']), 2)
										codec_type = "PCMA"
								else:
										decoded = audioop.ulaw2lin(bytes(stream_info['audio_data']), 2)
										codec_type = "PCMU"
								print(f"디코딩 완료 - 코덱: {codec_type}, 디코딩크기: {len(decoded)} bytes")
								amplified = audioop.mul(decoded, 2, 2.0)
								try:
										before_size = 0
										if os.path.exists(stream_info['filepath']):
												before_size = os.path.getsize(stream_info['filepath'])
												temp_filepath = stream_info['filepath'] + '.tmp'
												with wave.open(stream_info['filepath'], 'rb') as wav_read:
														params = wav_read.getparams()
														existing_frames = wav_read.readframes(wav_read.getnframes())
												with wave.open(temp_filepath, 'wb') as wav_write:
														wav_write.setparams(params)
														wav_write.writeframes(existing_frames)
														wav_write.writeframes(amplified)
												os.replace(temp_filepath, stream_info['filepath'])
										else:
												with wave.open(stream_info['filepath'], 'wb') as wav_file:
														wav_file.setnchannels(1)
														wav_file.setsampwidth(2)
														wav_file.setframerate(8000)
														wav_file.writeframes(amplified)
										after_size = os.path.getsize(stream_info['filepath'])
										print(f"WAV 파일 크기 변화: {before_size} -> {after_size} bytes (증가: {after_size - before_size} bytes)")
								except Exception as write_error:
										print(f"WAV 파일 쓰기 세부 오류: {write_error}")
										if 'temp_filepath' in locals() and os.path.exists(temp_filepath):
												os.remove(temp_filepath)
										raise
								stream_info['audio_data'] = bytearray()
				except Exception as e:
						print(f"WAV 파일 쓰기 중 오류: {e}")
						print(traceback.format_exc())

		def finalize_stream(self, stream_key):
				try:
						if stream_key not in self.active_streams:
								print(f"존재하지 않는 스트림 키: {stream_key}")
								return None
						with self.stream_locks[stream_key]:
								stream_info = self.active_streams[stream_key]
								if not stream_info['saved']:
										if stream_info['audio_data']:
												self._write_to_wav(stream_key, 8)
										stream_info['saved'] = True
								return dict(stream_info)
				except Exception as e:
						print(f"스트림 종료 중 오류: {e}")
						print(traceback.format_exc())
						return None

		def save_file_info(self, file_info):
				try:
						self.filesinfo.insert_one(file_info)
				except Exception as e:
						print(f"파일 정보 저장 실패: {e}")

def main():
		try:
					app = QApplication(sys.argv)
					app.setApplicationName("Recap Voice")
					
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
					window.show()
					
					# 바탕화면 아이콘 클릭 시 단일 인스턴스 처리
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
if __name__ == "__main__":
		main()