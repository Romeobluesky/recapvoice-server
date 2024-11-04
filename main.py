import sys
import psutil
from pathlib import Path
import configparser
import socket

from PySide6.QtWidgets import (
	QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
	QGroupBox, QLabel, QLineEdit, QPushButton, QCheckBox,
	QTableWidget, QTableWidgetItem, QProgressBar, QStyle, QComboBox,
	QHeaderView
)
from PySide6.QtGui import QColor
from PySide6.QtCore import Qt, QTimer, QDateTime
from settings_popup import SettingsPopup

def create_led(label, color):
	widget = QWidget()
	layout = QHBoxLayout()
	layout.setAlignment(Qt.AlignCenter)
	layout.setContentsMargins(0, 0, 0, 0)

	led = QLabel()
	led.setObjectName("led_indicator")
	led.setFixedSize(15, 15)
	led.setStyleSheet(
		f'#led_indicator {{ '
		f'background-color: {color}; '
		f'border-radius: 7px; '
		f'border: 1px solid gray; '
		f'}}'
	)

	layout.addWidget(led)
	if label:
		layout.addWidget(QLabel(label))

	widget.setLayout(layout)
	return widget

class MainWindow(QMainWindow):
	def __init__(self):
		super().__init__()

		# 기본 윈도우 설정
		self.setWindowTitle('Packet Wave')
		self.setGeometry(100, 100, 1200, 800)

		# 중앙 위젯 설정
		central_widget = QWidget()
		self.setCentralWidget(central_widget)
		self.main_layout = QVBoxLayout(central_widget)

		# UI 섹션 추가
		self.setup_company_section()
		self.setup_record_section()

		# 회선상태와 디스크정보를 담을 컨테이너 생성
		status_container = QHBoxLayout()

		# 회선상태 섹션 (30%)
		led_group = QGroupBox('회선 상태')
		led_layout = QHBoxLayout()
		led_layout.addWidget(create_led('회선 Init ', 'yellow'))
		led_layout.addWidget(create_led('대 기 중 ', 'blue'))
		led_layout.addWidget(create_led('녹 취 중 ', 'green'))
		led_layout.addWidget(create_led('녹취안됨 ', 'red'))
		led_group.setLayout(led_layout)
		status_container.addWidget(led_group, 30)  # 30% 비율 설정

		# 디스크정보 섹션 (70%)
		disk_group = QGroupBox('디스크 정보')
		disk_layout = QHBoxLayout()

		# settings.ini에서 Storage 경로 읽기
		config = configparser.ConfigParser()
		config.read('settings.ini', encoding='utf-8')
		storage_path = config.get('Storage', 'path', fallback='D:\\')
		drive_letter = storage_path.split(':')[0]

		# 클래스 변수로 저장
		self.disk_label = QLabel(f'녹취드라이버 ( {drive_letter} : \\) 사용률:')
		self.progress_bar = QProgressBar()
		self.progress_bar.setStyleSheet("QProgressBar { text-align: center; }")
		self.progress_bar.setMinimum(0)
		self.progress_bar.setMaximum(100)
		self.disk_usage_label = QLabel()

		# 레이아웃에 추가
		disk_layout.addWidget(self.disk_label)
		disk_layout.addWidget(self.progress_bar)
		disk_layout.addWidget(self.disk_usage_label)

		disk_group.setLayout(disk_layout)
		status_container.addWidget(disk_group, 70)  # 70% 비율 설정

		# 메인 레이아웃에 컨테이너 추가
		self.main_layout.addLayout(status_container)

		self.setup_line_section()
		self.setup_log_section()

		# 타이머 설정
		self.timer = QTimer(self)
		self.timer.timeout.connect(self.update_disk_usage)
		self.timer.start(600000)  # 10분(600,000ms)으로 변경
		self.update_disk_usage()  # 초기 디스크 사용량 표시

	def setup_company_section(self):
		company_group = QGroupBox('회사 정보')
		company_layout = QHBoxLayout()

		input_layout = QHBoxLayout()

		# 대표번호
		label1 = QLabel('대표번호:')
		input_layout.addWidget(label1)
		tel_input = QLineEdit()
		tel_input.setFixedHeight(tel_input.sizeHint().height() + 4)
		input_layout.addWidget(tel_input)

		# 회사명
		label2 = QLabel('회사명:')
		input_layout.addWidget(label2)
		company_input = QLineEdit()
		company_input.setFixedHeight(company_input.sizeHint().height() + 4)
		input_layout.addWidget(company_input)

		# 회사ID
		label3 = QLabel('회사ID:')
		input_layout.addWidget(label3)
		id_input = QLineEdit()
		id_input.setFixedHeight(id_input.sizeHint().height() + 4)
		input_layout.addWidget(id_input)

		button_layout = QHBoxLayout()
		settings_btn = QPushButton('환경설정')
		close_btn = QPushButton('닫기')

		# 버튼 크기 통일
		button_width = 80
		button_height = 27
		settings_btn.setFixedSize(button_width, button_height)
		close_btn.setFixedSize(button_width, button_height)

		# 버튼 스타일 설정
		button_style = """
			QPushButton {
				background-color: #2196F3;
				color: white;
				border: none;
				padding: 2px;
			}
			QPushButton:hover {
				background-color: #1976D2;
			}
			QPushButton:pressed {
				background-color: #0D47A1;
			}
		"""
		settings_btn.setStyleSheet(button_style)
		close_btn.setStyleSheet(button_style)

		settings_btn.clicked.connect(self.show_settings_popup)
		close_btn.clicked.connect(self.close)

		button_layout.addWidget(settings_btn)
		button_layout.addWidget(close_btn)

		company_layout.addLayout(input_layout)
		company_layout.addLayout(button_layout)
		company_group.setLayout(company_layout)
		self.main_layout.addWidget(company_group)

	def show_settings_popup(self):
		settings_popup = SettingsPopup()
		settings_popup.path_changed.connect(self.on_path_changed)  # 새로운 메서드 연결
		settings_popup.setGeometry(
			QStyle.alignedRect(
				Qt.LeftToRight,
				Qt.AlignCenter,
				settings_popup.size(),
				self.frameGeometry()
			)
		)
		settings_popup.exec_()

	def on_path_changed(self, new_path):
		"""경로 변경 시 호출되는 메서드"""
		try:
			drive_letter = new_path.split(':')[0]

			# UI 업데이트
			self.disk_label.setText(f'녹취드라이버 ( {drive_letter} : ) 사용률:')

			# 디스크 정보 업데이트
			disk_usage = psutil.disk_usage(f"{drive_letter}:")
			total_gb = disk_usage.total / (1024**3)
			used_gb = disk_usage.used / (1024**3)
			free_gb = disk_usage.free / (1024**3)
			percent = int(disk_usage.percent)

			self.progress_bar.setValue(percent)
			self.disk_usage_label.setText(f'전체: {total_gb:.1f}GB | 사용중: {used_gb:.1f}GB | 남은용량: {free_gb:.1f}GB')
		except Exception as e:
			print(f"Error updating disk info: {e}")
			self.disk_usage_label.setText(f'드라이브 정보를 읽을 수 없습니다')

	def setup_record_section(self):
		record_group = QGroupBox('녹취정보')
		record_layout = QHBoxLayout()

		# Record IP 레이블과 ComboBox를 포함할 컨테이너 위젯 생성
		ip_container = QWidget()
		ip_layout = QHBoxLayout(ip_container)
		ip_layout.setContentsMargins(0, 0, 0, 0)
		ip_layout.setSpacing(0)

		label = QLabel('Record IP:')
		label.setContentsMargins(0, 0, 0, 0)
		ip_layout.addWidget(label)

		# IP 콤보박스 설정
		self.ip_combo = QComboBox()
		self.ip_combo.setContentsMargins(0, 0, 0, 0)
		self.ip_combo.setMinimumWidth(self.ip_combo.minimumWidth() + 500)
		self.load_network_interfaces()  # IP 주소 로드
		self.ip_combo.currentTextChanged.connect(self.update_ip_settings)
		ip_layout.addWidget(self.ip_combo)

		record_layout.addWidget(ip_container)
		record_layout.addSpacing(50)

		record_layout.addWidget(QCheckBox('녹취자동시작'))
		record_layout.addSpacing(30)

		# 녹취 토글 버튼 설정
		self.record_btn = QPushButton('녹취 ON')
		self.record_btn.setCheckable(True)
		self.record_btn.setFixedSize(120, 27)
		self.record_btn.setStyleSheet("""
			QPushButton {
				background-color: #FF0000;
				color: white;
				border: none;
				padding: 2px;
			}
			QPushButton:hover {
				background-color: #D32F2F;
			}
			QPushButton:pressed {
				background-color: #B71C1C;
			}
		""")
		self.record_btn.clicked.connect(self.toggle_recording)
		record_layout.addWidget(self.record_btn)

		record_group.setLayout(record_layout)
		record_layout.setAlignment(Qt.AlignLeft)
		self.main_layout.addWidget(record_group)

	def load_network_interfaces(self):
		"""시스템의 모든 네트워크 인터페이스의 IP 주소를 가져옴"""
		ip_addresses = []
		for interface, addrs in psutil.net_if_addrs().items():
			for addr in addrs:
				if addr.family == socket.AF_INET:  # IPv4 주소만 필터링
					ip_addresses.append(addr.address)
		self.ip_combo.clear()
		self.ip_combo.addItems(ip_addresses)

	def update_ip_settings(self, new_ip):
		"""settings.ini 파일의 IP 설정 업데이트"""
		try:
			config = configparser.ConfigParser()
			config.read('settings.ini', encoding='utf-8')
			if 'Network' not in config:
				config['Network'] = {}
			config['Network']['ip'] = new_ip

			with open('settings.ini', 'w', encoding='utf-8') as configfile:
				config.write(configfile)
		except Exception as e:
			print(f"설정 파일 업데이트 중 오류 발생: {e}")

	def toggle_recording(self):
		"""녹취 버튼 토글 처리"""
		if self.record_btn.isChecked():
			self.record_btn.setText("녹취 OFF")
			self.record_btn.setStyleSheet("""
				QPushButton {
					background-color: #808080;  /* 회색 */
					color: white;
					border: none;
					padding: 2px;
				}
				QPushButton:hover {
					background-color: #696969;  /* 진한 회색 */
				}
				QPushButton:pressed {
					background-color: #505050;  /* 더 진한 회색 */
				}
			""")
		else:
			self.record_btn.setText("녹취 ON")
			self.record_btn.setStyleSheet("""
				QPushButton {
					background-color: #FF0000;  /* 빨간색 */
					color: white;
					border: none;
					padding: 2px;
				}
				QPushButton:hover {
					background-color: #D32F2F;  /* 진한 빨간색 */
				}
				QPushButton:pressed {
					background-color: #B71C1C;  /* 더 진한 빨간색 */
				}
			""")

	def setup_line_section(self):
		line_group = QGroupBox('회선 리스트')
		line_layout = QVBoxLayout()

		self.line_table = QTableWidget()
		self.line_table.setObjectName("line_table")
		self.line_table.setColumnCount(9)
		self.line_table.setHorizontalHeaderLabels([
			'LED', 'NO', '회선번호', '전화기 IP', '사용자명',
			'사용자ID', '내용', '기타', '상태'
		])

		# 선택 모드 설정
		self.line_table.setSelectionBehavior(QTableWidget.SelectRows)
		self.line_table.setSelectionMode(QTableWidget.SingleSelection)

		# 스타일 시트 설정
		self.line_table.setStyleSheet("""
			QHeaderView::section {
				background-color: black;
				color: white;
				padding: 4px;
			}
			QTableWidget {
				alternate-background-color: #DDDDDD;  /* 홀수 행 배경색 */
			}
			QTableWidget::item:selected {
				background-color: lightblue;
				color: black;
			}
			QHeaderView {
				background-color: black;
			}
			QHeaderView::section:selected {
				background-color: black;
				color: white;
			}
		""")

		# 홀수 행 배경색 적용 설정
		self.line_table.setAlternatingRowColors(True)

		# 고정 너비 컬럼 설정
		fixed_widths = {
			0: 50,   # LED
			1: 50,   # NO
			2: 100,  # 회선번호
			3: 100,  # 전화기 IP
			4: 100,  # 사용자명
			5: 100,  # 사용자ID
			7: 200,  # 기타
			8: 80    # 상태
		}

		# 고정 너비 적용
		header = self.line_table.horizontalHeader()
		for col, width in fixed_widths.items():
			header.setSectionResizeMode(col, QHeaderView.Fixed)
			self.line_table.setColumnWidth(col, width)

		# 자동 조절 컬럼 설정 (내용)
		header.setSectionResizeMode(6, QHeaderView.Stretch)

		# 데이터 추가
		self.line_table.setRowCount(20)
		for i in range(20):
			# LED 컬럼에 LED 위젯 추가 (레이블 없이)
			led_widget = create_led('', 'blue')  # 빈 레이블로 변경
			self.line_table.setCellWidget(i, 0, led_widget)

			items = [
				str(20-i),  # NO
				f'회선-{20-i}',
				f'192.168.0.{20-i}',
				f'사용자{20-i}',
				f'USER{20-i}',
				f'PyMySQL은 아래의 6가지 패턴 순서대로 진행됩니다. 하나씩 실행해보면서 그 역할을 확인해봅시다. {20-i}',
				f'기타 {20-i}'
			]

			# 나머지 컬럼들에 데이터 추가
			for j, item in enumerate(items):
				table_item = QTableWidgetItem(item)
				if j not in [5, 6]:  # 내용과 기타 컬럼만 편집 가능
					table_item.setFlags(table_item.flags() & ~Qt.ItemIsEditable)
				if j in [0, 3, 4]:  # NO, 사용자명, 사용자ID는 중앙 정렬
					table_item.setTextAlignment(Qt.AlignCenter)
				self.line_table.setItem(i, j+1, table_item)  # j+1로 인덱스 조정

			# 상태 컬럼 설정
			status_item = QTableWidgetItem()
			if i in [2, 5, 8]:
				status_item.setText('로그아웃')
				status_item.setForeground(QColor('red'))
			else:
				status_item.setText('로그인')
				status_item.setForeground(QColor('blue'))
			status_item.setTextAlignment(Qt.AlignCenter)
			status_item.setFlags(status_item.flags() & ~Qt.ItemIsEditable)
			self.line_table.setItem(i, 8, status_item)

		line_layout.addWidget(self.line_table)
		line_group.setLayout(line_layout)
		self.main_layout.addWidget(line_group, stretch=2)

		# 행 높이 설정
		self.line_table.verticalHeader().setDefaultSectionSize(25)  # 25px로 설정

		# 행 번호(인덱스) 컬럼 숨기기
		self.line_table.verticalHeader().setVisible(False)

	def setup_log_section(self):
		log_group = QGroupBox('로그 리스트')
		log_layout = QVBoxLayout()

		self.log_table = QTableWidget()
		self.log_table.setObjectName("log_table")
		self.log_table.setColumnCount(6)
		self.log_table.setHorizontalHeaderLabels([
			'NO', '시간', '구분', '구분', '내용', '기타'
		])

		# 선택 모드 설정
		self.log_table.setSelectionBehavior(QTableWidget.SelectRows)
		self.log_table.setSelectionMode(QTableWidget.SingleSelection)

		# 스타일 시트 설정
		self.log_table.setStyleSheet("""
			QHeaderView::section {
				background-color: #333333;
				color: white;
				padding: 4px;
			}
			QTableWidget {
				alternate-background-color: #DDDDDD;  /* 홀수 행 배경색 */
			}
			QTableWidget::item:selected {
				background-color: lightblue;
				color: black;
			}
			QHeaderView {
				background-color: #333333;
			}
			QHeaderView::section:selected {
				background-color: #333333;
				color: white;
			}
		""")

		# 홀수 행 배경색 적용 설정
		self.log_table.setAlternatingRowColors(True)

		# 컬럼 너비 설정
		header = self.log_table.horizontalHeader()

		# 고정 너비 컬럼 설정
		fixed_widths = {
			0: 50,    # NO
			1: 150,   # 시간
			2: 100,   # 구분
			3: 100,   # 구분
			5: 200    # 기타
		}

		# 고정 너비 적용
		for col, width in fixed_widths.items():
			header.setSectionResizeMode(col, QHeaderView.Fixed)
			self.log_table.setColumnWidth(col, width)

		# 자동 조절 컬럼 설정 (내용)
		header.setSectionResizeMode(4, QHeaderView.Stretch)  # 내용 컬럼만 Stretch

		# 테이블 높이 설정
		self.log_table.setMinimumHeight(200)

		# 행 번호 숨기기
		self.log_table.verticalHeader().setVisible(False)

		# 데이터 추가
		self.log_table.setRowCount(20)
		current_datetime = QDateTime.currentDateTime().toString('yyyy-MM-dd hh:mm:ss')
		for i in range(20):
			items = [
				str(20-i),
				current_datetime,
				'구분A',
				'구분B',
				f'로그내용 {20-i}',
				f'기타 {20-i}'
			]
			for j, item in enumerate(items):
				table_item = QTableWidgetItem(item)
				table_item.setFlags(table_item.flags() & ~Qt.ItemIsEditable)
				if j in [0, 1, 2, 3]:  # NO, 시간, 구분A, 구분B
					table_item.setTextAlignment(Qt.AlignCenter)
				self.log_table.setItem(i, j, table_item)

		log_layout.addWidget(self.log_table)
		log_group.setLayout(log_layout)
		self.main_layout.addWidget(log_group, stretch=1)

		# 행 높이 설정
		self.log_table.verticalHeader().setDefaultSectionSize(25)  # 25px로 설정

	def update_disk_usage(self):
		try:
			disk_usage = psutil.disk_usage('D:')
			total_gb = disk_usage.total / (1024**3)
			used_gb = disk_usage.used / (1024**3)
			free_gb = disk_usage.free / (1024**3)
			percent = int(disk_usage.percent)

			self.progress_bar.setValue(percent)
			self.disk_usage_label.setText(f'전체: {total_gb:.1f}GB | 사용중: {used_gb:.1f}GB | 남은용량: {free_gb:.1f}GB')
		except Exception as e:
			self.disk_usage_label.setText('D드라이브 정보를 읽을 수 없습니다')

# QSS 파일 로드 함수 추가
def load_stylesheet():
	qss_file = Path(__file__).parent / "styles" / "styles.qss"
	if qss_file.exists():
		with open(qss_file, "r", encoding='utf-8') as f:
			return f.read()
	return ""

if __name__ == '__main__':
	app = QApplication(sys.argv)
	app.setStyle('Fusion')

	# QSS 스타일시트 적용
	app.setStyleSheet(load_stylesheet())

	window = MainWindow()
	window.show()
	sys.exit(app.exec())