"""
Helpers/storage.py
S3-compatible storage abstraction for profile backgrounds and shell
exchange icons.
Currently backed by Supabase Storage (S3-compatible API).
"""

import io
import os

import certifi
import boto3
from botocore.config import Config
from botocore.exceptions import ClientError
from PIL import Image

from Helpers.logger import log, WARN, ERROR
from Helpers import telemetry


class S3Storage:
    """S3-compatible storage client for Supabase Storage."""

    def __init__(self):
        self._client = None
        test_mode = os.getenv("TEST_MODE", "").lower() in ("true", "1", "t")
        if test_mode:
            self._bucket = os.getenv("TEST_S3_BUCKET_NAME", "Tort-Reborn-Dev")
        else:
            self._bucket = os.getenv("S3_BUCKET_NAME", "Tort-Reborn-Prod")

    @property
    def _is_configured(self) -> bool:
        return bool(os.getenv("S3_ENDPOINT_URL") and os.getenv("S3_ACCESS_KEY_ID"))

    @property
    def client(self):
        if self._client is None:
            self._client = boto3.client(
                "s3",
                endpoint_url=os.getenv("S3_ENDPOINT_URL"),
                aws_access_key_id=os.getenv("S3_ACCESS_KEY_ID"),
                aws_secret_access_key=os.getenv("S3_SECRET_ACCESS_KEY"),
                config=Config(signature_version="s3v4"),
                region_name=os.getenv("S3_REGION", "us-east-1"),
                verify=certifi.where(),
            )
        return self._client

    def get_bytes(self, key: str) -> bytes | None:
        if not self._is_configured:
            return None
        try:
            with telemetry.track("s3.get"):
                resp = self.client.get_object(Bucket=self._bucket, Key=key)
                data = resp["Body"].read()
                resp["Body"].close()
                return data
        except Exception:
            return None

    def get_image(self, key: str) -> Image.Image | None:
        data = self.get_bytes(key)
        if data:
            return Image.open(io.BytesIO(data)).convert("RGBA")
        return None

    def put_bytes(self, key: str, data: bytes, content_type: str = "image/png"):
        with telemetry.track("s3.put"):
            self.client.put_object(
                Bucket=self._bucket,
                Key=key,
                Body=data,
                ContentType=content_type,
            )

    def put_image(self, key: str, image: Image.Image):
        buf = io.BytesIO()
        image.save(buf, format="PNG")
        buf.seek(0)
        self.put_bytes(key, buf.getvalue())


# Singleton
storage = S3Storage()


# --- Profile background helpers ---

# In-process cache of profile backgrounds. The bot owns the only write path
# (save_background), so write-through here gives zero-staleness reads at ~0ms
# versus the ~300ms S3 round trip Phase 0 measured. Values are the pristine
# fetched images; reads hand out copies because callers mutate them in place.
_bg_cache: dict = {}


def get_background(bg_id) -> Image.Image:
    """Profile background from memory, falling back to S3 (then default)."""
    from Helpers.variables import IS_TEST_MODE

    cached = _bg_cache.get(bg_id)
    if cached is not None:
        return cached.copy()
    img = storage.get_image(f"profile_backgrounds/{bg_id}.png")
    if img:
        _bg_cache[bg_id] = img
        return img.copy()
    if bg_id != 1:
        try:
            return get_background(1)
        except FileNotFoundError:
            raise FileNotFoundError(
                f"Background {bg_id} not found in S3 (fallback background 1 also missing)"
            ) from None
    if IS_TEST_MODE:
        return Image.open("images/profile_pictures/default.png")
    raise FileNotFoundError(f"Background {bg_id} not found in S3")


def get_background_file(bg_id):
    """Download a profile background and return as a discord.File."""
    import discord

    data = storage.get_bytes(f"profile_backgrounds/{bg_id}.png")
    if data:
        return discord.File(io.BytesIO(data), filename=f"{bg_id}.png")
    raise FileNotFoundError(f"Background {bg_id} not found in S3")


def save_background(bg_id, image: Image.Image):
    """Upload a profile background to S3 and refresh the memory cache."""
    storage.put_image(f"profile_backgrounds/{bg_id}.png", image)
    _bg_cache[bg_id] = image.copy()


# --- Shell exchange icon helpers ---

def _se_icon_key(category: str, name_key: str) -> str:
    """Build the S3 key for a shell exchange icon.

    category: "ings" or "mats"
    name_key: normalised name, e.g. "ancient heart" → stored as "ancient_heart"
    """
    safe = name_key.replace(" ", "_")
    return f"shell_exchange/{category}/{safe}.png"


def get_shell_exchange_icon(category: str, name_key: str) -> Image.Image | None:
    """Download a shell exchange icon from S3."""
    return storage.get_image(_se_icon_key(category, name_key))


def save_shell_exchange_icon(category: str, name_key: str, image: Image.Image):
    """Upload a shell exchange icon to S3."""
    storage.put_image(_se_icon_key(category, name_key), image)


def delete_shell_exchange_icon(category: str, name_key: str):
    """Delete a shell exchange icon from S3."""
    key = _se_icon_key(category, name_key)
    try:
        storage.client.delete_object(Bucket=storage._bucket, Key=key)
    except ClientError:
        pass
