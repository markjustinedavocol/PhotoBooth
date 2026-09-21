"""Private Cloudinary storage for photos, strips and avatars.

Files are uploaded as Cloudinary "raw" assets with the "authenticated" delivery
type, so they have no public URL: only a signed URL (which this app generates
server-side and never shows to other users) can fetch them. The app keeps
serving images through its own permission-checked views, exactly as it does
with local storage.

Configure with the CLOUDINARY_URL environment variable
(cloudinary://<api_key>:<api_secret>@<cloud_name>).
"""
import posixpath
import urllib.error
import urllib.request
from io import BytesIO

import cloudinary
import cloudinary.uploader
import cloudinary.utils
from django.conf import settings
from django.core.files.base import File
from django.core.files.storage import Storage
from django.utils.deconstruct import deconstructible

RESOURCE_TYPE = "raw"  # stored byte-for-byte; no format conversion
DELIVERY_TYPE = "authenticated"  # not publicly reachable


@deconstructible
class PrivateCloudinaryStorage(Storage):
    def __init__(self, folder=None):
        self.folder = (folder if folder is not None else getattr(settings, "CLOUDINARY_FOLDER", "")).strip("/")

    # ------------------------------------------------------------ helpers

    def _public_id(self, name):
        name = name.replace("\\", "/").lstrip("/")
        return posixpath.join(self.folder, name) if self.folder else name

    def _signed_url(self, name):
        url, _ = cloudinary.utils.cloudinary_url(
            self._public_id(name),
            resource_type=RESOURCE_TYPE,
            type=DELIVERY_TYPE,
            sign_url=True,
            secure=True,
        )
        return url

    # ------------------------------------------------------------ Storage API

    def _save(self, name, content):
        if hasattr(content, "seek"):
            content.seek(0)
        stream = BytesIO(content.read())
        cloudinary.uploader.upload(
            stream,
            public_id=self._public_id(name),
            resource_type=RESOURCE_TYPE,
            type=DELIVERY_TYPE,
            overwrite=True,
            invalidate=True,
            filename=posixpath.basename(name),
        )
        return name

    def _open(self, name, mode="rb"):
        if "w" in mode or "a" in mode:
            raise ValueError("PrivateCloudinaryStorage files are read-only once saved.")
        try:
            with urllib.request.urlopen(self._signed_url(name), timeout=30) as response:
                data = response.read()
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                raise FileNotFoundError(name) from exc
            raise
        return File(BytesIO(data), name=name)

    def delete(self, name):
        if name:
            cloudinary.uploader.destroy(
                self._public_id(name),
                resource_type=RESOURCE_TYPE,
                type=DELIVERY_TYPE,
                invalidate=True,
            )

    def exists(self, name):
        # Every upload path in this project adds a random token to the filename,
        # so collisions don't happen; skipping the lookup saves an Admin API call
        # (which Cloudinary rate-limits) on every upload.
        return False

    def url(self, name):
        # Only used by the Django admin / your own profile form. The public site
        # always goes through permission-checked views instead.
        return self._signed_url(name)

    def size(self, name):
        with self._open(name) as fh:
            return len(fh.read())
