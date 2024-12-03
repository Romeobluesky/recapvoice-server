import atexit
import subprocess

# 종료할 프로세스 목록
processes_to_kill = ['nginx.exe', 'mongod.exe', 'node.exe']

def kill_processes():
    for process in processes_to_kill:
        subprocess.call(['taskkill', '/f', '/im', process])

# 프로그램 종료 시 kill_processes 함수 실행
atexit.register(kill_processes)

from PySide6.QtWidgets import *
from PySide6.QtCore import *
from PySide6.QtGui import *
from PySide6.QtNetwork import *

import os
import psutil
import configparser
import requests
import pyshark
import threading
import asyncio
import datetime
from config_loader import load_config

from voip_monitor import VoipMonitor
from packet_monitor import PacketMonitor
from settings_popup import SettingsPopup

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
		self.setWindowIcon(QIcon("images/icon03.png"))
		self.setWindowTitle("reCap VOICE")

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

		# LINE LIST와 LOG LIST의 비율 조정
		line_list = self._create_line_list()
		log_list = self._create_log_list()
		content_layout.addWidget(line_list, 60)  # 60% 비율
		content_layout.addWidget(log_list, 40)   # 40% 비율

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
			print(f"네트워 인터페이스 로드 패: {e}")

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
		self.phone_number.setText(config.get('Extension', 'Rep_number', fallback=''))

		phone_layout.addWidget(phone_text)
		phone_layout.addWidget(self.phone_number)

		# ID CODE 섹션
		id_section = QWidget()
		id_layout = QHBoxLayout(id_section)
		id_layout.setAlignment(Qt.AlignRight)
		id_layout.setContentsMargins(0, 0, 0, 0)

		id_text = QLabel("ID CODE | ")
		self.id_code = QLabel()
		self.id_code.setText(config.get('Extension', 'Id_code', fallback=''))

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

		# 로고 영역
		logo_label = QLabel()
		logo_label.setFixedHeight(100)
		logo_label.setAlignment(Qt.AlignCenter)
		logo_pixmap = QPixmap("images/recapvoicelogo.png")
		if not logo_pixmap.isNull():
			# 원본 이미지의 가로/세로 비율 계산
			aspect_ratio = logo_pixmap.height() / logo_pixmap.width()
			target_width = 188  # 원하는 가로 크기
			target_height = int(target_width * aspect_ratio)  # 비율에 맞는 세로 크기 계산

			scaled_logo = logo_pixmap.scaled(
				target_width,
				target_height,
				Qt.KeepAspectRatio,
				Qt.SmoothTransformation
			)
			logo_label.setPixmap(scaled_logo)
		layout.addWidget(logo_label)

		# 메뉴 버들을 담을 컨테이너
		menu_container = QWidget()

		menu_layout = QVBoxLayout(menu_container)
		menu_layout.setContentsMargins(0, 0, 0, 0)
		menu_layout.setSpacing(5)

		# 버튼 생성 및 클릭 이벤트 연결
		voip_btn = self._create_menu_button("VOIP MONITOR", "images/voip_icon.png")
		voip_btn.clicked.connect(self.show_voip_monitor)

		packet_btn = self._create_menu_button("PACKET MONITOR", "images/packet_icon.png")
		packet_btn.clicked.connect(self.show_packet_monitor)

		setting_btn = self._create_menu_button("SETTING", "images/setting_icon.png")
		setting_btn.clicked.connect(self.show_settings)

		menu_layout.addWidget(voip_btn)
		menu_layout.addWidget(packet_btn)
		menu_layout.addStretch()

		menu_layout.addWidget(setting_btn)

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

		# Network IP (1/4 비율) 공인아이피
		network_group = self._create_info_group("NETWORK IP", self.get_public_ip())
		top_layout.addWidget(network_group, 25)

		# PORT MIRRORING IP (1/4 비율) 내부이피
		config = configparser.ConfigParser()
		config.read('settings.ini', encoding='utf-8')
		port_mirror_ip = config.get('Network', 'ip', fallback='127.0.0.1')
		port_group = self._create_info_group("PORT MIRRORING IP", port_mirror_ip)
		top_layout.addWidget(port_group, 25)

		# Record Start (1/4 비율)
		record_start = self._create_toggle_group("RECORD START")
		top_layout.addWidget(record_start, 25)

		# CLIENT START (1/4 비율)
		client_start = self._create_client_start_group()
		top_layout.addWidget(client_start, 25)

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
		bottom_layout.addWidget(disk_group, 70)

		# 회선상태 섹션 (30%)
		led_group = QGroupBox('회선 상태')
		led_layout = QHBoxLayout()
		led_layout.addWidget(self._create_led_with_text('회선 Init ', 'yellow'))
		led_layout.addWidget(self._create_led_with_text('대 기 중 ', 'blue'))
		led_layout.addWidget(self._create_led_with_text('녹 취 중 ', 'green'))
		led_layout.addWidget(self._create_led_with_text('녹취안됨 ', 'red'))
		led_group.setLayout(led_layout)
		bottom_layout.addWidget(led_group, 30)

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
		if title == "NETWORK IP":
			self.ip_value = QLabel(value)
			value_label = self.ip_value
		elif title == "PORT MIRRORING IP":
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

		off_btn = QPushButton("OFF")
		off_btn.setObjectName("toggleOff")
		off_btn.setCursor(Qt.PointingHandCursor)

		on_btn = QPushButton("ON")
		on_btn.setObjectName("toggleOn")
		on_btn.setCursor(Qt.PointingHandCursor)

		button_layout.addWidget(off_btn, 1)
		button_layout.addWidget(on_btn, 1)

		layout.addWidget(button_container)

		return group

	def _create_line_list(self):
		group = QGroupBox("전화연결 상태")
		group.setObjectName("line_list")
		group.setStyleSheet("""
			QGroupBox {
				background-color: #2d2d2d;
				border: 1px solid #3a3a3a;
				border-radius: 4px;
				margin-top: 10px;
				padding: 10px;
				color: white;
				font-weight: bold;
			}
		""")

		layout = QVBoxLayout(group)
		layout.setContentsMargins(15, 15, 15, 15)
		layout.setSpacing(0)

		# 스크롤 영역 생성
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

		# 상단 컨테이너 (LED와 정보를 포함)
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
			"회선 연결": "#FFB800",  # 란색
			"대기중": "#18508F",     # 파란색
			"녹취중": "#00FF00",     # 초록색
			"녹취안됨": "#FFB800",   # 노란색
		}
		return colors.get(state, "#666666")  # 기본값은 회색

	def _create_log_list(self):
		"""VoIP 모니터링 리스트 생성"""
		group = QGroupBox("LOG LIST")
		layout = QVBoxLayout(group)
		layout.setContentsMargins(15, 15, 15, 15)

		# 테이블 위젯 설정
		table = QTableWidget()
		table.setObjectName("log_list_table")  # 업데이트를 위한 객체 이름 설정
		table.setColumnCount(7)
		table.setHorizontalHeaderLabels([
			'시간', '통화 방', '발신번호', '수신번호', '상태', '결과', 'Call-ID'
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
		shadow.setBlurRadius(3)
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
		try:
			self.voip_window = VoipMonitor()
			self.voip_window.show()
		except Exception as e:
			print(f"Error opening VOIP Monitor: {e}")
			QMessageBox.warning(self, "오류", "VOIP Monitor를 열 수 없습니다.")

	def show_packet_monitor(self):
		try:
			self.packet_window = PacketMonitor()
			self.packet_window.show()
		except Exception as e:
			print(f"Error opening Packet Monitor: {e}")
			QMessageBox.warning(self, "오류", "Packet Monitor를 열 수 없니다.")

	def show_settings(self):
		try:
			# 기존 settings_popup 인스턴스를 사용
			self.settings_popup.show()
		except Exception as e:
			print(f"Error opening Settings: {e}")
			QMessageBox.warning(self, "오류", "Settings를  수 없습니다.")

	def update_dashboard_settings(self, settings_data):
		"""설정 변경 시 대시보드 데이트"""
		try:
			# 대표번호 업데이트
			if 'Extension' in settings_data:
				self.phone_number.setText(settings_data['Extension']['Rep_number'])

			# NETWORK IP 업데이트
			if 'Network' in settings_data:
				self.ip_value.setText(settings_data['Network']['ap_ip'])

			# PORT MIRRORING IP 업데이트
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
		"""SIP 패킷 분석"""
		try:
			sip_layer = packet.sip
			call_id = sip_layer.call_id
			print(f"\n=== SIP 패킷 감지 ===")
			print(f"Call-ID: {call_id}")

			if hasattr(sip_layer, 'status_line'):
				status_code = sip_layer.status_code
				print(f"Status Line: {sip_layer.status_line}")
				print(f"Status Code: {status_code}")

				# 100 Trying 감지 시 즉시 블록 생성
				if status_code == '100':
					print("100 Trying 감지")
					extension = self.extract_number(sip_layer.from_user)
					if extension and len(extension) == 4 and extension[0] in ['1', '2', '3', '4']:
						print(f"내선번호 감지: {extension}")
						# 대기중 록 생성
						self.block_update_signal.emit(extension, "대기중", "")
						print(f"대기중 블록 생성 요청: {extension}")

				# 나머지 상태 코드 처리
				if call_id in self.active_calls:
					if status_code == '183':  # Session Progress (벨울림)
						print("Ringing 상태 감지")
						self.update_call_status(call_id, '벨울림')

					elif status_code == '200':  # OK
						print("통화 연결됨")
						if self.active_calls[call_id]['status'] != '통화종료':
							self.update_call_status(call_id, '통화중')

						# 통화 시간 업데이트 타이머 시작
						if not hasattr(self, 'duration_timer') or not self.duration_timer.isActive():
							self.duration_timer = QTimer()
							self.duration_timer.timeout.connect(self.update_call_duration)
							self.duration_timer.start(1000)  # 1초마다 업데이트

					elif status_code in ['486', '603']:  # Busy, Decline
						print("통화 거절됨")
						self.update_call_status(call_id, '통화종료', '수신거부')
						# 대기중 록 생성
						self.block_update_signal.emit(extension, "대기중", "")
						print(f"대기중 블록 생성 요청: {extension}")

			elif hasattr(sip_layer, 'request_line'):
				print(f"Request Line: {sip_layer.request_line}")

				if 'INVITE' in sip_layer.request_line:
					print("INVITE 요청 감지")
					from_number = self.extract_number(sip_layer.from_user)
					to_number = self.extract_number(sip_layer.to_user)

					self.active_calls[call_id] = {
						'start_time': datetime.datetime.now(),
						'status': '시도중',
						'from_number': from_number,
						'to_number': to_number,
						'direction': '수신' if to_number.startswith(('1','2','3','4')) else '발신'
					}
					self.update_call_status(call_id, '시도중')

				elif 'BYE' in sip_layer.request_line:
					if call_id in self.active_calls:
						self.update_call_status(call_id, '통화종료', '정상종료')
						# 대기중 록 생성
						self.block_update_signal.emit(extension, "대기중", "")
						print(f"대기중 블록 생성 요청: {extension}")

				# CANCEL 요청 처리
				elif 'CANCEL' in sip_layer.request_line:
					if call_id in self.active_calls:
						self.update_call_status(call_id, '통화종료', '발신취소')
						# 대기중 록 생성
						self.block_update_signal.emit(extension, "대기중", "")
						print(f"대기중 블록 생성 요청: {extension}")

		except Exception as e:
			print(f"SIP 패킷 분석 중 오류: {e}")
			import traceback
			print(traceback.format_exc())

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
				'direction': '수신' if to_number.startswith(('1','2','3','4')) else '발신',
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

			# LOG LIST 즉시 데이트
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
			is_extension = lambda num: num.startswith(('1', '2', '3', '4')) and len(num) == 4
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
			if 'UDP' not in packet:
				return False

			# payload를 hex string으로 변
			payload_hex = packet.udp.payload.replace(':', '')
			payload = bytes.fromhex(payload_hex)

			if len(payload) < 12:
				return False

			version = (payload[0] >> 6) & 0x03
			payload_type = payload[1] & 0x7F

			return version == 2 and payload_type in [0, 8]  # PCMU=0, PCMA=8

		except Exception as e:
			print(f"RTP 패킷 검증 중 오류: {e}")
			return False

	def determine_stream_direction(self, packet):
		"""RTP 스트 향 결정"""
		src_port = int(packet.udp.srcport)
		dst_port = int(packet.udp.dstport)

		if 3000 <= src_port <= 3999:  # SIP 포트 범위
			return "발신"
		else:
			return "수신"

	def extract_number(self, sip_user):
		"""SIP User 필드에서 화번호 추 (전체 번호 반환)"""
		try:
			if not sip_user:
				return ''

			sip_user = str(sip_user)

			# sip: 제거 및 전체 번호 추
			if 'sip:' in sip_user:
				number = sip_user.split('sip:')[1].split('@')[0]
				return ''.join(c for c in number if c.isdigit())

			# Q 문자로 분리된 경우 처리
			if 'Q' in sip_user:
				return sip_user.split('Q')[1]

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

			# self.active_calls에서 이 RTP 스트림과 칭되는 Call-ID 찾기
			for call_id, call_info in self.active_calls.items():
				if "media_endpoints" in call_info:
					for endpoint in call_info["media_endpoints"]:
						if (src_ip == endpoint["ip"] and src_port == endpoint["port"]) or \
						   (dst_ip == endpoint["ip"] and dst_port == endpoint["port"]):
							return call_id
			return None

		except Exception as e:
			print(f"RTP Call-ID 매칭 오류: {e}")
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
		"""강제로 록 상태 업데이트"""
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
		"""통화 상태 통합 관리"""
		try:
			if call_id in self.active_calls:
				# 상태 업데이트
				self.active_calls[call_id].update({
					'status': new_status,
					'result': result
				})

				if new_status == '통화종료':
					self.active_calls[call_id]['end_time'] = datetime.datetime.now()
					extension = self.get_extension_from_call(call_id)
					if extension:
						self.block_update_signal.emit(extension, "통화종료", self.active_calls[call_id]['to_number'])

				else:
					extension = self.get_extension_from_call(call_id)
					if extension:
						received_number = self.active_calls[call_id]['to_number']
						self.block_update_signal.emit(extension, new_status, received_number)

			# LOG LIST 업데이트
			self.update_voip_status()

			print(f"통화 상태 업데이트 - Call-ID: {call_id}, Status: {new_status}, Result: {result}")

		except Exception as e:
			print(f"통화 상태 업데이트 중 오류: {e}")

	@Slot()
	def handle_first_registration(self):
		"""첫 번째 SIP 등록 감지 시 처리"""
		try:
			if not self.first_registration:
				self.first_registration = True
				print("첫 번째 SIP 등록 완료")
		except Exception as e:
			print(f"첫 번째 등록 처리 중 오류: {e}")

	def capture_packets(self, interface):
		"""패킷 캡처 및 분석"""
		try:
			loop = asyncio.new_event_loop()
			asyncio.set_event_loop(loop)

			# SIP 패킷만 캡처하도록 필터 설정
			capture = pyshark.LiveCapture(
				interface=interface,
				display_filter='sip'
			)

			print(f"패킷 캡처 감시 - Interface: {interface}")

			# 패킷 캡처 시작 전에 인터페이스 확인
			if not interface:
				print("Error: No interface selected")
				return

			for packet in capture.sniff_continuously():
				try:
					if 'SIP' in packet:
						# SIP 패킷 분석
						self.analyze_sip_packet(packet)

				except Exception as packet_error:
					print(f"개별 패킷 처리 중 오류: {packet_error}")
					continue

		except Exception as e:
			print(f"패킷 캡처 중 오류: {e}")
			import traceback
			print(traceback.format_exc())
		finally:
			if 'capture' in locals():
				capture.close()
			if 'loop' in locals():
				loop.close()

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
		"""CLIENT START 그룹 생성"""
		group = QGroupBox("CLIENT START")
		layout = QHBoxLayout(group)
		layout.setContentsMargins(15, 20, 15, 15)
		layout.setSpacing(2)

		# 버튼 컨테이너
		button_container = QWidget()
		button_layout = QHBoxLayout(button_container)
		button_layout.setContentsMargins(0, 0, 0, 0)
		button_layout.setSpacing(2)

		# OFF/ON 버튼
		self.off_btn = QPushButton("OFF")
		self.off_btn.setObjectName("toggleOff")
		self.off_btn.setCursor(Qt.PointingHandCursor)
		self.off_btn.clicked.connect(self.stop_client)

		self.on_btn = QPushButton("ON")
		self.on_btn.setObjectName("toggleOn")
		self.on_btn.setCursor(Qt.PointingHandCursor)
		self.on_btn.clicked.connect(self.start_client)

		button_layout.addWidget(self.off_btn, 1)
		button_layout.addWidget(self.on_btn, 1)

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
			processes_to_kill = ['nginx.exe', 'mongod.exe', 'node.exe']

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

if __name__ == "__main__":
	app = QApplication([])
	window = Dashboard()
	window.show()
	app.exec()