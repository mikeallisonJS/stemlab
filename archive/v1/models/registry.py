"""Catalog of the supported separation models and a factory to create them."""

from typing import Dict, List, Optional, Tuple, Type

from models.bandsplit_model import BandSplitModel
from models.base_model import BaseModel
from models.d3net_model import D3NetModel
from models.demucs_model import DemucsModel
from models.spleeter_model import SpleeterModel


class ModelFamily:
    """
    A group of related models shown together in the user interface.

    Args:
        key: Stable identifier, used in saved settings
        title: Name shown to the user
        model_class: Class implementing the models
        models: Model name -> description
        default: Model offered by default for this family
    """

    def __init__(self, key: str, title: str, model_class: Type[BaseModel],
                 models: Dict[str, str], default: str):
        self.key = key
        self.title = title
        self.model_class = model_class
        self.models = models
        self.default = default

    @property
    def backend(self) -> str:
        return self.model_class.BACKEND


FAMILIES: Dict[str, ModelFamily] = {
    family.key: family
    for family in (
        ModelFamily("demucs4", "Demucs v4", DemucsModel, DemucsModel.V4_MODELS, "htdemucs"),
        ModelFamily("demucs3", "Demucs v3", DemucsModel, DemucsModel.V3_MODELS, "hdemucs_mmi"),
        ModelFamily("spleeter", "Spleeter", SpleeterModel, SpleeterModel.AVAILABLE_MODELS, "2stems"),
        ModelFamily("bandsplit", "Band-Split RoFormer", BandSplitModel,
                    BandSplitModel.AVAILABLE_MODELS, "vocals"),
        ModelFamily("d3net", "D3Net", D3NetModel, D3NetModel.AVAILABLE_MODELS, "standard"),
    )
}

# Backend key -> name shown to the user
BACKEND_TITLES = {
    "demucs": "Demucs (v3 and v4)",
    "spleeter": "Spleeter",
    "bandsplit": "Band-Split RoFormer",
    "d3net": "D3Net",
}


def model_id(family_key: str, model_name: str) -> str:
    """Identifier of a model, e.g. "demucs4:htdemucs"."""
    return f"{family_key}:{model_name}"


def parse_model_id(identifier: str) -> Optional[Tuple[str, str]]:
    """Split a model identifier into (family key, model name), or None if unknown."""
    family_key, _, model_name = identifier.partition(":")
    family = FAMILIES.get(family_key)
    if family is None or model_name not in family.models:
        return None
    return family_key, model_name


def default_model_ids() -> List[str]:
    """The models every installation offers: the default of each family."""
    return [model_id(family.key, family.default) for family in FAMILIES.values()]


def is_default(identifier: str) -> bool:
    return identifier in default_model_ids()


def display_name(identifier: str) -> str:
    """Name shown to the user, e.g. "Demucs v4 (htdemucs)"."""
    family_key, model_name = identifier.split(":", 1)
    return f"{FAMILIES[family_key].title} ({model_name})"


def create_model(identifier: str) -> BaseModel:
    """Create the model instance for an identifier."""
    parsed = parse_model_id(identifier)
    if parsed is None:
        raise ValueError(f"Unknown model: {identifier}")
    family_key, model_name = parsed
    return FAMILIES[family_key].model_class(model_name=model_name)


def backend_models() -> Dict[str, BaseModel]:
    """One representative model per backend, for installing and uninstalling."""
    representatives: Dict[str, BaseModel] = {}
    for family in FAMILIES.values():
        if family.backend not in representatives:
            representatives[family.backend] = family.model_class(model_name=family.default)
    return representatives


def find_model_id(name: str) -> Optional[str]:
    """
    Resolve a model given on the command line: either a full identifier
    ("demucs4:htdemucs") or just a model name unique across families ("htdemucs").
    """
    if parse_model_id(name):
        return name
    if name in FAMILIES:
        return model_id(name, FAMILIES[name].default)
    matches = [model_id(family.key, name) for family in FAMILIES.values() if name in family.models]
    return matches[0] if len(matches) == 1 else None
