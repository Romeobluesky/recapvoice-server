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
	try:
		if 'SIP' not in packet:
			return

		sip = packet.sip
		print("\r[DEBUG] SIP 패킷 감지됨", flush=True)
		
		if hasattr(sip, 'call_id'):
			call_id = sip.call_id
			print(f"\r[DEBUG] Call-ID: {call_id}", flush=True)
		else:
			return

		if hasattr(sip, 'request_line'):
			method = sip.request_line.split()[0]
			print(f"\r[DEBUG] Request: {method}", flush=True)
			handle_sip_request(method, call_id, sip, packet)
		
		elif hasattr(sip, 'status_line'):
			status_code = sip.status_line.split()[1]
			print(f"\r[DEBUG] Response: {status_code}", flush=True)
			handle_sip_response(status_code, call_id, sip)
			
	except Exception as e:
		print(f"\r[ERROR] SIP 패킷 분석 중 오류: {str(e)}", flush=True)

def handle_sip_request(method, call_id, sip_layer, packet):
	"""SIP Request 처리"""
	try:
		if method == "INVITE":
			print("\r[DEBUG] INVITE 요청 처리 시작", flush=True)
			
			# From/To 헤더 접근 방식 수정
			from_header = getattr(sip_layer, 'from')  # from_ -> from
			to_header = getattr(sip_layer, 'to')
			
			print(f"\r[DEBUG] From: {from_header}", flush=True)
			print(f"\r[DEBUG] To: {to_header}", flush=True)
			
			from_number = from_header.split('@')[0].split(':')[-1]
			to_number = to_header.split('@')[0].split(':')[-1]
			
			# settings.ini에서 IP 가져오기
			config = configparser.ConfigParser()
			config.read('settings.ini', encoding='utf-8')
			network_ip = config.get('Network', 'ip')
			
			# 발신/수신 구분
			source_ip = packet.ip.src
			call_direction = "발신" if source_ip in network_ip.split(',') else "수신"
			
			if call_id not in active_calls:
				active_calls[call_id] = {
					"direction": call_direction,
					"status": "시도중",
					"start_time": datetime.datetime.now(),
					"from_number": from_number,
					"to_number": to_number,
					"audio_frames": {"streams": {}}
				}
				print(f"\r통화 시작: [{call_direction}] {from_number} -> {to_number}", flush=True)
	
	except Exception as e:
		print(f"\r[ERROR] SIP 요청 처리 중 오류: {str(e)}", flush=True)
		import traceback
		print(traceback.format_exc())

def handle_sip_response(status_code, call_id, sip_layer):
	"""SIP Response 처리"""
	try:
		if call_id in active_calls:
			direction = active_calls[call_id].get("direction", "알수없음")
			from_number = active_calls[call_id].get("from_number", "알수없음")
			to_number = active_calls[call_id].get("to_number", "알수없음")
			
			# sip_codes 로드
			sip_codes = load_sip_codes()
			status_desc = sip_codes.get(str(status_code), "알수없는 응답")
			call_info = f"[{direction}] {from_number} -> {to_number}"
			
			# 상태 메시지 출력 형식
			status_msg = f"통화 상태: {call_info} ({status_code} {status_desc})"
			
			print(f"\r{status_msg:<100}", flush=True)
			
			if status_code == "100":
				active_calls[call_id]["status"] = "시도중"
			elif status_code == "180":
				active_calls[call_id]["status"] = "벨울림"
			elif status_code == "182":
				active_calls[call_id]["status"] = "대기중"
			elif status_code == "183":
				active_calls[call_id]["status"] = "호처리중"
			elif status_code == "200":
				active_calls[call_id]["status"] = "통화중"
			elif status_code == "401" or status_code == "407":
				active_calls[call_id]["status"] = "인증필요"
			elif status_code.startswith('4'):
				active_calls[call_id]["status"] = "실패"
				if status_code not in ["401", "407"]:
					del active_calls[call_id]
			elif status_code.startswith('5'):
				active_calls[call_id]["status"] = "서버오류"
				del active_calls[call_id]
			elif status_code.startswith('6'):
				active_calls[call_id]["status"] = "전역오류"
				del active_calls[call_id]
	
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
	cleanup_timer = 0
	# SIP와 RTP 패킷 모두 캡처하도록 필터 수정
	capture = pyshark.LiveCapture(interface=interface, bpf_filter="port 5060 or udp portrange 10000-20000")
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
	config = load_config()
	if not config:
		log_message("오류", "설정 파일 로드 실패")
		exit(1)

	# 메인 로직 실행
	interface = choose_interface()
	if interface:
		try:
			start_capture(interface)
		except Exception as e:
			log_message("오류", f"프로그램 실행 중 오류 발생: {str(e)}")
	else:
		log_message("정보", "프로그램을 종료합니다.")
