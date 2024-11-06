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

def save_audio(call_id, frames):
	"""음성 데이터 WAV 저장"""
	try:
		filename = os.path.join(SAVE_PATH, f"call_recording_{call_id}_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.wav")
		os.makedirs(os.path.dirname(filename), exist_ok=True)

		with wave.open(filename, 'wb') as wf:
			wf.setnchannels(1)
			wf.setsampwidth(2)
			wf.setframerate(SAMPLE_RATE)
			wf.writeframes(b''.join(frames))
		log_message("정보", f"음성 파일 저장 완료: {filename}")
	except Exception as e:
		log_message("오류", f"음성 파일 저장 실패: {str(e)}")

def analyze_rtp(packet, call_id):
	"""RTP 패킷 분석"""
	if packet.haslayer(UDP):
		udp_layer = packet[UDP]
		if 10000 <= udp_layer.dport <= 20000:
			rtp_payload = bytes(udp_layer.payload)
			if len(active_calls[call_id]["audio_frames"]) < 100000:
				active_calls[call_id]["audio_frames"].append(rtp_payload)
			else:
				log_message("경고", f"통화 {call_id}의 버퍼가 가득 찼습니다.")

def analyze_sip(packet):
	"""SIP 패킷 분석"""
	if 'SIP' in packet:
		sip_layer = packet['SIP']
		sip_method = sip_layer.get_field_value('request_method')
		call_id = sip_layer.get_field_value('call-id')

		if sip_method == "INVITE":
			active_calls[call_id] = {
				"audio_frames": [],
				"status": "active",
				"start_time": datetime.datetime.now()
			}
			log_message("정보", f"통화 시도: {call_id}")
		elif sip_method == "BYE" and call_id in active_calls:
			log_message("정보", f"통화 종료: {call_id}")
			save_audio(call_id, active_calls[call_id]["audio_frames"])
			del active_calls[call_id]
		elif sip_layer.get_field_value('status_code') == '100':
			log_message("정보", f"통화 발신가능: {call_id}")            
		elif sip_layer.get_field_value('status_code') == '183':
			log_message("정보", f"통화 중: {call_id}")
		elif sip_method == "INVITE IN":
			log_message("정보", f"온 전화 받는 주: {call_id}")
		elif sip_method == "IN CALL":
			log_message("정보", f"한 전화 받는 중: {call_id}")            
		elif sip_layer.get_field_value('status_code') == '200' and sip_method != "BYE":
			log_message("정보", f"통화 수신가능: {call_id}")        
		elif sip_layer.get_field_value('status_code') == '200' and sip_method == "BYE":
			log_message("정보", f"통화.종료: {call_id}")
		elif sip_layer.get_field_value('status_code') == '407':
			log_message("정보", f"전화거는 중..: {call_id}")
		elif sip_layer.get_field_value('status_code') == '407' and sip_method == '200':
			log_message("정보", f"통화연결 성공: {call_id}")
		elif sip_layer.get_field_value('status_code') in ['403', '404', '487']:
			log_message("경고", f"통화 실패: {call_id} (코드: {sip_layer.get_field_value('status_code')})")

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
				analyze_rtp(packet, call_id)
	except KeyboardInterrupt:
		log_message("정보", "사용자에 의해 캡처가 중단되었습니다.")
	except Exception as e:
		log_message("오류", f"캡처 중 오류 발생: {str(e)}")
	finally:
		capture.close()

if __name__ == '__main__':
	# 로깅 설정
	setup_logging()

	# 전역 변수 초기화
	active_calls = {}
	SAVE_PATH, SAMPLE_RATE = load_config()

	# 메인 로직 실행
	interface = choose_interface()
	if interface:
		try:
			start_capture(interface)
		except Exception as e:
			log_message("오류", f"프로그램 실행 중 오류 발생: {str(e)}")
	else:
		log_message("정보", "프로그램을 종료합니다.")
