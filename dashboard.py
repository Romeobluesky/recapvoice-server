from PySide6.QtWidgets import *
from PySide6.QtCore import *
from PySide6.QtGui import *

import os
import psutil
import configparser
import requests

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
            if y_offset >= self.height() - 10:  # 위젯 높이를 넘어가지 않도록 체크
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
	def __init__(self):
		super().__init__()
		self.setWindowIcon(QIcon("images/logo.png"))
		self.setWindowTitle("Packet Wave")
		
		# SettingsPopup 인스턴스 생성
		self.settings_popup = SettingsPopup()
		
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
		
		# 상태 정보 섹션
		status_section = self._create_status_section()
		content_layout.addLayout(status_section)
		
		# LINE LIST와 LOG LIST의 비율 조정
		line_list = self._create_line_list()
		log_list = self._create_log_list()
		content_layout.addWidget(line_list, 60)  # 65% 비율
		content_layout.addWidget(log_list, 40)   # 35% 비율
		
		self._apply_styles()
		
		# 초기 크기 설정
		self.resize(1400, 1000)  # 높이를 1000으로 증가
		
		# 설정 변경 시그널 연결
		self.settings_popup.settings_changed.connect(self.update_dashboard_settings)
		self.settings_popup.path_changed.connect(self.update_storage_path)

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
		
		# 로고 영
		logo_label = QLabel()
		logo_label.setFixedHeight(100)
		logo_label.setAlignment(Qt.AlignCenter)
		logo_pixmap = QPixmap("images/logo.png")
		if not logo_pixmap.isNull():
			scaled_logo = logo_pixmap.scaled(50, 50, Qt.KeepAspectRatio, Qt.SmoothTransformation)
			logo_label.setPixmap(scaled_logo)
		layout.addWidget(logo_label)
		
		# 메뉴 버튼들을 담을 컨테이너
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
		text_label.setStyleSheet("color: black;")
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
		
		# Auto Record (1/4 비율)
		auto_record = self._create_toggle_group("AUTO RECORD")
		top_layout.addWidget(auto_record, 25)
		
		# Record Start (1/4 비율)
		record_start = self._create_toggle_group("RECORD START")
		top_layout.addWidget(record_start, 25)
		
		layout.addLayout(top_layout)
		
		# �� 상태 정보 섹션
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
		self.progress_bar.setFixedHeight(18)  # 프로그레스바 높이 18로 설정
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
		scroll.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)  # 크기 정책 설정
		
		# 통화 블록들을 담을 컨테이너
		calls_container = QWidget()
		calls_container.setObjectName("scrollContents")
		calls_layout = FlowLayout(calls_container, margin=0, spacing=20)
		
		# 20개의 블록 생성
		for i in range(16):
			if i % 2 == 0:
				block = self._create_call_block(
					internal_number=f"100{i}",
					received_number="01012345678",
					duration="00:00:00",
					status="대기중"
				)
			else:
				block = self._create_call_block(
					internal_number=f"100{i}",
					received_number="01077141436",
					duration=f"00:{i:02d}:22",
					status="통화중"
				)
			calls_layout.addWidget(block)
		
		scroll.setWidget(calls_container)
		
		# 패킷 플로우를 표시할 하단 위젯
		packet_flow = PacketFlowWidget()
		packet_flow.setFixedHeight(0)
		
		# 레이아웃에 위젯 추가 및 비율 설정
		layout.addWidget(scroll, 1)  # stretch factor 1 설정
		layout.addWidget(packet_flow)
		
		# 스크롤바 스타일 설정
		scroll.setStyleSheet("""
			QScrollArea {
				border: none;
				background-color: #2d2d2d;
			}
			QWidget#scrollContents {
				background-color: #2d2d2d;  /* 블록들이 있는 영역의 배경색만 변경 */
			}
			QScrollBar:vertical {
				width: 8px;
				background: #2d2d2d;
				border-radius: 2px;
				margin: 0px;
			}
			QScrollBar::handle:vertical {
				background: #666666;
				border-radius: 4px;
				min-height: 20px;
			}
			QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
				height: 0px;
			}
			QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
				background: none;
			}
		""")
		
		return group

	def _create_call_block(self, internal_number, received_number, duration, status):
		block = QWidget()
		block.setFixedSize(200, 150)
		block.setObjectName("callBlock")
		layout = QVBoxLayout(block)
		layout.setContentsMargins(15, 15, 15, 15)
		layout.setSpacing(15)
		
		# 정보 표시 레이블들
		info_layout = QGridLayout()
		info_layout.setSpacing(8)
		info_layout.setContentsMargins(0, 0, 0, 0)
		
		if status == "대기중":
			# 대기중일 때는 내선과 상태만 표시
			labels = [
				("내선:", internal_number),
				("상태:", status)
			]
			# 대기중일 때의 LED 상태
			led_states = ["회선 Init", "대기중"]  # 노란색, 파란색
		else:
			# 통화중일 때는 모든 정보 표시
			labels = [
				("내선:", internal_number),
				("수신:", received_number),
				("상태:", status),
				("시간:", duration)
			]
			# 통화중일 때의 LED 상태
			led_states = ["회선 Init", "녹취중"]  # 노란색, 초록색
		
		for idx, (title, value) in enumerate(labels):
			title_label = QLabel(title)
			title_label.setObjectName("blockTitle")
			value_label = QLabel(value)
			value_label.setObjectName("blockValue")
			
			info_layout.addWidget(title_label, idx, 0)
			info_layout.addWidget(value_label, idx, 1)
		
		# LED 상태 표시 영역
		led_container = QWidget()
		led_layout = QHBoxLayout(led_container)
		led_layout.setContentsMargins(0, 0, 0, 0)
		led_layout.setSpacing(8)
		led_layout.setAlignment(Qt.AlignRight)
		
		# LED 추가 (상태에 따라 다른 LED 표시)
		for state in led_states:
			led = self._create_led("", self._get_led_color(state))
			led_layout.addWidget(led)
		
		layout.addLayout(info_layout)
		layout.addWidget(led_container)
		
		# 나머지 스타일 코드는 동일
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
					background-color: #2D3436;
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
			"회선 Init": "#FFB800",  # 노란색
			"대기중": "#18508F",     # 파란색
			"녹취중": "#00FF00",     # 초록색
			"녹취안됨": "#FFB800",   # 노란색
		}
		return colors.get(state, "#666666")  # 기본값은 회색

	def _create_log_list(self):
		group = QGroupBox("LOG LIST")
		layout = QVBoxLayout(group)
		layout.setContentsMargins(15, 15, 15, 15)
		
		table = QTableWidget()
		table.setMinimumHeight(150)
		table.setColumnCount(4)
		table.setHorizontalHeaderLabels(["발신번호", "수신번호", "패킷플로우", "상태"])
		
		# 테스트 데이터 추가
		table.setRowCount(5)  # 기본 5행 표시
		test_data = [
			("1001", "01012345678", "패킷 데이터...", "통화중"),
			("1002", "01077141436", "패킷 데이터...", "대기중"),
			("1003", "01012345678", "패킷 데이터...", "통화중"),
			("1004", "01077141436", "패킷 데이터...", "대기중"),
			("1005", "01012345678", "패킷 데이터...", "통화중"),
		]
		
		for row, (caller, receiver, packet, status) in enumerate(test_data):
			table.setItem(row, 0, QTableWidgetItem(caller))
			table.setItem(row, 1, QTableWidgetItem(receiver))
			table.setItem(row, 2, QTableWidgetItem(packet))
			table.setItem(row, 3, QTableWidgetItem(status))
		
		# 열 너비 조정
		table.setColumnWidth(0, 100)  # 발신번호
		table.setColumnWidth(1, 100)  # 수신번호
		table.setColumnWidth(3, 100)  # 상태
		table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)  # 패킷플로우
		
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
				background-color: #2d2d2d;
				border: none;
				gridline-color: #3a3a3a;
			}
			QTableWidget::item {
				padding: 5px;
			}
			QHeaderView::section {
				background-color: #34495e;
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
		"""전화연결상태 블록용 LED (텍스트 없음)"""
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
		
		# 그림자 효과 추가
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
			# settings.ini에서 Recording 경로 읽기
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
			QMessageBox.warning(self, "오류", "Packet Monitor를 열 수 없습니다.")

	def show_settings(self):
		try:
			# 기존 settings_popup 인스턴스를 사용
			self.settings_popup.show()
		except Exception as e:
			print(f"Error opening Settings: {e}")
			QMessageBox.warning(self, "오류", "Settings를 열 수 없습니다.")

	def update_dashboard_settings(self, settings_data):
		"""설정 변경 시 대시보드 업데이트"""
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
			QMessageBox.warning(self, "오류", "대시보드 업데이트 중 오류가 발생했습니다.")

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
			
			#print(f"Recording path updated to: {new_path}")  # 디버깅용
			
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

# FlowLayout 클래스 추가 (Qt의 유동적 그리드 레이아웃 구현)
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
