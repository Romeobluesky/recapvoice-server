# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

PacketWave is a VoIP monitoring and recording system that captures voice packets using Wireshark/pyshark, processes audio streams, and provides a web-based interface for management. The system supports both development and production environments with automatic service management.

## Key Architecture Components

### Core Python Applications
- **dashboard.py** - Main PySide6 GUI application and system orchestrator
  - Single-instance QMainWindow with comprehensive VoIP monitoring
  - Multi-threaded packet capture using pyshark/Wireshark integration
  - Real-time SIP/RTP packet analysis and call state management
  - MongoDB integration for call logging and WebSocket server coordination
  - System resource monitoring and automatic service lifecycle management
- **voip_monitor.py** - VoIP packet monitoring using pyshark
- **packet_monitor.py** - Core packet analysis and stream management
- **rtpstream_manager.py** - RTP stream processing and audio extraction
- **wav_merger.py** - Audio file processing and merging functionality
- **websocketserver.py** - WebSocket server for real-time communication
- **callstate_machine.py** - VoIP call lifecycle state management

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

### Dashboard Configuration System
#### Working Directory Management
```python
def get_work_directory(self):
    """작업 디렉토리를 결정합니다 (개발/프로덕션 모드에 따라)"""
    # settings.ini 모드에 따라 경로 결정
    # production: %ProgramFiles(x86)%\Recap Voice
    # development: settings.ini의 dir_path
```

#### Initialization Sequence
1. **Single Instance Check**: QLocalServer를 통한 중복 실행 방지
2. **Working Directory Setup**: 모드별 경로 설정 및 권한 확인
3. **Directory Creation**: images/, logs/ 등 필수 디렉토리 생성
4. **Log System Init**: 날짜별 로그 파일 및 심볼릭 링크 생성
5. **Service Startup**: WebSocket, MongoDB, Network Interface 초기화

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

### Dashboard Core Architecture (dashboard.py)

#### Main Class Structure
- **Dashboard(QMainWindow)** - Central application controller
  - Singleton pattern with instance tracking (`_instance`)
  - Signal-based thread-safe communication system
  - Integrated system resource monitoring and cleanup

#### Thread Architecture
- **Main GUI Thread**: UI updates, user interactions, Qt event handling
- **Packet Capture Thread**: Continuous packet monitoring via pyshark
- **WebSocket Server Thread**: Asynchronous client communication
- **MongoDB Operations**: Database logging and call record management
- **Resource Monitor Thread**: System performance tracking

#### Core Signal System
```python
block_creation_signal = Signal(str)           # Extension block creation
block_update_signal = Signal(str, str, str)    # Extension status updates
extension_update_signal = Signal(str)          # Extension number updates
start_led_timer_signal = Signal(object)        # LED indicator control
sip_packet_signal = Signal(object)             # SIP packet analysis
safe_log_signal = Signal(str, str)             # Thread-safe logging
```

#### Packet Processing Pipeline
1. **Network Interface Detection**: Automatic discovery of active interfaces
2. **Packet Capture**: Multi-threaded pyshark capture with filtering
3. **SIP Analysis**: Real-time SIP message parsing and call identification
4. **RTP Handling**: Audio stream extraction and processing
5. **State Management**: Call lifecycle tracking via CallStateMachine
6. **Recording Control**: Coordinated audio capture and file management

#### Service Integration Architecture
- **MongoDB Client**: Call logging, metadata storage, query operations
- **WebSocket Server**: Real-time web client notifications
- **NestJS Integration**: Service lifecycle management and process monitoring
- **Wireshark/tshark**: Packet capture engine integration

### Call State Machine
- Uses **callstate_machine.py** for VoIP call lifecycle management
- States: IDLE, RINGING, CONNECTED, DISCONNECTED
- Integrates with RTP stream processing and recording triggers

### WebSocket Communication
- Real-time updates between Python backend and web frontend
- Call status, recording progress, file availability
- Managed through **websocketserver.py** with async/await patterns

## Build and Deployment

### PyInstaller Configuration
- **build.ps1** - PowerShell build script with full dependency management
- Includes Qt multimedia DLLs, models folder handling
- Production settings modification during build

### Dependencies
- External tools must be installed: Wireshark, Npcap, FFmpeg, Node.js
- Python virtual environment recommended (myenv/)
- Windows-specific implementation using pywin32

## Dashboard Application Entry Points

### Main Function Architecture
```python
def main():
    """메인 애플리케이션 진입점"""
    # QApplication 초기화 및 명령줄 인수 처리
    # 단일 인스턴스 확인 (QLocalSocket)
    # Dashboard 인스턴스 생성 및 GUI 실행
```

### Key Initialization Methods
- `__init__()`: 핵심 시스템 초기화 및 설정 로드
- `initialize_main_window()`: GUI 컴포넌트 및 레이아웃 설정
- `_init_ui()`: 사용자 인터페이스 구성 요소 생성
- `setup_single_instance()`: 애플리케이션 중복 실행 방지

### Critical System Methods
- `start_packet_capture()`: 네트워크 패킷 캡처 시작
- `analyze_sip_packet()`: SIP 메시지 분석 및 상태 관리
- `handle_rtp_packet()`: RTP 오디오 스트림 처리
- `_save_to_mongodb()`: 통화 기록 데이터베이스 저장

## Testing Notes

- No automated test framework for Python components
- NestJS includes Jest testing setup
- Manual testing through GUI and web interface
- Log files in logs/ directory for debugging
- Real-time debugging through SIP console log interface within dashboard

## System Requirements & Dependencies

### Runtime Dependencies
- **Python 3.8+**: PySide6, pyshark, pymongo, psutil
- **Wireshark/tshark**: Packet capture engine (system installation)
- **MongoDB**: Database server (embedded instance)
- **FFmpeg**: Audio processing (system dependency)
- **Node.js 16+**: NestJS web client runtime

### Windows-Specific Components
- **pywin32**: Windows API integration for process management
- **Npcap**: Network packet capture driver
- **Qt Multimedia**: Audio handling DLLs for PySide6

## 프로그램에서 현재 제외 된 폴더
- @models/
- @modules/