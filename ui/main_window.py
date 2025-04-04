import os
import sys
import tempfile
import subprocess
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
    QLabel, QPushButton, QComboBox, QFileDialog,
    QProgressBar, QMessageBox, QFrame, QCheckBox, QDialog
)
from PyQt6.QtCore import Qt, QMimeData, QUrl, pyqtSignal, QThread
from PyQt6.QtGui import QDragEnterEvent, QDropEvent

from models.demucs_model import DemucsModel
from models.spleeter_model import SpleeterModel
from models.bandsplit_model import BandSplitRNNModel
from models.d3net_model import D3NetModel
from ui.drop_area import DropArea
from ui.model_selection_dialog import ModelSelectionDialog
from ui.manage_models_dialog import ManageModelsDialog
from ui.results_window import ResultsWindow


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
        
        # Create model collections for the selection dialog
        self.model_collections = {
            "DemucsModel": ("Demucs v4", self.demucs_models, DemucsModel),
            "DemucsV3Model": ("Demucs v3", 
                            {k: v for k, v in self.demucs_models.items() 
                             if k in ["demucs", "demucs_extra", "demucs_quantized", "tasnet", "tasnet_extra"]},
                            DemucsModel),
            "SpleeterModel": ("Spleeter", self.spleeter_models, SpleeterModel),
            "BandSplitRNNModel": ("Band-Split RNN", self.bandsplit_models, BandSplitRNNModel),
            "D3NetModel": ("D3Net", self.d3net_models, D3NetModel)
        }
        
        self.current_model = None
        self.current_audio_file = None
        self.results_window = None
        
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
        
        # Add manage models button
        self.manage_models_button = QPushButton("Manage Models...")
        self.manage_models_button.clicked.connect(self.show_manage_models_dialog)
        
        model_layout.addWidget(model_label)
        model_layout.addWidget(self.model_combo)
        model_layout.addWidget(self.advanced_model_button)
        model_layout.addWidget(self.manage_models_button)
        
        # Add install button
        self.install_button = QPushButton("Install Model")
        self.install_button.setVisible(False)
        self.install_button.clicked.connect(self.install_model)
        model_layout.addWidget(self.install_button)
        
        # Add remove button
        self.remove_button = QPushButton("Remove Model")
        self.remove_button.setVisible(False)
        self.remove_button.clicked.connect(self.remove_model)
        model_layout.addWidget(self.remove_button)
        
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
        # Use the new advanced model selection dialog
        result = ModelSelectionDialog.get_model(self, self.model_collections)
        
        if result:
            model_name, model_type, display_name = result
            
            # Check if we already have this model
            if display_name not in self.models:
                # Create the model based on type
                if model_type == "DemucsModel" or model_type == "DemucsV3Model":
                    if model_type == "DemucsV3Model":
                        # Set is_v3 flag for Demucs v3 models
                        self.models[display_name] = DemucsModel(model_name=model_name, is_v3=True)
                    else:
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
    
    def show_manage_models_dialog(self):
        """
        Shows a dialog for managing (removing) models.
        """
        dialog = ManageModelsDialog(self, self.model_collections)
        dialog.models_removed.connect(self.remove_models_batch)
        dialog.exec()
    
    def remove_models_batch(self, models_to_remove):
        """Remove multiple models at once."""
        if not models_to_remove:
            return
            
        # Get display names for all models to be removed
        display_names_to_remove = []
        
        for model_name, model_type in models_to_remove:
            # Find the display name used in our combo box
            for display_name, model in self.models.items():
                if (isinstance(model, self.model_collections[model_type][2]) and 
                    getattr(model, 'model_name', None) == model_name):
                    display_names_to_remove.append(display_name)
                    break
        
        # Remove each model
        removed_count = 0
        for display_name in display_names_to_remove:
            # Find its index in the combo box
            index = self.model_combo.findData(display_name)
            if index >= 0:
                # Remove from combo box
                self.model_combo.removeItem(index)
                # Remove from models dictionary
                self.models.pop(display_name)
                removed_count += 1
        
        # Select the first model in the list
        if self.model_combo.count() > 0:
            self.model_combo.setCurrentIndex(0)
            first_model_name = self.model_combo.itemData(0)
            self.current_model = self.models.get(first_model_name)
        else:
            self.current_model = None
        
        # Update UI
        self.update_ui_state()
        
        # Show confirmation
        if removed_count > 0:
            QMessageBox.information(
                self,
                "Models Removed",
                f"{removed_count} model{'s' if removed_count > 1 else ''} removed successfully."
            )
    
    def on_model_changed(self, index):
        model_name = self.model_combo.itemData(index)
        self.current_model = self.models.get(model_name)
        
        # Check if model is available
        if hasattr(self.current_model, 'available'):
            self.install_button.setVisible(not self.current_model.available)
        else:
            self.install_button.setVisible(False)
        
        # Show remove button for non-default models
        # Default models are the first 5 models added during initialization
        default_models = [
            "Demucs v4 (default)", 
            "Demucs v3 (default)", 
            "Spleeter (2stems)", 
            "Band-Split RNN (standard)",
            "D3Net (standard)"
        ]
        can_remove = model_name not in default_models
        self.remove_button.setVisible(can_remove)
        
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
            
        # Update UI state to reflect current model and file status
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
                # Update the model's available property
                if hasattr(self.current_model, 'available'):
                    self.current_model.available = True
                
                # Show success message
                QMessageBox.information(
                    self, 
                    "Installation Successful", 
                    f"The {self.current_model.name} model was installed successfully."
                )
                
                # Update the combo box to remove "(not installed)" text
                current_index = self.model_combo.currentIndex()
                model_name = self.model_combo.itemData(current_index)
                self.model_combo.setItemText(current_index, model_name)
                
                # Hide the install button
                self.install_button.setVisible(False)
                
                # Update UI state to enable processing button if a file is already selected
                self.update_ui_state()
                
                # If a file was previously selected, ensure the drop area shows it
                if self.current_audio_file:
                    filename = os.path.basename(self.current_audio_file)
                    self.drop_area.set_file(filename)
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
        # Check model availability
        model_available = True
        if hasattr(self.current_model, 'available'):
            model_available = self.current_model.available
            
        # Check if we can process
        can_process = (
            self.current_model is not None and 
            self.current_audio_file is not None and
            model_available
        )
        
        # Enable or disable the process button
        self.process_button.setEnabled(can_process)
        
        # Update drop area message based on state
        if not model_available and self.current_model is not None:
            # Model not installed
            self.drop_area.set_message(f"Model not installed. Click 'Install Model' first.")
        elif self.current_audio_file is None:
            # No file selected yet
            self.drop_area.set_message("Drag an audio file here")
        elif can_process:
            # Both model and file are ready
            filename = os.path.basename(self.current_audio_file)
            self.drop_area.set_file(filename)
        else:
            # Default message
            self.drop_area.set_message("Drag an audio file here")
    
    def process_audio(self):
        if not self.current_model or not self.current_audio_file:
            return
            
        # Create a model-specific temporary directory
        model_name = self.current_model.__class__.__name__
        model_variant = getattr(self.current_model, 'model_name', 'default')
        output_dir = tempfile.mkdtemp(prefix=f"captainstems_{model_name}_{model_variant}_")
        
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
        
        # Show the results window with processed stems
        display_name = self.model_combo.currentText().split(" (not installed)")[0]
        self.results_window = ResultsWindow(
            parent=self,
            source_dir=output_dir,
            source_audio=self.current_audio_file,
            model_name=display_name
        )
        self.results_window.show()
    
    def on_processing_error(self, error_message):
        self.progress_bar.setVisible(False)
        self.process_button.setEnabled(True)
        
        QMessageBox.critical(
            self,
            "Processing Error",
            f"An error occurred during audio separation:\n{error_message}"
        )

    def remove_model(self):
        if not self.current_model:
            return
        
        # Get current model info
        current_index = self.model_combo.currentIndex()
        model_name = self.model_combo.itemData(current_index)
        
        # Confirm removal
        confirmation = QMessageBox.question(
            self,
            "Confirm Removal",
            f"Are you sure you want to remove the model '{model_name}'?\n\n"
            "This will only remove it from the selection list, not from your system.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        
        if confirmation == QMessageBox.StandardButton.Yes:
            # Remove the model
            self.model_combo.removeItem(current_index)
            self.models.pop(model_name)
            
            # Select the first model in the list
            if self.model_combo.count() > 0:
                self.model_combo.setCurrentIndex(0)
                first_model_name = self.model_combo.itemData(0)
                self.current_model = self.models.get(first_model_name)
            else:
                self.current_model = None
            
            # Update UI
            self.update_ui_state()
            
            # Show confirmation
            QMessageBox.information(
                self,
                "Model Removed",
                f"The model '{model_name}' has been removed from the selection list."
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
            result_dir = self.model.process(
                self.audio_file,
                self.output_dir,
                two_stems=self.two_stems,
                progress_callback=self.progress_updated.emit
            )
            self.processing_finished.emit(result_dir)
        except Exception as e:
            self.processing_error.emit(str(e)) 