"""
モデル設定読み込みモジュール - config/models.yamlからGeminiモデル情報を読み込む
"""

import yaml
from pathlib import Path
from typing import Dict, List, Optional

# プロジェクトのルートディレクトリを特定
PROJECT_ROOT = Path(__file__).parent.parent.parent.resolve()
MODELS_CONFIG_PATH = PROJECT_ROOT / "config" / "models.yaml"


class ModelInfo:
    """モデル情報を保持するデータクラス"""
    
    def __init__(self, name: str, description: str = ""):
        self.name = name
        self.description = description
    
    def __str__(self) -> str:
        return f"{self.name} - {self.description}" if self.description else self.name


def load_models() -> List[ModelInfo]:
    """
    config/models.yamlからモデル情報を読み込む
    
    Returns:
        List[ModelInfo]: モデル情報のリスト。読み込みに失敗した場合は空リスト。
    """
    try:
        if not MODELS_CONFIG_PATH.exists():
            print(f"モデル設定ファイルが見つかりません: {MODELS_CONFIG_PATH}")
            return []
        
        with open(MODELS_CONFIG_PATH, "r", encoding="utf-8") as f:
            yaml_data = yaml.safe_load(f)
        
        models_list = []
        
        # 古い形式の設定ファイルをサポート（直接モデルリスト）
        models_data = yaml_data.get("models", [])
        if not models_data and isinstance(yaml_data, list):
            models_data = yaml_data
        
        # 新しい形式の設定ファイルをサポート（カテゴリ分け）
        if not models_data:
            # generative_modelsカテゴリがあるか確認
            models_data = yaml_data.get("generative_models", [])
        
        for model_data in models_data:
            if isinstance(model_data, dict):
                name = model_data.get("name", "")
                description = model_data.get("description", "")
                if name:
                    models_list.append(ModelInfo(name, description))
            elif isinstance(model_data, str):
                # 単純な文字列の場合
                models_list.append(ModelInfo(model_data))
        
        return models_list
    
    except Exception as e:
        print(f"モデル設定の読み込みに失敗しました: {e}")
        return []


def get_model_names() -> List[str]:
    """
    利用可能なモデル名のリストを取得
    
    Returns:
        List[str]: モデル名のリスト
    """
    return [model.name for model in load_models()]


def get_default_model() -> Optional[str]:
    """
    デフォルトのモデル名を取得
    
    Returns:
        Optional[str]: デフォルトモデル名。モデルが見つからない場合はNone。
    """
    models = load_models()
    if models:
        return models[0].name
    return None


if __name__ == "__main__":
    # このファイルを直接実行した場合、モデル一覧をテスト表示
    models = load_models()
    if models:
        print(f"利用可能なモデル ({len(models)}):")
        for i, model in enumerate(models, 1):
            print(f"{i}. {model}")
    else:
        print("利用可能なモデルが見つかりませんでした。") 