#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
MongoDB 서버 확인 및 시작 스크립트

이 스크립트는 MongoDB 서버가 실행 중인지 확인하고, 
실행 중이 아니면 자동으로 시작합니다.
"""

import os
import sys
import time
import socket
import subprocess
import platform
import argparse
from pymongo import MongoClient
from pymongo.errors import ServerSelectionTimeoutError

def is_port_in_use(port):
    """지정된 포트가 사용 중인지 확인"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('localhost', port)) == 0

def test_mongodb_connection(timeout=2000):
    """MongoDB 연결 테스트"""
    try:
        client = MongoClient('mongodb://localhost:27017/', 
                            serverSelectionTimeoutMS=timeout)
        client.server_info()  # 실제 연결 테스트
        client.close()
        return True
    except ServerSelectionTimeoutError:
        return False
    except Exception as e:
        print(f"MongoDB 연결 테스트 중 오류: {e}")
        return False

def find_mongod_executable():
    """MongoDB 실행 파일 경로 찾기"""
    system = platform.system()
    
    # Windows 환경
    if system == "Windows":
        # 일반적인 MongoDB 설치 경로
        common_paths = [
            r"C:\Program Files\MongoDB\Server\6.0\bin\mongod.exe",  # MongoDB 6.0
            r"C:\Program Files\MongoDB\Server\5.0\bin\mongod.exe",  # MongoDB 5.0
            r"C:\Program Files\MongoDB\Server\4.4\bin\mongod.exe",  # MongoDB 4.4
            r"C:\mongodb\bin\mongod.exe",                           # 사용자 정의 경로
        ]
        
        # 현재 작업 디렉토리와 상대 경로 검색
        local_paths = [
            os.path.join(os.getcwd(), "mongodb", "bin", "mongod.exe"),
            os.path.join(os.getcwd(), "bin", "mongod.exe"),
            "mongod.exe"
        ]
        
        search_paths = common_paths + local_paths
        
        for path in search_paths:
            if os.path.exists(path):
                return path
                
        # PATH 환경 변수에서 검색
        try:
            result = subprocess.run(["where", "mongod"], 
                                  capture_output=True, 
                                  text=True, 
                                  check=False)
            if result.returncode == 0:
                mongod_path = result.stdout.strip().split('\n')[0]
                if os.path.exists(mongod_path):
                    return mongod_path
        except Exception:
            pass
    
    # Linux/Mac 환경
    else:
        try:
            result = subprocess.run(["which", "mongod"], 
                                  capture_output=True, 
                                  text=True, 
                                  check=False)
            if result.returncode == 0:
                return result.stdout.strip()
        except Exception:
            pass
        
        # 일반적인 Linux 설치 경로
        common_paths = [
            "/usr/bin/mongod",
            "/usr/local/bin/mongod",
            "/opt/mongodb/bin/mongod"
        ]
        
        for path in common_paths:
            if os.path.exists(path):
                return path
    
    return None

def start_mongodb(data_dir=None, log_path=None):
    """MongoDB 서버 시작"""
    mongod_path = find_mongod_executable()
    
    if not mongod_path:
        print("MongoDB 실행 파일을 찾을 수 없습니다.")
        return False
    
    print(f"MongoDB 실행 파일 경로: {mongod_path}")
    
    # 기본 데이터 디렉토리 설정
    if not data_dir:
        data_dir = os.path.join(os.getcwd(), "data", "db")
    
    # 데이터 디렉토리가 없으면 생성
    os.makedirs(data_dir, exist_ok=True)
    
    # 로그 파일 경로 설정
    if not log_path:
        log_dir = os.path.join(os.getcwd(), "logs")
        os.makedirs(log_dir, exist_ok=True)
        log_path = os.path.join(log_dir, "mongodb.log")
    
    cmd = [
        mongod_path,
        "--dbpath", data_dir,
        "--logpath", log_path,
        "--logappend"
    ]
    
    try:
        # Windows에서는 숨겨진 창으로 실행
        if platform.system() == "Windows":
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
        else:
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
        
        print(f"MongoDB 서버 시작 (PID: {process.pid})")
        return True
    except Exception as e:
        print(f"MongoDB 서버 시작 실패: {e}")
        return False

def main():
    """메인 함수"""
    parser = argparse.ArgumentParser(description="MongoDB 서버 확인 및 시작")
    parser.add_argument("--data-dir", help="MongoDB 데이터 디렉토리 경로")
    parser.add_argument("--log-path", help="MongoDB 로그 파일 경로")
    parser.add_argument("--timeout", type=int, default=5000, help="연결 타임아웃(ms)")
    parser.add_argument("--wait", type=int, default=10, help="서버 시작 후 대기 시간(초)")
    args = parser.parse_args()
    
    print("MongoDB 서버 확인 중...")
    
    # MongoDB 포트(27017)가 사용 중인지 확인
    if is_port_in_use(27017):
        print("포트 27017이 이미 사용 중입니다.")
        
        # 실제로 MongoDB 서버가 실행 중인지 확인
        if test_mongodb_connection(args.timeout):
            print("MongoDB 서버가 실행 중이며 연결 가능합니다.")
            return 0
        else:
            print("포트는 사용 중이지만 MongoDB 서버에 연결할 수 없습니다.")
            print("다른 프로그램이 해당 포트를 사용 중이거나 MongoDB가 올바르게 실행되지 않았을 수 있습니다.")
            return 1
    
    print("MongoDB 서버가 실행 중이 아닙니다. 서버를 시작합니다...")
    
    # MongoDB 서버 시작
    if start_mongodb(args.data_dir, args.log_path):
        print(f"서버 시작을 기다리는 중... ({args.wait}초)")
        
        # 서버 시작 대기
        start_time = time.time()
        while time.time() - start_time < args.wait:
            if test_mongodb_connection(1000):  # 빠른 테스트
                elapsed = time.time() - start_time
                print(f"MongoDB 서버가 성공적으로 시작되었습니다. (소요 시간: {elapsed:.1f}초)")
                return 0
            time.sleep(0.5)
        
        print("MongoDB 서버 시작 시간이 초과되었습니다.")
        return 1
    else:
        print("MongoDB 서버를 시작하지 못했습니다.")
        return 1

if __name__ == "__main__":
    sys.exit(main()) 