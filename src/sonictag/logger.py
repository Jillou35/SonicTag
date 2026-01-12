import logging

logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("SonicTag")
logger.setLevel(logging.INFO)
