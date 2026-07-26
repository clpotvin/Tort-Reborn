"""
Test suite for the profile-background memory cache (Helpers/storage.py).

Tests:
1. Second get_background for the same id does not hit S3
2. Returned images are independent copies (mutation cannot poison the cache)
3. save_background updates the cache in place (write-through invalidation)
"""

import os
import sys
from unittest.mock import patch

import pytest
from PIL import Image

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from Helpers import storage


@pytest.fixture(autouse=True)
def _clean_cache():
    storage._bg_cache.clear()
    yield
    storage._bg_cache.clear()


def _img(color):
    return Image.new("RGBA", (4, 4), color)


def test_second_read_is_served_from_memory():
    with patch.object(storage.storage, "get_image", return_value=_img("red")) as s3:
        storage.get_background(1)
        storage.get_background(1)
    assert s3.call_count == 1


def test_returned_image_is_a_copy():
    with patch.object(storage.storage, "get_image", return_value=_img("red")):
        first = storage.get_background(1)
        first.putpixel((0, 0), (0, 0, 0, 0))  # mutate what the caller got
        second = storage.get_background(1)
    assert second.getpixel((0, 0)) != (0, 0, 0, 0)


def test_save_background_updates_cache_write_through():
    with patch.object(storage.storage, "get_image", return_value=_img("red")):
        assert storage.get_background(1).getpixel((0, 0))[0] == 255  # red
    with patch.object(storage.storage, "put_image") as put:
        storage.save_background(1, _img("blue"))
    put.assert_called_once()
    with patch.object(storage.storage, "get_image") as s3:
        refreshed = storage.get_background(1)
    s3.assert_not_called()  # served from the updated cache
    assert refreshed.getpixel((0, 0))[2] == 255  # blue


def test_double_missing_background_names_original_id():
    """When both the requested bg and the fallback bg 1 are missing from S3,
    the error names the originally requested id, not the fallback's."""
    import Helpers.variables as variables

    with patch.object(storage.storage, "get_image", return_value=None), \
         patch.object(variables, "IS_TEST_MODE", False):
        with pytest.raises(FileNotFoundError, match="Background 7"):
            storage.get_background(7)
