# RTPStreamManager 클래스 (기존 코드 기반)
import os
import threading
import time
import datetime
import configparser
import wave
import audioop
import traceback
import hashlib

class RTPStreamManager:
		def __init__(self):
				self.active_streams = {}
				self.stream_locks = {}
				self.file_locks = {}
				self.min_buffer_size = 4000
				self.max_buffer_size = 16000
				self.buffer_adjust_threshold = 0.8
				
		def get_stream_key(self, call_id, direction):
				return f"{call_id}_{direction}"
				
		def create_stream(self, call_id, direction, call_info, phone_ip):
				try:
						stream_key = self.get_stream_key(call_id, direction)
						if stream_key not in self.active_streams:
								self.stream_locks[stream_key] = threading.Lock()
								self.file_locks[stream_key] = threading.Lock()
								
								config = configparser.ConfigParser()
								config.read('settings.ini', encoding='utf-8')
								base_path = config.get('Recording', 'save_path', fallback='C:/Program Files (x86)/Recap Voice/RecapVoiceRecord')
								
								today = datetime.datetime.now().strftime("%Y%m%d")
								
								# 통화별 시간과 고유 식별자 저장을 위한 딕셔너리가 없으면 생성
								if not hasattr(self, 'call_start_times'):
										self.call_start_times = {}
								if not hasattr(self, 'call_unique_ids'):
										self.call_unique_ids = {}
								if not hasattr(self, 'stream_start_times'):
										self.stream_start_times = {}
								
								# call_id에 대한 정보가 없으면 새로 생성
								if call_id not in self.call_start_times:
										if 'start_time' in call_info:
												self.call_start_times[call_id] = call_info['start_time'].strftime("%H%M%S%f")[:9]
										else:
												self.call_start_times[call_id] = datetime.datetime.now().strftime("%H%M%S%f")[:9]
										
										# call_id를 해싱하여 고유 식별자 생성 (6자리)
										call_hash = hashlib.md5(call_id.encode()).hexdigest()[:6]
										self.call_unique_ids[call_id] = call_hash
								
								# 저장된 정보 사용
								time_str = self.call_start_times[call_id]
								call_hash = self.call_unique_ids[call_id]
								
								# 스트림별 개별 시작 시간 기록 (정확한 동기화를 위해)
								stream_start_time = datetime.datetime.now()
								self.stream_start_times[stream_key] = stream_start_time
								print(f"스트림 {direction} 시작 시간 기록: {stream_start_time.strftime('%H:%M:%S.%f')}")
								
								# 디렉토리 경로 생성 및 확인
								file_dir = os.path.join(base_path, today, phone_ip, time_str)
								if not os.path.exists(file_dir):
										try:
												os.makedirs(file_dir)
										except Exception as e:
												print(f"디렉토리 생성 실패: {e}")
												return None
												
								# 파일명 생성 (call_id 해시를 포함하여 완전 고유성 보장)
								base_filename = f"{time_str}_{direction}_{call_info['from_number']}_{call_info['to_number']}_{today}_{call_hash}.wav"
								filepath = os.path.join(file_dir, base_filename)
								
								# 추가 보안: 여전히 파일이 존재하는 경우 순차번호 추가 (극히 드문 경우)
								counter = 1
								while os.path.exists(filepath):
										filename = f"{time_str}_{direction}_{call_info['from_number']}_{call_info['to_number']}_{today}_{call_hash}_{counter:03d}.wav"
										filepath = os.path.join(file_dir, filename)
										counter += 1
										if counter > 999:  # 무한 루프 방지
												print(f"파일 중복 해결 실패: {base_filename}")
												break
								
								try:
										with wave.open(filepath, 'wb') as wav_file:
												wav_file.setnchannels(1)
												wav_file.setsampwidth(2)
												wav_file.setframerate(8000)
								except Exception as e:
										print(f"WAV 파일 초기화 실패: {e}")
										return None
										
								print(f"새로운 스트림 생성: {stream_key}")
								print(f"파일 경로: {filepath}")
								print(f"Call ID: {call_id}")
								print(f"Call Hash: {call_hash}")
								
								self.active_streams[stream_key] = {
										'call_id': call_id,
										'call_hash': call_hash,  # 고유 식별자 추가
										'direction': direction,
										'call_info': call_info,
										'phone_ip': phone_ip,
										'file_dir': file_dir,
										'filepath': filepath,
										'audio_data': bytearray(),
										'sequence': 0,
										'saved': False,
										'wav_file': None,
										'current_buffer_size': 8000,
										'packet_count': 0,
										'last_write_time': time.time(),
										'packet_rate': 0,
										'is_internal_call': self._is_internal_call(call_info)
								}
								
						return stream_key
				except Exception as e:
						print(f"스트림 생성 중 오류: {e}")
						return None

		def _is_internal_call(self, call_info):
				from_number = str(call_info['from_number'])
				to_number = str(call_info['to_number'])
				return (len(from_number) == 4 and from_number[0] in '123456789' and
								len(to_number) == 4 and to_number[0] in '123456789')

		def _adjust_buffer_size(self, stream_info):
				try:
						current_time = time.time()
						time_diff = current_time - stream_info['last_write_time']
						if time_diff > 0:
								current_rate = stream_info['packet_count'] / time_diff
								alpha = 0.3
								stream_info['packet_rate'] = (alpha * current_rate + (1 - alpha) * stream_info['packet_rate'])
								if stream_info['is_internal_call']:
										target_size = min(int(stream_info['packet_rate'] * 0.8 * 1000), self.max_buffer_size // 2)
								else:
										target_size = min(int(stream_info['packet_rate'] * 1.2 * 1000), self.max_buffer_size)
								target_size = max(self.min_buffer_size, min(target_size, self.max_buffer_size))
								if abs(target_size - stream_info['current_buffer_size']) > self.min_buffer_size:
										if target_size > stream_info['current_buffer_size']:
												stream_info['current_buffer_size'] += self.min_buffer_size
										else:
												stream_info['current_buffer_size'] -= self.min_buffer_size
								stream_info['packet_count'] = 0
								stream_info['last_write_time'] = current_time
								print(f"버퍼 크기 조정: {stream_info['current_buffer_size']} bytes")
				except Exception as e:
						print(f"버퍼 크기 조정 중 오류: {e}")

		def process_packet(self, stream_key, audio_data, sequence, payload_type):
				if not stream_key or not audio_data:
						print("유효하지 않은 스트림 키 또는 오디오 데이터")
						return

				if stream_key not in self.stream_locks:
						print(f"스트림 락이 존재하지 않음: {stream_key}")
						return

				try:
						with self.stream_locks[stream_key]:
								if stream_key not in self.active_streams:
										print(f"활성 스트림이 존재하지 않음: {stream_key}")
										return

								stream_info = self.active_streams[stream_key]
								
								if stream_info['saved']:
										print("이미 저장된 스트림")
										return

								try:
										##print(f"패킷 수신 - 시퀀스: {sequence}, 크기: {len(audio_data)} bytes")
										
										# 시퀀스 번호 검증
										if stream_info['sequence'] > 0:
												expected_sequence = (stream_info['sequence'] + 1) % 65536
												if sequence != expected_sequence:
														print(f"시퀀스 불연속 감지: 예상={expected_sequence}, 실제={sequence}")
														# 시퀀스 불연속 로깅
														self._log_sequence_discontinuity(stream_key, expected_sequence, sequence)
										
										# 중복 패킷 체크
										if sequence <= stream_info['sequence']:
												print(f"중복 패킷 무시: 현재={stream_info['sequence']}, 수신={sequence}")
												return

										# 메모리 사용량 체크
										current_memory = len(stream_info['audio_data'])
										if current_memory > self.max_buffer_size * 2:
												print(f"경고: 버퍼 크기 초과 - {current_memory} bytes")
												self._handle_buffer_overflow(stream_key)
												return

										# 오디오 데이터 추가
										try:
												stream_info['audio_data'].extend(audio_data)
										except Exception as extend_error:
												print(f"오디오 데이터 추가 실패: {extend_error}")
												return

										stream_info['sequence'] = sequence
										stream_info['packet_count'] += 1

										#print(f"버퍼 상태 - 현재크기: {len(stream_info['audio_data'])}, "
										#			f"목표크기: {stream_info['current_buffer_size']}, "
										#			f"내선통화: {stream_info['is_internal_call']}")

										# 버퍼 크기 체크 및 WAV 파일 쓰기
										if len(stream_info['audio_data']) >= stream_info['current_buffer_size']:
												try:
														self._write_to_wav(stream_key, payload_type)
												except Exception as write_error:
														print(f"WAV 파일 쓰기 실패: {write_error}")
														return

												try:
														self._adjust_buffer_size(stream_info)
												except Exception as adjust_error:
														print(f"버퍼 크기 조정 실패: {adjust_error}")

								except Exception as process_error:
										print(f"패킷 처리 중 오류: {process_error}")
										print(traceback.format_exc())

				except Exception as lock_error:
						print(f"스트림 락 획득 실패: {lock_error}")
						print(traceback.format_exc())

		def _log_sequence_discontinuity(self, stream_key, expected, actual):
				try:
						with open('sequence_errors.log', 'a') as f:
								timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
								f.write(f"[{timestamp}] 스트림: {stream_key}, 예상: {expected}, 실제: {actual}\n")
				except Exception as e:
						print(f"시퀀스 오류 로깅 실패: {e}")

		def _handle_buffer_overflow(self, stream_key):
				try:
						stream_info = self.active_streams[stream_key]
						# 버퍼의 후반부만 유지
						stream_info['audio_data'] = stream_info['audio_data'][-self.max_buffer_size:]
						print(f"버퍼 오버플로우 처리 완료 - 새 크기: {len(stream_info['audio_data'])} bytes")
				except Exception as e:
						print(f"버퍼 오버플로우 처리 실패: {e}")

		def _write_to_wav(self, stream_key, payload_type):
				try:
						with self.file_locks[stream_key]:
								stream_info = self.active_streams[stream_key]
								if not stream_info['audio_data']:
										return
								print(f"WAV 쓰기 시작 - 데이터크기: {len(stream_info['audio_data'])} bytes")
								if payload_type == 8:
										decoded = audioop.alaw2lin(bytes(stream_info['audio_data']), 2)
										codec_type = "PCMA"
								else:
										decoded = audioop.ulaw2lin(bytes(stream_info['audio_data']), 2)
										codec_type = "PCMU"
								print(f"디코딩 완료 - 코덱: {codec_type}, 디코딩크기: {len(decoded)} bytes")
								amplified = audioop.mul(decoded, 2, 2.0)
								try:
										before_size = 0
										if os.path.exists(stream_info['filepath']):
												before_size = os.path.getsize(stream_info['filepath'])
												temp_filepath = stream_info['filepath'] + '.tmp'
												with wave.open(stream_info['filepath'], 'rb') as wav_read:
														params = wav_read.getparams()
														existing_frames = wav_read.readframes(wav_read.getnframes())
												with wave.open(temp_filepath, 'wb') as wav_write:
														wav_write.setparams(params)
														wav_write.writeframes(existing_frames)
														wav_write.writeframes(amplified)
												os.replace(temp_filepath, stream_info['filepath'])
										else:
												with wave.open(stream_info['filepath'], 'wb') as wav_file:
														wav_file.setnchannels(1)
														wav_file.setsampwidth(2)
														wav_file.setframerate(8000)
														wav_file.writeframes(amplified)
										after_size = os.path.getsize(stream_info['filepath'])
										print(f"WAV 파일 크기 변화: {before_size} -> {after_size} bytes (증가: {after_size - before_size} bytes)")
								except Exception as write_error:
										print(f"WAV 파일 쓰기 세부 오류: {write_error}")
										if 'temp_filepath' in locals() and os.path.exists(temp_filepath):
												os.remove(temp_filepath)
										raise
								stream_info['audio_data'] = bytearray()
				except Exception as e:
						print(f"WAV 파일 쓰기 중 오류: {e}")
						print(traceback.format_exc())

		def finalize_stream(self, stream_key):
				try:
						if stream_key not in self.active_streams:
								print(f"존재하지 않는 스트림 키: {stream_key}")
								return None
						with self.stream_locks[stream_key]:
								stream_info = self.active_streams[stream_key]
								if not stream_info['saved']:
										if stream_info['audio_data']:
												self._write_to_wav(stream_key, 8)
										stream_info['saved'] = True
										print(f"스트림 종료 완료: {stream_key}")
										print(f"최종 파일: {stream_info['filepath']}")
								
								# call_start_times 및 call_unique_ids에서 해당 call_id 정보 정리
								call_id = stream_info['call_id']
								if hasattr(self, 'call_start_times') and call_id in self.call_start_times:
										# 해당 call_id의 모든 스트림이 종료된 경우에만 정리
										call_streams = [key for key in self.active_streams.keys() if self.active_streams[key]['call_id'] == call_id]
										if len(call_streams) <= 1:  # 현재 스트림이 마지막인 경우
												self.call_start_times.pop(call_id, None)
												if hasattr(self, 'call_unique_ids'):
														self.call_unique_ids.pop(call_id, None)
												print(f"Call ID {call_id} 정보 정리 완료")
								
								return dict(stream_info)
				except Exception as e:
						print(f"스트림 종료 중 오류: {e}")
						print(traceback.format_exc())
						return None

		def get_memory_usage_summary(self):
				"""현재 메모리 사용량 요약 정보 반환"""
				try:
						total_memory = 0
						call_memory = {}
						stream_count = len(self.active_streams)
						
						for stream_key, stream_info in self.active_streams.items():
								call_id = stream_info['call_id']
								memory_usage = len(stream_info['audio_data'])
								total_memory += memory_usage
								
								if call_id not in call_memory:
										call_memory[call_id] = 0
								call_memory[call_id] += memory_usage
						
						return {
								'total_streams': stream_count,
								'total_memory_bytes': total_memory,
								'total_memory_mb': round(total_memory / (1024 * 1024), 2),
								'call_memory_usage': call_memory,
								'avg_memory_per_stream': round(total_memory / stream_count, 2) if stream_count > 0 else 0
						}
				except Exception as e:
						print(f"메모리 사용량 조회 실패: {e}")
						return {}

		def cleanup_finished_calls(self):
				"""완료된 통화의 메모리 정리"""
				try:
						finished_streams = []
						for stream_key, stream_info in self.active_streams.items():
								if stream_info.get('saved', False):
										finished_streams.append(stream_key)
						
						for stream_key in finished_streams:
								try:
										if stream_key in self.stream_locks:
												del self.stream_locks[stream_key]
										if stream_key in self.file_locks:
												del self.file_locks[stream_key]
										if stream_key in self.active_streams:
												del self.active_streams[stream_key]
										print(f"완료된 스트림 정리: {stream_key}")
								except Exception as e:
										print(f"스트림 정리 실패 {stream_key}: {e}")
										
						return len(finished_streams)
				except Exception as e:
						print(f"완료된 통화 정리 실패: {e}")
						return 0

		def save_file_info(self, file_info):
				try:
						self.filesinfo.insert_one(file_info)
				except Exception as e:
						print(f"파일 정보 저장 실패: {e}")