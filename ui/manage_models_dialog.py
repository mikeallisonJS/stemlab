from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QListWidget, QListWidgetItem,
    QMessageBox, QTreeWidget, QTreeWidgetItem, QHeaderView
)
from PyQt6.QtCore import Qt, pyqtSignal

from core import paths
from models import registry
from ui.install_dialog import InstallDialog
from ui.workers import FunctionWorker


class ManageModelsDialog(QDialog):
    """
    Dialog for managing models: installing and uninstalling the model
    backends, and removing custom models from the selection list.
    """

    models_removed = pyqtSignal(list)  # list of model identifiers
    backends_changed = pyqtSignal()  # a backend was installed or uninstalled

    def __init__(self, parent=None, custom_models=None):
        """
        Initialize the dialog.

        Args:
            parent: Parent widget
            custom_models: Identifiers of the models the user added to the
                           selection list (default models cannot be removed)
        """
        super().__init__(parent)
        self.setWindowTitle("Manage Models")
        self.setMinimumSize(620, 520)
        self.custom_models = list(custom_models or [])
        self.backends = registry.backend_models()
        self.size_worker = None
        self.size_outdated = False

        self.init_ui()
        self.refresh_backends()

    def init_ui(self):
        """Initialize the UI components."""
        layout = QVBoxLayout(self)

        # Backends
        header = QLabel("<h2>Manage Models</h2>")
        header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(header)

        instructions = QLabel(
            "Each model family is installed into its own environment, so installing or "
            "removing one never affects the others."
        )
        instructions.setWordWrap(True)
        layout.addWidget(instructions)

        self.backend_tree = QTreeWidget()
        self.backend_tree.setHeaderLabels(["Model family", "Status", "Disk usage"])
        self.backend_tree.setRootIsDecorated(False)
        self.backend_tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.backend_tree.header().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.backend_tree.header().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        for backend in self.backends:
            item = QTreeWidgetItem([registry.BACKEND_TITLES.get(backend, backend), "", ""])
            item.setData(0, Qt.ItemDataRole.UserRole, backend)
            self.backend_tree.addTopLevelItem(item)
        self.backend_tree.currentItemChanged.connect(self.update_buttons)
        layout.addWidget(self.backend_tree)

        backend_buttons = QHBoxLayout()
        self.install_button = QPushButton("Install")
        self.install_button.clicked.connect(self.install_selected)
        backend_buttons.addWidget(self.install_button)
        self.uninstall_button = QPushButton("Uninstall")
        self.uninstall_button.clicked.connect(self.uninstall_selected)
        backend_buttons.addWidget(self.uninstall_button)
        backend_buttons.addStretch()
        layout.addLayout(backend_buttons)

        # Custom models
        custom_header = QLabel("<b>Custom models in the selection list</b>")
        layout.addWidget(custom_header)

        # List of models
        self.model_list = QListWidget()
        for identifier in self.custom_models:
            item = QListWidgetItem(registry.display_name(identifier))
            item.setData(Qt.ItemDataRole.UserRole, identifier)
            item.setCheckState(Qt.CheckState.Unchecked)
            self.model_list.addItem(item)
        layout.addWidget(self.model_list)

        self.no_models_label = QLabel(
            "No custom models. Use \"Advanced Models...\" to add more models to the list."
        )
        self.no_models_label.setEnabled(False)
        layout.addWidget(self.no_models_label)

        # Button layout
        button_layout = QHBoxLayout()

        # Remove button - only enabled when items are selected
        self.remove_button = QPushButton("Remove Selected")
        self.remove_button.setEnabled(False)
        self.remove_button.clicked.connect(self.remove_selected)
        button_layout.addWidget(self.remove_button)

        button_layout.addStretch()

        # Close button
        close_button = QPushButton("Close")
        close_button.clicked.connect(self.accept)
        button_layout.addWidget(close_button)

        layout.addLayout(button_layout)

        # Connect list item changed signal
        self.model_list.itemChanged.connect(self.update_remove_button)
        self.update_custom_visibility()
        self.backend_tree.setCurrentItem(self.backend_tree.topLevelItem(0))

    # Backends ---------------------------------------------------------------

    def selected_backend(self):
        item = self.backend_tree.currentItem()
        return item.data(0, Qt.ItemDataRole.UserRole) if item else None

    def refresh_backends(self):
        """Update the status of every backend and measure disk usage in the background."""
        for index in range(self.backend_tree.topLevelItemCount()):
            item = self.backend_tree.topLevelItem(index)
            model = self.backends[item.data(0, Qt.ItemDataRole.UserRole)]
            model.available = model.check_dependencies()
            item.setText(1, "Installed" if model.available else "Not installed")
            item.setText(2, "..." if model.available else "")
        self.update_buttons()
        self.measure_sizes()

    def measure_sizes(self):
        """Measure the disk usage of the installed backends on a worker thread."""
        if self.size_worker is not None:
            # Measure again once the running measurement is done
            self.size_outdated = True
            return
        self.size_outdated = False
        models = {key: model for key, model in self.backends.items() if model.available}
        self.size_worker = FunctionWorker(
            lambda: {key: model.installed_size() for key, model in models.items()}, self
        )
        self.size_worker.succeeded.connect(self.on_sizes_measured)
        self.size_worker.finished.connect(self.on_size_worker_finished)
        self.size_worker.start()

    def on_sizes_measured(self, sizes):
        for index in range(self.backend_tree.topLevelItemCount()):
            item = self.backend_tree.topLevelItem(index)
            backend = item.data(0, Qt.ItemDataRole.UserRole)
            if backend in sizes and self.backends[backend].available:
                item.setText(2, paths.format_size(sizes[backend]))

    def on_size_worker_finished(self):
        self.size_worker = None
        if self.size_outdated:
            self.measure_sizes()

    def update_buttons(self, *_args):
        backend = self.selected_backend()
        installed = bool(backend) and self.backends[backend].available
        self.install_button.setEnabled(bool(backend) and not installed)
        self.uninstall_button.setEnabled(installed)

    def install_selected(self):
        backend = self.selected_backend()
        if backend and self.install_backend(self, self.backends[backend]):
            self.backends_changed.emit()
        self.refresh_backends()

    def uninstall_selected(self):
        backend = self.selected_backend()
        if not backend:
            return
        title = registry.BACKEND_TITLES.get(backend, backend)
        confirm = QMessageBox.question(
            self,
            "Confirm Uninstall",
            f"Uninstall {title}?\n\n"
            "This deletes its environment and downloaded model weights. "
            "The models stay in the selection list and can be installed again later.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        InstallDialog.run(self, self.backends[backend], title, uninstall=True)
        self.backends_changed.emit()
        self.refresh_backends()

    @staticmethod
    def install_backend(parent, model):
        """
        Ask for confirmation, then install the backend of a model.

        Returns:
            bool: True if the backend was installed
        """
        title = registry.BACKEND_TITLES.get(model.BACKEND, model.BACKEND)
        confirm = QMessageBox.question(
            parent,
            "Install Model",
            f"Install {title}?\n\n"
            f"Download size: {model.INSTALL_SIZE}.\n"
            f"It is installed into its own environment in:\n{model.env.path}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return False
        return InstallDialog.run(parent, model, title)

    # Custom models ----------------------------------------------------------

    def update_custom_visibility(self):
        has_models = self.model_list.count() > 0
        self.model_list.setVisible(has_models)
        self.no_models_label.setVisible(not has_models)

    def update_remove_button(self):
        """Enable/disable the remove button based on selection."""
        has_selection = False
        for i in range(self.model_list.count()):
            if self.model_list.item(i).checkState() == Qt.CheckState.Checked:
                has_selection = True
                break

        self.remove_button.setEnabled(has_selection)

    def remove_selected(self):
        """Remove selected models."""
        models_to_remove = []
        items_to_remove = []

        for i in range(self.model_list.count()):
            item = self.model_list.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                models_to_remove.append(item.data(Qt.ItemDataRole.UserRole))
                items_to_remove.append(i)

        if not models_to_remove:
            return

        # Signal models to be removed from the selection
        self.models_removed.emit(models_to_remove)

        # Remove items from the list (in reverse order to not mess up indices)
        for i in sorted(items_to_remove, reverse=True):
            self.model_list.takeItem(i)

        # Update the custom_models list
        self.custom_models = [m for m in self.custom_models if m not in models_to_remove]
        self.update_custom_visibility()
        self.update_remove_button()

    def done(self, result):
        self.size_outdated = False
        if self.size_worker is not None:
            self.size_worker.wait()
        super().done(result)
