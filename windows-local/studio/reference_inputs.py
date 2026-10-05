"""Immutable, hash-bound Comfy reference inputs prepared locally with Pillow."""
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import shutil
import tempfile

from PIL import Image, ImageOps


class ReferenceInputError(ValueError):
    """A reference, path, or persisted snapshot failed validation."""


def _sha256(data):
    return hashlib.sha256(data).hexdigest()


def _hex(value, length):
    return (isinstance(value, str) and len(value) == length
            and all(char in '0123456789abcdef' for char in value))


def _input_root(config):
    configured = config.get('comfy_input_dir')
    if configured is None:
        comfy_dir = config.get('comfy_dir')
        if not isinstance(comfy_dir, (str, Path)) or not str(comfy_dir):
            raise ReferenceInputError('Configure the local Comfy input directory.')
        return (Path(comfy_dir)/'input').resolve()
    if not isinstance(configured, (str, Path)) or not str(configured):
        raise ReferenceInputError('Configure the local Comfy input directory.')
    return Path(configured).resolve()


def _bundle_paths(config, job_id):
    if not _hex(job_id, 32):
        raise ReferenceInputError('Reference snapshot needs a 32-character lowercase hex job ID.')
    root = _input_root(config)
    namespace = (root/'ByrdHouse/references').resolve()
    directory = (namespace/job_id).resolve()
    if not namespace.is_relative_to(root) or not directory.is_relative_to(namespace):
        raise ReferenceInputError('Reference snapshot path is outside the configured Comfy input directory.')
    relative = f'ByrdHouse/references/{job_id}/reference.png'
    staged = (directory/'reference.png').resolve()
    metadata = (directory/'reference.png.json').resolve()
    if not staged.is_relative_to(directory) or not metadata.is_relative_to(directory):
        raise ReferenceInputError('Reference snapshot file is outside its job directory.')
    return namespace, directory, staged, metadata, relative


def _source_root(config, use_original):
    key = 'photo_dir' if use_original else 'reference_dir'
    value = config.get(key)
    if value is None and not use_original and config.get('photo_dir'):
        value = Path(config['photo_dir']).parent/'references'
    if not isinstance(value, (str, Path)) or not str(value):
        raise ReferenceInputError(f'Configure {key} before staging a reference.')
    return Path(value).resolve()


def _source_binding(config, row, use_original):
    if not isinstance(row, dict) or not isinstance(row.get('id'), str) or not row['id'].strip():
        raise ReferenceInputError('Choose an installed local reference.')
    if type(use_original) is not bool:
        raise ReferenceInputError('Choose reference-file or original-photo staging explicitly.')
    if use_original and row.get('generated', False):
        raise ReferenceInputError('Source preservation requires an original photograph.')
    root = _source_root(config, use_original)
    key = 'source' if use_original else 'file'
    value = row.get(key)
    if not isinstance(value, (str, Path)) or not str(value):
        raise ReferenceInputError(f'The reference is missing its {key} path.')
    candidate = Path(value)
    source = (candidate if candidate.is_absolute() else root/candidate).resolve()
    if not source.is_relative_to(root) or source == root:
        raise ReferenceInputError('Reference source is outside its allowed local folder.')
    expected_original_hash = row.get('source_sha256')
    if expected_original_hash is not None and not _hex(expected_original_hash, 64):
        raise ReferenceInputError('The reference original-source hash is invalid.')
    if use_original and expected_original_hash is None:
        raise ReferenceInputError('Source preservation requires the original manifest SHA256.')
    return source, {
        'reference_id': row['id'],
        'source_kind': 'original_photo' if use_original else 'reference_file',
        'source': str(source),
        'manifest_original_source_sha256': expected_original_hash,
    }


def _read_card(path):
    try:
        card = json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(card, dict):
            raise ValueError('Expected an object.')
        return card
    except (OSError, ValueError) as exc:
        raise ReferenceInputError('Cannot validate saved reference snapshot metadata.') from exc


def _decoded_rgb(data):
    try:
        with Image.open(io.BytesIO(data)) as image:
            if getattr(image, 'n_frames', 1) != 1:
                raise ReferenceInputError('A reference snapshot needs a single still image.')
            return ImageOps.exif_transpose(image).convert('RGB')
    except (OSError, ValueError) as exc:
        raise ReferenceInputError('Cannot decode the local reference image.') from exc


def reverify_reference(config, snapshot, job_id=None):
    """Verify a saved snapshot without reading a manifest or mutable source file.

    Pass the JSON snapshot stored in the job spec. Its paths, sidecar, PNG bytes,
    dimensions, and decoded RGB pixels must still match. Original aliases may be
    edited or removed after staging; they never replace this job's pinned input.
    """
    if not isinstance(snapshot, dict):
        raise ReferenceInputError('The job is missing its reference snapshot.')
    saved_job_id = snapshot.get('job_id')
    if job_id is not None and saved_job_id != job_id:
        raise ReferenceInputError('Reference snapshot belongs to another job.')
    _, _, staged, metadata, relative = _bundle_paths(config, saved_job_id)
    expected = {
        'schema': 'byrdhouse.reference-input.v1',
        'job_id': saved_job_id,
        'comfy_image': relative, 'staged_path': str(staged), 'metadata_path': str(metadata),
        'normalization': 'exif-transpose-rgb-no-resize',
    }
    if any(snapshot.get(key) != value for key, value in expected.items()):
        raise ReferenceInputError('Reference snapshot path or provenance does not match this job.')
    if not isinstance(snapshot.get('purpose'), str) or not snapshot['purpose'].strip():
        raise ReferenceInputError('Reference snapshot metadata is missing its purpose.')
    if snapshot.get('source_kind') not in ('original_photo', 'reference_file'):
        raise ReferenceInputError('Reference snapshot source provenance is invalid.')
    if not isinstance(snapshot.get('reference_id'), str) or not snapshot['reference_id'].strip():
        raise ReferenceInputError('Reference snapshot is missing its reference ID.')
    if any(type(snapshot.get(key)) is not int or snapshot[key] <= 0 for key in ('width', 'height')):
        raise ReferenceInputError('Reference snapshot dimensions are invalid.')
    recorded_source = snapshot.get('source')
    if not isinstance(recorded_source, str) or not recorded_source:
        raise ReferenceInputError('Reference snapshot source path is invalid.')
    source = Path(recorded_source)
    source_root = _source_root(config, snapshot['source_kind'] == 'original_photo')
    # Check the recorded canonical path lexically; never follow a mutable alias.
    if not source.is_absolute() or not source.is_relative_to(source_root) or source == source_root:
        raise ReferenceInputError('Recorded reference source is outside its allowed local folder.')
    for key in ('source_sha256', 'rgb_pixel_sha256', 'staged_png_sha256'):
        if not _hex(snapshot.get(key), 64):
            raise ReferenceInputError('Reference snapshot hashes are missing or invalid.')
    original_hash = snapshot.get('manifest_original_source_sha256')
    if original_hash is not None and not _hex(original_hash, 64):
        raise ReferenceInputError('Reference snapshot manifest hash is invalid.')
    if snapshot['source_kind'] == 'original_photo' and (
            snapshot.get('manifest_original_source_sha256') != snapshot['source_sha256']):
        raise ReferenceInputError('Original-photo snapshot is not bound to the manifest source hash.')
    if _read_card(metadata) != snapshot:
        raise ReferenceInputError('Reference snapshot metadata changed after staging.')
    try:
        data = staged.read_bytes()
    except OSError as exc:
        raise ReferenceInputError('The staged reference image is missing.') from exc
    if _sha256(data) != snapshot['staged_png_sha256']:
        raise ReferenceInputError('Staged reference PNG changed after staging.')
    if not data.startswith(b'\x89PNG\r\n\x1a\n'):
        raise ReferenceInputError('The staged reference is not a PNG.')
    rgb = _decoded_rgb(data)
    if ([rgb.width, rgb.height] != [snapshot.get('width'), snapshot.get('height')]
            or _sha256(rgb.tobytes()) != snapshot['rgb_pixel_sha256']):
        raise ReferenceInputError('Staged reference RGB pixels or dimensions changed after staging.')
    return dict(snapshot)


def stage_reference(config, row, job_id, use_original=False):
    """Create once, then validate a job's orientation-normalized RGB reference.

    Ordinary rendering stages row.file from reference_dir and hashes those bytes
    independently of the original-photo manifest hash. Original mode stages
    row.source under photo_dir and checks its bytes against row.source_sha256.
    Nothing is resized. The Comfy alias in row.comfy_image is never consulted.
    """
    namespace, directory, staged, metadata, relative = _bundle_paths(config, job_id)
    source, binding = _source_binding(config, row, use_original)
    if directory.exists():
        existing = _read_card(metadata)
        if any(existing.get(key) != value for key, value in binding.items()):
            raise ReferenceInputError('This job already has a different reference snapshot.')
        return reverify_reference(config, existing, job_id)
    if not source.is_file():
        raise ReferenceInputError('The local reference source is missing.')
    try:
        source_bytes = source.read_bytes()
    except OSError as exc:
        raise ReferenceInputError('Cannot read the local reference source.') from exc
    source_hash = _sha256(source_bytes)
    if use_original and source_hash != binding['manifest_original_source_sha256']:
        raise ReferenceInputError('Original source changed or the manifest hash is stale.')
    rgb = _decoded_rgb(source_bytes)
    encoded = io.BytesIO()
    rgb.save(encoded, format='PNG')
    png = encoded.getvalue()
    snapshot = {
        'schema': 'byrdhouse.reference-input.v1',
        'purpose': 'Immutable local Carey reference input for this job; no generative processing',
        'job_id': job_id, **binding,
        'source_sha256': source_hash, 'rgb_pixel_sha256': _sha256(rgb.tobytes()),
        'staged_png_sha256': _sha256(png), 'width': rgb.width, 'height': rgb.height,
        'comfy_image': relative, 'staged_path': str(staged), 'metadata_path': str(metadata),
        'normalization': 'exif-transpose-rgb-no-resize',
        'created': datetime.now(timezone.utc).isoformat(timespec='seconds'),
    }
    namespace.mkdir(parents=True, exist_ok=True)
    # Publish image and metadata together. Rename never replaces a populated job
    # directory; a simultaneous winner is validated instead of being overwritten.
    temporary = Path(tempfile.mkdtemp(prefix=f'.{job_id}-', dir=namespace)).resolve()
    try:
        (temporary/'reference.png').write_bytes(png)
        (temporary/'reference.png.json').write_text(
            json.dumps(snapshot, indent=2, ensure_ascii=False), encoding='utf-8')
        try:
            temporary.rename(directory)
        except OSError:
            if not directory.exists():
                raise
            existing = _read_card(metadata)
            if any(existing.get(key) != value for key, value in binding.items()):
                raise ReferenceInputError('A different reference snapshot already owns this job.')
            return reverify_reference(config, existing, job_id)
    finally:
        # Remove only this helper's verified staging directory, never a job input.
        if (temporary.exists() and temporary.is_relative_to(namespace)
                and temporary.name.startswith(f'.{job_id}-')):
            shutil.rmtree(temporary)
    return reverify_reference(config, snapshot, job_id)
