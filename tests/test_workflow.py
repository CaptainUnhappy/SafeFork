# Copyright (c) 2026 CaptainUnhappy
# SPDX-License-Identifier: MPL-2.0

import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / "skills/safefork/assets/safe-fork-sync.yml"
BASH = os.environ.get("BASH", r"C:\Program Files\Git\bin\bash.exe")
A, B, C, D, E = (letter * 40 for letter in "abcde")


def scenario(case):
    state = {
        "upstream_heads": {"main": B},
        "fork_heads": {"main": B},
        "upstream_tags": {},
        "fork_tags": {},
        "source_list_reads": 0,
        "verify_reads": 0,
        "calls": [],
    }
    if case in {"fast_forward", "dry_run", "diverged", "target_moved", "eventual_consistency", "file_drop"}:
        state["fork_heads"]["main"] = A
    if case == "tags_missing":
        state["upstream_tags"] = {"v1": D, "v2": E}
    elif case == "tag_conflict":
        state["upstream_tags"] = {"v1": D}
        state["fork_tags"] = {"v1": E}
    elif case == "new_branch":
        state["upstream_heads"]["release/v1"] = C
    elif case == "fork_only":
        state["fork_heads"]["scratch"] = A
    elif case == "reserved_branch":
        state["upstream_heads"]["sync-control"] = C
    return state


def field(args, name):
    prefix = f"{name}="
    return next(arg[len(prefix):] for arg in args if arg.startswith(prefix))


def mock_api(args):
    case = os.environ["TEST_CASE"]
    path = Path(os.environ["TEST_STATE"])
    state = json.loads(path.read_text())
    route = next(arg for arg in args if arg == "meta" or arg.startswith("repos/"))
    method = args[args.index("--method") + 1] if "--method" in args else "GET"
    state["calls"].append({"method": method, "route": route, "args": args})
    result, status = "", 0

    if route == "meta":
        result = "ssh-ed25519 AAAATEST"
    elif route == "repos/CaptainUnhappy/example-SafeFork":
        result = "owner/example"
    elif "/git/matching-refs/" in route:
        upstream = "owner/example/" in route
        ref_type = "heads" if route.endswith("/heads/") else "tags"
        refs = dict(state[("upstream_" if upstream else "fork_") + ref_type])
        if upstream:
            state["source_list_reads"] += 1
            if case == "source_changed" and state["source_list_reads"] >= 3 and ref_type == "heads":
                refs["main"] = C
        for name, sha in refs.items():
            print(f"refs/{ref_type}/{name}\t{sha}")
    elif "/compare/" in route:
        result = "diverged" if case == "diverged" else "ahead"
    elif "/git/trees/" in route:
        upstream = "owner/example/" in route
        result = "39" if upstream and case == "file_drop" else "100"
    elif "/git/ref/" in route and method == "GET":
        ref = route.split("/git/ref/", 1)[1]
        ref_type, name = ref.split("/", 1)
        refs = state["fork_heads" if ref_type == "heads" else "fork_tags"]
        result = refs.get(name, "")
        if case == "target_moved" and ref == "heads/main":
            result = C
        if case == "eventual_consistency" and ref == "heads/main" and state["fork_heads"]["main"] == B:
            state["verify_reads"] += 1
            result = A if state["verify_reads"] == 1 else B
        status = 0 if result else 1
    elif route.endswith("/git/refs") and method == "POST":
        ref, sha = field(args, "ref"), field(args, "sha")
        _, ref_type, name = ref.split("/", 2)
        refs = state["fork_heads" if ref_type == "heads" else "fork_tags"]
        if name in refs:
            status = 1
        else:
            refs[name], result = sha, sha
    elif "/git/refs/heads/" in route and method == "PATCH":
        name, sha = route.split("/git/refs/heads/", 1)[1], field(args, "sha")
        assert "force=false" in args
        state["fork_heads"][name], result = sha, sha
    else:
        raise AssertionError(f"Unexpected request: {args}")

    path.write_text(json.dumps(state))
    if result:
        print(result)
    return status


def mock_git(args):
    state_path = Path(os.environ["TEST_STATE"])
    state = json.loads(state_path.read_text())
    command = next((arg for arg in args if arg in {"init", "fetch", "rev-parse", "push"}), "")

    if command in {"init", "fetch"}:
        pass
    elif command == "rev-parse":
        _, _, ref_type, name = args[-1].split("/", 3)
        refs = state["upstream_heads" if ref_type == "heads" else "upstream_tags"]
        print(refs[name])
    elif command == "push":
        _, destination = args[-1].split(":refs/", 1)
        ref_type, name = destination.split("/", 1)
        target = state["fork_heads" if ref_type == "heads" else "fork_tags"]
        source = state["upstream_heads" if ref_type == "heads" else "upstream_tags"]
        state["calls"].append({"method": "GIT_PUSH", "route": destination, "args": args})
        target[name] = source[name]
    else:
        raise AssertionError(f"Unexpected git command: {args}")

    state_path.write_text(json.dumps(state))
    return 0


class RealGitPushTests(unittest.TestCase):
    """Exercise the template's push_ref with real Git and local repositories."""

    @classmethod
    def setUpClass(cls):
        workflow = yaml.load(WORKFLOW.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)
        script = workflow["jobs"]["sync"]["steps"][0]["run"]
        start = script.index("push_ref() {")
        end = script.index('\n\nif [ -z "$UPSTREAM_REPO"', start)
        cls.push_function = script[start:end]

    def git(self, repo, *args, input=None):
        result = subprocess.run(
            ["git", "-C", str(repo), *args], input=input, text=True,
            capture_output=True, encoding="utf-8", check=True,
        )
        return result.stdout.strip()

    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.source, self.fork, self.stage = (Path(folder.name) / name for name in ("source.git", "fork.git", "stage.git"))
        for repo in (self.source, self.fork, self.stage):
            subprocess.run(["git", "init", "--bare", "--quiet", str(repo)], check=True)
        self.git(self.source, "config", "user.name", "SafeFork Test")
        self.git(self.source, "config", "user.email", "test@example.invalid")
        tree = self.git(self.source, "hash-object", "-w", "-t", "tree", "--stdin", input="")
        self.old = self.git(self.source, "commit-tree", tree, "-m", "initial")
        middle = self.git(self.source, "commit-tree", tree, "-p", self.old, "-m", "update 1")
        self.new = self.git(self.source, "commit-tree", tree, "-p", middle, "-m", "update 2")
        self.tree = tree
        self.git(self.source, "update-ref", "refs/heads/main", self.new)
        self.git(self.fork, "fetch", "--quiet", "--no-tags", self.source.as_uri(), f"{self.old}:refs/heads/main")

    def push_ref(self, kind, name, expected):
        # Rewrite only transport URLs. Fetch, ancestry checks and push stay real.
        shim = r'''
set -euo pipefail
report() { printf '%s\n' "$1"; }
verify_ref() {
  local actual
  actual=$(command git -C "$TEST_FORK_PATH" rev-parse "refs/$1")
  [ "$actual" = "$2" ]
}
git() {
  local arg
  local -a args=()
  for arg in "$@"; do
    case "$arg" in
      "https://github.com/owner/example.git") arg=$TEST_UPSTREAM_URL ;;
      "git@github.com:CaptainUnhappy/example-SafeFork.git") arg=$TEST_FORK_PATH ;;
    esac
    args+=("$arg")
  done
  command git "${args[@]}"
}
'''
        env = dict(
            os.environ, push_dir=self.stage.as_posix(), UPSTREAM_REPO="owner/example",
            GITHUB_REPOSITORY="CaptainUnhappy/example-SafeFork",
            TEST_UPSTREAM_URL=self.source.as_uri(), TEST_FORK_PATH=self.fork.as_posix(),
        )
        return subprocess.run(
            [BASH, "-s", "--", kind, name, expected],
            input=shim + self.push_function + '\npush_ref "$@"\n',
            env=env, capture_output=True, encoding="utf-8",
        )

    def test_real_fast_forward_preserves_history_and_fork_only_ref(self):
        self.git(self.fork, "update-ref", "refs/heads/scratch", self.old)
        result = self.push_ref("heads", "main", self.new)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.git(self.fork, "rev-parse", "refs/heads/main"), self.new)
        self.assertEqual(self.git(self.stage, "rev-parse", "refs/safefork/heads/main~2"), self.old)
        self.assertEqual(self.git(self.fork, "rev-parse", "refs/heads/scratch"), self.old)

    def test_real_new_branch_copy_preserves_history(self):
        self.git(self.source, "update-ref", "refs/heads/release/v1", self.new)
        result = self.push_ref("heads", "release/v1", self.new)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.git(self.fork, "rev-parse", "refs/heads/release/v1"), self.new)
        self.assertEqual(self.git(self.fork, "rev-parse", "refs/heads/release/v1~2"), self.old)

    def test_real_annotated_tag_copy_preserves_object_and_history(self):
        self.git(self.source, "-c", "tag.gpgSign=false", "tag", "-a", "v1", "-m", "release", self.new)
        tag_sha = self.git(self.source, "rev-parse", "refs/tags/v1")
        result = self.push_ref("tags", "v1", tag_sha)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.git(self.fork, "rev-parse", "refs/tags/v1"), tag_sha)
        self.assertEqual(self.git(self.fork, "cat-file", "-t", tag_sha), "tag")
        self.assertEqual(self.git(self.fork, "rev-parse", "refs/tags/v1^{}"), self.new)
        self.assertEqual(self.git(self.fork, "rev-parse", "refs/tags/v1~2"), self.old)

    def test_real_push_rejects_divergence_without_overwrite(self):
        fork_tip = self.git(self.source, "commit-tree", self.tree, "-p", self.old, "-m", "fork work")
        self.git(self.fork, "fetch", "--quiet", "--no-tags", self.source.as_uri(), f"{fork_tip}:refs/heads/main")
        result = self.push_ref("heads", "main", self.new)
        self.assertNotEqual(result.returncode, 0)
        self.assertRegex(result.stderr, r"\((?:fetch first|non-fast-forward)\)")
        self.assertEqual(self.git(self.fork, "rev-parse", "refs/heads/main"), fork_tip)

    def test_real_source_sha_mismatch_writes_nothing(self):
        result = self.push_ref("heads", "main", self.old)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("fetched SHA differs", result.stdout)
        self.assertEqual(self.git(self.fork, "rev-parse", "refs/heads/main"), self.old)


class WorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        workflow = yaml.load(WORKFLOW.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)
        cls.workflow = workflow
        cls.script = workflow["jobs"]["sync"]["steps"][0]["run"]

    def test_contract_and_syntax(self):
        self.assertEqual(self.workflow["permissions"], {"contents": "read"})
        self.assertIn('upstream_tags_raw=$(list_refs "$UPSTREAM_REPO" tags)', self.script)
        self.assertNotIn("--method DELETE", self.script)
        self.assertNotIn("force=true", self.script)
        result = subprocess.run([BASH, "-n"], input=self.script, text=True, capture_output=True, encoding="utf-8")
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_behavior(self):
        cases = {
            "aligned": (0, 0), "tags_missing": (0, 2), "new_branch": (0, 1),
            "fork_only": (0, 0), "fast_forward": (0, 1), "dry_run": (0, 0),
            "diverged": (1, 0), "tag_conflict": (1, 0), "source_changed": (1, 0),
            "target_moved": (1, 0), "eventual_consistency": (0, 1),
            "file_drop": (1, 0), "reserved_branch": (1, 0),
        }
        for case, (expected_exit, expected_writes) in cases.items():
            with self.subTest(case=case), tempfile.TemporaryDirectory() as folder:
                state_path = Path(folder) / "state.json"
                state_path.write_text(json.dumps(scenario(case)))
                env = dict(
                    os.environ,
                    GITHUB_REPOSITORY="CaptainUnhappy/example-SafeFork",
                    UPSTREAM_REPO="owner/example",
                    CONTROL_BRANCH="sync-control",
                    PRIMARY_BRANCH="main",
                    MIN_FILE_COUNT="3",
                    MIN_FILE_PERCENT="40",
                    SAFEFORK_DEPLOY_KEY="test-private-key",
                    DRY_RUN="true" if case == "dry_run" else "false",
                    GITHUB_STEP_SUMMARY=(Path(folder) / "summary.md").as_posix(),
                    TEST_CASE=case,
                    TEST_STATE=state_path.as_posix(),
                    PYTHONIOENCODING="utf-8",
                )
                command = shlex.quote(Path(sys.executable).as_posix()) + " " + shlex.quote(Path(__file__).as_posix())
                shim = "gh() { " + command + ' mock "$@"; }\ngit() { ' + command + ' git-mock "$@"; }\nsleep() { :; }\n'
                result = subprocess.run([BASH, "-s"], input=shim + self.script, env=env, capture_output=True, encoding="utf-8")
                self.assertEqual(result.returncode, expected_exit, result.stdout + result.stderr)
                calls = json.loads(state_path.read_text())["calls"]
                writes = [call for call in calls if call["method"] in {"POST", "PATCH", "DELETE", "GIT_PUSH"}]
                self.assertEqual(len(writes), expected_writes, result.stdout + result.stderr)
                self.assertFalse(any(call["method"] == "DELETE" for call in writes))
                self.assertFalse(any("force=true" in call["args"] for call in writes))


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "mock":
        sys.exit(mock_api(sys.argv[2:]))
    if len(sys.argv) > 1 and sys.argv[1] == "git-mock":
        sys.exit(mock_git(sys.argv[2:]))
    unittest.main(verbosity=2)
