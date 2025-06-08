#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MongoDB 연결 테스트 스크립트
클라이언트 PC에서 MongoDB 서버에 연결할 수 있는지 확인
"""

import configparser
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError

def load_config():
    """설정 파일 로드"""
    config = configparser.ConfigParser()
    config.read('settings.ini', encoding='utf-8')
    return config

def test_mongodb_connection():
    """MongoDB 연결 테스트"""
    try:
        # 설정 읽기
        config = load_config()
        mongo_host = config.get('MongoDB', 'host', fallback='localhost')
        mongo_port = config.getint('MongoDB', 'port', fallback=27017)
        mongo_database = config.get('MongoDB', 'database', fallback='packetwave')
        mongo_username = config.get('MongoDB', 'username', fallback='')
        mongo_password = config.get('MongoDB', 'password', fallback='')
        
        # MongoDB 연결 문자열 생성
        if mongo_username and mongo_password:
            mongo_uri = f"mongodb://{mongo_username}:{mongo_password}@{mongo_host}:{mongo_port}/"
        else:
            mongo_uri = f"mongodb://{mongo_host}:{mongo_port}/"
        
        print(f"MongoDB 연결 시도: {mongo_uri}")
        
        # 연결 시도 (타임아웃 5초)
        client = MongoClient(mongo_uri, serverSelectionTimeoutMS=5000)
        
        # 연결 테스트
        client.admin.command('ping')
        print("✅ MongoDB 연결 성공!")
        
        # 데이터베이스 접근 테스트
        db = client[mongo_database]
        collections = db.list_collection_names()
        print(f"📁 사용 가능한 컬렉션: {collections}")
        
        # 각 컬렉션의 문서 수 확인
        for collection_name in ['members', 'filesinfo', 'internalnumber']:
            if collection_name in collections:
                count = db[collection_name].count_documents({})
                print(f"📊 {collection_name} 컬렉션: {count}개 문서")
            else:
                print(f"⚠️  {collection_name} 컬렉션이 존재하지 않습니다")
        
        client.close()
        return True
        
    except ConnectionFailure as e:
        print(f"❌ MongoDB 연결 실패 (ConnectionFailure): {e}")
        return False
    except ServerSelectionTimeoutError as e:
        print(f"❌ MongoDB 서버 선택 타임아웃: {e}")
        print("💡 확인사항:")
        print("   1. MongoDB 서버가 실행 중인지 확인")
        print("   2. 서버 IP 주소가 올바른지 확인")
        print("   3. 포트 27017이 열려있는지 확인")
        print("   4. 방화벽 설정 확인")
        return False
    except Exception as e:
        print(f"❌ 예상치 못한 오류: {e}")
        return False

if __name__ == "__main__":
    print("=" * 50)
    print("MongoDB 연결 테스트")
    print("=" * 50)
    
    success = test_mongodb_connection()
    
    print("=" * 50)
    if success:
        print("✅ 테스트 완료: MongoDB 연결 성공")
    else:
        print("❌ 테스트 실패: MongoDB 연결 불가")
    print("=" * 50) 