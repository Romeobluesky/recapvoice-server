# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

PacketWave is a VoIP monitoring and recording system that captures voice packets using Wireshark/pyshark, processes audio streams, and provides a web-based interface for management. The system supports both development and production environments with automatic service management.

## Key Architecture Components

### Core Python Applications
- **dashboard.py** - Main PySide6 GUI application and entry point
- **voip_monitor.py** - VoIP packet monitoring using pyshark
- **packet_monitor.py** - Core packet analysis and stream management
- **rtpstream_manager.py** - RTP stream processing and audio extraction
- **wav_merger.py** - Audio file processing and merging functionality
- **websocketserver.py** - WebSocket server for real-time communication

### NestJS Web Client
- **packetwave_client/** - Full-stack Node.js/NestJS application
  - TypeScript-based with MongoDB integration
  - EJS templating for web interface
  - WebSocket support for real-time updates
  - Express session management

### External Dependencies
- **MongoDB** - Database for call records and metadata (embedded in mongodb/)
- **Nginx** - Web server and reverse proxy (embedded in nginx/)
- **FFmpeg** - Audio processing and conversion
- **Wireshark/tshark** - Packet capture and analysis

## Common Development Commands

### Python Application
```bash
# Install Python dependencies
pip install -r requirements.txt

# Run main application
python dashboard.py

# Build executable (Windows)
.\build.ps1
# or
pyinstaller_command.bat
```

### NestJS Client
```bash
cd packetwave_client

# Install dependencies
npm install

# Development mode
npm run start:dev

# Production build
npm run build
npm start

# Testing
npm test
npm run test:e2e

# Linting
npm run lint
```

### Service Management
```bash
# Start all services (Nginx, MongoDB, NestJS)
start.bat

# Stop services
cd packetwave_client
npm run stop
```

## Configuration Management

### Environment Settings
- **settings.ini** - Main configuration file
  - `mode = development|production` - Environment mode
  - Storage paths, database settings, network interfaces
  - Wireshark and audio processing parameters

### Development vs Production
- **Development**: Uses local paths from settings.ini `dir_path`
- **Production**: Uses `%ProgramFiles(x86)%\Recap Voice`

## File Structure Patterns

### Audio Recording Storage
```
{base_path}/PacketWaveRecord/
├── {server_ip}/
│   └── {date}/
│       └── {from_number}_{to_number}/
│           ├── {time}_IN_{from}_{to}_{date}_{call_hash}.wav
│           ├── {time}_OUT_{from}_{to}_{date}_{call_hash}.wav
│           └── {time}_MERGE_{from}_{to}_{date}.wav
```

### Application Structure
- **Root**: Python GUI application and services
- **packetwave_client/**: NestJS web application
- **mongodb/**: Embedded MongoDB instance
- **nginx/**: Embedded web server
- **models/**: AI models for speech processing

## Key State Management

### Call State Machine
- Uses **callstate_machine.py** for VoIP call lifecycle management
- States: IDLE, RINGING, CONNECTED, DISCONNECTED
- Integrates with RTP stream processing

### WebSocket Communication
- Real-time updates between Python backend and web frontend
- Call status, recording progress, file availability
- Managed through **websocketserver.py**

## Build and Deployment

### PyInstaller Configuration
- **build.ps1** - PowerShell build script with full dependency management
- Includes Qt multimedia DLLs, models folder handling
- Production settings modification during build

### Dependencies
- External tools must be installed: Wireshark, Npcap, FFmpeg, Node.js
- Python virtual environment recommended (myenv/)
- Windows-specific implementation using pywin32

## Testing Notes

- No automated test framework for Python components
- NestJS includes Jest testing setup
- Manual testing through GUI and web interface
- Log files in logs/ directory for debugging

## 분리 대상 제안
● 이제 분리 방안을 제시하겠습니다.

  📊 dashboard.py 분석 결과

  현재 상태:

  - 총 라인 수: 3,344줄
  - 총 함수/메서드: 101개
  - 파일 크기: 매우 큰 단일 파일

  ---
  🔧 리팩토링 분리 방안

  1. SIP 관련 모듈 (sip_handler.py)

  # 분리 대상 메서드들:
  - analyze_sip_packet()
  - _handle_register_request()
  - _handle_sip_response()
  - _handle_refer_request()
  - handle_sip_response()
  - extract_number()
  - is_extension()  # 유틸리티 함수

  2. 내선번호 관리 모듈 (extension_manager.py)

  # 분리 대상 메서드들:
  - add_extension()
  - refresh_extension_list_with_register()
  - update_extension_in_main_thread()
  - update_extension_display()
  - get_extension_from_call()
  - toggle_led_color()
  - cleanup_led_timers()

  3. 패킷 처리 모듈 (packet_processor.py)

  # 분리 대상 메서드들:
  - start_packet_capture()
  - capture_packets()
  - handle_rtp_packet()
  - is_rtp_packet()
  - determine_stream_direction()
  - get_call_id_from_rtp()
  - update_packet_status()

  4. 로깅 모듈 (logging_utils.py)

  # 분리 대상 메서드들:
  - log_error()
  - log_to_sip_console()
  - init_sip_console_welcome()
  - initialize_log_file()

  5. UI 컴포넌트 모듈 (ui_components.py)

  # 분리 대상 메서드들:
  - _create_extension_box()
  - _create_sip_console_log()
  - _create_log_list()
  - _create_header()
  - _create_sidebar()
  - _create_menu_button()

  6. 데이터베이스 모듈 (database_handler.py)

  # 분리 대상 메서드들:
  - _save_to_mongodb()
  - retry_mongodb_connection()
  - (MongoDB 관련 초기화 코드)

  ---
  📁 제안하는 폴더 구조

  D:\Work_state\packet_wave\
  ├── dashboard.py           # 메인 Dashboard 클래스 (축소됨)
  ├── modules/
  │   ├── __init__.py
  │   ├── sip_handler.py     # SIP 패킷 처리
  │   ├── extension_manager.py   # 내선번호 관리
  │   ├── packet_processor.py    # 패킷 캡처/처리
  │   ├── logging_utils.py       # 로깅 기능
  │   ├── ui_components.py       # UI 컴포넌트
  │   └── database_handler.py    # DB 처리
  └── utils/
      ├── __init__.py
      └── helpers.py         # 유틸리티 함수들

  ---
  ⚡ 예상 효과

  - dashboard.py: 3,344줄 → 약 1,500~2,000줄로 축소
  - 유지보수성: 각 모듈별 독립 관리
  - 가독성: 기능별 명확한 분리
  - 재사용성: 다른 프로젝트에서도 모듈 재사용 가능

  이 중에서 어떤 모듈부터 분리해보시겠어요?
