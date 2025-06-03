#!/bin/bash

echo "===== 시스템 초기화 중... ====="
echo "MongoDB 서버 확인 및 시작..."

python3 ensure_mongodb.py --wait 20
if [ $? -ne 0 ]; then
    echo "MongoDB 서버 시작 실패!"
    echo "수동으로 MongoDB 서버를 시작하고 다시 시도하세요."
    read -p "계속하려면 Enter 키를 누르세요..."
    exit 1
fi

echo "===== 메인 프로그램 시작 ====="
python3 dashboard.py
if [ $? -ne 0 ]; then
    echo "프로그램 실행 중 오류가 발생했습니다."
    read -p "계속하려면 Enter 키를 누르세요..."
fi 