"""
非同期ワーカークラス - UIとAPIバックエンドの橋渡し

QThread を使用して UI スレッドとは別のスレッドで Gemini API 処理を実行
"""

import os
import sys
import datetime
import time
from pathlib import Path
from typing import Optional, Union, Dict, Any, List, Generator

from PySide6.QtCore import QThread, Signal, QObject

from src.utils.logger import app_logger as logger
from src.utils.file_ops import check_file_size, save_text_output, sanitize_filename, default_output_filename
from src.config.settings import settings
from src.backend.gemini_client import GeminiClient
from src.backend.title_generator import request_title
from src.utils.video_ops import compress_video_to_target


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
        
        # 結果テキストと出力ファイルをクリア
        self._result_text = ""
        self._output_file = None
    
    def run(self) -> None:
        """QThreadで実行される処理"""
        self._output_file = None # 実行開始時にも念のためクリア
        try:
            # 状態更新
            self.status_update.emit("処理を開始しています...")
            self.progress_update.emit(0)
            
            # 基本チェック
            if not self.video_path or not self.prompt:
                raise ValueError("動画ファイルとプロンプトが設定されていません")
            
            # ファイルサイズチェック
            original_file_size_mb = Path(self.video_path).stat().st_size / (1024 * 1024)
            
            if original_file_size_mb > self.max_file_size_mb:
                # 元のパスを保存
                self._original_video_path = self.video_path
                
                self.status_update.emit("動画サイズ超過 → 自動圧縮を試みます...")
                self.progress_update.emit(5) # 進捗を少し進める
                try:
                    # 圧縮関数呼び出し
                    compressed_path = compress_video_to_target(
                        self.video_path,
                        self.max_file_size_mb,
                        # logger=logger, # デフォルトで app_logger を使用
                        progress_cb=lambda msg, pct: (
                            self.status_update.emit(msg),
                            self.progress_update.emit(pct))
                    )

                    # 圧縮結果のハンドリング
                    if compressed_path is None:
                        # FFmpeg が見つからなかった場合
                        self.status_update.emit("警告: FFmpeg が見つからないため圧縮をスキップしました。")
                        raise ValueError(f"ファイルサイズが上限（{self.max_file_size_mb}MB）を超えています（圧縮スキップ）。")
                    elif compressed_path == Path(self.video_path):
                        # サイズが既に条件を満たしていた場合 (通常ここには来ないはずだが念のため)
                        pass # 何もしない
                    else:
                        # 圧縮成功 → パスを差し替え
                        self.status_update.emit("動画の圧縮が完了しました。")
                        self.video_path = str(compressed_path) # self.video_path を圧縮後のパスに更新

                except RuntimeError as compress_err:
                    # 圧縮処理自体が失敗した場合 (CRF上限到達など)
                    self.status_update.emit(f"自動圧縮に失敗しました: {compress_err}")
                    raise ValueError(
                        f"ファイルサイズが上限（{self.max_file_size_mb}MB）を超えています（自動圧縮失敗）。\n"
                        f"エラー詳細: {compress_err}"
                    )
                except Exception as e:
                    # 予期せぬエラー
                    self.status_update.emit(f"圧縮中に予期せぬエラーが発生しました: {e}")
                    raise ValueError(f"ファイルサイズが上限（{self.max_file_size_mb}MB）を超えています（圧縮中エラー）。")
            
            # 出力ディレクトリ確保 (Pathオブジェクトであることを保証)
            self.output_dir = Path(self.output_dir) # configureで設定済みだが念のため
            self.output_dir.mkdir(parents=True, exist_ok=True) # なければ作成
            
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
            
            # ---- ここからタイトル生成とファイル名決定 ----
            self.status_update.emit("ファイル名を生成しています...")
            self.progress_update.emit(85) # 進捗を調整
            
            generated_title = None
            if self._result_text: # 解析結果がある場合のみタイトル生成試行
                try:
                    # request_title は失敗時に None を返す想定
                    generated_title = request_title(self._result_text, self._client)
                except Exception as title_e:
                    # タイトル生成中の予期せぬエラー
                    logger.error(f"タイトル生成中にエラーが発生: {title_e}", exc_info=True)
                    # generated_title は None のまま
            
            # 出力ファイルの拡張子 (仮に.mdとする。必要なら設定等から取得)
            output_ext = ".md"
            
            if generated_title:
                safe_title = sanitize_filename(generated_title)
                # 日付 + タイトル + 拡張子
                filename = f"{datetime.datetime.now():%Y%m%d}_{safe_title}{output_ext}"
                self._output_file = self.output_dir / filename
                # ファイル名の衝突チェック (連番付与)
                counter = 1
                original_stem = self._output_file.stem
                while self._output_file.exists():
                    self._output_file = self.output_dir / f"{original_stem}_{counter}{output_ext}"
                    counter += 1
                logger.info(f"生成されたタイトルに基づくファイル名: {self._output_file.name}")
            else:
                # タイトル生成失敗 or 解析結果なしの場合、デフォルト名を使用
                logger.warning("タイトル生成に失敗したか、解析結果が空のため、デフォルトファイル名を使用します。")
                self._output_file = default_output_filename(self.output_dir, output_ext)
                logger.info(f"デフォルトファイル名を使用: {self._output_file.name}")
            
            # ---- ここまで ----
            
            # 状態更新
            self.status_update.emit("結果を保存しています...")
            self.progress_update.emit(90) # 進捗を調整
            
            # 結果保存
            if not self._output_file:
                 # 通常ここには来ないはずだが、念のため
                 raise RuntimeError("出力ファイルパスが決定されていません。")

            saved = save_text_output(self._result_text, self._output_file, self.use_bom)
            if not saved:
                raise IOError(f"結果の保存に失敗しました: {self._output_file}")
            
            # 完了シグナル発行
            self.status_update.emit("処理が完了しました")
            self.progress_update.emit(100)
            self.complete.emit(str(self._output_file)) # 保存した実際のパスを通知
        
        except Exception as e:
            # エラー処理
            error_msg = f"処理中にエラーが発生しました: {e}"
            logger.error(error_msg, exc_info=True) # トレースバックもログに記録
            self.error.emit(error_msg)
            self.status_update.emit("エラーが発生しました")
            self.progress_update.emit(0)
        
        finally:
            # クリーンアップ
            # 圧縮一時ファイルの削除
            try:
                if hasattr(self, '_original_video_path') and self.video_path != self._original_video_path:
                    temp_file = Path(self.video_path)
                    if temp_file.exists() and temp_file.name.endswith('_compressed.mp4') or '_compressed_' in temp_file.name:
                        logger.info(f"圧縮一時ファイルを削除します: {temp_file}")
                        temp_file.unlink()
            except Exception as temp_e:
                logger.warning(f"圧縮一時ファイル削除中にエラー: {temp_e}")
                
            if self._client:
                try:
                    # アップロードした動画ファイルと、タイトル生成に使ったファイルの参照を削除
                    self._client.cleanup_files()
                    logger.info("GeminiClientのファイル参照をクリーンアップしました。")
                except Exception as clean_e:
                    logger.warning(f"クリーンアップ中にエラー: {clean_e}")
    
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