#!/mvenv/Scripts/activate
# -*- coding: utf-8 -*-
import atexit
import subprocess
import audioop
import wave
import os
import psutil
import configparser
import threading
import asyncio
import datetime
import sys
import time
import traceback  # 추가된 import
import platform  # 추가된 import

# 서드파티 라이브러리
import requests
import pyshark
from pydub import AudioSegment

# PySide6 라이브러리
from PySide6.QtWidgets import *
from PySide6.QtCore import *
from PySide6.QtGui import *
from PySide6.QtNetwork import *
from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtMultimedia import QMediaPlayer
from PySide6.QtMultimediaWidgets import QVideoWidget

# 로컬 모듈
from config_loader import load_config, get_wireshark_path
from voip_monitor import VoipMonitor
from packet_monitor import PacketMonitor
from wav_merger import WavMerger
from wav_chat_extractor import WavChatExtractor
from settings_popup import SettingsPopup

# MongoDB 관련 import
from pymongo import MongoClient

# 종료할 프로세스 목록
processes_to_kill = ['nginx.exe', 'mongod.exe', 'node.exe', 'Dumpcap.exe']

def kill_processes():
    for process in processes_to_kill:
        subprocess.call(['taskkill', '/f', '/im', process])

atexit.register(kill_processes)

# 추가 import (윈도우 관련)
import win32gui
import win32con
import win32process

def resource_path(relative_path):
    """리소스 파일의 절대 경로를 반환"""
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.abspath('.'), relative_path)

# -------------------------------------------------------------------
# 상태 전이 관리를 위한 FSM 클래스 (예시)
from enum import Enum, auto
class CallState(Enum):
    IDLE = auto()         # 대기중
    TRYING = auto()       # 시도중
    IN_CALL = auto()      # 통화중
    TERMINATED = auto()   # 통화종료

class CallStateMachine:
    def __init__(self):
        self.state = CallState.IDLE

    def update_state(self, new_state):
        if self.is_valid_transition(new_state):
            print(f"상태 전이: {self.state.name} -> {new_state.name}")
            self.state = new_state
        else:
            print(f"잘못된 상태 전이 시도: {self.state.name} -> {new_state.name}")

    def is_valid_transition(self, new_state):
        valid_transitions = {
            CallState.IDLE: [CallState.TRYING],
            CallState.TRYING: [CallState.IN_CALL, CallState.TERMINATED],
            CallState.IN_CALL: [CallState.TERMINATED],
            CallState.TERMINATED: [CallState.IDLE]
        }
        return new_state in valid_transitions.get(self.state, [])
# -------------------------------------------------------------------

class PacketFlowWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.setMinimumHeight(100)
        self.packets = []
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update)
        self.timer.start(1000)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), QColor("#2d2d2d"))
        y_offset = 10
        for packet in self.packets:
            if y_offset >= self.height() - 10:
                break
            painter.setPen(Qt.white)
            painter.drawText(10, y_offset + 15, packet["time"])
            painter.setPen(QPen(QColor("#18508F"), 2))
            painter.drawLine(200, y_offset + 15, self.width() - 200, y_offset + 15)
            painter.setPen(Qt.white)
            painter.drawText(self.width() // 2 - 50, y_offset + 10, packet["type"])
            y_offset += 30

class Dashboard(QMainWindow):
    # Signal: 내선번호, 상태, 수신번호 전달
    block_creation_signal = Signal(str)
    block_update_signal = Signal(str, str, str)

    def __init__(self):
        super().__init__()
        self.play_intro_video()

    def play_intro_video(self):
        try:
            # 비디오 위젯 생성
            self.video_widget = QVideoWidget()
            self.setCentralWidget(self.video_widget)
            
            # 미디어 플레이어 설정
            self.media_player = QMediaPlayer()
            self.media_player.setVideoOutput(self.video_widget)
            
            # 비디오 파일 경로 설정
            video_path = resource_path("images/recapvoicelogo.mp4")
            self.media_player.setSource(QUrl.fromLocalFile(video_path))
            
            # 창 테두리 제거 및 전체 화면 설정
            self.setWindowFlag(Qt.FramelessWindowHint)
            self.showFullScreen()
            
            # 비디오 재생 완료 시그널 연결
            self.media_player.mediaStatusChanged.connect(self.handle_media_status)
            
            # 비디오 재생 시작
            self.media_player.play()
            
        except Exception as e:
            print(f"인트로 비디오 재생 중 오류: {e}")
            self.initialize_main_window()

    def handle_media_status(self, status):
        if status == QMediaPlayer.MediaStatus.EndOfMedia:
            # 비디오 재생이 끝나면 메인 창 초기화
            self.initialize_main_window()

    def initialize_main_window(self):
        # 기존 비디오 위젯 제거
        if hasattr(self, 'video_widget'):
            self.video_widget.deleteLater()
        if hasattr(self, 'media_player'):
            self.media_player.deleteLater()

        # 메인 창 초기화 전에 숨기기
        self.hide()
        
        # 전체 화면 해제 및 창 설정 복원
        self.setWindowFlag(Qt.FramelessWindowHint, False)
        self.setWindowState(Qt.WindowMaximized)  # 미리 최대화 상태로 설정
        
        # 기존 초기화 코드 실행
        self.setWindowIcon(QIcon(resource_path("images/recapvoice_squere.ico")))
        self.setWindowTitle("Recap Voice")
        self.setAttribute(Qt.WA_QuitOnClose, False)
        self.block_creation_signal.connect(self.create_block_in_main_thread)
        self.block_update_signal.connect(self.update_block_in_main_thread)
        self.settings_popup = SettingsPopup()
        self.active_calls_lock = threading.RLock()
        self.active_calls = {}
        self.call_state_machines = {}
        self.capture_thread = None
        self.voip_timer = QTimer()
        self.voip_timer.timeout.connect(self.update_voip_status)
        self.voip_timer.start(1000)
        self.streams = {}
        self.packet_timer = QTimer()
        self.packet_timer.timeout.connect(self.update_packet_status)
        self.packet_timer.start(1000)
        self.sip_registrations = {}
        self.first_registration = False
        self.packet_get = 0
        self._init_ui()
        self.selected_interface = None
        self.load_network_interfaces()
        QTimer.singleShot(1000, self.start_packet_capture)
        self.duration_timer = QTimer()
        self.duration_timer.timeout.connect(self.update_call_duration)
        self.duration_timer.start(1000)
        self.wav_merger = WavMerger()
        self.chat_extractor = WavChatExtractor()

        try:
            self.mongo_client = MongoClient('mongodb://localhost:27017/')
            self.db = self.mongo_client['packetwave']
            self.filesinfo = self.db['filesinfo']
        except Exception as e:
            print(f"MongoDB 연결 실패: {e}")

        config = load_config()
        if config.get('Environment', 'mode') == 'production':
            wireshark_path = get_wireshark_path()
            def hide_wireshark_windows():
                try:
                    for proc in psutil.process_iter(['pid', 'name', 'exe']):
                        if proc.info['name'] in ['dumpcap.exe', 'tshark.exe']:
                            if proc.info['exe'] and wireshark_path in proc.info['exe']:
                                def enum_windows_callback(hwnd, _):
                                    try:
                                        _, pid = win32process.GetWindowThreadProcessId(hwnd)
                                        if pid == proc.info['pid']:
                                            style = win32gui.GetWindowLong(hwnd, win32con.GWL_STYLE)
                                            style &= ~win32con.WS_VISIBLE
                                            win32gui.SetWindowLong(hwnd, win32con.GWL_STYLE, style)
                                            win32gui.ShowWindow(hwnd, win32con.SW_HIDE)
                                    except:
                                        pass
                                    return True
                                win32gui.EnumWindows(enum_windows_callback, None)
                except Exception as e:
                    print(f"Error hiding windows: {e}")
            self.hide_console_timer = QTimer()
            self.hide_console_timer.timeout.connect(hide_wireshark_windows)
            self.hide_console_timer.start(100)
        self.setup_tray_icon()
        try:
            subprocess.Popen(['start.bat'], shell=True)
            self.on_btn.setStyleSheet("""
                QPushButton {
                    background-color: #FF0000;
                    color: white;
                    border: none;
                    border-radius: 4px;
                    min-height: 35px;
                }
                QPushButton:hover {
                    background-color: #CC0000;
                }
            """)
            print("클라이언트 서버가 자동으로 시작되었습니다.")
        except Exception as e:
            print(f"클라이언트 서버 자동 시작 실패: {e}")

        atexit.register(self.cleanup)
        
        # 리소스 모니터링 타이머 설정
        self.resource_timer = QTimer()
        self.resource_timer.timeout.connect(self.monitor_system_resources)
        self.resource_timer.start(10000)  # 10초마다 체크
        
        # 스레드 관리를 위한 변수 추가
        self.active_threads = set()
        self.thread_lock = threading.Lock()
        
        # 의존성 및 시스템 제한 체크
        self.check_dependencies()
        self.check_system_limits()
        self.setup_crash_handler()

        # UI가 완전히 준비된 후 창 표시
        QTimer.singleShot(100, self.show_maximized_window)

    def show_maximized_window(self):
        """최대화된 상태로 창을 표시"""
        self.show()
        self.raise_()
        self.activateWindow()

    def cleanup(self):
        if hasattr(self, 'capture') and self.capture:
            try:
                if hasattr(self, 'loop') and self.loop and self.loop.is_running():
                    self.loop.run_until_complete(self.capture.close_async())
                else:
                    self.capture.close()
            except Exception as e:
                print(f"Cleanup error: {e}")

    def _init_ui(self):
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        layout = QHBoxLayout(main_widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.sidebar = self._create_sidebar()
        layout.addWidget(self.sidebar)
        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(20, 20, 20, 20)
        content_layout.setSpacing(20)
        layout.addWidget(content)
        header = self._create_header()
        content_layout.addWidget(header)
        status_section = self._create_status_section()
        content_layout.addLayout(status_section)
        line_list = self._create_line_list()
        log_list = self._create_log_list()
        content_layout.addWidget(line_list, 80)
        content_layout.addWidget(log_list, 20)
        content_layout.setStretch(2, 80)
        content_layout.setStretch(3, 20)
        self._apply_styles()
        self.resize(1400, 900)
        self.settings_popup.settings_changed.connect(self.update_dashboard_settings)
        self.settings_popup.path_changed.connect(self.update_storage_path)

    def load_network_interfaces(self):
        try:
            interfaces = list(psutil.net_if_addrs().keys())
            config = load_config()
            default_interface = config.get('Network', 'interface', fallback=interfaces[0])
            self.selected_interface = default_interface
        except Exception as e:
            print(f"네트워크 인터페이스 로드 실패: {e}")

    def start_packet_capture(self):
        if not self.capture_thread or not self.capture_thread.is_alive():
            self.capture_thread = threading.Thread(
                target=self.capture_packets,
                args=(self.selected_interface,),
                daemon=True
            )
            self.capture_thread.start()

    def _create_header(self):
        header = QWidget()
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(10, 5, 10, 5)
        phone_section = QWidget()
        phone_layout = QHBoxLayout(phone_section)
        phone_layout.setAlignment(Qt.AlignLeft)
        phone_layout.setContentsMargins(0, 0, 0, 0)
        phone_text = QLabel("대표번호 | ")
        self.phone_number = QLabel()
        config = configparser.ConfigParser()
        config.read('settings.ini', encoding='utf-8')
        self.phone_number.setText(config.get('Extension', 'rep_number', fallback=''))
        phone_layout.addWidget(phone_text)
        phone_layout.addWidget(self.phone_number)
        id_section = QWidget()
        id_layout = QHBoxLayout(id_section)
        id_layout.setAlignment(Qt.AlignRight)
        id_layout.setContentsMargins(0, 0, 0, 0)
        id_text = QLabel("ID CODE | ")
        self.id_code = QLabel()
        self.id_code.setText(config.get('Extension', 'id_code', fallback=''))
        id_layout.addWidget(id_text)
        id_layout.addWidget(self.id_code)
        header_layout.addWidget(phone_section, 1)
        header_layout.addWidget(id_section, 1)
        return header

    def _create_sidebar(self):
        sidebar = QWidget()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(200)
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        logo_container = QWidget()
        logo_container_layout = QVBoxLayout(logo_container)
        logo_container_layout.setContentsMargins(0, 30, 0, 30)
        logo_container_layout.setSpacing(0)
        logo_label = QLabel()
        logo_label.setAlignment(Qt.AlignCenter)
        logo_pixmap = QPixmap(resource_path("images/recapvoice_squere_w.png"))
        if not logo_pixmap.isNull():
            aspect_ratio = logo_pixmap.height() / logo_pixmap.width()
            target_width = 120
            target_height = int(target_width * aspect_ratio)
            scaled_logo = logo_pixmap.scaled(
                target_width,
                target_height,
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation
            )
            logo_label.setPixmap(scaled_logo)
        logo_container_layout.addWidget(logo_label)
        layout.addWidget(logo_container)
        menu_container = QWidget()
        menu_layout = QVBoxLayout(menu_container)
        menu_layout.setContentsMargins(0, 0, 0, 0)
        menu_layout.setSpacing(5)
        voip_btn = self._create_menu_button("VOIP MONITOR", "images/voip_icon.png")
        voip_btn.clicked.connect(self.show_voip_monitor)
        packet_btn = self._create_menu_button("PACKET MONITOR", "images/packet_icon.png")
        packet_btn.clicked.connect(self.show_packet_monitor)
        menu_layout.addWidget(voip_btn)
        menu_layout.addWidget(packet_btn)
        menu_layout.addStretch()
        layout.addWidget(menu_container)
        return sidebar

    def _create_menu_button(self, text, icon_path):
        btn = QPushButton()
        btn.setObjectName("menu_button")
        btn.setFixedHeight(40)
        btn.setCursor(Qt.PointingHandCursor)
        layout = QHBoxLayout(btn)
        layout.setContentsMargins(15, 0, 15, 0)
        layout.setSpacing(0)
        icon_label = QLabel()
        icon_label.setFixedSize(24, 24)
        icon_pixmap = QPixmap(icon_path)
        if not icon_pixmap.isNull():
            scaled_icon = icon_pixmap.scaled(16, 16, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            icon_label.setPixmap(scaled_icon)
        layout.addWidget(icon_label)
        text_label = QLabel(text)
        text_label.setStyleSheet("color: #2d2d2d;")
        layout.addWidget(text_label)
        layout.addStretch()
        return btn

    def get_public_ip(self):
        try:
            response = requests.get('https://api64.ipify.org/?format=json')
            ip = response.json().get('ip')
            return ip
        except requests.RequestException as e:
            print(f"An error occurred: {e}")
            return None

    def _create_status_section(self):
        layout = QVBoxLayout()
        top_layout = QHBoxLayout()
        top_layout.setSpacing(15)
        network_group = self._create_info_group("네트워크 IP", self.get_public_ip())
        top_layout.addWidget(network_group, 25)
        config = configparser.ConfigParser()
        config.read('settings.ini', encoding='utf-8')
        port_mirror_ip = config.get('Network', 'ip', fallback='127.0.0.1')
        port_group = self._create_info_group("포트미러링 IP", port_mirror_ip)
        top_layout.addWidget(port_group, 25)
        client_start = self._create_client_start_group()
        top_layout.addWidget(client_start, 25)
        record_start = self._create_toggle_group("환경설정 / 관리사이트")
        top_layout.addWidget(record_start, 25)
        layout.addLayout(top_layout)
        bottom_layout = QHBoxLayout()
        bottom_layout.setSpacing(15)
        config.read('settings.ini', encoding='utf-8')
        storage_path = config.get('Recording', 'save_path', fallback='C:\\')
        drive_letter = storage_path.split(':')[0]
        disk_group = QGroupBox('디스크 정보')
        disk_layout = QHBoxLayout()
        self.disk_label = QLabel(f'녹취드라이버 ( {drive_letter} : ) 사용률:')
        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedHeight(18)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                text-align: center;
                border: 1px solid #ccc;
                border-radius: 2px;
                background-color: #f0f0f0;
            }
            QProgressBar::chunk {
                background-color: #18508F;
            }
        """)
        self.progress_bar.setMinimum(0)
        self.progress_bar.setMaximum(100)
        self.disk_usage_label = QLabel()
        disk_layout.addWidget(self.disk_label)
        disk_layout.addWidget(self.progress_bar)
        disk_layout.addWidget(self.disk_usage_label)
        disk_group.setLayout(disk_layout)
        bottom_layout.addWidget(disk_group, 80)
        led_group = QGroupBox('회선 상태')
        led_layout = QHBoxLayout()
        led_layout.addWidget(self._create_led_with_text('회선 연결 ', 'yellow'))
        led_layout.addWidget(self._create_led_with_text('대 기 중 ', 'blue'))
        led_layout.addWidget(self._create_led_with_text('녹 취 중 ', 'green'))
        led_group.setLayout(led_layout)
        bottom_layout.addWidget(led_group, 20)
        layout.addLayout(bottom_layout)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_disk_usage)
        self.timer.start(600000)
        self.update_disk_usage()
        return layout

    def _create_info_group(self, title, value):
        group = QGroupBox(title)
        layout = QVBoxLayout(group)
        layout.setContentsMargins(15, 20, 15, 15)
        if title == "네트워크 IP":
            self.ip_value = QLabel(value)
            value_label = self.ip_value
        elif title == "포트미러링 IP":
            self.mirror_ip_value = QLabel(value)
            value_label = self.mirror_ip_value
        else:
            value_label = QLabel(value)
        value_label.setObjectName("statusLabel")
        value_label.setAlignment(Qt.AlignCenter)
        value_label.setStyleSheet("""
            color: #3e5063;
            font-size: 14px;
            font-weight: bold;
        """)
        layout.addWidget(value_label)
        return group

    def _create_toggle_group(self, title):
        group = QGroupBox(title)
        layout = QHBoxLayout(group)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(2)
        button_container = QWidget()
        button_layout = QHBoxLayout(button_container)
        button_layout.setContentsMargins(0, 0, 0, 0)
        button_layout.setSpacing(2)
        settings_btn = QPushButton("환경설정")
        settings_btn.setObjectName("toggleOn")
        settings_btn.setCursor(Qt.PointingHandCursor)
        settings_btn.clicked.connect(self.show_settings)
        admin_btn = QPushButton("관리사이트이동")
        admin_btn.setObjectName("toggleOff")
        admin_btn.setCursor(Qt.PointingHandCursor)
        admin_btn.clicked.connect(self.open_admin_site)
        button_layout.addWidget(settings_btn, 1)
        button_layout.addWidget(admin_btn, 1)
        layout.addWidget(button_container)
        return group

    def _create_line_list(self):
        group = QGroupBox("전화연결 상태")
        group.setObjectName("line_list")
        group.setMaximumHeight(400)
        group.setStyleSheet("""
            QGroupBox {
                background-color: #2d2d2d !important;
                border: 1px solid #3a3a3a;
                border-radius: 4px;
                margin-top: 10px;
                padding: 10px;
                color: white;
                font-weight: bold;
            }
            QScrollArea {
                background-color: #2d2d2d !important;
            }
            QWidget#scrollContents {
                background-color: #2d2d2d !important;
            }
        """)
        layout = QVBoxLayout(group)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.calls_container = QWidget()
        self.calls_container.setObjectName("scrollContents")
        self.calls_layout = FlowLayout(self.calls_container, margin=0, spacing=20)
        scroll.setWidget(self.calls_container)
        layout.addWidget(scroll)
        self.active_extensions = {}
        return group

    def _create_call_block(self, internal_number, received_number, duration, status):
        block = QWidget()
        block.setFixedSize(200, 150)
        block.setObjectName("callBlock")
        layout = QVBoxLayout(block)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(0)
        layout.setAlignment(Qt.AlignTop)
        top_container = QWidget()
        top_layout = QVBoxLayout(top_container)
        top_layout.setContentsMargins(0, 0, 0, 0)
        top_layout.setSpacing(4)
        top_layout.setAlignment(Qt.AlignTop)
        led_container = QWidget()
        led_layout = QHBoxLayout(led_container)
        led_layout.setContentsMargins(0, 0, 0, 0)
        led_layout.setSpacing(4)
        led_layout.setAlignment(Qt.AlignRight)
        if status != "대기중" and received_number:
            led_states = ["회선 연결", "녹취중"]
        else:
            led_states = ["회선 연결", "대기중"]
        for state in led_states:
            led = self._create_led("", self._get_led_color(state))
            led_layout.addWidget(led)
        top_layout.addWidget(led_container)
        info_layout = QGridLayout()
        info_layout.setSpacing(4)
        info_layout.setContentsMargins(0, 0, 0, 0)
        # 내선번호 레이블은 "extensionLabel", 통화 시간 레이블은 "durationLabel"
        if status != "대기중" and received_number:
            labels = [
                ("내선:", internal_number),
                ("수신:", received_number),
                ("상태:", status),
                ("시간:", duration)
            ]
        else:
            labels = [
                ("내선:", internal_number),
                ("상태:", status)
            ]
        for idx, (title, value) in enumerate(labels):
            title_label = QLabel(title)
            title_label.setObjectName("blockTitle")
            title_label.setStyleSheet("color: #888888; font-size: 12px;")
            value_label = QLabel(value)
            # objectName 지정
            if title.strip() == "내선:":
                value_label.setObjectName("extensionLabel")
            elif title.strip() == "시간:":
                value_label.setObjectName("durationLabel")
            else:
                value_label.setObjectName("blockValue")
            value_label.setStyleSheet("color: white; font-size: 12px; font-weight: bold; margin-left: 4px;")
            info_layout.addWidget(title_label, idx, 0)
            info_layout.addWidget(value_label, idx, 1)
        top_layout.addLayout(info_layout)
        layout.addWidget(top_container)
        base_style = """
            QWidget#callBlock {
                border-radius: 4px;
                background-color: #2A2A2A;
                border: 1px solid #383838;
            }
            QLabel#blockTitle {
                color: #888888;
                font-size: 12px;
                font-weight: normal;
            }
            QLabel#blockValue, QLabel#extensionLabel {
                font-size: 12px;
                font-weight: bold;
                margin-left: 4px;
            }
        """
        if status == "대기중":
            block.setStyleSheet(base_style + """
                QWidget#callBlock {
                    background-color: #2A2A2A;
                    border: 1px solid #383838;
                }
                QLabel#blockValue, QLabel#extensionLabel {
                    color: #888888;
                }
            """)
            effect = QGraphicsOpacityEffect()
            effect.setOpacity(0.6)
            block.setGraphicsEffect(effect)
        else:
            block.setStyleSheet(base_style + """
                QWidget#callBlock {
                    background-color: #2A2A2A;
                    border: 2px solid #18508F;
                }
                QLabel#blockValue, QLabel#extensionLabel {
                    color: #FFFFFF;
                }
            """)
            shadow = QGraphicsDropShadowEffect()
            shadow.setBlurRadius(10)
            shadow.setColor(QColor("#18508F"))
            shadow.setOffset(0, 0)
            block.setGraphicsEffect(shadow)
        return block

    def _get_led_color(self, state):
        colors = {
            "회선 연결": "yellow",
            "대기중": "blue",
            "녹취중": "green",
        }
        return colors.get(state, "yellow")

    def _create_log_list(self):
        group = QGroupBox("LOG LIST")
        group.setMinimumHeight(200)
        layout = QVBoxLayout(group)
        layout.setContentsMargins(15, 15, 15, 15)
        table = QTableWidget()
        table.setObjectName("log_list_table")
        table.setColumnCount(7)
        table.setHorizontalHeaderLabels([
            '시간', '통화 방향', '발신번호', '수신번호', '상태', '결과', 'Call-ID'
        ])
        table.setStyleSheet("""
            QTableWidget {
                background-color: #2D2A2A;
                color: white;
                gridline-color: #444444;
            }
            QHeaderView::section {
                background-color: #1E1E1E;
                color: white;
                padding: 5px;
                border: 1px solid #444444;
            }
            QTableWidget::item {
                border: 1px solid #444444;
            }
            QTableWidget::item:selected {
                background-color: #4A90E2;
                color: white;
            }
        """)
        table.setColumnWidth(0, 150)
        table.setColumnWidth(1, 80)
        table.setColumnWidth(2, 120)
        table.setColumnWidth(3, 120)
        table.setColumnWidth(4, 80)
        table.setColumnWidth(5, 80)
        table.setColumnWidth(6, 400)
        table.setSelectionBehavior(QTableWidget.SelectRows)
        table.setSelectionMode(QTableWidget.SingleSelection)
        table.setSortingEnabled(True)
        table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(table)
        return group

    def _apply_styles(self):
        self.setStyleSheet("""
            QMainWindow {
                background-color: #2d2d2d;
            }
            QWidget#sidebar {
                background-color: #38ab89;
            }
            QWidget {
                font-family: 'Segoe UI', sans-serif;
                color: white;
            }
            QPushButton#menu_button {
                background-color: #48c9b0;
                border: none;
                text-align: left;
                padding: 10px 15px;
            }
            QPushButton#menu_button:hover {
                background-color: rgba(255, 255, 255, 0.5);
            }
            QPushButton#menu_button QLabel {
                color: black;
                font-weight: bold;
            }
            QGroupBox {
                border: 1px solid #3a3a3a;
                border-radius: 4px;
                margin-top: 10px;
                padding: 10px;
                color: white;
                font-weight: bold;
            }
            #statusLabel {
                background-color: #48c9b0;
                padding: 5px;
                border-radius: 4px;
            }
            #toggleOff, #toggleOn {
                min-height: 35px;
                border: none;
                border-radius: 4px;
            }
            #toggleOff {
                background-color: #34495e;
                color: white;
            }
            #toggleOff:hover {
                background-color: black;
            }
            #toggleOn {
                background-color: #8e44ad;
                color: white;
            }
            #toggleOn:hover {
                background-color: black;
            }
            QTableWidget {
                background-color: #2A2A2A;
                border: none;
                gridline-color: #3a3a3a;
            }
            QTableWidget::item {
                padding: 5px;
            }
            QHeaderView::section {
                background-color: #2A2A2A;
                padding: 5px;
                border: none;
            }
            QWidget#callBlock {
                color: white;
                padding: 10px;
            }
            QWidget#callBlock QLabel {
                color: white;
                font-size: 12px;
            }
        """)

    def _create_led_with_text(self, text, color):
        widget = QWidget()
        layout = QHBoxLayout()
        layout.setAlignment(Qt.AlignLeft)
        layout.setContentsMargins(0, 0, 0, 0)
        led = QLabel()
        led.setObjectName("led_indicator")
        led.setFixedSize(8, 8)
        led.setStyleSheet(f'#led_indicator {{ background-color: {color}; border-radius: 4px; border: 1px solid rgba(0, 0, 0, 0.2); }}')
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(0)
        shadow.setColor(QColor(color))
        shadow.setOffset(0, 0)
        led.setGraphicsEffect(shadow)
        text_label = QLabel(text)
        text_label.setStyleSheet("color: white; font-size: 12px;")
        layout.addWidget(led)
        layout.addWidget(text_label)
        widget.setLayout(layout)
        return widget

    def _create_led(self, label, color):
        widget = QWidget()
        layout = QHBoxLayout()
        layout.setAlignment(Qt.AlignCenter)
        layout.setContentsMargins(0, 0, 0, 0)
        led = QLabel()
        led.setObjectName("led_indicator")
        led.setFixedSize(8, 8)
        led.setStyleSheet(f'#led_indicator {{ background-color: {color}; border-radius: 4px; border: 1px solid rgba(0, 0, 0, 0.2); }}')
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(3)
        shadow.setColor(QColor(color))
        shadow.setOffset(0, 0)
        led.setGraphicsEffect(shadow)
        layout.addWidget(led)
        widget.setLayout(layout)
        return widget

    def update_disk_usage(self):
        try:
            config = configparser.ConfigParser()
            config.read('settings.ini', encoding='utf-8')
            storage_path = config.get('Recording', 'save_path', fallback='D:\\')
            drive_letter = storage_path.replace('\\', '/').split('/')[0].split(':')[0]
            disk_usage = psutil.disk_usage(f"{drive_letter}:")
            total_gb = disk_usage.total / (1024**3)
            used_gb = disk_usage.used / (1024**3)
            free_gb = disk_usage.free / (1024**3)
            percent = int(disk_usage.percent)
            self.disk_label.setText(f'녹취드라이버( {drive_letter}: )')
            self.progress_bar.setValue(percent)
            self.disk_usage_label.setText(f'전체: {total_gb:.1f}GB | 사용중: {used_gb:.1f}GB | 남은용량: {free_gb:.1f}GB')
        except Exception as e:
            print(f"Error updating disk info: {e}")
            self.disk_usage_label.setText(f'{drive_letter}드라이브 정보를 읽을 수 없습니다')

    def show_voip_monitor(self):
        try:
            self.voip_window = VoipMonitor()
            self.voip_window.setWindowFlags(Qt.Window)
            self.voip_window.setAttribute(Qt.WA_QuitOnClose, False)
            self.voip_window.show()
            config = load_config()
            if config.get('Environment', 'mode') == 'production':
                wireshark_path = get_wireshark_path()
                def hide_wireshark_windows():
                    try:
                        for proc in psutil.process_iter(['pid', 'name', 'exe']):
                            if proc.info['name'] in ['dumpcap.exe', 'tshark.exe']:
                                if proc.info['exe'] and wireshark_path in proc.info['exe']:
                                    def enum_windows_callback(hwnd, _):
                                        try:
                                            _, pid = win32process.GetWindowThreadProcessId(hwnd)
                                            if pid == proc.info['pid']:
                                                style = win32gui.GetWindowLong(hwnd, win32con.GWL_STYLE)
                                                style &= ~win32con.WS_VISIBLE
                                                win32gui.SetWindowLong(hwnd, win32con.GWL_STYLE, style)
                                                win32gui.ShowWindow(hwnd, win32con.SW_HIDE)
                                        except:
                                            pass
                                        return True
                                    win32gui.EnumWindows(enum_windows_callback, None)
                    except Exception as e:
                        print(f"Error hiding windows: {e}")
                self.hide_console_timer = QTimer()
                self.hide_console_timer.timeout.connect(hide_wireshark_windows)
                self.hide_console_timer.start(100)
        except Exception as e:
            print(f"Error opening VOIP Monitor: {e}")
            QMessageBox.warning(self, "오류", "VOIP Monitor를 열 수 없습니다.")

    def show_packet_monitor(self):
        try:
            self.packet_monitor = PacketMonitor()
            self.packet_monitor.setWindowFlags(Qt.Window)
            self.packet_monitor.setAttribute(Qt.WA_QuitOnClose, False)
            self.packet_monitor.show()
            config = load_config()
            if config.get('Environment', 'mode') == 'production':
                wireshark_path = get_wireshark_path()
                def hide_wireshark_windows():
                    try:
                        for proc in psutil.process_iter(['pid', 'name', 'exe']):
                            if proc.info['name'] in ['dumpcap.exe', 'tshark.exe']:
                                if proc.info['exe'] and wireshark_path in proc.info['exe']:
                                    def enum_windows_callback(hwnd, _):
                                        try:
                                            _, pid = win32process.GetWindowThreadProcessId(hwnd)
                                            if pid == proc.info['pid']:
                                                style = win32gui.GetWindowLong(hwnd, win32con.GWL_STYLE)
                                                style &= ~win32con.WS_VISIBLE
                                                win32gui.SetWindowLong(hwnd, win32con.GWL_STYLE, style)
                                                win32gui.ShowWindow(hwnd, win32con.SW_HIDE)
                                        except:
                                            pass
                                        return True
                                    win32gui.EnumWindows(enum_windows_callback, None)
                    except Exception as e:
                        print(f"Error hiding windows: {e}")
                self.hide_console_timer = QTimer()
                self.hide_console_timer.timeout.connect(hide_wireshark_windows)
                self.hide_console_timer.start(100)
        except Exception as e:
            print(f"Error opening Packet Monitor: {e}")
            QMessageBox.warning(self, "오류", "Packet Monitor를 열 수 없습니다.")

    def show_settings(self):
        try:
            self.settings_popup = SettingsPopup(self)
            self.settings_popup.settings_changed.connect(self.update_dashboard_settings)
            self.settings_popup.path_changed.connect(self.update_storage_path)
            self.settings_popup.exec()
        except Exception as e:
            print(f"설정 창 표시 중 오류: {e}")
            QMessageBox.warning(self, "오류", "Settings를 열 수 없습니다.")

    def update_dashboard_settings(self, settings_data):
        try:
            if 'Extension' in settings_data:
                self.phone_number.setText(settings_data['Extension']['rep_number'])
            if 'Network' in settings_data:
                self.ip_value.setText(settings_data['Network']['ap_ip'])
                self.mirror_ip_value.setText(settings_data['Network']['ip'])
            if 'Recording' in settings_data:
                drive_letter = settings_data['Recording']['save_path'].split(':')[0]
                self.disk_label.setText(f'녹취드라이버 ( {drive_letter} : ) 사용률:')
            self.update_disk_usage()
        except Exception as e:
            print(f"Error updating dashboard settings: {e}")
            QMessageBox.warning(self, "오류", "대시보드 업데이트 중 오류가 발생했습니다.")

    def update_storage_path(self, new_path):
        try:
            config = configparser.ConfigParser()
            config.read('settings.ini', encoding='utf-8')
            if 'Recording' not in config:
                config['Recording'] = {}
            config['Recording']['save_path'] = new_path
            self.update_disk_usage()
        except Exception as e:
            print(f"Error updating storage path: {e}")
            QMessageBox.warning(self, "오류", "저장 경로 업데이트 중 오류가 발생했습니다.")

    TABLE_STYLE = """
        QTableWidget::item:selected {
            background-color: #18508F;
            color: white;
        }
    """

    def _set_table_style(self, table: QTableWidget) -> None:
        table.setSelectionBehavior(QTableWidget.SelectRows)
        table.setSelectionMode(QTableWidget.SingleSelection)
        table.setStyleSheet(self.TABLE_STYLE)

    @Slot(str)
    def create_waiting_block(self, extension):
        try:
            if not self.block_exists(extension):
                block = self._create_call_block(
                    internal_number=extension,
                    received_number="",
                    duration="00:00:00",
                    status="대기중"
                )
                self.calls_layout.addWidget(block)
                print(f"대기중 블록 생성됨: {extension}")
        except Exception as e:
            print(f"대기중 블록 생성 중 오류: {e}")

    def log_error(self, message, error=None, additional_info=None):
        try:
            with open('voip_monitor.log', 'a', encoding='utf-8', buffering=1) as log_file:  # buffering=1: 라인 버퍼링
                timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
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

    def analyze_sip_packet(self, packet):
        try:
            sip_layer = packet.sip
            call_id = sip_layer.call_id
            if hasattr(sip_layer, 'request_line'):
                request_line = str(sip_layer.request_line)
                self.log_error("SIP 패킷 분석", additional_info={
                    "request_line": request_line,
                    "call_id": call_id
                })

                # INVITE 처리 시 블록 생성 로직 강화
                if 'INVITE' in request_line:
                    try:
                        from_number = self.extract_number(sip_layer.from_user)
                        to_number = self.extract_number(sip_layer.to_user)
                        
                        # 내선번호 확인 및 블록 생성
                        extension = None
                        if len(from_number) == 4 and from_number[0] in '123456789':
                            extension = from_number
                        elif len(to_number) == 4 and to_number[0] in '123456789':
                            extension = to_number
                        
                        if extension:
                            self.log_error("내선 블록 생성 시도", additional_info={
                                "extension": extension,
                                "from_number": from_number,
                                "to_number": to_number
                            })
                            # 메인 스레드에서 블록 생성
                            self.block_creation_signal.emit(extension)
                        
                        # 기존 통화 정보 저장 로직
                        with self.active_calls_lock:
                            before_state = dict(self.active_calls) if call_id in self.active_calls else None
                            self.active_calls[call_id] = {
                                'start_time': datetime.datetime.now(),
                                'status': '시도중',
                                'from_number': from_number,
                                'to_number': to_number,
                                'direction': '수신' if to_number.startswith(('1','2','3','4','5','6','7','8','9')) else '발신',
                                'media_endpoints': []
                            }
                            after_state = dict(self.active_calls[call_id])
                            self.log_error("통화 상태 업데이트", additional_info={
                                "before": before_state,
                                "after": after_state
                            })
                            
                            self.call_state_machines[call_id] = CallStateMachine()
                            self.call_state_machines[call_id].update_state(CallState.TRYING)
                        self.update_call_status(call_id, '시도중')
                        
                    except Exception as invite_error:
                        self.log_error("INVITE 처리 중 오류", invite_error)

                elif 'REFER' in request_line:
                    try:
                        with open('voip_monitor.log', 'a', encoding='utf-8') as log_file:
                            log_file.write("\n=== 돌려주기 요청 감지 ===\n")
                            log_file.write(f"시간: {datetime.datetime.now()}\n")
                            log_file.write(f"Call-ID: {call_id}\n")
                            log_file.write(f"Request Line: {request_line}\n")
                            
                            # active_calls 상태 로깅
                            with self.active_calls_lock:
                                if call_id not in self.active_calls:
                                    log_file.write(f"[오류] 해당 Call-ID를 찾을 수 없음: {call_id}\n")
                                    return
                                original_call = dict(self.active_calls[call_id])
                                log_file.write(f"현재 통화 정보: {original_call}\n")
                            
                            # 필수 정보 확인
                            if not all(k in original_call for k in ['to_number', 'from_number']):
                                log_file.write("[오류] 필수 통화 정보 누락\n")
                                log_file.write(f"누락된 정보: {set(['to_number', 'from_number']) - set(original_call.keys())}\n")
                                return
                                
                            external_number = original_call['to_number']
                            forwarding_ext = original_call['from_number']
                            
                            # REFER-TO 헤더 확인
                            if not hasattr(sip_layer, 'refer_to'):
                                log_file.write("[오류] REFER 헤더가 존재하지 않습니다.\n")
                                log_file.write(f"사용 가능한 SIP 헤더들: {dir(sip_layer)}\n")
                                return
                                
                            refer_to = str(sip_layer.refer_to)
                            log_file.write(f"REFER-TO 헤더: {refer_to}\n")
                            
                            forwarded_ext = self.extract_number(refer_to.split('@')[0])
                            if not forwarded_ext:
                                log_file.write("[오류] 유효하지 않은 Refer-To 번호\n")
                                return
                                
                            log_file.write(f"발신번호(유지): {external_number}\n")
                            log_file.write(f"수신번호(유지): {forwarding_ext}\n")
                            log_file.write(f"돌려받을 내선: {forwarded_ext}\n")
                            
                            # 통화 상태 업데이트
                            update_info = {
                                'status': '통화중',
                                'is_forwarded': True,
                                'forward_to': forwarded_ext,
                                'result': '돌려주기',
                                'from_number': external_number,
                                'to_number': forwarding_ext
                            }
                            
                            with self.active_calls_lock:
                                if call_id in self.active_calls:
                                    before_update = dict(self.active_calls[call_id])
                                    self.active_calls[call_id].update(update_info)
                                    after_update = dict(self.active_calls[call_id])
                                    log_file.write("통화 상태 업데이트:\n")
                                    log_file.write(f"업데이트 전: {before_update}\n")
                                    log_file.write(f"업데이트 후: {after_update}\n")
                                    
                                    # 관련 통화 상태도 업데이트
                                    for active_call_id, call_info in self.active_calls.items():
                                        if (call_info.get('from_number') == forwarding_ext and 
                                            call_info.get('to_number') == forwarding_ext):
                                            before_related = dict(call_info)
                                            call_info.update({
                                                'status': '통화중',
                                                'result': '돌려주기'
                                            })
                                            after_related = dict(call_info)
                                            log_file.write(f"관련 통화 업데이트 (Call-ID: {active_call_id}):\n")
                                            log_file.write(f"업데이트 전: {before_related}\n")
                                            log_file.write(f"업데이트 후: {after_related}\n")
                            
                            log_file.write("=== 돌려주기 처리 완료 ===\n\n")
                            
                    except Exception as ex:
                        with open('voip_monitor.log', 'a', encoding='utf-8') as log_file:
                            log_file.write(f"\n[심각한 오류] REFER 처리 중 예외 발생: {ex}\n")
                            import traceback
                            log_file.write(traceback.format_exc())
                            log_file.write("\n")
                        return
                elif 'BYE' in request_line:
                    try:
                        with self.active_calls_lock:
                            if call_id in self.active_calls:
                                before_state = dict(self.active_calls[call_id])
                                self.update_call_status(call_id, '통화종료', '정상종료')
                                extension = self.get_extension_from_call(call_id)
                                after_state = dict(self.active_calls[call_id])
                                self.log_error("BYE 처리", additional_info={
                                    "extension": extension,
                                    "before_state": before_state,
                                    "after_state": after_state
                                })
                        if extension:
                            self.block_update_signal.emit(extension, "대기중", "")
                    except Exception as bye_error:
                        self.log_error("BYE 처리 중 오류", bye_error)
                        
                elif 'CANCEL' in request_line:
                    try:
                        with self.active_calls_lock:
                            if call_id in self.active_calls:
                                before_state = dict(self.active_calls[call_id])
                                self.update_call_status(call_id, '통화종료', '발신취소')
                                extension = self.get_extension_from_call(call_id)
                                after_state = dict(self.active_calls[call_id])
                                self.log_error("CANCEL 처리", additional_info={
                                    "extension": extension,
                                    "before_state": before_state,
                                    "after_state": after_state
                                })
                        if extension:
                            self.block_update_signal.emit(extension, "대기중", "")
                    except Exception as cancel_error:
                        self.log_error("CANCEL 처리 중 오류", cancel_error)
                        
            elif hasattr(sip_layer, 'status_line'):
                status_code = sip_layer.status_code
                if status_code == '100':
                    extension = self.extract_number(sip_layer.from_user)
                    if extension and len(extension) == 4 and extension[0] in ['1','2','3','4','5','6','7','8','9']:
                        self.block_update_signal.emit(extension, "대기중", "")
                with self.active_calls_lock:
                    if call_id in self.active_calls:
                        if status_code == '183':
                            self.update_call_status(call_id, '벨울림')
                            extension = self.get_extension_from_call(call_id)
                            if extension:
                                received_number = self.active_calls[call_id]['to_number']
                                self.block_update_signal.emit(extension, "벨울림", received_number)
                        elif status_code == '200':
                            if self.active_calls[call_id]['status'] != '통화종료':
                                self.update_call_status(call_id, '통화중')
                                extension = self.get_extension_from_call(call_id)
                                if extension:
                                    received_number = self.active_calls[call_id]['to_number']
                                    self.block_update_signal.emit(extension, "통화중", received_number)
        except Exception as e:
            self.log_error("SIP 패킷 분석 중 심각한 오류", e)
            import traceback
            print(traceback.format_exc())

    def handle_new_call(self, sip_layer, call_id):
        try:
            print(f"새로운 통화 처리 시작 - Call-ID: {call_id}")
            from_number = self.extract_number(sip_layer.from_user)
            to_number = self.extract_number(sip_layer.to_user)
            print(f"발신번호: {from_number}")
            print(f"수신번호: {to_number}")
            with self.active_calls_lock:
                self.active_calls[call_id] = {
                    'start_time': datetime.datetime.now(),
                    'status': '시도중',
                    'from_number': from_number,
                    'to_number': to_number,
                    'direction': '수신' if to_number.startswith(('1','2','3','4','5','6','7','8','9')) else '발신',
                    'media_endpoints': []
                }
                self.call_state_machines[call_id] = CallStateMachine()
                self.call_state_machines[call_id].update_state(CallState.TRYING)
            print(f"통화 정보 저장 완료: {self.active_calls[call_id]}")
        except Exception as e:
            print(f"새 통화 처리 중 오류: {e}")

    def handle_call_end(self, sip_layer, call_id):
        with self.active_calls_lock:
            if call_id in self.active_calls:
                self.active_calls[call_id].update({
                    'status': '통화종료',
                    'end_time': datetime.datetime.now(),
                    'result': '정상종료'
                })
        self.update_voip_status()
        extension = self.get_extension_from_call(call_id)
        if extension:
            QMetaObject.invokeMethod(self, "update_block_to_waiting", Qt.QueuedConnection, Q_ARG(str, extension))
            print(f"통화 종료 처리: {extension}")

    def get_extension_from_call(self, call_id):
        with self.active_calls_lock:
            if call_id in self.active_calls:
                call_info = self.active_calls[call_id]
                from_number = call_info['from_number']
                to_number = call_info['to_number']
                is_extension = lambda num: num.startswith(('1', '2', '3', '4', '5', '6', '7', '8', '9')) and len(num) == 4
                return from_number if is_extension(from_number) else to_number if is_extension(to_number) else None
        return None

    def handle_call_cancel(self, call_id):
        with self.active_calls_lock:
            if call_id in self.active_calls:
                self.active_calls[call_id].update({
                    'status': '통화종료',
                    'end_time': datetime.datetime.now(),
                    'result': '발신취소'
                })

    def update_voip_status(self):
        try:
            table = self.findChild(QTableWidget, "log_list_table")
            if not table:
                return
            with self.active_calls_lock:
                sorted_calls = sorted(
                    self.active_calls.items(),
                    key=lambda x: x[1]['start_time'],
                    reverse=True
                )
            table.setRowCount(0)
            table.setRowCount(len(sorted_calls))
            for row, (call_id, call_info) in enumerate(sorted_calls):
                time_item = QTableWidgetItem(call_info['start_time'].strftime('%Y-%m-%d %H:%M:%S'))
                direction_item = QTableWidgetItem(call_info.get('direction', ''))
                from_item = QTableWidgetItem(str(call_info.get('from_number', '')))
                to_item = QTableWidgetItem(str(call_info.get('to_number', '')))
                status_item = QTableWidgetItem(call_info.get('status', ''))
                result_item = QTableWidgetItem(call_info.get('result', ''))
                callid_item = QTableWidgetItem(call_id)
                items = [time_item, direction_item, from_item, to_item, status_item, result_item, callid_item]
                for col, item in enumerate(items):
                    item.setTextAlignment(Qt.AlignCenter)
                    table.setItem(row, col, item)
            table.viewport().update()
        except Exception as e:
            print(f"VoIP 상태 업데이트 중 오류: {e}")

    def update_packet_status(self):
        try:
            with self.active_calls_lock:
                for call_id, call_info in self.active_calls.items():
                    if call_info.get('status_changed', False):
                        extension = self.get_extension_from_call(call_id)
                        if extension:
                            self.create_waiting_block(extension)
                        call_info['status_changed'] = False
        except Exception as e:
            print(f"패킷 상태 업데이트 중 오류: {e}")

    def calculate_duration(self, call_info):
        if 'start_time' in call_info:
            if 'end_time' in call_info:
                duration = call_info['end_time'] - call_info['start_time']
            else:
                duration = datetime.datetime.now() - call_info['start_time']
            return str(duration).split('.')[0]
        return "00:00:00"

    def is_rtp_packet(self, packet):
        try:
            if not hasattr(packet, 'udp') or not hasattr(packet.udp, 'payload'):
                return False
            payload_hex = packet.udp.payload.replace(':', '')
            try:
                payload = bytes.fromhex(payload_hex)
            except ValueError:
                return False
            if len(payload) < 12:
                return False
            version = (payload[0] >> 6) & 0x03
            if version != 2:
                return False
            payload_type = payload[1] & 0x7F
            return payload_type in [0, 8]
        except Exception as e:
            print(f"RTP 패킷 확인 중 오류: {e}")
            return False

    def determine_stream_direction(self, packet, call_id):
        try:
            if call_id not in self.active_calls:
                return None
            call_info = self.active_calls[call_id]
            if 'media_endpoints' not in call_info:
                call_info['media_endpoints'] = []
            if 'media_endpoints_set' not in call_info:
                call_info['media_endpoints_set'] = {'local': set(), 'remote': set()}
            src_ip = packet.ip.src
            dst_ip = packet.ip.dst
            try:
                pbx_ip = call_id.split('@')[1].split(';')[0].split(':')[0]
            except:
                print(f"PBX IP 추출 실패 - Call-ID: {call_id}")
                return None
            src_endpoint = f"{src_ip}:{packet.udp.srcport}"
            dst_endpoint = f"{dst_ip}:{packet.udp.dstport}"
            if src_ip == pbx_ip:
                endpoint_info = {"ip": src_ip, "port": packet.udp.srcport}
                if endpoint_info not in call_info['media_endpoints']:
                    call_info['media_endpoints'].append(endpoint_info)
                call_info['media_endpoints_set']['local'].add(src_endpoint)
                call_info['media_endpoints_set']['remote'].add(dst_endpoint)
                print(f"OUT 패킷: {src_endpoint} -> {dst_endpoint}")
                return "OUT"
            elif dst_ip == pbx_ip:
                endpoint_info = {"ip": dst_ip, "port": packet.udp.dstport}
                if endpoint_info not in call_info['media_endpoints']:
                    call_info['media_endpoints'].append(endpoint_info)
                call_info['media_endpoints_set']['local'].add(dst_endpoint)
                call_info['media_endpoints_set']['remote'].add(src_endpoint)
                print(f"IN 패킷: {src_endpoint} -> {dst_endpoint}")
                return "IN"
            if src_endpoint in call_info['media_endpoints_set']['local']:
                return "OUT"
            elif src_endpoint in call_info['media_endpoints_set']['remote']:
                return "IN"
            elif dst_endpoint in call_info['media_endpoints_set']['local']:
                return "IN"
            elif dst_endpoint in call_info['media_endpoints_set']['remote']:
                return "OUT"
            return None
        except Exception as e:
            print(f"방향 결정 중 오류: {e}")
            import traceback
            print(traceback.format_exc())
            return None

    def extract_number(self, sip_user):
        try:
            if not sip_user:
                return ''
            sip_user = str(sip_user)
            if 'sip:' in sip_user:
                number = sip_user.split('sip:')[1].split('@')[0]
                return ''.join(c for c in number if c.isdigit())
            if '109' in sip_user:
                for i, char in enumerate(sip_user):
                    if i > sip_user.index('109') + 2 and char.isalpha():
                        return sip_user[i+1:]
            return ''.join(c for c in sip_user if c.isdigit())
        except Exception as e:
            print(f"전화번호 추출 중 오류: {e}")
            return ''

    def get_call_id_from_rtp(self, packet):
        try:
            src_ip = packet.ip.src
            dst_ip = packet.ip.dst
            src_port = int(packet.udp.srcport)
            dst_port = int(packet.udp.dstport)
            src_endpoint = f"{src_ip}:{src_port}"
            dst_endpoint = f"{dst_ip}:{dst_port}"
            with self.active_calls_lock:
                for call_id, call_info in self.active_calls.items():
                    if "media_endpoints_set" in call_info:
                        if (src_endpoint in call_info["media_endpoints_set"]["local"] or 
                            src_endpoint in call_info["media_endpoints_set"]["remote"] or
                            dst_endpoint in call_info["media_endpoints_set"]["local"] or
                            dst_endpoint in call_info["media_endpoints_set"]["remote"]):
                            return call_id
                    elif "media_endpoints" in call_info:
                        for endpoint in call_info["media_endpoints"]:
                            if (src_ip == endpoint.get("ip") and src_port == endpoint.get("port")) or \
                               (dst_ip == endpoint.get("ip") and dst_port == endpoint.get("port")):
                                return call_id
            return None
        except Exception as e:
            print(f"RTP Call-ID 매칭 오류: {e}")
            import traceback
            print(traceback.format_exc())
            return None

    def handle_sip_response(self, status_code, call_id, sip_layer):
        try:
            if hasattr(sip_layer, 'from'):
                ip = None
                if '@' in call_id:
                    ip = call_id.split('@')[1]
                if ip:
                    extension = self.extract_number(sip_layer.from_user)
                    if ip not in self.sip_registrations:
                        self.sip_registrations[ip] = {'status': [], 'extension': extension}
                    self.sip_registrations[ip]['status'].append(status_code)
                    if len(self.sip_registrations[ip]['status']) >= 3:
                        recent_status = self.sip_registrations[ip]['status'][-3:]
                        if '100' in recent_status and '401' in recent_status and '200' in recent_status:
                            QMetaObject.invokeMethod(self, "create_waiting_block", Qt.QueuedConnection, Q_ARG(str, extension))
                            self.handle_first_registration()
            with self.active_calls_lock:
                if call_id in self.active_calls:
                    if status_code == '200':
                        self.active_calls[call_id]['status'] = '통화중'
                    elif status_code == '180':
                        self.active_calls[call_id]['status'] = '벨울림'
                    extension = self.get_extension_from_call(call_id)
                    received_number = self.active_calls[call_id].get('to_number', "")
                    self.block_update_signal.emit(extension, self.active_calls[call_id]['status'], received_number)
        except Exception as e:
            print(f"SIP 응답 처리 중 오류: {e}")

    def create_or_update_block(self, extension):
        self.block_creation_signal.emit(extension)

    def block_exists(self, extension):
        try:
            for i in range(self.calls_layout.count()):
                block = self.calls_layout.itemAt(i).widget()
                if block:
                    for label in block.findChildren(QLabel):
                        if label.objectName() == "extensionLabel" and label.text() == extension:
                            return True
            return False
        except Exception as e:
            print(f"블록 존재 여부 확인 중 오류: {e}")
            return False

    @Slot(str)
    def create_block_in_main_thread(self, extension):
        """메인 스레드에서 블록을 생성하는 메서드"""
        try:
            if not self.block_exists(extension):
                block = self._create_call_block(
                    internal_number=extension,
                    received_number="",
                    duration="00:00:00",
                    status="대기중"
                )
                self.calls_layout.addWidget(block)
                self.log_error("블록 생성 완료", additional_info={"extension": extension})
        except Exception as e:
            self.log_error("블록 생성 중 오류", e)

    def update_block_to_waiting(self, extension):
        try:
            for i in range(self.calls_layout.count()-1, -1, -1):
                block = self.calls_layout.itemAt(i).widget()
                if block:
                    for child in block.findChildren(QLabel):
                        if child.objectName() == "extensionLabel" and child.text() == extension:
                            self.calls_layout.removeWidget(block)
                            block.deleteLater()
            new_block = self._create_call_block(
                internal_number=extension,
                received_number="",
                duration="00:00:00",
                status="대기중"
            )
            self.calls_layout.addWidget(new_block)
            self.calls_layout.update()
            self.calls_container.update()
            print(f"블록 강제 업데이트 완료: {extension} -> 대기중")
            self.update_voip_status()
        except Exception as e:
            print(f"블록 강제 업데이트 오류: {e}")

    def update_block_in_main_thread(self, extension, status, received_number):
        try:
            for i in range(self.calls_layout.count()-1, -1, -1):
                block = self.calls_layout.itemAt(i).widget()
                if block:
                    for child in block.findChildren(QLabel):
                        if child.objectName() == "extensionLabel" and child.text() == extension:
                            self.calls_layout.removeWidget(block)
                            block.deleteLater()
            call_id = None
            with self.active_calls_lock:
                for cid, call_info in self.active_calls.items():
                    if self.get_extension_from_call(cid) == extension:
                        call_id = cid
                        break
            duration = "00:00:00"
            if call_id and status == "통화중":
                duration = self.calculate_duration(self.active_calls[call_id])
            new_block = self._create_call_block(
                internal_number=extension,
                received_number=received_number,
                duration=duration,
                status=status
            )
            self.calls_layout.addWidget(new_block)
            self.calls_layout.update()
            self.calls_container.update()
        except Exception as e:
            print(f"블록 업데이트 중 오류: {e}")

    def update_call_status(self, call_id, new_status, result=''):
        try:
            with self.active_calls_lock:
                if call_id in self.active_calls:
                    self.active_calls[call_id].update({
                        'status': new_status,
                        'result': result
                    })
                    if new_status == '통화종료':
                        self.active_calls[call_id]['end_time'] = datetime.datetime.now()
                        if hasattr(self, 'stream_manager'):
                            stream_info_in = None
                            stream_info_out = None
                            in_key = f"{call_id}_IN"
                            if in_key in self.stream_manager.active_streams:
                                stream_info_in = self.stream_manager.finalize_stream(in_key)
                            out_key = f"{call_id}_OUT"
                            if out_key in self.stream_manager.active_streams:
                                stream_info_out = self.stream_manager.finalize_stream(out_key)
                            if stream_info_in and stream_info_out:
                                try:
                                    file_dir = stream_info_in['file_dir']
                                    timestamp = os.path.basename(file_dir)
                                    local_num = self.active_calls[call_id]['from_number']
                                    remote_num = self.active_calls[call_id]['to_number']
                                    merged_file = self.wav_merger.merge_and_save(
                                        stream_info_in['phone_ip'],
                                        timestamp,
                                        timestamp,
                                        local_num,
                                        remote_num,
                                        stream_info_in['filepath'],
                                        stream_info_out['filepath'],
                                        file_dir
                                    )
                                    if merged_file:
                                        html_file = self.chat_extractor.extract_chat_to_html(
                                            stream_info_in['phone_ip'],
                                            timestamp,
                                            timestamp,
                                            local_num,
                                            remote_num,
                                            stream_info_in['filepath'],
                                            stream_info_out['filepath'],
                                            file_dir
                                        )
                                        if html_file:
                                            self._save_to_mongodb(
                                                merged_file, html_file, 
                                                local_num, remote_num
                                            )
                                            try:
                                                if os.path.exists(stream_info_in['filepath']):
                                                    os.remove(stream_info_in['filepath'])
                                                if os.path.exists(stream_info_out['filepath']):
                                                    os.remove(stream_info_out['filepath'])
                                            except Exception as e:
                                                print(f"파일 삭제 중 오류: {e}")
                                except Exception as e:
                                    print(f"파일 처리 중 오류: {e}")
                    extension = self.get_extension_from_call(call_id)
                    received_number = self.active_calls[call_id].get('to_number', "")
                    self.block_update_signal.emit(extension, new_status, received_number)
            self.update_voip_status()
        except Exception as e:
            print(f"통화 상태 업데이트 중 오류: {e}")

    @Slot()
    def handle_first_registration(self):
        try:
            if not self.first_registration:
                self.first_registration = True
                print("첫 번째 SIP 등록 완료")
        except Exception as e:
            print(f"첫 번째 등록 처리 중 오류: {e}")

    def capture_packets(self, interface):
        try:
            self.log_error("패킷 캡처 시작 시도", additional_info={"interface": interface})
            
            # 인터페이스 유효성 검사
            if not interface:
                self.log_error("유효하지 않은 인터페이스")
                return
                
            # 시스템 리소스 확인
            cpu_percent = psutil.cpu_percent()
            memory = psutil.virtual_memory()
            self.log_error("시스템 리소스 상태", additional_info={
                "cpu": f"{cpu_percent}%",
                "memory": f"{memory.percent}%"
            })
            
            # 캡처 초기화
            capture = None
            loop = None
            
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                
                # Wireshark 설정 확인
                wireshark_path = get_wireshark_path()
                if not os.path.exists(wireshark_path):
                    self.log_error("Wireshark 경로 오류", additional_info={"path": wireshark_path})
                    return
                    
                capture = pyshark.LiveCapture(
                    interface=interface,
                    display_filter='sip or (udp and (udp.port >= 10000 and udp.port <= 20000))'
                )
                
                # 패킷 캡처 시작
                for packet in capture.sniff_continuously():
                    try:
                        # 메모리 사용량 모니터링
                        process = psutil.Process()
                        if process.memory_percent() > 80:  # 메모리 사용량이 80% 이상이면 경고
                            self.log_error("높은 메모리 사용량 감지", 
                                additional_info={"memory_percent": process.memory_percent()})
                        
                        if 'SIP' in packet:
                            self.analyze_sip_packet(packet)
                        elif 'UDP' in packet and self.is_rtp_packet(packet):
                            self.handle_rtp_packet(packet)
                            
                    except Exception as packet_error:
                        self.log_error("패킷 처리 중 오류", packet_error)
                        continue
                        
            except KeyboardInterrupt:
                self.log_error("사용자에 의한 캡처 중단")
            except Exception as capture_error:
                self.log_error("캡처 프로세스 오류", capture_error)
                
            finally:
                self.cleanup_capture(capture, loop)
                
        except Exception as e:
            self.log_error("캡처 스레드 치명적 오류", e)
            
    def cleanup_capture(self, capture, loop):
        """캡처 리소스 정리"""
        try:
            if capture:
                try:
                    if loop and not loop.is_closed():
                        async def close_capture():
                            await capture.close_async()
                        loop.run_until_complete(close_capture())
                    else:
                        capture.close()
                except Exception as close_error:
                    self.log_error("캡처 종료 실패", close_error)
                    
            if loop and not loop.is_closed():
                try:
                    tasks = asyncio.all_tasks(loop) if hasattr(asyncio, 'all_tasks') else []
                    for task in tasks:
                        task.cancel()
                    loop.stop()
                    loop.close()
                except Exception as loop_error:
                    self.log_error("이벤트 루프 종료 실패", loop_error)
                    
        except Exception as cleanup_error:
            self.log_error("리소스 정리 중 오류", cleanup_error)

    def handle_rtp_packet(self, packet):
        try:
            if not hasattr(self, 'stream_manager'):
                self.stream_manager = RTPStreamManager()
                self.log_error("RTP 스트림 매니저 생성")
                
            active_calls = []
            with self.active_calls_lock:
                for call_id, call_info in self.active_calls.items():
                    if call_info.get('status') == '통화중':
                        active_calls.append((call_id, call_info))
                        
            if not active_calls:
                return
                
            for call_id, call_info in active_calls:
                try:
                    # 파일 경로 생성 전에 phone_ip 유효성 검사
                    if '@' not in call_id:
                        self.log_error("유효하지 않은 call_id 형식", additional_info={"call_id": call_id})
                        continue
                        
                    phone_ip = call_id.split('@')[1].split(';')[0].split(':')[0]
                    if not phone_ip:
                        self.log_error("phone_ip를 추출할 수 없음", additional_info={"call_id": call_id})
                        continue

                    # 저장 경로 확인 및 생성
                    config = configparser.ConfigParser()
                    config.read('settings.ini', encoding='utf-8')
                    base_path = config.get('Recording', 'save_path', fallback='D:/PacketWaveRecord')
                    
                    today = datetime.datetime.now().strftime("%Y%m%d")
                    time_str = datetime.datetime.now().strftime("%H%M%S")
                    
                    save_dir = os.path.join(base_path, today, phone_ip, time_str)
                    
                    try:
                        if not os.path.exists(save_dir):
                            os.makedirs(save_dir)
                            self.log_error("저장 디렉토리 생성", additional_info={"path": save_dir})
                    except Exception as dir_error:
                        self.log_error("디렉토리 생성 실패", dir_error, {"path": save_dir})
                        continue

                    direction = self.determine_stream_direction(packet, call_id)
                    if not direction:
                        continue
                        
                    if hasattr(packet.udp, 'payload'):
                        payload_hex = packet.udp.payload.replace(':', '')
                        try:
                            payload = bytes.fromhex(payload_hex)
                            version = (payload[0] >> 6) & 0x03
                            payload_type = payload[1] & 0x7F
                            sequence = int.from_bytes(payload[2:4], byteorder='big')
                            audio_data = payload[12:]
                            
                            if len(audio_data) == 0:
                                continue
                                
                            stream_key = self.stream_manager.create_stream(
                                call_id, direction, call_info, phone_ip
                            )
                            
                            if stream_key:
                                self.stream_manager.process_packet(
                                    stream_key, audio_data, sequence, payload_type
                                )
                                
                        except Exception as payload_error:
                            self.log_error("페이로드 분석 오류", payload_error)
                            continue
                            
                except Exception as call_error:
                    self.log_error("통화별 RTP 처리 오류", call_error, {"call_id": call_id})
                    continue
                    
        except Exception as e:
            self.log_error("RTP 패킷 처리 중 심각한 오류", e)
            import traceback
            self.log_error("상세 오류 정보", additional_info={"traceback": traceback.format_exc()})

    def save_wav_file(self, filepath, audio_data, payload_type):
        try:
            if len(audio_data) == 0:
                print("오디오 데이터가 없습니다.")
                return
            with wave.open(filepath, 'wb') as wav_file:
                wav_file.setnchannels(1)
                wav_file.setsampwidth(2)
                wav_file.setframerate(8000)
                if payload_type == 8:
                    decoded_data = audioop.alaw2lin(bytes(audio_data), 2)
                else:
                    decoded_data = audioop.ulaw2lin(bytes(audio_data), 2)
                amplified_data = audioop.mul(decoded_data, 2, 4.0)
                wav_file.writeframes(amplified_data)
                print(f"WAV 파일 저장 완료: {filepath}")
                print(f"원본 데이터 크기: {len(audio_data)} bytes")
                print(f"디코딩된 데이터 크기: {len(decoded_data)} bytes")
                print(f"최종 데이터 크기: {len(amplified_data)} bytes")
        except Exception as e:
            print(f"WAV 파일 저장 중 오류: {e}")

    def decode_alaw(self, audio_data):
        try:
            return audioop.alaw2lin(audio_data, 2)
        except Exception as e:
            print(f"A-law 디코딩 오류: {e}")
            return audio_data

    def decode_ulaw(self, audio_data):
        try:
            return audioop.ulaw2lin(audio_data, 2)
        except Exception as e:
            print(f"μ-law 디코딩 오류: {e}")
            return audio_data

    def update_call_duration(self):
        try:
            with self.active_calls_lock:
                for call_id, call_info in self.active_calls.items():
                    if call_info.get('status') == '통화중':
                        extension = self.get_extension_from_call(call_id)
                        if extension:
                            duration = self.calculate_duration(call_info)
                            self.block_update_signal.emit(extension, "통화중", call_info['to_number'])
                            for i in range(self.calls_layout.count()):
                                block = self.calls_layout.itemAt(i).widget()
                                if block:
                                    found = False
                                    for child in block.findChildren(QLabel):
                                        if child.objectName() == "extensionLabel" and child.text() == extension:
                                            found = True
                                            break
                                    if found:
                                        for label in block.findChildren(QLabel):
                                            if label.objectName() == "durationLabel":
                                                label.setText(duration)
                                                break
        except Exception as e:
            print(f"통화 시간 업데이트 중 오류: {e}")

    def _create_client_start_group(self):
        group = QGroupBox("클라이언트서버")
        layout = QHBoxLayout(group)
        layout.setContentsMargins(15, 20, 15, 15)
        layout.setSpacing(2)
        button_container = QWidget()
        button_layout = QHBoxLayout(button_container)
        button_layout.setContentsMargins(0, 0, 0, 0)
        button_layout.setSpacing(2)
        self.on_btn = QPushButton("ON")
        self.on_btn.setObjectName("toggleOn")
        self.on_btn.setCursor(Qt.PointingHandCursor)
        self.on_btn.clicked.connect(self.start_client)
        self.off_btn = QPushButton("OFF")
        self.off_btn.setObjectName("toggleOff")
        self.off_btn.setCursor(Qt.PointingHandCursor)
        self.off_btn.clicked.connect(self.stop_client)
        button_layout.addWidget(self.on_btn, 1)
        button_layout.addWidget(self.off_btn, 1)
        layout.addWidget(button_container)
        return group

    def start_client(self):
        try:
            subprocess.Popen(['start.bat'], shell=True)
            self.on_btn.setStyleSheet("""
                QPushButton {
                    background-color: #FF0000;
                    color: white;
                    border: none;
                    border-radius: 4px;
                    min-height: 35px;
                }
                QPushButton:hover {
                    background-color: #CC0000;
                }
            """)
        except Exception as e:
            print(f"클라이언트 시작 중 오류: {e}")

    def stop_client(self):
        try:
            processes_to_kill = ['nginx.exe', 'mongod.exe', 'node.exe','Dumpcap.exe']
            import os
            for process in processes_to_kill:
                os.system(f'taskkill /f /im {process}')
                print(f"프로세스 종료 시도: {process}")
            self.on_btn.setStyleSheet("""
                QPushButton {
                    background-color: #8e44ad;
                    color: white;
                    border: none;
                    border-radius: 4px;
                    min-height: 35px;
                }
                QPushButton:hover {
                    background-color: black;
                }
            """)
        except Exception as e:
            print(f"클라이언트 중지 중 오류: {e}")

    def extract_ip_from_callid(self, call_id):
        try:
            ip_part = call_id.split('@')[1]
            ip_part = ip_part.split(';')[0]
            ip_part = ip_part.replace('[', '').replace(']', '')
            ip_part = ip_part.split(':')[0]
            if self.is_valid_ip(ip_part):
                return ip_part
            else:
                print(f"유효하지 않은 IP 주소 형식: {ip_part}")
                return "unknown"
        except Exception as e:
            print(f"IP 주소 추출 실패. Call-ID: {call_id}, 오류: {e}")
            return "unknown"

    def is_valid_ip(self, ip):
        try:
            parts = ip.split('.')
            if len(parts) != 4:
                return False
            return all(0 <= int(part) <= 255 for part in parts)
        except:
            return False

    def open_admin_site(self):
        try:
            config = configparser.ConfigParser()
            config.read('settings.ini', encoding='utf-8')
            ip_address = config.get('Network', 'ip', fallback='127.0.0.1')
            url = f"http://{ip_address}:3000"
            QDesktopServices.openUrl(QUrl(url))
        except Exception as e:
            print(f"관리사이트 열기 실패: {e}")
            QMessageBox.warning(self, "오류", "관리사이트를 열 수 없습니다.")

    def _save_to_mongodb(self, merged_file, html_file, local_num, remote_num):
        try:
            max_id_doc = self.filesinfo.find_one(sort=[("id", -1)])
            next_id = 1 if max_id_doc is None else max_id_doc["id"] + 1
            now_kst = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9)))
            audio = AudioSegment.from_wav(merged_file)
            duration_seconds = int(len(audio) / 1000.0)
            hours = duration_seconds // 3600
            minutes = (duration_seconds % 3600) // 60
            seconds = duration_seconds % 60
            duration_formatted = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
            filesize = os.path.getsize(merged_file)
            doc = {
                "id": next_id,
                "user_id": local_num,
                "filename": merged_file,
                "from_number": local_num,
                "to_number": remote_num,
                "filesize": str(filesize),
                "filestype": "wav",
                "files_text": html_file,
                "down_count": 0,
                "created_at": now_kst,
                "playtime": duration_formatted,
            }
            result = self.filesinfo.insert_one(doc)
            print(f"MongoDB 저장 완료: {result.inserted_id} (재생시간: {duration_formatted})")
        except Exception as e:
            print(f"MongoDB 저장 중 오류: {e}")

    def setup_tray_icon(self):
        try:
            self.tray_icon = QSystemTrayIcon(self)
            app_icon = QIcon()
            app_icon.addFile(resource_path("images/recapvoice_squere.ico"), QSize(16, 16))
            app_icon.addFile(resource_path("images/recapvoice_squere.ico"), QSize(24, 24))
            app_icon.addFile(resource_path("images/recapvoice_squere.ico"), QSize(32, 32))
            app_icon.addFile(resource_path("images/recapvoice_squere.ico"), QSize(48, 48))
            if app_icon.isNull():
                app_icon = QApplication.style().standardIcon(QStyle.SP_ComputerIcon)
                print("아이콘 파일을 찾을 수 없습니다: images/recapvoice_squere.ico")
            self.tray_icon.setIcon(app_icon)
            self.setWindowIcon(app_icon)
            tray_menu = QMenu()
            open_action = QAction("Recap Voice 열기", self)
            open_action.triggered.connect(self.show_window)
            tray_menu.addAction(open_action)
            settings_action = QAction("환경 설정", self)
            settings_action.triggered.connect(self.show_settings)
            tray_menu.addAction(settings_action)
            tray_menu.addSeparator()
            quit_action = QAction("종료", self)
            quit_action.triggered.connect(self.quit_application)
            tray_menu.addAction(quit_action)
            self.tray_icon.setContextMenu(tray_menu)
            self.tray_icon.setToolTip("Recap Voice")
            self.tray_icon.show()
            self.tray_icon.activated.connect(self.tray_icon_activated)
        except Exception as e:
            print(f"트레이 아이콘 설정 중 오류: {e}")
            import traceback
            print(traceback.format_exc())

    def closeEvent(self, event):
        if self.tray_icon.isVisible():
            event.ignore()
            self.hide()
            self.tray_icon.showMessage(
                "Recap Voice",
                "프로그램이 트레이로 최소화되었습니다.",
                QSystemTrayIcon.Information,
                2000
            )

    def show_window(self):
        self.show()
        self.activateWindow()

    def show_settings(self):
        try:
            self.settings_popup = SettingsPopup(self)
            self.settings_popup.settings_changed.connect(self.update_dashboard_settings)
            self.settings_popup.path_changed.connect(self.update_storage_path)
            self.settings_popup.exec()
        except Exception as e:
            print(f"설정 창 표시 중 오류: {e}")
            QMessageBox.warning(self, "오류", "Settings를 열 수 없습니다.")

    def quit_application(self):
        try:
            self.tray_icon.hide()
            QApplication.quit()
        except Exception as e:
            print(f"프로그램 종료 중 오류: {e}")

    def tray_icon_activated(self, reason):
        if reason == QSystemTrayIcon.DoubleClick:
            self.show_window()

    def monitor_system_resources(self):
        try:
            process = psutil.Process()
            
            # CPU 사용량 모니터링
            cpu_percent = process.cpu_percent(interval=1.0)
            if cpu_percent > 80:  # CPU 사용량이 80% 이상인 경우
                self.log_error("높은 CPU 사용량 감지", additional_info={
                    "cpu_percent": cpu_percent,
                    "threads": len(process.threads()),
                    "open_files": len(process.open_files()),
                    "connections": len(process.connections())
                })
                
            # 스레드 상태 모니터링
            thread_count = len(process.threads())
            if thread_count > 100:  # 스레드가 비정상적으로 많은 경우
                self.log_error("비정상적인 스레드 수 감지", additional_info={
                    "thread_count": thread_count,
                    "thread_ids": [t.id for t in process.threads()]
                })
                
            # 파일 디스크립터 모니터링
            open_files = process.open_files()
            if len(open_files) > 1000:  # 열린 파일이 너무 많은 경우
                self.log_error("과도한 파일 디스크립터", additional_info={
                    "open_files_count": len(open_files),
                    "file_paths": [f.path for f in open_files[:10]]  # 처음 10개만 로깅
                })
                
            # 네트워크 연결 모니터링
            connections = process.connections()
            if len(connections) > 100:  # 연결이 너무 많은 경우
                self.log_error("과도한 네트워크 연결", additional_info={
                    "connection_count": len(connections),
                    "connection_status": [c.status for c in connections]
                })
                
        except Exception as e:
            self.log_error("리소스 모니터링 오류", e)

    def start_new_thread(self, target, name=None):
        """스레드 생성 및 관리"""
        try:
            with self.thread_lock:
                # 죽은 스레드 정리
                self.active_threads = {t for t in self.active_threads if t.is_alive()}
                
                if len(self.active_threads) > 50:  # 스레드 수 제한
                    self.log_error("스레드 수 초과", additional_info={
                        "active_threads": len(self.active_threads)
                    })
                    return None
                    
                thread = threading.Thread(target=target, name=name)
                thread.daemon = True  # 메인 프로세스 종료시 함께 종료
                thread.start()
                self.active_threads.add(thread)
                return thread
                
        except Exception as e:
            self.log_error("스레드 생성 오류", e)
            return None

    def check_dependencies(self):
        try:
            # 라이브러리 버전 체크
            import pkg_resources
            required = {
                'pyshark': '0.4.5',  # 최소 요구 버전
                'PySide6': '6.0.0',
                'psutil': '5.8.0',
                'pymongo': '3.12.0'
            }
            
            for package, min_version in required.items():
                version = pkg_resources.get_distribution(package).version
                self.log_error(f"라이브러리 버전 체크", additional_info={
                    "package": package,
                    "current_version": version,
                    "required_version": min_version
                })
                
            # Wireshark 버전 체크
            try:
                import subprocess
                result = subprocess.run(['tshark', '--version'], capture_output=True, text=True)
                self.log_error("Wireshark 버전", additional_info={
                    "version_info": result.stdout.split('\n')[0]
                })
            except Exception as e:
                self.log_error("Wireshark 버전 체크 실패", e)
            
        except Exception as e:
            self.log_error("의존성 체크 중 오류", e)

    def check_system_limits(self):
        try:
            import resource
            # 파일 디스크립터 제한 확인
            soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
            self.log_error("시스템 리소스 제한", additional_info={
                "file_descriptors": {
                    "soft_limit": soft,
                    "hard_limit": hard
                },
                "max_processes": len(psutil.Process().children(recursive=True)),
                "python_bits": platform.architecture()[0],
                "python_version": sys.version
            })
            
            # 메모리 제한 확인
            if hasattr(resource, 'RLIMIT_AS'):
                mem_soft, mem_hard = resource.getrlimit(resource.RLIMIT_AS)
                self.log_error("메모리 제한", additional_info={
                    "memory_limit": {
                        "soft_limit": mem_soft,
                        "hard_limit": mem_hard
                    }
                })
                
        except Exception as e:
            self.log_error("시스템 제한 체크 중 오류", e)

    def setup_crash_handler(self):
        try:
            import faulthandler
            faulthandler.enable()
            crash_log = open('crash.log', 'w')
            faulthandler.enable(file=crash_log)
            
            # Windows 전용 예외 핸들러
            if os.name == 'nt':
                import ctypes
                def windows_exception_handler(ex_type, value, tb):
                    if ex_type is ctypes.c_int:
                        self.log_error("심각한 시스템 오류", additional_info={
                            "error_code": value,
                            "traceback": traceback.format_tb(tb)
                        })
                sys.excepthook = windows_exception_handler
                
        except Exception as e:
            self.log_error("크래시 핸들러 설정 실패", e)

class FlowLayout(QLayout):
    def __init__(self, parent=None, margin=0, spacing=-1):
        super().__init__(parent)
        self._items = []
        self.setContentsMargins(margin, margin, margin, margin)
        self.setSpacing(spacing)

    def addItem(self, item):
        self._items.append(item)

    def count(self):
        return len(self._items)

    def itemAt(self, index):
        if 0 <= index < len(self._items):
            return self._items[index]
        return None

    def takeAt(self, index):
        if 0 <= index < len(self._items):
            return self._items.pop(index)
        return None

    def expandingDirections(self):
        return Qt.Orientations()

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        height = self._doLayout(QRect(0, 0, width, 0), True)
        return height

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._doLayout(rect, False)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        margin = self.contentsMargins()
        size += QSize(2 * margin.top(), 2 * margin.bottom())
        return size

    def _doLayout(self, rect, testOnly):
        x = rect.x()
        y = rect.y()
        lineHeight = 0
        spacing = self.spacing()
        for item in self._items:
            widget = item.widget()
            spaceX = spacing
            spaceY = spacing
            nextX = x + item.sizeHint().width() + spaceX
            if nextX - spaceX > rect.right() and lineHeight > 0:
                x = rect.x()
                y = y + lineHeight + spaceY
                nextX = x + item.sizeHint().width() + spaceX
                lineHeight = 0
            if not testOnly:
                item.setGeometry(QRect(QPoint(x, y), item.sizeHint()))
            x = nextX
            lineHeight = max(lineHeight, item.sizeHint().height())
        return y + lineHeight - rect.y()

# RTPStreamManager 클래스 (기존 코드 기반)
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
                base_path = config.get('Recording', 'save_path', fallback='D:/PacketWaveRecord')
                
                today = datetime.datetime.now().strftime("%Y%m%d")
                time_str = datetime.datetime.now().strftime("%H%M%S")
                
                # 디렉토리 경로 생성 및 확인
                file_dir = os.path.join(base_path, today, phone_ip, time_str)
                if not os.path.exists(file_dir):
                    try:
                        os.makedirs(file_dir)
                    except Exception as e:
                        print(f"디렉토리 생성 실패: {e}")
                        return None
                        
                # 파일명 생성
                filename = f"{time_str}_{direction}_{call_info['from_number']}_{call_info['to_number']}_{today}.wav"
                filepath = os.path.join(file_dir, filename)
                
                try:
                    with wave.open(filepath, 'wb') as wav_file:
                        wav_file.setnchannels(1)
                        wav_file.setsampwidth(2)
                        wav_file.setframerate(8000)
                except Exception as e:
                    print(f"WAV 파일 초기화 실패: {e}")
                    return None
                    
                self.active_streams[stream_key] = {
                    'call_id': call_id,
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
        try:
            with self.stream_locks[stream_key]:
                stream_info = self.active_streams[stream_key]
                if not stream_info['saved']:
                    print(f"패킷 수신 - 시퀀스: {sequence}, 크기: {len(audio_data)} bytes")
                    if stream_info['sequence'] > 0:
                        expected_sequence = (stream_info['sequence'] + 1) % 65536
                        if sequence != expected_sequence:
                            print(f"시퀀스 불연속 감지: 예상={expected_sequence}, 실제={sequence}")
                    if sequence <= stream_info['sequence']:
                        print(f"중복 패킷 무시: 현재={stream_info['sequence']}, 수신={sequence}")
                        return
                    stream_info['audio_data'].extend(audio_data)
                    stream_info['sequence'] = sequence
                    stream_info['packet_count'] += 1
                    print(f"버퍼 상태 - 현재크기: {len(stream_info['audio_data'])}, 목표크기: {stream_info['current_buffer_size']}, 내선통화: {stream_info['is_internal_call']}")
                    if len(stream_info['audio_data']) >= stream_info['current_buffer_size']:
                        self._write_to_wav(stream_key, payload_type)
                        self._adjust_buffer_size(stream_info)
        except Exception as e:
            print(f"패킷 처리 중 오류: {e}")

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
            import traceback
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
                return dict(stream_info)
        except Exception as e:
            print(f"스트림 종료 중 오류: {e}")
            import traceback
            print(traceback.format_exc())
            return None

    def save_file_info(self, file_info):
        try:
            self.filesinfo.insert_one(file_info)
        except Exception as e:
            print(f"파일 정보 저장 실패: {e}")

if __name__ == "__main__":
    try:
        app = QApplication([])
        window = Dashboard()
        
        # 전역 예외 핸들러 설정
        def handle_exception(exc_type, exc_value, exc_traceback):
            window.log_error("치명적인 오류 발생", 
                error=exc_value, 
                additional_info={
                    "type": str(exc_type),
                    "traceback": "".join(traceback.format_tb(exc_traceback))
                }
            )
            print("치명적인 오류가 발생했습니다. voip_monitor.log를 확인하세요.")
            sys.exit(1)

        sys.excepthook = handle_exception
        
        # 메모리 모니터링
        def check_memory_usage():
            process = psutil.Process()
            memory_info = process.memory_info()
            window.log_error("메모리 사용량 체크", additional_info={
                "rss": f"{memory_info.rss / 1024 / 1024:.2f} MB",
                "vms": f"{memory_info.vms / 1024 / 1024:.2f} MB"
            })
            
        memory_timer = QTimer()
        memory_timer.timeout.connect(check_memory_usage)
        memory_timer.start(60000)  # 1분마다 체크
        
        window.show()
        app.exec()
        
    except Exception as e:
        with open('voip_monitor.log', 'a', encoding='utf-8') as f:
            f.write(f"\n=== 프로그램 시작 실패 ===\n")
            f.write(f"시간: {datetime.datetime.now()}\n")
            f.write(f"오류: {str(e)}\n")
            f.write(traceback.format_exc())
            f.write("\n")
        sys.exit(1)