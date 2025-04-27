"""
ファイル操作ユーティリティ
- ファイルサイズチェック
- 出力ファイル命名・保存
"""

import os
import datetime
import codecs
import re
from pathlib import Path
from typing import Optional, Union, BinaryIO

from src.utils.logger import app_logger as logger


def check_file_size(file_path: Union[str, Path], max_size_mb: int = 100) -> bool:
    """
    ファイルサイズが指定の上限以下かチェック
    
    Args:
        file_path: チェックするファイルのパス
        max_size_mb: 許容される最大サイズ（MB）
        
    Returns:
        bool: ファイルサイズが上限以下ならTrue
    """
    try:
        file_path = Path(file_path)
        if not file_path.exists():
            logger.error(f"ファイルが存在しません: {file_path}")
            return False
        
        # ファイルサイズを取得 (bytes)
        file_size = file_path.stat().st_size
        
        # MB単位に変換
        file_size_mb = file_size / (1024 * 1024)
        
        # サイズチェック
        if file_size_mb <= max_size_mb:
            logger.debug(f"ファイルサイズOK: {file_path.name} ({file_size_mb:.2f}MB / {max_size_mb}MB)")
            return True
        else:
            logger.warning(f"ファイルサイズ超過: {file_path.name} ({file_size_mb:.2f}MB > {max_size_mb}MB)")
            return False
    
    except Exception as e:
        logger.error(f"ファイルサイズチェック中にエラー: {e}")
        return False


def sanitize_filename(name: str) -> str:
    """
    ファイル名として不適切な文字を置換し、整形する。

    Args:
        name: 整形前のファイル名候補

    Returns:
        str: 整形後のファイル名
    """
    # Windowsで禁止されている文字をアンダースコアに置換
    name = re.sub(r'[\\/:*?"<>|]', '_', name)
    # 先頭と末尾の空白文字を削除
    name = name.strip()
    # 連続するアンダースコアを1つにまとめる
    name = re.sub(r'_+', '_', name)
    # ファイル名の先頭や末尾がアンダースコアなら削除
    name = name.strip('_')
    # 空になった場合はデフォルト名を返す
    if not name:
        name = "untitled"
    return name


def default_output_filename(output_dir: Path, ext: str = ".md") -> Path:
    """
    フォールバック用のデフォルト出力ファイル名を生成する。
    衝突を避けるために連番を付与する。

    Args:
        output_dir: 出力ディレクトリ
        ext: 拡張子 (例: ".md")

    Returns:
        Path: 生成されたデフォルトファイルパス
    """
    base_name = datetime.datetime.now().strftime("%Y%m%d") + "_analysis_result"
    output_path = output_dir / f"{base_name}{ext}"
    counter = 1
    while output_path.exists():
        output_path = output_dir / f"{base_name}_{counter}{ext}"
        counter += 1
    return output_path


def get_output_filename(video_path: Union[str, Path], output_dir: Optional[Path] = None) -> Path:
    """
    出力ファイル名を生成
    
    Args:
        video_path: 元動画ファイルのパス
        output_dir: 出力ディレクトリ (指定がなければプロジェクトルートの 'output')
        
    Returns:
        Path: 生成された出力ファイルパス (タイムスタンプ付き)
    """
    # パスオブジェクトに変換
    video_path = Path(video_path)
    
    # 出力ディレクトリの確認
    if output_dir is None:
        output_dir = Path(__file__).parent.parent.parent / "output"
    
    # ディレクトリが存在しなければ作成
    output_dir.mkdir(exist_ok=True)
    
    # タイムスタンプ
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # 元のファイル名から拡張子を除いた部分を取得
    video_name = video_path.stem
    
    # 出力ファイル名を生成 (timestamp_videoname.txt)
    output_filename = f"{timestamp}_{video_name}.txt"
    
    return output_dir / output_filename


def save_text_output(text: str, output_path: Union[str, Path], use_bom: bool = True) -> bool:
    """
    テキスト出力を保存
    
    Args:
        text: 保存するテキスト
        output_path: 出力ファイルパス
        use_bom: UTF-8 with BOMを使用するか (Windowsでの文字化け防止)
        
    Returns:
        bool: 保存成功時True
    """
    try:
        output_path = Path(output_path)
        
        # 親ディレクトリが存在しなければ作成
        output_path.parent.mkdir(exist_ok=True)
        
        # エンコーディング指定
        encoding = "utf-8-sig" if use_bom else "utf-8"
        
        # ファイル書き込み
        with open(output_path, "w", encoding=encoding) as f:
            f.write(text)
        
        logger.info(f"結果をファイルに保存しました: {output_path}")
        return True
    
    except Exception as e:
        logger.error(f"ファイル保存中にエラー: {e}")
        return False


def is_valid_mp4(file_path: Union[str, Path]) -> bool:
    """
    有効なMP4ファイルかをチェック
    
    Args:
        file_path: チェックするファイルのパス
        
    Returns:
        bool: 有効なMP4の場合True
    """
    try:
        path = Path(file_path)
        
        # 1. ファイルが存在するか
        if not path.exists() or not path.is_file():
            logger.warning(f"ファイルが存在しないか、通常ファイルではありません: {path}")
            return False
        
        # 2. 拡張子がMP4か (.mp4 または .MP4)
        if path.suffix.lower() != ".mp4":
            logger.warning(f"MP4ファイルではありません: {path} (拡張子: {path.suffix})")
            return False
        
        # 3. ファイルサイズが0より大きいか
        if path.stat().st_size <= 0:
            logger.warning(f"ファイルサイズが0です: {path}")
            return False
        
        # 4. ファイルがアクセス可能か (読み込みテスト)
        try:
            with open(path, "rb") as f:
                # MP4ファイルのマジックバイトをチェック（通常は "ftyp"がヘッダ近くに含まれる）
                header = f.read(20)  # 最初の20バイトを読み込み
                if b"ftyp" not in header:
                    logger.warning(f"MP4形式ではないファイルです: {path}")
                    return False
        except IOError as e:
            logger.error(f"ファイルアクセスエラー: {path} - {e}")
            return False
        
        return True
    
    except Exception as e:
        logger.error(f"MP4ファイル検証中にエラー: {e}")
        return False


if __name__ == "__main__":
    # このファイルを直接実行した場合、テスト動作
    import sys
    
    # コマンドライン引数でファイルパスを受け取る
    if len(sys.argv) > 1:
        test_file = sys.argv[1]
        print(f"テストするファイル: {test_file}")
        
        # MP4チェック
        is_mp4 = is_valid_mp4(test_file)
        print(f"有効なMP4: {is_mp4}")
        
        # サイズチェック
        size_ok = check_file_size(test_file, 100)
        print(f"サイズOK: {size_ok}")
        
        # 出力パス生成
        output_path = get_output_filename(test_file)
        print(f"出力パス: {output_path}")
    else:
        print("使用法: python file_ops.py <テストするファイルパス>") 