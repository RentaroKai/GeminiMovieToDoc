"""
Gemini API を使用して、解析結果テキストからファイル名を生成するモジュール
"""

import json
import re
from typing import Optional

from src.backend.gemini_client import GeminiClient
from src.utils.logger import app_logger as logger

# Geminiに投げるプロンプトテンプレート
# デフォルトモデル gemini-2.5-flash-preview-04-17 を想定
TITLE_GENERATION_PROMPT = """
以下のテキスト内容を要約し、ファイル名として適切な短いタイトルを日本語で生成してください。
タイトルには記号や特殊文字を含めず、JSON形式 ({{\"title\": \"生成されたタイトル\"}}) で返してください。

{analysis_text}
"""

# 解析テキストの最大文字数 (トークン数ではなく単純な文字数)
MAX_TEXT_LENGTH = 4000

def request_title(text: str, client: GeminiClient) -> Optional[str]:
    """
    解析結果テキストを基に、Gemini API を呼び出してタイトルを生成する。

    Args:
        text: 解析結果のテキスト。
        client: 初期化済みの GeminiClient インスタンス。

    Returns:
        生成されたタイトル文字列。失敗した場合は None。
    """
    if not text:
        logger.warning("タイトル生成のためのテキストが空です。")
        return None

    # テキストが長すぎる場合は切り詰める
    truncated_text = text[:MAX_TEXT_LENGTH]
    if len(text) > MAX_TEXT_LENGTH:
        logger.debug(f"タイトル生成のため、テキストを{MAX_TEXT_LENGTH}文字に切り詰めました。")

    # プロンプトを作成
    prompt = TITLE_GENERATION_PROMPT.format(analysis_text=truncated_text)

    try:
        logger.info("Geminiにタイトル生成をリクエストします...")
        # generate_contentモード (非ストリーミング) で呼び出し
        # ストリーミングはFalseに設定 (タイトル生成は短い応答を期待するため)
        response = client.generate_content_mode(prompt=prompt, streaming=False)
        logger.debug(f"Geminiからの応答: {response}")

        if not response:
            logger.warning("Geminiから空の応答がありました。")
            return None

        # 応答からタイトルを抽出 (JSON形式を期待するが、柔軟に対応)
        title = None

        # 1. JSON形式での抽出を試みる
        try:
            # 応答文字列からJSON部分だけを抽出する試み (```json ... ``` を考慮)
            # DOTALLで複数行のマッチング、非貪欲マッチング .*? を使用
            json_match = re.search(r'```json\s*(\{.*?\})\s*```', response, re.DOTALL | re.IGNORECASE)
            json_str = response
            if json_match:
                json_str = json_match.group(1)
            
            # JSON文字列の前後の空白や改行を削除
            json_str = json_str.strip()
            
            data = json.loads(json_str)
            if isinstance(data, dict) and "title" in data and isinstance(data["title"], str):
                title = data["title"].strip()
                # タイトルが空文字列でないかも確認
                if title:
                    logger.info(f"JSONからタイトルを抽出しました: '{title}'")
                else:
                     logger.warning("JSONから抽出したタイトルが空でした。")
                     title = None # 空の場合は抽出失敗扱い
            else:
                logger.warning("JSON形式でしたが、'title'キーが見つからないか、値が文字列ではありませんでした。")

        except json.JSONDecodeError:
            logger.warning("応答はJSON形式ではありませんでした。正規表現での抽出を試みます。")
            # JSONデコード失敗時は何もしない (titleはNoneのまま)
            pass 

        # 2. JSONで抽出できなかった場合、正規表現で "title": "..." パターンを探す
        if not title:
            # 引用符の種類 (' または ") と空白文字に柔軟に対応
            # よりシンプルなパターンで試す
            match = re.search(r'"title"\s*:\s*"(.*?)"', response) # ダブルクォートのみ
            if not match:
                match = re.search(r"'title'\s*:\s*'(.*?)'", response) # シングルクォートのみ
            
            if match:
                title = match.group(1).strip()
                # 抽出したタイトルが空文字列でないか確認
                if title:
                     logger.info(f"正規表現でタイトルを抽出しました: '{title}'")
                else:
                     logger.warning("正規表現で抽出したタイトルが空でした。")
                     title = None # 空の場合は抽出失敗扱い

        # 3. それでも抽出できなかった場合、応答の最初の非空行をタイトル候補とする
        if not title:
            lines = response.strip().split('\n')
            first_meaningful_line = None
            for line in lines:
                stripped_line = line.strip()
                if stripped_line:
                    first_meaningful_line = stripped_line
                    break
            
            if first_meaningful_line:
                 # 50文字までに制限
                title = first_meaningful_line[:50]
                title = title.strip() # 念のため再度strip
                if title:
                    logger.warning(f"タイトル抽出に失敗。応答の最初の非空行を仮タイトルとします: '{title}'")
                else:
                    logger.warning("応答の最初の非空行も空でした。")
                    title = None # 結局空なら失敗
            else:
                logger.warning("応答全体が空または空白文字のみでした。")

        # 最終的に抽出したタイトルが空文字列でないことを確認
        if title:
            return title
        else:
            logger.warning("有効なタイトルを抽出できませんでした。")
            return None

    except Exception as e:
        logger.error(f"タイトル生成中に予期せぬエラーが発生しました: {e}", exc_info=True)
        return None 