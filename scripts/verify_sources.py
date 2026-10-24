"""Read-only authenticated GitHub check of pinned README bytes and excerpts."""
import base64
from datetime import datetime, timezone
import hashlib
import json
import subprocess
from build import ROOT, extract


def main():
    data = json.loads((ROOT/'data/projects.json').read_text())
    checks = []
    for project in data['projects']:
        endpoint = f"repos/Akkaya-Furkan/{project['repo']}/contents/README.md?ref={project['commit']}"
        response = json.loads(subprocess.check_output(['gh', 'api', endpoint]))
        raw = base64.b64decode(response['content'])
        assert hashlib.sha256(raw).hexdigest() == project['readme_sha256'], project['repo']
        fields, _ = extract(raw.decode())
        assert fields == project['fields'], project['repo']
        checks.append(dict(repo=project['repo'], url=project['url'], sha256_match=True, excerpts_match=True))
    report = dict(checked_at=datetime.now(timezone.utc).isoformat(), expected=len(data['projects']),
                  verified=len(checks), checks=checks)
    path = ROOT/'docs/source-verification.json'
    path.write_text(json.dumps(report, indent=2)+'\n')
    print(f"Verified {len(checks)}/{len(data['projects'])} remote README files and excerpt sets")


if __name__ == '__main__':
    main()
