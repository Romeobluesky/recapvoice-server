import os
import psutil
import configparser
import socket
import requests
import uuid
import netifaces  # 새로운 라이브러리 추가 필요

from PySide6.QtWidgets import (
	QDialog, QVBoxLayout, QLabel, QLineEdit, QPushButton,
	QHBoxLayout, QCheckBox, QComboBox, QProgressBar, QGroupBox, QFileDialog,
	QMessageBox
)
from PySide6.QtCore import Qt, Signal
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
	network_ip_changed = Signal(str)  # Network IP 변경 전용 신호

	def __init__(self, parent=None):
		super().__init__(parent)
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
			self.config['MongoDB'] = {
				'host': '192.168.0.61',
				'port': '27017',
				'database': 'packetwave',
				'username': '',
				'password': ''
			}
			self.config['Extension'] = {
				'rep_number': '000-0000-0000',
				'id_code': 'DIFK-0000-0000-0000',
				'get_interface_length': '4',
				'hardware_id': self.get_mac_address()
			}
			self.config['OtherSettings'] = {
				'disk_persent': '70',
				'disk_alarm': 'true'
			}

			# 설정 파일 저장
			with open('settings.ini', 'w', encoding='utf-8') as configfile:
				self.config.write(configfile)
		else:
			# BOM 처리를 위해 파일을 먼저 읽고 BOM 제거 후 ConfigParser로 처리
			try:
				with open('settings.ini', 'r', encoding='utf-8-sig') as f:
					content = f.read()
				# BOM이 제거된 내용으로 ConfigParser 파싱
				import io
				self.config.read_string(content)
			except Exception as e:
				# BOM 처리 실패 시 기본 방식으로 재시도
				print(f"BOM 처리 중 오류 발생, 기본 방식으로 재시도: {e}")
				self.config.read('settings.ini', encoding='utf-8')
			# MongoDB 섹션이 없을 경우 기본값으로 생성
			if 'MongoDB' not in self.config:
				self.config['MongoDB'] = {
					'host': '192.168.0.61',
					'port': '27017',
					'database': 'packetwave',
					'username': '',
					'password': ''
				}

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

		# UI 구성요소 추가
		main_layout.addWidget(self.create_company_section())
		# 섹션 간 간격 추가
		main_layout.addSpacing(10)
		main_layout.addWidget(self.create_record_section())
		# 동일한 간격 추가
		main_layout.addSpacing(10)
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

	def get_mac_address(self):
		"""이더넷 인터페이스의 MAC 주소 반환 (대문자로)"""
		try:
			# 모든 네트워크 인터페이스 가져오기
			interfaces = netifaces.interfaces()

			# 이더넷 인터페이스 찾기
			for interface in interfaces:
				# 루프백 인터페이스 제외
				if interface == 'lo' or interface.startswith('lo'):
					continue

				# 인터페이스 주소 정보 가져오기
				addresses = netifaces.ifaddresses(interface)

				# MAC 주소(AF_LINK) 정보가 있는지 확인
				if netifaces.AF_LINK in addresses:
					mac = addresses[netifaces.AF_LINK][0]['addr']
					# IPv4 주소가 있는 인터페이스인지 확인 (이더넷 연결 확인)
					if netifaces.AF_INET in addresses:
						# MAC 주소를 대문자로 변환하고 하이픈으로 변경하여 반환
						return mac.replace(':', '-').upper()

			# 이더넷 인터페이스를 찾지 못한 경우 첫 번째 MAC 주소 반환
			for interface in interfaces:
				if interface == 'lo' or interface.startswith('lo'):
					continue

				addresses = netifaces.ifaddresses(interface)
				if netifaces.AF_LINK in addresses:
					mac = addresses[netifaces.AF_LINK][0]['addr']
					# MAC 주소를 대문자로 변환하고 하이픈으로 변경하여 반환
					return mac.replace(':', '-').upper()

			# 백업 방법: 기존 방식 사용
			mac = uuid.UUID(int=uuid.getnode()).hex[-12:]
			# MAC 주소를 하이픈으로 구분하여 반환
			return "-".join([mac[e:e+2] for e in range(0, 11, 2)]).upper()

		except Exception as e:
			print(f"MAC 주소 가져오기 오류: {e}")
			# 오류 발생 시 기존 방식 사용
			mac = uuid.UUID(int=uuid.getnode()).hex[-12:]
			# MAC 주소를 하이픈으로 구분하여 반환
			return "-".join([mac[e:e+2] for e in range(0, 11, 2)]).upper()

	def create_company_section(self):
		"""회사 정보 섹션 생성"""
		company_group = QGroupBox()

		# 기존 수직 레이아웃 대신 수직 레이아웃으로 변경
		layout = QVBoxLayout()

		# 첫 번째 행: 대표번호와 AP 서버 IP
		first_row = QHBoxLayout()

		# 대표번호 입력필드
		self.rep_number_input = QLineEdit()
		self.rep_number_input.setText(self.config['Extension'].get('rep_number', ''))

		# AP 서버 IP 입력필드
		self.ap_ip_input = QLineEdit()
		self.ap_ip_input.setText(self.get_public_ip())
		self.ap_ip_input.setReadOnly(True)

		first_row.addWidget(QLabel('대표번호:'))
		first_row.addWidget(self.rep_number_input)
		first_row.addWidget(QLabel('공인서버 IP:'))
		first_row.addWidget(self.ap_ip_input)

		# 두 번째 행: 라이선스 No.와 하드웨어 ID
		second_row = QHBoxLayout()

		# 라이선스 No. 입력필드
		self.license_input = QLineEdit()
		self.license_input.setText(self.config['Extension'].get('license_no', ''))

		# 하드웨어 ID 입력필드
		self.hardware_id_input = QLineEdit()
		# 항상 현재 MAC 주소를 가져와서 설정 (설정 파일 값 무시)
		mac_address = self.get_mac_address()
		self.hardware_id_input.setText(mac_address)
		# 하드웨어 ID 필드를 읽기 전용으로 설정하여 사용자가 수정할 수 없게 함
		self.hardware_id_input.setReadOnly(True)

		second_row.addWidget(QLabel('라이선스:'))
		second_row.addWidget(self.license_input)
		second_row.addWidget(QLabel('하드웨어 ID:'))
		second_row.addWidget(self.hardware_id_input)

		# 두 행을 메인 레이아웃에 추가
		layout.addLayout(first_row)
		layout.addLayout(second_row)

		company_group.setLayout(layout)
		return company_group

	def create_record_section(self):
		"""녹취 정보 섹션 생성"""
		record_group = QGroupBox()
		layout = QVBoxLayout()

		# Database IP
		layout.addLayout(self.create_database_ip_section())

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
		record_ip_label = QLabel('포트미러링 IP:')
		record_ip_label.setFixedWidth(80)  # 라벨 너비 고정

		# 이더넷 인터페이스 콤보박스
		self.ip_combo = QComboBox()
		self.ip_combo.setFixedHeight(26)
		self.load_network_interfaces()

		layout.addWidget(record_ip_label)
		layout.addWidget(self.ip_combo)
		layout.setSpacing(10)  # 위젯 간 간격 설정

		return layout
	def create_database_ip_section(self):
		"""Database IP 섹션 생성"""
		layout = QHBoxLayout()

		# Database IP 라벨 생성 및 고정 너비 설정
		db_ip_label = QLabel('Database IP:')
		db_ip_label.setFixedWidth(80)  # 라벨 너비 고정

		# Database IP용 별도 콤보박스
		self.db_ip_combo = QComboBox()
		self.db_ip_combo.setFixedHeight(26)
		self.load_database_interfaces()

		layout.addWidget(db_ip_label)
		layout.addWidget(self.db_ip_combo)
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
		# 현재 MAC 주소 가져오기 (저장 시에도 항상 최신 MAC 주소 사용)
		current_mac = self.get_mac_address()

		# Network IP 변경 감지를 위해 이전 값 저장
		old_network_ip = self.config.get('Network', 'ip', fallback='') if 'Network' in self.config else ''
		new_network_ip = self.ip_combo.currentText()

		# 설정값 업데이트
		settings_data = {
			'Extension': {
				'rep_number': self.rep_number_input.text(),
				'license_no': self.license_input.text(),
				'hardware_id': current_mac  # 항상 현재 MAC 주소 사용
			},
			'Network': {
				'ip': self.ip_combo.currentText(),
				'ap_ip': self.ap_ip_input.text()
			},			'MongoDB': {
				'host': self.db_ip_combo.currentText(),
				'port': self.config['MongoDB']['port'] if 'MongoDB' in self.config and 'port' in self.config['MongoDB'] else '27017',
				'database': self.config['MongoDB']['database'] if 'MongoDB' in self.config and 'database' in self.config['MongoDB'] else 'packetwave',
				'username': self.config['MongoDB']['username'] if 'MongoDB' in self.config and 'username' in self.config['MongoDB'] else '',
				'password': self.config['MongoDB']['password'] if 'MongoDB' in self.config and 'password' in self.config['MongoDB'] else ''
			},
			'OtherSettings': {
				'disk_persent': self.disk_percent_input.text(),
				'disk_alarm': 'true' if self.alarm_checkbox.isChecked() else 'false'
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
				self.config[section][key] = str(value)

		# 파일 저장
		with open('settings.ini', 'w', encoding='utf-8') as configfile:
			self.config.write(configfile)

		# 설정 변경 시그널 발생
		self.settings_changed.emit(settings_data)
		self.path_changed.emit(settings_data['Recording']['save_path'])

		# Network IP 변경 시 별도 신호 발송
		if old_network_ip != new_network_ip:
			print(f"Network IP 변경 감지: {old_network_ip} → {new_network_ip}")
			self.network_ip_changed.emit(new_network_ip)

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
	def load_database_interfaces(self):
		"""Database IP용 이더넷 인터페이스 목록 로드"""
		# 모든 네트워크 인터페이스 조회
		interfaces = psutil.net_if_addrs()

		# 이더넷 인터페이스만 필터링
		ethernet_ips = []
		for interface, addrs in interfaces.items():
			for addr in addrs:
				if addr.family == socket.AF_INET:  # IPv4 주소만
					ethernet_ips.append(addr.address)

		# 콤보박스에 추가
		self.db_ip_combo.clear()
		self.db_ip_combo.addItems(ethernet_ips)

		# 현재 설정된 MongoDB host IP 선택
		current_db_ip = ''
		if 'MongoDB' in self.config and 'host' in self.config['MongoDB']:
			current_db_ip = self.config['MongoDB']['host']

		index = self.db_ip_combo.findText(current_db_ip)
		if index >= 0:
			self.db_ip_combo.setCurrentIndex(index)

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