from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
    QPushButton, QListWidget, QListWidgetItem, 
    QDialogButtonBox, QMessageBox
)
from PyQt6.QtCore import Qt, pyqtSignal

class ManageModelsDialog(QDialog):
    """
    Dialog for managing models, allowing users to remove custom models.
    """
    
    models_removed = pyqtSignal(list)  # list of tuples (model_name, model_type)
    
    def __init__(self, parent=None, model_collections=None):
        """
        Initialize the dialog with model collections.
        
        Args:
            parent: Parent widget
            model_collections: Dictionary of model collections with format:
                               {model_type: (display_name, available_models, model_class)}
        """
        super().__init__(parent)
        self.setWindowTitle("Manage Models")
        self.setMinimumSize(450, 400)
        self.model_collections = model_collections or {}
        
        self.init_ui()
        
    def init_ui(self):
        """Initialize the UI components."""
        layout = QVBoxLayout(self)
        
        # Header
        header = QLabel("<h2>Manage Custom Models</h2>")
        header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(header)
        
        # Instructions
        instructions = QLabel("Select models to remove from the application. Default models cannot be removed.")
        layout.addWidget(instructions)
        
        # List of custom models
        self.model_list = QListWidget()
        layout.addWidget(self.model_list)
        
        # Default models to exclude from removal
        default_models = {
            "DemucsModel": ["htdemucs", "htdemucs_ft", "htdemucs_6s"],
            "DemucsV3Model": ["demucs", "demucs_extra", "demucs_quantized", "tasnet", "tasnet_extra"],
            "SpleeterModel": ["2stems", "4stems", "5stems"],
            "BandSplitRNNModel": ["standard", "light"],
            "D3NetModel": ["standard", "optimized"]
        }
        
        # Add custom models to the list
        self.custom_models = []
        for model_type, (display_name, models_dict, _) in self.model_collections.items():
            default_for_type = default_models.get(model_type, [])
            for model_name in models_dict:
                if model_name not in default_for_type:
                    item = QListWidgetItem(f"{display_name} - {model_name}")
                    item.setData(Qt.ItemDataRole.UserRole, (model_name, model_type))
                    item.setCheckState(Qt.CheckState.Unchecked)
                    self.model_list.addItem(item)
                    self.custom_models.append((model_name, model_type))
        
        # If no custom models, show a message
        if not self.custom_models:
            self.model_list.setVisible(False)
            no_models_label = QLabel("No custom models found that can be removed.")
            no_models_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(no_models_label)
        
        # Button layout
        button_layout = QHBoxLayout()
        
        # Select All / None buttons
        if self.custom_models:
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
        # Collect models to remove
        models_to_remove = []
        items_to_remove = []
        
        for i in range(self.model_list.count()):
            item = self.model_list.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                model_name, model_type = item.data(Qt.ItemDataRole.UserRole)
                models_to_remove.append((model_name, model_type))
                items_to_remove.append(i)
        
        if not models_to_remove:
            return
        
        # Create a list of display names for confirmation
        remove_names = [f"{self.model_collections[t][0]} - {n}" for n, t in models_to_remove]
        
        # Confirm removal
        confirm = QMessageBox.question(
            self,
            "Confirm Removal",
            f"Remove these {len(models_to_remove)} models?\n\n" + "\n".join(remove_names),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        
        if confirm == QMessageBox.StandardButton.Yes:
            # Signal to parent that models should be removed
            self.models_removed.emit(models_to_remove)
            
            # Remove items from the list (in reverse order to not mess up indices)
            for i in sorted(items_to_remove, reverse=True):
                self.model_list.takeItem(i)
            
            # Update the custom_models list
            self.custom_models = [m for m in self.custom_models if m not in models_to_remove]
            
            # Update UI if no more custom models
            if not self.custom_models:
                self.model_list.setVisible(False)
                no_models_label = QLabel("No custom models found that can be removed.")
                no_models_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                self.layout().addWidget(no_models_label)
                self.remove_button.setEnabled(False) 