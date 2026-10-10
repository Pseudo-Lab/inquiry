import contextlib
import io
import json
import os
from pathlib import Path
import re
import subprocess
from tempfile import TemporaryDirectory
import unittest
from unittest import mock

from inquiry.cli import main
from inquiry.config import ConfigError, OpenAISettings, check_config, load_openai_settings


SYNTHETIC_KEY = "sk-test-config-canary-do-not-use"


def _write_env(root, *, key=SYNTHETIC_KEY, model="gpt-5.6-terra", text=None):
    path = Path(root, ".env")
    content = text if text is not None else f"OPENAI_API_KEY={key}\nINQUIRY_MODEL={model}\n"
    path.write_text(content, encoding="utf-8")
    path.chmod(0o600)
    return path


class ConfigTests(unittest.TestCase):
    def test_loads_only_the_explicit_root_without_environment_fallback(self):
        with TemporaryDirectory() as parent:
            root = Path(parent, "project")
            root.mkdir()
            _write_env(parent, key="sk-parent-secret", model="parent-model")
            _write_env(root)
            with mock.patch.dict(os.environ, {
                "OPENAI_API_KEY": "sk-environment-secret",
                "INQUIRY_MODEL": "environment-model",
            }):
                before = dict(os.environ)
                settings = load_openai_settings(root)
                after = dict(os.environ)

            self.assertEqual(settings.api_key, SYNTHETIC_KEY)
            self.assertEqual(settings.model, "gpt-5.6-terra")
            self.assertEqual(after, before)
            self.assertNotIn(SYNTHETIC_KEY, repr(settings))

    def test_model_override_is_explicit_and_interpolation_is_disabled(self):
        with TemporaryDirectory() as root:
            _write_env(root, text=(
                "OPENAI_API_KEY=${UNTRUSTED_KEY}\n"
                "INQUIRY_MODEL=${UNTRUSTED_MODEL}\n"
            ))
            with mock.patch.dict(os.environ, {
                "UNTRUSTED_KEY": "expanded-secret",
                "UNTRUSTED_MODEL": "expanded-model",
            }):
                settings = load_openai_settings(root, model="gpt-5.6-terra")

            self.assertEqual(settings.api_key, "${UNTRUSTED_KEY}")
            self.assertEqual(settings.model, "gpt-5.6-terra")

    def test_missing_blank_duplicate_and_parse_errors_are_static_and_secret_free(self):
        cases = (
            (None, "Project .env file is missing."),
            ("OPENAI_API_KEY=\nINQUIRY_MODEL=gpt-5.6-terra\n", "Project .env must define a non-empty OPENAI_API_KEY."),
            (f"OPENAI_API_KEY={SYNTHETIC_KEY}\nINQUIRY_MODEL=\n", "Project .env must define a non-empty INQUIRY_MODEL."),
            (f"OPENAI_API_KEY={SYNTHETIC_KEY}\nOPENAI_API_KEY=other\nINQUIRY_MODEL=gpt-5.6-terra\n", "Project .env contains duplicate settings."),
            (f"OPENAI_API_KEY={SYNTHETIC_KEY}\nINQUIRY_MODEL='unterminated\n", "Project .env is invalid."),
        )
        for text, expected in cases:
            with self.subTest(expected=expected), TemporaryDirectory() as root:
                if text is not None:
                    _write_env(root, text=text)
                stdout = io.StringIO()
                stderr = io.StringIO()
                with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                    with self.assertRaisesRegex(ConfigError, f"^{re.escape(expected)}$") as raised:
                        load_openai_settings(root)
                combined = f"{raised.exception}{stdout.getvalue()}{stderr.getvalue()}"
                self.assertNotIn(SYNTHETIC_KEY, combined)
                self.assertNotIn("unterminated", combined)

    def test_rejects_symlink_broad_permissions_and_wrong_owner(self):
        with TemporaryDirectory() as parent:
            target = Path(parent, "target")
            target.write_text(f"OPENAI_API_KEY={SYNTHETIC_KEY}\nINQUIRY_MODEL=gpt-5.6-terra\n", encoding="utf-8")
            target.chmod(0o600)
            symlink_root = Path(parent, "symlink-root")
            symlink_root.mkdir()
            Path(symlink_root, ".env").symlink_to(target)
            with self.assertRaisesRegex(ConfigError, "Project .env must be a secure regular file owned by the current user."):
                load_openai_settings(symlink_root)

        with TemporaryDirectory() as root:
            path = _write_env(root)
            path.chmod(0o644)
            with self.assertRaisesRegex(ConfigError, "Project .env permissions must deny group and other access."):
                load_openai_settings(root)

        with TemporaryDirectory() as root:
            _write_env(root)
            real_fstat = os.fstat

            def wrong_owner(fd):
                stat_result = real_fstat(fd)
                values = list(stat_result)
                values[4] = os.getuid() + 1
                return os.stat_result(values)

            with mock.patch("inquiry.config.os.fstat", side_effect=wrong_owner):
                with self.assertRaisesRegex(ConfigError, "Project .env must be a secure regular file owned by the current user."):
                    load_openai_settings(root)

    @unittest.skipUnless(hasattr(os, "mkfifo"), "FIFO test requires POSIX")
    def test_rejects_nonregular_env_without_blocking(self):
        with TemporaryDirectory() as root:
            os.mkfifo(Path(root, ".env"), 0o600)
            with self.assertRaisesRegex(ConfigError, "Project .env must be a secure regular file owned by the current user."):
                load_openai_settings(root)

    @unittest.skipUnless(os.name == "posix", "Git safety contract is POSIX-only")
    def test_git_repository_requires_ignored_and_untracked_env(self):
        with TemporaryDirectory() as root:
            subprocess.run(["git", "init", "-q", root], check=True)
            path = _write_env(root)
            with self.assertRaisesRegex(ConfigError, "Project .env must be ignored by Git."):
                load_openai_settings(root)

            Path(root, ".gitignore").write_text(".env\n", encoding="utf-8")
            self.assertEqual(load_openai_settings(root).model, "gpt-5.6-terra")

            subprocess.run(["git", "-C", root, "add", "-f", ".env"], check=True)
            with self.assertRaisesRegex(ConfigError, "Project .env must not be tracked by Git."):
                load_openai_settings(root)
            path.chmod(0o600)

    def test_git_inspection_failure_is_closed(self):
        with TemporaryDirectory() as root:
            _write_env(root)
            failed = subprocess.CompletedProcess(["git"], 2, stdout=b"", stderr=b"secret-like diagnostic")
            overrides = {
                "GIT_DIR": "/redirected/git-dir",
                "GIT_WORK_TREE": "/redirected/work-tree",
                "GIT_INDEX_FILE": "/redirected/index",
                "GIT_COMMON_DIR": "/redirected/common-dir",
                "GIT_OBJECT_DIRECTORY": "/redirected/objects",
                "GIT_ALTERNATE_OBJECT_DIRECTORIES": "/redirected/alternate-objects",
                "GIT_CONFIG_COUNT": "1",
                "GIT_CONFIG_KEY_0": "core.excludesFile",
                "GIT_CONFIG_VALUE_0": "/redirected/excludes",
            }
            with mock.patch.dict(os.environ, overrides):
                before = dict(os.environ)
                with mock.patch("inquiry.config.subprocess.run", return_value=failed) as run:
                    with self.assertRaisesRegex(ConfigError, "Could not verify project .env Git safety.") as raised:
                        load_openai_settings(root)
                self.assertEqual(dict(os.environ), before)
            self.assertNotIn("diagnostic", str(raised.exception))
            self.assertTrue(all(call.kwargs.get("shell") is False for call in run.call_args_list))
            child_environment = run.call_args.kwargs["env"]
            self.assertFalse(any(name.startswith("GIT_") for name in child_environment))
            self.assertEqual(child_environment.get("PATH"), before.get("PATH"))

    @unittest.skipUnless(os.name == "posix", "Git safety contract is POSIX-only")
    def test_git_checks_ignore_repository_and_config_environment_overrides(self):
        with TemporaryDirectory() as parent:
            victim = Path(parent, "victim")
            foreign = Path(parent, "foreign")
            victim.mkdir()
            foreign.mkdir()
            subprocess.run(["git", "init", "-q", victim], check=True)
            subprocess.run(["git", "init", "-q", foreign], check=True)

            _write_env(victim)
            subprocess.run(["git", "-C", victim, "add", "-f", ".env"], check=True)
            Path(foreign, ".git", "info", "exclude").write_text(".env\n", encoding="utf-8")
            redirect = {
                "GIT_DIR": str(Path(foreign, ".git")),
                "GIT_WORK_TREE": str(victim),
            }
            with mock.patch.dict(os.environ, redirect):
                before = dict(os.environ)
                with self.assertRaisesRegex(ConfigError, "Project .env must not be tracked by Git."):
                    load_openai_settings(victim)
                self.assertEqual(dict(os.environ), before)

            subprocess.run(["git", "-C", victim, "rm", "--cached", "-q", ".env"], check=True)
            excludes = Path(parent, "injected-ignore")
            excludes.write_text(".env\n", encoding="utf-8")
            config_injection = {
                "GIT_CONFIG_COUNT": "1",
                "GIT_CONFIG_KEY_0": "core.excludesFile",
                "GIT_CONFIG_VALUE_0": str(excludes),
            }
            with mock.patch.dict(os.environ, config_injection):
                before = dict(os.environ)
                with self.assertRaisesRegex(ConfigError, "Project .env must be ignored by Git."):
                    load_openai_settings(victim)
                self.assertEqual(dict(os.environ), before)

    def test_check_config_and_cli_emit_only_masked_status(self):
        with TemporaryDirectory() as root:
            _write_env(root)
            status = check_config(root)
            self.assertEqual(status, {
                "provider": "openai",
                "model": "gpt-5.6-terra",
                "api_key_configured": True,
                "permissions": "protected",
                "git": "not-applicable",
            })
            self.assertNotIn(SYNTHETIC_KEY, repr(status))

            stdout = io.StringIO()
            stderr = io.StringIO()
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                main(["--dir", root, "config", "check"])
            self.assertEqual(json.loads(stdout.getvalue()), status)
            self.assertNotIn(SYNTHETIC_KEY, stdout.getvalue() + stderr.getvalue())


class SettingsRepresentationTests(unittest.TestCase):
    def test_api_key_is_excluded_from_repr(self):
        settings = OpenAISettings(SYNTHETIC_KEY, "gpt-5.6-terra")
        self.assertNotIn(SYNTHETIC_KEY, repr(settings))


if __name__ == "__main__":
    unittest.main()
