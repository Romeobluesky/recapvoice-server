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
import audioop  # 오디오 변환을 위해 추가

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
		
		# Recording 섹션 검증
		if 'Recording' in config:
			recording_config = {
				'save_path': config['Recording'].get('save_path', r'C:\\'),
				'channels': config['Recording'].getint('channels', 1),
				'sample_rate': config['Recording'].getint('sample_rate', 8000)
			}
			log_message("정보", f"녹취 설정 로드: {recording_config}")
			return recording_config
		else:
			log_message("오류", "Recording 섹션을 찾을 수 없습니다")
			return None
	except Exception as e:
		log_message("오류", f"설정 파일 로드 실패: {str(e)}")
		return None

def save_audio(call_id, call_info):
	"""음성 데이터 WAV 파일로 저장"""
	try:
		log_message("디버그", f"녹취 저장 시작 - Call-ID: {call_id}")
		
		# 설정 가져오기
		config = load_config()
		if not config:
			config = {
				'save_path': r"C:\\",  # 기본값
				'channels': 1,
				'sample_rate': 8000
			}
		
		# call_info 유효성 검사
		if not call_info or not isinstance(call_info, dict):
			log_message("경고", f"유효하지 않은 call_info - Call-ID: {call_id}")
			return
			
		if not has_valid_streams(call_info):
			log_message("경고", f"유효한 스트림 데이터 없음 - Call-ID: {call_id}")
			return
			
		if "streams" not in call_info:
			log_message("경고", f"streams 키가 없음 - Call-ID: {call_id}")
			return
			
		if not call_info["streams"]:
			log_message("경고", f"스트림 데이터 없음 - Call-ID: {call_id}")
			return
			
		# 스트림 정보 출력
		for stream_id, stream_info in call_info["streams"].items():
			packet_count = len(stream_info.get("packets", []))
			log_message("디버그", 
					   f"스트림 정보 - Stream ID: {stream_id}, "
					   f"패킷 수: {packet_count}, "
					   f"Source IP: {stream_info.get('source_ip')}")
		
		save_dir = config['save_path']
		if not os.path.exists(save_dir):
			os.makedirs(save_dir, exist_ok=True)
		
			now = datetime.datetime.now()
			timestamp = now.strftime('%Y%m%d_%H%M%S')
			
			for stream_id, stream_info in call_info["streams"].items():
				if not stream_info.get("packets"):
					continue
				
				# 파일명 형식: 날짜_시간_발신번호_수신번호_방향.wav
				filename = os.path.join(
					save_dir,
					f"{timestamp}_{call_info.get('from_number', 'unknown')}_{call_info.get('to_number', 'unknown')}_{stream_id}.wav"
				)
				
				# WAV 파일 생성 (설정값 적용)
				with wave.open(filename, 'wb') as wav_file:
					wav_file.setnchannels(config['channels'])
					wav_file.setsampwidth(2)  # 16-bit
					wav_file.setframerate(config['sample_rate'])
					
					# 패킷 정렬
					sorted_packets = sorted(stream_info["packets"], key=lambda x: x["sequence"])
					
					# 패킷 데이터 쓰기
					for packet in sorted_packets:
						wav_file.writeframes(packet["data"])
				
				log_message("정보", f"녹취 저장 완료: {filename}")
				
	except Exception as e:
		log_message("오류", f"녹취 저장 실패: {str(e)}")

def analyze_sdp(packet, call_id):
	"""SDP 정보 분석"""
	try:
		if call_id not in active_calls:
			return
			
		if 'SDP' not in str(packet.layers):
			return
			
		# SDP 정보 초기화
		if 'sdp_info' not in active_calls[call_id]:
			active_calls[call_id]['sdp_info'] = {}
			
		# SDP에서 미디어 정보 추출
		media_info = {
			'setup_frame': packet.number,
			'codec': 'G711' if 'PCMU' in str(packet) or 'PCMA' in str(packet) else 'UNKNOWN',
			'source_ip': packet.ip.src,
			'dest_ip': packet.ip.dst
		}
		
		active_calls[call_id]['sdp_info'][packet.number] = media_info
		log_message("디버그", f"SDP 정보 저장 - Call-ID: {call_id}, Frame: {packet.number}")
		
	except Exception as e:
		log_message("에러", f"SDP 분석 중 오류: {str(e)}")

def analyze_rtp(packet, call_id):
	"""RTP 패킷 분석"""
	try:
		if not is_rtp_packet(packet):
			return
		
		# RTP 패킷 정보 출력
		print("\n=== RTP 패킷 정보 ===")
		print(f"Frame Number: {packet.number}")
		print(f"Source IP: {packet.ip.src}")
		print(f"Source Port: {packet.udp.srcport}")
		print(f"Dest IP: {packet.ip.dst}")
		print(f"Dest Port: {packet.udp.dstport}")
		
		# RTP 데이터 추출 및 출력
		rtp_data = extract_rtp_data(packet)
		if rtp_data:
			print(f"Version: {rtp_data['version']}")
			print(f"Payload Type: {rtp_data['payload_type']} ({'PCMU' if rtp_data['payload_type'] == 0 else 'PCMA'})")
			print(f"Sequence: {rtp_data['sequence']}")
			print(f"Timestamp: {rtp_data['timestamp']}")
			print(f"SSRC: 0x{rtp_data['ssrc']:08x}")
			print(f"Payload Length: {len(rtp_data['data'])} bytes")
			print("==================\n")
		
		if call_id not in active_calls:
			log_message("경고", f"미등록 통화 RTP 패킷 감지 - Call-ID: {call_id}")
			return
			
		# streams 초기화
		if 'streams' not in active_calls[call_id]:
			active_calls[call_id]['streams'] = {}
			
		# 스트림 식별자 생성 (SSRC 기반)
		ssrc = rtp_data['ssrc']
		stream_id = f"{packet.ip.src}:{packet.udp.srcport}:{ssrc}"
		
		# 새 스트림 초기화
		if stream_id not in active_calls[call_id]['streams']:
			active_calls[call_id]['streams'][stream_id] = {
				'setup_frame': packet.number,
				'source_ip': packet.ip.src,
				'source_port': packet.udp.srcport,
				'dest_ip': packet.ip.dst,
				'dest_port': packet.udp.dstport,
				'ssrc': ssrc,
				'codec': 'PCMU' if rtp_data['payload_type'] == 0 else 'PCMA',
				'packets': []
			}
			log_message("디버그", f"새 RTP 스트림 생성 - Call-ID: {call_id}, Stream ID: {stream_id}")
		
		# 패킷 데이터 저장
		active_calls[call_id]['streams'][stream_id]['packets'].append({
			'frame_number': packet.number,
			'sequence': rtp_data['sequence'],
			'timestamp': rtp_data['timestamp'],
			'data': rtp_data['data']
		})
		
		log_message("디버그", 
				   f"RTP 패킷 저장 - Call-ID: {call_id}, "
				   f"Stream ID: {stream_id}, "
				   f"Sequence: {rtp_data['sequence']}, "
				   f"패킷 수: {len(active_calls[call_id]['streams'][stream_id]['packets'])}")
		
	except Exception as e:
		log_message("에러", f"RTP  처리 중 오류: {str(e)}")

def extract_rtp_data(packet):
	"""RTP 패킷에서 데이터 추출"""
	try:
		payload = bytes(packet.udp.payload)
		
		# RTP 헤더 파싱
		version = (payload[0] >> 6) & 0x03
		payload_type = payload[1] & 0x7F
		sequence = (payload[2] << 8) | payload[3]
		timestamp = int.from_bytes(payload[4:8], byteorder='big')
		ssrc = int.from_bytes(payload[8:12], byteorder='big')
		
		# 음성 데이터
		voice_data = payload[12:]
		
		return {
			'version': version,
			'payload_type': payload_type,
			'sequence': sequence,
			'timestamp': timestamp,
			'ssrc': ssrc,
			'data': voice_data
		}
		
	except Exception as e:
		log_message("에러", f"RTP 데이터 추출 중 오류: {str(e)}")
		return None

def is_rtp_packet(packet):
	"""RTP 패킷 검증"""
	try:
		if 'UDP' not in packet:
			return False
			
		# UDP 페이로드 가져오기
		payload = bytes(packet.udp.payload)
		if len(payload) < 12:  # RTP 헤더 최소 크기
			return False
			
		# RTP 버전 체크 (첫 2비트가 10인 확인)
		version = (payload[0] >> 6) & 0x03
		if version != 2:  # RFC 1889 Version (2)
			return False
			
		# Payload Type 확인 (G.711 PCMU=0, PCMA=8)
		payload_type = payload[1] & 0x7F
		if payload_type not in [0, 8]:  # G.711 코덱만 허용
			return False
			
		return True
		
	except Exception as e:
		log_message("에러", f"RTP 패킷 검증 중 오류: {str(e)}")
		return False

def get_call_id_from_rtp(packet, stream_id):
	"""RTP 패킷과 관련된 Call-ID 찾기"""
	try:
		src_ip = packet.ip.src
		
		# active_calls에서 이 RTP 스트림과 매칭되는 Call-ID 찾기
		for call_id, call_info in active_calls.items():
			if "media_endpoints" in call_info:
				for endpoint in call_info["media_endpoints"]:
					if src_ip == endpoint["ip"]:
						return call_id
		return None
	
	except Exception as e:
		print(f"RTP Call-ID 매칭 오류: {str(e)}")
		return None

def load_sip_codes():
	"""SIP 응답 드 로드"""
	sip_codes = {}
	try:
		with open('docs/SIPResponseCode.csv', 'r', encoding='utf-8') as f:
			next(f)  # 헤더 스킵
			for line in f:
				code, response = line.strip().split(',')
				sip_codes[code] = response
		return sip_codes
	except Exception as e:
		print(f"SIP 코드 파일 로드 실패: {str(e)}")
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
		print(f"전화번호 추출 중 오류: {str(e)}")
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
					direction = '수신' if to_number and to_number[0] in ['1','2','3','4'] else '발'
					
					active_calls[call_id] = {
						'start_time': datetime.datetime.now(),
						'status': '시도중',
						'result': '',
						'direction': direction,
						'from_number': extract_number(sip_layer.from_user),
						'to_number': to_number,
						'call_id': call_id,
						'streams': {},  # 스트림 저장용 딕셔너리 추가
						'media_endpoints': []  # RTP 드포인트 정보 저
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
					# 녹취 저장
					log_message("정", f"통화 종료 감지 - 녹취 저장 시작 - Call-ID: {call_id}")
					save_audio(call_id, active_calls[call_id])
					
					# 통화 상태 업데이트
					active_calls[call_id]['status'] = '통화종료'
					bye_from_number = extract_number(sip_layer.from_user)
					
					# 종료 주체 확인
					if bye_from_number == active_calls[call_id]['from_number']:
						active_calls[call_id]['result'] = '발신종료'
					else:
						active_calls[call_id]['result'] = '수신종료'
						
					# 종료 시간 기록
					active_calls[call_id]['end_time'] = datetime.datetime.now()
					
					# 통화 시간 계산 및 기록
					duration = active_calls[call_id]['end_time'] - active_calls[call_id]['start_time']
					active_calls[call_id]['duration'] = str(duration).split('.')[0]
					
					log_message("정보", 
							   f"통화 종료 리셋 - Call-ID: {call_id}, "
							   f"결과: {active_calls[call_id]['result']}, "
							   f"통화시간: {active_calls[call_id]['duration']}")
					
			elif hasattr(sip_layer, 'status_line'):
				handle_sip_response(sip_layer.status_code, call_id, sip_layer)
			
	except Exception as e:
		print(f"SIP 패킷 분석 중 오류: {str(e)}")

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
		print(f"SIP 응답 처리 중 오류: {str(e)}")

def cleanup_old_calls():
	"""오래된 통화 정리"""
	current_time = datetime.datetime.now()
	for call_id in list(active_calls.keys()):
			call_start_time = active_calls[call_id].get("start_time")
			if call_start_time and (current_time - call_start_time).seconds > 7200:
				print(f"오래된 통화 기록 제거: {call_id}")
				save_audio(call_id, active_calls[call_id]["audio_frames"])
				del active_calls[call_id]

def determine_stream_direction(packet):
	"""통화 방향 및 번 정보 결정"""
	src_port = int(packet.udp.srcport)
	dst_port = int(packet.udp.dstport)
	
	# 일반적으로 SIP 포트는 3000-3999 범위를 사용
	if 3000 <= src_port <= 3999:
		direction = "발신"
		local_num = f"{packet.ip.src}:{src_port}"
		remote_num = f"{packet.ip.dst}:{dst_port}"
	else:
		direction = "수신"
		local_num = f"{packet.ip.dst}:{dst_port}"
		remote_num = f"{packet.ip.src}:{src_port}"
	
	return direction, local_num, remote_num

def capture_packets(interface, ui_callback=None):
	"""패킷 패킷모니터 시작"""
	try:
		loop = asyncio.new_event_loop()
		asyncio.set_event_loop(loop)
		
		# SIP와 RTP 패킷 모두 캡처
		capture = pyshark.LiveCapture(
			interface=interface,
			bpf_filter="udp"
		)
		
		streams = {}
		wav_files = {}
		
		for packet in capture.sniff_continuously():
			try:
				if hasattr(packet, 'udp'):
					# SIP 패킷 처리 (포트 5060)
					if int(packet.udp.dstport) == 5060 or int(packet.udp.srcport) == 5060:
						if hasattr(packet, 'sip'):
							if hasattr(packet.sip, 'Method'):
								if packet.sip.Method == 'BYE':
									# 관련된 RTP 스트림 찾아서 상태 변경
									for stream_key in list(streams.keys()):
										streams[stream_key]['status'] = '녹음완료'
										if stream_key in wav_files and wav_files[stream_key]:
											wav_files[stream_key].close()
											wav_files[stream_key] = None
										if ui_callback:
											ui_callback(stream_key, streams[stream_key])
					
					# RTP 패킷 처리
					payload = bytes.fromhex(packet.udp.payload.replace(':', ''))
					
					if len(payload) >= 12:
						version = (payload[0] >> 6) & 0x03
						payload_type = payload[1] & 0x7F
						sequence = int.from_bytes(payload[2:4], byteorder='big')
						voice_data = payload[12:]
						
						if version == 2 and payload_type in [0, 8]:
							stream_key = f"{packet.ip.src}:{packet.udp.srcport}-{packet.ip.dst}:{packet.udp.dstport}"
							direction, local_num, remote_num = determine_stream_direction(packet)
							
							if stream_key not in streams:
								streams[stream_key] = {
									'start_time': datetime.datetime.now(),
									'packets': 0,
									'last_sequence': sequence,
									'codec': 'PCMA' if payload_type == 8 else 'PCMU',
									'status': '녹음중',
									'result': '',
									'direction': direction,
									'local_num': local_num,
									'remote_num': remote_num
								}
								
								# WAV 파일 생성
								save_dir = r"D:\PacketWaveRecord"
								if not os.path.exists(save_dir):
									os.makedirs(save_dir)
								
								local_num = local_num.replace(':', '_')
								remote_num = remote_num.replace(':', '_')
								timestamp = streams[stream_key]['start_time'].strftime('%Y%m%d_%H%M%S')
								
								filename = os.path.join(
									save_dir,
									f"{timestamp}_{direction}_{local_num}-{remote_num}.wav"
								)
								
								wav_files[stream_key] = wave.open(filename, 'wb')
								wav_files[stream_key].setnchannels(1)
								wav_files[stream_key].setsampwidth(2)
								wav_files[stream_key].setframerate(8000)
							
							# G.711 디코딩
							if payload_type == 8:  # PCMA (a-law)
								decoded_data = audioop.alaw2lin(voice_data, 2)
							else:  # PCMU (μ-law)
								decoded_data = audioop.ulaw2lin(voice_data, 2)
							
							# WAV 파일에 쓰기
							if stream_key in wav_files and wav_files[stream_key]:
								wav_files[stream_key].writeframes(decoded_data)
								streams[stream_key]['packets'] += 1
							
							if ui_callback:
								ui_callback(stream_key, streams[stream_key])
				
			except Exception as e:
				print(f"패킷 분석 중 오류: {str(e)}")
				
	except Exception as e:
		print(f"패킷모니터 시작 중 오류: {str(e)}")
	finally:
		# 모든 스트림 상태를 녹음완료로 변경
		for stream_key in streams:
			streams[stream_key]['status'] = '녹음완료'
			if ui_callback:
				ui_callback(stream_key, streams[stream_key])
		
		# WAV 파일들을 모두 닫기
		for wav_file in wav_files.values():
			if wav_file:
				try:
					wav_file.close()
				except:
					pass
		
		if 'loop' in locals():
			loop.close()

class PacketMonitor(QMainWindow):
	def __init__(self):
		super().__init__()
		#self.setWindowTitle('패킷 모니터')
		#self.setGeometry(100, 100, 1200, 600)
		self.setWindowTitle("Packet Monitor")
		self.resize(1200, 600)
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
		interface_layout.addSpacing(20)		# 왼쪽 여백 추가
		interface_label = QLabel("네트워크 인터페이스:")
		self.interface_combo = QComboBox()
		self.interface_combo.setStyleSheet("QComboBox { min-width: 200px; height: 27px; }")
		self.start_button = QPushButton("PACKET MONITOR START")
		self.start_button.setStyleSheet("QPushButton { min-width: 180px; height: 22px; background-color: #C533BE; }")

		interface_layout.addWidget(interface_label)
		interface_layout.addWidget(self.interface_combo)
		interface_layout.addWidget(self.start_button)
		interface_layout.addStretch()
		
		layout.addLayout(interface_layout)
		
		# 테블 위젯 설정
		self.table = QTableWidget()
		self.table.setColumnCount(8)
		self.table.setHorizontalHeaderLabels([
			'시간', '통화 방향', '발신번호', '수신번호', '상태', 
			'스트림', '코덱', '패킷 수'
		])
		
		# 컬 너 설정
		self.table.setColumnWidth(5, 280)  # 스트림 컬럼 280으로 변경
		self.table.setColumnWidth(6, 100)  # 코덱 컬럼
		
		layout.addWidget(self.table)
		
		# 인터페이스 목록 로드
		self.load_interfaces()
		
		# 이벤트 연결
		self.start_button.clicked.connect(self.start_capture)
		self.timer = QTimer()
		self.timer.timeout.connect(self.update_table)
		self.timer.start(500)
		
		# 스트림 정보 저장을 위한 딕셔너리
		self.streams = {}

	def load_interfaces(self):
		"""네트워크 인터이스 목록 로드"""
		interfaces = list(psutil.net_if_addrs().keys())
		for iface in interfaces:
			addrs = psutil.net_if_addrs()[iface]
			ip_addresses = [addr.address for addr in addrs if addr.family == socket.AF_INET]
			if ip_addresses:
				self.interface_combo.addItem(f"{iface} - {ip_addresses[0]}", iface)

	def start_capture(self):
		"""UI에서 패킷모니터 시작"""
		try:
			selected_interface = self.interface_combo.currentData()
			if not selected_interface:
				log_message("오류", "인터페이스를 선택해주세요")
				return
				
			# 캡처 스레드 시작
			self.capture_thread = threading.Thread(
				target=capture_packets,
				args=(selected_interface, self.add_stream_info),  # 콜백 추가
				daemon=True
			)
			self.capture_thread.start()
			
			self.start_button.setEnabled(False)
			self.start_button.setText("캡처 중...")
			
		except Exception as e:
			log_message("오류", f"패킷모니터 시작 실패: {str(e)}")

	def update_table(self):
		"""테이블 업데이트"""
		current_row = 0
		
		for stream_key, stream_info in self.streams.items():
			if current_row >= self.table.rowCount():
				self.table.insertRow(current_row)
			
			# 시간
			time_item = QTableWidgetItem(
				stream_info['start_time'].strftime('%Y-%m-%d %H:%M:%S')
			)
			time_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)  # 중앙 정렬
			
			# 통화 방향
			direction_item = QTableWidgetItem(stream_info['direction'])
			direction_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
			
			# 발신/수신 번호
			local_num_item = QTableWidgetItem(stream_info['local_num'])
			local_num_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
			remote_num_item = QTableWidgetItem(stream_info['remote_num'])
			remote_num_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
			
			# 상태
			status_item = QTableWidgetItem(stream_info['status'])
			status_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
			
			# 스트림 (왼쪽 정렬 유지)
			stream_item = QTableWidgetItem(stream_key)
			
			# 코덱
			codec_item = QTableWidgetItem(stream_info['codec'])
			codec_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
			
			# 패킷 수
			packets_item = QTableWidgetItem(str(stream_info['packets']))
			packets_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
			
			# 아이템 설정
			self.table.setItem(current_row, 0, time_item)
			self.table.setItem(current_row, 1, direction_item)
			self.table.setItem(current_row, 2, local_num_item)
			self.table.setItem(current_row, 3, remote_num_item)
			self.table.setItem(current_row, 4, status_item)
			self.table.setItem(current_row, 5, stream_item)
			self.table.setItem(current_row, 6, codec_item)
			self.table.setItem(current_row, 7, packets_item)
			
			current_row += 1

	def add_stream_info(self, stream_key, stream_info):
		"""스트림 정보 추가/업데이트"""
		self.streams[stream_key] = stream_info

def has_valid_streams(call_info):
	"""통화 정보에 유효한 스트림이 있는지 확인"""
	try:
		if not call_info:
			log_message("디버그", "call_info가 None입니다")
			return False
			
		if 'streams' not in call_info:
			log_message("디버그", "streams 키가 없습니다")
			return False
			
		if not call_info['streams']:
			log_message("디버그", "streams가 비어있습니다")
			return False
			
		# streams 내부의 패킷 데이터 확인
		for stream_id, stream in call_info['streams'].items():
			if 'packets' in stream and stream['packets']:
				log_message("디버그", f"유효한 스트림 발견: {stream_id}, 패킷 수: {len(stream['packets'])}")
				return True
				
		log_message("디버그", "모든 스트림에 킷이 없습니다")
		return False
		
	except Exception as e:
		log_message("에러", f"스트림 검증 중 오류: {str(e)}")
		return False

def test_has_valid_streams():
	"""has_valid_streams 함수 테스트"""
	# 테스트 케이스 1: streams 키가 없는 경우
	test_case1 = {}
	assert has_valid_streams(test_case1) == False
	
	# 스트 케이스 2: 빈 스트림
	test_case2 = {"streams": {}}
	assert has_valid_streams(test_case2) == False
	
	# 테스트 케이스 3: 유효한 스트림
	test_case3 = {
		"streams": {
			"stream1": {
				"packets": [{"data": b"test", "sequence": 1}]  # 실제 패킷 데이터가 있는 경우
			}
		}
	}
	assert has_valid_streams(test_case3) == True
	
	print("모든 테스트 통과!")

if __name__ == '__main__':
	# 테스트 실행
	test_has_valid_streams()
	
	# 로깅 설정
	setup_logging()

	# 전역 변수 초기화
	active_calls = {}
	config = load_config()
	
	if not config:
		log_message("오류", "정 파일 로드 실패")
		exit(1)

	# UI 애플리케이션 생성
	app = QApplication(sys.argv)
	window = PacketMonitor()
	window.show()
	
	try:
		sys.exit(app.exec())
	except Exception as e:
		log_message("오류", f"프로그램 실행 중 오류 발생: {str(e)}")
