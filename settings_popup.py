import os
import psutil
import configparser
from PySide6.QtWidgets import (
	QDialog, QVBoxLayout, QLabel, QLineEdit, QPushButton,
	QHBoxLayout, QCheckBox, QComboBox, QProgressBar, QGroupBox, QFileDialog,
	QMessageBox
)
from PySide6.QtCore import Qt, Signal
import socket

import requests

class SettingsPopup(QDialog):
	# 상수 정의
	WINDOW_SIZE = (600, 300)
	BUTTON_SIZES = {
		'path_button': (100, 28),
		'usage_input': (50, None),
		'dialog_button': (80, 26)
	}

	# 시그널 정의
	path_changed = Signal(str)
	settings_changed = Signal(dict)  # 모든 설정값을 dictionary로 전달

	def __init__(self):
		super().__init__()
		# 설정 파일 로드 또는 생성
		self.config = configparser.ConfigParser()
		
		if not os.path.exists('settings.ini') or os.path.getsize('settings.ini') == 0:
			# 기본 설정값 설정
			self.config['Environment'] = {
				'mode': 'production'
			}
			self.config['Recording'] = {
				'save_path': 'D:/PacketWaveRecord',
				'channels': '1',
				'sample_rate': '8000'
			}
			self.config['Network'] = {
				'ip': '192.168.0.64',
				'ap_ip': '222.100.152.166',
				'port': '8080'
			}
			self.config['Extension'] = {
				'rep_number': '',
				'id_code': 'DIFK-2345-EF78-AFE6',
				'get_interface_length': '4'
			}
			self.config['OtherSettings'] = {
				'disk_persent': '70',
				'disk_alarm': 'true'
			}
			
			# 설정 파일 저장
			with open('settings.ini', 'w', encoding='utf-8') as configfile:
				self.config.write(configfile)
		else:
			self.config.read('settings.ini', encoding='utf-8')

		# 인스턴스 변수 초기화
		self.disk_info_label = None
		self.progress_bar = None
		self.drive_combo = None
		self.path_input = None
		self.init_ui()

		# settings.ini의 저장 경로 로드
		self.load_storage_path()

	def init_ui(self):
		"""UI 초기화"""
		self.setWindowTitle('환경설정')
		self.resize(*self.WINDOW_SIZE)

		main_layout = QVBoxLayout()
		self.apply_stylesheet()

		# UI 구성요 추가
		main_layout.addWidget(self.create_company_section())
		main_layout.addWidget(self.create_record_section())
		main_layout.addLayout(self.create_button_section())

		self.setLayout(main_layout)
		self.update_disk_info()

	def get_public_ip(self):
		try:
			response = requests.get('https://api64.ipify.org/?format=json')
			ip = response.json().get('ip')
			return ip
		except requests.RequestException as e:
			print(f"An error occurred: {e}")
			return None

	def create_company_section(self):
		"""회사 정보 섹션 생성"""
		company_group = QGroupBox()
		layout = QHBoxLayout()

		# 대표번호 입력필드
		self.rep_number_input = QLineEdit()
		self.rep_number_input.setText(self.config['Extension'].get('rep_number', ''))

		# AP 서버 IP 입력필드
		self.ap_ip_input = QLineEdit()
		self.ap_ip_input.setText(self.get_public_ip())
		self.ap_ip_input.setReadOnly(True)

		layout.addWidget(QLabel('대표 번호:'))
		layout.addWidget(self.rep_number_input)
		layout.addWidget(QLabel('AP 서버 IP:'))
		layout.addWidget(self.ap_ip_input)

		company_group.setLayout(layout)
		return company_group

	def create_record_section(self):
		"""녹취 정보 섹션 생성"""
		record_group = QGroupBox()
		layout = QVBoxLayout()

		# Record IP
		layout.addLayout(self.create_record_ip_section())
		layout.addLayout(self.create_path_section())

		# Disk 정보
		self.disk_info_label = QLabel()
		self.progress_bar = QProgressBar()
		layout.addWidget(self.disk_info_label)
		layout.addWidget(self.progress_bar)

		# Alarm 설정
		layout.addLayout(self.create_alarm_section())

		record_group.setLayout(layout)
		return record_group

	def create_record_ip_section(self):
		"""Record IP 섹션 생성"""
		layout = QHBoxLayout()

		# Record IP 라벨 생성 및 고정 너비 설정
		record_ip_label = QLabel('Record IP:')
		record_ip_label.setFixedWidth(80)  # 라벨 너비 고정

		# 이더넷 인터페이스 콤보박스
		self.ip_combo = QComboBox()
		self.ip_combo.setFixedHeight(26)
		self.load_network_interfaces()

		layout.addWidget(record_ip_label)
		layout.addWidget(self.ip_combo)
		layout.setSpacing(10)  # 위젯 간 간격 설정

		return layout

	def create_path_section(self):
		"""저장 경로 섹션 생성"""
		layout = QHBoxLayout()
		layout.addWidget(QLabel('저장 경로 : '))

		# 드라이브 선택
		self.drive_combo = QComboBox()
		drives = [f"{d}:\\" for d in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'
				 if os.path.exists(f"{d}:\\")]
		self.drive_combo.addItems(drives)
		self.drive_combo.currentIndexChanged.connect(self.update_disk_info)

		# 경로 입력
		self.path_input = QLineEdit()
		self.path_input.setReadOnly(True)
		self.path_input.setStyleSheet(
			"background-color: #f0f0f0; color: #333;")

		# 경로 탐색 버튼
		path_button = QPushButton('경로탐색')
		path_button.setFixedSize(*self.BUTTON_SIZES['path_button'])
		path_button.clicked.connect(self.select_path)

		layout.addWidget(self.drive_combo)
		layout.addWidget(self.path_input)
		layout.addWidget(path_button)
		return layout

	def create_alarm_section(self):
		"""Alarm 설정 섹션 생성"""
		layout = QHBoxLayout()
		layout.setAlignment(Qt.AlignLeft)  # 전체 레이아웃 왼쪽 정렬

		# Disk 사용률 입력
		self.disk_percent_input = QLineEdit()
		self.disk_percent_input.setText(self.config['OtherSettings'].get('disk_persent', '90'))
		self.disk_percent_input.setFixedWidth(50)
		self.disk_percent_input.setAlignment(Qt.AlignCenter)  # 오른쪽 정렬

		# Alarm 끄기 체크박스
		self.alarm_checkbox = QCheckBox('Alarm 끄기')
		self.alarm_checkbox.setChecked(self.config['OtherSettings'].get('disk_alarm', 'true').lower() == 'true')

		layout.addWidget(QLabel('Disk 사용률:'))
		layout.addWidget(self.disk_percent_input)
		layout.addWidget(QLabel('% 이상이면 Alarm 발생'))
		layout.addWidget(self.alarm_checkbox)

		# 오른쪽 여백을 채우는 stretch 추가
		layout.addStretch()

		return layout

	def create_button_section(self):
		"""버튼 섹션 생성"""
		layout = QHBoxLayout()

		save_button = QPushButton('저장')
		cancel_button = QPushButton('취소')

		# 버튼 스타일 설정
		button_style = """
			QPushButton {
				background-color: #4169E1;
				color: white;
				border: none;
				padding: 2px;
			}
			QPushButton:hover {
				background-color: black;
			}
			QPushButton:pressed {
				background-color: black;
			}
		"""
		save_button.setStyleSheet(button_style)
		cancel_button.setStyleSheet(button_style)

		save_button.setFixedHeight(27)
		cancel_button.setFixedHeight(27)

		# 저장 버튼 클릭 이벤트 연결
		save_button.clicked.connect(self.save_settings)
		cancel_button.clicked.connect(self.close)

		layout.addWidget(save_button, 1)
		layout.addWidget(cancel_button, 1)

		return layout

	def load_storage_path(self):
		"""settings.ini에서 저장 경로 로드"""
		if 'Recording' in self.config and 'save_path' in self.config['Recording']:
			storage_path = self.config['Recording']['save_path']
			if storage_path:
				# 드라이브 문자 추출 (예: "D:\Records" -> "D:\")
				drive = storage_path.split(':')[0] + ':\\'
				# 드라이브 콤보박스에서 해당 드라이브 선택
				index = self.drive_combo.findText(drive)
				if index >= 0:
					self.drive_combo.setCurrentIndex(index)
				# 전체 경로를 경로 입력창에 설정
				self.path_input.setText(storage_path)

	def select_path(self):
		"""경로 선택 다이얼로그"""
		current_drive = self.drive_combo.currentText()
		path = QFileDialog.getExistingDirectory(
			self,
			"Select Directory",
			current_drive,
			QFileDialog.ShowDirsOnly | QFileDialog.DontResolveSymlinks
		)

		if path:
			# 선택된 경로에서 드라이브 문자 추출 (예: "D:\path" -> "D:\")
			selected_drive = path.split(':')[0] + ':\\'

			# 현재 선택된 드라이브와 다른 경우
			if selected_drive != current_drive:
				# 드라이브 콤보박스에서 해당 드라이브 찾기
				index = self.drive_combo.findText(selected_drive)
				if index >= 0:
					# 드라이브 콤보박스 업데이트
					self.drive_combo.setCurrentIndex(index)

			# 경로 입력창 업데이트
			self.path_input.setText(path)
			# settings.ini 파일 업데이트 및 시그널 발생
			self.update_storage_path(path)

	def update_storage_path(self, path):
		"""settings.ini 파일의 저장 경로 업데이트"""
		if 'Recording' not in self.config:
			self.config['Recording'] = {}

		old_path = self.config['Recording'].get('save_path', '')
		if old_path != path:
			self.config['Recording']['save_path'] = path
			with open('settings.ini', 'w', encoding='utf-8') as configfile:
				self.config.write(configfile)

			# 시그널 발생
			self.path_changed.emit(path)

			# 경로 변경 알림창 표시
			msg_box = QMessageBox(
				QMessageBox.Information,
				"경로 변경",
				f"저장 경로가 변경되었습니다.\n\n이전 경로: {old_path}\n새 경로: {path}",
				QMessageBox.Ok,
				self
			)

			# OK 버튼의 크기 조정
			ok_button = msg_box.button(QMessageBox.Ok)
			ok_button.setFixedWidth(200)

			msg_box.exec()

	def save_settings(self):
		"""설정 저장"""
		# 설정값 업데이트
		settings_data = {
			'Extension': {
				'rep_number': self.rep_number_input.text()
			},
			'Network': {
				'ip': self.ip_combo.currentText(),
				'ap_ip': self.ap_ip_input.text()
			},
			'OtherSettings': {
				'disk_persent': self.disk_percent_input.text(),
				'disk_alarm': str(self.alarm_checkbox.isChecked()).lower()
			},
			'Recording': {
				'save_path': self.path_input.text(),
				'channels': '1',
				'sample_rate': '8000'
			}
		}

		# settings.ini 파일 업데이트
		for section, values in settings_data.items():
			if section not in self.config:
				self.config[section] = {}
			for key, value in values.items():
				self.config[section][key] = value

		# 파일 저장
		with open('settings.ini', 'w', encoding='utf-8') as configfile:
			self.config.write(configfile)

		# 설정 변경 시그널 발생
		self.settings_changed.emit(settings_data)

		QMessageBox.information(self, "설정 저장", "설정이 성공적으로 저장되었습니다.")
		self.close()

	def update_disk_info(self):
		"""디스크 정보 업데이트"""
		drive = self.drive_combo.currentText()
		if os.path.exists(drive):
			usage = psutil.disk_usage(drive)
			total_gb = usage.total / (1024**3)
			free_gb = usage.free / (1024**3)
			percent = int(usage.percent)

			self.disk_info_label.setText(
				f'Disk 정보: 총용량[{total_gb:.1f}GB], '
				f'남은용량 [{free_gb:.1f}GB], '
				f'사용률 [{percent}%]'
			)
			self.progress_bar.setValue(percent)

	def load_network_interfaces(self):
		"""이더넷 인터페이스 목록 로드"""
		# 모든 네트워크 인터페이스 조회
		interfaces = psutil.net_if_addrs()

		# 이더넷 인터페이스만 필터링
		ethernet_ips = []
		for interface, addrs in interfaces.items():
			for addr in addrs:
				if addr.family == socket.AF_INET:  # IPv4 주소만
					ethernet_ips.append(addr.address)

		# 콤보박스에 추가
		self.ip_combo.clear()
		self.ip_combo.addItems(ethernet_ips)

		# 현재 설정된 IP 선택
		current_ip = self.config['Network'].get('ip', '')
		index = self.ip_combo.findText(current_ip)
		if index >= 0:
			self.ip_combo.setCurrentIndex(index)

	def apply_stylesheet(self):
		"""다크모드 스타일시트 적용"""
		self.setStyleSheet("""
			QDialog {
				background-color: #1e1e1e;
			}
			QLabel {
				font-size: 12px;
				color: #ffffff;
				margin-top: 4px;
				padding-right: 15px;
			}
			QLineEdit, QComboBox {
				padding: 5px;
				border: 1px solid #333333;
				background-color: #2d2d2d;
				color: #ffffff;
			}
			QLineEdit:disabled {
				background-color: #383838;
				color: #808080;
			}
			QProgressBar {
				text-align: center;
				border: 1px solid #333333;
				background-color: #2d2d2d;
				color: #ffffff;
			}
			QProgressBar::chunk {
				background-color: #48c9b0;
			}
			QPushButton {
				padding: 8px 15px;
				background-color: #48c9b0;
				color: white;
				border: none;
				border-radius: 2px;
			}
			QPushButton:hover {
				background-color: #45b39d;
			}
			QPushButton:pressed {
				background-color: #40a391;
			}
			QCheckBox {
				margin-top: 4px;
				color: #ffffff;
			}
			QCheckBox::indicator {
				width: 13px;
				height: 13px;
				background-color: #2d2d2d;
				border: 1px solid #333333;
			}
			QCheckBox::indicator:checked {
				background-color: #48c9b0;
			}
			QGroupBox {
				border: 1px solid #333333;
				margin-top: 10px;
				color: #ffffff;
				background-color: #252525;
			}
			QComboBox::drop-down {
				border: none;
				background-color: #48c9b0;
				width: 25px;
			}
			QComboBox::down-arrow {
				image: none;
				border-left: 5px solid transparent;
				border-right: 5px solid transparent;
				border-top: 5px solid white;
				margin-top: 3px;
			}
			QComboBox:on {
				border: 1px solid #48c9b0;
			}
			QComboBox QAbstractItemView {
				background-color: #2d2d2d;
				color: #ffffff;
				selection-background-color: #48c9b0;
				selection-color: #ffffff;
				border: 1px solid #333333;
			}
		""")