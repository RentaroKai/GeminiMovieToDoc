# Gemini Movie Analyzer

議事録君が遅くてだるいので文字起こししなくていい場合はこっちで簡易に議事録まとめを作れるようにした。  
ただのgemini動画解析ラッパーなのでplaygroundが使える環境であれば不要。

## 主な機能

*   MP4 動画ファイルのドラッグ＆ドロップによる追加。
*   カスタムプロンプトの入力、またはテンプレート（将来実装予定）を使用した分析。
*   Gemini API を介した動画分析 (ファイルアップロードとコンテンツ生成)。
    *   **自動動画圧縮:** アップロードする動画ファイルがAPIの最大サイズ制限を超えている場合、システムに `ffmpeg` へのパスが通っていれば、自動的に動画の圧縮を試みます。(圧縮設定は `config/settings.json` で調整可能です。)
*   分析結果を `output/` ディレクトリにテキストファイルとして保存。
*   ログの記録 (`logs/` ディレクトリ): アプリケーションの動作ログを記録。

## セットアップ

1.  **リポジトリのクローン:**
    ```bash
    git clone <リポジトリURL>
    cd GeminiMovieToDoc2
    ```
2.  **仮想環境の作成 (推奨):**
    ```bash
    python -m venv .venv
    # Windows コマンドプロンプトの場合:
    .venv\Scripts\activate
    # Git Bash / Linux / macOS の場合:
    # source .venv/bin/activate
    ```
3.  **依存関係のインストール:**
    ```bash
    pip install -r requirements.txt
    ```
4.  **APIキーの設定:**
    *   Google Gemini API キーを環境変数 `GEMINI_API_KEY` に設定してください。
    *   **注意:** APIキーは安全に管理してください。 `.env` ファイルは使用しません。

5.  **アプリケーションの実行:**
    ```bash
    python run_app.py
    ```

## ビルド (実行ファイル作成)

単一の実行ファイルを作成する場合は、以下のコマンドを実行します。

```bash
pyinstaller --onefile --windowed --icon=icon.ico run_app.py
# コンソールを表示したい場合 (デバッグ用):
# pyinstaller --onefile --icon=icon.ico run_app.py
```
作成された実行ファイルは `dist` フォルダ内に格納されます。

