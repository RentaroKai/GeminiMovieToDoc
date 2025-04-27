"""
ロギング機能 - アプリケーション全体でのログ記録・表示機能
- 標準logging + ローテーション出力
- GUI内表示
"""

import logging
import os
import sys
from datetime import datetime
from logging.handlers import RotatingFileHandler, TimedRotatingFileHandler
from pathlib import Path
from typing import Optional, List, Dict, Any
from io import StringIO

from rich.logging import RichHandler

# 共通関数をインポート
from src.utils.path_utils import get_app_root

# アプリケーションルートとログディレクトリを定義
APP_ROOT = get_app_root()
LOG_DIR = APP_ROOT / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True) # ログディレクトリを作成

# ログフォーマット
LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# GUIに表示するためのログメッセージを保持するリスト
gui_log_records: List[Dict[str, Any]] = []


class GUILogHandler(logging.Handler):
    """
    GUIにログを表示するためのカスタムハンドラ
    """
    def __init__(self):
        super().__init__()
        self.setFormatter(logging.Formatter(LOG_FORMAT, DATE_FORMAT))
    
    def emit(self, record):
        """GUIに表示するためにログレコードを保存する"""
        message = self.format(record)
        level = record.levelname
        
        # GUI表示用に整形したレコードを保存
        record_dict = {
            "time": datetime.fromtimestamp(record.created).strftime(DATE_FORMAT),
            "level": level,
            "message": record.message,
            "formatted_message": message,
        }
        
        gui_log_records.append(record_dict)
        
        # リストが大きくなりすぎないように古いものを削除
        if len(gui_log_records) > 1000:
            gui_log_records.pop(0)


def setup_logger(name: str = "gemini_movie_analyzer", 
                 console_level: int = logging.INFO,
                 file_level: int = logging.DEBUG,
                 gui_level: int = logging.INFO) -> logging.Logger:
    """
    アプリケーションロガーのセットアップ
    
    Args:
        name: ロガー名
        console_level: コンソール出力のログレベル
        file_level: ファイル出力のログレベル
        gui_level: GUI表示のログレベル
        
    Returns:
        設定済みのロガーインスタンス
    """
    # ロガーを取得/作成
    logger = logging.getLogger(name)
    
    # 既に設定済みの場合は何もしない
    if logger.handlers:
        return logger
    
    # ロガーのレベルを設定（最も低いレベルに）
    min_level = min(console_level, file_level, gui_level)
    logger.setLevel(min_level)
    
    # ログディレクトリを作成
    LOG_DIR.mkdir(exist_ok=True)
    
    # 1. コンソールハンドラの設定（Rich利用）
    console_handler = RichHandler(level=console_level, 
                                  show_time=False, 
                                  show_path=False)
    console_handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(console_handler)
    
    # 2. 通常ログファイルハンドラの設定（日次ローテーション、最大30日）
    log_file = LOG_DIR / "app.log"
    file_handler = TimedRotatingFileHandler(
        filename=log_file,
        when="midnight",
        interval=1,
        backupCount=30,
        encoding="utf-8"
    )
    file_handler.setLevel(file_level)
    file_handler.setFormatter(logging.Formatter(LOG_FORMAT, DATE_FORMAT))
    logger.addHandler(file_handler)
    
    # 3. デバッグログファイルハンドラの設定（サイズローテーション）
    debug_file = LOG_DIR / "debug.log"
    debug_handler = RotatingFileHandler(
        filename=debug_file,
        maxBytes=10 * 1024 * 1024,  # 10MB
        backupCount=5,
        encoding="utf-8"
    )
    debug_handler.setLevel(logging.DEBUG)
    debug_handler.setFormatter(logging.Formatter(LOG_FORMAT, DATE_FORMAT))
    logger.addHandler(debug_handler)
    
    # 4. GUIログハンドラの設定
    gui_handler = GUILogHandler()
    gui_handler.setLevel(gui_level)
    logger.addHandler(gui_handler)
    
    # 起動時のログ
    logger.info(f"===== アプリケーション起動: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} =====")
    logger.debug(f"OS: {sys.platform}, Python: {sys.version}")
    
    return logger


# アプリケーション全体で使うロガーインスタンス
app_logger = setup_logger()


def get_gui_logs(level: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
    """
    GUI表示用のログレコードを取得
    
    Args:
        level: フィルターするログレベル（"INFO", "ERROR"など）
        limit: 返すログの最大数
        
    Returns:
        ログレコードのリスト（新しいものから順）
    """
    if level:
        filtered = [log for log in gui_log_records if log["level"] == level]
        return filtered[-limit:]
    
    return gui_log_records[-limit:]


if __name__ == "__main__":
    # このファイルを直接実行した場合、ロギング動作をテスト
    logger = setup_logger("test_logger")
    
    logger.debug("これはデバッグメッセージです")
    logger.info("これは情報メッセージです")
    logger.warning("これは警告メッセージです")
    logger.error("これはエラーメッセージです")
    
    # GUIログのテスト
    gui_logs = get_gui_logs()
    print(f"\nGUIログレコード ({len(gui_logs)}):")
    for log in gui_logs:
        print(f"{log['time']} [{log['level']}] {log['message']}") 