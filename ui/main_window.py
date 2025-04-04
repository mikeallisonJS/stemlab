import os
import sys
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
    QLabel, QPushButton, QComboBox, QFileDialog,
    QProgressBar, QMessageBox, QFrame
)
from PyQt6.QtCore import Qt, QMimeData, QUrl, pyqtSignal, QThread
from PyQt6.QtGui import QDragEnterEvent, QDropEvent

from models.demucs_model import DemucsModel
from ui.drop_area import DropArea


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("CaptainStems")
        self.setMinimumSize(800, 600)
        
        # Models
        self.models = {
            "Demucs v4": DemucsModel()
        }
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
        
        model_layout.addWidget(model_label)
        model_layout.addWidget(self.model_combo)
        
        # Add install button
        self.install_button = QPushButton("Install Model")
        self.install_button.setVisible(False)
        self.install_button.clicked.connect(self.install_model)
        model_layout.addWidget(self.install_button)
        
        model_layout.addStretch()
        
        layout.addLayout(model_layout)
        
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
    
    def on_model_changed(self, index):
        model_name = self.model_combo.itemData(index)
        self.current_model = self.models.get(model_name)
        
        # Check if model is available
        if hasattr(self.current_model, 'available'):
            self.install_button.setVisible(not self.current_model.available)
        else:
            self.install_button.setVisible(False)
            
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
            
        self.worker = ProcessingThread(
            self.current_model,
            self.current_audio_file,
            output_dir
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
    
    def __init__(self, model, audio_file, output_dir):
        super().__init__()
        self.model = model
        self.audio_file = audio_file
        self.output_dir = output_dir
    
    def run(self):
        try:
            self.model.process(
                self.audio_file,
                self.output_dir,
                progress_callback=self.progress_updated.emit
            )
            self.processing_finished.emit(self.output_dir)
        except Exception as e:
            self.processing_error.emit(str(e)) 