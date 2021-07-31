"""
utils.py
"""

import os
import sys


def get_project_root() -> str:
    """ Return this project's root directory. """
    # Construct the project root directory path.
    path = os.path.realpath(__file__)
    path = os.path.dirname(path)

    # Check if the project root directory path looks to be correct.
    assert os.path.exists(os.path.join(path, "utils.py"))

    return path


def add_to_sys_path(path: str) -> None:
    """ Add the path to the system path. """
    path = os.path.realpath(path)
    if path and path not in sys.path:
        sys.path.insert(0, path)
