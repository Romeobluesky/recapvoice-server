#!/usr/bin/env python3
"""
MongoDB 백업 복원 도구
PacketWave 시스템용 통합 복원 스크립트
"""

import os
import json
import pymongo
import bson
import sys
from pathlib import Path
from datetime import datetime

def list_backups():
    """백업 목록 조회"""
    backup_root = Path('backup')
    if not backup_root.exists():
        print("[ERROR] backup 디렉토리가 존재하지 않습니다.")
        return []
    
    backups = []
    for item in backup_root.iterdir():
        if item.is_dir() and item.name.startswith('mongodb_backup_'):
            summary_file = item / 'backup_summary.json'
            if summary_file.exists():
                try:
                    with open(summary_file, 'r', encoding='utf-8') as f:
                        summary = json.load(f)
                    backups.append({
                        'path': item,
                        'name': item.name,
                        'timestamp': summary.get('backup_timestamp', ''),
                        'databases': summary.get('total_databases', 0),
                        'collections': summary.get('total_collections', 0),
                        'documents': summary.get('total_documents', 0)
                    })
                except Exception as e:
                    print(f"[WARNING] {item.name} 정보를 읽을 수 없습니다: {e}")
    
    # 최신순으로 정렬
    backups.sort(key=lambda x: x['timestamp'], reverse=True)
    return backups

def restore_backup(backup_path):
    """특정 백업 복원"""
    try:
        print(f"[START] 백업 복원 시작: {backup_path}")
        
        # MongoDB 연결
        client = pymongo.MongoClient('mongodb://localhost:27017/', serverSelectionTimeoutMS=5000)
        client.server_info()
        print("[SUCCESS] MongoDB 서버 연결 성공")
        
        # 백업 정보 읽기
        summary_file = backup_path / 'backup_summary.json'
        with open(summary_file, 'r', encoding='utf-8') as f:
            summary = json.load(f)
        
        print(f"[INFO] 복원할 데이터:")
        print(f"  - 데이터베이스: {summary['total_databases']}개")
        print(f"  - 컬렉션: {summary['total_collections']}개")
        print(f"  - 문서: {summary['total_documents']}개")
        
        # 사용자 확인
        if input("\n계속 진행하시겠습니까? (y/N): ").lower() != 'y':
            print("[CANCEL] 복원이 취소되었습니다.")
            return False
        
        # 각 데이터베이스 복원
        for db_name, db_info in summary['databases'].items():
            print(f"\n[RESTORE] 데이터베이스 '{db_name}' 복원 중...")
            
            db = client[db_name]
            db_backup_dir = backup_path / db_name
            
            for collection_name, col_info in db_info['collections'].items():
                bson_file = db_backup_dir / f"{collection_name}.bson"
                
                if bson_file.exists() and col_info['document_count'] > 0:
                    print(f"  [RESTORE] 컬렉션 '{collection_name}' 복원 중...")
                    
                    collection = db[collection_name]
                    
                    # 기존 데이터 확인
                    existing_count = collection.count_documents({})
                    if existing_count > 0:
                        choice = input(f"    기존 데이터 {existing_count}개가 있습니다. 삭제하고 복원하시겠습니까? (y/N): ")
                        if choice.lower() == 'y':
                            collection.drop()
                            print(f"    [INFO] 기존 컬렉션 삭제됨")
                        else:
                            print(f"    [SKIP] '{collection_name}' 건너뜀")
                            continue
                    
                    # BSON 파일 읽기
                    with open(bson_file, 'rb') as f:
                        data = f.read()
                    
                    docs = []
                    offset = 0
                    while offset < len(data):
                        doc_size = int.from_bytes(data[offset:offset+4], 'little')
                        doc_bson = data[offset:offset+doc_size]
                        docs.append(bson.BSON(doc_bson).decode())
                        offset += doc_size
                    
                    if docs:
                        collection.insert_many(docs)
                        print(f"    [SUCCESS] {len(docs)}개 문서 복원 완료")
                else:
                    print(f"  [SKIP] '{collection_name}' - 백업 데이터 없음")
        
        client.close()
        print(f"\n[COMPLETE] 백업 복원 완료!")
        return True
        
    except Exception as e:
        print(f"[ERROR] 복원 실패: {e}")
        return False

def main():
    """메인 함수"""
    print("================================")
    print("MongoDB 백업 복원 도구")
    print("PacketWave 시스템")
    print("================================\n")
    
    # 백업 목록 조회
    backups = list_backups()
    
    if not backups:
        print("[ERROR] 사용 가능한 백업이 없습니다.")
        return
    
    # 백업 목록 출력
    print("[INFO] 사용 가능한 백업:")
    for i, backup in enumerate(backups, 1):
        timestamp_str = backup['timestamp'][:19].replace('T', ' ')
        print(f"  {i}. {backup['name']}")
        print(f"     시간: {timestamp_str}")
        print(f"     데이터: DB {backup['databases']}개, 컬렉션 {backup['collections']}개, 문서 {backup['documents']}개")
        print()
    
    # 백업 선택
    try:
        choice = int(input(f"복원할 백업을 선택하세요 (1-{len(backups)}): "))
        if 1 <= choice <= len(backups):
            selected_backup = backups[choice - 1]
            success = restore_backup(selected_backup['path'])
            
            if success:
                print("\n[SUCCESS] 복원이 완료되었습니다!")
            else:
                print("\n[FAILED] 복원에 실패했습니다.")
        else:
            print("[ERROR] 잘못된 선택입니다.")
    except ValueError:
        print("[ERROR] 숫자를 입력해주세요.")
    except KeyboardInterrupt:
        print("\n[CANCEL] 복원이 취소되었습니다.")

if __name__ == "__main__":
    main()