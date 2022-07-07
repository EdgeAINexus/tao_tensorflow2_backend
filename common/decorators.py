# Copyright (c) 2017-2018, NVIDIA CORPORATION.  All rights reserved.
"""Modulus decorators."""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import inspect


def override(method):
    """Override decorator.

    Decorator implementing method overriding in python
    Must also use the @subclass class decorator
    """
    method.override = True
    return method


def subclass(class_object):
    """Subclass decorator.

    Verify all @override methods
    Use a class decorator to find the method's class
    """
    for name, method in class_object.__dict__.items():
        if hasattr(method, "override"):
            found = False
            for base_class in inspect.getmro(class_object)[1:]:
                if name in base_class.__dict__:
                    if not method.__doc__:
                        # copy docstring
                        method.__doc__ = base_class.__dict__[name].__doc__
                    found = True
                    break
            assert found, f'"{class_object.__name__}.{name}" not found in any base class'
    return class_object
