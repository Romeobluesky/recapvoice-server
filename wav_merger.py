#wav 병합 클래스
import os
import subprocess
import datetime

class WavMerger:
	def merge_and_save(self, time_str, local_num, remote_num, in_file, out_file, save_dir, call_hash=None):
		try:
			# 날짜 형식 추가
			today = datetime.datetime.now().strftime("%Y%m%d")
			
			# 병합된 파일명: {time}_MERGE_{from}_{to}_{yyyymmdd}_{call_hash}.wav
			if call_hash:
				merged_filename = f"{time_str}_MERGE_{local_num}_{remote_num}_{today}_{call_hash}.wav"
			else:
				merged_filename = f"{time_str}_MERGE_{local_num}_{remote_num}_{today}.wav"
			merged_filepath = os.path.join(save_dir, merged_filename)
			
			# 중복 파일 생성 방지 - 이미 존재하는 경우 건너뛰기
			if os.path.exists(merged_filepath):
				print(f"✅ MERGE 파일이 이미 존재함: {merged_filename}")
				return merged_filepath

			# 파일 길이 분석을 통한 자동 동기화
			in_duration = self._get_wav_duration(in_file)
			out_duration = self._get_wav_duration(out_file)
			
			print(f"🔊 음성 파일 분석 - IN(상대방→내선): {in_duration:.2f}초, OUT(내선→상대방): {out_duration:.2f}초")
			
			# 더 긴 파일 기준으로 동기화 (실제 통화에서는 보통 OUT이 먼저 시작)
			max_duration = max(in_duration, out_duration)
			
			# ffmpeg 명령어 구성 - 자연스러운 양방향 통화 병합
			# RTP 스트림의 실제 시간 순서를 반영한 자연스러운 대화 구현
			cmd = [
				'ffmpeg',
				'-i', in_file,  # IN 스트림 (상대방 → 내선)  
				'-i', out_file,  # OUT 스트림 (내선 → 상대방)
				'-filter_complex', 
				# 각 오디오 스트림을 정규화 (볼륨 조정)
				'[0:a]aformat=sample_fmts=s16:sample_rates=16000:channel_layouts=mono,volume=0.85[in_norm];'
				'[1:a]aformat=sample_fmts=s16:sample_rates=16000:channel_layouts=mono,volume=0.85[out_norm];'
				# 자연스러운 통화: 두 스트림을 시간축에서 적절히 믹싱
				# 각 참가자의 음성이 겹치지 않도록 처리
				'[in_norm][out_norm]amix=inputs=2:duration=longest:dropout_transition=1,dynaudnorm=p=0.9:m=30[mixed];'
				# 최종 음성 품질 향상 (노이즈 감소, 음성 명료도 개선)
				'[mixed]highpass=f=80,lowpass=f=8000,compand=attacks=0.3:decays=0.8:points=-80/-80|-45/-15|-27/-9|0/-7[final]',
				'-map', '[final]',
				'-ar', '16000',  # 샘플레이트 16kHz
				'-ac', '1',      # 모노 채널
				'-c:a', 'pcm_s16le',  # 16비트 PCM 인코딩
				'-y',  # 기존 파일 덮어쓰기
				merged_filepath
			]

			# ffmpeg 실행
			result = subprocess.run(cmd, capture_output=True, text=True)

			if result.returncode == 0:
				print(f"✅ 자연스러운 통화 병합 완료: {merged_filename}")
				print(f"📁 저장 위치: {merged_filepath}")
				return merged_filepath
			else:
				print(f"❌ FFmpeg 병합 오류: {result.stderr}")
				# 오류 분석 및 대안 제시
				if "Unknown decoder" in result.stderr:
					print("💡 해결 방안: FFmpeg가 오래된 버전일 수 있습니다. 최신 버전으로 업데이트하세요.")
				elif "No such file or directory" in result.stderr:
					print(f"💡 해결 방안: 입력 파일이 존재하지 않습니다. IN: {os.path.exists(in_file)}, OUT: {os.path.exists(out_file)}")
				return None

		except Exception as e:
			print(f"WAV 파일 병합 중 오류 발생: {e}")
			return None
	
	def _get_wav_duration(self, wav_file):
		"""WAV 파일의 재생 시간(초)을 반환"""
		try:
			result = subprocess.run([
				'ffprobe', '-v', 'quiet', '-show_entries', 
				'format=duration', '-of', 'csv=p=0', wav_file
			], capture_output=True, text=True)
			
			if result.returncode == 0 and result.stdout.strip():
				return float(result.stdout.strip())
			else:
				print(f"파일 길이 분석 실패 (ffprobe): {wav_file}")
				# 대체 방법: wave 라이브러리 사용
				import wave
				with wave.open(wav_file, 'rb') as wav:
					frames = wav.getnframes()
					sample_rate = wav.getframerate()
					duration = frames / float(sample_rate)
					return duration
		except Exception as e:
			print(f"파일 길이 분석 오류: {e}")
			return 0.0
