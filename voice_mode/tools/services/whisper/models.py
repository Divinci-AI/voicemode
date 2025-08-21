"""Whisper model registry and utilities."""

import os
from pathlib import Path
from typing import Dict, List, Optional, TypedDict
from voice_mode.config import WHISPER_MODEL_PATH, WHISPER_MODEL


class ModelInfo(TypedDict):
    """Information about a Whisper model."""
    size_mb: int  # Download size in MB
    languages: str  # Language support description
    description: str  # Brief description
    filename: str  # Expected filename when downloaded


# Registry of all available Whisper models
WHISPER_MODELS: Dict[str, ModelInfo] = {
    "tiny": {
        "size_mb": 39,
        "languages": "Multilingual",
        "description": "Fastest, least accurate",
        "filename": "ggml-tiny.bin"
    },
    "tiny.en": {
        "size_mb": 39,
        "languages": "English only",
        "description": "Fastest English model",
        "filename": "ggml-tiny.en.bin"
    },
    "base": {
        "size_mb": 142,
        "languages": "Multilingual",
        "description": "Good balance of speed and accuracy",
        "filename": "ggml-base.bin"
    },
    "base.en": {
        "size_mb": 142,
        "languages": "English only",
        "description": "Good English model",
        "filename": "ggml-base.en.bin"
    },
    "small": {
        "size_mb": 466,
        "languages": "Multilingual",
        "description": "Better accuracy, slower",
        "filename": "ggml-small.bin"
    },
    "small.en": {
        "size_mb": 466,
        "languages": "English only",
        "description": "Better English accuracy",
        "filename": "ggml-small.en.bin"
    },
    "medium": {
        "size_mb": 1500,
        "languages": "Multilingual",
        "description": "High accuracy, slow",
        "filename": "ggml-medium.bin"
    },
    "medium.en": {
        "size_mb": 1500,
        "languages": "English only",
        "description": "High English accuracy",
        "filename": "ggml-medium.en.bin"
    },
    "large-v1": {
        "size_mb": 2900,
        "languages": "Multilingual",
        "description": "Original large model",
        "filename": "ggml-large-v1.bin"
    },
    "large-v2": {
        "size_mb": 2900,
        "languages": "Multilingual",
        "description": "Improved large model (recommended)",
        "filename": "ggml-large-v2.bin"
    },
    "large-v3": {
        "size_mb": 3100,
        "languages": "Multilingual",
        "description": "Latest large model",
        "filename": "ggml-large-v3.bin"
    },
    "large-v3-turbo": {
        "size_mb": 1600,
        "languages": "Multilingual",
        "description": "Faster large model with good accuracy",
        "filename": "ggml-large-v3-turbo.bin"
    }
}


def get_model_directory() -> Path:
    """Get the directory where Whisper models are stored."""
    # Use the configured path from config.py
    model_dir = Path(WHISPER_MODEL_PATH)
    
    # If config path doesn't exist, check service installation
    if not model_dir.exists():
        service_models = Path.home() / ".voicemode" / "services" / "whisper" / "models"
        if service_models.exists():
            return service_models
    
    return model_dir


def get_current_model() -> str:
    """Get the currently selected Whisper model."""
    # Use the configured model from config.py
    model = WHISPER_MODEL
    
    # Validate it's a known model
    if model not in WHISPER_MODELS:
        return "large-v2"  # Default fallback
    
    return model


def is_model_installed(model_name: str) -> bool:
    """Check if a model is installed."""
    if model_name not in WHISPER_MODELS:
        return False
    
    model_dir = get_model_directory()
    model_info = WHISPER_MODELS[model_name]
    model_path = model_dir / model_info["filename"]
    
    return model_path.exists()


def has_coreml_model(model_name: str) -> bool:
    """Check if a Core ML model is available for the given model.
    
    Core ML models are only used on macOS with Apple Silicon.
    They have the extension .mlmodelc and provide faster inference.
    """
    import platform
    
    # Core ML is only relevant on macOS
    if platform.system() != "Darwin":
        return False
    
    if model_name not in WHISPER_MODELS:
        return False
    
    model_dir = get_model_directory()
    model_info = WHISPER_MODELS[model_name]
    
    # Core ML models can be either compiled (.mlmodelc) or package (.mlpackage)
    # Check for both formats
    coreml_compiled = model_dir / f"ggml-{model_name}-encoder.mlmodelc"
    coreml_package = model_dir / f"coreml-encoder-{model_name}.mlpackage"
    
    return coreml_compiled.exists() or coreml_package.exists()


def get_installed_models() -> List[str]:
    """Get list of installed models."""
    installed = []
    for model_name in WHISPER_MODELS:
        if is_model_installed(model_name):
            installed.append(model_name)
    return installed


def get_total_size(models: Optional[List[str]] = None) -> int:
    """Get total size of models in MB.
    
    Args:
        models: List of model names. If None, uses all models.
    
    Returns:
        Total size in MB
    """
    if models is None:
        models = list(WHISPER_MODELS.keys())
    
    total = 0
    for model in models:
        if model in WHISPER_MODELS:
            total += WHISPER_MODELS[model]["size_mb"]
    
    return total


def format_size(size_mb: int) -> str:
    """Format size in MB to human-readable string."""
    if size_mb < 1000:
        return f"{size_mb} MB"
    else:
        size_gb = size_mb / 1000
        return f"{size_gb:.1f} GB"


def is_macos() -> bool:
    """Check if running on macOS."""
    import platform
    return platform.system() == "Darwin"


def is_apple_silicon() -> bool:
    """Check if running on Apple Silicon (M1/M2/M3/M4)."""
    import platform
    return platform.system() == "Darwin" and platform.machine() == "arm64"


def set_current_model(model_name: str) -> None:
    """Set the current active Whisper model.
    
    Args:
        model_name: Name of the model to set as active
    
    Updates the voicemode.env configuration file for persistence.
    """
    from pathlib import Path
    import re
    
    # Configuration file path
    config_path = Path.home() / ".voicemode" / "voicemode.env"
    
    # Ensure directory exists
    config_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Read existing configuration
    config = {}
    if config_path.exists():
        with open(config_path, 'r') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                match = re.match(r'^([A-Z_]+)=(.*)$', line)
                if match:
                    key, value = match.groups()
                    value = value.strip('"').strip("'")
                    config[key] = value
    
    # Update the model
    config['VOICEMODE_WHISPER_MODEL'] = model_name
    
    # Write back to file, preserving structure
    lines = []
    updated_keys = set()
    
    if config_path.exists():
        with open(config_path, 'r') as f:
            for line in f:
                stripped = line.strip()
                if stripped and not stripped.startswith('#'):
                    match = re.match(r'^([A-Z_]+)=', stripped)
                    if match:
                        key = match.group(1)
                        if key == 'VOICEMODE_WHISPER_MODEL':
                            lines.append(f"VOICEMODE_WHISPER_MODEL={model_name}\n")
                            updated_keys.add(key)
                        elif key in config:
                            lines.append(f"{key}={config[key]}\n")
                            updated_keys.add(key)
                        else:
                            lines.append(line)
                    else:
                        lines.append(line)
                else:
                    lines.append(line)
    
    # Add VOICEMODE_WHISPER_MODEL if it wasn't in the file
    if 'VOICEMODE_WHISPER_MODEL' not in updated_keys:
        if lines and not lines[-1].strip() == '':
            lines.append('\n')
        lines.append("# Whisper Configuration\n")
        lines.append(f"VOICEMODE_WHISPER_MODEL={model_name}\n")
    
    # Write the updated configuration
    with open(config_path, 'w') as f:
        f.writelines(lines)