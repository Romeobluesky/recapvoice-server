import os
import psutil
from PySide6.QtWidgets import (
	QDialog, QVBoxLayout, QLabel, QLineEdit, QPushButton, 
	QHBoxLayout, QCheckBox, QComboBox, QProgressBar, QGroupBox, QFileDialog
)
from PySide6.QtCore import Qt

class SettingsPopup(QDialog):
	# 상수 정의
	WINDOW_SIZE = (600, 300)
	BUTTON_SIZES = {
		'path_button': (100, 28),
		'usage_input': (50, None),
		'dialog_button': (80, 26)
	}
	
	def __init__(self):
		super().__init__()
		# 인스턴스 변수 초기화
		self.disk_info_label = None
		self.progress_bar = None
		self.drive_combo = None
		self.path_input = None
		self.init_ui()
		
	def init_ui(self):
		"""UI 초기화"""
		self.setWindowTitle('환경설정')
		self.resize(*self.WINDOW_SIZE)
		
		main_layout = QVBoxLayout()
		self.apply_stylesheet()
		
		# UI 구성요소 추가
		main_layout.addWidget(self.create_company_section())
		main_layout.addWidget(self.create_record_section())
		main_layout.addLayout(self.create_button_section())
		
		self.setLayout(main_layout)
		self.update_disk_info()
	
	def create_company_section(self):
		"""회사 정보 섹션 생성"""
		company_group = QGroupBox('회사 정보')
		layout = QHBoxLayout()
		
		fields = [
			('대표 번호:', QLineEdit()),
			('AP 서버 IP:', QLineEdit())
		]
		
		for label_text, widget in fields:
			layout.addWidget(QLabel(label_text))
			layout.addWidget(widget)
		
		company_group.setLayout(layout)
		return company_group
	
	def create_record_section(self):
		"""녹취 정보 섹션 생성"""
		record_group = QGroupBox('녹취 정보')
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
		layout.addWidget(QLabel('Record IP:'))
		layout.addWidget(QLineEdit())
		return layout
	
	def create_path_section(self):
		"""저장 경로 섹션 생성"""
		layout = QHBoxLayout()
		layout.addWidget(QLabel('저장 경로: '))
		
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
		layout.setAlignment(Qt.AlignLeft)
		
		layout.addWidget(QLabel('Disk 사용률:'))
		
		usage_input = QLineEdit()
		usage_input.setFixedWidth(self.BUTTON_SIZES['usage_input'][0])
		layout.addWidget(usage_input)
		
		layout.addWidget(QLabel('% 이상이면 Alarm 발생'))
		layout.addWidget(QCheckBox('Alarm 끄기'))
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
		
		# 버튼 높이만 고정
		save_button.setFixedHeight(27)
		cancel_button.setFixedHeight(27)
		
		cancel_button.clicked.connect(self.close)
		
		# 버튼을 1:1 비율로 레이아웃에 추가
		layout.addWidget(save_button, 1)
		layout.addWidget(cancel_button, 1)
		
		return layout
	
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
			self.path_input.setText(path)
	
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
	
	def apply_stylesheet(self):
		"""스타일시트 적용"""
		self.setStyleSheet("""
			QLabel {
				font-size: 12px;
				color: #333;
				margin-top: 4px;
				padding-right: 15px;
			}
			QLineEdit, QComboBox {
				padding: 5px;
				border: 1px solid #ccc;
			}
			QProgressBar {
				text-align: center;
				border: 1px solid #ccc;
			}
			QPushButton {
				padding: 8px 15px;
				background-color: #09225E;
				color: white;
				border: none;
			}
			QPushButton:hover {
				background-color: #000000;
				color: white;
			}
			QCheckBox {
				margin-top: 4px;
			}
			QGroupBox {
				border: 1px solid #ccc;
				margin-top: 10px;
			}
		""")