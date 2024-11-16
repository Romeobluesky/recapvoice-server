# 테스트 메인 실행 파일
import os
from config_loader import load_config
from wav_merger import WavMerger
from wav_chat_extractor import WavChatExtractor

def main():
	try:
		# 설정 파일 로드
		config = load_config()
		save_path = config["Recording"]["save_path"]

		# RTP 데이터 예제
		rtp_data = [
			{
				"ip": "192.168.1.10",
				"timestamp_dir": "20241116_103045",
				"timestamp": "20241116103045",
				"local_num": "1234",
				"remote_num": "5678",
				"wav1_path": "D:/PacketWaveRecord/192.168.1.10/20241116_103045/20241116103045_in_1234-5678.wav",
				"wav2_path": "D:/PacketWaveRecord/192.168.1.10/20241116_103045/20241116103045_out_1234-5678.wav",
			},
		]

		print("음성 인식 모델 초기화 중...")
		merger = WavMerger()
		chat_extractor = WavChatExtractor()
		print("초기화 완료\n")

		for data in rtp_data:
			print(f"\n[{data['ip']}] 처리 시작")
			
			# 1. WAV 병합
			merged_file = merger.merge_and_save(
				data["ip"],
				data["timestamp_dir"],
				data["timestamp"],
				data["local_num"],
				data["remote_num"],
				data["wav1_path"],
				data["wav2_path"],
				save_path
			)
			if not merged_file:
				print(f"[{data['ip']}] WAV 병합 실패")
				continue

			# 2. HTML 생성
			html_file = chat_extractor.extract_chat_to_html(
				data["ip"],
				data["timestamp_dir"],
				data["timestamp"],
				data["local_num"],
				data["remote_num"],
				data["wav1_path"],
				data["wav2_path"],
				save_path
			)
			if not html_file:
				print(f"[{data['ip']}] HTML 생성 실패")
				continue

			print(f"[{data['ip']}] 처리 완료")

		print("\n모든 처리가 완료되었습니다. 출력 디렉토리를 확인하세요.")

	except Exception as e:
		print(f"실행 중 오류 발생: {str(e)}")

if __name__ == "__main__":
	main()
