# -*- coding: utf-8 -*-
"""
로깅 유틸리티 모듈
Dashboard 클래스에서 로깅 관련 기능을 분리
"""

import datetime
import os
import sys
import traceback
from PySide6.QtCore import *
from PySide6.QtGui import QTextCursor


class LoggingUtils:
    """로깅 관련 유틸리티 함수들"""
    
    def __init__(self, dashboard_instance=None):
        self.dashboard = dashboard_instance
        self.log_level = getattr(dashboard_instance, 'log_level', 'info') if dashboard_instance else 'info'
    
    def initialize_log_file(self):
        """로그 파일을 초기화합니다."""
        try:
            # 로그 디렉토리 확인
            log_dir = 'logs'
            if not os.path.exists(log_dir):
                os.makedirs(log_dir)

            # 오늘 날짜로 로그 파일 이름 생성
            today = datetime.datetime.now().strftime("%Y%m%d")
            log_file_path = os.path.join(log_dir, f'voip_monitor_{today}.log')

            # 현재 로그 파일로 심볼릭 링크 생성
            current_log_path = 'voip_monitor.log'
            if os.path.exists(current_log_path):
                if os.path.islink(current_log_path):
                    os.remove(current_log_path)
                else:
                    # 기존 파일이 있으면 백업
                    backup_path = f"{current_log_path}.bak"
                    if os.path.exists(backup_path):
                        os.remove(backup_path)
                    os.rename(current_log_path, backup_path)

            # 윈도우에서는 심볼릭 링크 대신 하드 링크 사용
            if os.name == 'nt':
                # 로그 파일 직접 생성
                with open(log_file_path, 'a', encoding='utf-8') as f:
                    f.write(f"\n=== 프로그램 시작: {datetime.datetime.now()} ===\n")

                # voip_monitor.log 파일도 직접 생성
                with open(current_log_path, 'w', encoding='utf-8') as f:
                    f.write(f"\n=== 프로그램 시작: {datetime.datetime.now()} ===\n")
            else:
                # Unix 시스템에서는 심볼릭 링크 사용
                with open(log_file_path, 'a', encoding='utf-8') as f:
                    f.write(f"\n=== 프로그램 시작: {datetime.datetime.now()} ===\n")
                os.symlink(log_file_path, current_log_path)

            self.log_error("로그 파일 초기화 완료", level="info")
        except Exception as e:
            print(f"로그 파일 초기화 중 오류: {e}")
            raise

    def log_to_sip_console(self, message, level="INFO"):
        """SIP 콘솔에 로그 메시지 추가"""
        try:
            if not self.dashboard or not hasattr(self.dashboard, 'sip_console_text') or self.dashboard.sip_console_text is None:
                return

            # 타임스탬프 추가
            timestamp = datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]

            # 레벨에 따른 색상 설정
            color_map = {
                "INFO": "#00FF00",    # 녹색
                "DEBUG": "#00FFFF",   # 시안색
                "WARNING": "#FFFF00", # 노란색
                "ERROR": "#FF0000",   # 빨간색
                "SIP": "#FF00FF"      # 마젠타색
            }
            color = color_map.get(level, "#00FF00")

            # HTML 형식으로 메시지 포맷
            formatted_message = f'<span style="color: {color};">[{timestamp}] [{level}] {message}</span>'

            # 메인 스레드에서 실행되도록 보장
            if hasattr(self.dashboard, '_append_to_console'):
                QMetaObject.invokeMethod(
                    self.dashboard, "_append_to_console",
                    Qt.QueuedConnection,
                    Q_ARG(str, formatted_message)
                )
            else:
                # 직접 추가
                self.append_to_console(formatted_message)
        except Exception as e:
            print(f"SIP 콘솔 로그 오류: {e}")

    def append_to_console(self, message):
        """콘솔에 메시지 추가 (메인 스레드에서 실행)"""
        try:
            if not self.dashboard or not hasattr(self.dashboard, 'sip_console_text') or self.dashboard.sip_console_text is None:
                return

            # 메시지 추가
            self.dashboard.sip_console_text.append(message)

            # 자동 스크롤 체크
            if hasattr(self.dashboard, 'auto_scroll_checkbox') and self.dashboard.auto_scroll_checkbox.isChecked():
                scrollbar = self.dashboard.sip_console_text.verticalScrollBar()
                scrollbar.setValue(scrollbar.maximum())

            # 최대 라인 수 제한 (성능을 위해)
            max_lines = 1000
            document = self.dashboard.sip_console_text.document()
            if document.blockCount() > max_lines:
                cursor = QTextCursor(document)
                cursor.movePosition(QTextCursor.Start)
                cursor.movePosition(QTextCursor.Down, QTextCursor.KeepAnchor, 100)
                cursor.removeSelectedText()
        except Exception as e:
            print(f"콘솔 메시지 추가 오류: {e}")

    def init_sip_console_welcome(self):
        """SIP 콘솔 초기화 환영 메시지"""
        try:
            self.log_to_sip_console("PacketWave SIP Console Log 시작", "INFO")
            self.log_to_sip_console("개발 모드와 배포 모드에서 SIP 관련 로그를 확인할 수 있습니다", "INFO")
            self.log_to_sip_console("패킷 모니터링 준비 완료", "INFO")
        except Exception as e:
            print(f"SIP 콘솔 초기화 오류: {e}")

    def log_error(self, message, error=None, additional_info=None, level="error", console_output=True):
        """로그 메시지를 파일에 기록하고 콘솔에 출력합니다."""
        try:
            # 로그 레벨 확인
            log_levels = {
                "debug": 0,
                "info": 1,
                "warning": 2,
                "error": 3
            }

            current_level = log_levels.get(level.lower(), 0)
            min_level = log_levels.get(self.log_level.lower(), 1)

            # 설정된 최소 레벨보다 낮은 로그는 무시
            if current_level < min_level:
                return

            timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            # 콘솔 출력 (console_output이 True인 경우에만)
            if console_output:
                level_prefix = {
                    "debug": "[디버그]",
                    "info": "[정보]",
                    "warning": "[경고]",
                    "error": "[오류]"
                }.get(level.lower(), "[정보]")

                print(f"\n[{timestamp}] {level_prefix} {message}")

                if additional_info:
                    print(f"추가 정보: {additional_info}")
                if error:
                    print(f"에러 메시지: {str(error)}")

            # 파일 로깅
            with open('voip_monitor.log', 'a', encoding='utf-8', buffering=1) as log_file:  # buffering=1: 라인 버퍼링
                log_file.write(f"\n[{timestamp}] {message}\n")
                if additional_info:
                    log_file.write(f"추가 정보: {additional_info}\n")
                if error:
                    log_file.write(f"에러 메시지: {str(error)}\n")
                    log_file.write("스택 트레이스:\n")
                    log_file.write(traceback.format_exc())
                log_file.write("\n")
                log_file.flush()  # 강제로 디스크에 쓰기
                os.fsync(log_file.fileno())  # 운영체제 버퍼도 비우기
        except Exception as e:
            print(f"로깅 중 오류 발생: {e}")
            sys.stderr.write(f"Critical logging error: {e}\n")
            sys.stderr.flush()