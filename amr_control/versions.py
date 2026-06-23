"""Deployed service-version introspection.

The webapp talks to the robot over MQTT and is otherwise decoupled from the
ROS2 stack, but it runs on the same host and already mounts the Docker socket
read-only (the live-logs feature shells out to ``docker logs``). We reuse that
access here to report the *deployed* version of every service container.

Each image is stamped by CI with the git commit it was built from via the
standard OCI label ``org.opencontainers.image.revision``; the deploy pins the
image to a release tag (e.g. ``jazzy-0.3.0``) via ``WEBAPP_VERSION`` /
``ROBOT_VERSION``. Reading the running container's image tag + that label tells
us exactly what is live without touching the hardware/nav repos at all.

``nav`` is an opt-in compose profile, so its container may be absent — that is
reported as ``running: False`` rather than an error.
"""
import json
import subprocess
import threading
import time

# (service key, container name). Container names are fixed by the deploy
# compose files in cmexa_install. nav may be absent (opt-in profile).
SERVICE_CONTAINERS = (
    ('webapp', 'cmexa-webapp'),
    ('hardware', 'cmexaiii-hardware'),
    ('nav', 'cmexaiii-nav'),
    ('brickd', 'cmexa-brickd'),
)

# Versions only change on a redeploy, so a short cache keeps page loads from
# spawning a `docker inspect` per service every time.
_CACHE_TTL_SEC = 60.0
_REVISION_LABEL = 'org.opencontainers.image.revision'
_CREATED_LABEL = 'org.opencontainers.image.created'

_cache = {'at': 0.0, 'data': None}
_lock = threading.Lock()


def _tag_from_image(image):
    """Extract the tag from an image ref, ignoring any registry host:port.

    'ghcr.io/cme-research/cmexa_hardware:jazzy-0.3.0' -> 'jazzy-0.3.0'
    'ghcr.io/.../img' (no tag) -> None
    """
    if not image:
        return None
    last_segment = image.rsplit('/', 1)[-1]
    if ':' not in last_segment:
        return None
    return last_segment.rsplit(':', 1)[1]


def _friendly_version(tag, short_sha):
    """Human-facing version string shown on the navbar badge.

    Prefer a pinned release tag (jazzy-0.3.0). When the deploy uses a moving
    tag (``*-latest``/``latest``) the tag is meaningless, so fall back to the
    short git sha, which is always precise.
    """
    if tag and tag != 'latest' and not tag.endswith('-latest'):
        return tag
    if short_sha:
        return short_sha
    return tag or 'unknown'


def _inspect(container):
    """Return a version record for one container.

    A missing container (e.g. nav profile disabled) or unavailable Docker
    socket yields a record with ``running: False`` rather than raising, so the
    UI can show every service row regardless.
    """
    record = {
        'container': container,
        'running': False,
        'image': None,
        'tag': None,
        'revision': None,
        'revision_short': None,
        'built': None,
        'version': 'unknown',
    }
    try:
        out = subprocess.run(
            ['docker', 'inspect', container],
            capture_output=True, text=True, timeout=5,
        )
    except FileNotFoundError:
        record['error'] = 'docker CLI not available'
        return record
    except subprocess.TimeoutExpired:
        record['error'] = 'docker inspect timed out'
        return record
    except Exception as exc:  # pragma: no cover - defensive
        record['error'] = str(exc)
        return record

    if out.returncode != 0:
        # `No such object` => not deployed; anything else => surface briefly.
        stderr = (out.stderr or '').strip()
        if stderr and 'No such object' not in stderr:
            record['error'] = stderr
        return record

    try:
        info = json.loads(out.stdout)[0]
    except (ValueError, IndexError):
        record['error'] = 'unparseable docker inspect output'
        return record

    config = info.get('Config') or {}
    labels = config.get('Labels') or {}
    state = info.get('State') or {}

    image = config.get('Image') or ''
    revision = labels.get(_REVISION_LABEL)
    short_sha = revision[:7] if revision else None

    record['running'] = bool(state.get('Running'))
    record['image'] = image or None
    record['tag'] = _tag_from_image(image)
    record['revision'] = revision
    record['revision_short'] = short_sha
    record['built'] = labels.get(_CREATED_LABEL) or info.get('Created')
    record['version'] = _friendly_version(record['tag'], short_sha)
    return record


def get_service_versions(force=False):
    """Return version records for all known service containers (cached)."""
    now = time.time()
    with _lock:
        cached = _cache['data']
        if not force and cached is not None and (now - _cache['at']) < _CACHE_TTL_SEC:
            return cached

    data = [dict(service=key, **_inspect(name)) for key, name in SERVICE_CONTAINERS]

    with _lock:
        _cache['at'] = time.time()
        _cache['data'] = data
    return data


def get_webapp_version():
    """Convenience: the webapp's own friendly version string (or 'unknown')."""
    for record in get_service_versions():
        if record['service'] == 'webapp':
            return record['version']
    return 'unknown'
