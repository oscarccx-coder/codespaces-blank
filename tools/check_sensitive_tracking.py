"""Fail on indexed private runtime paths or recognizable credential literals.

This bounded pattern scan does not certify history or unknown secret formats.
Only filenames/rule names are emitted, never matched credential values.
"""
import argparse
import pathlib
import re
import subprocess

def sensitive(path):
    p = pathlib.PurePosixPath(path.lower())
    return (bool(set(p.parts) & {'storage', 'recordings', 'audio', 'workspace', 'models'})
            or p.suffix in {'.db', '.sqlite', '.sqlite3', '.log', '.wav', '.mp3', '.m4a', '.flac', '.ogg', '.pcm', '.key', '.pem', '.p12', '.pfx'}
            or p.name.endswith(('.db-wal', '.db-shm', '.sqlite-wal', '.sqlite-shm'))
            or p.name == '.env' or p.name.startswith('.env.')
            or p.name.endswith('.env'))

PATTERNS = {
    'provider-token': re.compile(rb'(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{50,}|sk-(?:proj-)?[A-Za-z0-9_-]{30,}|xox[baprs]-[A-Za-z0-9-]{20,}|AKIA[0-9A-Z]{16})'),
    'private-key': re.compile(rb'-----BEGIN (?:RSA |EC |OPENSSH |ENCRYPTED )?PRIVATE KEY-----'),
    'device-auth-token': re.compile(rb'''["']auth_token["']\s*:\s*["'][A-Za-z0-9_-]{32,}["']'''),
}

def check(root, secrets=False):
    def git(*args):
        return subprocess.check_output(['git', '-C', str(root), *args])
    entries = git('ls-files', '--stage', '-z').split(b'\0')
    findings = []
    seen = set()
    for entry in entries:
        if not entry: continue
        meta, name = entry.split(b'\t', 1)
        mode, sha, stage = meta.split()
        path = name.decode('utf-8', 'surrogateescape')
        if not secrets:
            if sensitive(path): findings.append((path, 'sensitive-path'))
            continue
        if sha in seen or mode == b'160000': continue
        seen.add(sha)
        # Read the index blob, not mutable working-tree contents.
        data = git('cat-file', 'blob', sha.decode())
        for rule, pattern in PATTERNS.items():
            if pattern.search(data): findings.append((path, rule))
    return findings

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=pathlib.Path, default=pathlib.Path('.'))
    parser.add_argument('--secrets', action='store_true')
    args = parser.parse_args()
    findings = check(args.root, args.secrets)
    for path, rule in findings: print(f'FAIL {rule}: {path!r}')
    print(f'{"FAIL" if findings else "PASS"}: {len(findings)} finding(s); {"indexed secret patterns" if args.secrets else "indexed private paths"}')
    raise SystemExit(bool(findings))
