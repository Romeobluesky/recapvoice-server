#wav 채팅 추출 클래스
import os
from datetime import timedelta
#서드파티 라이브러리
from pydub import AudioSegment
import speech_recognition as sr

class WavChatExtractor:
	def __init__(self):
		print("음성 인식기 초기화 중...")
		self.recognizer = sr.Recognizer()
		print("초기화 완료!")

	def extract_audio_text_by_chunk(self, wav_path, chunk_duration=3000):  # 3초 단위
		try:
			print(f"음성 파일 분석 시작: {wav_path}")
			audio = AudioSegment.from_wav(wav_path)

			texts = []
			temp_dir = "temp_audio_chunks"
			os.makedirs(temp_dir, exist_ok=True)

			total_chunks = len(audio) // chunk_duration + 1

			for i in range(0, len(audio), chunk_duration):
				chunk_num = i // chunk_duration + 1
				print(f"청크 처리 중: {chunk_num}/{total_chunks}")

				chunk = audio[i:i + chunk_duration]
				temp_path = os.path.join(temp_dir, f"chunk_{i}.wav")
				chunk.export(temp_path, format="wav")

				# Google STT로 음성 인식
				with sr.AudioFile(temp_path) as source:
					audio_data = self.recognizer.record(source)
					try:
						text = self.recognizer.recognize_google(
							audio_data,
							language='ko-KR'
						)
						if text.strip():
							text = self.clean_text(text)
							if text:
								texts.append((i//1000, text))
					except (sr.UnknownValueError, sr.RequestError):
						pass  # 음성 인식 실패 시 조용히 넘어감

				os.remove(temp_path)

			os.rmdir(temp_dir)
			return texts

		except Exception as e:
			print(f"음성 인식 오류: {str(e)}")
			return []

	def clean_text(self, text):
		"""텍스트 정제 함수"""
		# 1. 기본 정제
		text = text.replace('.', '').replace(',', '')

		# 2. 불필요한 반복 제거
		text = ' '.join(text.split())

		return text

	def extract_chat_to_html(self, ip, timestamp_dir, timestamp, local_num, remote_num, wav1_path, wav2_path, save_path):
		try:
			save_dir = os.path.join(save_path, ip, timestamp_dir)
			os.makedirs(save_dir, exist_ok=True)
			output_html_path = os.path.join(save_dir, f"{timestamp}_chat_{local_num}-{remote_num}.html")

			print(f"[{ip}] 음성 인식 시작...")
			texts1 = self.extract_audio_text_by_chunk(wav1_path)
			texts2 = self.extract_audio_text_by_chunk(wav2_path)
			print(f"[{ip}] 음성 인식 완료")

			html_content = f"""
			<!DOCTYPE html>
			<html>
			<head>
				<meta charset="utf-8">
				<style>
					body {{ font-family: Arial, sans-serif; }}
					.chat-container {{
						max-width: 800px;
						margin: 20px auto;
						padding: 20px;
						background: #f5f5f5;
						border-radius: 10px;
					}}
					.chat-header {{
						text-align: center;
						padding: 10px;
						border-bottom: 1px solid #ddd;
						margin-bottom: 20px;
					}}
					.message {{
						margin: 10px 0;
						padding: 10px 15px;
						border-radius: 15px;
						max-width: 70%;
						position: relative;
						clear: both;
					}}
					.receiver {{
						background: #e3e3e3;
						float: left;
						margin-right: auto;
					}}
					.sender {{
						background: #0084ff;
						color: white;
						float: right;
						margin-left: auto;
					}}
					.timestamp {{
						font-size: 0.8em;
						margin-top: 5px;
						opacity: 0.7;
					}}
					.clearfix {{ clear: both; }}
				</style>
			</head>
			<body>
				<div class="chat-container">
					<div class="chat-header">
						<h2>통화 기록</h2>
						<p>발신: {local_num} ↔ 수신: {remote_num}</p>
					</div>
			"""

			# 두 음성 파일의 텍스트를 시간순으로 정렬
			all_texts = []
			for time, text in texts1:
				all_texts.append(('receiver', time, text, local_num))
			for time, text in texts2:
				all_texts.append(('sender', time, text, remote_num))

			# 시간순 정렬
			all_texts.sort(key=lambda x: x[1])

			# 메시지 생성
			for msg_type, time, text, number in all_texts:
				time_str = str(timedelta(seconds=time))

				if msg_type == 'receiver':
					html_content += f"""
					<div class="message receiver">
						<div>수신: {number}</div>
						<div class="content">{text}</div>
						<div class="timestamp">{time_str}</div>
					</div>
					<div class="clearfix"></div>
					"""
				else:
					html_content += f"""
					<div class="message sender">
						<div>발신: {number}</div>
						<div class="content">{text}</div>
						<div class="timestamp">{time_str}</div>
					</div>
					<div class="clearfix"></div>
					"""

			html_content += """
				</div>
			</body>
			</html>
			"""

			with open(output_html_path, 'w', encoding='utf-8') as f:
				f.write(html_content)

			print(f"[{ip}] 채팅 HTML 생성 완료: {output_html_path}")
			return output_html_path

		except Exception as e:
			print(f"채팅 HTML 생성 중 오류 발생 (IP {ip}): {e}")
			return None
