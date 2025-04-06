from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
    QPushButton, QListWidget, QListWidgetItem, 
    QDialogButtonBox, QMessageBox, QCheckBox
)
from PyQt6.QtCore import Qt, pyqtSignal

class ManageModelsDialog(QDialog):
    """
    Dialog for managing models, allowing users to remove custom models.
    """
    
    models_removed = pyqtSignal(list)  # list of tuples (model_name, model_type)
    models_uninstalled = pyqtSignal(list)  # list of tuples (model_name, model_type)
    
    def __init__(self, parent=None, model_collections=None, show_default_models=False):
        """
        Initialize the dialog with model collections.
        
        Args:
            parent: Parent widget
            model_collections: Dictionary of model collections with format:
                               {model_type: (display_name, available_models, model_class)}
            show_default_models: Whether to show default models (for uninstallation only)
        """
        super().__init__(parent)
        self.setWindowTitle("Manage Models")
        self.setMinimumSize(450, 450)
        self.model_collections = model_collections or {}
        self.show_default_models = show_default_models
        
        self.init_ui()
        
    def init_ui(self):
        """Initialize the UI components."""
        layout = QVBoxLayout(self)
        
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
            QCheckBox {
                color: #e0e0e0;
            }
            QCheckBox::indicator {
                width: 14px;
                height: 14px;
                border: 1px solid #3e3e42;
                background-color: #252526;
            }
            QCheckBox::indicator:checked {
                background-color: #007acc;
            }
        """)
        
        # Header
        if self.show_default_models:
            header = QLabel("<h2>Manage All Models</h2>")
        else:
            header = QLabel("<h2>Manage Custom Models</h2>")
        header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(header)
        
        # Instructions
        if self.show_default_models:
            instructions = QLabel(
                "Select models to manage. Default models can only be uninstalled, not removed from the list."
            )
        else:
            instructions = QLabel(
                "Select models to remove from the application. Default models cannot be removed."
            )
        layout.addWidget(instructions)
        
        # List of models
        self.model_list = QListWidget()
        # Set styling for dark mode
        self.model_list.setStyleSheet("""
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
            QListWidget::indicator {
                width: 14px;
                height: 14px;
                border: 1px solid #3e3e42;
                background-color: #2d2d30;
            }
            QListWidget::indicator:checked {
                background-color: #007acc;
            }
        """)
        layout.addWidget(self.model_list)
        
        # Default models to exclude from removal (but not uninstallation)
        default_models = {
            "DemucsModel": ["htdemucs", "htdemucs_ft", "htdemucs_6s"],
            "DemucsV3Model": ["demucs", "demucs_extra", "demucs_quantized", "tasnet", "tasnet_extra"],
            "SpleeterModel": ["2stems", "4stems", "5stems"],
            "BandSplitRNNModel": ["standard", "light"],
            "D3NetModel": ["standard", "optimized"]
        }
        
        # Add models to the list
        self.custom_models = []
        self.default_models = []
        
        for model_type, (display_name, models_dict, _) in self.model_collections.items():
            default_for_type = default_models.get(model_type, [])
            
            for model_name in models_dict:
                is_default = model_name in default_for_type
                if is_default and not self.show_default_models:
                    continue  # Skip default models unless showing all
                
                item = QListWidgetItem(f"{display_name} - {model_name}")
                item.setData(Qt.ItemDataRole.UserRole, (model_name, model_type))
                item.setCheckState(Qt.CheckState.Unchecked)
                
                # Mark default models with a different color and store in appropriate list
                if is_default:
                    item.setForeground(Qt.GlobalColor.cyan)
                    self.default_models.append((model_name, model_type))
                else:
                    # Set a clearly visible color for custom models
                    item.setForeground(Qt.GlobalColor.lightGray)
                    self.custom_models.append((model_name, model_type))
                
                # Set background color for better visibility in dark mode
                item.setBackground(Qt.GlobalColor.transparent)
                
                self.model_list.addItem(item)
        
        # If no models to display, show a message
        if not self.custom_models and not (self.default_models and self.show_default_models):
            self.model_list.setVisible(False)
            no_models_label = QLabel("No models found that can be managed.")
            no_models_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(no_models_label)
        
        # Complete uninstallation option
        self.uninstall_checkbox = QCheckBox("Completely uninstall model dependencies")
        self.uninstall_checkbox.setToolTip("This will remove all Python packages associated with the model")
        layout.addWidget(self.uninstall_checkbox)
        
        # Button layout
        button_layout = QHBoxLayout()
        
        # Select All / None buttons
        if self.custom_models or (self.default_models and self.show_default_models):
            select_all_button = QPushButton("Select All")
            select_all_button.clicked.connect(self.select_all)
            button_layout.addWidget(select_all_button)
            
            select_none_button = QPushButton("Select None")
            select_none_button.clicked.connect(self.select_none)
            button_layout.addWidget(select_none_button)
        
        button_layout.addStretch()
        
        # Remove button - only enabled when items are selected
        self.remove_button = QPushButton("Remove Selected")
        self.remove_button.setEnabled(False)
        self.remove_button.clicked.connect(self.remove_selected)
        button_layout.addWidget(self.remove_button)
        
        # Close button
        close_button = QPushButton("Close")
        close_button.clicked.connect(self.accept)
        button_layout.addWidget(close_button)
        
        layout.addLayout(button_layout)
        
        # Connect list item changed signal
        self.model_list.itemChanged.connect(self.update_remove_button)
    
    def update_remove_button(self):
        """Enable/disable the remove button based on selection."""
        has_selection = False
        for i in range(self.model_list.count()):
            if self.model_list.item(i).checkState() == Qt.CheckState.Checked:
                has_selection = True
                break
        
        self.remove_button.setEnabled(has_selection)
    
    def select_all(self):
        """Select all items in the list."""
        for i in range(self.model_list.count()):
            self.model_list.item(i).setCheckState(Qt.CheckState.Checked)
    
    def select_none(self):
        """Deselect all items in the list."""
        for i in range(self.model_list.count()):
            self.model_list.item(i).setCheckState(Qt.CheckState.Unchecked)
    
    def remove_selected(self):
        """Remove selected models."""
        # Collect models to remove or uninstall
        models_to_remove = []  # For custom models to remove from UI
        models_to_uninstall = []  # For all models to uninstall
        items_to_remove = []
        default_models_selected = 0
        
        for i in range(self.model_list.count()):
            item = self.model_list.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                model_name, model_type = item.data(Qt.ItemDataRole.UserRole)
                
                # Check if this is a default model
                is_default = False
                for default_name, default_type in self.default_models:
                    if model_name == default_name and model_type == default_type:
                        is_default = True
                        default_models_selected += 1
                        break
                
                # Only remove custom models, but can uninstall any model
                if self.uninstall_checkbox.isChecked():
                    models_to_uninstall.append((model_name, model_type))
                
                if not is_default:
                    models_to_remove.append((model_name, model_type))
                    items_to_remove.append(i)
        
        if not models_to_remove and not models_to_uninstall:
            return
        
        # Build message for confirmation
        message_parts = []
        
        # Get display names for removal
        if models_to_remove:
            remove_names = [f"{self.model_collections[t][0]} - {n}" for n, t in models_to_remove]
            message_parts.append(f"Remove these {len(models_to_remove)} models from the list:\n• " + 
                               "\n• ".join(remove_names))
        
        # Get display names for uninstallation
        if models_to_uninstall:
            uninstall_names = [f"{self.model_collections[t][0]} - {n}" for n, t in models_to_uninstall]
            message_parts.append(f"Uninstall dependencies for these {len(models_to_uninstall)} models:\n• " + 
                               "\n• ".join(uninstall_names))
        
        # Put together the message
        message = "\n\n".join(message_parts)
        
        # Add warning for default models if necessary
        if default_models_selected > 0 and self.uninstall_checkbox.isChecked():
            message += (
                "\n\nNote: Default models can be uninstalled but will remain in the model list. "
                "You can reinstall them later if needed."
            )
        
        # Add warning about dependencies
        if self.uninstall_checkbox.isChecked():
            message += (
                "\n\nWARNING: You've selected to completely uninstall the model dependencies. "
                "This will remove the Python packages required by these models, "
                "which may affect other models of the same type."
            )
        
        # Confirm removal
        confirm = QMessageBox.question(
            self,
            "Confirm Action",
            message,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        
        if confirm == QMessageBox.StandardButton.Yes:
            # Signal to parent if uninstallation is needed
            if models_to_uninstall and self.uninstall_checkbox.isChecked():
                self.models_uninstalled.emit(models_to_uninstall)
            
            # Signal models to be removed from the selection
            if models_to_remove:
                self.models_removed.emit(models_to_remove)
            
            # Remove items from the list (in reverse order to not mess up indices)
            for i in sorted(items_to_remove, reverse=True):
                self.model_list.takeItem(i)
            
            # Update the custom_models list
            self.custom_models = [m for m in self.custom_models if m not in models_to_remove]
            
            # Update UI if no more models
            if not self.custom_models and not self.default_models:
                self.model_list.setVisible(False)
                no_models_label = QLabel("No models found that can be managed.")
                no_models_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                self.layout().addWidget(no_models_label)
                self.remove_button.setEnabled(False) 