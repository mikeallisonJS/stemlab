from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTabWidget, QWidget,
    QLabel, QPushButton, QListWidget, QListWidgetItem,
    QFrame, QSplitter, QTextBrowser
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont

from models import registry


class ModelSelectionDialog(QDialog):
    """
    Advanced model selection dialog with tabs for different model categories.
    """

    def __init__(self, parent=None, current_model=None):
        """
        Initialize the dialog.

        Args:
            parent: Parent widget
            current_model: Identifier of the model to preselect, e.g. "demucs4:htdemucs"
        """
        super().__init__(parent)
        self.setWindowTitle("Advanced Model Selection")
        self.setMinimumSize(820, 520)
        self.selected_model = None
        self.model_lists = {}
        self.details_browsers = {}
        # Installation state per backend, looked up once
        self.installed = {
            backend: model.available for backend, model in registry.backend_models().items()
        }

        self.init_ui()
        self.preselect(current_model)

    def init_ui(self):
        """Initialize the UI components."""
        # Main layout
        main_layout = QVBoxLayout(self)

        # Tabs for model categories
        self.tabs = QTabWidget()
        main_layout.addWidget(self.tabs)

        # Add tabs for each model family
        for family in registry.FAMILIES.values():
            self.tabs.addTab(self.create_model_tab(family), family.title)
        self.tabs.currentChanged.connect(self.on_tab_changed)

        # Button layout
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        cancel_button = QPushButton("Cancel")
        cancel_button.clicked.connect(self.reject)
        button_layout.addWidget(cancel_button)

        self.select_button = QPushButton("Select Model")
        self.select_button.setEnabled(False)
        self.select_button.setDefault(True)
        self.select_button.clicked.connect(self.accept)
        button_layout.addWidget(self.select_button)

        main_layout.addLayout(button_layout)

    def create_model_tab(self, family):
        """Create a tab for a specific model family."""
        tab = QWidget()
        layout = QHBoxLayout(tab)

        # Splitter for list and details
        splitter = QSplitter(Qt.Orientation.Horizontal)
        layout.addWidget(splitter)

        # Left side: Model list
        list_frame = QFrame()
        list_layout = QVBoxLayout(list_frame)
        title = QLabel(f"Available {family.title} Models")
        title_font = QFont(title.font())
        title_font.setBold(True)
        title.setFont(title_font)
        list_layout.addWidget(title)

        model_list = QListWidget()
        model_list.setMinimumWidth(240)
        list_layout.addWidget(model_list)

        # Add models to the list, the family's default first
        names = sorted(family.models, key=lambda name: (name != family.default, name))
        for model_name in names:
            item = QListWidgetItem(model_name)
            item.setData(Qt.ItemDataRole.UserRole, registry.model_id(family.key, model_name))
            model_list.addItem(item)

        model_list.currentItemChanged.connect(self.on_model_selected)
        model_list.itemDoubleClicked.connect(lambda _item: self.accept())
        self.model_lists[family.key] = model_list

        # Right side: Model details
        details_frame = QFrame()
        details_layout = QVBoxLayout(details_frame)
        details_title = QLabel("Model Details")
        details_title.setFont(title_font)
        details_layout.addWidget(details_title)

        details_browser = QTextBrowser()
        details_browser.setMinimumWidth(440)
        details_browser.setOpenExternalLinks(True)
        details_browser.setHtml("<p>Select a model to see its details.</p>")
        details_layout.addWidget(details_browser)
        self.details_browsers[family.key] = details_browser

        # Add frames to splitter
        splitter.addWidget(list_frame)
        splitter.addWidget(details_frame)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)

        return tab

    def preselect(self, identifier):
        """Open the tab of a model and select it."""
        parsed = registry.parse_model_id(identifier) if identifier else None
        if parsed is None:
            return
        family_key, _model_name = parsed
        self.tabs.setCurrentIndex(list(registry.FAMILIES).index(family_key))
        model_list = self.model_lists[family_key]
        for row in range(model_list.count()):
            if model_list.item(row).data(Qt.ItemDataRole.UserRole) == identifier:
                model_list.setCurrentRow(row)
                break

    def on_tab_changed(self, index):
        """The selection follows the visible tab."""
        family_key = list(registry.FAMILIES)[index]
        item = self.model_lists[family_key].currentItem()
        self.selected_model = item.data(Qt.ItemDataRole.UserRole) if item else None
        self.select_button.setEnabled(self.selected_model is not None)

    def on_model_selected(self, item, _previous=None):
        """Handle model selection from any list."""
        if item is None:
            return
        identifier = item.data(Qt.ItemDataRole.UserRole)
        family_key, model_name = registry.parse_model_id(identifier)

        # Store the selected model
        self.selected_model = identifier

        # Enable the select button
        self.select_button.setEnabled(True)

        # Update details browser
        self.details_browsers[family_key].setHtml(self.get_model_details(family_key, model_name))

    def get_model_details(self, family_key, model_name):
        """Get detailed HTML description of the model."""
        family = registry.FAMILIES[family_key]
        description = family.models.get(model_name, "No description available")
        model = family.model_class(model_name=model_name)
        stems = ", ".join(model.get_stems())

        if self.installed.get(family.backend):
            status = "Installed"
        else:
            status = f"Not installed ({family.model_class.INSTALL_SIZE})"

        # Base HTML
        details_html = f"""
        <h2>{model_name}</h2>
        <p><b>Type:</b> {family.title}</p>
        <p><b>Description:</b> {description}</p>
        <p><b>Stems produced:</b> {stems}</p>
        <p><b>Status:</b> {status}</p>
        """

        # Add model-specific information
        if family_key == "demucs3":
            details_html += self.get_demucs_v3_details(model_name)
        elif family_key == "demucs4":
            details_html += self.get_demucs_v4_details(model_name)
        elif family_key == "spleeter":
            details_html += self.get_spleeter_details(model_name)
        elif family_key == "bandsplit":
            details_html += self.get_bandsplit_details(model_name)
        elif family_key == "d3net":
            details_html += self.get_d3net_details(model_name)

        return details_html

    def get_demucs_v3_details(self, model_name):
        """Get details specific to Demucs v3 models."""
        details = """
        <h3>Demucs v3 Information</h3>
        <p>Demucs v3 (Hybrid Demucs) is the previous generation model from Meta AI Research. It
        combines waveform and spectrogram processing and won the Sony MDX challenge.</p>
        <p><b>Key features:</b></p>
        <ul>
        <li>Support for vocals/instrumental (2 stems) mode</li>
        """

        if model_name == "hdemucs_mmi":
            details += """
            <li>Single network trained on MusDB plus 800 additional songs</li>
            <li>Fastest of the v3 models</li>
            """
        elif model_name == "mdx":
            details += """
            <li>Bag of 4 networks trained on MusDB HQ only</li>
            <li>Winner of track A of the MDX challenge</li>
            """
        elif model_name == "mdx_extra":
            details += """
            <li>Bag of 4 networks trained with extra data</li>
            <li>Best quality of the v3 models, ranked 2nd in track B of the MDX challenge</li>
            """

        details += """
        </ul>
        <p><a href="https://github.com/adefossez/demucs">More information on Demucs GitHub</a></p>
        """
        return details

    def get_demucs_v4_details(self, model_name):
        """Get details specific to Demucs v4 models."""
        details = """
        <h3>Demucs v4 Information</h3>
        <p>Demucs v4 (Hybrid Transformer Demucs) is the latest model from Meta AI Research, featuring transformer architecture.</p>
        <p><b>Key features:</b></p>
        <ul>
        <li>Better separation quality than v3</li>
        <li>Support for vocals/instrumental (2 stems) mode</li>
        """

        if model_name == "htdemucs":
            details += """
            <li>Default balanced model</li>
            """
        elif model_name == "htdemucs_ft":
            details += """
            <li>Fine-tuned version: one specialised network per stem</li>
            <li>Higher quality, but takes 4 times as long</li>
            """
        elif model_name == "htdemucs_6s":
            details += """
            <li>Extended 6-stem version adding guitar and piano</li>
            <li>The piano stem is experimental and less clean than the others</li>
            """

        details += """
        </ul>
        <p><a href="https://github.com/adefossez/demucs">More information on Demucs GitHub</a></p>
        """
        return details

    def get_spleeter_details(self, model_name):
        """Get details specific to Spleeter models."""
        details = """
        <h3>Spleeter Information</h3>
        <p>Spleeter is a source separation model from Deezer Research. It is very fast,
        even without a GPU, at the cost of lower quality than the newer models.</p>
        <p><b>Technology:</b> Spleeter uses TensorFlow as its backend. Its models reproduce
        frequencies up to 11 kHz.</p>
        <p><a href="https://github.com/deezer/spleeter">More information on Spleeter GitHub</a></p>
        """
        return details

    def get_bandsplit_details(self, model_name):
        """Get details specific to Band-Split RoFormer models."""
        details = """
        <h3>Band-Split RoFormer Information</h3>
        <p>Band-Split RoFormer splits the spectrum into frequency bands and models them with
        transformers. It is the successor of Band-Split RNN and currently among the best
        performing separation architectures.</p>
        """

        if model_name == "vocals":
            details += """
            <p><b>Vocals model features:</b></p>
            <ul>
            <li>Highest quality vocal and instrumental separation available here</li>
            <li>Checkpoint: BS-RoFormer by viperx (SDR 12.98)</li>
            </ul>
            """
        elif model_name == "6stems":
            details += """
            <p><b>6 stems model features:</b></p>
            <ul>
            <li>Separates guitar and piano in addition to the usual four stems</li>
            <li>Checkpoint: BS-RoFormer SW by jarredou</li>
            </ul>
            """

        details += """
        <p><b>Technology:</b> Runs on PyTorch through python-audio-separator. A GPU is
        strongly recommended. Each model downloads about 650 MB of weights on first use.</p>
        <p><a href="https://github.com/nomadkaraoke/python-audio-separator">More information on python-audio-separator GitHub</a></p>
        """
        return details

    def get_d3net_details(self, model_name):
        """Get details specific to D3Net models."""
        details = """
        <h3>D3Net Information</h3>
        <p>D3Net (Densely connected multidilated DenseNet) is a source separation model from Sony AI Research.</p>
        """

        if model_name == "standard":
            details += """
            <p><b>Standard model features:</b></p>
            <ul>
            <li>Averages each prediction with one for swapped stereo channels</li>
            <li>Best quality, twice the processing time of the fast model</li>
            </ul>
            """
        elif model_name == "fast":
            details += """
            <p><b>Fast model features:</b></p>
            <ul>
            <li>Single prediction per audio segment</li>
            <li>Half the processing time, slightly lower quality</li>
            </ul>
            """

        details += """
        <p><b>Technology:</b> Sony's pretrained networks, converted to ONNX. They run on the
        GPU through DirectML on Windows and on the CPU elsewhere, where D3Net is slow.</p>
        <p><a href="https://github.com/sony/ai-research-code/tree/master/d3net">More information on D3Net GitHub</a></p>
        """
        return details

    @classmethod
    def get_model(cls, parent, current_model=None):
        """
        Static method to show the dialog and return the selected model.

        Args:
            parent: Parent widget
            current_model: Identifier of the model to preselect

        Returns:
            Identifier of the selected model (e.g. "demucs4:htdemucs_ft"),
            or None if the dialog was cancelled
        """
        dialog = cls(parent, current_model)
        result = dialog.exec()

        if result == QDialog.DialogCode.Accepted and dialog.selected_model:
            return dialog.selected_model

        return None
