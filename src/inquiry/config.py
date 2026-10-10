"""Project-local OpenAI settings with file and Git safety checks."""

from dataclasses import dataclass, field
from io import StringIO
import os
from pathlib import Path
import stat
import subprocess

from dotenv import dotenv_values
from dotenv.parser import parse_stream


MISSING_FILE = "Project .env file is missing."
UNSAFE_FILE = "Project .env must be a secure regular file owned by the current user."
UNSAFE_PERMISSIONS = "Project .env permissions must deny group and other access."
INVALID_FILE = "Project .env is invalid."
DUPLICATE_SETTINGS = "Project .env contains duplicate settings."
MISSING_API_KEY = "Project .env must define a non-empty OPENAI_API_KEY."
MISSING_MODEL = "Project .env must define a non-empty INQUIRY_MODEL."
TRACKED_FILE = "Project .env must not be tracked by Git."
UNIGNORED_FILE = "Project .env must be ignored by Git."
GIT_CHECK_FAILED = "Could not verify project .env Git safety."


class ConfigError(ValueError):
    """A safe, application-owned configuration error."""


@dataclass(frozen=True)
class OpenAISettings:
    api_key: str = field(repr=False)
    model: str


def _run_git(root, *arguments):
    git_environment = {
        name: value for name, value in os.environ.items()
        if not name.startswith("GIT_")
    }
    try:
        return subprocess.run(
            ["git", "-C", os.path.abspath(root), *arguments],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=git_environment,
            check=False,
            shell=False,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        raise ConfigError(GIT_CHECK_FAILED) from None


def _has_git_marker(root):
    current = Path(root)
    for directory in (current, *current.parents):
        try:
            if os.path.lexists(os.path.join(directory, ".git")):
                return True
        except OSError:
            raise ConfigError(GIT_CHECK_FAILED) from None
    return False


def _check_git(root):
    repository = _run_git(root, "rev-parse", "--is-inside-work-tree")
    if repository.returncode != 0:
        if repository.returncode == 128 and not _has_git_marker(root):
            return "not-applicable"
        raise ConfigError(GIT_CHECK_FAILED)
    if repository.stdout.strip() != b"true":
        raise ConfigError(GIT_CHECK_FAILED)

    tracked = _run_git(root, "ls-files", "--error-unmatch", "--", ".env")
    if tracked.returncode == 0:
        raise ConfigError(TRACKED_FILE)
    if tracked.returncode != 1:
        raise ConfigError(GIT_CHECK_FAILED)

    ignored = _run_git(root, "check-ignore", "-q", "--", ".env")
    if ignored.returncode == 1:
        raise ConfigError(UNIGNORED_FILE)
    if ignored.returncode != 0:
        raise ConfigError(GIT_CHECK_FAILED)
    return "protected"


def _validate_stat(file_stat):
    if not stat.S_ISREG(file_stat.st_mode) or file_stat.st_uid != os.getuid():
        raise ConfigError(UNSAFE_FILE)
    if stat.S_IMODE(file_stat.st_mode) & 0o077:
        raise ConfigError(UNSAFE_PERMISSIONS)


def _read_env(root):
    path = os.path.join(root, ".env")
    flags = os.O_RDONLY | os.O_NONBLOCK
    nofollow = getattr(os, "O_NOFOLLOW", None)
    if nofollow is None:
        raise ConfigError(UNSAFE_FILE)
    flags |= nofollow
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC

    try:
        descriptor = os.open(path, flags)
    except FileNotFoundError:
        raise ConfigError(MISSING_FILE) from None
    except OSError:
        raise ConfigError(UNSAFE_FILE) from None

    try:
        initial_stat = os.fstat(descriptor)
        _validate_stat(initial_stat)
        git_status = _check_git(root)
        with os.fdopen(descriptor, "r", encoding="utf-8", errors="strict", newline="") as stream:
            descriptor = -1
            contents = stream.read()
            final_stat = os.fstat(stream.fileno())
        _validate_stat(final_stat)
        if (initial_stat.st_dev, initial_stat.st_ino) != (final_stat.st_dev, final_stat.st_ino):
            raise ConfigError(UNSAFE_FILE)
        return contents, git_status
    except UnicodeError:
        raise ConfigError(INVALID_FILE) from None
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def _parse_env(contents):
    seen = set()
    try:
        for binding in parse_stream(StringIO(contents)):
            if binding.error:
                raise ConfigError(INVALID_FILE)
            if binding.key is None:
                continue
            if binding.key in seen:
                raise ConfigError(DUPLICATE_SETTINGS)
            seen.add(binding.key)
        values = dotenv_values(stream=StringIO(contents), interpolate=False)
    except ConfigError:
        raise
    except Exception:
        raise ConfigError(INVALID_FILE) from None
    return values


def _required_value(values, name, message):
    value = values.get(name)
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(message)
    return value.strip()


def _load(root, model):
    absolute_root = os.path.abspath(os.fspath(root))
    contents, git_status = _read_env(absolute_root)
    values = _parse_env(contents)
    api_key = _required_value(values, "OPENAI_API_KEY", MISSING_API_KEY)
    selected_model = model if model is not None else values.get("INQUIRY_MODEL")
    if not isinstance(selected_model, str) or not selected_model.strip():
        raise ConfigError(MISSING_MODEL)
    return OpenAISettings(api_key=api_key, model=selected_model.strip()), git_status


def load_openai_settings(root, *, model=None):
    """Load settings exclusively from ``root/.env`` without mutating the environment."""

    settings, _ = _load(root, model)
    return settings


def check_config(root, *, model=None):
    """Return validated configuration status without credential material."""

    settings, git_status = _load(root, model)
    return {
        "provider": "openai",
        "model": settings.model,
        "api_key_configured": True,
        "permissions": "protected",
        "git": git_status,
    }
