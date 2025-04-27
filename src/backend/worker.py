"""
非同期ワーカークラス - UIとAPIバックエンドの橋渡し

QThread を使用して UI スレッドとは別のスレッドで Gemini API 処理を実行
"""

import os
import sys
from pathlib import Path
from typing import Optional, Union, Dict, Any, List, Generator

from PySide6.QtCore import QThread, Signal, QObject

from src.utils.logger import app_logger as logger
from src.utils.file_ops import check_file_size, get_output_filename, save_text_output
from src.config.settings import settings
from src.backend.gemini_client import GeminiClient


class GeminiWorker(QThread):
    """
    Gemini API 呼び出しを行う非同期ワーカー (QThread)
    
    Signals:
        progress_update: 進捗更新シグナル (int: 進捗率 0-100)
        status_update: 状態更新シグナル (str: 状態メッセージ)
        error: エラーシグナル (str: エラーメッセージ)
        result_ready: 結果取得シグナル (str: API からの応答テキスト)
        stream_chunk: ストリーミング時のテキストチャンクシグナル (str: テキストチャンク)
        complete: 完了シグナル (str: 保存したファイルパス)
    """
    
    progress_update = Signal(int)
    status_update = Signal(str)
    error = Signal(str)
    result_ready = Signal(str)
    stream_chunk = Signal(str)
    complete = Signal(str)
    
    def __init__(self, parent: Optional[QObject] = None):
        """
        ワーカーの初期化
        
        Args:
            parent: 親QObject
        """
        super().__init__(parent)
        
        self.video_path = None
        self.prompt = None
        self.api_key = None
        self.model_name = None
        self.mode = None
        self.streaming = True
        self.output_dir = None
        self.use_bom = True
        self.max_file_size_mb = 100
        
        self._result_text = ""
        self._output_file = None
        self._client = None
    
    def configure(self, video_path: Union[str, Path], prompt: str, 
                 api_key: Optional[str] = None, model_name: Optional[str] = None,
                 mode: Optional[str] = None, streaming: Optional[bool] = None,
                 output_dir: Optional[Path] = None, use_bom: Optional[bool] = None,
                 max_file_size_mb: Optional[int] = None) -> None:
        """
        ワーカーの設定
        
        Args:
            video_path: 解析する動画ファイルのパス
            prompt: 解析プロンプト
            api_key: Gemini API キー
            model_name: 使用するモデル名
            mode: API連携モード
            streaming: ストリーミングモードを使用するか
            output_dir: 出力ディレクトリ
            use_bom: UTF-8 with BOMを使用するか
            max_file_size_mb: 許容される最大ファイルサイズ (MB)
        """
        self.video_path = Path(video_path)
        self.prompt = prompt
        self.api_key = api_key
        self.model_name = model_name or settings.gemini.model_name
        self.mode = mode or settings.gemini.mode
        
        # 明示的に指定があればそれを使用し、そうでなければ設定値を使用
        if streaming is not None:
            self.streaming = streaming
        else:
            self.streaming = settings.gemini.stream_response
            
        self.output_dir = output_dir or settings.file.output_directory
        
        if use_bom is not None:
            self.use_bom = use_bom
        else:
            self.use_bom = settings.file.use_bom
            
        self.max_file_size_mb = max_file_size_mb or settings.file.max_file_size_mb
        
        # 結果テキストをクリア
        self._result_text = ""
    
    def run(self) -> None:
        """QThreadで実行される処理"""
        try:
            # 状態更新
            self.status_update.emit("処理を開始しています...")
            self.progress_update.emit(0)
            
            # 基本チェック
            if not self.video_path or not self.prompt:
                raise ValueError("動画ファイルとプロンプトが設定されていません")
            
            # ファイルサイズチェック
            if not check_file_size(self.video_path, self.max_file_size_mb):
                raise ValueError(f"ファイルサイズが上限（{self.max_file_size_mb}MB）を超えています")
            
            # 出力ファイル名生成
            self._output_file = get_output_filename(self.video_path, self.output_dir)
            
            # 状態更新
            self.status_update.emit("Gemini APIに接続しています...")
            self.progress_update.emit(10)
            
            # クライアント初期化
            self._client = GeminiClient(api_key=self.api_key, model_name=self.model_name)
            
            # 状態更新
            self.status_update.emit("動画を解析しています...")
            self.progress_update.emit(20)
            
            # 動画解析
            if self.streaming:
                # ストリーミングモード
                self._process_streaming()
            else:
                # 非ストリーミングモード
                self._process_non_streaming()
            
            # 状態更新
            self.status_update.emit("結果を保存しています...")
            self.progress_update.emit(90)
            
            # 結果保存
            saved = save_text_output(self._result_text, self._output_file, self.use_bom)
            if not saved:
                raise IOError(f"結果の保存に失敗しました: {self._output_file}")
            
            # 完了シグナル発行
            self.status_update.emit("処理が完了しました")
            self.progress_update.emit(100)
            self.complete.emit(str(self._output_file))
        
        except Exception as e:
            # エラー処理
            error_msg = f"処理中にエラーが発生しました: {e}"
            logger.error(error_msg)
            self.error.emit(error_msg)
            self.status_update.emit("エラーが発生しました")
            self.progress_update.emit(0)
        
        finally:
            # クリーンアップ
            if self._client:
                try:
                    self._client.cleanup_files()
                except Exception as e:
                    logger.warning(f"クリーンアップ中にエラー: {e}")
    
    def _process_streaming(self) -> None:
        """ストリーミングモードでの処理"""
        try:
            # ストリーミング処理
            stream = self._client.analyze_video(
                self.video_path, 
                self.prompt,
                mode=self.mode,
                streaming=True
            )
            
            # ジェネレータから結果を受信
            chunk_count = 0
            progress_base = 20
            
            for chunk in stream:
                # チャンクをストリーミング
                self.stream_chunk.emit(chunk)
                
                # 結果に追加
                self._result_text += chunk
                
                # 進捗更新（ランダムに増加）
                chunk_count += 1
                if chunk_count % 5 == 0:  # 5チャンクごとに進捗更新
                    # 20% から 90% までの進捗を徐々に増やす
                    progress = min(90, progress_base + chunk_count // 2)
                    self.progress_update.emit(progress)
                    
                    # 状態更新
                    if progress < 50:
                        self.status_update.emit("動画を解析しています...")
                    elif progress < 70:
                        self.status_update.emit("テキストを生成しています...")
                    else:
                        self.status_update.emit("レスポンスを整形しています...")
            
            # 完了時には全テキストを送信
            self.result_ready.emit(self._result_text)
            
        except Exception as e:
            logger.error(f"ストリーミング処理中にエラー: {e}")
            raise
    
    def _process_non_streaming(self) -> None:
        """非ストリーミングモードでの処理"""
        try:
            # 非ストリーミング処理
            self.status_update.emit("動画を解析しています...")
            self.progress_update.emit(30)
            
            # 解析実行
            result = self._client.analyze_video(
                self.video_path, 
                self.prompt,
                mode=self.mode,
                streaming=False
            )
            
            # 結果保存
            self._result_text = result
            
            # 進捗更新
            self.progress_update.emit(80)
            self.status_update.emit("レスポンスを処理しています...")
            
            # 結果シグナル発行
            self.result_ready.emit(self._result_text)
            
        except Exception as e:
            logger.error(f"非ストリーミング処理中にエラー: {e}")
            raise


if __name__ == "__main__":
    # このファイルを直接実行した場合、テスト
    import time
    from PySide6.QtWidgets import QApplication
    
    def on_progress(value):
        print(f"進捗: {value}%")
    
    def on_status(message):
        print(f"状態: {message}")
    
    def on_error(message):
        print(f"エラー: {message}")
    
    def on_result(text):
        print(f"結果: {text[:100]}...")
    
    def on_stream_chunk(chunk):
        print(f"チャンク: {chunk}")
    
    def on_complete(output_file):
        print(f"完了: {output_file}")
        # アプリケーション終了
        app.quit()
    
    # テスト用のファイルパスとプロンプトを設定
    if len(sys.argv) >= 2:
        test_file = sys.argv[1]
        api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        
        if not api_key:
            print("環境変数 GEMINI_API_KEY または GOOGLE_API_KEY にAPIキーを設定してください")
            sys.exit(1)
        
        # QApplication作成
        app = QApplication([])
        
        # ワーカー作成
        worker = GeminiWorker()
        
        # シグナル接続
        worker.progress_update.connect(on_progress)
        worker.status_update.connect(on_status)
        worker.error.connect(on_error)
        worker.result_ready.connect(on_result)
        worker.stream_chunk.connect(on_stream_chunk)
        worker.complete.connect(on_complete)
        
        # 設定
        worker.configure(
            video_path=test_file,
            prompt="この動画について詳しく説明してください。何が映っていて、どんな内容か解析してください。",
            api_key=api_key,
            streaming=True
        )
        
        # 実行
        worker.start()
        
        # イベントループ開始
        sys.exit(app.exec())
    
    else:
        print("使用法: python worker.py <テストするファイルパス>") 