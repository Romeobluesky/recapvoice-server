# MongoDB 백업/복원 가이드
PacketWave 시스템 MongoDB 데이터 백업 및 복원 방법

## 📋 개요

이 가이드는 PacketWave VoIP 모니터링 시스템의 MongoDB 데이터를 안전하게 백업하고 복원하는 방법을 설명합니다.

## 🔧 백업 도구

### 1. 자동 백업 스크립트
- `backup_mongodb.bat` - Windows 배치 파일
- `mongodb_backup.py` - Python 백업 스크립트

### 2. 복원 도구
- `restore_mongodb.py` - 통합 복원 도구
- `backup/mongodb_backup_*/restore.py` - 개별 백업 복원 스크립트

## 💾 백업 수행 방법

### 방법 1: 배치 파일 사용 (권장)
```batch
# Windows 명령 프롬프트에서
backup_mongodb.bat
```

### 방법 2: Python 스크립트 직접 실행
```bash
python mongodb_backup.py
```

## 📊 백업되는 데이터

### 포함 데이터베이스
- `packetwave` - 메인 애플리케이션 데이터베이스

### 포함 컬렉션
- `members` - 사용자 계정 정보 (2개 문서)
- `message_set` - 메시지 설정
- `internalnumber` - 내선번호 관리  
- `filesinfo` - 파일 정보
- `guest` - 게스트 정보
- `callconsult` - 통화 상담 정보
- `tags` - 태그 정보

### 제외 데이터베이스
- `admin` - MongoDB 관리 데이터베이스
- `config` - MongoDB 구성 데이터베이스
- `local` - MongoDB 로컬 데이터베이스

## 🔄 복원 방법

### 방법 1: 통합 복원 도구 사용 (권장)
```bash
python restore_mongodb.py
```
- 사용 가능한 백업 목록 표시
- 대화형 백업 선택
- 안전한 복원 프로세스

### 방법 2: 개별 백업 복원
```bash
# 특정 백업 폴더로 이동 후
python backup/mongodb_backup_20250822_155428/restore.py
```

## 📁 백업 파일 구조

```
backup/
└── mongodb_backup_YYYYMMDD_HHMMSS/
    ├── backup_summary.json     # 전체 백업 정보
    ├── restore.py             # 개별 복원 스크립트
    └── packetwave/            # 데이터베이스 폴더
        ├── backup_info.json   # 데이터베이스 백업 정보
        ├── members.bson       # 사용자 데이터 (BSON 형식)
        ├── members_indexes.json # 인덱스 정보
        └── [기타 컬렉션 파일들...]
```

## ⚠️ 주의사항

### 백업 시 주의사항
1. **MongoDB 서버 실행 확인**: 백업 전 MongoDB 서비스가 실행 중인지 확인
2. **충분한 저장 공간**: 백업 파일 저장을 위한 디스크 공간 확보
3. **정기 백업**: 데이터 손실 방지를 위한 정기적인 백업 수행

### 복원 시 주의사항
1. **기존 데이터 확인**: 복원 시 기존 데이터 덮어쓰기 여부 선택 가능
2. **MongoDB 서버 상태**: 복원 전 MongoDB 서버 정상 작동 확인
3. **백업 호환성**: 동일한 MongoDB 버전에서 생성된 백업 사용 권장

## 🔍 백업 검증

### 백업 성공 확인
```bash
# 백업 정보 조회
cat backup/mongodb_backup_YYYYMMDD_HHMMSS/backup_summary.json

# 파일 크기 확인
dir backup/mongodb_backup_YYYYMMDD_HHMMSS/packetwave/
```

### 복원 검증
```python
import pymongo
client = pymongo.MongoClient('mongodb://localhost:27017/')
db = client['packetwave']
print("복원된 컬렉션:", db.list_collection_names())
print("members 문서 수:", db.members.count_documents({}))
```

## 📞 지원

문제 발생 시:
1. MongoDB 서버 로그 확인: `mongodb/logs/mongod.log`
2. 백업/복원 스크립트 오류 메시지 확인
3. 필요시 기술 지원팀 문의

## 🔄 자동화

### 정기 백업 설정 (선택사항)
Windows 작업 스케줄러를 이용한 자동 백업:
1. 작업 스케줄러 실행
2. 기본 작업 만들기
3. 프로그램: `D:\Work_state\packet_wave\backup_mongodb.bat`
4. 트리거: 매일/매주 설정

---
**마지막 업데이트**: 2025-08-22
**MongoDB 버전**: 8.0.3
**시스템**: PacketWave VoIP 모니터링 시스템