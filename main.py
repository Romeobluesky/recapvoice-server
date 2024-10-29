import sys
import warnings
from PyQt5.QtWidgets import (
	QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
	QGroupBox, QLabel, QLineEdit, QPushButton, QCheckBox,
	QTableWidget, QTableWidgetItem, QProgressBar, QStyle, QComboBox
)
from PyQt5.QtGui import QColor
from PyQt5.QtCore import Qt, QTimer, QTime, QDateTime
import psutil
from settings_popup import SettingsPopup  # 팝업창 import

warnings.filterwarnings("ignore", category=DeprecationWarning)

def create_led(label, color):
	widget = QWidget()
	layout = QHBoxLayout()
	led = QLabel()
	led.setFixedSize(15, 15)
	led.setStyleSheet(
		f'background-color: {color}; border-radius: 7px; border: 1px solid gray;'
	)
	layout.addWidget(led)
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
		self.setup_led_section()
		self.setup_disk_section()
		self.setup_line_section()
		self.setup_log_section()
		
		# 타이머 설정
		self.timer = QTimer(self)
		self.timer.timeout.connect(self.update_disk_usage)
		self.timer.start(5000)
		self.update_disk_usage()

	def setup_company_section(self):
		company_group = QGroupBox('회사정보')
		company_layout = QHBoxLayout()
		
		input_layout = QHBoxLayout()
		input_layout.addWidget(QLabel('대표번호:'))
		tel_input = QLineEdit()
		tel_input.setFixedHeight(tel_input.sizeHint().height() + 4)  # 높이 4px 증가
		input_layout.addWidget(tel_input)
		
		input_layout.addWidget(QLabel('회사명:'))
		company_input = QLineEdit()
		company_input.setFixedHeight(company_input.sizeHint().height() + 4)  # 높이 4px 증가
		input_layout.addWidget(company_input)
		
		input_layout.addWidget(QLabel('회사ID:'))
		id_input = QLineEdit()
		id_input.setFixedHeight(id_input.sizeHint().height() + 4)  # 높이 4px 증가
		input_layout.addWidget(id_input)
		
		button_layout = QHBoxLayout()
		settings_btn = QPushButton('환경설정')
		close_btn = QPushButton('닫기')
		
		# 버튼 크기 통일
		button_width = 80
		button_height = 25
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
		popup = SettingsPopup()
		popup.setGeometry(
			QStyle.alignedRect(
				Qt.LeftToRight,
				Qt.AlignCenter,
				popup.size(),
				self.frameGeometry()
			)
		)
		popup.exec_()

	def setup_record_section(self):
		record_group = QGroupBox('녹취정보')
		record_layout = QHBoxLayout()
		
		# Record IP 레이블과 ComboBox를 포함할 컨테이너 위젯 생성
		ip_container = QWidget()
		ip_layout = QHBoxLayout(ip_container)
		ip_layout.setContentsMargins(0, 0, 0, 0)  # 바깥 여백 제거
		ip_layout.setSpacing(0)  # 내부 간격 제거
		
		label = QLabel('Record IP:')
		label.setContentsMargins(0, 0, 0, 0)  # 레이블 여백 제거
		ip_layout.addWidget(label)
		
		ip_combo = QComboBox()
		ip_combo.setContentsMargins(0, 0, 0, 0)  # ComboBox 여백 제거
		ip_combo.setMinimumWidth(ip_combo.minimumWidth() + 500)  # 너비 30 증가
		ip_combo.addItems(['192.168.0.1', '192.168.0.2', '192.168.0.3'])
		ip_layout.addWidget(ip_combo)
		
		record_layout.addWidget(ip_container)
		record_layout.addSpacing(50)  # ComboBox와 체크박스 사이 간격
		
		record_layout.addWidget(QCheckBox('녹취자동시작'))
		record_layout.addWidget(QPushButton('녹취종료'))
		
		record_group.setLayout(record_layout)
		record_layout.setAlignment(Qt.AlignLeft)  # 왼쪽 정렬 추가
		self.main_layout.addWidget(record_group)

	def setup_led_section(self):
		led_group = QGroupBox('회선 상태')
		led_layout = QHBoxLayout()
		led_layout.addWidget(create_led('회선 Init ', 'yellow'))
		led_layout.addWidget(create_led('대 기 중 ', 'blue'))
		led_layout.addWidget(create_led('녹 취 중 ', 'green'))
		led_layout.addWidget(create_led('녹취안됨 ', 'red'))
		led_group.setLayout(led_layout)
		self.main_layout.addWidget(led_group)

	def setup_disk_section(self):
		disk_group = QGroupBox('디스크 정보')
		disk_layout = QHBoxLayout()
		disk_layout.addWidget(QLabel('녹취드라이버(D:) 사용률:'))
		self.progress_bar = QProgressBar()
		self.progress_bar.setStyleSheet("QProgressBar { text-align: center; }")
		self.progress_bar.setMinimum(0)
		self.progress_bar.setMaximum(100)
		disk_layout.addWidget(self.progress_bar)
		self.disk_usage_label = QLabel()
		disk_layout.addWidget(self.disk_usage_label)
		disk_group.setLayout(disk_layout)
		self.main_layout.addWidget(disk_group)

	def update_disk_usage(self):
		try:
			disk_usage = psutil.disk_usage('D:')
			total_gb = disk_usage.total / (1024**3)
			used_gb = disk_usage.used / (1024**3)
			free_gb = disk_usage.free / (1024**3)
			percent = int(disk_usage.percent)
			
			self.progress_bar.setValue(percent)
			self.disk_usage_label.setText(f'전체: {total_gb:.1f}GB 사용: {used_gb:.1f}GB 남은: {free_gb:.1f}GB')
		except Exception as e:
			self.disk_usage_label.setText('D드라이브 정보를 읽을 수 없습니다')

	def setup_line_section(self):
		line_group = QGroupBox('회선 리스트')
		line_layout = QVBoxLayout()
		
		self.line_table = QTableWidget()
		self.line_table.setColumnCount(8)
		self.line_table.setHorizontalHeaderLabels([
			'순번', '회선번호', '전화기 IP', '사용자명', 
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
			QTableWidget::item:selected {
				background-color: lightblue;
				color: black;
			}
			QHeaderView {
				background-color: black;
			}
			QHeaderView::section:selected {
				background-color: black;  /* 헤더 선택 시에도 검정색 유지 */
				color: white;
			}
		""")
		
		# 컬럼 너비 비율 설정
		header = self.line_table.horizontalHeader()
		header.setSectionResizeMode(0, header.Fixed)  # 순번
		header.setSectionResizeMode(7, header.Fixed)  # 상태
		self.line_table.setColumnWidth(0, 50)        # 순번 폭 고정
		self.line_table.setColumnWidth(7, 80)        # 상태 폭 고정
		
		# 나머지 컬럼들은 자동 조절
		for i in range(1, 7):
			header.setSectionResizeMode(i, header.Stretch)
		
		# 이블 높이 설정
		self.line_table.setMinimumHeight(300)
		
		# 행 번호 숨기기
		self.line_table.verticalHeader().setVisible(False)
		
		# 데이터 추가
		self.line_table.setRowCount(20)
		for i in range(20):
			items = [
				str(i+1),
				f'회선-{i+1}',
				f'192.168.0.{i+1}',
				f'사용자{i+1}',
				f'USER{i+1}',
				f'내용 {i+1}',
				f'기타 {i+1}'
			]
			for j, item in enumerate(items):
				table_item = QTableWidgetItem(item)
				if j not in [5, 6]:
					table_item.setFlags(table_item.flags() & ~Qt.ItemIsEditable)
				if j == 0:  # 순번 열은 중앙 정렬
					table_item.setTextAlignment(Qt.AlignCenter)
				self.line_table.setItem(i, j, table_item)
			
			# 태 컬럼 설정 (읽기 전용)
			status_item = QTableWidgetItem()
			if i in [2, 5, 8]:
				status_item.setText('로그아웃')
				status_item.setForeground(QColor('red'))
			else:
				status_item.setText('로그인')
				status_item.setForeground(QColor('blue'))
			status_item.setTextAlignment(Qt.AlignCenter)
			status_item.setFlags(status_item.flags() & ~Qt.ItemIsEditable)
			self.line_table.setItem(i, 7, status_item)

		line_layout.addWidget(self.line_table)
		line_group.setLayout(line_layout)
		self.main_layout.addWidget(line_group)

	def setup_log_section(self):
		log_group = QGroupBox('로그 리스트')
		log_layout = QVBoxLayout()
		
		self.log_table = QTableWidget()
		self.log_table.setColumnCount(6)
		self.log_table.setHorizontalHeaderLabels([
			'순번', '시간', '구분', '구분', '내용', '기타'
		])
		
		# 선택 모드 설정
		self.log_table.setSelectionBehavior(QTableWidget.SelectRows)
		self.log_table.setSelectionMode(QTableWidget.SingleSelection)
		
		# 스타일 시트 설정
		self.log_table.setStyleSheet("""
			QHeaderView::section {
				background-color: black;
				color: white;
				padding: 4px;
			}
			QTableWidget::item:selected {
				background-color: lightblue;
				color: black;
			}
			QHeaderView {
				background-color: black;
			}
			QHeaderView::section:selected {
				background-color: black;  /* 헤더 선택 시에도 검정색 유지 */
				color: white;
			}
		""")
		
		# 컬럼 너비 비율 설정
		header = self.log_table.horizontalHeader()
		header.setSectionResizeMode(0, header.Fixed)  # 순번
		self.log_table.setColumnWidth(0, 50)         # 순번 폭 고정
		
		# 나머지 컬럼들은 자동 조절
		for i in range(1, 6):
			header.setSectionResizeMode(i, header.Stretch)
		
		# 테이블 높이 설정
		self.log_table.setMinimumHeight(200)
		
		# 행 번호 숨기기
		self.log_table.verticalHeader().setVisible(False)
		
		# 데이터 추가
		self.log_table.setRowCount(20)
		current_datetime = QDateTime.currentDateTime().toString('yyyy-MM-dd hh:mm:ss')
		for i in range(20):
			items = [
				str(i+1),
				current_datetime,
				'구분A',
				'구분B',
				f'로그내용 {i+1}',
				f'기타 {i+1}'
			]
			for j, item in enumerate(items):
				table_item = QTableWidgetItem(item)
				table_item.setFlags(table_item.flags() & ~Qt.ItemIsEditable)
				if j == 0:  # 순번 열은 중앙 정렬
					table_item.setTextAlignment(Qt.AlignCenter)
				self.log_table.setItem(i, j, table_item)

		log_layout.addWidget(self.log_table)
		log_group.setLayout(log_layout)
		self.main_layout.addWidget(log_group)

if __name__ == '__main__':
	app = QApplication(sys.argv)
	window = MainWindow()
	window.show()
	sys.exit(app.exec_())
