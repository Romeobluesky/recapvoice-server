import pyshark
import psutil
import wave
import datetime
from scapy.all import UDP
import configparser
import os
import logging
import socket
from PySide6.QtWidgets import (QApplication, QMainWindow, QTableWidget, 
                             QTableWidgetItem, QVBoxLayout, QWidget,
                             QComboBox, QPushButton, QHBoxLayout, QLabel)
from PySide6.QtCore import Qt, QTimer
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

def save_audio(call_id, call_info):
	"""음성 데이터 WAV 파일로 저장"""
	try:
		if "streams" not in call_info or not call_info["streams"]:
			log_message("경고", f"통화 {call_id}에 저장할 음성 데이터가 없습니다.")
			return
		
		# Recording 설정 로드
		recording_config = load_config()
		save_path = recording_config['save_path']
		
		if not os.path.exists(save_path):
			log_message("경고", f"저장 경로가 존재하지 않습니다: {save_path}")
			os.makedirs(save_path, exist_ok=True)
			log_message("정보", f"저장 경로를 생성했습니다: {save_path}")
		
		# 저장 디렉토리 생성 (연/월/일/시간 구조)
		now = datetime.datetime.now()
		date_path = now.strftime('%Y\\%m\\%d\\%H')
		save_dir = os.path.join(save_path, date_path)
		os.makedirs(save_dir, exist_ok=True)
		
		# 각 스트림별로 저장
		timestamp = now.strftime('%H%M%S')
		for stream_id, stream_info in call_info["streams"].items():
			if stream_info["packets"]:
				# 발신자/수신자 정보 포함
				filename = os.path.join(
					save_dir, 
					f"{timestamp}_{call_id}_{stream_info['source_ip']}_{stream_info['dest_ip']}.wav"
				)
				
				# 정렬된 음성 데이터 생성
				sorted_packets = sorted(stream_info["packets"], 
									 key=lambda x: x["sequence"])
				audio_data = b''.join(packet["data"] for packet in sorted_packets)
				
				# WAV 파일 저장
				with wave.open(filename, 'wb') as wf:
					wf.setnchannels(recording_config['channels'])
					wf.setsampwidth(2)  # 16-bit
					wf.setframerate(recording_config['sample_rate'])
					wf.writeframes(audio_data)
				
				log_message("정보", f"음성 파일 저장 완료: {filename}")
		
	except Exception as e:
		log_message("오류", f"음성 파일 저장 중 오류: {str(e)}")

def analyze_rtp(packet):
	"""RTP 패킷 분석 및 음성 데이터 추출"""
	try:
		call_id = get_call_id_from_rtp(packet)
		if call_id and call_id in active_calls:
			# RTP 엔드포인트 정보 저장
			src_ip = packet.ip.src
			dst_ip = packet.ip.dst
			src_port = packet.udp.srcport
			dst_port = packet.udp.dstport
			
			if 'media_endpoints' not in active_calls[call_id]:
				active_calls[call_id]['media_endpoints'] = []
				
			# 새로운 엔드포인트 추가
			endpoints = active_calls[call_id]['media_endpoints']
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

def get_call_id_from_rtp(packet, stream_id):
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

def extract_number(sip_user):
	"""SIP User 필드에서 전화번호 추출"""
	try:
		if not sip_user:
			return ''
		# 특수문자 제거하고 숫자만 추출
		number = ''.join(c for c in str(sip_user) if c.isdigit())
		return number
	except Exception as e:
		log_message("오류", f"전화번호 추출 중 오류: {str(e)}")
		return ''

def analyze_sip(packet):
	"""SIP 패킷 분석"""
	try:
		sip_layer = packet.sip
		call_id = sip_layer.call_id
		
		if hasattr(sip_layer, 'request_line'):
			# INVITE 요청 처리
			if 'INVITE' in sip_layer.request_line:
				if call_id not in active_calls:
					to_number = extract_number(sip_layer.to_user)
					# 내선번호가 1xxx, 2xxx, 3xxx, 4xxx 형태라고 가정
					direction = '수신' if to_number and to_number[0] in ['1','2','3','4'] else '발신'
					
					active_calls[call_id] = {
						'start_time': datetime.datetime.now(),
						'status': '시도중',
						'result': '',
						'direction': direction,
						'from_number': extract_number(sip_layer.from_user),
						'to_number': to_number,
						'call_id': call_id
					}
			
			# CANCEL 요청 처리 (벨 울리는 중 발신자 종료)
			elif 'CANCEL' in sip_layer.request_line and call_id in active_calls:
				if active_calls[call_id]['status'] == '시도중':
					active_calls[call_id]['status'] = '통화종료'
					active_calls[call_id]['result'] = '수신전종료'
					active_calls[call_id]['end_time'] = datetime.datetime.now()
			
			# BYE 요청 처리
			elif 'BYE' in sip_layer.request_line and call_id in active_calls:
				if active_calls[call_id]['status'] == '통화중':
					active_calls[call_id]['status'] = '통화종료'
					bye_from_number = extract_number(sip_layer.from_user)
					if bye_from_number == active_calls[call_id]['from_number']:
						active_calls[call_id]['result'] = '발신종료'
					else:
						active_calls[call_id]['result'] = '수신종료'
					active_calls[call_id]['end_time'] = datetime.datetime.now()
	
		elif hasattr(sip_layer, 'status_line'):
			handle_sip_response(sip_layer.status_code, call_id, sip_layer)
			
	except Exception as e:
		log_message("오류", f"SIP 패킷 분석 중 오류: {str(e)}")

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
				save_audio(call_id, active_calls[call_id]["audio_frames"])
				del active_calls[call_id]

def start_capture(interface):
	"""패킷 캡처 시작"""
	try:
		# 새로운 이벤트 루프 생성 및 설정
		loop = asyncio.new_event_loop()
		asyncio.set_event_loop(loop)
		
		capture = pyshark.LiveCapture(
			interface=interface,
			bpf_filter="port 5060 or udp portrange 10000-20000"
		)
		
		log_message("정보", f"인터페이스 {interface}에서 패킷 캡처 시작")
		
		for packet in capture.sniff_continuously():
			try:
				if 'SIP' in packet:
					analyze_sip(packet)
				elif 'RTP' in packet:
					analyze_rtp(packet)
			except Exception as e:
				log_message("오류", f"패킷 분석 중 오류: {str(e)}")
				
	except Exception as e:
		log_message("오류", f"캡처 시작 중 오류: {str(e)}")
	finally:
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

class VoIPMonitorUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('VoIP 모니터')
        self.setGeometry(100, 100, 1200, 600)
        
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
        interface_label = QLabel("네트워크 인터페이스:")
        self.interface_combo = QComboBox()
        self.start_button = QPushButton("캡처 시작")
        
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
        
        # 컬럼 너비 설정
        self.table.setColumnWidth(0, 150)
        self.table.setColumnWidth(1, 80)
        self.table.setColumnWidth(2, 120)
        self.table.setColumnWidth(3, 120)
        self.table.setColumnWidth(4, 80)
        self.table.setColumnWidth(5, 80)
        self.table.setColumnWidth(6, 400)
        
        layout.addWidget(self.table)
        
        # 인터페이스 목록 로드
        self.load_interfaces()
        
        # 이벤트 연결
        self.start_button.clicked.connect(self.start_capture)
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_table)
        self.timer.start(500)

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
                target=start_capture,
                args=(interface,),
                daemon=True
            )
            capture_thread.start()

    def update_table(self):
        """active_calls 딕셔너리의 내용으로 테이블 업데이트"""
        self.table.setRowCount(len(active_calls))
        
        for row, (call_id, call_info) in enumerate(active_calls.items()):
            # 시간
            time_item = QTableWidgetItem(
                call_info['start_time'].strftime('%Y-%m-%d %H:%M:%S')
            )
            self.table.setItem(row, 0, time_item)
            
            # 통화 방향
            direction_item = QTableWidgetItem(call_info['direction'])
            self.table.setItem(row, 1, direction_item)
            
            # 발신번호
            from_item = QTableWidgetItem(call_info.get('from_number', ''))
            self.table.setItem(row, 2, from_item)
            
            # 수신번호
            to_item = QTableWidgetItem(call_info.get('to_number', ''))
            self.table.setItem(row, 3, to_item)
            
            # 상태
            status_item = QTableWidgetItem(call_info['status'])
            self.table.setItem(row, 4, status_item)
            
            # 결과
            result_item = QTableWidgetItem(call_info.get('result', ''))
            self.table.setItem(row, 5, result_item)
            
            # Call-ID
            callid_item = QTableWidgetItem(call_info.get('call_id', ''))
            self.table.setItem(row, 6, callid_item)
            
            # IP 주소 표시 (컬럼 7로 변경)
            if 'media_endpoints' in call_info:
                ip_addresses = [f"{ep['ip']}:{ep['port']}" for ep in call_info['media_endpoints']]
                ip_text = '\n'.join(ip_addresses)
            else:
                ip_text = ''
            ip_item = QTableWidgetItem(ip_text)
            self.table.setItem(row, 7, ip_item)
            
            # 포트 정보
            if 'media_endpoints' in call_info:
                ports = [str(ep['port']) for ep in call_info['media_endpoints']]
                port_text = ', '.join(ports)
            else:
                port_text = ''
            port_item = QTableWidgetItem(port_text)
            self.table.setItem(row, 8, port_item)

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
	window = VoIPMonitorUI()
	window.show()
	
	try:
		sys.exit(app.exec())
	except Exception as e:
		log_message("오류", f"프로그램 실행 중 오류 발생: {str(e)}")