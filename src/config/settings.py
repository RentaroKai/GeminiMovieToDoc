"""
設定管理モジュール - pydanticを使用した設定のバリデーションと保存

設定の優先度:
1. UI入力
2. 環境変数
3. 設定ファイル
"""

import json
import os
from pathlib import Path
from typing import Optional, List, Literal

from pydantic import BaseModel, Field, validator

# utils から関数をインポート
from src.utils.path_utils import get_app_root
from src.utils.logger import app_logger # ログ出力用にインポート

# アプリケーションルートを取得
APP_ROOT = get_app_root()
CONFIG_DIR = APP_ROOT / "config"
OUTPUT_DIR = APP_ROOT / "output" # 出力先もルート基準に変更

# 起動時にディレクトリを確認・作成
CONFIG_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# パス情報をログ出力
app_logger.info(f"APP_ROOT determined as: {APP_ROOT}")
app_logger.info(f"CONFIG_DIR set to: {CONFIG_DIR}")
app_logger.info(f"OUTPUT_DIR set to: {OUTPUT_DIR}")


class GeminiSettings(BaseModel):
    """Gemini API関連の設定"""
    api_key: Optional[str] = Field(None, description="Gemini APIキー")
    model_name: str = Field("gemini-2.5-flash-preview-05-20", description="使用するGeminiモデル名")
    mode: Literal["generate_content", "stream_generate_content"] = Field("generate_content", description="API連携モード")
    stream_response: bool = Field(False, description="ストリーミングレスポンスを使用するか")

    @validator('mode')
    def validate_mode(cls, v):
        if v not in ["generate_content", "stream_generate_content"]:
            raise ValueError("modeは 'generate_content' または 'stream_generate_content' である必要があります")
        return v


class FileSettings(BaseModel):
    """ファイル操作関連の設定"""
    max_file_size_mb: int = Field(500, description="アップロード可能な最大ファイルサイズ(MB)")
    output_directory: Path = Field(OUTPUT_DIR, description="解析結果の保存先ディレクトリ")
    use_bom: bool = Field(True, description="出力ファイルにBOMを付与するか (Windowsでの文字化け防止)")
    input_directory: Path = Field(APP_ROOT, description="ファイル選択時にデフォルトで開くフォルダ")
    
    @validator('max_file_size_mb')
    def validate_file_size(cls, v):
        if v <= 0 or v > 1000:
            raise ValueError("ファイルサイズは1～1000MBの範囲で指定してください")
        return v


class UISettings(BaseModel):
    """UI関連の設定"""
    last_prompt: str = Field("", description="最後に使用したプロンプト")
    custom_prompt: str = Field("", description="カスタムプロンプト用の保存領域")
    template_names: List[str] = Field([], description="プロンプトテンプレート名のリスト")


class Settings(BaseModel):
    """アプリケーション全体の設定"""
    gemini: GeminiSettings = Field(default_factory=GeminiSettings)
    file: FileSettings = Field(default_factory=FileSettings)
    ui: UISettings = Field(default_factory=UISettings)


def load_settings() -> Settings:
    """
    設定を読み込む
    
    優先度:
    1. 設定ファイル (settings.json)
    2. 環境変数 (GEMINI_API_KEY or GOOGLE_API_KEY)
    """
    settings_path = CONFIG_DIR / "settings.json"
    app_logger.info(f"Attempting to load settings from: {settings_path}")
    
    # デフォルト設定
    settings_dict = {}
    
    # 設定ファイルから読み込み (存在する場合)
    if settings_path.exists():
        try:
            with open(settings_path, "r", encoding="utf-8") as f:
                settings_dict = json.load(f)
            app_logger.info(f"Successfully loaded settings from {settings_path}")
        except (json.JSONDecodeError, IOError) as e:
            # print(f"設定ファイルの読み込みに失敗しました: {e}")
            app_logger.error(f"Failed to load settings file {settings_path}: {e}", exc_info=True)
    else:
        app_logger.warning(f"Settings file not found at {settings_path}. Using defaults/env vars.")

    # 設定ファイルにAPIキーがない場合、環境変数から取得
    if not settings_dict.get("gemini", {}).get("api_key"):
        api_key_env = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        if api_key_env:
            if "gemini" not in settings_dict:
                settings_dict["gemini"] = {}
            settings_dict["gemini"]["api_key"] = api_key_env

    # Settingsモデルを生成
    try:
        return Settings(**settings_dict)
    except Exception as e:
        app_logger.error(f"設定の検証に失敗しました: {e}", exc_info=True)
        # フォールバック: デフォルト設定を返す
        app_logger.warning("Settings validation failed. Falling back to default settings.")
        return Settings()


def save_settings(settings: Settings) -> bool:
    """
    設定をファイルに保存する
    
    Args:
        settings: 保存する設定
        
    Returns:
        bool: 保存に成功したかどうか
    """
    settings_path = CONFIG_DIR / "settings.json"
    app_logger.info(f"Attempting to save settings to: {settings_path}")
    try:
        # 設定ディレクトリが存在しない場合は作成 (念のため再度確認)
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        
        # 設定を辞書に変換
        settings_dict = settings.dict()
        
        # Pathオブジェクトを文字列に変換
        if "file" in settings_dict and "output_directory" in settings_dict["file"]:
            settings_dict["file"]["output_directory"] = str(settings_dict["file"]["output_directory"])
        # 入力ディレクトリも文字列に変換
        if "file" in settings_dict and "input_directory" in settings_dict["file"]:
            settings_dict["file"]["input_directory"] = str(settings_dict["file"]["input_directory"])
        
        # API Keyをそのまま保存するように変更
        # if "gemini" in settings_dict and settings_dict["gemini"].get("api_key"):
        #     settings_dict["gemini"]["api_key"] = None
        
        with open(settings_path, "w", encoding="utf-8") as f:
            json.dump(settings_dict, f, ensure_ascii=False, indent=2)
        app_logger.info(f"Successfully saved settings to {settings_path}")
        return True
    except Exception as e:
        # エラーログに詳細を出力
        # from src.utils.logger import app_logger # ここでインポートしない
        app_logger.error(f"Error occurred while saving settings to {settings_path}: {e}", exc_info=True)
        # print(f"設定の保存に失敗しました: {e}") # printからロガーに変更
        return False


# デフォルト設定インスタンス (起動時に読み込み)
settings = load_settings() 