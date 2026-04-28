# utils.py
# Author information: Sai Dore
from pathlib import Path  
import logging  
import yaml  
import os

def get_env_or_default(env_name: str, default_value: str) -> str:
    """Return environment value if set, otherwise use default."""
    return os.getenv(env_name, default_value)

def load_yaml_file(file_path: str | Path) -> dict:
    """Load one YAML config file and return it as a dictionary."""

    file_path = Path(file_path)
    with file_path.open("r", encoding="utf-8") as file:
        data = yaml.safe_load(file)

    return data if data is not None else {}

def setup_logging(log_file: str = "logs/pipeline.log") -> logging.Logger:
    """Set up project logging for both console and file output."""

    # Create the logs folder if it does not already exist and get main logger
    log_path = Path(log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("weather_pipeline")

    if logger.handlers:    # Avoid adding duplicate handlers 
        return logger

    logger.setLevel(logging.INFO)
    # Create a consistent log message format
    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Send logs to a file
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(formatter)

    # Send logs to the terminal
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)

    # Attach both handlers to the logger
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    # Keep logs from being duplicated by parent loggers
    logger.propagate = False

    return logger