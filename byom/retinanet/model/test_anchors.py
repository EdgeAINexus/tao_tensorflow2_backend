import math
import numpy as np
from collections.abc import Iterable
from itertools import repeat

from byom.retinanet.model.anchors import Anchors

def _pair(x):
    if not isinstance(x, Iterable):
        return tuple(repeat(x, 2))
    elif len(x) == 2:
        return x
    else:
        raise ValueError('Not a valid pair!')
        

class mmdet_anchor_generator():
    """MMDet Anchor Generator reimplemented with numpy.
    
    https://github.com/open-mmlab/mmdetection/blob/c76ab0eb3c637b86c343d8454e07e00cfecc1b78/mmdet/core/anchor/anchor_generator.py#L216
    
    Args:
        strides (list[int] | list[tuple[int, int]]): Strides of anchors
            in multiple feature levels in order (w, h).
        ratios (list[float]): The list of ratios between the height and width
            of anchors in a single level.
        scales (list[int] | None): Anchor scales for anchors in a single level.
            It cannot be set at the same time if `octave_base_scale` and
            `scales_per_octave` are set.
        base_sizes (list[int] | None): The basic sizes
            of anchors in multiple levels.
            If None is given, strides will be used as base_sizes.
            (If strides are non square, the shortest stride is taken.)
        scale_major (bool): Whether to multiply scales first when generating
            base anchors. If true, the anchors in the same row will have the
            same scales. By default it is True in V2.0
        octave_base_scale (int): The base scale of octave.
        scales_per_octave (int): Number of scales for each octave.
            `octave_base_scale` and `scales_per_octave` are usually used in
            retinanet and the `scales` should be None when they are set.
        centers (list[tuple[float, float]] | None): The centers of the anchor
            relative to the feature grid center in multiple feature levels.
            By default it is set to be None and not used. If a list of tuple of
            float is given, they will be used to shift the centers of anchors.
        center_offset (float): The offset of center in proportion to anchors'
            width and height. By default it is 0 in V2.0.
    """    

    def __init__(self,
                 strides,
                 ratios,
                 scales=None,
                 base_sizes=None,
                 scale_major=True,
                 octave_base_scale=None,
                 scales_per_octave=None,
                 centers=None,
                 center_offset=0.):
        # check center and center_offset
        if center_offset != 0:
            assert centers is None, 'center cannot be set when center_offset' \
                                    f'!=0, {centers} is given.'
        if not (0 <= center_offset <= 1):
            raise ValueError('center_offset should be in range [0, 1], '
                             f'{center_offset} is given.')
        if centers is not None:
            assert len(centers) == len(strides), \
                'The number of strides should be the same as centers, got ' \
                f'{strides} and {centers}'

        # calculate base sizes of anchors
        self.strides = [_pair(stride) for stride in strides]
        self.base_sizes = [min(stride) for stride in self.strides
                           ] if base_sizes is None else base_sizes
        assert len(self.base_sizes) == len(self.strides), \
            'The number of strides should be the same as base sizes, got ' \
            f'{self.strides} and {self.base_sizes}'

        # calculate scales of anchors
        assert ((octave_base_scale is not None
                 and scales_per_octave is not None) ^ (scales is not None)), \
            'scales and octave_base_scale with scales_per_octave cannot' \
            ' be set at the same time'
        if scales is not None:
            self.scales = np.array(scales)
        elif octave_base_scale is not None and scales_per_octave is not None:
            octave_scales = np.array(
                [2**(i / scales_per_octave) for i in range(scales_per_octave)])
            scales = octave_scales * octave_base_scale
            self.scales = scales
        else:
            raise ValueError('Either scales or octave_base_scale with '
                             'scales_per_octave should be set')

        self.octave_base_scale = octave_base_scale
        self.scales_per_octave = scales_per_octave
        self.ratios = ratios
        self.scale_major = scale_major
        self.centers = centers
        self.center_offset = center_offset
        self.base_anchors = self.gen_base_anchors()

    def _meshgrid(self, x, y, row_major=True):
        """Generate mesh grid of x and y.
        Args:
            x (torch.Tensor): Grids of x dimension.
            y (torch.Tensor): Grids of y dimension.
            row_major (bool, optional): Whether to return y grids first.
                Defaults to True.
        Returns:
            tuple[torch.Tensor]: The mesh grids of x and y.
        """
        # use shape instead of len to keep tracing while exporting to onnx
        xx = np.tile(x, y.shape[0])
        yy = np.tile(y.reshape(-1, 1), (1, x.shape[0])).reshape(-1)
        if row_major:
            return xx, yy
        else:
            return yy, xx
    
    
    @property
    def num_base_anchors(self):
        """list[int]: total number of base anchors in a feature grid"""
        return self.num_base_priors

    @property
    def num_base_priors(self):
        """list[int]: The number of priors (anchors) at a point
        on the feature grid"""
        return [base_anchors.size(0) for base_anchors in self.base_anchors]

    @property
    def num_levels(self):
        """int: number of feature levels that the generator will be applied"""
        return len(self.strides)

    def gen_base_anchors(self):
        """Generate base anchors.
        Returns:
            list(torch.Tensor): Base anchors of a feature grid in multiple \
                feature levels.
        """
        multi_level_base_anchors = []
        for i, base_size in enumerate(self.base_sizes):
            center = None
            if self.centers is not None:
                center = self.centers[i]
            multi_level_base_anchors.append(
                self.gen_single_level_base_anchors(
                    base_size,
                    scales=self.scales,
                    ratios=self.ratios,
                    center=center))
        return multi_level_base_anchors

    def gen_single_level_base_anchors(self,
                                      base_size,
                                      scales,
                                      ratios,
                                      center=None):
        """Generate base anchors of a single level.
        Args:
            base_size (int | float): Basic size of an anchor.
            scales (torch.Tensor): Scales of the anchor.
            ratios (torch.Tensor): The ratio between between the height
                and width of anchors in a single level.
            center (tuple[float], optional): The center of the base anchor
                related to a single feature grid. Defaults to None.
        Returns:
            torch.Tensor: Anchors in a single-level feature maps.
        """
        w = base_size
        h = base_size
        if center is None:
            x_center = self.center_offset * w
            y_center = self.center_offset * h
        else:
            x_center, y_center = center

        h_ratios = np.sqrt(ratios)
        w_ratios = 1 / h_ratios

        if self.scale_major:
            ws = (w * w_ratios[:, None] * scales[None, :]).reshape(-1)
            hs = (h * h_ratios[:, None] * scales[None, :]).reshape(-1)
        else:
            ws = (w * scales[:, None] * w_ratios[None, :]).reshape(-1)
            hs = (h * scales[:, None] * h_ratios[None, :]).reshape(-1)

        # use float anchor and the anchor's center is aligned with the
        # pixel center
        base_anchors = [
            x_center - 0.5 * ws, y_center - 0.5 * hs, x_center + 0.5 * ws,
            y_center + 0.5 * hs
        ]
        base_anchors = np.stack(base_anchors, axis=-1)

        return base_anchors
    
    def single_level_grid_priors(self,
                                 featmap_size,
                                 level_idx,
                                 dtype=np.float32):
        """Generate grid anchors of a single level.
        Note:
            This function is usually called by method ``self.grid_priors``.
        Args:
            featmap_size (tuple[int]): Size of the feature maps.
            level_idx (int): The index of corresponding feature map level.
            dtype (obj:`torch.dtype`): Date type of points.Defaults to
                ``torch.float32``.
        Returns:
            torch.Tensor: Anchors in the overall feature maps.
        """

        base_anchors = self.base_anchors[level_idx].astype(dtype)
        feat_h, feat_w = featmap_size
        stride_w, stride_h = self.strides[level_idx]
        # First create Range with the default dtype, than convert to
        # target `dtype` for onnx exporting.
        shift_x = np.arange(0, feat_w).astype(dtype) * stride_w
        shift_y = np.arange(0, feat_h).astype(dtype) * stride_h

        shift_xx, shift_yy = self._meshgrid(shift_x, shift_y)
        shifts = np.stack([shift_xx, shift_yy, shift_xx, shift_yy], axis=-1)
        # first feat_w elements correspond to the first row of shifts
        # add A anchors (1, A, 4) to K shifts (K, 1, 4) to get
        # shifted anchors (K, A, 4), reshape to (K*A, 4)

        all_anchors = base_anchors[None, :, :] + shifts[:, None, :]
        all_anchors = all_anchors.reshape(-1, 4)
        # first A rows correspond to A anchors of (0, 0) in feature map,
        # then (0, 1), (0, 2), ...
        return all_anchors
    
    def grid_priors(self, featmap_sizes, dtype=np.float32):
        """Generate grid anchors in multiple feature levels.
        Args:
            featmap_sizes (list[tuple]): List of feature map sizes in
                multiple feature levels.
            dtype (:obj:`torch.dtype`): Dtype of priors.
                Default: torch.float32.
        Return:
            list[torch.Tensor]: Anchors in multiple feature levels. \
                The sizes of each tensor should be [N, 4], where \
                N = width * height * num_base_anchors, width and height \
                are the sizes of the corresponding feature level, \
                num_base_anchors is the number of anchors for that level.
        """
        assert self.num_levels == len(featmap_sizes)
        multi_level_anchors = []
        for i in range(self.num_levels):
            anchors = self.single_level_grid_priors(
                featmap_sizes[i], level_idx=i, dtype=dtype)
            multi_level_anchors.append(anchors)
        return multi_level_anchors
    

def compare_single_level_anchors():
    s = 16
    base_size = 9
    l = int(math.log(s, 2))
    w, h = 32, 32
    # mmdet
    anchor_gen = mmdet_anchor_generator(
        strides=[s],
        ratios=[1],
        scales=[1],
        base_sizes=[base_size],
        scale_major=True,
        octave_base_scale=None,
        scales_per_octave=None,
        centers=None,
        center_offset=0.)
    anchors = anchor_gen.grid_priors([(h/s, w/s)])
    print(anchors)
    # result
    """[[-4.5, -4.5,  4.5,  4.5],
        [11.5, -4.5, 20.5,  4.5],
        [-4.5, 11.5,  4.5, 20.5],
        [11.5, 11.5, 20.5, 20.5]]"""

    # tao 
    tao_anchors = Anchors(
        min_level=l,
        max_level=l,
        num_scales=1, aspect_ratios=[(1, 1)],
        anchor_scale=base_size/s, image_size=(h, w))
    print(tao_anchors.boxes - s // 2)

    # result
    """[[-4.5 -4.5  4.5  4.5]
        [-4.5 11.5  4.5 20.5]
        [11.5 -4.5 20.5  4.5]
        [11.5 11.5 20.5 20.5]]"""
compare_single_level_anchors()
