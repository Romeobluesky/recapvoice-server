#wav 병합 클래스
import os
import subprocess

class WavMerger:
    def merge_and_save(self, ip, timestamp_dir, timestamp, local_num, remote_num, wav1_path, wav2_path, save_path):
        try:
            # 저장 디렉토리 생성
            save_dir = os.path.join(save_path, ip, timestamp_dir)
            os.makedirs(save_dir, exist_ok=True)

            # 출력 파일 경로
            output_path = os.path.join(save_dir, f"{timestamp}_merge_{local_num}-{remote_num}.wav")

            # ffmpeg 명령어 구성
            cmd = [
                'ffmpeg',
                '-i', wav1_path,  # 첫 번째 입력 파일
                '-i', wav2_path,  # 두 번째 입력 파일
                '-filter_complex', 'amix=inputs=2:duration=longest:dropout_transition=0',  # 오디오 믹싱
                '-y',  # 기존 파일 덮어쓰기
                output_path
            ]

            # ffmpeg 실행
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode == 0:
                print(f"[{ip}] WAV 파일 병합 완료: {output_path}")
                return output_path
            else:
                print(f"[{ip}] FFmpeg 오류: {result.stderr}")
                return None

        except Exception as e:
            print(f"WAV 파일 병합 중 오류 발생 (IP {ip}): {e}")
            return None
