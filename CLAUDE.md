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

## 프로그램에서 현재 제외 된 폴더
- models
- modules