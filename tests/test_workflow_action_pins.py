"""GitHub workflow supply-chain contract: external actions use immutable refs.

Pure stdlib parsing intentionally checks only the action references, not the
semantics of a workflow. Actual YAML parsing and action startup remain hosted
CI responsibilities.
"""
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"
USES = re.compile(r"^\s*(?:-\s*)?uses:\s*([^\s#]+)", flags=re.MULTILINE)
PIN = re.compile(r"^[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)+@[0-9a-f]{40}$")


class GitHubActionPinTest(unittest.TestCase):
    def test_every_external_action_has_immutable_commit_reference(self):
        files = sorted(WORKFLOWS.glob("*.yml"))
        self.assertGreaterEqual(len(files), 2)
        actions = []
        for path in files:
            content = path.read_text(encoding="utf-8")
            actions.extend((path.name, ref) for ref in USES.findall(content))
        self.assertGreaterEqual(len(actions), 14)
        for filename, reference in actions:
            with self.subTest(file=filename, uses=reference):
                if reference.startswith("./"):
                    continue  # local repository action, not external code
                self.assertRegex(reference, PIN)

    def test_pinned_workflows_keep_least_privilege_read_token(self):
        for path in WORKFLOWS.glob("*.yml"):
            with self.subTest(workflow=path.name):
                source = path.read_text(encoding="utf-8")
                self.assertRegex(source, r"(?m)^permissions:\s*\n\s*contents:\s*read\s*$")


if __name__ == "__main__":
    unittest.main()
