# Copyright (c) 2022-2023, NVIDIA CORPORATION.  All rights reserved.
"""Helper utils for packaging."""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import glob
import os

# Rename all .py files to .py_tmp temporarily.
ignore_list = ['__init__.py', '__version__.py']

LOCAL_DIR = os.path.dirname(os.path.abspath(__file__))


def up_directory(dir_path, n=1):
    """Go up n directories from dir_path."""
    dir_up = dir_path
    for _ in range(n):
        dir_up = os.path.split(dir_up)[0]
    return dir_up


TOP_LEVEL_DIR = up_directory(LOCAL_DIR, 3)

def remove_prefix(dir_path):
    """Remove a certain prefix from path."""
    max_path = 8
    prefix = dir_path
    while max_path > 0:
        prefix = os.path.split(prefix)[0]
        if prefix.endswith('ai_infra'):
            return dir_path[len(prefix) + 1:]
        max_path -= 1
    return dir_path


def get_subdirs(path):
    """Get all subdirs of given path."""
    dirs = os.walk(path)
    return [remove_prefix(x[0]) for x in dirs]


def rename_py_files(path, ext, new_ext, ignore_files):
    """Rename all .ext files in a path to .new_ext except __init__ files."""
    files = glob.glob(path + '/*' + ext)
    for ignore_file in ignore_files:
        files = [f for f in files if ignore_file not in f]

    for filename in files:
        os.rename(filename, filename.replace(ext, new_ext))


def get_version_details():
    """Simple function to get packages for setup.py."""
    # Define env paths.
    LAUNCHER_SDK_PATH = os.path.join(TOP_LEVEL_DIR, "release/python") 
    # Get current __version__.
    version_locals = {}
    with open(os.path.join(LAUNCHER_SDK_PATH, 'version.py')) as version_file:
        exec(version_file.read(), {}, version_locals)

    return  version_locals


def cleanup():
    """Cleanup directories after the build process."""
    req_subdirs = get_subdirs(TOP_LEVEL_DIR)
    # Cleanup. Rename all .py_tmp files back to .py and delete pyc files
    for dir_path in req_subdirs:
        dir_path = os.path.join(TOP_LEVEL_DIR, dir_path)
        # TODO: @vpraveen Think about removing python files before the final
        # release.
        rename_py_files(dir_path, '.py_tmp', '.py', ignore_list)
        pyc_list = glob.glob(dir_path + '/*.pyc')
        for pyc_file in pyc_list:
            os.remove(pyc_file)