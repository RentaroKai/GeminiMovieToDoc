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

# プロジェクトのルートディレクトリを特定
PROJECT_ROOT = Path(__file__).parent.parent.parent.resolve()
CONFIG_DIR = PROJECT_ROOT / "config"
OUTPUT_DIR = PROJECT_ROOT / "output"


class GeminiSettings(BaseModel):
    """Gemini API関連の設定"""
    api_key: Optional[str] = Field(None, description="Gemini APIキー")
    model_name: str = Field("gemini-2.5-flash-preview-04-17", description="使用するGeminiモデル名")
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
    
    @validator('max_file_size_mb')
    def validate_file_size(cls, v):
        if v <= 0 or v > 1000:
            raise ValueError("ファイルサイズは1～1000MBの範囲で指定してください")
        return v


class UISettings(BaseModel):
    """UI関連の設定"""
    last_prompt: str = Field("", description="最後に使用したプロンプト")
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
    
    # デフォルト設定
    settings_dict = {}
    
    # 設定ファイルから読み込み (存在する場合)
    if settings_path.exists():
        try:
            with open(settings_path, "r", encoding="utf-8") as f:
                settings_dict = json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            print(f"設定ファイルの読み込みに失敗しました: {e}")

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
        print(f"設定の検証に失敗しました: {e}")
        # フォールバック: デフォルト設定を返す
        return Settings()


def save_settings(settings: Settings) -> bool:
    """
    設定をファイルに保存する
    
    Args:
        settings: 保存する設定
        
    Returns:
        bool: 保存に成功したかどうか
    """
    try:
        # 設定ディレクトリが存在しない場合は作成
        CONFIG_DIR.mkdir(exist_ok=True)
        
        # 設定を辞書に変換
        settings_dict = settings.dict()
        
        # Pathオブジェクトを文字列に変換
        if "file" in settings_dict and "output_directory" in settings_dict["file"]:
            settings_dict["file"]["output_directory"] = str(settings_dict["file"]["output_directory"])
        
        # API Keyをそのまま保存するように変更
        # if "gemini" in settings_dict and settings_dict["gemini"].get("api_key"):
        #     settings_dict["gemini"]["api_key"] = None
        
        with open(CONFIG_DIR / "settings.json", "w", encoding="utf-8") as f:
            json.dump(settings_dict, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        # エラーログに詳細を出力
        from src.utils.logger import app_logger # ここでインポート
        app_logger.error(f"設定の保存中にエラーが発生しました: {e}", exc_info=True)
        # print(f"設定の保存に失敗しました: {e}") # printからロガーに変更
        return False


# デフォルト設定インスタンス
settings = load_settings() 