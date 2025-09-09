import os
import time
import threading
import logging
import subprocess
from datetime import datetime
from pathlib import Path
from sip_rtp_session_grouper import SipRtpSessionGrouper




class ExtensionRecordingManager:
    def __init__(self, dashboard_instance=None):
        self.dashboard = dashboard_instance
        self.logger = logging.getLogger(__name__)
        if not self.logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)
            self.logger.setLevel(logging.INFO)

        self.recordings = {}  # call_id별 녹음 정보 저장
        self.session_grouper = SipRtpSessionGrouper()
        self.logger.info("전역 캡처 ExtensionRecordingManager 초기화 완료")

    def start_call_recording(self, call_id, extension=None, from_number=None, to_number=None):
        """통화 녹음 시작"""
        try:
            if call_id in self.recordings:
                self.logger.warning(f"이미 녹음 중인 통화: {call_id}")
                return True  # 이미 녹음 중이므로 성공으로 처리

            # 현재 시간으로 녹음 정보 초기화
            recording_info = {
                'call_id': call_id,
                'start_time': datetime.now(),
                'extension': extension,
                'from_number': from_number,
                'to_number': to_number,
                'pcapng_path': f"temp_recordings/{call_id}.pcapng"
            }

            self.recordings[call_id] = recording_info
            self.logger.info(f"통화 녹음 시작: {call_id} (내선: {extension})")
            return True  # 성공

        except Exception as e:
            self.logger.error(f"녹음 시작 오류: {e}")
            return False  # 실패

    def stop_call_recording(self, call_id):
        """통화 녹음 중지"""
        try:
            if call_id not in self.recordings:
                self.logger.warning(f"통화 녹음 정보 없음: {call_id}")
                return

            recording_info = self.recordings[call_id]
            self.logger.info(f"통화 녹음 중지: {call_id}")

            # 별도 스레드에서 WAV 변환 처리 (1초 지연)
            conversion_thread = threading.Thread(
                target=self.delayed_wav_conversion,
                args=(recording_info,),
                daemon=True
            )
            conversion_thread.start()

            # 녹음 정보 정리 (변환 스레드 시작 후)
            del self.recordings[call_id]
            self.logger.info(f"통화 녹음 정보 정리 완료: {call_id}")

        except Exception as e:
            self.logger.error(f"녹음 중지 오류: {e}")

    def delayed_wav_conversion(self, call_info):
        """지연된 WAV 변환 (별도 스레드에서 실행)"""
        try:
            # 1초 대기 (pcapng 파일 안정화)
            time.sleep(1)

            # temp_capture 파일 찾기
            temp_capture_file = None

            # 1. dashboard에서 temp_capture_file 확인
            if self.dashboard and hasattr(self.dashboard, 'temp_capture_file'):
                temp_capture_file = self.dashboard.temp_capture_file
                self.logger.info(f"Dashboard에서 temp_capture_file 확인: {temp_capture_file}")

            # 2. 기본 경로 확인 (회전된 파일명도 포함)
            if not temp_capture_file:
                import glob
                # 회전된 파일들 찾기
                pattern = "temp_captures/temp_capture*.pcapng"
                capture_files = glob.glob(pattern)
                if capture_files:
                    # 가장 최근 파일 사용
                    temp_capture_file = max(capture_files, key=os.path.getmtime)
                    self.logger.info(f"회전된 temp_capture_file 발견: {temp_capture_file}")
                else:
                    temp_capture_file = "temp_captures/temp_capture.pcapng"
                    self.logger.info(f"기본 temp_capture_file 사용: {temp_capture_file}")

            # 3. temp_captures 디렉토리 확인 및 생성
            temp_captures_dir = "temp_captures"
            if not os.path.exists(temp_captures_dir):
                os.makedirs(temp_captures_dir)
                self.logger.info(f"temp_captures 디렉토리 생성: {temp_captures_dir}")

            # 4. 파일 존재 확인 및 처리
            if os.path.exists(temp_capture_file):
                file_size = os.path.getsize(temp_capture_file)
                self.logger.info(f"전역 캡처 파일 발견: {temp_capture_file} ({file_size} bytes)")

                if file_size > 0:
                    # Dashboard에서 active_calls 정보 가져오기
                    active_calls_data = None
                    if self.dashboard and hasattr(self.dashboard, 'active_calls'):
                        active_calls_data = dict(self.dashboard.active_calls)
                        self.logger.info(f"Active calls 데이터 전달: {len(active_calls_data)}개 세션")

                    # Dashboard에서 latest_terminated_call_id 가져오기
                    latest_terminated_call_id = None
                    if self.dashboard and hasattr(self.dashboard, 'latest_terminated_call_id'):
                        latest_terminated_call_id = self.dashboard.latest_terminated_call_id
                        self.logger.info(f"최신 종료 Call-ID 전달: {latest_terminated_call_id}")

                    # process_captured_pcap으로 Call-ID별 분리 및 WAV 변환 (active_calls 정보 및 latest_terminated_call_id 포함)
                    self.session_grouper.process_captured_pcap(temp_capture_file, active_calls_data, latest_terminated_call_id)
                else:
                    self.logger.warning(f"전역 캡처 파일이 비어있음: {temp_capture_file}")
            else:
                self.logger.warning(f"전역 캡처 파일 없음: {temp_capture_file}")

        except Exception as e:
            self.logger.error(f"WAV 변환 중 오류: {e}")

    def set_refer_mapping(self, call_id: str, from_number: str):
        """REFER 메소드 처리 시 Call-ID와 실제 발신번호 매핑 설정"""
        self.session_grouper.set_refer_mapping(call_id, from_number)
        self.logger.info(f"REFER 매핑 전달: {call_id} → {from_number}")

    def clear_refer_mapping(self, call_id: str = None):
        """REFER 매핑 정리"""
        self.session_grouper.clear_refer_mapping(call_id)

    def convert_and_save(self, call_info):
        """WAV 변환 및 저장 (호환성을 위한 메서드)"""
        # 실제로는 delayed_wav_conversion에서 처리됨
        pass


    def cleanup_all_recordings(self):
        """모든 녹음 정리"""
        try:
            count = len(self.recordings)
            self.recordings.clear()
            self.logger.info(f"녹음 정리: {count}개 항목")
            self.logger.info("모든 녹음 정리 완료")
        except Exception as e:
            self.logger.error(f"전체 녹음 정리 오류: {e}")


# 전역 인스턴스 관리
_recording_manager_instance = None


def get_recording_manager(dashboard_instance=None):
    """ExtensionRecordingManager 인스턴스를 반환하는 팩토리 함수"""
    global _recording_manager_instance
    if _recording_manager_instance is None:
        _recording_manager_instance = ExtensionRecordingManager(dashboard_instance)
    elif dashboard_instance and not _recording_manager_instance.dashboard:
        _recording_manager_instance.dashboard = dashboard_instance
        _recording_manager_instance.logger.info("Dashboard 인스턴스 연결됨")
    return _recording_manager_instance