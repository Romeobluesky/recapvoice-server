#wav 병합 클래스
import os
import subprocess
import datetime

class WavMerger:
	def merge_and_save(self, time_str, local_num, remote_num, in_file, out_file, save_dir):
		try:
			# 날짜 형식 추가
			today = datetime.datetime.now().strftime("%Y%m%d")
			
			# 병합된 파일명: {time}_MERGE_{from}_{to}_{yyyymmdd}.wav
			merged_filename = f"{time_str}_MERGE_{local_num}_{remote_num}_{today}.wav"
			merged_filepath = os.path.join(save_dir, merged_filename)

			# ffmpeg 명령어 구성
			cmd = [
				'ffmpeg',
				'-i', in_file,  # 첫 번째 입력 파일
				'-i', out_file,  # 두 번째 입력 파일
				'-filter_complex', 'amix=inputs=2:duration=longest:dropout_transition=0',  # 오디오 믹싱
				'-y',  # 기존 파일 덮어쓰기
				merged_filepath
			]

			# ffmpeg 실행
			result = subprocess.run(cmd, capture_output=True, text=True)

			if result.returncode == 0:
				print(f"WAV 파일 병합 완료: {merged_filepath}")
				return merged_filepath
			else:
				print(f"FFmpeg 오류: {result.stderr}")
				return None

		except Exception as e:
			print(f"WAV 파일 병합 중 오류 발생: {e}")
			return None
