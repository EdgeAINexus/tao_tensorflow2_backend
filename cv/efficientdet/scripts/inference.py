# Copyright (c) 2022-2023, NVIDIA CORPORATION.  All rights reserved.

"""EfficientDet standalone inference."""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import os
import tensorflow as tf
# from tensorflow.python.framework.ops import disable_eager_execution
from tensorflow.python.util import deprecation
import warnings

from common.hydra.hydra_runner import hydra_runner
import common.logging.logging as status_logging
import common.no_warning # noqa pylint: disable=W0611

from cv.efficientdet.config.default_config import ExperimentConfig
from cv.efficientdet.inferencer import inference, inference_trt
from cv.efficientdet.utils import helper, hparams_config, label_utils
from cv.efficientdet.utils.config_utils import generate_params_from_cfg
from cv.efficientdet.utils.horovod_utils import initialize

deprecation._PRINT_DEPRECATION_WARNINGS = False

os.environ['CUDA_VISIBLE_DEVICES'] = '0'
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'  # or any {'0', '1', '2'}
os.environ["TF_CPP_VMODULE"] = 'non_max_suppression_op=0,generate_box_proposals_op=0,executor=0'
supported_img_format = ['.jpg', '.jpeg', '.JPG', '.JPEG', '.png', '.PNG']


def get_label_dict(label_txt):
    """Create label dict from txt file."""
    with open(label_txt, 'r', encoding='utf-8') as f:
        labels = f.readlines()
        return {i + 1: label[:-1] for i, label in enumerate(labels)}


def batch_generator(iterable, batch_size=1):
    """Load a list of image paths in batches.

    Args:
        iterable: a list of image paths
        n: batch size
    """
    total_len = len(iterable)
    for ndx in range(0, total_len, batch_size):
        yield iterable[ndx:min(ndx + batch_size, total_len)]


def infer_tlt(cfg, label_id_mapping, min_score_thresh, ci_run=False):
    """Launch EfficientDet TLT model Inference."""
    # disable_eager_execution()
    tf.autograph.set_verbosity(0)
    # Parse and update hparams
    MODE = 'infer'
    config = hparams_config.get_detection_config(cfg.model.name)
    config.update(generate_params_from_cfg(config, cfg, mode='infer'))
    params = config.as_dict()
    initialize(config, training=False, ci_run=ci_run)
    if not os.path.exists(cfg.inference.output_dir):
        os.makedirs(cfg.inference.output_dir, exist_ok=True)
    # Load model from graph json
    model = helper.load_model(cfg.inference.model_path, cfg, MODE, is_qat=cfg.train.qat)

    infer_model = inference.InferenceModel(model, config.image_size, params,
                                           cfg.inference.batch_size,
                                           label_id_mapping=label_id_mapping,
                                           min_score_thresh=min_score_thresh,
                                           max_boxes_to_draw=cfg.inference.max_boxes_to_draw)
    imgpath_list = [os.path.join(cfg.inference.image_dir, imgname)
                    for imgname in sorted(os.listdir(cfg.inference.image_dir))
                    if os.path.splitext(imgname)[1].lower()
                    in supported_img_format]
    for image_paths in batch_generator(imgpath_list, cfg.inference.batch_size):
        infer_model.visualize_detections(
            image_paths,
            cfg.inference.output_dir,
            cfg.inference.dump_label)


def infer_trt(cfg, label_id_mapping, min_score_thresh):
    """Run trt inference."""
    output_dir = os.path.realpath(cfg.inference.output_dir)
    os.makedirs(output_dir, exist_ok=True)
    trt_infer = inference_trt.TensorRTInfer(
        cfg.inference.model_path,
        label_id_mapping,
        min_score_thresh)
    trt_infer.visualize_detections(
        cfg.inference.image_dir,
        cfg.inference.output_dir,
        cfg.inference.dump_label)


spec_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@hydra_runner(
    config_path=os.path.join(spec_root, "experiment_specs"),
    config_name="inference", schema=ExperimentConfig
)
def main(cfg: ExperimentConfig):
    """Wrapper function for EfficientDet inference."""
    # set up status logger
    status_file = os.path.join(cfg.results_dir, "status.json")
    status_logging.set_status_logger(
        status_logging.StatusLogger(
            filename=status_file,
            is_master=True,
            verbosity=1,
            append=True
        )
    )
    s_logger = status_logging.get_status_logger()
    s_logger.write(
        status_level=status_logging.Status.STARTED,
        message="Starting EfficientDet inference."
    )
    label_id_mapping = {}
    if cfg.inference.label_map:
        if str(cfg.inference.label_map).endswith('.yaml'):
            label_id_mapping = label_utils.get_label_map(cfg.inference.label_map)
        else:
            label_id_mapping = get_label_dict(cfg.inference.label_map)

    if cfg.inference.model_path.endswith('.engine'):
        warnings.warn("Please use tao-deploy to run TensorRT inference.")
        # infer_trt(cfg, label_id_mapping, cfg.evaluate.min_score_thresh)
    elif cfg.inference.model_path.endswith('.tlt'):
        infer_tlt(cfg, label_id_mapping, cfg.inference.min_score_thresh)
    else:
        raise ValueError("Only .tlt models are supported with tao inference.")
    s_logger.write(
        status_level=status_logging.Status.SUCCESS,
        message="Inference finished successfully."
    )


if __name__ == '__main__':
    main()
