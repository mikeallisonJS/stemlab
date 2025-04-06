from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTabWidget, QWidget,
    QLabel, QPushButton, QListWidget, QListWidgetItem, QGridLayout,
    QFrame, QSplitter, QTextBrowser, QGroupBox, QDialogButtonBox
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont, QIcon

class ModelSelectionDialog(QDialog):
    """
    Advanced model selection dialog with tabs for different model categories.
    """
    
    model_selected = pyqtSignal(str, str, str)  # model_name, model_type, display_name
    
    def __init__(self, parent=None, model_collections=None):
        """
        Initialize the dialog with model collections.
        
        Args:
            parent: Parent widget
            model_collections: Dictionary of model collections with format:
                               {model_type: (display_name, available_models, model_class)}
        """
        super().__init__(parent)
        self.setWindowTitle("Advanced Model Selection")
        self.setMinimumSize(800, 500)
        self.model_collections = model_collections or {}
        self.selected_model = None
        self.selected_model_type = None
        self.selected_display_name = None
        
        self.init_ui()
        
    def init_ui(self):
        """Initialize the UI components."""
        # Main layout
        main_layout = QVBoxLayout(self)
        
        # Apply dark theme to dialog
        self.setStyleSheet("""
            QDialog {
                background-color: #1e1e1e;
                color: #e0e0e0;
            }
            QLabel {
                color: #e0e0e0;
            }
            QPushButton {
                background-color: #2d2d30;
                color: #e0e0e0;
                border: 1px solid #3e3e42;
                padding: 5px 15px;
            }
            QPushButton:hover {
                background-color: #3e3e42;
            }
            QPushButton:pressed {
                background-color: #007acc;
            }
            QPushButton:disabled {
                background-color: #2d2d30;
                color: #656565;
            }
        """)
        
        # Tabs for model categories
        self.tabs = QTabWidget()
        # Set styling for tab widget for dark mode
        self.tabs.setStyleSheet("""
            QTabWidget::pane {
                border: 1px solid #3e3e42;
                background-color: #252526;
            }
            QTabBar::tab {
                background-color: #2d2d30;
                color: #e0e0e0;
                padding: 8px 16px;
                border: 1px solid #3e3e42;
                border-bottom: none;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
            }
            QTabBar::tab:selected {
                background-color: #252526;
                border-bottom-color: #252526;
            }
            QTabBar::tab:hover:!selected {
                background-color: #3e3e42;
            }
        """)
        main_layout.addWidget(self.tabs)
        
        # Add tabs for each model type
        for model_type, (display_name, models_dict, _) in self.model_collections.items():
            tab = self.create_model_tab(model_type, display_name, models_dict)
            self.tabs.addTab(tab, display_name)
        
        # Button layout
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        
        cancel_button = QPushButton("Cancel")
        cancel_button.clicked.connect(self.reject)
        button_layout.addWidget(cancel_button)
        
        self.select_button = QPushButton("Select Model")
        self.select_button.setEnabled(False)
        self.select_button.clicked.connect(self.accept)
        button_layout.addWidget(self.select_button)
        
        main_layout.addLayout(button_layout)
        
    def create_model_tab(self, model_type, display_name, models_dict):
        """Create a tab for a specific model type."""
        tab = QWidget()
        layout = QHBoxLayout(tab)
        
        # Splitter for list and details
        splitter = QSplitter(Qt.Orientation.Horizontal)
        layout.addWidget(splitter)
        
        # Left side: Model list
        list_frame = QFrame()
        list_layout = QVBoxLayout(list_frame)
        title = QLabel(f"Available {display_name} Models")
        title.setFont(QFont("Arial", 12, QFont.Weight.Bold))
        list_layout.addWidget(title)
        
        self.model_lists = getattr(self, 'model_lists', {})
        model_list = QListWidget()
        model_list.setMinimumWidth(250)
        # Set styling for dark mode
        model_list.setStyleSheet("""
            QListWidget {
                background-color: #252526;
                color: #e0e0e0;
                font-family: Arial, sans-serif;
                font-size: 11pt;
                border: 1px solid #3e3e42;
            }
            QListWidget::item {
                padding: 4px;
            }
            QListWidget::item:selected {
                background-color: #007acc;
                color: #ffffff;
            }
            QListWidget::item:hover:!selected {
                background-color: #3e3e42;
            }
        """)
        list_layout.addWidget(model_list)
        
        # Add models to the list
        model_keys = sorted(models_dict.keys())
        for model_name in model_keys:
            description = models_dict[model_name]
            item = QListWidgetItem(f"{model_name}")
            item.setData(Qt.ItemDataRole.UserRole, (model_name, model_type))
            model_list.addItem(item)
        
        model_list.itemClicked.connect(self.on_model_selected)
        self.model_lists[model_type] = model_list
        
        # Right side: Model details
        details_frame = QFrame()
        details_layout = QVBoxLayout(details_frame)
        details_title = QLabel("Model Details")
        details_title.setFont(QFont("Arial", 12, QFont.Weight.Bold))
        details_layout.addWidget(details_title)
        
        self.details_browsers = getattr(self, 'details_browsers', {})
        details_browser = QTextBrowser()
        details_browser.setMinimumWidth(450)
        details_browser.setOpenExternalLinks(True)
        
        # Set explicit stylesheet for the text browser for dark mode
        details_browser.setStyleSheet("""
            QTextBrowser {
                background-color: #1e1e1e;
                color: #e0e0e0;
                font-family: Arial, sans-serif;
                font-size: 11pt;
                border: 1px solid #3e3e42;
                padding: 8px;
            }
            QScrollBar:vertical {
                background-color: #252526;
                width: 14px;
                margin: 0px;
            }
            QScrollBar::handle:vertical {
                background-color: #3e3e42;
                min-height: 20px;
            }
            QScrollBar::handle:vertical:hover {
                background-color: #007acc;
            }
        """)
        
        details_layout.addWidget(details_browser)
        self.details_browsers[model_type] = details_browser
        
        # Add frames to splitter
        splitter.addWidget(list_frame)
        splitter.addWidget(details_frame)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)
        
        return tab
    
    def on_model_selected(self, item):
        """Handle model selection from any list."""
        model_name, model_type = item.data(Qt.ItemDataRole.UserRole)
        
        # Update all lists to show only the selected item as selected
        for list_type, model_list in self.model_lists.items():
            if list_type != model_type:
                model_list.clearSelection()
        
        # Store the selected model
        self.selected_model = model_name
        self.selected_model_type = model_type
        display_name = f"{self.model_collections[model_type][0]} ({model_name})"
        self.selected_display_name = display_name
        
        # Enable the select button
        self.select_button.setEnabled(True)
        
        # Update details browser
        details = self.get_model_details(model_name, model_type)
        self.details_browsers[model_type].setHtml(details)
    
    def get_model_details(self, model_name, model_type):
        """Get detailed HTML description of the model."""
        models_dict = self.model_collections[model_type][1]
        description = models_dict.get(model_name, "No description available")
        
        # Common CSS style for all model details - dark mode
        style = """
        <style>
            body { 
                font-family: Arial, sans-serif; 
                color: #e0e0e0; 
                background-color: #1e1e1e;
                margin: 0;
                padding: 0;
            }
            h2 { 
                color: #62aaff; 
                border-bottom: 1px solid #3e3e42;
                padding-bottom: 8px;
            }
            h3 { 
                color: #56cc90;
                margin-top: 24px; 
            }
            p { 
                line-height: 1.5; 
            }
            b { 
                color: #ffffff; 
                font-weight: bold;
            }
            ul { 
                margin-left: 20px; 
                padding-left: 10px;
            }
            li { 
                margin-bottom: 8px; 
                line-height: 1.4;
            }
            a { 
                color: #0099ff; 
                text-decoration: none;
            }
            a:hover {
                text-decoration: underline;
            }
        </style>
        """
        
        # Base HTML with styling
        details_html = f"""
        {style}
        <h2>{model_name}</h2>
        <p><b>Type:</b> {self.model_collections[model_type][0]}</p>
        <p><b>Description:</b> {description}</p>
        """
        
        # Add model-specific information
        if model_type == "DemucsModel":
            if "v3" in self.model_collections[model_type][0].lower():
                details_html += self.get_demucs_v3_details(model_name)
            else:
                details_html += self.get_demucs_v4_details(model_name)
        elif model_type == "SpleeterModel":
            details_html += self.get_spleeter_details(model_name)
        elif model_type == "BandSplitRNNModel":
            details_html += self.get_bandsplit_details(model_name)
        elif model_type == "D3NetModel":
            details_html += self.get_d3net_details(model_name)
            
        return details_html
    
    def get_demucs_v3_details(self, model_name):
        """Get details specific to Demucs v3 models."""
        details = """
        <h3>Demucs v3 Information</h3>
        <p>Demucs v3 is the legacy model from Meta AI Research (formerly Facebook AI Research).</p>
        <p><b>Stems produced:</b> vocals, drums, bass, other</p>
        <p><b>Key features:</b></p>
        <ul>
        """
        
        if model_name == "demucs":
            details += """
            <li>Original version with balanced quality</li>
            <li>Good general-purpose performance</li>
            """
        elif model_name == "demucs_extra":
            details += """
            <li>Extra training with more data</li>
            <li>Better quality than the base model</li>
            """
        elif model_name == "demucs_quantized":
            details += """
            <li>Quantized model (smaller size)</li>
            <li>Faster processing with slightly lower quality</li>
            """
        elif "tasnet" in model_name:
            details += """
            <li>Based on Conv-TasNet architecture</li>
            <li>Different approach than standard Demucs</li>
            """
            
        details += """
        </ul>
        <p><a href="https://github.com/facebookresearch/demucs">More information on Demucs GitHub</a></p>
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
            <li>Separates into: vocals, drums, bass, other</li>
            """
        elif model_name == "htdemucs_ft":
            details += """
            <li>Fine-tuned version with additional training</li>
            <li>Higher quality but similar stems as default</li>
            <li>Separates into: vocals, drums, bass, other</li>
            """
        elif model_name == "htdemucs_6s":
            details += """
            <li>Extended 6-stem version</li>
            <li>Separates into: vocals, drums, bass, other, guitar, piano</li>
            """
            
        details += """
        </ul>
        <p><a href="https://github.com/facebookresearch/demucs">More information on Demucs GitHub</a></p>
        """
        return details
    
    def get_spleeter_details(self, model_name):
        """Get details specific to Spleeter models."""
        details = """
        <h3>Spleeter Information</h3>
        <p>Spleeter is a source separation model from Deezer Research.</p>
        """
        
        if model_name == "2stems":
            details += """
            <p><b>This model separates audio into 2 stems:</b></p>
            <ul>
            <li>vocals: All vocal elements</li>
            <li>accompaniment: All instrumental elements</li>
            </ul>
            """
        elif model_name == "4stems":
            details += """
            <p><b>This model separates audio into 4 stems:</b></p>
            <ul>
            <li>vocals: All vocal elements</li>
            <li>drums: Drum kit and percussion</li>
            <li>bass: Bass guitar and similar instruments</li>
            <li>other: All other instruments</li>
            </ul>
            """
        elif model_name == "5stems":
            details += """
            <p><b>This model separates audio into 5 stems:</b></p>
            <ul>
            <li>vocals: All vocal elements</li>
            <li>drums: Drum kit and percussion</li>
            <li>bass: Bass guitar and similar instruments</li>
            <li>piano: Piano and keyboard instruments</li>
            <li>other: All other instruments</li>
            </ul>
            """
            
        details += """
        <p><b>Technology:</b> Spleeter uses TensorFlow as its backend.</p>
        <p><a href="https://github.com/deezer/spleeter">More information on Spleeter GitHub</a></p>
        """
        return details
    
    def get_bandsplit_details(self, model_name):
        """Get details specific to Band-Split RNN models."""
        details = """
        <h3>Band-Split RNN Information</h3>
        <p>Band-Split RNN is a frequency-domain source separation model that uses recurrent neural networks.</p>
        <p><b>This model separates audio into 4 stems:</b></p>
        <ul>
        <li>vocals: All vocal elements</li>
        <li>drums: Drum kit and percussion</li>
        <li>bass: Bass guitar and similar instruments</li>
        <li>other: All other instruments</li>
        </ul>
        """
        
        if model_name == "standard":
            details += """
            <p><b>Standard model features:</b></p>
            <ul>
            <li>Full-quality model with best performance</li>
            <li>Balances quality and processing time</li>
            </ul>
            """
        elif model_name == "light":
            details += """
            <p><b>Light model features:</b></p>
            <ul>
            <li>Smaller, faster model</li>
            <li>Reduced memory and processing requirements</li>
            <li>Slightly lower quality than standard model</li>
            </ul>
            """
            
        details += """
        <p><b>Technology:</b> Band-Split RNN uses PyTorch as its backend.</p>
        <p><a href="https://github.com/sevagh/band-split-rnn">More information on Band-Split RNN GitHub</a></p>
        """
        return details
    
    def get_d3net_details(self, model_name):
        """Get details specific to D3Net models."""
        details = """
        <h3>D3Net Information</h3>
        <p>D3Net (Dense DenseNet with Dilated Dense block) is a deep source separation model from Sony AI Research.</p>
        <p><b>This model separates audio into 4 stems:</b></p>
        <ul>
        <li>vocals: All vocal elements</li>
        <li>drums: Drum kit and percussion</li>
        <li>bass: Bass guitar and similar instruments</li>
        <li>other: All other instruments</li>
        </ul>
        """
        
        if model_name == "standard":
            details += """
            <p><b>Standard model features:</b></p>
            <ul>
            <li>Default balanced model</li>
            <li>Good quality across a variety of music genres</li>
            </ul>
            """
        elif model_name == "optimized":
            details += """
            <p><b>Optimized model features:</b></p>
            <ul>
            <li>Enhanced performance with more training</li>
            <li>Better quality but more resource-intensive</li>
            </ul>
            """
            
        details += """
        <p><b>Technology:</b> D3Net uses PyTorch as its backend.</p>
        <p><a href="https://github.com/sony/ai-research-code/tree/master/d3net">More information on D3Net GitHub</a></p>
        """
        return details
    
    @classmethod
    def get_model(cls, parent, model_collections):
        """
        Static method to show the dialog and return the selected model.
        
        Args:
            parent: Parent widget
            model_collections: Dictionary of model collections
            
        Returns:
            Tuple (model_name, model_type, display_name) if a model was selected,
            None otherwise
        """
        dialog = cls(parent, model_collections)
        result = dialog.exec()
        
        if result == QDialog.DialogCode.Accepted and dialog.selected_model:
            return (dialog.selected_model, dialog.selected_model_type, dialog.selected_display_name)
        
        return None 