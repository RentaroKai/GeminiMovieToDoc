import sys
import os

"""
Gemini API クライアントラッパー
- APIキー取得
- 複数のAPI連携モード
- エラーハンドリング・リトライ機能
"""

import time
import random
from pathlib import Path
from typing import Optional, Union, List, Dict, Any, Callable, Generator, AsyncGenerator

import google.genai as genai
from google.genai import types

from src.utils.logger import app_logger as logger
from src.config.settings import settings

# リトライ設定
MAX_RETRIES = 3
INITIAL_RETRY_DELAY = 1.0  # 秒
MAX_RETRY_DELAY = 10.0  # 秒
MAX_FILE_WAIT_RETRIES = 120  # ファイル処理待機の最大リトライ回数
FILE_WAIT_RETRY_DELAY = 5   # ファイル処理待機の間隔（秒）


class GeminiClient:
    """
    Gemini API クライアントラッパー
    
    Google GenAI パッケージをラップし、以下の機能を提供:
    - API キー管理・検証
    - モデル選択・検証
    - ファイルアップロード・API呼び出し
    - エラーハンドリング・リトライ
    """
    
    def __init__(self, api_key: Optional[str] = None, model_name: Optional[str] = None):
        """
        Gemini クライアントの初期化
        
        Args:
            api_key: Gemini API キー (指定がなければ設定か環境変数から取得)
            model_name: 使用するモデル名 (指定がなければ設定から取得)
        """
        self.api_key = api_key or settings.gemini.api_key
        self.model_name = model_name or settings.gemini.model_name
        self.client = None
        self.available_models = []
        self.file_references = []  # アップロードしたファイルの参照を保持
        
        # クライアントの初期化
        self._initialize_client()
    
    def _initialize_client(self) -> None:
        """クライアントを初期化"""
        if not self.api_key:
            logger.error("Gemini API キーが設定されていません")
            raise ValueError("Gemini API キーが必要です。環境変数かsettings.jsonで設定してください。")
        
        try:
            # API キーを設定し、クライアントを初期化
            self.client = genai.Client(api_key=self.api_key)
            
            # 利用可能なモデルを取得
            self._get_available_models()
            
            # モデル名の検証
            self._validate_model_name()
            
            logger.info(f"Gemini クライアント初期化完了: モデル '{self.model_name}'")
        
        except Exception as e:
            logger.error(f"Gemini クライアント初期化エラー: {e}")
            raise
    
    def _get_available_models(self) -> None:
        """利用可能なモデルのリストを取得"""
        try:
            models = self._retry_operation(
                lambda: self.client.models.list(),
                "models.list"
            )
            self.available_models = [model.name for model in models]
            logger.debug(f"利用可能なモデル: {self.available_models}")
        except Exception as e:
            logger.error(f"モデル一覧取得エラー: {e}")
            self.available_models = []
    
    def _validate_model_name(self) -> None:
        """モデル名を検証し、必要に応じて修正"""
        if not self.available_models:
            logger.warning("利用可能なモデルが取得できないため、モデル名検証をスキップします")
            return
        
        logger.info(f"モデル名検証開始: 指定モデル='{self.model_name}'")
        logger.info(f"利用可能なモデル一覧 ({len(self.available_models)}):")
        for i, model in enumerate(self.available_models, 1):
            logger.info(f"  {i}. {model}")
        
        # 1. 完全一致を最優先でチェック（そのまま）
        if self.model_name in self.available_models:
            logger.info(f"完全一致モデルが見つかりました: '{self.model_name}'")
            return  # 完全一致が見つかった場合、そのまま使用
        
        # 2. models/接頭辞付きでの完全一致をチェック
        prefixed_model = f"models/{self.model_name}" if not self.model_name.startswith("models/") else self.model_name
        if prefixed_model in self.available_models:
            original_model = self.model_name
            self.model_name = prefixed_model
            logger.info(f"接頭辞付き完全一致モデルが見つかりました: '{original_model}' -> '{self.model_name}'")
            return
        
        # 3. 接頭辞を外した正規化での完全一致をチェック
        normalized_available = {}
        for model in self.available_models:
            normalized_name = model.replace("models/", "") if model.startswith("models/") else model
            normalized_available[normalized_name] = model
        
        normalized_input = self.model_name.replace("models/", "") if self.model_name.startswith("models/") else self.model_name
        if normalized_input in normalized_available:
            original_model = self.model_name
            self.model_name = normalized_available[normalized_input]
            logger.info(f"正規化完全一致モデルが見つかりました: '{original_model}' -> '{self.model_name}'")
            return
        
        # 4. 完全一致が見つからない場合のみ部分一致をチェック
        logger.info(f"完全一致モデルが見つからないため、部分一致を検索します")
        partial_matches = []
        for model in self.available_models:
            if self.model_name in model:
                partial_matches.append(model)
        
        if partial_matches:
            # 部分一致が複数ある場合、全てログに出力
            logger.info(f"部分一致モデルが見つかりました ({len(partial_matches)}):")
            for i, match in enumerate(partial_matches, 1):
                logger.info(f"  {i}. {match}")
            
            # 最初の部分一致を使用（将来的にはより良い選択ロジックを実装可能）
            original_model = self.model_name
            self.model_name = partial_matches[0]
            logger.warning(f"モデル名を部分一致で修正: '{original_model}' -> '{self.model_name}'")
            return
        
        # 5. 完全一致も部分一致も見つからない場合
        logger.error(f"指定されたモデル '{self.model_name}' に一致するモデルが見つかりません")
        if self.available_models:
            original_model = self.model_name
            self.model_name = self.available_models[0]
            logger.warning(f"デフォルトモデルを使用: '{original_model}' -> '{self.model_name}'")
        else:
            logger.error("利用可能なモデルが存在しません")
    
    def upload_file(self, file_path: Union[str, Path]) -> Optional[Dict[str, Any]]:
        """
        ファイルをアップロード
        
        Args:
            file_path: アップロードするファイルのパス
            
        Returns:
            Optional[Dict[str, Any]]: アップロード成功時はファイル参照情報、失敗時はNone
        """
        path = Path(file_path)
        if not path.exists():
            logger.error(f"ファイルが存在しません: {path}")
            return None
        
        try:
            # リトライロジックでファイルアップロード
            file_reference = self._retry_operation(
                lambda: self.client.files.upload(file=str(path)),
                f"ファイルアップロード: {path.name}"
            )
            
            # ファイル参照を保持
            if file_reference:
                # ファイル処理が完了 (ACTIVEになる) まで待機
                if not self._wait_for_file_processing(file_reference):
                    logger.error(f"ファイル処理待機失敗: {file_reference.name}")
                    # 失敗した場合、ファイル参照を削除リストに追加（後で削除試行）
                    self.file_references.append(file_reference)
                    return None # アップロード失敗として扱う
                
                self.file_references.append(file_reference)
                logger.info(f"ファイルアップロード成功 & ACTIVE確認: {path.name} (ID: {file_reference.name})")
                return {"name": file_reference.name, "path": str(path)}
            
            return None
            
        except Exception as e:
            logger.error(f"ファイルアップロードエラー: {e}")
            return None
    
    def _wait_for_file_processing(self, file_reference: Any) -> bool:
        """
        ファイルの処理完了 (ACTIVE状態) を待機
        
        Args:
            file_reference: アップロードされたファイルオブジェクト
            
        Returns:
            bool: 処理がACTIVEになった場合はTrue、タイムアウトまたは失敗した場合はFalse
        """
        logger.info(f"ファイル処理待機開始: {file_reference.name}")
        # 初期リトライ遅延を設定
        retry_delay = FILE_WAIT_RETRY_DELAY
        for attempt in range(MAX_FILE_WAIT_RETRIES):
            try:
                current_file = self.client.files.get(name=file_reference.name)
                state = current_file.state.name
                logger.debug(f"ファイル状態確認 ({attempt + 1}/{MAX_FILE_WAIT_RETRIES}): {file_reference.name} - {state}")
                
                if state == "ACTIVE":
                    logger.info(f"ファイル処理完了 (ACTIVE): {file_reference.name}")
                    return True
                elif state == "FAILED":
                    logger.error(f"ファイル処理失敗 (FAILED): {file_reference.name}")
                    return False
                # PROCESSING または他の状態の場合は待機を続ける
            except Exception as e:
                logger.warning(f"ファイル状態取得エラー ({file_reference.name}): {e}")
                # 状態取得エラーでもリトライを続ける

            # 次回リトライ前に指数バックオフ + ジッターで待機
            jitter = random.uniform(0, 0.1 * retry_delay)
            retry_delay = min(retry_delay * 2 + jitter, MAX_RETRY_DELAY)
            logger.debug(f"ファイル状態確認待機: {retry_delay:.2f}秒後に次の試行")
            time.sleep(retry_delay)
            
        logger.error(f"ファイル処理待機タイムアウト: {file_reference.name} ({MAX_FILE_WAIT_RETRIES}回試行)")
        return False
    
    def generate_content_mode(self, prompt: str, file_reference: Optional[Dict[str, Any]] = None, 
                             streaming: bool = True) -> Union[str, Generator[str, None, None]]:
        """
        generate_content モードでの応答生成
        
        Args:
            prompt: プロンプト
            file_reference: アップロード済みファイルの参照情報（upload_fileの戻り値）
            streaming: ストリーミングモードを使用するか
            
        Returns:
            生成されたコンテンツ (文字列またはストリームジェネレータ)
        """
        try:
            # 生成設定
            generation_config = types.GenerateContentConfig(
                temperature=0.4,
                top_p=0.95,
                top_k=0,
                max_output_tokens=8192,
                stop_sequences=[]
            )
            
            # コンテンツの準備
            contents = []
            
            # プロンプト追加
            contents.append(prompt)
            
            # ファイル参照があれば追加
            if file_reference:
                file = self._retry_operation(
                    lambda: self.client.files.get(name=file_reference["name"]),
                    f"ファイル取得: {file_reference['name']}"
                )
                contents.append(file)
            
            if streaming:
                # ストリーミングモード
                logger.debug(f"generate_content_streamを呼び出し: プロンプト='{prompt[:50]}...'")
                response_stream = self._retry_operation(
                    lambda: self.client.models.generate_content_stream(
                        model=self.model_name,
                        contents=contents,
                        config=generation_config
                    ),
                    "generate_content_stream"
                )
                
                # ストリーミングジェネレータ
                def text_generator():
                    for chunk in response_stream:
                        if hasattr(chunk, 'text'):
                            yield chunk.text
                
                return text_generator()
            
            else:
                # 非ストリーミングモード
                logger.debug(f"generate_contentを呼び出し: プロンプト='{prompt[:50]}...'")
                response = self._retry_operation(
                    lambda: self.client.models.generate_content(
                        model=self.model_name,
                        contents=contents,
                        config=generation_config
                    ),
                    "generate_content"
                )
                
                return response.text
        
        except Exception as e:
            logger.error(f"コンテンツ生成エラー (generate_content): {e}")
            raise
    
    def chat_session_mode(self, prompt: str, file_reference: Optional[Dict[str, Any]] = None,
                         streaming: bool = True) -> Union[str, Generator[str, None, None]]:
        """
        チャットセッションモードでの応答生成
        
        Args:
            prompt: プロンプト
            file_reference: アップロード済みファイルの参照情報（upload_fileの戻り値）
            streaming: ストリーミングモードを使用するか
            
        Returns:
            生成されたコンテンツ (文字列またはストリームジェネレータ)
        """
        try:
            # 生成設定
            generation_config = types.GenerateContentConfig(
                temperature=0.4,
                top_p=0.95,
                top_k=0,
                max_output_tokens=8192
            )
            
            # チャットセッション作成
            chat = self._retry_operation(
                lambda: self.client.chats.create(model=self.model_name),
                "chats.create"
            )
            
            # メッセージコンテンツの準備
            contents = []
            contents.append(prompt)
            
            # ファイル参照があれば追加
            if file_reference:
                file = self._retry_operation(
                    lambda: self.client.files.get(name=file_reference["name"]),
                    f"ファイル取得: {file_reference['name']}"
                )
                contents.append(file)
            
            if streaming:
                # ストリーミングモード
                logger.debug(f"send_message_streamを呼び出し: プロンプト='{prompt[:50]}...'")
                response_stream = self._retry_operation(
                    lambda: chat.send_message_stream(contents),
                    "send_message_stream"
                )
                
                # ストリーミングジェネレータ
                def text_generator():
                    for chunk in response_stream:
                        if hasattr(chunk, 'text'):
                            yield chunk.text
                
                return text_generator()
            
            else:
                # 非ストリーミングモード
                logger.debug(f"send_messageを呼び出し: プロンプト='{prompt[:50]}...'")
                response = self._retry_operation(
                    lambda: chat.send_message(contents),
                    "send_message"
                )
                
                return response.text
        
        except Exception as e:
            logger.error(f"コンテンツ生成エラー (chat_session): {e}")
            raise
    
    def analyze_video(self, video_path: Union[str, Path], prompt: str, 
                     mode: Optional[str] = None, streaming: Optional[bool] = None) -> Union[str, Generator[str, None, None]]:
        """
        動画を解析して結果を返す
        
        Args:
            video_path: 解析する動画ファイルのパス
            prompt: 解析プロンプト
            mode: API連携モード ("generate_content" または "chat")
            streaming: ストリーミングモードを使用するか
            
        Returns:
            Union[str, Generator[str, None, None]]: 解析結果またはストリーム
        """
        # デフォルト値を設定から取得
        if mode is None:
            mode = settings.gemini.mode
        if streaming is None:
            streaming = settings.gemini.stream_response
        
        try:
            # ファイルアップロード
            file_reference = self.upload_file(video_path)
            if not file_reference:
                raise ValueError(f"ファイルのアップロードに失敗しました: {video_path}")
            
            # モードに応じてAPI呼び出し
            if mode == "generate_content":
                logger.info(f"generate_contentモードで解析開始: {Path(video_path).name}")
                return self.generate_content_mode(prompt, file_reference, streaming)
            elif mode == "chat":
                logger.info(f"chatモードで解析開始: {Path(video_path).name}")
                return self.chat_session_mode(prompt, file_reference, streaming)
            else:
                raise ValueError(f"不明なモード: {mode}")
        
        except Exception as e:
            logger.error(f"動画解析エラー: {e}")
            raise
    
    def _retry_operation(self, operation: Callable, operation_name: str) -> Any:
        """
        リトライロジックを実装した操作実行
        
        Args:
            operation: 実行する操作（関数）
            operation_name: ログ用の操作名
            
        Returns:
            Any: 操作の結果
        """
        retry_count = 0
        retry_delay = INITIAL_RETRY_DELAY
        
        while retry_count <= MAX_RETRIES:
            try:
                result = operation()
                if retry_count > 0:
                    logger.info(f"{operation_name}: {retry_count}回目のリトライで成功")
                return result
            
            except Exception as e:
                retry_count += 1
                
                if retry_count > MAX_RETRIES:
                    logger.error(f"{operation_name}: リトライ回数上限到達 ({MAX_RETRIES}回) - エラー: {e}")
                    raise
                
                # エクスポネンシャルバックオフ + ジッター
                jitter = random.uniform(0, 0.1 * retry_delay)
                retry_delay = min(retry_delay * 2 + jitter, MAX_RETRY_DELAY)
                
                logger.warning(f"{operation_name}: エラー発生 ({e}) - {retry_delay:.2f}秒後に{retry_count}回目のリトライ")
                time.sleep(retry_delay)
    
    def cleanup_files(self) -> None:
        """アップロードしたファイルを削除"""
        for file_ref in self.file_references:
            try:
                # リトライ付きでファイル削除を実行
                self._retry_operation(
                    lambda: self.client.files.delete(name=file_ref.name),
                    f"ファイル削除: {file_ref.name}"
                )
                logger.debug(f"アップロードファイル削除: {file_ref.name}")
            except Exception as e:
                logger.warning(f"ファイル削除エラー ({file_ref.name}): {e}")
        
        # 削除を試行したファイル参照リストをクリア
        self.file_references = []


if __name__ == "__main__":
    # このファイルを直接実行した場合、クライアントのテスト
    # import os # 不要なので削除
    # import sys # 不要なので削除

    # APIキーを環境変数から取得
    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        print("環境変数 GEMINI_API_KEY または GOOGLE_API_KEY にAPIキーを設定してください")
        sys.exit(1)
    
    # コマンドライン引数でファイルパスとモデル名を受け取る
    if len(sys.argv) >= 2:
        test_file = sys.argv[1]
        model_name = sys.argv[2] if len(sys.argv) >= 3 else "gemini-2.5-pro"
        
        print(f"テスト設定:")
        print(f"- ファイル: {test_file}")
        print(f"- モデル: {model_name}")
        
        # クライアント初期化
        client = GeminiClient(api_key=api_key, model_name=model_name)
        
        # ファイルアップロード
        file_ref = client.upload_file(test_file)
        if file_ref:
            print(f"ファイルアップロード成功: {file_ref}")
            
            # テスト用プロンプト
            prompt = "この動画について詳しく説明してください。何が映っていて、どんな内容か解析してください。"
            
            # 非ストリーミングモードでテスト
            try:
                print("\n--- generate_content モードでテスト (非ストリーミング) ---")
                result = client.generate_content_mode(prompt, file_ref, streaming=False)
                print(f"結果: {result[:200]}...")
                
                print("\n--- chat モードでテスト (非ストリーミング) ---")
                result = client.chat_session_mode(prompt, file_ref, streaming=False)
                print(f"結果: {result[:200]}...")
            except Exception as e:
                print(f"エラー: {e}")
            
            # ファイルクリーンアップ
            client.cleanup_files()
    else:
        print("使用法: python gemini_client.py <テストするファイルパス> [モデル名]") 