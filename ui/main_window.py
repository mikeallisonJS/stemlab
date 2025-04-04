import os
import sys
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
    QLabel, QPushButton, QComboBox, QFileDialog,
    QProgressBar, QMessageBox, QFrame, QCheckBox
)
from PyQt6.QtCore import Qt, QMimeData, QUrl, pyqtSignal, QThread
from PyQt6.QtGui import QDragEnterEvent, QDropEvent

from models.demucs_model import DemucsModel
from models.spleeter_model import SpleeterModel
from models.bandsplit_model import BandSplitRNNModel
from models.d3net_model import D3NetModel
from ui.drop_area import DropArea


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("CaptainStems")
        self.setMinimumSize(800, 600)
        
        # Create model instances
        self.models = {}
        
        # Add Demucs v4 default model
        self.models["Demucs v4 (default)"] = DemucsModel(model_name="htdemucs")
        
        # Add Demucs v3 default model
        self.models["Demucs v3 (default)"] = DemucsModel(model_name="demucs")
        
        # Add Spleeter default model
        self.models["Spleeter (2stems)"] = SpleeterModel(model_name="2stems")
        
        # Add Band-Split RNN default model
        self.models["Band-Split RNN (standard)"] = BandSplitRNNModel(model_name="standard")
        
        # Add D3Net default model
        self.models["D3Net (standard)"] = D3NetModel(model_name="standard")
        
        # Get available models from each model type
        self.demucs_models = DemucsModel.get_available_models()
        self.spleeter_models = SpleeterModel.get_available_models()
        self.bandsplit_models = BandSplitRNNModel.get_available_models()
        self.d3net_models = D3NetModel.get_available_models()
        
        self.current_model = None
        self.current_audio_file = None
        
        self.init_ui()
    
    def init_ui(self):
        # Main layout
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        
        layout = QVBoxLayout(main_widget)
        
        # Title
        title_label = QLabel("CaptainStems")
        title_label.setStyleSheet("font-size: 24px; font-weight: bold;")
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title_label)
        
        # Model selection
        model_layout = QHBoxLayout()
        model_label = QLabel("Model:")
        self.model_combo = QComboBox()
        for model_name, model in self.models.items():
            display_name = f"{model_name}"
            if hasattr(model, 'available') and not model.available:
                display_name += " (not installed)"
            self.model_combo.addItem(display_name, model_name)
        self.model_combo.currentIndexChanged.connect(self.on_model_changed)
        
        # Advanced model selection button
        self.advanced_model_button = QPushButton("Advanced Models...")
        self.advanced_model_button.clicked.connect(self.show_advanced_model_selection)
        
        model_layout.addWidget(model_label)
        model_layout.addWidget(self.model_combo)
        model_layout.addWidget(self.advanced_model_button)
        
        # Add install button
        self.install_button = QPushButton("Install Model")
        self.install_button.setVisible(False)
        self.install_button.clicked.connect(self.install_model)
        model_layout.addWidget(self.install_button)
        
        model_layout.addStretch()
        
        layout.addLayout(model_layout)
        
        # Option for two-stems mode (vocals/instrumental)
        options_layout = QHBoxLayout()
        self.two_stems_checkbox = QCheckBox("Separate into vocals/instrumental only")
        self.two_stems_checkbox.setToolTip("For Demucs v4 models only")
        options_layout.addWidget(self.two_stems_checkbox)
        options_layout.addStretch()
        layout.addLayout(options_layout)
        
        # Drop area
        self.drop_area = DropArea()
        self.drop_area.file_dropped.connect(self.on_file_dropped)
        layout.addWidget(self.drop_area, 1)
        
        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)
        
        # Bottom buttons
        button_layout = QHBoxLayout()
        
        self.process_button = QPushButton("Process Audio")
        self.process_button.setEnabled(False)
        self.process_button.clicked.connect(self.process_audio)
        
        button_layout.addStretch()
        button_layout.addWidget(self.process_button)
        
        layout.addLayout(button_layout)
        
        # Initialize with first model
        self.on_model_changed(0)
    
    def show_advanced_model_selection(self):
        dialog = QMessageBox(self)
        dialog.setWindowTitle("Advanced Models")
        dialog.setText("Choose an advanced separation model:")
        
        # Create buttons for each advanced model
        # Group by model type
        v3_models = [k for k in self.demucs_models.keys() if k in ["demucs_extra", "demucs_quantized", "tasnet", "tasnet_extra"]]
        v4_models = [k for k in self.demucs_models.keys() if k in ["htdemucs_ft", "htdemucs_6s"]]
        spleeter_models = [k for k in self.spleeter_models.keys() if k in ["4stems", "5stems"]]
        bandsplit_models = [k for k in self.bandsplit_models.keys() if k in ["light"]]
        d3net_models = [k for k in self.d3net_models.keys() if k in ["optimized"]]
        
        # Add Demucs v3 models
        dialog.setInformativeText("Demucs v3 Models:")
        for model_name in v3_models:
            button = dialog.addButton(f"{model_name}: {self.demucs_models[model_name]}", QMessageBox.ButtonRole.ActionRole)
            button.model_name = model_name
            button.model_type = "DemucsModel"
            button.model_display_name = f"Demucs v3 ({model_name})"
        
        # Add Demucs v4 models
        detailed_text = "Demucs v4 Models:\n" + "\n".join([f"{m}: {self.demucs_models[m]}" for m in v4_models])
        
        # Add Spleeter models info
        detailed_text += "\n\nSpleeter Models:\n" + "\n".join([f"{m}: {self.spleeter_models[m]}" for m in spleeter_models])

        # Add Band-Split RNN models info
        detailed_text += "\n\nBand-Split RNN Models:\n" + "\n".join([f"{m}: {self.bandsplit_models[m]}" for m in ["standard"] + bandsplit_models])
        
        # Add D3Net models info
        detailed_text += "\n\nD3Net Models:\n" + "\n".join([f"{m}: {self.d3net_models[m]}" for m in ["standard"] + d3net_models])
        
        dialog.setDetailedText(detailed_text)
        
        # Add Demucs v4 model buttons
        for model_name in v4_models:
            button = dialog.addButton(f"{model_name}: {self.demucs_models[model_name]}", QMessageBox.ButtonRole.ActionRole)
            button.model_name = model_name
            button.model_type = "DemucsModel"
            button.model_display_name = f"Demucs v4 ({model_name})"
        
        # Add Spleeter model buttons
        for model_name in spleeter_models:
            button = dialog.addButton(f"{model_name}: {self.spleeter_models[model_name]}", QMessageBox.ButtonRole.ActionRole)
            button.model_name = model_name
            button.model_type = "SpleeterModel"
            button.model_display_name = f"Spleeter ({model_name})"
            
        # Add Band-Split RNN model buttons
        for model_name in bandsplit_models:
            button = dialog.addButton(f"{model_name}: {self.bandsplit_models[model_name]}", QMessageBox.ButtonRole.ActionRole)
            button.model_name = model_name
            button.model_type = "BandSplitRNNModel"
            button.model_display_name = f"Band-Split RNN ({model_name})"
            
        # Add D3Net model buttons
        for model_name in d3net_models:
            button = dialog.addButton(f"{model_name}: {self.d3net_models[model_name]}", QMessageBox.ButtonRole.ActionRole)
            button.model_name = model_name
            button.model_type = "D3NetModel"
            button.model_display_name = f"D3Net ({model_name})"
        
        # Add cancel button
        cancel_button = dialog.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
        
        dialog.exec()
        
        clicked_button = dialog.clickedButton()
        if clicked_button is not None and clicked_button is not cancel_button:
            # Create model and add to models dict
            model_name = clicked_button.model_name
            model_type = clicked_button.model_type
            display_name = clicked_button.model_display_name
            
            # Check if we already have this model
            if display_name not in self.models:
                if model_type == "DemucsModel":
                    self.models[display_name] = DemucsModel(model_name=model_name)
                elif model_type == "SpleeterModel":
                    self.models[display_name] = SpleeterModel(model_name=model_name)
                elif model_type == "BandSplitRNNModel":
                    self.models[display_name] = BandSplitRNNModel(model_name=model_name)
                elif model_type == "D3NetModel":
                    self.models[display_name] = D3NetModel(model_name=model_name)
                
                # Add to combo box
                model = self.models[display_name]
                model_display = display_name
                if hasattr(model, 'available') and not model.available:
                    model_display += " (not installed)"
                self.model_combo.addItem(model_display, display_name)
            
            # Select the model
            index = self.model_combo.findData(display_name)
            if index >= 0:
                self.model_combo.setCurrentIndex(index)
    
    def on_model_changed(self, index):
        model_name = self.model_combo.itemData(index)
        self.current_model = self.models.get(model_name)
        
        # Check if model is available
        if hasattr(self.current_model, 'available'):
            self.install_button.setVisible(not self.current_model.available)
        else:
            self.install_button.setVisible(False)
        
        # Update two-stems checkbox based on model
        is_demucs_v4 = isinstance(self.current_model, DemucsModel) and not getattr(self.current_model, 'is_v3', False)
        is_spleeter_2stems = isinstance(self.current_model, SpleeterModel) and self.current_model.model_name == "2stems"
        is_bandsplit_rnn = isinstance(self.current_model, BandSplitRNNModel)
        is_d3net = isinstance(self.current_model, D3NetModel)
        
        # Only enable two-stems checkbox for Demucs v4 models
        # (Spleeter 2stems is already just vocals/accompaniment)
        # (Band-Split RNN and D3Net always output 4 stems)
        if is_demucs_v4:
            self.two_stems_checkbox.setEnabled(True)
            self.two_stems_checkbox.setToolTip("Separate into vocals and instrumental only")
        else:
            self.two_stems_checkbox.setEnabled(False)
            self.two_stems_checkbox.setChecked(False)
            
            if isinstance(self.current_model, DemucsModel) and getattr(self.current_model, 'is_v3', False):
                self.two_stems_checkbox.setToolTip("Two-stems mode not available for Demucs v3 models")
            elif is_spleeter_2stems:
                self.two_stems_checkbox.setToolTip("Spleeter 2stems is already vocals/accompaniment only")
            elif is_bandsplit_rnn:
                self.two_stems_checkbox.setToolTip("Band-Split RNN always outputs 4 stems")
            elif is_d3net:
                self.two_stems_checkbox.setToolTip("D3Net always outputs 4 stems")
            else:
                self.two_stems_checkbox.setToolTip("Two-stems mode not available for this model")
            
        self.update_ui_state()
    
    def install_model(self):
        if not self.current_model:
            return
            
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(10)
        
        # Try to install the model
        if hasattr(self.current_model, 'install_dependencies'):
            success = self.current_model.install_dependencies()
            
            self.progress_bar.setValue(100)
            self.progress_bar.setVisible(False)
            
            if success:
                QMessageBox.information(
                    self, 
                    "Installation Successful", 
                    f"The {self.current_model.name} model was installed successfully."
                )
                
                # Update the combo box
                current_index = self.model_combo.currentIndex()
                model_name = self.model_combo.itemData(current_index)
                self.model_combo.setItemText(current_index, model_name)
                
                # Hide the install button
                self.install_button.setVisible(False)
                
                # Update UI state
                self.update_ui_state()
            else:
                QMessageBox.critical(
                    self, 
                    "Installation Failed", 
                    f"Failed to install {self.current_model.name} model. Please try again or install manually."
                )
    
    def on_file_dropped(self, file_path):
        self.current_audio_file = file_path
        self.drop_area.set_file(os.path.basename(file_path))
        self.update_ui_state()
    
    def update_ui_state(self):
        model_available = True
        if hasattr(self.current_model, 'available'):
            model_available = self.current_model.available
            
        can_process = (
            self.current_model is not None and 
            self.current_audio_file is not None and
            model_available
        )
        
        self.process_button.setEnabled(can_process)
    
    def process_audio(self):
        if not self.current_model or not self.current_audio_file:
            return
            
        # Ask for output directory
        output_dir = QFileDialog.getExistingDirectory(
            self, "Select Output Directory", os.path.dirname(self.current_audio_file)
        )
        
        if not output_dir:
            return
        
        # Check if we should use two-stems mode (only meaningful for Demucs v4)
        two_stems = False
        is_demucs_v4 = isinstance(self.current_model, DemucsModel) and not getattr(self.current_model, 'is_v3', False)
        if is_demucs_v4:
            two_stems = self.two_stems_checkbox.isChecked()
            
        self.worker = ProcessingThread(
            self.current_model,
            self.current_audio_file,
            output_dir,
            two_stems
        )
        
        self.worker.progress_updated.connect(self.update_progress)
        self.worker.processing_finished.connect(self.on_processing_finished)
        self.worker.processing_error.connect(self.on_processing_error)
        
        self.progress_bar.setVisible(True)
        self.process_button.setEnabled(False)
        self.worker.start()
    
    def update_progress(self, value):
        self.progress_bar.setValue(value)
    
    def on_processing_finished(self, output_dir):
        self.progress_bar.setVisible(False)
        self.process_button.setEnabled(True)
        
        QMessageBox.information(
            self,
            "Processing Complete",
            f"Audio separation complete! Files saved to:\n{output_dir}"
        )
    
    def on_processing_error(self, error_message):
        self.progress_bar.setVisible(False)
        self.process_button.setEnabled(True)
        
        QMessageBox.critical(
            self,
            "Processing Error",
            f"An error occurred during processing:\n{error_message}"
        )


class ProcessingThread(QThread):
    progress_updated = pyqtSignal(int)
    processing_finished = pyqtSignal(str)
    processing_error = pyqtSignal(str)
    
    def __init__(self, model, audio_file, output_dir, two_stems=False):
        super().__init__()
        self.model = model
        self.audio_file = audio_file
        self.output_dir = output_dir
        self.two_stems = two_stems
    
    def run(self):
        try:
            self.model.process(
                self.audio_file,
                self.output_dir,
                two_stems=self.two_stems,
                progress_callback=self.progress_updated.emit
            )
            self.processing_finished.emit(self.output_dir)
        except Exception as e:
            self.processing_error.emit(str(e)) 