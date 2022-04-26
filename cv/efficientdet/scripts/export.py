# Copyright (c) 2022, NVIDIA CORPORATION.  All rights reserved.

"""Export EfficientDet model to etlt and TRT engine."""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import os

import tensorflow as tf
from tensorflow.python.util import deprecation

from cv.efficientdet.config.hydra_runner import hydra_runner
from cv.efficientdet.config.default_config import ExperimentConfig
from cv.efficientdet.exporter.onnx_exporter import EfficientDetGraphSurgeon
from cv.efficientdet.exporter.trt_builder import EngineBuilder
from cv.efficientdet.inferencer import inference

from cv.efficientdet.utils import helper, hparams_config
from cv.efficientdet.utils.config_utils import generate_params_from_cfg

deprecation._PRINT_DEPRECATION_WARNINGS = False

os.environ['CUDA_VISIBLE_DEVICES'] = '0'
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'  # or any {'0', '1', '2'}
os.environ["TF_CPP_VMODULE"] = 'non_max_suppression_op=0,generate_box_proposals_op=0,executor=0'
supported_img_format = ['.jpg', '.jpeg', '.JPG', '.JPEG', '.png', '.PNG']


def run_export(cfg, results_dir=None, key=None):
    """Launch EfficientDet export."""
    # disable_eager_execution()
    tf.autograph.set_verbosity(0)
    
    gpus = tf.config.experimental.list_physical_devices('GPU')
    for gpu in gpus:
        tf.config.experimental.set_memory_growth(gpu, True)
    if gpus:
        tf.config.experimental.set_visible_devices(gpus[0], 'GPU')

    # Parse and update hparams
    MODE = 'export'
    config = hparams_config.get_detection_config(cfg['model_config']['model_name'])
    config.update(generate_params_from_cfg(config, cfg, mode='export'))
    params = config.as_dict()

    # TODO(@yuw): change to EFF
    assert str(cfg.export_config.output_path).endswith('.onnx'), "ONNX!!!"
    output_dir = os.path.dirname(cfg.export_config.output_path)

    # Load model from graph json
    model = helper.load_model(cfg['export_config']['model_path'], cfg, MODE)
    model.summary()
    input_shape = list(model.layers[0].input_shape[0][1:3])
    max_batch_size = cfg.export_config.max_batch_size
    # fake_images = tf.keras.Input(shape=[None, None, None], batch_size=max_batch_size)
    export_model = inference.InferenceModel(model, config.image_size, params, max_batch_size)
    export_model.infer = tf.function(export_model.infer)
    tf.saved_model.save(
        export_model,
        output_dir,
        signatures=export_model.infer.get_concrete_function(
            tf.TensorSpec(shape=(None, None, None, 3), dtype=tf.uint8)))

    print("Generating ONNX.....")
    # convert to onnx
    effdet_gs = EfficientDetGraphSurgeon(output_dir, legacy_plugins=False)
    effdet_gs.update_preprocessor('NHWC', input_shape, preprocessor="imagenet")
    effdet_gs.update_shapes()
    effdet_gs.update_network()
    effdet_gs.update_nms()
    # TODO(@yuw): convert onnx to eff
    onnx_file = effdet_gs.save(cfg.export_config.output_path)
    # assert 0
    print("Generating Engine.....")
    # convert to engine
    if cfg.export_config.engine_file is not None or cfg.export_config.data_type == 'int8':

        output_engine_path = cfg.export_config.engine_file
        builder = EngineBuilder(cfg.export_config.verbose, workspace=cfg.export_config.max_workspace_size)
        builder.create_network(onnx_file, batch_size=max_batch_size)
        builder.create_engine(
            output_engine_path,
            cfg.export_config.data_type,
            cfg.export_config.cal_image_dir,
            cfg.export_config.cal_cache_file,
            cfg.export_config.cal_batch_size * cfg.export_config.cal_batches,
            cfg.export_config.cal_batch_size)


spec_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
@hydra_runner(
    config_path=os.path.join(spec_root, "experiment_specs"),
    config_name="export", schema=ExperimentConfig
)
def main(cfg: ExperimentConfig):
    """Wrapper function for EfficientDet exporter.
    """
    run_export(cfg=cfg,
               results_dir=cfg.results_dir,
               key=cfg.key)


if __name__ == '__main__':
    main()