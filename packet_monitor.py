import pyshark
import psutil
import wave
import datetime
from scapy.all import UDP
import configparser
import os
import logging
import socket

def setup_logging():
	"""로깅 설정"""
	logging.basicConfig(
		level=logging.INFO,
		format='%(asctime)s - %(levelname)s - %(message)s',
		handlers=[
			logging.FileHandler('voip_monitor.log'),
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

		SAVE_PATH = config.get('Recording', 'SAVE_PATH', fallback='.')
		SAMPLE_RATE = config.getint('Recording', 'SAMPLE_RATE', fallback=8000)

		return SAVE_PATH, SAMPLE_RATE
	except Exception as e:
		log_message("오류", f"설정 파일 로드 실패: {str(e)}")
		return '.', 8000

def choose_interface():
	"""네트워크 인터페이스 선택"""
	interfaces = list(psutil.net_if_addrs().keys())

	if not interfaces:
		log_message("오류", "사용 가능한 네트워크 인터페이스가 없습니다.")
		return None

	print("\n사용 가능한 네트워크 인터페이스:")
	for idx, iface in enumerate(interfaces):
		addrs = psutil.net_if_addrs()[iface]
		ip_addresses = [addr.address for addr in addrs if addr.family == socket.AF_INET]
		print(f"{idx}: {iface} - IP: {ip_addresses or '없음'}")

	while True:
		try:
			choice = input("\n사용할 인터페이스의 번호를 입력하세요 (q: 종료): ")
			if choice.lower() == 'q':
				return None
			choice = int(choice)
			if 0 <= choice < len(interfaces):
				return interfaces[choice]
			print("올바른 번호를 입력해주세요.")
		except ValueError:
			print("숫자를 입력해주세요.")

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
		if 'RTP' in packet:
			rtp = packet.rtp
			# 소스/목적지 IP와 포트를 포함한 스트림 식별자 생성
			stream_id = f"{packet.ip.src}:{packet.udp.srcport}-{packet.ip.dst}:{packet.udp.dstport}"
			call_id = get_call_id_from_rtp(packet, stream_id)
			
			if call_id and call_id in active_calls:
				payload_type = int(rtp.payload_type)
				
				if payload_type in [0, 8]:  # PCMU 또는 PCMA
					audio_data = bytes(rtp.payload)
					direction = determine_stream_direction(packet)
					
					# 스트림별로 데이터 저장
					if "streams" not in active_calls[call_id]:
						active_calls[call_id]["streams"] = {}
					
					if stream_id not in active_calls[call_id]["streams"]:
						active_calls[call_id]["streams"][stream_id] = {
							"direction": direction,
							"packets": [],
							"start_time": datetime.datetime.now(),
							"source_ip": packet.ip.src,
							"source_port": packet.udp.srcport,
							"dest_ip": packet.ip.dst,
							"dest_port": packet.udp.dstport
						}
					
					active_calls[call_id]["streams"][stream_id]["packets"].append({
						"timestamp": rtp.timestamp,
						"sequence": rtp.sequence_number,
						"payload_type": payload_type,
						"data": audio_data
					})
					
					log_message("정보", f"RTP 패킷 캡처: Call-ID {call_id}, "
								f"Stream {stream_id}, Seq: {rtp.sequence_number}")
	
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

def analyze_sip(packet):
	"""SIP 패킷 분석"""
	if 'SIP' not in packet:
		return

	sip_layer = packet['SIP']
	call_id = sip_layer.get_field_value('call-id')
	
	try:
		# Request 분석
		method = sip_layer.get_field_value('request_method')
		if method:
			handle_sip_request(method, call_id, sip_layer)
			return

		# Response 분석
		status_code = sip_layer.get_field_value('status_code')
		if status_code:
			handle_sip_response(status_code, call_id, sip_layer)
			
	except Exception as e:
		log_message("오류", f"SIP 패킷 분석 중 오류: {str(e)}")

def handle_sip_request(method, call_id, sip_layer):
	"""SIP Request 처리"""
	if method == "INVITE":
		if call_id not in active_calls:
			# From/To URI에서 전화번호 추출
			from_number = sip_layer.get_field_value('from').split('@')[0].replace('sip:', '')
			to_number = sip_layer.get_field_value('to').split('@')[0].replace('sip:', '')
			
			active_calls[call_id] = {
				"sip_packets": [],
				"audio_frames": [],
				"status": "initiating",
				"start_time": datetime.datetime.now(),
				"from_number": from_number,  # 발신 번호
				"to_number": to_number,      # 수신 번호
				"call_info": f"{from_number} -> {to_number}"  # 통화 정보
			}
			log_message("정보", f"새로운 통화 시도: {from_number} -> {to_number}")
	
		# SIP 패킷 저장
		if call_id in active_calls:
			active_calls[call_id]["sip_packets"].append({
				"method": method,
				"timestamp": datetime.datetime.now(),
				"from_uri": sip_layer.get_field_value('from'),
				"to_uri": sip_layer.get_field_value('to')
			})

	elif method == "BYE":
		if call_id in active_calls:
			duration = datetime.datetime.now() - active_calls[call_id]["start_time"]
			log_message("정보", f"통화 종료: {call_id} (통화시간: {duration})")
			save_audio(call_id, active_calls[call_id]["audio_frames"])
			del active_calls[call_id]
	
	elif method == "REGISTER":
		log_message("정보", f"SIP 등록 요청: {sip_layer.get_field_value('from')}")
	
	elif method == "OPTIONS":
		log_message("정보", f"SIP 옵션 요청: {call_id}")

def handle_sip_response(status_code, call_id, sip_layer):
	"""SIP Response 처리"""
	response_desc = sip_codes.get(status_code, "Unknown Response")
	
	# Informational (1xx)
	if status_code.startswith('1'):
		if call_id in active_calls:
			active_calls[call_id]["status"] = "progressing"
			log_message("정보", f"통화 진행 중: {call_id} ({status_code} {response_desc})")
	
	# Success (2xx)
	elif status_code.startswith('2'):
		if call_id in active_calls:
			active_calls[call_id]["status"] = "established"
			log_message("정보", f"통화 연결됨: {call_id} ({status_code} {response_desc})")
	
	# Redirection (3xx)
	elif status_code.startswith('3'):
		log_message("정보", f"통화 리다이렉션: {call_id} ({status_code} {response_desc})")
	
	# Client Error (4xx)
	elif status_code.startswith('4'):
		log_message("경고", f"클라이언트 오류: {call_id} ({status_code} {response_desc})")
		if call_id in active_calls:
			del active_calls[call_id]
	
	# Server Error (5xx)
	elif status_code.startswith('5'):
		log_message("오류", f"서버 오류: {call_id} ({status_code} {response_desc})")
		if call_id in active_calls:
			del active_calls[call_id]
	
	# Global Error (6xx)
	elif status_code.startswith('6'):
		log_message("오류", f"전역 오류: {call_id} ({status_code} {response_desc})")
		if call_id in active_calls:
			del active_calls[call_id]

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
	cleanup_timer = 0
	capture = pyshark.LiveCapture(interface=interface, bpf_filter="port 5060")
	log_message("정보", f"패킷 캡처 시작: {interface}")

	try:
		for packet in capture.sniff_continuously():
			cleanup_timer += 1
			if cleanup_timer >= 1000:
				cleanup_old_calls()
				cleanup_timer = 0

			analyze_sip(packet)
			for call_id in list(active_calls.keys()):
				analyze_rtp(packet)
	except KeyboardInterrupt:
		log_message("정보", "사용자에 의해 캡처가 중단되었습니다.")
	except Exception as e:
		log_message("오류", f"캡처 중 오류 발생: {str(e)}")
	finally:
		capture.close()

def determine_stream_direction(packet):
	"""RTP 스트림의 방향 결정"""
	return {
		'source_ip': packet.ip.src,
		'source_port': packet.udp.srcport,
		'dest_ip': packet.ip.dst,
		'dest_port': packet.udp.dstport
	}

if __name__ == '__main__':
	# 로깅 설정
	setup_logging()

	# 전역 변수 초기화
	active_calls = {}
	SAVE_PATH, SAMPLE_RATE = load_config()
	sip_codes = load_sip_codes()  # SIP 응답 코드 로드

	# 메인 로직 실행
	interface = choose_interface()
	if interface:
		try:
			start_capture(interface)
		except Exception as e:
			log_message("오류", f"프로그램 실행 중 오류 발생: {str(e)}")
	else:
		log_message("정보", "프로그램을 종료합니다.")
