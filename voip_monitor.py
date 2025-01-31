import pyshark
import psutil
import datetime
import configparser
import os
import logging
import socket
from PySide6.QtWidgets import (QApplication, QMainWindow, QTableWidget, 
							 QTableWidgetItem, QVBoxLayout, QWidget,
							 QComboBox, QPushButton, QHBoxLayout, QLabel)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import *
import sys
import threading
import asyncio

def setup_logging():
	"""로깅 설정"""
	logging.basicConfig(
		level=logging.INFO,
		format='%(asctime)s - %(levelname)s - %(message)s',
		handlers=[
			logging.FileHandler('voip_monitor.log', encoding='utf-8'),
			logging.StreamHandler()
		]
	)

def log_message(level, message):
	"""통합된 로깅 함수"""
	if level.lower() == "오류":
		logging.error(message)
	elif level.lower() == "경고":
		logging.warning(message)
	else:
		logging.info(message)

def load_config():
	"""설정 파일 로드"""
	try:
		config = configparser.ConfigParser()
		config.read('settings.ini', encoding='utf-8')
		return config
	except Exception as e:
		log_message("오류", f"설정 파일 로드 실패: {str(e)}")
		return None

def analyze_rtp(packet, voip_monitor):
	"""RTP 패킷 분석 및 음성 데이터 추출"""
	try:
		call_id = get_call_id_from_rtp(packet)
		if call_id and call_id in voip_monitor.active_calls:
			# RTP 엔드포인트 정보 저장
			src_ip = packet.ip.src
			dst_ip = packet.ip.dst
			src_port = packet.udp.srcport
			dst_port = packet.udp.dstport
			
			if 'media_endpoints' not in voip_monitor.active_calls[call_id]:
				voip_monitor.active_calls[call_id]['media_endpoints'] = []
				
			# 새로운 엔드포인트 추가
			endpoints = voip_monitor.active_calls[call_id]['media_endpoints']
			new_endpoint = {
				'ip': src_ip,
				'port': src_port,
			}
			if new_endpoint not in endpoints:
				endpoints.append(new_endpoint)
				
			new_endpoint = {
				'ip': dst_ip,
				'port': dst_port,
			}
			if new_endpoint not in endpoints:
				endpoints.append(new_endpoint)
	
	except Exception as e:
		log_message("오류", f"RTP 패킷 분석 중 오류: {str(e)}")

def get_call_id_from_rtp(packet):  # stream_id 매개변수 제거
	"""RTP 패킷과 관련된 Call-ID 찾기"""
	try:
		src_ip = packet.ip.src
		dst_ip = packet.ip.dst
		src_port = int(packet.udp.srcport)
		dst_port = int(packet.udp.dstport)
		
		# active_calls에서 이 RTP 스트림과 매칭되는 Call-ID 찾기
		for call_id, call_info in active_calls.items():
			if "media_endpoints" in call_info:
				for endpoint in call_info["media_endpoints"]:
					if (src_ip == endpoint["ip"] and src_port == endpoint["port"]) or \
					   (dst_ip == endpoint["ip"] and dst_port == endpoint["port"]):
						return call_id
		return None
	
	except Exception as e:
		log_message("오류", f"RTP Call-ID 매칭 오류: {str(e)}")
		return None

def load_sip_codes():
	"""SIP 응답 코드 로드"""
	sip_codes = {}
	try:
		with open('docs/SIPResponseCode.csv', 'r', encoding='utf-8') as f:
			next(f)  # 헤더 스킵
			for line in f:
				code, response = line.strip().split(',')
				sip_codes[code] = response
		return sip_codes
	except Exception as e:
		log_message("오류", f"SIP 코드 파일 로드 실패: {str(e)}")
		return {}

def extract_number(sip_header):
	"""SIP 헤더에서 전화번호 추출"""
	try:
		if not sip_header:
			return ''
			
		# From 헤더에서 큰따옴표 안의 값 추출
		if '"' in sip_header:
			quoted_part = sip_header.split('"')[1]  # "07086661427,1427" 에서 07086661427,1427 추출
			return quoted_part.split(',')[-1]  # 콤마가 있는 경우 마지막 값 반환 (1427)
			
		# To 헤더에서 sip: 다음의 번호 추출
		if 'sip:' in sip_header:
			number = sip_header.split('sip:')[1].split('@')[0]
			return number
			
		return str(sip_header)
		
	except Exception as e:
		log_message("오류", f"전화번호 추출 중 오류: {str(e)}")
		return ''

def analyze_sip(packet, voip_monitor):
	"""SIP 패킷 분석"""
	try:
		sip_layer = packet.sip
		call_id = sip_layer.call_id
		
		# 디버깅을 위한 로그 추가
		log_message("정보", f"SIP 패킷 분석 시작 - Call-ID: {call_id}")
		
		if hasattr(sip_layer, 'request_line'):
			# INVITE 요청 처리
			if 'INVITE' in sip_layer.request_line:
				log_message("정보", f"INVITE 요청 감지 - Call-ID: {call_id}")
				
				if call_id not in voip_monitor.active_calls:
					try:
						# From 헤더 파싱
						from_header = getattr(sip_layer, 'From', '')
						log_message("정보", f"From 헤더 전체: {from_header}")
						from_number = ''
						
						# From 헤더의 display info에서 번호 추출
						if '"' in from_header:
							display_info = from_header.split('"')[1]  # "070XXXXXXXX,1427" 추출
							if ',' in display_info:
								main_number, extension = display_info.split(',')
								from_number = f"{main_number}-{extension}"  # 070XXXXXXXX-1427 형식으로 변환
							else:
								from_number = display_info
						else:
							from_number = getattr(sip_layer, 'from_user', '')
							
						log_message("정보", f"파싱된 발신번호: {from_number}")
						
						# To 헤더 파싱
						to_header = getattr(sip_layer, 'To', '')
						log_message("정보", f"To 헤더: {to_header}")
						to_number = ''
						
						# To 헤더에서 번호 추출 시도
						try:
							if 'sip:' in to_header:
								to_parts = to_header.split('sip:')[1].split('@')[0]
								to_number = to_parts
							else:
								to_number = getattr(sip_layer, 'to_user', '')
						except:
							to_number = getattr(sip_layer, 'to_user', '')
							
						log_message("정보", f"추출된 수신번호: {to_number}")
						
						# 내선번호 판단 함수 추가
						def is_extension(number):
							"""내선번호 여부 확인 (4자리 && 1-9로 시작)"""
							return (number and 
									len(str(number)) == 4 and 
									str(number)[0] in ['1','2','3','4','5','6','7','8','9'])

						# 방향 결정
						direction = '수신' if is_extension(to_number) else '발신'
						
						# active_calls에 저장
						voip_monitor.active_calls[call_id] = {
							'start_time': datetime.datetime.now(),
							'status': '시도중',
							'result': '',
							'direction': direction,
							'from_number': from_number,
							'to_number': to_number,
							'call_id': call_id,
							'media_endpoints': []
						}
						log_message("정보", f"새로운 통화 추가됨 - Call-ID: {call_id}")
						
					except Exception as parse_error:
						log_message("오류", f"헤더 파싱 중 오류 상세: {str(parse_error)}")
						import traceback
						log_message("오류", traceback.format_exc())
			
			# BYE 요청 처리
			elif 'BYE' in sip_layer.request_line:
				log_message("정보", f"BYE 요청 감지 - Call-ID: {call_id}")
				if call_id in voip_monitor.active_calls:
					voip_monitor.active_calls[call_id]['status'] = '통화종료'
					bye_from_number = sip_layer.from_user
					if bye_from_number == voip_monitor.active_calls[call_id]['from_number']:
						voip_monitor.active_calls[call_id]['result'] = '발신종료'
					else:
						voip_monitor.active_calls[call_id]['result'] = '수신종료'
					voip_monitor.active_calls[call_id]['end_time'] = datetime.datetime.now()
			
			# CANCEL 요청 처리
			elif 'CANCEL' in sip_layer.request_line:
				log_message("정보", f"CANCEL 요청 감지 - Call-ID: {call_id}")
				if call_id in voip_monitor.active_calls:
					voip_monitor.active_calls[call_id]['status'] = '통화종료'
					voip_monitor.active_calls[call_id]['result'] = '발신취소'
					voip_monitor.active_calls[call_id]['end_time'] = datetime.datetime.now()
		
		# SIP Response 처리
		elif hasattr(sip_layer, 'status_line'):
			status_code = sip_layer.status_code
			log_message("정보", f"SIP 응답 감지 - Status Code: {status_code}, Call-ID: {call_id}")
			
			if call_id in voip_monitor.active_calls:
				if status_code == '180':  # Ringing
					voip_monitor.active_calls[call_id]['status'] = '벨울림'
				elif status_code == '200':  # OK
					if voip_monitor.active_calls[call_id]['status'] != '통화종료':
						voip_monitor.active_calls[call_id]['status'] = '통화중'
				elif status_code in ['486', '603']:  # Busy, Decline
					voip_monitor.active_calls[call_id]['status'] = '통화종료'
					voip_monitor.active_calls[call_id]['result'] = '수신거부'
					voip_monitor.active_calls[call_id]['end_time'] = datetime.datetime.now()
				elif status_code == '408':  # Request Timeout
					voip_monitor.active_calls[call_id]['status'] = '통화종료'
					voip_monitor.active_calls[call_id]['result'] = '응답없음'
					voip_monitor.active_calls[call_id]['end_time'] = datetime.datetime.now()
					
	except Exception as e:
		log_message("오류", f"SIP 패킷 분석 중 오류 상세: {str(e)}")
		# 스택 트레이스 출력
		import traceback
		log_message("오류", traceback.format_exc())

def handle_sip_response(status_code, call_id, sip_layer):
	"""SIP Response 처리"""
	try:
		if call_id in active_calls:
			current_status = active_calls[call_id]['status']
			
			# 시도중 상태에서의 응답 처리
			if current_status == '시도중':
				if status_code == '200':  # 200 OK - 통화 연결됨
					active_calls[call_id]['status'] = '통화중'
					active_calls[call_id]['result'] = ''
					
				elif status_code in ['486', '487', '603', '480']:  # 즉시 실패하는 응답
					active_calls[call_id]['status'] = '통화종료'
					active_calls[call_id]['result'] = '부재중'
					active_calls[call_id]['end_time'] = datetime.datetime.now()
					
				elif status_code in ['401', '407']:  # 인증 필요
					# 이미 인증 시도를 했다면 부재중으로 처리
					if active_calls[call_id].get('auth_attempted'):
						active_calls[call_id]['status'] = '통화종료'
						active_calls[call_id]['result'] = '부재중'
						active_calls[call_id]['end_time'] = datetime.datetime.now()
					else:
						active_calls[call_id]['auth_attempted'] = True
			
			# 통화중 상태에서의 응답 처리
			elif current_status == '통화중':
				if status_code == '200' and 'BYE' in str(sip_layer):  # 정상 종료
					active_calls[call_id]['status'] = '통화종료'
					active_calls[call_id]['result'] = 'OK'
					active_calls[call_id]['end_time'] = datetime.datetime.now()
					
	except Exception as e:
		log_message("오류", f"SIP 응답 처리 중 오류: {str(e)}")

def cleanup_old_calls():
	"""오래된 통화 정리"""
	current_time = datetime.datetime.now()
	for call_id in list(active_calls.keys()):
			call_start_time = active_calls[call_id].get("start_time")
			if call_start_time and (current_time - call_start_time).seconds > 7200:
				log_message("정보", f"오래된 통화 기록 제거: {call_id}")
				del active_calls[call_id]

def capture_voip_packets(interface, voip_monitor):
	"""패킷 캡처 함수"""
	try:
		# 새로운 이벤트 루프 생성 및 설정
		loop = asyncio.new_event_loop()
		asyncio.set_event_loop(loop)
		
		capture = pyshark.LiveCapture(interface=interface, display_filter='sip or rtp')
		for packet in capture.sniff_continuously():
			if 'SIP' in packet:
				analyze_sip(packet, voip_monitor)
			elif 'RTP' in packet:
				analyze_rtp(packet, voip_monitor)
	except Exception as e:
		log_message("오류", f"패킷 캡처 중 오류: {str(e)}")
	finally:
		# 캡처 종료 시 이벤트 루프 정리
		if 'capture' in locals():
			capture.close()
		if 'loop' in locals():
			loop.close()

def determine_stream_direction(packet):
	"""RTP 스트림의 방향 결정"""
	return {
		'source_ip': packet.ip.src,
		'source_port': packet.udp.srcport,
		'dest_ip': packet.ip.dst,
		'dest_port': packet.udp.dstport
	}

class VoipMonitor(QMainWindow):
	def __init__(self):
		super().__init__()
		self.setWindowTitle('VOIP MONITOR')
		self.setWindowIcon(QIcon("images/logo.png"))
		self.resize(1200, 600)
		
		# active_calls 초기화
		self.active_calls = {}
		
		# 스타일 설정
		self.setStyleSheet("""
			QMainWindow {
				background-color: black;
			}
			QLabel {
				color: white;
				font-size: 12px;
			}
		""")
		
		central_widget = QWidget()
		self.setCentralWidget(central_widget)
		layout = QVBoxLayout(central_widget)
		
		# 인터페이스 선택 영역
		interface_layout = QHBoxLayout()
		interface_layout.addSpacing(20)  # 왼쪽 여백 추가
		interface_label = QLabel("네트워크 인터페이스:")
		self.interface_combo = QComboBox()
		self.interface_combo.setStyleSheet("QComboBox { min-width: 200px; height: 27px; }")
		self.start_button = QPushButton("VOIP MONITOR START")
		self.start_button.setStyleSheet("QPushButton { min-width: 180px; height: 22px; background-color: #C533BE; }")
		
		interface_layout.addWidget(interface_label)
		interface_layout.addWidget(self.interface_combo)
		interface_layout.addWidget(self.start_button)
		interface_layout.addStretch()
		
		layout.addLayout(interface_layout)
		
		# 테이블 위젯 설정
		self.table = QTableWidget()
		self.table.setColumnCount(7)
		self.table.setHorizontalHeaderLabels([
			'시간', '통화 방향', '발신번호', '수신번호', '상태', '결과', 'Call-ID'
		])
		
		# 테이블 스타일 설정
		self.table.setStyleSheet("""
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
				background-color: #4A90E2;  /* 선택된 행의 배경색 */
				color: white;  /* 선택된 행의 텍스트 색상 */
			}						   
		""")
		
		# 컬럼 너비 설정
		self.table.setColumnWidth(0, 150)  # 시간
		self.table.setColumnWidth(1, 80)   # 통화 방향
		self.table.setColumnWidth(2, 120)  # 발신번호
		self.table.setColumnWidth(3, 120)  # 수신번호
		self.table.setColumnWidth(4, 80)   # 상태
		self.table.setColumnWidth(5, 80)   # 결과
		self.table.setColumnWidth(6, 400)  # Call-ID
		
		# 테이블 설정
		self.table.setSelectionBehavior(QTableWidget.SelectRows)
		self.table.setSelectionMode(QTableWidget.SingleSelection)
		self.table.setSortingEnabled(True)
		self.table.horizontalHeader().setStretchLastSection(True)
		
		layout.addWidget(self.table)
		
		# 인터페이스 목록 로드
		self.load_interfaces()
		
		# 이벤트 연결
		self.start_button.clicked.connect(self.start_capture)
		self.timer = QTimer()
		self.timer.timeout.connect(self.update_table)
		self.timer.start(100)  # 100ms 간격으로 업데이트

	def load_interfaces(self):
		"""네트워크 인터페이스 목록 로드"""
		interfaces = list(psutil.net_if_addrs().keys())
		for iface in interfaces:
			addrs = psutil.net_if_addrs()[iface]
			ip_addresses = [addr.address for addr in addrs if addr.family == socket.AF_INET]
			if ip_addresses:
				self.interface_combo.addItem(f"{iface} - {ip_addresses[0]}", iface)

	def start_capture(self):
		"""선택된 인터페이스로 캡처 시작"""
		interface = self.interface_combo.currentData()
		if interface:
			self.start_button.setEnabled(False)
			self.interface_combo.setEnabled(False)
			
			capture_thread = threading.Thread(
				target=capture_voip_packets,
				args=(interface, self),
				daemon=True
			)
			capture_thread.start()

	def update_table(self):
		"""테이블 업데이트"""
		try:
			# 테이블 정렬 상태 저장
			current_sort_column = self.table.horizontalHeader().sortIndicatorSection()
			current_sort_order = self.table.horizontalHeader().sortIndicatorOrder()
			
			# 현재 선택된 항목 저장
			current_row = self.table.currentRow()
			
			# 테이블 내용 초기화
			self.table.setRowCount(0)
			self.table.setRowCount(len(self.active_calls))
			
			for row, (call_id, call_info) in enumerate(self.active_calls.items()):
				# 시간
				time_item = QTableWidgetItem(call_info['start_time'].strftime('%Y-%m-%d %H:%M:%S'))
				self.table.setItem(row, 0, time_item)
				
				# 통화 방향
				direction_item = QTableWidgetItem(call_info.get('direction', ''))
				self.table.setItem(row, 1, direction_item)
				
				# 발신번호
				from_item = QTableWidgetItem(str(call_info.get('from_number', '')))
				self.table.setItem(row, 2, from_item)
				
				# 수신번호
				to_item = QTableWidgetItem(str(call_info.get('to_number', '')))
				self.table.setItem(row, 3, to_item)
				
				# 상태
				status_item = QTableWidgetItem(call_info.get('status', ''))
				self.table.setItem(row, 4, status_item)
				
				# 결과
				result_item = QTableWidgetItem(call_info.get('result', ''))
				self.table.setItem(row, 5, result_item)
				
				# Call-ID
				callid_item = QTableWidgetItem(call_id)
				self.table.setItem(row, 6, callid_item)
				
				# 각 셀을 가운데 정렬
				for col in range(7):
					item = self.table.item(row, col)
					if item:
						item.setTextAlignment(Qt.AlignCenter)
			
			# 정렬 상태 복원
			self.table.sortItems(current_sort_column, current_sort_order)
			
			# 선택 상태 복원
			if current_row >= 0 and current_row < self.table.rowCount():
				self.table.setCurrentCell(current_row, 0)
				
		except Exception as e:
			log_message("오류", f"테이블 업데이트 중 오류: {str(e)}")

if __name__ == '__main__':
	# 로깅 설정
	setup_logging()

	# 전역 변수 초기화
	active_calls = {}
	config = load_config()
	
	if not config:
		log_message("오류", "설정 파일 로드 실패")
		exit(1)

	# UI 애플리케이션 생성
	app = QApplication(sys.argv)
	window = VoipMonitor()
	window.show()
	
	try:
		sys.exit(app.exec())
	except Exception as e:
		log_message("오류", f"프로그램 실행 중 오류 발생: {str(e)}")