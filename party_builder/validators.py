# This file contains reusable checks for values that must follow the same rule in several forms or
# models.
# Central validation prevents one screen from accepting information that another part of the site
# would reject.

from __future__ import annotations

import uuid
from pathlib import Path

from django.core.exceptions import ValidationError
from PIL import Image, UnidentifiedImageError

ALLOWED_IMAGE_FORMATS = {"JPEG", "PNG", "WEBP"}
ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
MAX_IMAGE_BYTES = 5 * 1024 * 1024


# Return a generated media path while preserving only a safe extension.
def _safe_image_path(folder: str, filename: str) -> str:
    """Return a generated media path while preserving only a safe extension."""

    extension = Path(filename).suffix.lower()
    if extension not in ALLOWED_IMAGE_EXTENSIONS:
        extension = ".jpg"
    return f"catalogue/{folder}/{uuid.uuid4().hex}{extension}"


# Store uploaded category images under the sanitized categories path, using the shared filename
# hardening instead of trusting the original upload name.
def category_image_upload_to(instance, filename: str) -> str:
    return _safe_image_path("categories", filename)


# Store uploaded package images under the sanitized packages path, using the shared filename
# hardening instead of trusting the original upload name.
def package_image_upload_to(instance, filename: str) -> str:
    return _safe_image_path("packages", filename)


# Store uploaded add-on images under the sanitized addons path, using the shared filename hardening
# instead of trusting the original upload name.
def addon_image_upload_to(instance, filename: str) -> str:
    return _safe_image_path("addons", filename)


# This safeguard verifies catalogue image before the surrounding workflow continues.
# When the rule is not met, it stops the action with a controlled error rather than allowing an
# inconsistent record.
def validate_catalogue_image(uploaded_file) -> None:
    """Accept only genuine JPEG, PNG, or WebP images no larger than 5 MB.

    Pillow reads the file header instead of trusting the browser-provided file
    name or content type. The stream is rewound afterwards so Django can save it.
    """

    if not uploaded_file:
        return

    if uploaded_file.size > MAX_IMAGE_BYTES:
        raise ValidationError("Image files must be 5 MB or smaller.")

    extension = Path(uploaded_file.name).suffix.lower()
    if extension not in ALLOWED_IMAGE_EXTENSIONS:
        raise ValidationError("Upload a JPEG, PNG, or WebP image.")

    try:
        current_position = uploaded_file.tell()
    except (AttributeError, OSError):
        current_position = 0

    try:
        image = Image.open(uploaded_file)
        image.verify()
        if image.format not in ALLOWED_IMAGE_FORMATS:
            raise ValidationError("Upload a genuine JPEG, PNG, or WebP image.")
    except (UnidentifiedImageError, OSError, ValueError) as error:
        raise ValidationError("The uploaded file is not a valid image.") from error
    finally:
        try:
            uploaded_file.seek(current_position)
        except (AttributeError, OSError):
            pass
