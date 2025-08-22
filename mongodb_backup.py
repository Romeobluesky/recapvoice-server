#!/usr/bin/env python3
"""
MongoDB 전체 백업 스크립트
PacketWave 시스템용 MongoDB 백업 도구
"""

import os
import json
import pymongo
from datetime import datetime
from pathlib import Path
import bson
import gridfs

def create_backup_directory():
    """백업 디렉토리 생성"""
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_dir = Path(f'backup/mongodb_backup_{timestamp}')
    backup_dir.mkdir(parents=True, exist_ok=True)
    return backup_dir

def backup_database(client, db_name, backup_dir):
    """특정 데이터베이스 백업"""
    print(f"[BACKUP] 데이터베이스 '{db_name}' 백업 시작...")
    
    db = client[db_name]
    db_backup_dir = backup_dir / db_name
    db_backup_dir.mkdir(exist_ok=True)
    
    # 컬렉션 목록 가져오기
    collections = db.list_collection_names()
    
    backup_info = {
        'database': db_name,
        'timestamp': datetime.now().isoformat(),
        'collections': {},
        'total_documents': 0
    }
    
    for collection_name in collections:
        print(f"  [COLLECTION] '{collection_name}' 백업 중...")
        collection = db[collection_name]
        
        # 컬렉션 데이터를 BSON으로 백업
        collection_file = db_backup_dir / f"{collection_name}.bson"
        documents = list(collection.find())
        
        if documents:
            with open(collection_file, 'wb') as f:
                for doc in documents:
                    f.write(bson.BSON.encode(doc))
        
        # 인덱스 정보 백업
        indexes = list(collection.list_indexes())
        index_file = db_backup_dir / f"{collection_name}_indexes.json"
        with open(index_file, 'w', encoding='utf-8') as f:
            json.dump(indexes, f, indent=2, default=str)
        
        # 백업 정보 업데이트
        doc_count = len(documents)
        backup_info['collections'][collection_name] = {
            'document_count': doc_count,
            'indexes': len(indexes)
        }
        backup_info['total_documents'] += doc_count
        
        print(f"    [SUCCESS] {doc_count}개 문서 백업 완료")
    
    # 백업 정보 저장
    info_file = db_backup_dir / 'backup_info.json'
    with open(info_file, 'w', encoding='utf-8') as f:
        json.dump(backup_info, f, indent=2, ensure_ascii=False)
    
    return backup_info

def main():
    """메인 백업 함수"""
    try:
        print("[START] MongoDB 전체 백업 시작...")
        
        # MongoDB 연결
        client = pymongo.MongoClient('mongodb://localhost:27017/', serverSelectionTimeoutMS=5000)
        
        # 서버 연결 테스트
        client.server_info()
        print("[SUCCESS] MongoDB 서버 연결 성공")
        
        # 백업 디렉토리 생성
        backup_dir = create_backup_directory()
        print(f"[INFO] 백업 디렉토리: {backup_dir}")
        
        # 데이터베이스 목록 가져오기
        databases = client.list_database_names()
        print(f"[INFO] 발견된 데이터베이스: {databases}")
        
        # 시스템 데이터베이스 제외하고 백업
        user_databases = [db for db in databases if db not in ['admin', 'config', 'local']]
        
        total_backup_info = {
            'backup_timestamp': datetime.now().isoformat(),
            'databases': {},
            'total_databases': len(user_databases),
            'total_collections': 0,
            'total_documents': 0
        }
        
        # 각 데이터베이스 백업
        for db_name in user_databases:
            backup_info = backup_database(client, db_name, backup_dir)
            total_backup_info['databases'][db_name] = backup_info
            total_backup_info['total_collections'] += len(backup_info['collections'])
            total_backup_info['total_documents'] += backup_info['total_documents']
        
        # 전체 백업 정보 저장
        summary_file = backup_dir / 'backup_summary.json'
        with open(summary_file, 'w', encoding='utf-8') as f:
            json.dump(total_backup_info, f, indent=2, ensure_ascii=False)
        
        # 백업 완료 스크립트 생성
        restore_script = backup_dir / 'restore.py'
        with open(restore_script, 'w', encoding='utf-8') as f:
            f.write(f'''#!/usr/bin/env python3
"""
MongoDB 백업 복원 스크립트
백업 날짜: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""

import os
import json
import pymongo
import bson
from pathlib import Path

def restore_backup():
    backup_dir = Path(__file__).parent
    client = pymongo.MongoClient('mongodb://localhost:27017/')
    
    with open(backup_dir / 'backup_summary.json', 'r', encoding='utf-8') as f:
        summary = json.load(f)
    
    for db_name in summary['databases']:
        print(f"복원 중: {{db_name}}")
        db = client[db_name]
        db_dir = backup_dir / db_name
        
        for collection_name in summary['databases'][db_name]['collections']:
            bson_file = db_dir / f"{{collection_name}}.bson"
            if bson_file.exists():
                collection = db[collection_name]
                collection.drop()  # 기존 컬렉션 삭제
                
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
                    print(f"  복원됨: {{collection_name}} ({{len(docs)}}개 문서)")

if __name__ == "__main__":
    restore_backup()
    print("백업 복원 완료!")
''')
        
        client.close()
        
        print("\n[COMPLETE] 백업 완료!")
        print(f"[STATS] 백업 통계:")
        print(f"  - 데이터베이스: {total_backup_info['total_databases']}개")
        print(f"  - 컬렉션: {total_backup_info['total_collections']}개") 
        print(f"  - 문서: {total_backup_info['total_documents']}개")
        print(f"[PATH] 백업 위치: {backup_dir.absolute()}")
        print(f"[RESTORE] 복원 명령: python {restore_script}")
        
        return True
        
    except Exception as e:
        print(f"[ERROR] 백업 실패: {e}")
        return False

if __name__ == "__main__":
    success = main()
    if success:
        print("[SUCCESS] 백업이 성공적으로 완료되었습니다!")
    else:
        print("[FAILED] 백업 중 오류가 발생했습니다.")