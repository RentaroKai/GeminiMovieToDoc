import sys
import os

"""
メインウィンドウ - アプリケーションのUI実装
"""

import os
from pathlib import Path
from typing import Optional, List, Dict, Any

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QTextEdit, QComboBox, QLineEdit, QFileDialog,
    QProgressBar, QTabWidget, QMessageBox, QSplitter, QFrame,
    QListWidget, QListWidgetItem, QCheckBox, QGroupBox, QToolButton
)
from PySide6.QtCore import Qt, QUrl, Signal, QSize, QMimeData
from PySide6.QtGui import QDragEnterEvent, QDropEvent, QIcon

from src.utils.logger import app_logger as logger, get_gui_logs
from src.utils.file_ops import is_valid_mp4, check_file_size
from src.config.models_loader import load_models, get_model_names, get_default_model
from src.config.settings import settings, load_settings, save_settings
from src.backend.worker import GeminiWorker


class DropArea(QLabel):
    """
    ファイルドロップ用エリア
    """
    file_dropped = Signal(str)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setText("MP4ファイルをここにドラッグ＆ドロップ")
        self.setStyleSheet("""
            QLabel {
                border: 2px dashed #aaa;
                border-radius: 5px;
                padding: 20px;
                background-color: #f8f8f8;
                color: #333; /* 文字色を明示的に指定 */
                font-size: 16px;
                min-height: 100px;
            }
            QLabel:hover {
                border-color: #3498db;
                background-color: #ecf0f1;
            }
            /* ドラッグ中のスタイル */
            QLabel[acceptDrops="true"]:hover {
                border-color: #2980b9;
                background-color: #e0e0e0; /* 背景色をグレーに */
                color: #000; /* 文字色を黒に */
            }
        """)
        self.setAcceptDrops(True)
        self._is_dragging = False # ドラッグ状態を追跡するフラグ
    
    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        """ドラッグイベント開始時のハンドラ"""
        # URLを受け入れる
        if event.mimeData().hasUrls():
            self._is_dragging = True
            self.update() # スタイル再適用のため更新
            event.acceptProposedAction()
    
    def dragLeaveEvent(self, event) -> None:
        """ドラッグがエリア外に出たときのハンドラ"""
        self._is_dragging = False
        self.update() # スタイル再適用のため更新
        super().dragLeaveEvent(event)
    
    def dropEvent(self, event: QDropEvent) -> None:
        """ドロップイベント時のハンドラ"""
        self._is_dragging = False
        self.update() # スタイル再適用のため更新
        # ファイルURLsを取得
        urls = event.mimeData().urls()
        if urls:
            # 最初のURLをファイルパスとして取得
            file_path = urls[0].toLocalFile()
            self.file_dropped.emit(file_path)
    
    # スタイルシート更新のためにプロパティを追加
    def isDragging(self) -> bool:
        return self._is_dragging
    
    # isDragging プロパティをQtに通知
    isDraggingChanged = Signal()
    
    # プロパティの定義 (Python 3.9+ スタイル)
    @property
    def isDraggingProp(self) -> bool:
        return self.isDragging()
    
    @isDraggingProp.setter
    def isDraggingProp(self, value: bool):
        if self._is_dragging != value:
            self._is_dragging = value
            self.isDraggingChanged.emit()


class LogDisplay(QListWidget):
    """
    ログ表示ウィジェット
    """
    def __init__(self, parent=None, log_level=None):
        super().__init__(parent)
        self.log_level = log_level
        self.setAlternatingRowColors(True)
        self.setWordWrap(True)
        self.update_logs()
    
    def update_logs(self):
        """ログをUIに反映"""
        self.clear()
        logs = get_gui_logs(level=self.log_level)
        for log in logs:
            item = QListWidgetItem(f"{log['time']} [{log['level']}] {log['message']}")
            # ログレベルによって色を変える
            if log['level'] == 'ERROR':
                item.setForeground(Qt.GlobalColor.red)
            elif log['level'] == 'WARNING':
                item.setForeground(Qt.GlobalColor.darkYellow)
            self.addItem(item)
        
        # 最新のログまでスクロール
        if self.count() > 0:
            self.scrollToBottom()


class MainWindow(QMainWindow):
    """
    アプリケーションのメインウィンドウ
    """
    def __init__(self):
        super().__init__()
        
        # アプリケーション設定の読み込み
        self.settings = load_settings()
        
        # 実際のAPIキーを内部で保持（UIのマスク表示と分離）
        self._actual_api_key = self.settings.gemini.api_key or ""
        # 小/大モード切替フラグ（初期は小モード）
        self._is_small_mode = True
        
        # Largeモード用UIを生成（中央ウィジェットは後で設定）
        self.init_ui()
        # Smallモード用UIを生成
        self.build_small_frame()
        # Small/Large UIをまとめるコンテナを設定
        container = QWidget()
        container_layout = QVBoxLayout(container)
        container_layout.addWidget(self.small_frame)
        container_layout.addWidget(self.large_frame)
        self.setCentralWidget(container)
        # 初期状態は小モード（small_frameのみ表示）
        self.large_frame.hide()
        self.adjustSize()
        
        # ワーカーの初期化
        self.worker = GeminiWorker()
        self.connect_worker_signals()
        
        # ファイルリスト
        self.video_files = []
        
        # Markdownバッファ (ストリーミング用)
        self._md_buffer = ""
        
        # アプリケーション情報
        self.setWindowTitle("Gemini Movie Analyzer")
        #self.setWindowIcon(QIcon("path/to/icon.png"))  # アイコン設定（必要に応じて）
        # (サイズはモード切替時に自動設定)
        
        # 起動時に「①議事録作成」を選択状態にして明示的にシグナル発火
        self.template_combo.setCurrentIndex(0)
        # 明示的に議事録テンプレート選択を実行（シグナルが発火しない場合のため）
        self.on_template_selected(0)
    
    def init_ui(self):
        """UIコンポーネントの初期化"""
        main_widget = QWidget()
        # Largeモード用フレームとして保持（中央ウィジェットは外で設定）
        self.large_frame = main_widget
        main_layout = QVBoxLayout(main_widget)
        
        # 折りたたみ用の矢印ボタンを大モード内に配置
        header_layout = QHBoxLayout()
        header_layout.addStretch()
        self.collapse_button = QToolButton()
        self.collapse_button.setArrowType(Qt.ArrowType.UpArrow)
        self.collapse_button.setToolTip("簡易表示に縮小")
        self.collapse_button.clicked.connect(self.toggle_mode)
        header_layout.addWidget(self.collapse_button)
        main_layout.addLayout(header_layout)
        
        # 上部と下部に分割
        splitter = QSplitter(Qt.Orientation.Vertical)
        main_layout.addWidget(splitter)
        
        # 上部: 入力エリア
        top_widget = QWidget()
        top_layout = QVBoxLayout(top_widget)
        
        # ドロップエリアとファイルリスト
        drop_file_layout = QHBoxLayout()
        
        # ファイルドロップエリア
        self.drop_area = DropArea()
        self.drop_area.file_dropped.connect(self.on_file_dropped)
        drop_file_layout.addWidget(self.drop_area, 2)
        
        # ファイル選択ボタン
        file_select_layout = QVBoxLayout()
        self.select_file_btn = QPushButton("ファイル選択...")
        self.select_file_btn.clicked.connect(self.on_select_file)
        file_select_layout.addWidget(self.select_file_btn)
        
        # ファイルリスト
        self.file_list = QListWidget()
        file_select_layout.addWidget(QLabel("選択したファイル:"))
        file_select_layout.addWidget(self.file_list)
        
        # クリアボタン
        self.clear_file_btn = QPushButton("クリア")
        self.clear_file_btn.clicked.connect(self.on_clear_file)
        file_select_layout.addWidget(self.clear_file_btn)
        
        drop_file_layout.addLayout(file_select_layout, 1)
        top_layout.addLayout(drop_file_layout)
        
        # プロンプト入力エリア
        prompt_layout = QVBoxLayout()
        prompt_layout.addWidget(QLabel("解析プロンプト:"))
        
        # プロンプトツールバー
        prompt_toolbar = QHBoxLayout()
        
        # テンプレートプルダウン
        prompt_toolbar.addWidget(QLabel("テンプレート:"))
        self.template_combo = QComboBox()
        self.template_combo.addItem("①議事録作成")
        self.template_combo.addItem("②カスタムプロンプト")
        self.template_combo.addItem("③汎用動画解析")
        self.template_combo.addItem("④シーン検出と詳細説明")
        self.template_combo.addItem("⑤技術的な解析")
        self.template_combo.currentIndexChanged.connect(self.on_template_selected)
        prompt_toolbar.addWidget(self.template_combo)
        
        # プロンプトクリアボタン
        self.clear_prompt_btn = QPushButton("クリア")
        self.clear_prompt_btn.clicked.connect(self.on_clear_prompt)
        prompt_toolbar.addWidget(self.clear_prompt_btn)
        
        prompt_toolbar.addStretch(1)
        prompt_layout.addLayout(prompt_toolbar)
        
        # プロンプトテキストエディタ
        self.prompt_edit = QTextEdit()
        # デフォルトのプレースホルダーを設定
        self._default_placeholder = "プロンプトを入力または上からテンプレートを選択してください。例: 「この動画について詳しく解析し、主な登場人物、会話内容、重要な場面を説明してください。」"
        self.prompt_edit.setPlaceholderText(self._default_placeholder)
        # ここでの last_prompt の復元は不要。__init__ の最後で setCurrentIndex(0) することで対応
        # if self.settings.ui.last_prompt:
        #     self.prompt_edit.setText(self.settings.ui.last_prompt)
        prompt_layout.addWidget(self.prompt_edit)
        
        top_layout.addLayout(prompt_layout)
        
        # APIキーと設定エリア
        api_settings_layout = QHBoxLayout()
        
        # APIキー入力
        api_key_layout = QVBoxLayout()
        api_key_layout.addWidget(QLabel("Gemini API キー:"))
        self.api_key_input = QLineEdit()
        self.api_key_input.setPlaceholderText("環境変数 GEMINI_API_KEY または GOOGLE_API_KEY から自動取得")
        if self._actual_api_key:
            # APIキーが存在する場合、マスキングして表示
            self.api_key_input.setText("*" * len(self._actual_api_key) if len(self._actual_api_key) > 0 else "")
            self.api_key_input.setEchoMode(QLineEdit.EchoMode.Password) # 入力時も隠す
        else:
            # APIキーが存在しない場合、通常表示
            self.api_key_input.setEchoMode(QLineEdit.EchoMode.Normal)
        # テキスト変更時の処理を追加
        self.api_key_input.textChanged.connect(self._on_api_key_changed)
        api_key_layout.addWidget(self.api_key_input)
        api_settings_layout.addLayout(api_key_layout, 2)
        
        # モデル選択
        model_layout = QVBoxLayout()
        model_layout.addWidget(QLabel("Gemini モデル:"))
        self.model_combo = QComboBox()
        # モデルリストを読み込み
        for model_name in get_model_names():
            self.model_combo.addItem(model_name)
        # 前回選択したモデルを復元
        model_index = self.model_combo.findText(self.settings.gemini.model_name)
        if model_index >= 0:
            self.model_combo.setCurrentIndex(model_index)
        model_layout.addWidget(self.model_combo)
        api_settings_layout.addLayout(model_layout, 1)
        
        # API連携モード選択
        mode_layout = QVBoxLayout()
        mode_layout.addWidget(QLabel("API連携モード:"))
        self.mode_combo = QComboBox()
        self.mode_combo.addItem("generate_content", "generate_content")
        self.mode_combo.addItem("チャットセッション", "chat")
        # 前回選択したモードを復元
        mode_index = 0 if self.settings.gemini.mode == "generate_content" else 1
        self.mode_combo.setCurrentIndex(mode_index)
        mode_layout.addWidget(self.mode_combo)
        api_settings_layout.addLayout(mode_layout, 1)
        
        # ストリーミングオプション
        streaming_layout = QVBoxLayout()
        streaming_layout.addWidget(QLabel("応答受信:"))
        self.streaming_check = QCheckBox("ストリーミング")
        self.streaming_check.setChecked(self.settings.gemini.stream_response)
        streaming_layout.addWidget(self.streaming_check)
        api_settings_layout.addLayout(streaming_layout, 1)
        
        top_layout.addLayout(api_settings_layout)
        
        # 実行ボタンと進捗バー
        exec_layout = QHBoxLayout()
        self.analyze_btn = QPushButton("動画を解析")
        self.analyze_btn.clicked.connect(self.on_analyze)
        self.analyze_btn.setStyleSheet("""
            QPushButton {
                background-color: #2980b9;
                color: white;
                padding: 8px;
                font-weight: bold;
                border-radius: 4px;
                min-height: 30px;
            }
            QPushButton:hover {
                background-color: #3498db;
            }
            QPushButton:disabled {
                background-color: #95a5a6;
            }
        """)
        exec_layout.addWidget(self.analyze_btn)
        
        # 進捗バー
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        exec_layout.addWidget(self.progress_bar, 2)
        
        # 状態表示ラベル
        self.status_label = QLabel("準備完了")
        exec_layout.addWidget(self.status_label)
        
        top_layout.addLayout(exec_layout)
        
        # 上部ウィジェットを追加
        splitter.addWidget(top_widget)
        
        # 下部: 結果表示エリア
        bottom_widget = QTabWidget()
        
        # 結果表示タブ
        self.result_text = QTextEdit()
        self.result_text.setReadOnly(True)
        bottom_widget.addTab(self.result_text, "解析結果")
        
        # ログタブ
        self.log_list = LogDisplay()
        bottom_widget.addTab(self.log_list, "ログ")
        
        # 設定タブ
        settings_tab = QWidget()
        settings_layout = QVBoxLayout(settings_tab)
        
        # 出力設定
        output_group = QGroupBox("出力設定")
        output_layout = QVBoxLayout(output_group)
        
        # 出力ディレクトリ
        output_dir_layout = QHBoxLayout()
        output_dir_layout.addWidget(QLabel("出力ディレクトリ:"))
        self.output_dir_edit = QLineEdit(str(self.settings.file.output_directory))
        output_dir_layout.addWidget(self.output_dir_edit, 2)
        self.browse_dir_btn = QPushButton("参照...")
        self.browse_dir_btn.clicked.connect(self.on_browse_output_dir)
        output_dir_layout.addWidget(self.browse_dir_btn)
        output_layout.addLayout(output_dir_layout)
        
        # BOM設定
        bom_layout = QHBoxLayout()
        bom_layout.addWidget(QLabel("エンコーディング:"))
        self.bom_check = QCheckBox("UTF-8 with BOM (Windows互換)")
        self.bom_check.setChecked(self.settings.file.use_bom)
        bom_layout.addWidget(self.bom_check)
        bom_layout.addStretch(1)
        output_layout.addLayout(bom_layout)
        
        # ファイルサイズ制限
        file_size_layout = QHBoxLayout()
        file_size_layout.addWidget(QLabel("最大ファイルサイズ (MB):"))
        self.file_size_edit = QLineEdit(str(self.settings.file.max_file_size_mb))
        self.file_size_edit.setMaximumWidth(100)
        file_size_layout.addWidget(self.file_size_edit)
        file_size_layout.addStretch(1)
        output_layout.addLayout(file_size_layout)
        
        settings_layout.addWidget(output_group)
        
        # 入力設定
        input_group = QGroupBox("入力設定")
        input_layout = QVBoxLayout(input_group)
        input_dir_layout = QHBoxLayout()
        input_dir_layout.addWidget(QLabel("ファイル選択時のフォルダ:"))
        self.input_dir_edit = QLineEdit(str(self.settings.file.input_directory))
        input_dir_layout.addWidget(self.input_dir_edit, 2)
        self.browse_input_btn = QPushButton("参照...")
        self.browse_input_btn.clicked.connect(self.on_browse_input_dir)
        input_dir_layout.addWidget(self.browse_input_btn)
        input_layout.addLayout(input_dir_layout)
        settings_layout.addWidget(input_group)
        
        # 設定保存ボタン
        save_settings_btn = QPushButton("設定を保存")
        save_settings_btn.clicked.connect(self.on_save_settings)
        settings_layout.addWidget(save_settings_btn)
        
        settings_layout.addStretch(1)
        
        # 設定タブを追加
        bottom_widget.addTab(settings_tab, "設定")
        
        # 下部ウィジェットを追加
        splitter.addWidget(bottom_widget)
        
        # スプリッターの初期サイズ比率を設定
        splitter.setSizes([400, 300])
    
    def _on_api_key_changed(self):
        """APIキー入力欄が変更されたときの処理"""
        # ユーザーが入力したテキストを取得
        text = self.api_key_input.text()
        
        # 現在のテキストがマスク（*のみ）でない場合は、実際のAPIキーを更新
        if text and not all(c == '*' for c in text):
            self._actual_api_key = text
    
    def connect_worker_signals(self):
        """ワーカースレッドのシグナルを接続"""
        self.worker.progress_update.connect(self.on_progress_update)
        self.worker.status_update.connect(self.on_status_update)
        self.worker.error.connect(self.on_worker_error)
        self.worker.result_ready.connect(self.on_result_ready)
        self.worker.stream_chunk.connect(self.on_stream_chunk)
        self.worker.complete.connect(self.on_worker_complete)
    
    def on_file_dropped(self, file_path: str):
        """ファイルがドロップされたときの処理"""
        logger.debug(f"ファイルドロップ: {file_path}")
        
        # MP4ファイルかチェック
        if not is_valid_mp4(file_path):
            QMessageBox.warning(self, "エラー", f"対応していないファイル形式です: {file_path}\n\n※MP4形式の動画ファイルのみ対応しています")
            return
        
        # 既に追加済みならスキップ
        if file_path in self.video_files:
            logger.debug(f"既に追加済みのファイル: {file_path}")
            return
        
        # ファイルリストに追加
        self.video_files.append(file_path)
        self.file_list.addItem(Path(file_path).name)
        
        # 小モード用: 選択ファイル名を更新
        if hasattr(self, 'small_file_label'):
            self.small_file_label.setText(Path(file_path).name)
        
        # UI状態更新
        self.update_ui_state()
    
    def on_select_file(self):
        """ファイル選択ボタンクリック時の処理"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "MP4ファイルを選択", str(self.settings.file.input_directory), "MP4ファイル (*.mp4)"
        )
        
        if file_path:
            self.on_file_dropped(file_path)
    
    def on_clear_file(self):
        """ファイルクリアボタンクリック時の処理"""
        self.video_files = []
        self.file_list.clear()
        self.update_ui_state()
        
        # 小モード用: ファイル表示リセット
        if hasattr(self, 'small_file_label'):
            self.small_file_label.setText("ファイル: 未選択")
    
    def on_template_selected(self, index: int):
        """テンプレートが選択されたときの処理"""
        # ログ追加: 選択されたインデックスとテキストを確認
        logger.debug(f"Template selected - index: {index}, text: {self.template_combo.itemText(index)}")
        
        # まずデフォルトのプレースホルダーに戻す
        self.prompt_edit.setPlaceholderText(self._default_placeholder)
        
        if index == 0: # ①議事録作成
            meeting_minutes_prompt = """\
あなたは優秀な議事録作成者です。以下の会話データから、正確で簡潔な議事録をマークダウン形式で作成してください。

作成時の重要なポイント：
1. 形式的な要素
- 箇条書きを適切に使用し、議題ごとに整理
- 以下の3セクションで構成：
  - 議題と議論内容
  - 決定事項
  - アクションアイテム

2. 内容面での注意点
- 重要な議論のポイントを簡潔に記載
- 担当者が決まった事項は、担当者名を明確に記載
- 曖昧な表現は避け、具体的な表現に変換

3. 出力形式
## 議題と議論内容
- 各議題の要点を箇条書きで記載

## 決定事項
- 会議で合意された内容を箇条書きで記載
- 決定に至った理由や背景も簡潔に記載（必要な場合）

## アクションアイテム
- タスク内容
- 担当者
- 期限（設定されている場合）

不明確な情報は「**要確認**」と太字で明記してください。
"""
            self.prompt_edit.setText(meeting_minutes_prompt)
        elif index == 1: # ②カスタムプロンプト
            # 保存されているカスタムプロンプトを読み込む
            custom_prompt = self.settings.ui.custom_prompt
            if custom_prompt:
                self.prompt_edit.setText(custom_prompt)
            else:
                # 空の場合はクリアし、専用のプレースホルダーを設定
                self.prompt_edit.clear()
                self.prompt_edit.setPlaceholderText("カスタムプロンプトを入力してください")
        else:
            # インデックス 2 以降のテンプレート
            templates = {
                2: "この動画の内容を詳しく解析してください。映像に何が映っているか、重要なシーンや出来事、登場人物、話の流れなどを説明してください。動画の主要なメッセージや目的も特定してください。", # ③汎用動画解析
                3: "この動画を細かく解析し、異なるシーンごとに時間経過に沿って説明してください。各シーンで何が起こっているか、特筆すべき視覚的要素、音声要素、重要な会話や行動を詳細に記述してください。", # ④シーン検出と詳細説明
                4: "この動画の技術的な側面を解析してください。撮影技法、カメラワーク、編集スタイル、特殊効果、照明、音響設計などについて専門的な観点から評価してください。使用されている機材や技術についても推測できる限り言及してください。" # ⑤技術的な解析
            }
            if index in templates:
                self.prompt_edit.setText(templates[index])
    
    def on_clear_prompt(self):
        """プロンプトクリアボタンクリック時の処理"""
        # テキストエリアをクリア
        self.prompt_edit.clear()
        # 保存されているカスタムプロンプトもリセット
        self.settings.ui.last_prompt = ""
        self.settings.ui.custom_prompt = ""  # カスタムプロンプトもクリア
        # シグナルをブロックして「②カスタムプロンプト」を選択
        self.template_combo.blockSignals(True)
        self.template_combo.setCurrentIndex(1)
        self.template_combo.blockSignals(False)
        # カスタムプロンプト用のプレースホルダーを設定
        self.prompt_edit.setPlaceholderText("カスタムプロンプトを入力してください")
    
    def on_browse_output_dir(self):
        """出力ディレクトリ参照ボタンクリック時の処理"""
        dir_path = QFileDialog.getExistingDirectory(
            self, "出力ディレクトリを選択", str(self.settings.file.output_directory)
        )
        
        if dir_path:
            self.output_dir_edit.setText(dir_path)
    
    def on_browse_input_dir(self):
        """入力ディレクトリ参照ボタンクリック時の処理"""
        dir_path = QFileDialog.getExistingDirectory(
            self, "ファイル選択時のフォルダを選択", str(self.settings.file.input_directory)
        )
        
        if dir_path:
            self.input_dir_edit.setText(dir_path)
    
    def on_save_settings(self):
        """設定保存ボタンクリック時の処理"""
        try:
            # 出力ディレクトリ
            self.settings.file.output_directory = Path(self.output_dir_edit.text())
            
            # 入力ディレクトリ
            self.settings.file.input_directory = Path(self.input_dir_edit.text())
            
            # BOM設定
            self.settings.file.use_bom = self.bom_check.isChecked()
            
            # ファイルサイズ制限
            try:
                file_size = int(self.file_size_edit.text())
                if file_size <= 0 or file_size > 1000:
                    raise ValueError("ファイルサイズは1～1000MBの範囲で指定してください")
                self.settings.file.max_file_size_mb = file_size
            except ValueError as e:
                QMessageBox.warning(self, "エラー", str(e))
                return
            
            # API関連設定
            # マスク文字列ではなく実際のAPIキーを保存
            self.settings.gemini.api_key = self._actual_api_key
            self.settings.gemini.model_name = self.model_combo.currentText()
            self.settings.gemini.mode = self.mode_combo.currentData()
            self.settings.gemini.stream_response = self.streaming_check.isChecked()
            
            # プロンプト
            self.settings.ui.last_prompt = self.prompt_edit.toPlainText()
            
            # カスタムプロンプトの場合、custom_promptにも保存
            if self.template_combo.currentIndex() == 1:  # ②カスタムプロンプト
                self.settings.ui.custom_prompt = self.prompt_edit.toPlainText()
            
            # 設定保存
            if save_settings(self.settings):
                QMessageBox.information(self, "成功", "設定を保存しました")
                logger.info("設定を保存しました")
            else:
                QMessageBox.warning(self, "エラー", "設定の保存に失敗しました")
        
        except Exception as e:
            QMessageBox.critical(self, "エラー", f"設定保存中にエラーが発生しました: {e}")
            logger.error(f"設定保存エラー: {e}")
    
    def on_analyze(self):
        """解析ボタンクリック時の処理"""
        # 入力チェック
        if not self.video_files:
            QMessageBox.warning(self, "エラー", "解析する動画ファイルを選択してください")
            return
        
        prompt = self.prompt_edit.toPlainText().strip()
        if not prompt:
            QMessageBox.warning(self, "エラー", "解析プロンプトを入力してください")
            return
        
        # 最初のファイルを使用
        video_path = self.video_files[0]
        
        # APIキー取得 - マスク文字列ではなく実際のAPIキーを使用
        api_key = self._actual_api_key
        
        # モデル名取得
        model_name = self.model_combo.currentText()
        
        # モード取得
        mode = self.mode_combo.currentData()
        
        # ストリーミング設定
        streaming = self.streaming_check.isChecked()
        
        # 出力ディレクトリ
        output_dir = Path(self.output_dir_edit.text())
        
        # BOM設定
        use_bom = self.bom_check.isChecked()
        
        # ファイルサイズ制限
        try:
            max_file_size = int(self.file_size_edit.text())
        except ValueError:
            max_file_size = self.settings.file.max_file_size_mb
        
        # 結果テキストとMarkdownバッファをクリア
        self.result_text.clear()
        self._md_buffer = ""
        
        # UI状態更新
        self.set_processing_state(True)
        
        # ワーカー設定
        self.worker.configure(
            video_path=video_path,
            prompt=prompt,
            api_key=api_key,
            model_name=model_name,
            mode=mode,
            streaming=streaming,
            output_dir=output_dir,
            use_bom=use_bom,
            max_file_size_mb=max_file_size
        )
        
        # プロンプトを設定に保存
        self.settings.ui.last_prompt = prompt
        
        # カスタムプロンプトの場合、custom_promptにも保存
        if self.template_combo.currentIndex() == 1:  # ②カスタムプロンプト
            self.settings.ui.custom_prompt = prompt
        
        # ワーカー開始
        self.worker.start()
        
        logger.info(f"解析開始: {Path(video_path).name}")
    
    def on_progress_update(self, value: int):
        """進捗更新時の処理"""
        self.progress_bar.setValue(value)
    
    def on_status_update(self, message: str):
        """状態更新時の処理"""
        self.status_label.setText(message)
        # ログも更新
        self.log_list.update_logs()
    
    def on_worker_error(self, error_message: str):
        """ワーカーエラー時の処理"""
        QMessageBox.critical(self, "エラー", error_message)
        self.set_processing_state(False)
        # ログを更新
        self.log_list.update_logs()
    
    def on_result_ready(self, text: str):
        """結果取得時の処理 (非ストリーミング)"""
        # Markdownとして結果を表示
        self.result_text.setMarkdown(text)
    
    def on_stream_chunk(self, chunk: str):
        """ストリーミングチャンク受信時の処理"""
        # チャンクをバッファに追加
        self._md_buffer += chunk
        # バッファの内容をMarkdownとして表示
        self.result_text.setMarkdown(self._md_buffer)

        # 自動スクロール (一番下まで)
        # スクロールバーを取得して最大値に設定
        scrollbar = self.result_text.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())
    
    def on_worker_complete(self, output_file: str):
        """処理完了時の処理"""
        self.set_processing_state(False)
        QMessageBox.information(
            self, 
            "処理完了", 
            f"動画の解析が完了しました。\n結果は以下に保存されました:\n{output_file}"
        )
        # ログを更新
        self.log_list.update_logs()
        # 結果テキストを自動で開く
        try:
            os.startfile(output_file)
            logger.debug(f"結果ファイルを自動オープン: {output_file}")
        except Exception as e:
            logger.error(f"自動オープン失敗: {e}")
    
    def set_processing_state(self, is_processing: bool):
        """処理中の UI 状態を設定"""
        # 処理中はボタンを無効化
        self.analyze_btn.setEnabled(not is_processing)
        self.select_file_btn.setEnabled(not is_processing)
        self.clear_file_btn.setEnabled(not is_processing)
        
        # 進捗バーをリセットまたはインディケータモードに
        if is_processing:
            self.progress_bar.setValue(0)
        else:
            self.progress_bar.setValue(0)
            self.status_label.setText("準備完了")
    
    def update_ui_state(self):
        """UI状態の更新"""
        has_files = len(self.video_files) > 0
        self.analyze_btn.setEnabled(has_files)
        self.clear_file_btn.setEnabled(has_files)
    
    def closeEvent(self, event):
        """アプリケーション終了時の処理"""
        # 現在の設定を保存
        try:
            # プロンプトを保存
            self.settings.ui.last_prompt = self.prompt_edit.toPlainText()
            
            # カスタムプロンプトの場合、custom_promptにも保存
            if self.template_combo.currentIndex() == 1:  # ②カスタムプロンプト
                self.settings.ui.custom_prompt = self.prompt_edit.toPlainText()
            
            # API関連設定 - マスク文字列ではなく実際のAPIキーを保存
            self.settings.gemini.api_key = self._actual_api_key
            self.settings.gemini.model_name = self.model_combo.currentText()
            self.settings.gemini.mode = self.mode_combo.currentData()
            self.settings.gemini.stream_response = self.streaming_check.isChecked()
            
            # 設定保存
            save_settings(self.settings)
            logger.debug("終了時に設定を保存しました")
        
        except Exception as e:
            logger.error(f"終了時の設定保存エラー: {e}")
        
        # 親クラスの処理を呼び出し
        super().closeEvent(event)

    def build_small_frame(self):
        """小モード用UIを作成"""
        self.small_frame = QWidget()
        layout = QHBoxLayout(self.small_frame)
        # ファイル選択ボタン
        btn_file = QPushButton("ファイル選択...")
        btn_file.clicked.connect(self.on_select_file)
        layout.addWidget(btn_file)
        # 選択ファイル名表示用ラベル
        self.small_file_label = QLabel("ファイル: 未選択")
        layout.addWidget(self.small_file_label)
        # 動画解析ボタン
        btn_analyze = QPushButton("動画を解析")
        btn_analyze.clicked.connect(self.on_analyze)
        # 大モードと同じ色付けを適用
        btn_analyze.setStyleSheet("""
            QPushButton {
                background-color: #2980b9;
                color: white;
                padding: 8px;
                font-weight: bold;
                border-radius: 4px;
                min-height: 30px;
            }
            QPushButton:hover {
                background-color: #3498db;
            }
            QPushButton:disabled {
                background-color: #95a5a6;
            }
        """)
        layout.addWidget(btn_analyze)
        # 詳細（大モード）に展開する矢印ボタン
        layout.addStretch()
        self.expand_button = QToolButton()
        self.expand_button.setArrowType(Qt.ArrowType.DownArrow)
        self.expand_button.setToolTip("詳細表示に展開")
        self.expand_button.clicked.connect(self.toggle_mode)
        layout.addWidget(self.expand_button)

    def toggle_mode(self):
        """小/大モード切替"""
        if self._is_small_mode:
            # 小モード→大モード
            self.small_frame.hide()
            self.large_frame.show()
            # 大モード用のデフォルトサイズ
            self.resize(1000, 700)
        else:
            # 大モード→小モード
            self.large_frame.hide()
            self.small_frame.show()
            # 小モードに合わせて自動調整
            self.adjustSize()
        self._is_small_mode = not self._is_small_mode
        logger.debug(f"表示モード切替: {'小モード' if self._is_small_mode else '大モード'}")


def run_main_window():
    """アプリケーションを起動する関数"""
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    run_main_window() 