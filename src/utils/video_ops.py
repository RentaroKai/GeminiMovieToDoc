"""
動画操作ユーティリティ
- FFmpegを使用した動画圧縮
"""

import shutil
import subprocess
from pathlib import Path
from typing import Optional, Callable, Union

from src.utils.logger import app_logger as logger

# CRF のデフォルト値（内部固定）
DEFAULT_CRF_START = 28
DEFAULT_CRF_STEP = 2
DEFAULT_CRF_MAX = 34

class FFmpegNotFoundError(Exception):
    """FFmpegが見つからない場合に発生する例外"""
    pass

def compress_video_to_target(
        input_path: Union[str, Path],
        target_size_mb: int,
        logger=logger,
        progress_cb: Optional[Callable[[str, int], None]] = None
) -> Optional[Path]:
    """
    target_size_mb を下回るまで FFmpeg で再エンコードする。
    - CRF を上げながら反復 (内部固定値: 開始={DEFAULT_CRF_START}, ステップ={DEFAULT_CRF_STEP}, 上限={DEFAULT_CRF_MAX})。
    - FFmpeg が見つからない場合、警告ログを出力して None を返す。
    - 上限 CRF でもサイズを超過する場合は失敗として例外 (RuntimeError)。

    Args:
        input_path: 入力動画ファイルのパス
        target_size_mb: 目標サイズ (MB)
        logger: ロガー
        progress_cb: 進捗コールバック関数 (メッセージ, 進捗率)

    Returns:
        圧縮後ファイルのパス（Path オブジェクト）。
        すでに条件を満たす場合は元の Path をそのまま返す。
        FFmpeg が見つからない場合は None を返す。
        
    Raises:
        RuntimeError: 圧縮が失敗した場合 (CRF上限到達など)。
        FileNotFoundError: 入力ファイルが見つからない場合。
    """
    input_path = Path(input_path)
    if not input_path.is_file():
        raise FileNotFoundError(f"入力ファイルが見つかりません: {input_path}")

    # FFmpeg の存在確認
    if not shutil.which("ffmpeg"):
        logger.warning("FFmpeg が見つかりません。PATH 環境変数を確認してください。動画圧縮はスキップされます。")
        return None

    # 現在のファイルサイズをチェック
    current_size_mb = input_path.stat().st_size / (1024 * 1024)
    
    # すでにターゲットサイズより小さい場合は処理不要
    if current_size_mb <= target_size_mb:
        logger.info(f"ファイルサイズは既に目標以下です: {current_size_mb:.2f}MB / {target_size_mb}MB")
        return input_path

    # 進捗通知
    if progress_cb:
        progress_cb(f"動画圧縮を開始します: {current_size_mb:.2f}MB → {target_size_mb}MB", 5)
    
    logger.info(f"動画圧縮開始: {input_path} ({current_size_mb:.2f}MB → {target_size_mb}MB)")

    # 一時出力ファイルのパスを作成
    output_stem = f"{input_path.stem}_compressed"
    output_path = input_path.with_stem(output_stem)
    
    # すでに同名ファイルが存在する場合は連番を付与
    counter = 1
    while output_path.exists():
        output_path = input_path.with_stem(f"{output_stem}_{counter}")
        counter += 1

    # CRF値を変えながら圧縮を試行
    crf = DEFAULT_CRF_START
    success = False
    
    while crf <= DEFAULT_CRF_MAX:
        if progress_cb:
            progress_cb(f"CRF {crf} で圧縮中...", 10 + (crf - DEFAULT_CRF_START) * 10)
        
        logger.info(f"CRF {crf} での圧縮を試行中...")
        
        # 前回の出力ファイルが存在する場合は削除
        if output_path.exists():
            output_path.unlink()
        
        # FFmpegコマンドを構築
        cmd = [
            "ffmpeg", "-y",
            "-i", str(input_path),
            "-vcodec", "libx264",
            "-crf", str(crf),
            "-preset", "medium",
            "-movflags", "+faststart",
            "-acodec", "aac",
            "-b:a", "128k",
            str(output_path)
        ]
        
        try:
            # FFmpegを実行
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=False  # エラーで例外を発生させない
            )
            
            # エラー時はログに出力して次のCRFへ
            if result.returncode != 0:
                logger.error(f"FFmpeg実行エラー (CRF {crf}): {result.stderr}")
                crf += DEFAULT_CRF_STEP
                continue
            
            # 出力ファイルが存在するか確認
            if not output_path.exists():
                logger.error(f"FFmpegが出力ファイルを生成しませんでした (CRF {crf})")
                crf += DEFAULT_CRF_STEP
                continue
            
            # サイズ確認
            output_size_mb = output_path.stat().st_size / (1024 * 1024)
            logger.info(f"圧縮結果 (CRF {crf}): {output_size_mb:.2f}MB")
            
            if output_size_mb <= target_size_mb:
                # 目標達成
                logger.info(f"目標サイズ達成: {output_size_mb:.2f}MB / {target_size_mb}MB (CRF {crf})")
                success = True
                break
            
            # 目標未達成の場合はCRFを上げて再試行
            logger.info(f"目標サイズ未達: {output_size_mb:.2f}MB > {target_size_mb}MB, CRFを {crf+DEFAULT_CRF_STEP} に上げて再試行")
            crf += DEFAULT_CRF_STEP
            
        except Exception as e:
            logger.error(f"FFmpeg実行中に例外が発生 (CRF {crf}): {e}", exc_info=True)
            # 出力ファイルを削除して次のCRFへ
            if output_path.exists():
                output_path.unlink()
            crf += DEFAULT_CRF_STEP

    # 圧縮結果の処理
    if success:
        if progress_cb:
            progress_cb("圧縮完了", 50)
        return output_path
    else:
        # 最後の出力ファイルを削除
        if output_path.exists():
            output_path.unlink()
        raise RuntimeError(f"最大CRF ({DEFAULT_CRF_MAX}) でも目標サイズ ({target_size_mb}MB) を達成できませんでした") 