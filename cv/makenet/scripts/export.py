# Copyright (c) 2021-2022, NVIDIA CORPORATION.  All rights reserved.

"""Export a classification model."""
import os
import logging

from cv.makenet.config.hydra_runner import hydra_runner
from cv.makenet.config.default_config import ExperimentConfig
from cv.makenet.export.classification_exporter import Exporter
logger = logging.getLogger(__name__)


def run_export(cfg=None):
    exporter = Exporter(config=cfg)
    exporter.export()


spec_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
@hydra_runner(
    config_path=os.path.join(spec_root, "experiment_specs"),
    config_name="export", schema=ExperimentConfig
)
def main(cfg: ExperimentConfig) -> None:
    """Wrapper function for continuous training of MakeNet application.
    """
    run_export(cfg=cfg)
    logger.info("Export finished successfully.")


if __name__ == "__main__":
    main()
