# Copyright (c) 2021-2022, NVIDIA CORPORATION.  All rights reserved.

"""Collection of helper functions."""
import os

import cv2
from tensorflow import keras
import tensorflow as tf
from numba import jit, njit
import numpy as np
from PIL import Image

from common.utils import (
    MultiGPULearningRateScheduler,
    SoftStartCosineAnnealingScheduler,
    StepLRScheduler
)
from backbones.utils_tf import swish

opt_dict = {
    'sgd': keras.optimizers.SGD,
    'adam': keras.optimizers.Adam,
    'rmsprop': keras.optimizers.RMSprop
}

scope_dict = {'dense': keras.layers.Dense,
              'conv2d': keras.layers.Conv2D}

regularizer_dict = {'l1': keras.regularizers.l1,
                    'l2': keras.regularizers.l2}


def initialize():
    """Initializes backend related initializations."""
    if tf.config.list_physical_devices('GPU'):
        data_format = 'channels_first'
    else:
        data_format = 'channels_last'
    tf.keras.backend.set_image_data_format(data_format)


def build_optimizer(optimizer_config):
    """build optimizer with the optimizer config."""

    if optimizer_config.optimizer == "sgd":
        return opt_dict["sgd"](
            learning_rate=optimizer_config.lr,
            momentum=optimizer_config.momentum,
            decay=optimizer_config.decay,
            nesterov=optimizer_config.nesterov
        )
    if optimizer_config.optimizer == "adam":
        return opt_dict["adam"](
            learning_rate=optimizer_config.lr,
            beta_1=optimizer_config.beta_1,
            beta_2=optimizer_config.beta_2,
            epsilon=optimizer_config.epsilon,
            decay=optimizer_config.decay
        )
    if optimizer_config.optimizer == "rmsprop":
        return opt_dict["rmsprop"](
            learning_rate=optimizer_config.lr,
            rho=optimizer_config.rho,
            epsilon=optimizer_config.epsilon,
            decay=optimizer_config.decay
        )
    raise ValueError("Unsupported Optimizer: {}".format(optimizer_config.optimizer))


def build_lr_scheduler(lr_config, hvd_size, max_iterations):
    """Build a learning rate scheduler from config."""
    # Set up the learning rate callback. It will modulate learning rate
    # based on iteration progress to reach max_iterations.
    if lr_config.scheduler == 'step':
        lrscheduler = StepLRScheduler(
            base_lr=lr_config.learning_rate * hvd_size,
            gamma=lr_config.gamma,
            step_size=lr_config.step_size,
            max_iterations=max_iterations
        )
    elif lr_config.scheduler == 'soft_anneal':
        lrscheduler = MultiGPULearningRateScheduler(
            base_lr=lr_config.learning_rate * hvd_size,
            soft_start=lr_config.soft_start,
            annealing_points=lr_config.annealing_points,
            annealing_divider=lr_config.annealing_divider,
            max_iterations=max_iterations
        )
    elif lr_config.scheduler == 'cosine':
        lrscheduler = SoftStartCosineAnnealingScheduler(
            base_lr=lr_config.learning_rate * hvd_size,
            min_lr_ratio=lr_config.min_lr_ratio,
            soft_start=lr_config.soft_start,
            max_iterations=max_iterations
        )
    else:
        raise ValueError(
            f"Only `step`, `cosine` and `soft_anneal` ",
            "LR scheduler are supported, but {lr_config.scheduler} is specified."
        )
    return lrscheduler


def get_input_shape(model):
    """Obtain input shape from a Keras model."""
    data_format = model.layers[1].data_format
    # Computing shape of input tensor
    image_shape = model.layers[0].input_shape[0][1:4]
    # Setting input shape
    if data_format == "channels_first":
        nchannels, image_height, image_width = image_shape[0:3]
    else:
        image_height, image_width, nchannels = image_shape[0:3]
    return image_height, image_width, nchannels


@njit
def randu(low, high):
    """standard uniform distribution."""
    return np.random.random()*(high-low) + low


@jit
def random_hue(img, max_delta=10.0):
    """
    Rotates the hue channel.

    Args:
        img: input image in float32
        max_delta: Max number of degrees to rotate the hue channel
    """
    # Rotates the hue channel by delta degrees
    delta = randu(-max_delta, max_delta)
    hsv = cv2.cvtColor(img.astype(np.float32), cv2.COLOR_BGR2HSV)
    hchannel = hsv[:, :, 0]
    hchannel = delta + hchannel
    # hue should always be within [0,360]
    idx = np.where(hchannel > 360)
    hchannel[idx] = hchannel[idx] - 360
    idx = np.where(hchannel < 0)
    hchannel[idx] = hchannel[idx] + 360
    hsv[:, :, 0] = hchannel
    return cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)


@jit
def random_saturation(img, max_shift):
    """random saturation data augmentation."""
    hsv = cv2.cvtColor(img.astype(np.float32), cv2.COLOR_BGR2HSV)
    shift = randu(-max_shift, max_shift)
    # saturation should always be within [0,1.0]
    hsv[:, :, 1] = np.clip(hsv[:, :, 1]+shift, 0.0, 1.0)
    return cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)


@jit
def random_contrast(img, center, max_contrast_scale):
    """random contrast data augmentation."""
    new_img = (img-center)*(1.0 + randu(-max_contrast_scale, max_contrast_scale)) \
        + center
    new_img = np.clip(new_img, 0., 1.)
    return new_img


@jit
def random_shift(x_img, shift_stddev):
    """random shift data augmentation."""
    shift = np.random.randn()*shift_stddev
    new_img = np.clip(x_img + shift, 0.0, 1.0)

    return new_img


def color_augmentation(
    x_img,
    color_shift_stddev=0.0,
    hue_rotation_max=25.0,
    saturation_shift_max=0.2,
    contrast_center=0.5,
    contrast_scale_max=0.1
):
    """color augmentation for images."""
    # convert PIL Image to numpy array
    x_img = np.array(x_img, dtype=np.float32)
    # normalize the image to (0, 1)
    x_img /= 255.0
    x_img = random_shift(x_img, color_shift_stddev)
    x_img = random_hue(x_img, max_delta=hue_rotation_max)
    x_img = random_saturation(x_img, saturation_shift_max)
    x_img = random_contrast(
        x_img,
        contrast_center,
        contrast_scale_max
    )
    # convert back to PIL Image
    x_img *= 255.0
    return Image.fromarray(x_img.astype(np.uint8), "RGB")


def setup_config(model, reg_config, bn_config=None):
    """Wrapper for setting up BN and regularizer.

    Args:
        model (keras Model): a Keras model
        reg_config (dict): reg_config dict
        bn_config (dict): config to override BatchNormalization parameters
    Return:
        A new model with overridden config.
    """

    if bn_config is not None:
        bn_momentum = bn_config['momentum']
        bn_epsilon = bn_config['epsilon']
    else:
        bn_momentum = 0.9
        bn_epsilon = 1e-5
    # Obtain the current configuration from model
    mconfig = model.get_config()
    # Obtain type and scope of the regularizer
    reg_type = reg_config['type'].lower()
    scope_list = reg_config['scope']
    layer_list = [scope_dict[i.lower()] for i in scope_list if i.lower()
                  in scope_dict]

    for layer, layer_config in zip(model.layers, mconfig['layers']):
        # BN settings
        if type(layer) == keras.layers.BatchNormalization:
            layer_config['config']['momentum'] = bn_momentum
            layer_config['config']['epsilon'] = bn_epsilon

        # Regularizer settings
        if reg_type:
            if type(layer) in layer_list and \
               hasattr(layer, 'kernel_regularizer'):

                assert reg_type in ['l1', 'l2', 'none'], \
                    "Regularizer can only be either L1, L2 or None."

                if reg_type in ['l1', 'l2']:
                    assert 0 < reg_config['weight_decay'] < 1, \
                        "Weight decay should be no less than 0 and less than 1"
                    regularizer = regularizer_dict[reg_type](
                                        reg_config['weight_decay'])
                    layer_config['config']['kernel_regularizer'] = \
                        {'class_name': regularizer.__class__.__name__,
                         'config': regularizer.get_config()}

                if reg_type == 'none':
                    layer_config['config']['kernel_regularizer'] = None
    with keras.utils.CustomObjectScope({'swish': swish}):
        updated_model = keras.models.Model.from_config(mconfig)
    updated_model.set_weights(model.get_weights())

    return updated_model