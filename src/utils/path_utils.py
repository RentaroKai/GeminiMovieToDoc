"""
パス関連のユーティリティ関数
"""
from pathlib import Path
import sys, os

def get_app_root() -> Path:
    """
    アプリケーションのルートディレクトリを取得します。

    スクリプト実行時と PyInstaller でパッケージ化された .exe 実行時の両方に対応します。

    Returns:
        Path: アプリケーションのルートディレクトリを示す Path オブジェクト。
              - スクリプト実行時: プロジェクトのルートディレクトリ (例: /path/to/your/project)
              - exe実行時: exeファイルが存在するディレクトリ (例: C:\\Users\\User\\AppData\\Local\\Temp\\_MEIxxxxxx や C:\\Program Files\\MyApp)
                         ※ sys.executable は onefile の場合でも .exe へのパスを指します。
    """
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        # PyInstaller による onefile 実行の場合
        # sys.executable は .exe へのパス
        # print(f"Running in frozen mode (onefile): {sys.executable}")
        return Path(sys.executable).resolve().parent
    elif getattr(sys, 'frozen', False):
        # PyInstaller による one-folder 実行の場合 (または _MEIPASS がない場合)
        # sys.executable は .exe へのパス
        # print(f"Running in frozen mode (onefolder/other): {sys.executable}")
        return Path(sys.executable).resolve().parent
    else:
        # 通常のスクリプト実行の場合
        # このファイルの親の親の親がプロジェクトルートになる想定
        # print(f"Running as script: {__file__}")
        return Path(__file__).resolve().parent.parent.parent 