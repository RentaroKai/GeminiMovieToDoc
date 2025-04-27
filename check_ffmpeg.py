"""
FFmpegが正しくインストールされているか確認するスクリプト
"""

import sys
import subprocess
import shutil
from pathlib import Path

def check_ffmpeg_installation():
    """FFmpegのインストール状態を確認"""
    print(f"Pythonバージョン: {sys.version}")
    print(f"実行環境: {sys.platform}")
    
    # PATHからffmpegを探す
    ffmpeg_path = shutil.which("ffmpeg")
    if ffmpeg_path:
        print(f"FFmpegが見つかりました: {ffmpeg_path}")
        
        # バージョン情報を取得
        try:
            result = subprocess.run(
                ["ffmpeg", "-version"], 
                capture_output=True, 
                text=True,
                check=True
            )
            version_info = result.stdout.split("\n")[0]
            print(f"FFmpegバージョン: {version_info}")
            return True
        except subprocess.CalledProcessError as e:
            print(f"FFmpegの実行中にエラーが発生しました: {e}")
            print(f"エラー出力: {e.stderr}")
            return False
    else:
        print("FFmpegが見つかりません。以下を確認してください:")
        print("1. FFmpegがインストールされているか")
        print("2. FFmpegが環境変数PATHに追加されているか")
        
        # Windowsの場合の追加情報
        if sys.platform == "win32":
            print("\nWindowsでのFFmpegインストール方法:")
            print("1. https://ffmpeg.org/download.html からFFmpegをダウンロード")
            print("2. ダウンロードしたファイルを任意のフォルダに展開（例: C:\\ffmpeg）")
            print("3. 環境変数PATHにFFmpegの実行ファイルがあるbinフォルダを追加")
            print("   例: C:\\ffmpeg\\bin")
            print("4. コマンドプロンプトを再起動")
        return False

if __name__ == "__main__":
    check_ffmpeg_installation() 