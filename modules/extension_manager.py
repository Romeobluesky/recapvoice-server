# -*- coding: utf-8 -*-
"""
내선번호 관리 모듈
Dashboard 클래스에서 내선번호 관련 기능을 분리
"""

from PySide6.QtCore import *
from PySide6.QtWidgets import *


class ExtensionManager:
    """내선번호 관리 관련 유틸리티 함수들"""
    
    def __init__(self, dashboard_instance):
        self.dashboard = dashboard_instance
    
    def toggle_led_color(self, led_indicator):
        """LED 색상을 노란색과 녹색 사이에서 토글"""
        try:
            # LED 객체가 여전히 유효한지 확인
            if led_indicator is None or not hasattr(led_indicator, 'isVisible'):
                return

            # LED가 표시되지 않거나 삭제된 경우 타이머 정지
            if not led_indicator.isVisible() or led_indicator.parent() is None:
                if hasattr(led_indicator, 'led_timer'):
                    led_indicator.led_timer.stop()
                return

            if hasattr(led_indicator, 'is_yellow'):
                if led_indicator.is_yellow:
                    # 녹색으로 변경
                    led_indicator.setStyleSheet("""
                        QLabel {
                            background-color: transparent;
                            border: none;
                            color: #32CD32;
                            font-size: 12px;
                            font-weight: bold;
                        }
                    """)
                    led_indicator.is_yellow = False
                else:
                    # 노란색으로 변경
                    led_indicator.setStyleSheet("""
                        QLabel {
                            background-color: transparent;
                            border: none;
                            color: #FFD700;
                            font-size: 12px;
                            font-weight: bold;
                        }
                    """)
                    led_indicator.is_yellow = True
        except RuntimeError:
            # C++ 객체가 삭제된 경우 타이머 정지
            if hasattr(led_indicator, 'led_timer'):
                try:
                    led_indicator.led_timer.stop()
                except:
                    pass

    def cleanup_led_timers(self, widget):
        """위젯 내의 LED 타이머들을 정리"""
        try:
            # 위젯의 모든 자식 위젯을 확인
            for child in widget.findChildren(QLabel):
                if hasattr(child, 'led_timer') and child.led_timer is not None:
                    child.led_timer.stop()
                    child.led_timer.deleteLater()
                if hasattr(child, 'is_yellow'):
                    delattr(child, 'is_yellow')
        except:
            pass

    def add_extension(self, extension):
        """새 내선번호 추가"""
        if extension and extension not in self.dashboard.sip_extensions:
            self.dashboard.sip_extensions.add(extension)
            self.update_extension_display()

    def refresh_extension_list_with_register(self, extension):
        """SIP REGISTER로 감지된 내선번호로 목록을 갱신 (Signal을 통해 메인 스레드에서 처리)"""
        if extension:
            print(f"SIP REGISTER 감지: 내선번호 {extension} 등록 요청")
            self.dashboard.log_to_sip_console(f"SIP REGISTER 감지: 내선번호 {extension} 등록 요청", "SIP")
            # 메인 스레드에서 처리하도록 Signal 발신
            self.dashboard.extension_update_signal.emit(extension)

    def update_extension_in_main_thread(self, extension):
        """메인 스레드에서 내선번호 업데이트 처리"""
        print(f"메인 스레드에서 내선번호 처리: {extension}")
        # 실제 등록된 내선번호 추가
        self.dashboard.sip_extensions.add(extension)
        self.update_extension_display()
        print(f"내선번호 {extension} 등록 완료")

    def update_extension_display(self):
        """내선번호 표시 업데이트"""
        print("=" * 50)
        print("EXTENSION MANAGER: update_extension_display 호출됨!!!")
        print("=" * 50)
        
        # UI 요소가 초기화되었는지 확인
        if not hasattr(self.dashboard, 'extension_list_layout'):
            print("ERROR: dashboard에 extension_list_layout 속성이 없음")
            return
        
        if self.dashboard.extension_list_layout is None:
            print("ERROR: extension_list_layout이 None임")
            return
            
        print("SUCCESS: extension_list_layout 확인됨")
            
        print(f"현재 내선번호 목록: {self.dashboard.sip_extensions}")
        print(f"내선번호 개수: {len(self.dashboard.sip_extensions)}")

        # 기존 위젯들 제거 (타이머도 함께 정리)
        while self.dashboard.extension_list_layout.count():
            child = self.dashboard.extension_list_layout.takeAt(0)
            if child.widget():
                widget = child.widget()
                # LED 타이머 정리
                self.cleanup_led_timers(widget)
                widget.deleteLater()

        # 정렬된 내선번호 목록 생성
        sorted_extensions = sorted(self.dashboard.sip_extensions)
        print(f"정렬된 내선번호: {sorted_extensions}")

        # 새로운 내선번호 위젯들 추가
        for extension in sorted_extensions:
            print(f"내선번호 {extension} 위젯 생성 중...")
            extension_widget = self._create_extension_widget(extension)
            if extension_widget:
                self.dashboard.extension_list_layout.addWidget(extension_widget)
                print(f"내선번호 {extension} 위젯 추가 완료")

        print(f"=== update_extension_display 완료 ===")

    def _create_extension_widget(self, extension):
        """개별 내선번호 위젯 생성"""
        try:
            container = QWidget()
            container.setFixedHeight(30)
            container.setStyleSheet("""
                QWidget {
                    background-color: #34495e;
                    border-radius: 4px;
                    margin: 2px;
                }
            """)

            layout = QHBoxLayout(container)
            layout.setContentsMargins(10, 5, 10, 5)

            # LED 표시기
            led_indicator = QLabel("●")
            led_indicator.setStyleSheet("""
                QLabel {
                    background-color: transparent;
                    border: none;
                    color: #32CD32;
                    font-size: 12px;
                    font-weight: bold;
                }
            """)
            led_indicator.setFixedSize(15, 15)

            # 내선번호 라벨
            extension_label = QLabel(f"내선: {extension}")
            extension_label.setStyleSheet("""
                QLabel {
                    background-color: transparent;
                    border: none;
                    color: white;
                    font-size: 12px;
                    font-weight: bold;
                }
            """)

            layout.addWidget(led_indicator)
            layout.addWidget(extension_label)
            layout.addStretch()

            return container

        except Exception as e:
            print(f"내선번호 위젯 생성 오류: {e}")
            return None

    def get_extension_from_call(self, call_id):
        """통화 ID에서 내선번호 추출"""
        with self.dashboard.active_calls_lock:
            if call_id in self.dashboard.active_calls:
                call_info = self.dashboard.active_calls[call_id]
                from_number = call_info['from_number']
                to_number = call_info['to_number']
                is_extension = lambda num: num.startswith(('1', '2', '3', '4', '5', '6', '7', '8', '9')) and len(num) == 4
                return from_number if is_extension(from_number) else to_number if is_extension(to_number) else None
        return None