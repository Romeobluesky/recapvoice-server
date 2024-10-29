import os
import psutil
from PyQt5.QtWidgets import (
	QDialog, QVBoxLayout, QLabel, QLineEdit, QPushButton, 
	QHBoxLayout, QCheckBox, QComboBox, QProgressBar, QGroupBox, QFileDialog
)
from PyQt5.QtCore import Qt

class SettingsPopup(QDialog):
	def __init__(self):
		super().__init__()
		self.setWindowTitle('환경설정')
		self.resize(600, 300)

		layout = QVBoxLayout()

		# 스타일시트 설정
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

		# 회사 정보
		company_group = QGroupBox('회사 정보')
		company_layout = QHBoxLayout()
		company_layout.addWidget(QLabel('대표 번호:'))
		company_layout.addWidget(QLineEdit())
		company_layout.addWidget(QLabel('AP 서버 IP:'))
		company_layout.addWidget(QLineEdit())
		company_group.setLayout(company_layout)
		layout.addWidget(company_group)

		# 녹취 정보
		record_group = QGroupBox('녹취 정보')
		record_layout = QVBoxLayout()

		# Record IP
		record_ip_layout = QHBoxLayout()
		record_ip_layout.addWidget(QLabel('Record IP:'))
		record_ip_layout.addWidget(QLineEdit())
		record_layout.addLayout(record_ip_layout)

		# 저장 경로
		path_layout = QHBoxLayout()
		path_layout.addWidget(QLabel('저장 경로: '))
		
		# 드라이브 목록 추가
		self.drive_combo = QComboBox()
		drives = [f"{d}:\\" for d in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ' if os.path.exists(f"{d}:\\")]
		self.drive_combo.addItems(drives)
		self.drive_combo.currentIndexChanged.connect(self.update_disk_info)
		path_layout.addWidget(self.drive_combo)
		
		# 파일 경로 입력 및 선택 (읽기 전용으로 변경)
		self.path_input = QLineEdit()
		self.path_input.setReadOnly(True)  # 읽기 전용으로 설정
		self.path_input.setStyleSheet("""
			QLineEdit {
				background-color: #f0f0f0;
				color: #333;
			}
		""")
		path_button = QPushButton('경로탐색')  # 버튼 텍스트 변경
		path_button.setFixedWidth(100)  # 버튼 너비 조정
		path_button.clicked.connect(self.select_path)
		path_layout.addWidget(self.path_input)
		path_layout.addWidget(path_button)
		
		record_layout.addLayout(path_layout)

		# Disk 정보
		self.disk_info_label = QLabel('Disk 정보: 총용량, 남은용량, 사용률(%)')
		record_layout.addWidget(self.disk_info_label)

		# 사용률 프로그래스바
		self.progress_bar = QProgressBar()
		record_layout.addWidget(self.progress_bar)

		# Disk 사용률 및 Alarm
		alarm_layout = QHBoxLayout()
		alarm_layout.setAlignment(Qt.AlignLeft)  # 전체 레이아웃 왼쪽 정렬
		
		disk_usage_label = QLabel('Disk 사용률:')
		alarm_layout.addWidget(disk_usage_label)
		
		usage_input = QLineEdit()
		usage_input.setFixedWidth(50)
		alarm_layout.addWidget(usage_input)
		
		percent_label = QLabel('% 이상이면 Alarm 발생')
		alarm_layout.addWidget(percent_label)
		
		alarm_checkbox = QCheckBox('Alarm 끄기')
		alarm_layout.addWidget(alarm_checkbox)
		
		# 나머지 공간을 채우기 위한 stretch 추가
		alarm_layout.addStretch()
		
		record_layout.addLayout(alarm_layout)

		record_group.setLayout(record_layout)
		layout.addWidget(record_group)

		# 버튼
		button_layout = QHBoxLayout()
		save_button = QPushButton('저장')
		cancel_button = QPushButton('취소')
		cancel_button.clicked.connect(self.close)
		button_layout.addWidget(save_button)
		button_layout.addWidget(cancel_button)
		layout.addLayout(button_layout)

		self.setLayout(layout)

		# 초기 Disk 정보 업데이트
		self.update_disk_info()

	def select_path(self):
		# 현재 선택된 드라이브 가져오기
		current_drive = self.drive_combo.currentText()
		
		# 파일 다이얼로그 실행 (시작 경로를 선택된 드라이브로 설정)
		path = QFileDialog.getExistingDirectory(
			self,
			"Select Directory",
			current_drive,  # 선택된 드라이브를 시작 경로로 설정
			QFileDialog.ShowDirsOnly | QFileDialog.DontResolveSymlinks
		)
		
		if path:
			self.path_input.setText(path)

	def update_disk_info(self):
		drive = self.drive_combo.currentText()
		if os.path.exists(drive):
			usage = psutil.disk_usage(drive)
			total_gb = usage.total / (1024**3)
			free_gb = usage.free / (1024**3)
			percent = int(usage.percent)
			self.disk_info_label.setText(f'Disk 정보: 총용량[{total_gb:.1f}GB], 남은용량 [{free_gb:.1f}GB], 사용률 [{percent}%]')
			self.progress_bar.setValue(percent)