import pyshark
import psutil
import wave
import datetime
from scapy.all import UDP
import configparser
import os

# 설정 파일 읽기
config = configparser.ConfigParser()
config.read('settings.ini', encoding='utf-8')

# 설정에서 경로 및 샘플링 속도 불러오기
SAVE_PATH = config.get('Recording', 'save_path', fallback='.')
SAMPLE_RATE = config.getint('Recording', 'sample_rate', fallback=8000)

# 전역 변수 초기화
active_calls = {}

# 사용 가능한 네트워크 인터페이스 목록을 표시하고 선택하는 함수
def choose_interface():
	interfaces = list(psutil.net_if_addrs().keys())
	print("사용 가능한 네트워크 인터페이스:")
	for idx, iface in enumerate(interfaces):
		print(f"{idx}: {iface}")
	
	choice = int(input("사용할 인터페이스의 번호를 입력하세요: "))
	return interfaces[choice]

# 로그를 기록하는 함수
def log_message(event, details=""):
	time_stamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
	print(f"[{time_stamp}] {event}: {details}")

# 음성 데이터를 WAV 형식으로 저장하는 함수
def save_audio(call_id, frames):
	# 설정된 경로와 파일명으로 저장
	filename = os.path.join(SAVE_PATH, f"call_recording_{call_id}_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.wav")
	with wave.open(filename, 'wb') as wf:
		wf.setnchannels(1)  # Mono channel
		wf.setsampwidth(2)  # Sample width in bytes
		wf.setframerate(SAMPLE_RATE)
		wf.writeframes(b''.join(frames))
	log_message("음성 파일 저장 완료", filename)

# RTP 패킷을 분석하고 음성 데이터를 저장하는 함수
def analyze_rtp(packet, call_id):
	if packet.haslayer(UDP):
		udp_layer = packet[UDP]
		if udp_layer.dport != 5060 and udp_layer.sport != 5060:  # RTP는 SIP 포트(5060)와 다름
			rtp_payload = bytes(udp_layer.payload)
			active_calls[call_id]["audio_frames"].append(rtp_payload)

# SIP 패킷을 분석하여 통화 상태를 확인하는 함수
def analyze_sip(packet):
	global active_calls
	if 'SIP' in packet:
		sip_layer = packet['SIP']
		sip_method = sip_layer.get_field_value('request_method')
		call_id = sip_layer.get_field_value('call-id')

		if sip_method == "INVITE":
			log_message("통화 시도", f"{call_id} 통화를 시도하고 있습니다.")
			active_calls[call_id] = {"audio_frames": [], "status": "active"}
		elif sip_method == "BYE" and call_id in active_calls:
			log_message("통화 종료", f"{call_id} 통화가 종료되었습니다.")
			save_audio(call_id, active_calls[call_id]["audio_frames"])
			del active_calls[call_id]
		elif sip_layer.get_field_value('status_code') == '180':
			log_message("통화 중", f"{call_id} 상대방의 전화벨이 울리고 있습니다.")
		elif sip_layer.get_field_value('status_code') == '200' and sip_method != "BYE":
			log_message("통화 성공", f"{call_id} 통화가 성공적으로 연결되었습니다.")
		elif sip_layer.get_field_value('status_code') in ['403', '404', '487']:
			log_message("통화 실패", f"{call_id} 통화 실패 코드: {sip_layer.get_field_value('status_code')}")

# 실시간 패킷 캡처 및 분석
def start_capture(interface):
	capture = pyshark.LiveCapture(interface=interface, bpf_filter="port 5060")
	log_message("패킷 캡처 시작", f"{interface} 인터페이스에서 SIP 패킷을 캡처합니다.")
	try:
		for packet in capture.sniff_continuously():
			analyze_sip(packet)
			for call_id in list(active_calls.keys()):
				analyze_rtp(packet, call_id)
	except KeyboardInterrupt:
		log_message("캡처 중단", "사용자에 의해 캡처가 중단되었습니다.")
	except EOFError:
		log_message("캡처 종료", "EOFError로 인해 캡처가 종료되었습니다.")
	finally:
		capture.close()

# 인터페이스 선택 및 캡처 시작
interface = choose_interface()
start_capture(interface)
