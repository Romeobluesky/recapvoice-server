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
		
		# LINE LIST와 LOG LIST
		line_list = self._create_line_list()
		log_list = self._create_log_list()
		content_layout.addWidget(line_list)
		content_layout.addWidget(log_list)
		
		self._apply_styles()
		
		# 초기 크기 설정
		self.resize(1200, 800)
		
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
		
		# 로고 영역
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
		
		# PORT MIRRORING IP (1/4 비율) 내부아이피
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
		
		# 하단 상태 정보 섹션
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
		led_layout.addWidget(self._create_led('회선 Init ', 'yellow'))
		led_layout.addWidget(self._create_led('대 기 중 ', 'blue'))
		led_layout.addWidget(self._create_led('녹 취 중 ', 'green'))
		led_layout.addWidget(self._create_led('녹취안됨 ', 'red'))
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
		group = QGroupBox("LINE LIST")
		layout = QVBoxLayout(group)
		layout.setContentsMargins(15, 15, 15, 15)
		
		table = QTableWidget()
		table.setColumnCount(9)
		table.setHorizontalHeaderLabels(["LED", "NO", "회선번호", "전화기 IP", "사용자명", "사용자ID", "내용", "기타", "상태"])
		table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
		table.setMaximumHeight(700)
		# 예제 데이터 추가
		example_data = [
			["●", "1", "회선-001", "192.168.0.101", "홍길동", "USER001", "정상 연결됨", "", "로그인"],
			["●", "2", "회선-002", "192.168.0.102", "김철수", "USER002", "정상 연결됨", "", "로그인"],
			["○", "3", "회선-003", "192.168.0.103", "이영희", "USER003", "연결 끊김", "확인 필요", "로그아웃"],
			["●", "4", "회선-004", "192.168.0.104", "박민수", "USER004", "정상 연결됨", "", "로그인"],
			["●", "5", "회선-005", "192.168.0.105", "최영식", "USER005", "정상 연결됨", "", "로그인"],
			["○", "6", "회선-006", "192.168.0.106", "정미영", "USER006", "연결 끊김", "점검 중", "로그아웃"],
			["●", "7", "회선-007", "192.168.0.107", "강동원", "USER007", "정상 연결됨", "", "로그인"],
			["●", "8", "회선-008", "192.168.0.108", "윤서연", "USER008", "정상 연결됨", "", "로그인"],
			["●", "9", "회선-001", "192.168.0.101", "홍길동", "USER001", "정상 연결됨", "", "로그인"],
			["●", "10", "회선-002", "192.168.0.102", "김철수", "USER002", "정상 연결됨", "", "로그인"],
			["○", "11", "회선-003", "192.168.0.103", "이영희", "USER003", "연결 끊김", "확인 필요","로그아웃"],
			["●", "12", "회선-004", "192.168.0.104", "박민수", "USER004", "정상 연결됨", "", "로그인"],
			["●", "13", "회선-005", "192.168.0.105", "최영식", "USER005", "정상 연결됨", "", "로그인"],
			["○", "14", "회선-006", "192.168.0.106", "정미영", "USER006", "연결 끊김", "점검 중", "로그아웃"],
			["●", "15", "회선-007", "192.168.0.107", "강동원", "USER007", "정상 연결됨", "", "로그인"],
			["●", "16", "회선-008", "192.168.0.108", "윤서연", "USER008", "정상 연결됨", "", "로그인"]
		]
		
		table.setRowCount(len(example_data))
		# 데이터 입력 및 스타일 적용
		for row, data in enumerate(example_data):
			for col, value in enumerate(data):
				item = QTableWidgetItem(value)
				item.setTextAlignment(Qt.AlignCenter)
				
				# LED 상태에 따른 색상 설정
				if col == 0:  # LED 열
					if value == "●":
						item.setForeground(QColor("#48c9b0"))  # 연결됨 - 민트색
					else:
						item.setForeground(QColor("#e74c3c"))  # 연결 끊김 - 빨간색

				if col == 8:  # 상태 열
					if value == "로그인":
						item.setForeground(QColor("#48c9b0"))  # 연결됨 - 민트색
					else:
						item.setForeground(QColor("#e74c3c"))  # 연결 끊김 - 빨간색

				if col == 6:  # 내용 열
					item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)

				else:
					# 편집 불가능하게 설정
					item.setFlags(item.flags() & ~Qt.ItemIsEditable)
				
				table.setItem(row, col, item)
		
		# 열 너비 조정
		# 고정 너비 컬럼 설정
		fixed_widths = {
			0: 50,   # LED
			1: 50,   # NO
			2: 200,  # 회선번호
			3: 120,  # 전화기 IP
			4: 100,  # 사용자명
			5: 100,  # 사용자ID
			7: 200,  # 기타
			8: 80    # 상태 - 고정 너비 설정
		}
		
		# 고정 너비 적용
		for col, width in fixed_widths.items():
			table.horizontalHeader().setSectionResizeMode(col, QHeaderView.Fixed)
			table.setColumnWidth(col, width)

		# 자동 조절 컬럼 설정 (내용)
		table.horizontalHeader().setSectionResizeMode(6, QHeaderView.Stretch)
		
		table.verticalHeader().setVisible(False)
		
		# 테이블 선택 스타일 설정
		self._set_table_style(table)
		
		layout.addWidget(table)
		return group

	def _create_log_list(self):
		group = QGroupBox("LOG LIST")
		layout = QVBoxLayout(group)
		layout.setContentsMargins(15, 15, 15, 15)
		
		table = QTableWidget()
		table.setColumnCount(6)
		table.setHorizontalHeaderLabels(["NO", "시간", "구분", "구분", "내용", "기타"])
		
		# 예제 데이터 추가
		example_data = [
			["1", "2024-03-19 14:30:22", "알림", "시스템", "시스템 시작됨", ""],
			["2", "2024-03-19 14:31:05", "경고", "연결", "회선-003 연결 끊김", "재연결 시도 중"],
			["3", "2024-03-19 14:32:15", "정보", "연결", "회선-001 정상 연결", ""],
			["4", "2024-03-19 14:33:00", "오류", "패킷", "패킷 손실 발생", "조치 필요"],
			["5", "2024-03-19 14:34:12", "정보", "연결", "회선-002 정상 연결", ""],
			["6", "2024-03-19 14:35:30", "경고", "시스템", "메모리 사용량 증가", "모니터링 필요"],
			["7", "2024-03-19 14:36:45", "정보", "업데이트", "시스템 업데이트 완료", ""],
			["8", "2024-03-19 14:37:20", "경고", "연결", "회선-006 연결 불안정", "점검 중"],
		]
		
		table.setRowCount(len(example_data))
		
		# 데이터 입력 및 스타일 적용
		for row, data in enumerate(example_data):
			for col, value in enumerate(data):
				item = QTableWidgetItem(value)
				item.setTextAlignment(Qt.AlignCenter)
				
				# 구분에 따른 색상 설정
				if col == 2:  # 구분 열
					if value == "경고":
						item.setForeground(QColor("#f1c40f"))  # 노란색
					elif value == "오류":
						item.setForeground(QColor("#e74c3c"))  # 빨간색
					elif value == "정보":
						item.setForeground(QColor("#48c9b0"))  # 민트색
				
				if col == 4:  # 내용 열
					item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)

				else:
					# 편집 불가능하게 설정
					item.setFlags(item.flags() & ~Qt.ItemIsEditable)

				table.setItem(row, col, item)
		
		# 열 너비 조정
		# 고정 너비 컬럼 설정
		fixed_widths = {
			0: 50,   # NO
			1: 150,  # 시간
			2: 100,  # 구분
			3: 100,  # 상태
			5: 200  # 기타
		}

		# 고정 너비 적용
		for col, width in fixed_widths.items():
			table.horizontalHeader().setSectionResizeMode(col, QHeaderView.Fixed)
			table.setColumnWidth(col, width)

		# 자동 조절 컬럼 설정 (내용)
		table.horizontalHeader().setSectionResizeMode(4, QHeaderView.Stretch)

		table.verticalHeader().setVisible(False)
		
		# 테이블 선택 스타일 설정
		self._set_table_style(table)
		
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
		""")

	def _create_led(self, label, color):
		widget = QWidget()
		layout = QHBoxLayout()
		layout.setAlignment(Qt.AlignCenter)
		layout.setContentsMargins(0, 0, 0, 0)
		
		led = QLabel()
		led.setObjectName("led_indicator")
		led.setFixedSize(10, 10)
		led.setStyleSheet(
			f'#led_indicator {{ '
			f'background-color: {color}; '
			f'}}'
		)
		
		layout.addWidget(led)
		if label:
			layout.addWidget(QLabel(label))
		
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
		"""저장 경로 변경 시 디스크 정보 업데이트"""
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

if __name__ == "__main__":
	app = QApplication([])
	window = Dashboard()
	window.show()
	app.exec()
