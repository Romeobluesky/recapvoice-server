# 표준 라이브러리
import atexit
import subprocess
import audioop
import wave
import os
import psutil
import configparser
import threading
import asyncio
import datetime
import sys
import re
import time

# 서드파티 라이브러리
import requests
import pyshark
from pydub import AudioSegment

# PySide6 라이브러리
from PySide6.QtWidgets import *
from PySide6.QtCore import *
from PySide6.QtGui import *
from PySide6.QtNetwork import *
from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices

# 로컬 모듈
from config_loader import load_config, get_wireshark_path
from voip_monitor import VoipMonitor
from packet_monitor import PacketMonitor
from wav_merger import WavMerger
from wav_chat_extractor import WavChatExtractor
from settings_popup import SettingsPopup

# MongoDB 관련 import 추가
from pymongo import MongoClient

# 종료할 프로세스 목록
processes_to_kill = ['nginx.exe', 'mongod.exe', 'node.exe','Dumpcap.exe']

def kill_processes():
    for process in processes_to_kill:
        subprocess.call(['taskkill', '/f', '/im', process])

# 프로그램 종료 시 kill_processes 함수 실행
atexit.register(kill_processes)

# 필요한 import 추가
import win32gui
import win32con
import psutil
import win32process

def resource_path(relative_path):
    """ 리소스 파일의 절대 경로를 가져오는 함수 """
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.abspath('.'), relative_path)

class PacketFlowWidget(QWidget):
	def __init__(self):
		super().__init__()
		self.setMinimumHeight(100)  # 최소 높이 설정
		self.packets = []

		self.timer = QTimer(self)
		self.timer.timeout.connect(self.update)
		self.timer.start(1000)

	def paintEvent(self, event):
		painter = QPainter(self)
		painter.setRenderHint(QPainter.Antialiasing)

		# 배경 그리기
		painter.fillRect(self.rect(), QColor("#2d2d2d"))

		# 패킷 플로우 그리기
		y_offset = 10  # 시작 위치를 10으로 변경
		for packet in self.packets:
			if y_offset >= self.height() - 10:  # 젯 높이를 넘어가 않도록 체크
				break

			# 시간 표시
			painter.setPen(Qt.white)
			painter.drawText(10, y_offset + 15, packet["time"])  # y_offset 조정

			# 패킷 라인 그리기
			painter.setPen(QPen(QColor("#18508F"), 2))
			painter.drawLine(200, y_offset + 15, self.width() - 200, y_offset + 15)  # y_offset 조정

			# 패킷 타입 표시
			painter.setPen(Qt.white)
			painter.drawText(self.width() // 2 - 50, y_offset + 10, packet["type"])  # y_offset 조정

			y_offset += 30

class Dashboard(QMainWindow):
	# Signal을 클래스 레벨에서 정의
	block_creation_signal = Signal(str)  # 내선번호를 전달하기 위한 시그널
	block_update_signal = Signal(str, str, str)  # (extension, status, received_number)

	def __init__(self):
		super().__init__()
		self.setWindowIcon(QIcon(resource_path("images/recapvoice_squere.ico")))
		self.setWindowTitle("Recap Voice")
		
		# 창이 자동으로 숨겨지지 않도록 설정
		self.setAttribute(Qt.WA_QuitOnClose, False)
		
		# Signal 연결
		self.block_creation_signal.connect(self.create_block_in_main_thread)
		self.block_update_signal.connect(self.update_block_in_main_thread)

		# SettingsPopup 인스턴스 생성
		self.settings_popup = SettingsPopup()

		# VoIP 모니터링 관련 변수 추가
		self.active_calls = {}
		self.capture_thread = None
		self.voip_timer = QTimer()
		self.voip_timer.timeout.connect(self.update_voip_status)
		self.voip_timer.start(1000)

		# 패킷 모니터링 관련 변수 추가
		self.streams = {}
		self.packet_timer = QTimer()
		self.packet_timer.timeout.connect(self.update_packet_status)
		self.packet_timer.start(1000)

		# SIP 등록 상태 추적
		self.sip_registrations = {}
		self.first_registration = False  # 변수 추가

		# RTP 패킷 카운트 변수 추가
		self.packet_get = 0

		# UI 초기화
		self._init_ui()

		# 네트워크 인터페이스 초기화 및 패킷 캡처 시작
		self.selected_interface = None
		self.load_network_interfaces()

		# 패킷 캡처 자동 시작
		QTimer.singleShot(1000, self.start_packet_capture)

		# 통화 시간 업데이트 타이머 추가
		self.duration_timer = QTimer()
		self.duration_timer.timeout.connect(self.update_call_duration)
		self.duration_timer.start(1000)  # 1초마다 업데이트

		# WavMerger와 WavChatExtractor 초기화
		self.wav_merger = WavMerger()
		self.chat_extractor = WavChatExtractor()

		# MongoDB 연결
		try:
			self.mongo_client = MongoClient('mongodb://localhost:27017/')
			self.db = self.mongo_client['packetwave']
			self.filesinfo = self.db['filesinfo']
			# print("MongoDB 연결 성공") # 이 로그 메시지 제거
		except Exception as e:
			print(f"MongoDB 연결 실패: {e}")

		# 배포 모드일 때만 콘솔창 숨김 처리
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

		# 트레이 아이콘 설정 (마지막에 수행)
		self.setup_tray_icon()
		
		# 클라이언트 서버 자동 시작
		try:
			# start.bat 실행
			subprocess.Popen(['start.bat'], shell=True)
			
			# ON 버튼 색상 변경
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
			print(f"클라이언트 서버 자동 시작 실패: {e}")
		
		# 창을 보이게 하고 활성화 (가장 마지막에 수행)
		QTimer.singleShot(100, self.ensure_window_visible)

		# 종료 시 cleanup 실행을 위한 등록
		atexit.register(self.cleanup)

		# 초기화가 끝난 후 창 최대화를 위한 타이머 설정
		QTimer.singleShot(100, self.initialize_window_state)

	def initialize_window_state(self):
		"""창 상태 초기화"""
		self.setWindowState(Qt.WindowMaximized)

	def ensure_window_visible(self):
		"""창이 확실히 보이도록 하는 메서드"""
		self.show()
		self.raise_()
		self.activateWindow()
		# WindowActive 대신 WindowMaximized 유지
		if self.windowState() != Qt.WindowMaximized:
			self.setWindowState(Qt.WindowMaximized)

	def cleanup(self):
		"""프로그램 종료 시 리소스 정리"""
		if hasattr(self, 'capture') and self.capture:
			try:
				if hasattr(self, 'loop') and self.loop and self.loop.is_running():
					self.loop.run_until_complete(self.capture.close_async())
				else:
					self.capture.close()
			except Exception as e:
				print(f"Cleanup error: {e}")

	def _init_ui(self):
		# 메인 위젯 설정
		main_widget = QWidget()
		self.setCentralWidget(main_widget)
		layout = QHBoxLayout(main_widget)
		layout.setContentsMargins(0, 0, 0, 0)
		layout.setSpacing(0)

		# 사이드바를 클래스 멤버 변수로 저장
		self.sidebar = self._create_sidebar()
		layout.addWidget(self.sidebar)

		# 메인 컨텐츠 영역
		content = QWidget()
		content_layout = QVBoxLayout(content)
		content_layout.setContentsMargins(20, 20, 20, 20)
		content_layout.setSpacing(20)
		layout.addWidget(content)

		# 상단 헤더 섹션
		header = self._create_header()
		content_layout.addWidget(header)

		# 태 정보 섹션
		status_section = self._create_status_section()
		content_layout.addLayout(status_section)

		# 전화연결 상태와 LOG LIST의 비율 조정
		line_list = self._create_line_list()
		log_list = self._create_log_list()

		# 비율 조정 및 마진 제거
		content_layout.addWidget(line_list, 80)
		content_layout.addWidget(log_list, 20)
		content_layout.setStretch(2, 80)  # line_list의 stretch factor
		content_layout.setStretch(3, 20)  # log_list의 stretch factor

		# 스타일 적용
		self._apply_styles()

		# 초기 크기 설정
		self.resize(1400, 900)

		# 설정 변경 시그널 연결
		self.settings_popup.settings_changed.connect(self.update_dashboard_settings)
		self.settings_popup.path_changed.connect(self.update_storage_path)

	def load_network_interfaces(self):
		"""사용 가능한 네트워크 인터페이스 로드"""
		try:
			interfaces = list(psutil.net_if_addrs().keys())
			# settings.ini에서 기본 인터페이스 읽기
			config = load_config()
			default_interface = config.get('Network', 'interface', fallback=interfaces[0])
			self.selected_interface = default_interface

		except Exception as e:
			print(f"네트워 인터페이스 로드 실패: {e}")

	def start_packet_capture(self):
		"""패킷 캡처 시작"""
		if not self.capture_thread or not self.capture_thread.is_alive():
			self.capture_thread = threading.Thread(
				target=self.capture_packets,
				args=(self.selected_interface,),
				daemon=True
			)
			self.capture_thread.start()

	def _create_header(self):
		header = QWidget()
		header_layout = QHBoxLayout(header)
		header_layout.setContentsMargins(10, 5, 10, 5)

		# 대표번호 섹션
		phone_section = QWidget()
		phone_layout = QHBoxLayout(phone_section)
		phone_layout.setAlignment(Qt.AlignLeft)
		phone_layout.setContentsMargins(0, 0, 0, 0)

		phone_text = QLabel("대표번호 | ")
		self.phone_number = QLabel()  # 클래스 멤버로 변경

		# settings.ini에서 대표번호 읽기
		config = configparser.ConfigParser()
		config.read('settings.ini', encoding='utf-8')
		self.phone_number.setText(config.get('Extension', 'rep_number', fallback=''))

		phone_layout.addWidget(phone_text)
		phone_layout.addWidget(self.phone_number)

		# ID CODE 섹션
		id_section = QWidget()
		id_layout = QHBoxLayout(id_section)
		id_layout.setAlignment(Qt.AlignRight)
		id_layout.setContentsMargins(0, 0, 0, 0)

		id_text = QLabel("ID CODE | ")
		self.id_code = QLabel()
		self.id_code.setText(config.get('Extension', 'id_code', fallback=''))

		id_layout.addWidget(id_text)
		id_layout.addWidget(self.id_code)

		header_layout.addWidget(phone_section, 1)
		header_layout.addWidget(id_section, 1)

		return header

	def _create_sidebar(self):
		sidebar = QWidget()
		sidebar.setObjectName("sidebar")
		sidebar.setFixedWidth(200)

		layout = QVBoxLayout(sidebar)
		layout.setContentsMargins(0, 0, 0, 0)
		layout.setSpacing(0)

		# 로고 컨테이너 추가 (마진 조정을 위한 컨테이너)
		logo_container = QWidget()
		logo_container_layout = QVBoxLayout(logo_container)
		logo_container_layout.setContentsMargins(0, 30, 0, 30)  # 위아래 30px 마진
		logo_container_layout.setSpacing(0)

		# 로고 영역
		logo_label = QLabel()
		logo_label.setAlignment(Qt.AlignCenter)
		logo_pixmap = QPixmap(resource_path("images/recapvoice_squere_w.png"))
		if not logo_pixmap.isNull():
			# 원본 이미지의 가로/세로 비율 계산
			aspect_ratio = logo_pixmap.height() / logo_pixmap.width()
			target_width = 120  # 원하는 가로 크기
			target_height = int(target_width * aspect_ratio)  # 비율에 맞는 세로 크기 계산

			scaled_logo = logo_pixmap.scaled(
				target_width,
				target_height,
				Qt.KeepAspectRatio,
				Qt.SmoothTransformation
			)
			logo_label.setPixmap(scaled_logo)

		# 로고를 컨테이너에 추가
		logo_container_layout.addWidget(logo_label)
		
		# 컨테이너를 메인 레이아웃에 추가
		layout.addWidget(logo_container)

		# 메뉴 컨테이너
		menu_container = QWidget()
		menu_layout = QVBoxLayout(menu_container)
		menu_layout.setContentsMargins(0, 0, 0, 0)
		menu_layout.setSpacing(5)

		# 버튼 생성 및 클릭 이벤트 연결
		voip_btn = self._create_menu_button("VOIP MONITOR", "images/voip_icon.png")
		voip_btn.clicked.connect(self.show_voip_monitor)  # show_voip_monitor와 연결

		packet_btn = self._create_menu_button("PACKET MONITOR", "images/packet_icon.png")
		packet_btn.clicked.connect(self.show_packet_monitor)  # show_packet_monitor와 연결

		menu_layout.addWidget(voip_btn)
		menu_layout.addWidget(packet_btn)
		menu_layout.addStretch()  # SETTING 버튼 대신 여백만 유지

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

		# 상단 IP 정보 섹션
		top_layout = QHBoxLayout()
		top_layout.setSpacing(15)

		# 네트워크 IP (1/4 비율) 공인아이피
		network_group = self._create_info_group("네트워크 IP", self.get_public_ip())
		top_layout.addWidget(network_group, 25)

		# 포트미러링 IP (1/4 비율) 내부이피
		config = configparser.ConfigParser()
		config.read('settings.ini', encoding='utf-8')
		port_mirror_ip = config.get('Network', 'ip', fallback='127.0.0.1')
		port_group = self._create_info_group("포트미러링 IP", port_mirror_ip)
		top_layout.addWidget(port_group, 25)

		# 클라이언트서버 (1/4 비율) - 위치 변경
		client_start = self._create_client_start_group()
		top_layout.addWidget(client_start, 25)

		# 환경설정 / 관리사이트 (1/4 비율) - 위치 변경
		record_start = self._create_toggle_group("환경설정 / 관리사이트")
		top_layout.addWidget(record_start, 25)

		layout.addLayout(top_layout)

		#  상태 정보 섹션
		bottom_layout = QHBoxLayout()
		bottom_layout.setSpacing(15)

		# settings.ini에서 Recording 경로 읽기
		config = configparser.ConfigParser()
		config.read('settings.ini', encoding='utf-8')
		storage_path = config.get('Recording', 'save_path', fallback='C:\\')
		drive_letter = storage_path.split(':')[0]

		# 디스크정보 섹션 (70%)
		disk_group = QGroupBox('디스크 정보')
		disk_layout = QHBoxLayout()

		self.disk_label = QLabel(f'녹취드라이버 ( {drive_letter} : ) 사용률:')
		self.progress_bar = QProgressBar()
		self.progress_bar.setFixedHeight(18)  # 프로그레스 높이 18로 설정
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

		# 회선상태 섹션 (30%)
		led_group = QGroupBox('회선 상태')
		led_layout = QHBoxLayout()
		led_layout.addWidget(self._create_led_with_text('회선 Init ', 'yellow'))
		led_layout.addWidget(self._create_led_with_text('대 기 중 ', 'blue'))
		led_layout.addWidget(self._create_led_with_text('녹 취 중 ', 'green'))
		led_group.setLayout(led_layout)
		bottom_layout.addWidget(led_group, 20)

		layout.addLayout(bottom_layout)

		# 타이머 설정
		self.timer = QTimer(self)
		self.timer.timeout.connect(self.update_disk_usage)
		self.timer.start(600000)  # 10분
		self.update_disk_usage()  # 초기 디스크 용량 표시

		return layout

	def _create_info_group(self, title, value):
		group = QGroupBox(title)
		layout = QVBoxLayout(group)
		layout.setContentsMargins(15, 20, 15, 15)

		# 레이블을 클래스 멤버 변수로 저장
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
		"""환경설정 / 관리사이트 그룹 생성"""
		group = QGroupBox(title)
		layout = QHBoxLayout(group)
		layout.setContentsMargins(15, 15, 15, 15)
		layout.setSpacing(2)

		button_container = QWidget()
		button_layout = QHBoxLayout(button_container)
		button_layout.setContentsMargins(0, 0, 0, 0)
		button_layout.setSpacing(2)

		# 환경설정 버튼
		settings_btn = QPushButton("환경설정")
		settings_btn.setObjectName("toggleOn")
		settings_btn.setCursor(Qt.PointingHandCursor)
		settings_btn.clicked.connect(self.show_settings)  # SETTING 버튼과 동일한 기능 연결

		# 관리사이트 버튼
		admin_btn = QPushButton("관리사이트이동")
		admin_btn.setObjectName("toggleOff")
		admin_btn.setCursor(Qt.PointingHandCursor)
		admin_btn.clicked.connect(self.open_admin_site)  # 새로운 기능 추가

		button_layout.addWidget(settings_btn, 1)
		button_layout.addWidget(admin_btn, 1)

		layout.addWidget(button_container)
		return group

	def _create_line_list(self):
		group = QGroupBox("전화연결 상태")
		group.setObjectName("line_list")
		#높이 값 증가
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

		# 스크롤 영역 속성
		scroll = QScrollArea()
		scroll.setWidgetResizable(True)
		scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
		scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

		# 통화 블록들을 담을 컨테이너
		self.calls_container = QWidget()
		self.calls_container.setObjectName("scrollContents")
		self.calls_layout = FlowLayout(self.calls_container, margin=0, spacing=20)

		scroll.setWidget(self.calls_container)
		layout.addWidget(scroll)

		# active_extensions 셔너리 추가 (내선번호 관리용)
		self.active_extensions = {}

		return group

	def _create_call_block(self, internal_number, received_number, duration, status):
		block = QWidget()
		block.setFixedSize(200, 150)
		block.setObjectName("callBlock")

		layout = QVBoxLayout(block)
		layout.setContentsMargins(15, 15, 15, 15)
		layout.setSpacing(0)  # 수직 간격 0으로 설정
		layout.setAlignment(Qt.AlignTop)  # 전체 내용을 상단에 정렬

		# 상단 컨테이너 (LED와 정보 포함)
		top_container = QWidget()
		top_layout = QVBoxLayout(top_container)
		top_layout.setContentsMargins(0, 0, 0, 0)
		top_layout.setSpacing(4)
		top_layout.setAlignment(Qt.AlignTop)  # 상단 정렬

		# LED 컨테이너
		led_container = QWidget()
		led_layout = QHBoxLayout(led_container)
		led_layout.setContentsMargins(0, 0, 0, 0)
		led_layout.setSpacing(4)
		led_layout.setAlignment(Qt.AlignRight)  # LED를 오른쪽으로 정렬

		if status != "대기중" and received_number:
			led_states = ["회선 초기화", "녹취중"]
		else:
			led_states = ["회선 Init", "대기중"]

		for state in led_states:
			led = self._create_led("", self._get_led_color(state))
			led_layout.addWidget(led)

		top_layout.addWidget(led_container)

		# 정보 레이아웃
		info_layout = QGridLayout()
		info_layout.setSpacing(4)
		info_layout.setContentsMargins(0, 0, 0, 0)

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
			title_label.setStyleSheet("""
				color: #888888;
				font-size: 12px;
			""")

			value_label = QLabel(value)
			value_label.setObjectName("blockValue")
			value_label.setStyleSheet("""
				color: white;
				font-size: 12px;
				font-weight: bold;
			""")

			info_layout.addWidget(title_label, idx, 0)
			info_layout.addWidget(value_label, idx, 1)

		top_layout.addLayout(info_layout)
		layout.addWidget(top_container)

		# 스타일 설정
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
			QLabel#blockValue {
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
				QLabel#blockValue {
					color: #888888;
				}
			""")
			effect = QGraphicsOpacityEffect()
			effect.setOpacity(0.6)
			block.setGraphicsEffect(effect)
		else:  # 통화중
			block.setStyleSheet(base_style + """
				QWidget#callBlock {
					background-color: #2A2A2A;
					border: 2px solid #18508F;
				}
				QLabel#blockValue {
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
		"""LED 상태별 색상 반환"""
		colors = {
			"회선 연결": "yellow",  # yellow
			"대기중": "blue",     # blue
			"녹취중": "green",     # green
		}
		return colors.get(state, "yellow")  # 기본값은 회색

	def _create_log_list(self):
		"""VoIP 모니터링 리스트 생성"""
		group = QGroupBox("LOG LIST")
		group.setMinimumHeight(200)  # 높이를 200px로 고정
		layout = QVBoxLayout(group)
		layout.setContentsMargins(15, 15, 15, 15)

		# 테이블 위젯 설정
		table = QTableWidget()
		table.setObjectName("log_list_table")  # 업데이트를 위한 객체 이름 설정
		table.setColumnCount(7)
		table.setHorizontalHeaderLabels([
			'시간', '통화 방향', '발신번호', '수신번호', '상태', '결과', 'Call-ID'
		])

		# 테이블 스타일 설정
		table.setStyleSheet("""
			QTableWidget {
				background-color: #2D2D2D;
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

		# 컬럼 너비 설정
		table.setColumnWidth(0, 150)  # 시간
		table.setColumnWidth(1, 80)   # 통화 방향
		table.setColumnWidth(2, 120)  # 발신번호
		table.setColumnWidth(3, 120)  # 수신번호
		table.setColumnWidth(4, 80)   # 상태
		table.setColumnWidth(5, 80)   # 결과
		table.setColumnWidth(6, 400)  # Call-ID

		# 테이블 설정
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
		"""회선상태 섹션용 LED (텍스트 포함)"""
		widget = QWidget()
		layout = QHBoxLayout()
		layout.setAlignment(Qt.AlignLeft)
		layout.setContentsMargins(0, 0, 0, 0)

		led = QLabel()
		led.setObjectName("led_indicator")
		led.setFixedSize(8, 8)
		led.setStyleSheet(
			f'#led_indicator {{ '
			f'background-color: {color}; '
			f'border-radius: 4px; '
			f'border: 1px solid rgba(0, 0, 0, 0.2); '
			f'}}'
		)

		# 그림자 효과 추가
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
		"""전화연결상태 블록용 LED (텍스 없음)"""
		widget = QWidget()
		layout = QHBoxLayout()
		layout.setAlignment(Qt.AlignCenter)
		layout.setContentsMargins(0, 0, 0, 0)

		led = QLabel()
		led.setObjectName("led_indicator")
		led.setFixedSize(8, 8)
		led.setStyleSheet(
			f'#led_indicator {{ '
			f'background-color: {color}; '
			f'border-radius: 4px; '
			f'border: 1px solid rgba(0, 0, 0, 0.2); '
			f'}}'
		)

		# 그자 과 추가
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
			# settings.ini에서 Recording 경로 읽
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

			#print(f"Disk usage updated for drive {drive_letter}")  # 디버깅용

		except Exception as e:
			print(f"Error updating disk info: {e}")
			self.disk_usage_label.setText(f'{drive_letter}드라이브 정보를 읽을 수 없습니다')

	# 팝업 창을 띄우는 메서드들 추가
	def show_voip_monitor(self):
		# VOIP Monitor 열기
		try:
			self.voip_window = VoipMonitor()
			# 윈도우 기본 스타일 적용
			self.voip_window.setWindowFlags(Qt.Window)  # 기본 윈도우 스타일로 설정
			self.voip_window.setAttribute(Qt.WA_QuitOnClose, False)  # 창을 닫아도 프로그램이 종료되지 않도록 설정
			self.voip_window.show()

			# 배포 모드일 때만 콘솔창 숨김 처리
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
			# PacketMonitor 시작
			self.packet_monitor = PacketMonitor()
			# 윈도우 기본 스타일 적용
			self.packet_monitor.setWindowFlags(Qt.Window)  # 기본 윈도우 스타일로 설정
			self.packet_monitor.setAttribute(Qt.WA_QuitOnClose, False)  # 창을 닫아도 프로그램이 종료되지 않도록 설정
			self.packet_monitor.show()
			
			# 배포 모드일 때만 콘솔창 숨김 처리
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
			# 기존 settings_popup 인스턴스를 사용
			self.settings_popup.show()
			print("Settings 열림")
		except Exception as e:
			print(f"Error opening Settings: {e}")
			QMessageBox.warning(self, "오류", "Settings를  수 없습니다.")

	def update_dashboard_settings(self, settings_data):
		"""설정 변경 시 대시보드 데이트"""
		try:
			# 대표번호 업데이트
			if 'Extension' in settings_data:
				self.phone_number.setText(settings_data['Extension']['rep_number'])

			# 네트워크 IP 업데이트
			if 'Network' in settings_data:
				self.ip_value.setText(settings_data['Network']['ap_ip'])

			# 포트미러링 IP 업데이트
			if 'Network' in settings_data:
				self.mirror_ip_value.setText(settings_data['Network']['ip'])

			# 디스크 정보 업데이트
			self.update_disk_usage()

		except Exception as e:
			print(f"Error updating dashboard settings: {e}")
			QMessageBox.warning(self, "오류", "대보드 업데이트 중 오류가 발생했습니다.")

	def update_storage_path(self, new_path):
		"""저장 경 변경 시 디스크 정보 업데이트"""
		try:
			# 설정 파일 업데이트
			config = configparser.ConfigParser()
			config.read('settings.ini', encoding='utf-8')
			if 'Recording' not in config:
				config['Recording'] = {}
			config['Recording']['save_path'] = new_path

			# 디스크 정보 업데이트
			self.update_disk_usage()

			#print(f"Recording path updated to: {new_path}")  # 디깅용

		except Exception as e:
			print(f"Error updating storage path: {e}")
			QMessageBox.warning(self, "오류", "저장 경로 업데이트 중 오류가 발생했습니다.")

	# 클래스 상수로 스타일 정의
	TABLE_STYLE = """
		QTableWidget::item:selected {
			background-color: #18508F;
			color: white;
		}
	"""

	def _set_table_style(self, table: QTableWidget) -> None:
		"""테이블 선택 스타일 설정을 위한 공통 메서드"""
		table.setSelectionBehavior(QTableWidget.SelectRows)
		table.setSelectionMode(QTableWidget.SingleSelection)
		table.setStyleSheet(self.TABLE_STYLE)


	@Slot(str)
	def create_waiting_block(self, extension):
		"""대기 블록 생성"""
		try:
			if not self.block_exists(extension):
				block = self._create_call_block(
					internal_number=extension,
					received_number="",
					duration="00:00:00",
					status="대기중"
				)
				self.calls_layout.addWidget(block)
				print(f"대기중 블 생성됨: {extension}")
		except Exception as e:
			print(f"대기중 블록 생성 중 오류: {e}")

	def analyze_sip_packet(self, packet):
		try:
			sip_layer = packet.sip
			call_id = sip_layer.call_id

			if hasattr(sip_layer, 'request_line'):
				request_line = str(sip_layer.request_line)
				try:
					if 'REFER' in request_line:
						print("\n=== 돌려주기 요청 감지 ===")
						print(f"Call-ID: {call_id}")
						
						# 1. 안전한 통화 정보 접근
						if call_id not in self.active_calls:
							print(f"[돌려주기] 해당 Call-ID를 찾을 수 없음: {call_id}")
							return
							
						try:
							# 2. 통화 정보 복사본 사용
							original_call = dict(self.active_calls[call_id])
							
							# 3. 필수 정보 검증
							if not all(k in original_call for k in ['to_number', 'from_number']):
								print("[돌려주기] 필수 통화 정보 누락")
								return
								
							external_number = original_call['to_number']    
							forwarding_ext = original_call['from_number']   
							
							# 4. Refer-To 헤더 안전하게 추출
							try:
								refer_to = str(sip_layer.refer_to)
								forwarded_ext = self.extract_number(refer_to.split('@')[0])
								if not forwarded_ext:
									print("[돌려주기] 유효하지 않은 Refer-To 번호")
									return
							except Exception as e:
								print(f"[돌려주기] Refer-To 추출 실패: {e}")
								return
								
							print(f"[돌려주기] 발신번호(유지): {external_number}")
							print(f"[돌려주기] 수신번호(유지): {forwarding_ext}")
							print(f"[돌려주기] 돌려받을 내선: {forwarded_ext}")
							
							# 5. 상태 업데이트를 위한 임시 딕셔너리 사용
							update_info = {
								'status': '통화중',
								'is_forwarded': True,
								'forward_to': forwarded_ext,
								'result': '돌려주기',
								'from_number': external_number,
								'to_number': forwarding_ext
							}
							
							# 6. 안전한 상태 업데이트
							with threading.Lock():  # 스레드 안전성 보장
								if call_id in self.active_calls:  # 재확인
									self.active_calls[call_id].update(update_info)
									
									# 7. 관련 통화 업데이트 (복사본 사용)
									active_calls_copy = dict(self.active_calls)
									for active_call_id, call_info in active_calls_copy.items():
										if (call_info.get('from_number') == forwarding_ext and 
											call_info.get('to_number') == forwarded_ext):
											if active_call_id in self.active_calls:  # 재확인
												self.active_calls[active_call_id].update({
													'status': '통화중',
													'result': '돌려주기'
												})
						
							print("[돌려주기] 기존 통화 상태 업데이트 완료")
							print("=== 돌려주기 처리 완료 ===\n")
							
						except Exception as refer_error:
							print(f"돌려주기 상세 처리 중 오류: {refer_error}")
							import traceback
							print(traceback.format_exc())
							# 오류 발생해도 계속 실행
							
					elif 'INVITE' in request_line:
						from_number = self.extract_number(sip_layer.from_user)
						to_number = self.extract_number(sip_layer.to_user)
						
						# 돌려주기 관련 INVITE인 경우 즉시 종료 처리
						if hasattr(self, 'refer_info') and \
						   from_number == self.refer_info.get('from_number') and \
						   to_number == self.refer_info.get('to_number'):
							self.active_calls[call_id] = {
								'start_time': datetime.datetime.now(),
								'status': '통화종료',
								'from_number': from_number,
								'to_number': to_number,
								'direction': '수신',
								'result': '돌려주기',
								'is_forwarded': True
							}
							delattr(self, 'refer_info')  # 사용 후 제거
						else:
							# 일반적인 INVITE 처리
							self.active_calls[call_id] = {
								'start_time': datetime.datetime.now(),
								'status': '시도중',
								'from_number': from_number,
								'to_number': to_number,
								'direction': '수신' if to_number.startswith(('1','2','3','4','5','6','7','8','9')) else '발신',
								'media_endpoints': []
							}
							self.update_call_status(call_id, '시도중')
					
					elif 'BYE' in request_line:
						if call_id in self.active_calls:
							self.update_call_status(call_id, '통화종료', '정상종료')
							extension = self.get_extension_from_call(call_id)
							if extension:
								self.block_update_signal.emit(extension, "대기중", "")
					
					elif 'CANCEL' in request_line:
						if call_id in self.active_calls:
							self.update_call_status(call_id, '통화종료', '발신취소')
							extension = self.get_extension_from_call(call_id)
							if extension:
								self.block_update_signal.emit(extension, "대기중", "")
				
				except Exception as request_error:
					print(f"Request Line 처리 중 오류: {request_error}")
					import traceback
					print(traceback.format_exc())
					# 오류 발생해도 계속 실행
					
			elif hasattr(sip_layer, 'status_line'):
				status_code = sip_layer.status_code
				
				if status_code == '100':
					extension = self.extract_number(sip_layer.from_user)
					if extension and len(extension) == 4 and extension[0] in ['1','2','3','4','5','6','7','8','9']:
						self.block_update_signal.emit(extension, "대기중", "")
				
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
	
		except Exception as e:
			print(f"SIP 패킷 분석 중 오류: {e}")
			import traceback
			print(traceback.format_exc())
			# 오류 발생해도 계속 실행

	def handle_new_call(self, sip_layer, call_id):
		"""새로운 통화 처리"""
		try:
			print(f"새로운 통화 처리 시작 - Call-ID: {call_id}")  # 디버그 로그

			from_number = self.extract_number(sip_layer.from_user)
			to_number = self.extract_number(sip_layer.to_user)

			print(f"발신번호: {from_number}")  # 디버그 로그
			print(f"수신번호: {to_number}")  # 디버그 로그

			self.active_calls[call_id] = {
				'start_time': datetime.datetime.now(),
				'status': '시도중',
				'from_number': from_number,
				'to_number': to_number,
				'direction': '수신' if to_number.startswith(('1','2','3','4','5','6','7','8','9')) else '발신',
				'media_endpoints': []
			}

			print(f"통화 정보 저장 완료: {self.active_calls[call_id]}")  # 디버그 로그

		except Exception as e:
			print(f"새 통화 처리 중 오류: {e}")

	def handle_call_end(self, sip_layer, call_id):
		"""통화 종료 처리"""
		if call_id in self.active_calls:
			# 통화 상태 업데이트
			self.active_calls[call_id].update({
				'status': '통화종료',
				'end_time': datetime.datetime.now(),
				'result': '정상종료'
			})

			# LOG LIST 즉시 업데이트
			self.update_voip_status()

			# 내선번호 찾기
			extension = self.get_extension_from_call(call_id)
			if extension:
				# 대기중 상태의 블록으로 강제 업데이트
				QMetaObject.invokeMethod(self,
					"update_block_to_waiting",
					Qt.QueuedConnection,
					Q_ARG(str, extension))
				print(f"통화 종료 처리: {extension}")

	def get_extension_from_call(self, call_id):
		"""통화 정보에서 내선번호 추출"""
		if call_id in self.active_calls:
			call_info = self.active_calls[call_id]
			from_number = call_info['from_number']
			to_number = call_info['to_number']

			# 내선번호 확인
			is_extension = lambda num: num.startswith(('1', '2', '3', '4', '5', '6', '7', '8', '9')) and len(num) == 4
			return from_number if is_extension(from_number) else to_number if is_extension(to_number) else None
		return None

	def handle_call_cancel(self, call_id):
		"""통화 취소 처리"""
		if call_id in self.active_calls:
			self.active_calls[call_id].update({
				'status': '통화종료',
				'end_time': datetime.datetime.now(),
				'result': '발신취소'
			})

	def update_voip_status(self):
		"""VoIP 상태 업데이트 (LOG LIST 섹션)"""
		try:
			table = self.findChild(QTableWidget, "log_list_table")
			if not table:
				return

			# active_calls를 시간 기준으로 정렬 (최신순)
			sorted_calls = sorted(
				self.active_calls.items(),
				key=lambda x: x[1]['start_time'],
				reverse=True  # 최신 항목이 위로 오도록 reverse=True 설정
			)

			# 테이블 내용 초기화
			table.setRowCount(0)
			table.setRowCount(len(sorted_calls))

			# 정렬된 순서대로 테이블에 추가
			for row, (call_id, call_info) in enumerate(sorted_calls):
				time_item = QTableWidgetItem(call_info['start_time'].strftime('%Y-%m-%d %H:%M:%S'))
				direction_item = QTableWidgetItem(call_info.get('direction', ''))
				from_item = QTableWidgetItem(str(call_info.get('from_number', '')))
				to_item = QTableWidgetItem(str(call_info.get('to_number', '')))
				status_item = QTableWidgetItem(call_info.get('status', ''))
				result_item = QTableWidgetItem(call_info.get('result', ''))
				callid_item = QTableWidgetItem(call_id)

				items = [time_item, direction_item, from_item, to_item,
						status_item, result_item, callid_item]

				for col, item in enumerate(items):
					item.setTextAlignment(Qt.AlignCenter)
					table.setItem(row, col, item)

			# 테이블 즉시 업데이트
			table.viewport().update()

		except Exception as e:
			print(f"VoIP 상태 업데이트 중 오류: {e}")

	def update_packet_status(self):
		"""패킷 상태 업데이트"""
		try:
			# 필요 경우에만 업데이트
			for call_id, call_info in self.active_calls.items():
				if call_info.get('status_changed', False):
					extension = self.get_extension_from_call(call_id)
					if extension:
						self.create_waiting_block(extension)
					call_info['status_changed'] = False
		except Exception as e:
			print(f"패킷 상태 업데이트 중 오류: {e}")

	def calculate_duration(self, call_info):
		"""통화 시간 계산"""
		if 'start_time' in call_info:
			if 'end_time' in call_info:
				duration = call_info['end_time'] - call_info['start_time']
			else:
				duration = datetime.datetime.now() - call_info['start_time']
			return str(duration).split('.')[0]
		return "00:00:00"

	def is_rtp_packet(self, packet):
		"""RTP 패킷 검증"""
		try:
			if not hasattr(packet, 'udp') or not hasattr(packet.udp, 'payload'):
				return False

			# UDP 페이로드를 hex로 변환
			payload_hex = packet.udp.payload.replace(':', '')

			try:
				payload = bytes.fromhex(payload_hex)
			except ValueError:
				return False

			if len(payload) < 12:  # RTP 헤더 최소 크기
				return False

			# RTP 버전 확인 (첫 2비트가 2여야 함)
			version = (payload[0] >> 6) & 0x03
			if version != 2:
				return False

			# 페이로드 타입 확인 (오디오 코덱)
			payload_type = payload[1] & 0x7F

			# 디버그 정보 출력
			#print(f"RTP 패킷 검사: Version={version}, PayloadType={payload_type}")

			# PCMU(0)와 PCMA(8)만 허용
			return payload_type in [0, 8]

		except Exception as e:
			print(f"RTP 패킷 확인 중 오류: {e}")
			return False

	def determine_stream_direction(self, packet, call_id):
		"""RTP 패킷의 방향 결정"""
		try:
			if call_id not in self.active_calls:
				return None

			call_info = self.active_calls[call_id]
			
			# media_endpoints 초기화
			if 'media_endpoints' not in call_info:
				call_info['media_endpoints'] = []
			if 'media_endpoints_set' not in call_info:
				call_info['media_endpoints_set'] = {
					'local': set(),
					'remote': set()
				}

			src_ip = packet.ip.src
			dst_ip = packet.ip.dst
			
			# Call-ID에서 IP 주소 추출 (안전하게 처리)
			try:
				pbx_ip = call_id.split('@')[1].split(';')[0].split(':')[0]
			except:
				print(f"PBX IP 추출 실패 - Call-ID: {call_id}")
				return None
				
			src_endpoint = f"{src_ip}:{packet.udp.srcport}"
			dst_endpoint = f"{dst_ip}:{packet.udp.dstport}"

			# 소스가 PBX IP인 경우 = OUT
			if src_ip == pbx_ip:
				# 기존 리스트에 추가
				endpoint_info = {"ip": src_ip, "port": packet.udp.srcport}
				if endpoint_info not in call_info['media_endpoints']:
					call_info['media_endpoints'].append(endpoint_info)
				# 새로운 세트에 추가
				call_info['media_endpoints_set']['local'].add(src_endpoint)
				call_info['media_endpoints_set']['remote'].add(dst_endpoint)
				print(f"OUT 패킷: {src_endpoint} -> {dst_endpoint}")
				return "OUT"
				
			# 목적지가 PBX IP인 경우 = IN
			elif dst_ip == pbx_ip:
				# 기존 리스트에 추가
				endpoint_info = {"ip": dst_ip, "port": packet.udp.dstport}
				if endpoint_info not in call_info['media_endpoints']:
					call_info['media_endpoints'].append(endpoint_info)
				# 새로운 세트에 추가
				call_info['media_endpoints_set']['local'].add(dst_endpoint)
				call_info['media_endpoints_set']['remote'].add(src_endpoint)
				print(f"IN 패킷: {src_endpoint} -> {dst_endpoint}")
				return "IN"
			
			# 이미 알고 있는 엔드포인트를 기반으로 방향 결정
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
			import traceback
			print(traceback.format_exc())
			return None

	def extract_number(self, sip_user):
		"""SIP User 필드에서 전화번호 추출"""
		try:
			if not sip_user:
				return ''

			sip_user = str(sip_user)

			# sip: 제거 및 전체 번호 추출
			if 'sip:' in sip_user:
				number = sip_user.split('sip:')[1].split('@')[0]
				return ''.join(c for c in number if c.isdigit())

			# 109 다음에 오는 알파벳 문자로 분리
			if '109' in sip_user:
				for i, char in enumerate(sip_user):
					if i > sip_user.index('109') + 2 and char.isalpha():
						return sip_user[i+1:]  # 알파벳 다음의 숫자들만 반환

			# 그 외의 경우 숫자만 추출하여 반환
			return ''.join(c for c in sip_user if c.isdigit())

		except Exception as e:
			print(f"전화번호 추출 중 오류: {e}")
			return ''

	def get_call_id_from_rtp(self, packet):
		"""RTP 패킷과 관련된 Call-ID 찾기"""
		try:
			src_ip = packet.ip.src
			dst_ip = packet.ip.dst
			src_port = int(packet.udp.srcport)
			dst_port = int(packet.udp.dstport)
			
			src_endpoint = f"{src_ip}:{src_port}"
			dst_endpoint = f"{dst_ip}:{dst_port}"

			# active_calls에서 이 RTP 스트림과 매칭되는 Call-ID 찾기
			for call_id, call_info in self.active_calls.items():
				if "media_endpoints_set" in call_info:  # 새로운 구조 사용
					if (src_endpoint in call_info["media_endpoints_set"]["local"] or 
						src_endpoint in call_info["media_endpoints_set"]["remote"] or
						dst_endpoint in call_info["media_endpoints_set"]["local"] or
						dst_endpoint in call_info["media_endpoints_set"]["remote"]):
						return call_id
				# 기존 구조도 체크
				elif "media_endpoints" in call_info:
					for endpoint in call_info["media_endpoints"]:
						if (src_ip == endpoint.get("ip") and src_port == endpoint.get("port")) or \
						   (dst_ip == endpoint.get("ip") and dst_port == endpoint.get("port")):
							return call_id
			return None

		except Exception as e:
			print(f"RTP Call-ID 매칭 오류: {e}")
			import traceback
			print(traceback.format_exc())
			return None

	def handle_sip_response(self, status_code, call_id, sip_layer):
		"""SIP Response 처리"""
		try:
			if hasattr(sip_layer, 'from'):
				ip = None
				if '@' in call_id:
					ip = call_id.split('@')[1]

				if ip:
					extension = self.extract_number(sip_layer.from_user)

					if ip not in self.sip_registrations:
						self.sip_registrations[ip] = {
							'status': [],
							'extension': extension
						}

					# 상태 코드 추가
					self.sip_registrations[ip]['status'].append(status_code)

					# 100->401->200 시퀀스 확인
					if len(self.sip_registrations[ip]['status']) >= 3:
						recent_status = self.sip_registrations[ip]['status'][-3:]
						if '100' in recent_status and '401' in recent_status and '200' in recent_status:
							# 대기중 블록 생성
							QMetaObject.invokeMethod(self,
								"create_waiting_block",
								Qt.QueuedConnection,
								Q_ARG(str, extension))
							self.handle_first_registration()

			# 통화 상태 업데이트
			if call_id in self.active_calls:
				if status_code == '200':  # OK
					self.active_calls[call_id]['status'] = '통화중'
				elif status_code == '180':  # Ringing
					self.active_calls[call_id]['status'] = '벨울림'

		except Exception as e:
			print(f"SIP 응답 처리 중 오류: {e}")

	def create_or_update_block(self, extension):
		"""내선번호 블록 생성 또는 업데이트"""
		# 시그널을 통해 메인 스레드에서 처리
		self.block_creation_signal.emit(extension)

	def block_exists(self, extension_number):
		"""특정 내선번호의 블록이 이미 존재하는 확인"""
		try:
			for i in range(self.calls_layout.count()):
				block = self.calls_layout.itemAt(i).widget()
				if block:
					for child in block.findChildren(QLabel):
						if child.objectName() == "blockValue" and child.text() == extension_number:
							return True
			return False
		except Exception as e:
			print(f"블록 존재 여부 확인 중 오류: {e}")
			return False

	def create_block_in_main_thread(self, extension):
		"""메인 스레드에서 블록 생성"""
		try:
			if not self.block_exists(extension):
				block = self._create_call_block(
					internal_number=extension,
					received_number="",
					duration="00:00:00",
					status="대기중"
				)
				self.calls_layout.addWidget(block)
				print(f"블록 생성됨 (메인 스레드): {extension}")

				# 레이아웃 업데이트
				self.calls_layout.update()
				self.calls_container.update()
		except Exception as e:
			print(f"메인 스레드 블록 생성 중 오류: {e}")

	def update_block_to_waiting(self, extension):
		"""블록을 대기중 상태로 업데이트"""
		try:
			# 기존 블록 제거
			for i in range(self.calls_layout.count()-1, -1, -1):
				block = self.calls_layout.itemAt(i).widget()
				if block:
					for child in block.findChildren(QLabel):
						if child.objectName() == "blockValue" and child.text() == extension:
							self.calls_layout.removeWidget(block)
							block.deleteLater()

			# 새로운 대기중 블록 생성
			new_block = self._create_call_block(
				internal_number=extension,
				received_number="",
				duration="00:00:00",
				status="대기중"
			)
			self.calls_layout.addWidget(new_block)

			# 레이아웃 강제 업데이트
			self.calls_layout.update()
			self.calls_container.update()
			print(f"블록 강제 업데이트 완료: {extension} -> 대기중")

			# LOG LIST 업데이트 강제 실행
			self.update_voip_status()

		except Exception as e:
			print(f"블록 강제 업데이트  오류: {e}")

	def check_registration(self):
		"""SIP 등록 상태 확인"""
		try:
			for ip, reg_info in self.sip_registrations.items():
				if reg_info['status'] and '200' in reg_info['status']:
					self.loading_overlay.hide()
					self.loading_timer.stop()
					return
		except Exception as e:
			print(f"등록 상태 확인 중 오류: {e}")

	def force_hide_loading(self):
		"""30초 후 강제로 로딩 화면 숨김"""
		if hasattr(self, 'loading_overlay') and self.loading_overlay.isVisible():
			self.loading_overlay.hide()
			if hasattr(self, 'loading_timer'):
				self.loading_timer.stop()
			print("로딩 화면 타임아웃으로 종료")

	def force_update_block(self, extension):
		"""강제로 블록 상태 업데이트"""
		try:
			# 기존 블록 모두 제거
			for i in range(self.calls_layout.count()-1, -1, -1):
				block = self.calls_layout.itemAt(i).widget()
				if block:
					for child in block.findChildren(QLabel):
						if child.objectName() == "blockValue" and child.text() == extension:
							self.calls_layout.removeWidget(block)
							block.deleteLater()

			# 새로운 대기중 블록 생성
			new_block = self._create_call_block(
				internal_number=extension,
				received_number="",
				duration="00:00:00",
				status="대기중"
			)
			self.calls_layout.addWidget(new_block)

			# 레이아웃 강제 업데이트
			self.calls_layout.update()
			self.calls_container.update()
			print(f"블록 강제 업데이트 완료: {extension} -> 대기중")

			# LOG LIST 업데이트 강제 실행
			self.update_voip_status()

		except Exception as e:
			print(f"블록 강제 업데이트  오류: {e}")

	def update_block_in_main_thread(self, extension, status, received_number):
		"""메인 스레드에서 블록 업데이트 (시그널로 호출됨)"""
		try:
			# 기존 블록 제거
			for i in range(self.calls_layout.count()-1, -1, -1):
				block = self.calls_layout.itemAt(i).widget()
				if block:
					for child in block.findChildren(QLabel):
						if child.objectName() == "blockValue" and child.text() == extension:
							self.calls_layout.removeWidget(block)
							block.deleteLater()

			# active_calls에서 해당 extension의 call_id 찾기
			call_id = None
			for cid, call_info in self.active_calls.items():
				if self.get_extension_from_call(cid) == extension:
					call_id = cid
					break

			# 통화 시간 계산
			duration = "00:00:00"
			if call_id and status == "통화중":
				duration = self.calculate_duration(self.active_calls[call_id])

			# 새 블록 생성
			new_block = self._create_call_block(
				internal_number=extension,
				received_number=received_number,
				duration=duration,
				status=status
			)
			self.calls_layout.addWidget(new_block)

			# 레이아웃 업데이트
			self.calls_layout.update()
			self.calls_container.update()

		except Exception as e:
			print(f"블록 업데이트 중 오류: {e}")

	def update_call_status(self, call_id, new_status, result=''):
		"""통화 상태 업데이트"""
		try:
			if call_id in self.active_calls:
				self.active_calls[call_id].update({
					'status': new_status,
					'result': result
				})

				if new_status == '통화종료':
					self.active_calls[call_id]['end_time'] = datetime.datetime.now()

					# 스트림 종료 처리
					if hasattr(self, 'stream_manager'):
						stream_info_in = None
						stream_info_out = None
						
						# IN 스트림 종료
						in_key = f"{call_id}_IN"
						if in_key in self.stream_manager.active_streams:
							stream_info_in = self.stream_manager.finalize_stream(in_key)
						
						# OUT 스트림 종료
						out_key = f"{call_id}_OUT"
						if out_key in self.stream_manager.active_streams:
							stream_info_out = self.stream_manager.finalize_stream(out_key)

						# WAV 파일 병합 및 HTML 생성
						if stream_info_in and stream_info_out:
							try:
								file_dir = stream_info_in['file_dir']
								timestamp = os.path.basename(file_dir)
								local_num = self.active_calls[call_id]['from_number']
								remote_num = self.active_calls[call_id]['to_number']

								# WAV 파일 병합
								merged_file = self.wav_merger.merge_and_save(
									stream_info_in['phone_ip'],
									timestamp,
									timestamp,
									local_num,
									remote_num,
									stream_info_in['filepath'],
									stream_info_out['filepath'],
									file_dir
								)

								if merged_file:
									# HTML 생성
									html_file = self.chat_extractor.extract_chat_to_html(
										stream_info_in['phone_ip'],
										timestamp,
										timestamp,
										local_num,
										remote_num,
										stream_info_in['filepath'],
										stream_info_out['filepath'],
										file_dir
									)

									if html_file:
										# MongoDB에 정보 저장
										self._save_to_mongodb(
											merged_file, html_file, 
											local_num, remote_num
										)

										# 모든 작업이 성공적으로 완료된 후 IN/OUT 파일 삭제
										try:
											if os.path.exists(stream_info_in['filepath']):
												os.remove(stream_info_in['filepath'])
											if os.path.exists(stream_info_out['filepath']):
												os.remove(stream_info_out['filepath'])
										except Exception as e:
											print(f"파일 삭제 중 오류: {e}")

							except Exception as e:
								print(f"파일 처리 중 오류: {e}")

				# 내선번호 찾기 및 블록 상태 업데이트
				extension = self.get_extension_from_call(call_id)
				if extension:
					self.block_update_signal.emit(extension, "대기중", "")

			# LOG LIST 업데이트
			self.update_voip_status()

		except Exception as e:
			print(f"통화 상태 업데이트 중 오류: {e}")

	@Slot()
	def handle_first_registration(self):
		"""첫 번 SIP 등록 감지 시 처리"""
		try:
			if not self.first_registration:
				self.first_registration = True
				print("첫 번째 SIP 등록 완료")
		except Exception as e:
			print(f"첫 번째 등록 처리 중 오류: {e}")

	def capture_packets(self, interface):
		"""패킷 캡처 및 분석"""
		capture = None
		loop = None
		
		try:
			# 새로운 이벤트 루프 생성
			loop = asyncio.new_event_loop()
			asyncio.set_event_loop(loop)

			# 캡처 객체 생성
			capture = pyshark.LiveCapture(
				interface=interface,
				display_filter='sip or (udp and (udp.port >= 10000 and udp.port <= 20000))'
			)
			capture.set_debug()

			print(f"패킷 캡처 감시 시작 - Interface: {interface}")

			if not interface:
				print("Error: 선택된 인터페이스가 없습니다")
				return

			# 패킷 캡처 및 처리
			for packet in capture.sniff_continuously():
				try:
					if 'SIP' in packet:
						self.analyze_sip_packet(packet)
					elif 'UDP' in packet and self.is_rtp_packet(packet):
						print("\nRTP 패킷 감지됨")
						self.handle_rtp_packet(packet)
				except Exception as packet_error:
					print(f"패킷 처리 중 오류: {packet_error}")
					continue

		except KeyboardInterrupt:
			print("패킷 캡처 중단됨")
		except Exception as e:
			print(f"패킷 캡처 중 오류: {e}")
			import traceback
			print(traceback.format_exc())
		finally:
			# 캡처 객체 정리
			if capture:
				try:
					# 비동기 종료 처리를 동기적으로 실행
					if loop and not loop.is_closed():
						async def close_capture():
							await capture.close_async()
						try:
							loop.run_until_complete(close_capture())
						except Exception:
							capture.close()
					else:
						capture.close()
				except Exception as close_error:
					print(f"캡처 종료 중 오류: {close_error}")

			# 이벤트 루프 정리
			if loop and not loop.is_closed():
				try:
					# 실행 중인 작업 완료 대기
					pending = asyncio.all_tasks(loop) if hasattr(asyncio, 'all_tasks') else []
					for task in pending:
						try:
							loop.run_until_complete(task)
						except Exception:
							pass
					
					loop.close()
				except Exception as loop_error:
					print(f"이벤트 루프 종료 중 오류: {loop_error}")

	def handle_rtp_packet(self, packet):
		"""RTP 패킷 처리"""
		try:
			# RTP 스트림 매니저가 없으면 생성
			if not hasattr(self, 'stream_manager'):
				self.stream_manager = RTPStreamManager()

			# 현재 활성화된 통화 중에서 '통화중' 상태인 것들 찾기
			active_calls = []
			for call_id, call_info in self.active_calls.items():
				if call_info.get('status') == '통화중':
					active_calls.append((call_id, call_info))

			if not active_calls:
				return

			# 각 활성 통화에 대해 처리
			for call_id, call_info in active_calls:
				try:
					# Call-ID에서 IP 주소 추출
					phone_ip = call_id.split('@')[1]
					
					# 스트림 방향 결정
					direction = self.determine_stream_direction(packet, call_id)
					if not direction:
						continue  # 방향 결정 실패 시 다음 통화로

					# UDP 페이로드 분석
					if hasattr(packet.udp, 'payload'):
						payload_hex = packet.udp.payload.replace(':', '')
						try:
							payload = bytes.fromhex(payload_hex)
							version = (payload[0] >> 6) & 0x03
							payload_type = payload[1] & 0x7F
							sequence = int.from_bytes(payload[2:4], byteorder='big')
							audio_data = payload[12:]  # RTP 헤더 제외

							if len(audio_data) == 0:
								continue  # 오디오 데이터가 없는 경우 스킵

							# 스트림 생성 또는 가져오기
							stream_key = self.stream_manager.create_stream(
								call_id, direction, call_info, phone_ip
							)
							
							if stream_key:
								# 패킷 처리
								self.stream_manager.process_packet(
									stream_key, audio_data, sequence, payload_type
								)

						except Exception as e:
							print(f"페이로드 분석 오류: {e}")
							continue

				except Exception as e:
					print(f"통화 처리 중 오류: {e}")
					continue

		except Exception as e:
			print(f"RTP 패킷 처리 중 오류: {e}")
			import traceback
			print(traceback.format_exc())  # 상세한 오류 정보 출력

	def save_wav_file(self, filepath, audio_data, payload_type):
		"""WAV 파일 저장"""
		try:
			if len(audio_data) == 0:
				print("오디오 데이터가 없습니다.")
				return

			# WAV 파일 설정
			with wave.open(filepath, 'wb') as wav_file:
				wav_file.setnchannels(1)  # 모노
				wav_file.setsampwidth(2)  # 16-bit
				wav_file.setframerate(8000)  # 8kHz

				# PCMA(8) 또는 PCMU(0) 디코딩
				if payload_type == 8:  # PCMA (A-law)
					decoded_data = audioop.alaw2lin(bytes(audio_data), 2)
				else:  # PCMU (μ-law)
					decoded_data = audioop.ulaw2lin(bytes(audio_data), 2)

				# 볼륨 증가
				amplified_data = audioop.mul(decoded_data, 2, 4.0)

				wav_file.writeframes(amplified_data)
				print(f"WAV 파일 저장 완료: {filepath}")
				print(f"원본 데이터 크기: {len(audio_data)} bytes")
				print(f"디코딩된 데이터 크기: {len(decoded_data)} bytes")
				print(f"최종 데이터 크기: {len(amplified_data)} bytes")

		except Exception as e:
			print(f"WAV 파일 저장 중 오류: {e}")

	def decode_alaw(self, audio_data):
		"""A-law 디코딩"""
		try:
			return audioop.alaw2lin(audio_data, 2)
		except Exception as e:
			print(f"A-law 디코딩 오류: {e}")
			return audio_data

	def decode_ulaw(self, audio_data):
		"""μ-law 디코딩"""
		try:
			return audioop.ulaw2lin(audio_data, 2)
		except Exception as e:
			print(f"μ-law 디코딩 오류: {e}")
			return audio_data

	def update_call_duration(self):
		"""통화 시간 업데이트"""
		try:
			for call_id, call_info in self.active_calls.items():
				if call_info.get('status') == '통화중':
					extension = self.get_extension_from_call(call_id)
					if extension:
						duration = self.calculate_duration(call_info)
						# 블록 업데이트 (통화중 상태와 시간 표시)
						self.block_update_signal.emit(extension, "통화중", call_info['to_number'])

						# 블록의 시간 레이블 업데이트
						for i in range(self.calls_layout.count()):
							block = self.calls_layout.itemAt(i).widget()
							if block:
								for child in block.findChildren(QLabel):
									if child.objectName() == "blockValue" and child.text() == extension:
										# 시간 레이블 찾기
										for label in block.findChildren(QLabel):
											if label.objectName() == "durationLabel":
												label.setText(duration)
												break
										break
		except Exception as e:
			print(f"통화 시간 업데이트 중 오류: {e}")

	def _create_client_start_group(self):
		"""클라이언트서버 그룹 생성"""
		group = QGroupBox("클라이언트서버")
		layout = QHBoxLayout(group)
		layout.setContentsMargins(15, 20, 15, 15)
		layout.setSpacing(2)

		# 버튼 컨테이너
		button_container = QWidget()
		button_layout = QHBoxLayout(button_container)
		button_layout.setContentsMargins(0, 0, 0, 0)
		button_layout.setSpacing(2)

		# ON/OFF 버튼 순서 변경
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
		"""start.bat 실행 및 ON 버튼 색상 변경"""
		try:
			# start.bat 실행
			import subprocess
			subprocess.Popen(['start.bat'], shell=True)

			# ON 버튼 색상 변경
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
		"""start.bat 중지 및 ON 버튼 색상 원복"""
		try:
			# 종료할 프로세스 목록
			processes_to_kill = ['nginx.exe', 'mongod.exe', 'node.exe','Dumpcap.exe']

			# 각 프로세스 종료
			import os
			for process in processes_to_kill:
				os.system(f'taskkill /f /im {process}')
				print(f"프로세스 종료 시도: {process}")

			# ON 버튼 색상 원복
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
		"""Call-ID에서 IP 주소 추출"""
		try:
			# @ 뒤의 문자열 추출
			ip_part = call_id.split('@')[1]

			# 가능한 모든 형식 처리
			# 1. IP:포트;파라미터 형식 (예: 192.168.0.10:5060;transport=udp)
			# 2. [IP]:포트 형식 (예: [192.168.0.10]:5060)
			# 3. IP:포트 형식 (예: 192.168.0.10:5060)
			# 4. 순수 IP 형식 (예: 192.168.0.10)

			# 세미콜론 이후 제거
			ip_part = ip_part.split(';')[0]

			# 대괄호 제거
			ip_part = ip_part.replace('[', '').replace(']', '')

			# 포트 부분 제거
			ip_part = ip_part.split(':')[0]

			# IP 주소 유효성 검사 (옵션)
			if self.is_valid_ip(ip_part):
				return ip_part
			else:
				print(f"유효하지 않은 IP 주소 형식: {ip_part}")
				return "unknown"

		except Exception as e:
			print(f"IP 주소 추출 실패. Call-ID: {call_id}, 오류: {e}")
			return "unknown"

	def is_valid_ip(self, ip):
		"""IP 주소 유효성 검사"""
		try:
			# IPv4 형식 검사
			parts = ip.split('.')
			if len(parts) != 4:
				return False
			return all(0 <= int(part) <= 255 for part in parts)
		except:
			return False

	def open_admin_site(self):
		"""관리사이트 열기"""
		try:
			# settings.ini에서 IP 주소 읽기
			config = configparser.ConfigParser()
			config.read('settings.ini', encoding='utf-8')
			ip_address = config.get('Network', 'ip', fallback='127.0.0.1')

			# URL 생성 및 웹브라우저로 열기
			url = f"http://{ip_address}:3000"
			QDesktopServices.openUrl(QUrl(url))
		except Exception as e:
			print(f"관리사이트 열기 실패: {e}")
			QMessageBox.warning(self, "오류", "관리사이트를 열 수 없습니다.")

	def _save_to_mongodb(self, merged_file, html_file, local_num, remote_num):
		try:
			# 현재 저장된 최대 id 값 조회
			max_id_doc = self.filesinfo.find_one(
				sort=[("id", -1)]  # id 필드 기준 내림차순 정렬
			)
			next_id = 1 if max_id_doc is None else max_id_doc["id"] + 1
			# 한국 시간으로 변환
			now_kst = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9)))
			# 재생 시간 계산
			audio = AudioSegment.from_wav(merged_file)
			duration_seconds = int(len(audio) / 1000.0)  # milliseconds to seconds
			
			# HH:MM:SS 형식으로 포맷팅
			hours = duration_seconds // 3600
			minutes = (duration_seconds % 3600) // 60
			seconds = duration_seconds % 60
			duration_formatted = f"{hours:02d}:{minutes:02d}:{seconds:02d}"

			filesize = os.path.getsize(merged_file)
			doc = {
				"id": next_id,                    # 자동 증가 ID
				"user_id": local_num,             # 내선번호
				"filename": merged_file,          # 병합된 WAV 파일 전체 경로
				"from_number": local_num,         # 발신번호
				"to_number": remote_num,          # 수신번호
				"filesize": str(filesize),        # 파일 크기를 문자열로 저장
				"filestype": "wav",               # 파일 타입
				"files_text": html_file,          # HTML 파일 전체 경로
				"down_count": 0,                  # 다운로드 카운트 초기값
				"created_at": now_kst,  # utcnow() 대신 now(UTC) 사용
				"playtime": duration_formatted,   # "00:00:00" 형식으로 저장
			}

			result = self.filesinfo.insert_one(doc)
			print(f"MongoDB 저장 완료: {result.inserted_id} (재생시간: {duration_formatted})")
			
		except Exception as e:
			print(f"MongoDB 저장 중 오류: {e}")

	def setup_tray_icon(self):
		"""트레이 아이콘 설정"""
		try:
			# 트레이 아이콘 생성
			self.tray_icon = QSystemTrayIcon(self)
			
			# 아이콘 설정
			app_icon = QIcon()
			app_icon.addFile(resource_path("images/recapvoice_squere.ico"), QSize(16, 16))
			app_icon.addFile(resource_path("images/recapvoice_squere.ico"), QSize(24, 24))
			app_icon.addFile(resource_path("images/recapvoice_squere.ico"), QSize(32, 32))
			app_icon.addFile(resource_path("images/recapvoice_squere.ico"), QSize(48, 48))
			
			# 아이콘이 없는 경우 기본 앱 아이콘 사용
			if app_icon.isNull():
				app_icon = QApplication.style().standardIcon(QStyle.SP_ComputerIcon)
				print("아이콘 파일을 찾을 수 없습니다: images/recapvoice_squere.ico")
			
			self.tray_icon.setIcon(app_icon)
			self.setWindowIcon(app_icon)  # 윈도우 아이콘도 설정
			
			# 트레이 메뉴 생성
			tray_menu = QMenu()
			
			# Recap Voice 열기 액션
			open_action = QAction("Recap Voice 열기", self)
			open_action.triggered.connect(self.show_window)
			tray_menu.addAction(open_action)
			
			# 환경 설정 액션
			settings_action = QAction("환경 설정", self)
			settings_action.triggered.connect(self.show_settings)
			tray_menu.addAction(settings_action)
			
			# 구분선 추가
			tray_menu.addSeparator()
			
			# 종료 액션
			quit_action = QAction("종료", self)
			quit_action.triggered.connect(self.quit_application)
			tray_menu.addAction(quit_action)
			
			# 메뉴 설정
			self.tray_icon.setContextMenu(tray_menu)
			
			# 툴팁 설정
			self.tray_icon.setToolTip("Recap Voice")
			
			# 트레이 아이콘 표시
			self.tray_icon.show()
			
			# 트레이 아이콘 더블클릭 이벤트 연결
			self.tray_icon.activated.connect(self.tray_icon_activated)
			
		except Exception as e:
			print(f"트레이 아이콘 설정 중 오류: {e}")
			import traceback
			print(traceback.format_exc())

	def closeEvent(self, event):
		"""창 닫기 이벤트 처리"""
		if self.tray_icon.isVisible():
			event.ignore()  # 기본 종료 동작 무시
			self.hide()     # 창 숨기기
			
			# 트레이로 최소화 알림
			self.tray_icon.showMessage(
				"Recap Voice",
				"프로그램이 트레이로 최소화되었습니다.",
				QSystemTrayIcon.Information,
				2000
			)

	def show_window(self):
		"""창 보이기"""
		self.show()
		self.activateWindow()

	def show_settings(self):
		"""환경 설정 창 표시"""
		try:
			settings_dialog = SettingsPopup(self)
			settings_dialog.exec()
		except Exception as e:
			print(f"설정 창 표시 중 오류: {e}")

	def quit_application(self):
		"""프로그램 종료"""
		try:
			# 트레이 아이콘 제거
			self.tray_icon.hide()
			
			# 프로그램 종료
			QApplication.quit()
		except Exception as e:
			print(f"프로그램 종료 중 오류: {e}")

	def tray_icon_activated(self, reason):
		"""트레이 아이콘 활성화 이벤트 처리"""
		if reason == QSystemTrayIcon.DoubleClick:
			self.show_window()

# FlowLayout 래스 추가 (Qt의 동적 그리 레이아웃 구현)
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

# RTP 스트림 관리를 위한 클래스 수정
class RTPStreamManager:
    def __init__(self):
        self.active_streams = {}  # {stream_key: StreamInfo}
        self.stream_locks = {}    # 스트림별 락
        self.file_locks = {}      # 파일 쓰기용 락
        # 버퍼 관련 설정 추가
        self.min_buffer_size = 4000   # 최소 버퍼 크기 (0.5초)
        self.max_buffer_size = 16000  # 최대 버퍼 크기 (2초)
        self.buffer_adjust_threshold = 0.8  # 버퍼 조정 임계값
        
    def get_stream_key(self, call_id, direction):
        """고유한 스트림 키 생성"""
        return f"{call_id}_{direction}"
        
    def create_stream(self, call_id, direction, call_info, phone_ip):
        """새로운 RTP 스트림 생성"""
        try:
            stream_key = self.get_stream_key(call_id, direction)
            
            if stream_key not in self.active_streams:
                self.stream_locks[stream_key] = threading.Lock()
                self.file_locks[stream_key] = threading.Lock()
                
                # 설정 파일 읽기
                config = configparser.ConfigParser()
                config.read('settings.ini', encoding='utf-8')
                base_path = config.get('Recording', 'save_path', fallback='C:\\')
                
                # 날짜와 시간 형식
                today = datetime.datetime.now().strftime("%Y%m%d")
                time_str = datetime.datetime.now().strftime("%H%M%S")
                
                file_dir = os.path.join(base_path, today, phone_ip, time_str)
                os.makedirs(file_dir, exist_ok=True)
                
                filename = f"{time_str}_{direction}_{call_info['from_number']}_{call_info['to_number']}_{today}.wav"
                filepath = os.path.join(file_dir, filename)
                
                # 스트림 정보에 버퍼 관련 필드 추가
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
                    'current_buffer_size': 8000,  # 초기 버퍼 크기
                    'packet_count': 0,            # 패킷 카운터
                    'last_write_time': time.time(),  # 마지막 쓰기 시간
                    'packet_rate': 0,             # 패킷 도착 속도
                    'is_internal_call': self._is_internal_call(call_info)  # 내선 통화 여부
                }
                
                # WAV 파일 초기화
                with wave.open(filepath, 'wb') as wav_file:
                    wav_file.setnchannels(1)
                    wav_file.setsampwidth(2)
                    wav_file.setframerate(8000)
                
            return stream_key
            
        except Exception as e:
            print(f"스트림 생성 중 오류: {e}")
            import traceback
            print(traceback.format_exc())
            return None

    def _is_internal_call(self, call_info):
        """내선 통화 여부 확인"""
        from_number = str(call_info['from_number'])
        to_number = str(call_info['to_number'])
        return (len(from_number) == 4 and from_number[0] in '123456789' and
                len(to_number) == 4 and to_number[0] in '123456789')

    def _adjust_buffer_size(self, stream_info):
        """버퍼 크기 동적 조정"""
        try:
            current_time = time.time()
            time_diff = current_time - stream_info['last_write_time']
            
            if time_diff > 0:
                # 패킷 도착 속도 계산 (패킷/초)
                current_rate = stream_info['packet_count'] / time_diff
                
                # 이동 평균으로 패킷 속도 업데이트
                alpha = 0.3  # 가중치 계수
                stream_info['packet_rate'] = (alpha * current_rate + 
                                            (1 - alpha) * stream_info['packet_rate'])
                
                # 내선 통화인 경우 더 작은 버퍼 사용
                if stream_info['is_internal_call']:
                    target_size = min(int(stream_info['packet_rate'] * 0.8 * 1000), 
                                    self.max_buffer_size // 2)
                else:
                    target_size = min(int(stream_info['packet_rate'] * 1.2 * 1000), 
                                    self.max_buffer_size)
                
                # 버퍼 크기 조정
                target_size = max(self.min_buffer_size, 
                                min(target_size, self.max_buffer_size))
                
                # 점진적으로 버퍼 크기 조정
                if abs(target_size - stream_info['current_buffer_size']) > self.min_buffer_size:
                    if target_size > stream_info['current_buffer_size']:
                        stream_info['current_buffer_size'] += self.min_buffer_size
                    else:
                        stream_info['current_buffer_size'] -= self.min_buffer_size
                
                # 카운터 초기화
                stream_info['packet_count'] = 0
                stream_info['last_write_time'] = current_time
                
                print(f"버퍼 크기 조정: {stream_info['current_buffer_size']} bytes")
                
        except Exception as e:
            print(f"버퍼 크기 조정 중 오류: {e}")

    def process_packet(self, stream_key, audio_data, sequence, payload_type):
        """RTP 패킷 처리"""
        try:
            with self.stream_locks[stream_key]:
                stream_info = self.active_streams[stream_key]
                if not stream_info['saved']:
                    # 시퀀스 번호와 패킷 크기 로깅
                    print(f"패킷 수신 - 시퀀스: {sequence}, 크기: {len(audio_data)} bytes")
                    
                    # 시퀀스 번호 체크 (연속성 확인)
                    if stream_info['sequence'] > 0:  # 첫 패킷이 아닌 경우
                        expected_sequence = (stream_info['sequence'] + 1) % 65536  # RTP 시퀀스는 16비트
                        if sequence != expected_sequence:
                            print(f"시퀀스 불연속 감지: 예상={expected_sequence}, 실제={sequence}")
                    
                    # 시퀀스 번호 체크 (중복 패킷)
                    if sequence <= stream_info['sequence']:
                        print(f"중복 패킷 무시: 현재={stream_info['sequence']}, 수신={sequence}")
                        return
                    
                    stream_info['audio_data'].extend(audio_data)
                    stream_info['sequence'] = sequence
                    stream_info['packet_count'] += 1
                    
                    # 버퍼 상태 로깅
                    print(f"버퍼 상태 - 현재크기: {len(stream_info['audio_data'])}, " 
                          f"목표크기: {stream_info['current_buffer_size']}, "
                          f"내선통화: {stream_info['is_internal_call']}")
                    
                    if len(stream_info['audio_data']) >= stream_info['current_buffer_size']:
                        self._write_to_wav(stream_key, payload_type)
                        self._adjust_buffer_size(stream_info)
                        
        except Exception as e:
            print(f"패킷 처리 중 오류: {e}")

    def _write_to_wav(self, stream_key, payload_type):
        try:
            with self.file_locks[stream_key]:
                stream_info = self.active_streams[stream_key]
                if not stream_info['audio_data']:
                    return

                print(f"WAV 쓰기 시작 - 데이터크기: {len(stream_info['audio_data'])} bytes")

                if payload_type == 8:  # PCMA
                    decoded = audioop.alaw2lin(bytes(stream_info['audio_data']), 2)
                    codec_type = "PCMA"
                else:  # PCMU
                    decoded = audioop.ulaw2lin(bytes(stream_info['audio_data']), 2)
                    codec_type = "PCMU"
                
                print(f"디코딩 완료 - 코덱: {codec_type}, 디코딩크기: {len(decoded)} bytes")
                amplified = audioop.mul(decoded, 2, 2.0)
                
                try:
                    before_size = 0
                    if os.path.exists(stream_info['filepath']):
                        before_size = os.path.getsize(stream_info['filepath'])
                        temp_filepath = stream_info['filepath'] + '.tmp'
                        
                        # 기존 WAV 파일 읽기
                        with wave.open(stream_info['filepath'], 'rb') as wav_read:
                            params = wav_read.getparams()
                            existing_frames = wav_read.readframes(wav_read.getnframes())

                        # 임시 파일에 쓰기
                        with wave.open(temp_filepath, 'wb') as wav_write:
                            wav_write.setparams(params)
                            wav_write.writeframes(existing_frames)
                            wav_write.writeframes(amplified)

                        # 임시 파일을 원본으로 이동
                        os.replace(temp_filepath, stream_info['filepath'])
                    else:
                        # 새 WAV 파일 생성
                        with wave.open(stream_info['filepath'], 'wb') as wav_file:
                            wav_file.setnchannels(1)
                            wav_file.setsampwidth(2)
                            wav_file.setframerate(8000)
                            wav_file.writeframes(amplified)

                    after_size = os.path.getsize(stream_info['filepath'])
                    print(f"WAV 파일 크기 변화: {before_size} -> {after_size} bytes "
                          f"(증가: {after_size - before_size} bytes)")

                except Exception as write_error:
                    print(f"WAV 파일 쓰기 세부 오류: {write_error}")
                    if 'temp_filepath' in locals() and os.path.exists(temp_filepath):
                        os.remove(temp_filepath)
                    raise

                stream_info['audio_data'] = bytearray()

        except Exception as e:
            print(f"WAV 파일 쓰기 중 오류: {e}")
            import traceback
            print(traceback.format_exc())

    def finalize_stream(self, stream_key):
        """스트림 종료 처리"""
        try:
            if stream_key not in self.active_streams:
                print(f"존재하지 않는 스트림 키: {stream_key}")
                return None
                
            with self.stream_locks[stream_key]:
                stream_info = self.active_streams[stream_key]
                if not stream_info['saved']:
                    # 남은 데이터 쓰기
                    if stream_info['audio_data']:
                        self._write_to_wav(stream_key, 8)  # 기본값으로 PCMA 사용
                    stream_info['saved'] = True
                    
                # 스트림 정보 복사본 반환
                return dict(stream_info)
                
        except Exception as e:
            print(f"스트림 종료 중 오류: {e}")
            import traceback
            print(traceback.format_exc())
            return None

    def save_file_info(self, file_info):
        """MongoDB에 파일 정보 저장"""
        try:
            # 파일 정보 저장
            self.filesinfo.insert_one(file_info)
            # print 문 제거 - 파일 정보 로그 출력하지 않음
        except Exception as e:
            print(f"파일 정보 저장 실패: {e}")

if __name__ == "__main__":
	app = QApplication([])
	window = Dashboard()
	window.show()
	app.exec()