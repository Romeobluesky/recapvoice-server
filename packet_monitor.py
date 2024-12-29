import pyshark
import wave
import datetime
import os
import logging
import socket
from PySide6.QtWidgets import *
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import *
import threading
import asyncio
import audioop
from config_loader import load_config

class AudioManager:
		"""오디오 처리 관련 클래스"""
		def __init__(self):
				self.config = load_config()
				self.wav_files = {}
				
		def create_wav_file(self, stream_key, timestamp, direction, local_num, remote_num):
				"""WAV 파일 생성"""
				try:
						save_dir = self.config.get('Recording', 'save_path', fallback='D:\\')
						channels = self.config.getint('Recording', 'channels', fallback=1)
						sample_rate = self.config.getint('Recording', 'sample_rate', fallback=8000)
						
						if not os.path.exists(save_dir):
								os.makedirs(save_dir)

						local_num = local_num.replace(':', '_')
						remote_num = remote_num.replace(':', '_')
						
						filename = os.path.join(
								save_dir,
								f"{timestamp}_{direction}_{local_num}-{remote_num}.wav"
						)

						wav_file = wave.open(filename, 'wb')
						wav_file.setnchannels(channels)
						wav_file.setsampwidth(2)
						wav_file.setframerate(sample_rate)
						
						self.wav_files[stream_key] = wav_file
						return True
						
				except Exception as e:
						logging.error(f"WAV 파일 생성 실패: {str(e)}")
						return False

		def write_audio_data(self, stream_key, payload_type, voice_data):
				"""오디오 데이터 WAV 파일에 쓰기"""
				try:
						if stream_key in self.wav_files:
								# G.711 디코딩
								decoded_data = (audioop.alaw2lin(voice_data, 2) 
															if payload_type == 8 
															else audioop.ulaw2lin(voice_data, 2))
															
								self.wav_files[stream_key].writeframes(decoded_data)
								return True
				except Exception as e:
						logging.error(f"오디오 데이터 쓰기 실패: {str(e)}")
				return False

		def close_wav_file(self, stream_key):
				"""WAV 파일 닫기"""
				if stream_key in self.wav_files and self.wav_files[stream_key]:
						try:
								self.wav_files[stream_key].close()
								self.wav_files[stream_key] = None
								return True
						except Exception as e:
								logging.error(f"WAV 파일 닫기 실패: {str(e)}")
				return False

class PacketAnalyzer:
		"""패킷 분석 관련 클래스"""
		@staticmethod
		def is_rtp_packet(payload):
				"""RTP 패킷 검증"""
				try:
						if len(payload) < 12:  # RTP 헤더 최소 크기
								return False

						version = (payload[0] >> 6) & 0x03
						payload_type = payload[1] & 0x7F
						
						return version == 2 and payload_type in [0, 8]  # G.711 코덱 확인
						
				except Exception as e:
						logging.error(f"RTP 패킷 검증 실패: {str(e)}")
						return False

		@staticmethod
		def determine_stream_direction(packet):
				"""통화 방향 및 번호 정보 결정"""
				src_port = int(packet.udp.srcport)
				dst_port = int(packet.udp.dstport)

				# SIP 포트 범위로 방향 결정 (3000-3999)
				if 3000 <= src_port <= 3999:
						direction = "OUT"
						local_num = f"{packet.ip.src}:{src_port}"
						remote_num = f"{packet.ip.dst}:{dst_port}"
				else:
						direction = "IN"
						local_num = f"{packet.ip.dst}:{dst_port}"
						remote_num = f"{packet.ip.src}:{src_port}"

				return direction, local_num, remote_num

class StreamManager:
		"""스트림 관리 클래스"""
		def __init__(self):
				self.streams = {}
				self.TIMEOUT_SECONDS = 5  # 5초 동안 패킷이 없으면 종료로 간주
				
		def create_stream(self, stream_key, direction, local_num, remote_num):
				"""새 스트림 생성"""
				self.streams[stream_key] = {
						'start_time': datetime.datetime.now(),
						'last_packet_time': datetime.datetime.now(),  # 마지막 패킷 시간 추가
						'packets': 0,
						'last_sequence': 0,
						'codec': None,
						'status': '녹음중.',
						'result': '',
						'direction': direction,
						'local_num': local_num,
						'remote_num': remote_num
				}
				return self.streams[stream_key]

		def update_stream(self, stream_key, sequence=None, codec=None):
				"""스트림 정보 업데이트"""
				if stream_key in self.streams:
						self.streams[stream_key]['last_packet_time'] = datetime.datetime.now()
						if sequence is not None:
								self.streams[stream_key]['last_sequence'] = sequence
						if codec is not None:
								self.streams[stream_key]['codec'] = codec
						self.streams[stream_key]['packets'] += 1

		def check_stream_timeout(self):
				"""스트림 타임아웃 체크"""
				current_time = datetime.datetime.now()
				for stream_key, stream_info in list(self.streams.items()):
						if stream_info['status'] == '녹음중.':
								time_diff = (current_time - stream_info['last_packet_time']).total_seconds()
								if time_diff > self.TIMEOUT_SECONDS:
										self.close_stream(stream_key)
										return stream_key  # 종료된 스트림 키 반환
				return None

		def close_stream(self, stream_key):
				"""스트림 종료"""
				if stream_key in self.streams:
						self.streams[stream_key]['status'] = '녹음완료'

class PacketMonitor(QMainWindow):
		"""패킷 모니터링 메인 클래스"""
		def __init__(self):
				super().__init__()
				self.config = load_config()
				self.audio_manager = AudioManager()
				self.stream_manager = StreamManager()
				self.packet_analyzer = PacketAnalyzer()
				
				self._init_ui()
				self._setup_timers()
				
		def _init_ui(self):
				"""UI 초기화"""
				self.setWindowIcon(QIcon("images/logo.png"))
				self.setWindowTitle("Packet Monitor")
				self.resize(1200, 600)
				
				# 메인 위젯 설정
				central_widget = QWidget()
				self.setCentralWidget(central_widget)
				layout = QVBoxLayout(central_widget)

				# 인터페이스 선택 영역
				self._setup_interface_section(layout)
				
				# 테이블 설정
				self._setup_table(layout)
				
				# 스타일 적용
				self._apply_styles()

		def _setup_interface_section(self, layout):
				"""인터페이스 선택 영역 설정"""
				interface_layout = QHBoxLayout()
				interface_layout.addSpacing(20)
				
				interface_label = QLabel("네트워크 인터페이스:")
				self.interface_combo = QComboBox()
				self.interface_combo.setStyleSheet("QComboBox { min-width: 200px; height: 27px; }")
				
				# 네트워크 인터페이스 목록 로드
				self._load_network_interfaces()
				
				self.start_button = QPushButton("PACKET MONITOR START")
				self.start_button.setStyleSheet(
						"QPushButton { min-width: 180px; height: 22px; background-color: #C533BE; }"
				)
				self.start_button.clicked.connect(self.start_capture)

				interface_layout.addWidget(interface_label)
				interface_layout.addWidget(self.interface_combo)
				interface_layout.addWidget(self.start_button)
				interface_layout.addStretch()
				
				layout.addLayout(interface_layout)

		def _setup_table(self, layout):
				"""테이블 설정"""
				self.table = QTableWidget()
				self.table.setColumnCount(8)
				self.table.setHorizontalHeaderLabels([
						'시간', '통화 방향', '발신번호', '수신번호', '상태',
						'스트림', '코덱', '패킷 수'
				])
				
				# 컬럼 너비 설정
				self.table.setColumnWidth(5, 280)
				self.table.setColumnWidth(6, 100)
				
				layout.addWidget(self.table)

		def _setup_timers(self):
				"""타이머 설정"""
				# 테이블 업데이트 타이머
				self.table_timer = QTimer()
				self.table_timer.timeout.connect(self.update_table)
				self.table_timer.start(500)

				# 스트림 타임아웃 체크 타이머
				self.timeout_timer = QTimer()
				self.timeout_timer.timeout.connect(self.check_stream_timeout)
				self.timeout_timer.start(1000)  # 1초마다 체크

		def _apply_styles(self):
				"""스타일 적용"""
				self.setStyleSheet("""
						QMainWindow {
								background-color: black;
						}
						QLabel {
								color: white;
								font-size: 12px;
						}
				""")

		def start_capture(self):
				"""패킷 캡처 시작"""
				try:
						interface = self.interface_combo.currentData()
						if not interface:
								logging.error("인터페이스를 선택해주세요")
								return

						self.capture_thread = threading.Thread(
								target=self._capture_packets,
								args=(interface,),
								daemon=True
						)
						self.capture_thread.start()
						
						self.start_button.setEnabled(False)
						self.start_button.setText("캡처 중...")
						
				except Exception as e:
						logging.error(f"패킷 캡처 시작 실패: {str(e)}")

		def _capture_packets(self, interface):
				"""패킷 캡처 및 분석"""
				try:
						loop = asyncio.new_event_loop()
						asyncio.set_event_loop(loop)

						capture = pyshark.LiveCapture(
								interface=interface,
								bpf_filter="udp"
						)

						for packet in capture.sniff_continuously():
								try:
										if hasattr(packet, 'udp'):
												self._process_packet(packet)
								except Exception as e:
										logging.error(f"패킷 처리 중 오류: {str(e)}")

				except Exception as e:
						logging.error(f"패킷 캡처 중 오류: {str(e)}")
				finally:
						if 'capture' in locals():
								capture.close()
						if 'loop' in locals():
								loop.close()

		def _process_packet(self, packet):
				"""패킷 처리"""
				try:
						payload = bytes.fromhex(packet.udp.payload.replace(':', ''))
						
						if self.packet_analyzer.is_rtp_packet(payload):
								direction, local_num, remote_num = (
										self.packet_analyzer.determine_stream_direction(packet)
								)
								
								stream_key = (
										f"{packet.ip.src}:{packet.udp.srcport}-"
										f"{packet.ip.dst}:{packet.udp.dstport}"
								)
								
								if stream_key not in self.stream_manager.streams:
										self.stream_manager.create_stream(
												stream_key, direction, local_num, remote_num
										)
										self.audio_manager.create_wav_file(
												stream_key,
												datetime.datetime.now().strftime('%Y%m%d_%H%M%S'),
												direction, local_num, remote_num
										)

								# 패킷 데이터 처리
								payload_type = payload[1] & 0x7F
								sequence = int.from_bytes(payload[2:4], byteorder='big')
								voice_data = payload[12:]
								
								self.stream_manager.update_stream(
										stream_key, 
										sequence=sequence,
										codec='PCMA' if payload_type == 8 else 'PCMU'
								)
								
								self.audio_manager.write_audio_data(
										stream_key, payload_type, voice_data
								)
								
				except Exception as e:
						logging.error(f"패킷 처리 중 오류: {str(e)}")

		def update_table(self):
				"""테이블 업데이트"""
				try:
						current_row = 0
						for stream_key, stream_info in self.stream_manager.streams.items():
								if current_row >= self.table.rowCount():
										self.table.insertRow(current_row)

								items = [
										(stream_info['start_time'].strftime('%Y-%m-%d %H:%M:%S'), True),
										(stream_info['direction'], True),
										(stream_info['local_num'], True),
										(stream_info['remote_num'], True),
										(stream_info['status'], True),
										(stream_key, False),
										(stream_info['codec'], True),
										(str(stream_info['packets']), True)
								]

								for col, (text, center) in enumerate(items):
										item = QTableWidgetItem(text)
										if center:
												item.setTextAlignment(Qt.AlignCenter)
										self.table.setItem(current_row, col, item)

								current_row += 1

				except Exception as e:
						logging.error(f"테이블 업데이트 중 오류: {str(e)}")

		def check_stream_timeout(self):
				"""스트림 타임아웃 체크 및 처리"""
				closed_stream = self.stream_manager.check_stream_timeout()
				if closed_stream:
						# WAV 파일 닫기
						self.audio_manager.close_wav_file(closed_stream)
						# 테이블 즉시 업데이트
						self.update_table()

		def _load_network_interfaces(self):
				"""네트워크 인터페이스 목록 로드"""
				try:
						import psutil
						interfaces = psutil.net_if_addrs()
						
						for iface_name, iface_addresses in interfaces.items():
								# IPv4 주소가 있는 인터페이스만 추가
								for addr in iface_addresses:
										if addr.family == socket.AF_INET:  # IPv4
												display_text = f"{iface_name} - {addr.address}"
												self.interface_combo.addItem(display_text, iface_name)
												break
						
						# 기본 인터페이스 선택
						if self.interface_combo.count() > 0:
								self.interface_combo.setCurrentIndex(0)
								self.selected_interface = self.interface_combo.currentData()
								
				except Exception as e:
						logging.error(f"네트워크 인터페이스 로드 실패: {str(e)}")

if __name__ == '__main__':
		logging.basicConfig(level=logging.INFO)
		app = QApplication([])
		window = PacketMonitor()
		window.show()
		app.exec()