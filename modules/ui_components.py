# -*- coding: utf-8 -*-
"""
UI 컴포넌트 모듈
Dashboard 클래스에서 UI 생성 관련 기능을 분리
"""

import configparser
from PySide6.QtCore import *
from PySide6.QtGui import *
from PySide6.QtWidgets import *


def resource_path(relative_path):
    """리소스 파일의 절대 경로를 반환"""
    import os
    import sys
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.abspath('.'), relative_path)


class UIComponents:
    """UI 컴포넌트 생성 관련 유틸리티 함수들"""
    
    def __init__(self, dashboard_instance):
        self.dashboard = dashboard_instance
    
    def create_header(self):
        """헤더 위젯 생성"""
        header = QWidget()
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(10, 5, 10, 5)
        
        phone_section = QWidget()
        phone_layout = QHBoxLayout(phone_section)
        phone_layout.setAlignment(Qt.AlignLeft)
        phone_layout.setContentsMargins(0, 0, 0, 0)
        
        phone_text = QLabel("대표번호 | ")
        self.dashboard.phone_number = QLabel()
        
        config = configparser.ConfigParser()
        config.read('settings.ini', encoding='utf-8')
        self.dashboard.phone_number.setText(config.get('Extension', 'rep_number', fallback=''))
        
        phone_layout.addWidget(phone_text)
        phone_layout.addWidget(self.dashboard.phone_number)
        
        license_section = QWidget()
        license_layout = QHBoxLayout(license_section)
        license_layout.setAlignment(Qt.AlignRight)
        license_layout.setContentsMargins(0, 0, 0, 0)
        
        license_text = QLabel("라이선스 NO. | ")
        self.dashboard.license_number = QLabel()
        self.dashboard.license_number.setText(config.get('Extension', 'license_no', fallback=''))
        
        license_layout.addWidget(license_text)
        license_layout.addWidget(self.dashboard.license_number)

        header_layout.addWidget(phone_section, 1)
        header_layout.addWidget(license_section, 1)
        return header

    def create_sidebar(self):
        """사이드바 위젯 생성"""
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

        # SIP 내선번호 표시 박스 추가
        print("=== Extension box를 사이드바에 추가 중 ===")
        extension_box = self.create_extension_box()
        layout.addWidget(extension_box)
        print(f"Extension box가 사이드바에 추가됨: {extension_box}")
        print(f"사이드바 레이아웃 내 위젯 개수: {layout.count()}")

        menu_container = QWidget()
        menu_layout = QVBoxLayout(menu_container)
        menu_layout.setContentsMargins(0, 0, 0, 0)
        menu_layout.setSpacing(5)
        menu_layout.addStretch()
        layout.addWidget(menu_container)
        return sidebar

    def create_menu_button(self, text, icon_path):
        """메뉴 버튼 생성"""
        btn = QPushButton()
        btn.setObjectName("menu_button")
        btn.setFixedHeight(50)
        btn.setCursor(Qt.PointingHandCursor)
        
        layout = QHBoxLayout(btn)
        layout.setContentsMargins(15, 0, 15, 0)
        layout.setSpacing(0)

        # 아이콘 추가
        if icon_path:
            icon = QLabel()
            icon_pixmap = QPixmap(resource_path(icon_path))
            if not icon_pixmap.isNull():
                scaled_icon = icon_pixmap.scaled(20, 20, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                icon.setPixmap(scaled_icon)
            layout.addWidget(icon)

        # 텍스트 추가
        text_label = QLabel(text)
        text_label.setStyleSheet("color: white; font-weight: bold;")
        layout.addWidget(text_label)
        layout.addStretch()

        return btn

    def create_extension_box(self):
        """SIP 내선번호 표시 박스 생성"""
        # 메인 컨테이너 (둥근 박스)
        extension_container = QWidget()
        extension_container.setObjectName("extension_container")
        extension_container.setFixedSize(200, 700)
        extension_container.setStyleSheet("""
            QWidget#extension_container {
                background-color: #48c9b0;
                border-radius: 5px;
                margin: 10px;
            }
        """)

        main_layout = QVBoxLayout(extension_container)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(5)

        # 헤더 영역 (타이틀만)
        title_label = QLabel("내선번호")
        title_label.setAlignment(Qt.AlignCenter)
        title_label.setFixedHeight(28)
        title_label.setObjectName("extension_title")
        title_label.setStyleSheet("""
            QLabel#extension_title {
                background-color: transparent;
                border: none;
                color: white;
                font-size: 12px;
                font-weight: bold;
                padding-top: 5px;
            }
        """)
        main_layout.addWidget(title_label)

        # 스크롤 영역
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll_area.setStyleSheet("""
            QScrollArea {
                border: none;
                background-color: transparent;
            }
            QScrollBar:vertical {
                background-color: rgba(255, 255, 255, 0.1);
                width: 8px;
                border-radius: 4px;
            }
            QScrollBar::handle:vertical {
                background-color: rgba(255, 255, 255, 0.3);
                border-radius: 4px;
                min-height: 20px;
            }
            QScrollBar::handle:vertical:hover {
                background-color: rgba(255, 255, 255, 0.5);
            }
        """)

        # 내선번호 목록 컨테이너
        extension_content = QWidget()
        self.dashboard.extension_list_layout = QVBoxLayout(extension_content)
        self.dashboard.extension_list_layout.setContentsMargins(5, 5, 5, 5)
        self.dashboard.extension_list_layout.setSpacing(3)
        self.dashboard.extension_list_layout.addStretch()

        scroll_area.setWidget(extension_content)
        main_layout.addWidget(scroll_area)

        print(f"=== Extension box 생성 완료 ===")
        print(f"Extension container: {extension_container}")
        print(f"Extension layout: {self.dashboard.extension_list_layout}")

        return extension_container

    def create_log_list(self):
        """로그 리스트 테이블 생성"""
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

    def create_sip_console_log(self):
        """SIP 콘솔 로그 레이어 생성"""
        group = QGroupBox("SIP CONSOLE LOG")
        group.setFixedHeight(300)  # 높이 300px로 고정
        
        layout = QVBoxLayout(group)
        layout.setContentsMargins(15, 15, 15, 15)

        # 텍스트 에디터 (읽기 전용)
        console_text = QTextEdit()
        console_text.setObjectName("sip_console_text")
        console_text.setReadOnly(True)
        console_text.setStyleSheet("""
            QTextEdit {
                background-color: #1E1E1E;
                color: #00FF00;
                font-family: 'Consolas', 'Courier New', monospace;
                font-size: 11px;
                border: 1px solid #444444;
                padding: 5px;
            }
        """)

        # 툴바 추가
        toolbar_layout = QHBoxLayout()

        # 클리어 버튼
        clear_btn = QPushButton("Clear")
        clear_btn.setFixedSize(60, 25)
        clear_btn.setStyleSheet("""
            QPushButton {
                background-color: #444444;
                color: white;
                border: 1px solid #666666;
                border-radius: 3px;
                font-size: 9px;
            }
            QPushButton:hover {
                background-color: #555555;
            }
            QPushButton:pressed {
                background-color: #333333;
            }
        """)
        clear_btn.clicked.connect(lambda: console_text.clear())

        # 자동 스크롤 체크박스
        auto_scroll_cb = QCheckBox("Auto Scroll")
        auto_scroll_cb.setChecked(True)
        auto_scroll_cb.setObjectName("auto_scroll_checkbox")
        auto_scroll_cb.setStyleSheet("""
            QCheckBox {
                color: white;
                font-size: 9px;
            }
            QCheckBox::indicator {
                width: 13px;
                height: 13px;
            }
            QCheckBox::indicator:unchecked {
                background-color: #444444;
                border: 1px solid #666666;
            }
            QCheckBox::indicator:checked {
                background-color: #48c9b0;
                border: 1px solid #48c9b0;
            }
        """)

        toolbar_layout.addWidget(clear_btn)
        toolbar_layout.addStretch()
        toolbar_layout.addWidget(auto_scroll_cb)

        layout.addLayout(toolbar_layout)
        layout.addWidget(console_text)

        # Dashboard에 참조 저장
        self.dashboard.sip_console_text = console_text
        self.dashboard.auto_scroll_checkbox = auto_scroll_cb

        return group