import ast
import json
import re
from datetime import datetime, timezone
from pathlib import Path


class Module:
    def __init__(self, context=None):
        context = context or {}
        base = Path(context.get("base_dir", ".")).resolve()
        self.base = base
        self.workspace = (base / "workspace").resolve()
        self.storage = (base / "storage").resolve()
        self.project_context_path = self.storage / "state" / "active_project.json"
        self.workspace.mkdir(parents=True, exist_ok=True)
        self.storage.mkdir(parents=True, exist_ok=True)

    def tools(self):
        return [
            {
                "name": "active_project",
                "description": "Return Apollo's persistent active Workspace project. This survives restarts.",
                "parameters": {"type": "object", "properties": {}}
            },
            {
                "name": "list_projects",
                "description": "List real project folders currently under Apollo/workspace.",
                "parameters": {"type": "object", "properties": {}}
            },
            {
                "name": "set_active_project",
                "description": "Set the persistent active Workspace project by existing project name.",
                "parameters": {
                    "type": "object",
                    "properties": {"project": {"type": "string"}},
                    "required": ["project"]
                }
            },
            {
                "name": "write_files",
                "description": (
                    "Create or replace a complete multi-file coding project in ONE call. "
                    "Use this for ordinary apps, scripts, websites and projects whose files "
                    "must work together. Every supplied code block must become a real file. "
                    "Apollo performs static syntax/local-link verification after writing. "
                    "Do NOT use for Apollo extension modules; use module_factory."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "project": {"type": "string", "description": "Project folder inside Apollo/workspace."},
                        "files": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "path": {"type": "string"},
                                    "content": {"type": "string"}
                                },
                                "required": ["path", "content"]
                            }
                        },
                        "overwrite": {"type": "boolean"}
                    },
                    "required": ["project", "files"]
                }
            },
            {
                "name": "write_file",
                "description": "Create or replace one real text/code file inside Apollo/workspace.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "content": {"type": "string"},
                        "overwrite": {"type": "boolean"}
                    },
                    "required": ["path", "content"]
                }
            },
            {
                "name": "verify_project",
                "description": (
                    "Statically verify an existing workspace project without executing it. "
                    "Checks Python syntax, relative/local Python imports and common local web-file references."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {"project": {"type": "string"}},
                    "required": ["project"]
                }
            },
            {
                "name": "inspect_project",
                "description": "Return the real project tree and Apollo project metadata.",
                "parameters": {
                    "type": "object",
                    "properties": {"project": {"type": "string"}},
                    "required": ["project"]
                }
            },
            {
                "name": "create_folder",
                "description": "Create a folder inside Apollo's workspace.",
                "parameters": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}
            },
            {
                "name": "list_files",
                "description": "List real files currently in Apollo's workspace.",
                "parameters": {"type": "object", "properties": {"path": {"type": "string"}}}
            },
            {
                "name": "read_file",
                "description": "Read a text/code file from Apollo's workspace.",
                "parameters": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}
            }
        ]

    def _load_active_project(self):
        try:
            data = json.loads(
                self.project_context_path.read_text(encoding="utf-8")
            )
            if not isinstance(data, dict):
                return {}
        except Exception:
            return {}

        project = str(data.get("project", "")).strip()
        if not project:
            return {}

        try:
            project_path = self._safe(project)
        except Exception:
            return {}

        if not project_path.is_dir():
            return {}

        data["project"] = project
        data["path"] = str(project_path)
        return data

    def _save_active_project(self, project, reason="file_builder"):
        project = str(project or "").strip().replace("\\", "/").strip("/")
        if not project:
            return {}

        project_path = self._safe(project)
        if not project_path.is_dir():
            raise FileNotFoundError(
                f"Workspace project does not exist: {project}"
            )

        payload = {
            "project": project,
            "path": str(project_path),
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "reason": str(reason or "file_builder"),
        }
        temp = self.project_context_path.with_suffix(".tmp")
        temp.write_text(
            json.dumps(payload, indent=2),
            encoding="utf-8",
        )
        temp.replace(self.project_context_path)
        return payload

    def _list_projects(self):
        projects = []
        if not self.workspace.exists():
            return projects

        for path in sorted(
            self.workspace.iterdir(),
            key=lambda item: item.name.lower(),
        ):
            if not path.is_dir():
                continue
            if path.name.startswith(".") or path.name.startswith("_"):
                continue

            manifest_path = path / ".apollo_project.json"
            metadata = {}
            if manifest_path.is_file():
                try:
                    metadata = json.loads(
                        manifest_path.read_text(encoding="utf-8")
                    )
                except Exception:
                    metadata = {}

            projects.append({
                "project": path.name,
                "path": str(path),
                "managed": manifest_path.is_file(),
                "updated_at": metadata.get("updated_at", ""),
                "files": sum(
                    1 for item in path.rglob("*")
                    if item.is_file()
                ),
            })

        return projects

    def _safe(self, relative):
        relative = str(relative or "").strip().replace("\\", "/")
        if not relative:
            return self.workspace
        p = Path(relative)
        if p.is_absolute():
            raise PermissionError("Absolute paths are not allowed.")
        parts = [part.lower() for part in p.parts]
        if parts and parts[0] in {"modules", "pending_modules"}:
            raise PermissionError(
                "file_builder cannot create Apollo extension modules. "
                "Use module_factory__create_candidate so the module remains pending until approval."
            )
        target = (self.workspace / p).resolve()
        if target != self.workspace and self.workspace not in target.parents:
            raise PermissionError("Path escapes Apollo workspace.")
        return target

    @staticmethod
    def _local_module_candidates(project_root):
        result = set()
        for p in project_root.rglob('*.py'):
            rel = p.relative_to(project_root)
            if p.name == '__init__.py':
                if rel.parent.parts:
                    result.add('.'.join(rel.parent.parts))
            else:
                result.add('.'.join(rel.with_suffix('').parts))
                if len(rel.parts) == 1:
                    result.add(rel.stem)
        return result

    def _verify_project(self, project_root):
        project_root = project_root.resolve()
        errors, warnings, checked = [], [], []
        py_modules = self._local_module_candidates(project_root)
        top_local = {x.split('.')[0] for x in py_modules}

        for p in sorted(project_root.rglob('*')):
            if not p.is_file() or p.name == '.apollo_project.json':
                continue
            rel = str(p.relative_to(project_root)).replace('\\', '/')
            checked.append(rel)
            if p.suffix.lower() == '.py':
                text = p.read_text(encoding='utf-8', errors='replace')
                try:
                    tree = ast.parse(text, filename=rel)
                except SyntaxError as exc:
                    errors.append({
                        'file': rel,
                        'kind': 'python_syntax',
                        'line': exc.lineno,
                        'message': exc.msg,
                    })
                    continue

                for node in ast.walk(tree):
                    if isinstance(node, ast.ImportFrom):
                        if node.level > 0:
                            parent = list(p.relative_to(project_root).parent.parts)
                            up = max(0, node.level - 1)
                            base = parent[: max(0, len(parent)-up)]
                            if node.module:
                                candidate = '.'.join(base + node.module.split('.'))
                                if candidate and candidate not in py_modules:
                                    candidate_path = project_root.joinpath(*candidate.split('.'))
                                    if not (candidate_path.with_suffix('.py').exists() or (candidate_path/'__init__.py').exists()):
                                        errors.append({'file': rel, 'kind': 'missing_local_import', 'message': f"Relative import target not found: {candidate}"})
                        elif node.module:
                            root = node.module.split('.')[0]
                            if root in top_local and node.module not in py_modules:
                                candidate_path = project_root.joinpath(*node.module.split('.'))
                                if not (candidate_path.with_suffix('.py').exists() or (candidate_path/'__init__.py').exists()):
                                    errors.append({'file': rel, 'kind': 'missing_local_import', 'message': f"Local import target not found: {node.module}"})
                    elif isinstance(node, ast.Import):
                        for alias in node.names:
                            root = alias.name.split('.')[0]
                            if root in top_local and alias.name not in py_modules:
                                candidate_path = project_root.joinpath(*alias.name.split('.'))
                                if not (candidate_path.with_suffix('.py').exists() or (candidate_path/'__init__.py').exists()):
                                    errors.append({'file': rel, 'kind': 'missing_local_import', 'message': f"Local import target not found: {alias.name}"})

            elif p.suffix.lower() in {'.html', '.htm'}:
                text = p.read_text(encoding='utf-8', errors='replace')
                refs = re.findall(r"(?:src|href)=[\"']([^\"'#?]+)", text, flags=re.I)
                for ref in refs:
                    if re.match(r'^[a-z]+://', ref, flags=re.I) or ref.startswith(('data:', '/')):
                        continue
                    target = (p.parent/ref).resolve()
                    if project_root not in target.parents and target != project_root:
                        continue
                    if not target.exists():
                        warnings.append({'file': rel, 'kind': 'missing_web_reference', 'message': f"Referenced local file not found: {ref}"})

        return {
            'ok': not errors,
            'errors': errors[:100],
            'warnings': warnings[:100],
            'checked_files': len(checked),
            'note': 'Static verification only; generated code is never executed automatically.'
        }

    def _write_manifest(self, project_root, files, verification):
        manifest = {
            'project': project_root.name,
            'updated_at': datetime.now(timezone.utc).isoformat(),
            'files': files,
            'verification': verification,
            'managed_by': 'Apollo Workshop / file_builder'
        }
        (project_root/'.apollo_project.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')

    def self_test(self):
        assert self.workspace.exists()
        test = self._safe('example/test.py')
        assert self.workspace in test.parents
        return 'Workspace path safety and multi-file static-verification helpers passed.'

    def run(self, action, arguments):
        arguments = arguments or {}

        if action == 'active_project':
            active = self._load_active_project()
            return {
                'active': bool(active),
                'project': active.get('project', ''),
                'path': active.get('path', ''),
                'context': active,
            }

        if action == 'list_projects':
            projects = self._list_projects()
            active = self._load_active_project()
            return {
                'projects': projects,
                'count': len(projects),
                'active_project': active.get('project', ''),
            }

        if action == 'set_active_project':
            project = str(arguments.get('project', '')).strip()
            context = self._save_active_project(
                project,
                reason='explicit_selection',
            )
            return {'set': True, 'context': context}

        if action == 'write_files':
            project = str(arguments.get('project', '')).strip().replace('\\', '/')
            files = arguments.get('files', [])
            overwrite = bool(arguments.get('overwrite', True))
            if not project:
                raise ValueError('project is required.')
            if not isinstance(files, list) or not files:
                raise ValueError('files must be a non-empty list.')
            if len(files) > 60:
                raise ValueError('A project may contain at most 60 files per batch.')

            project_root = self._safe(project)
            project_root.mkdir(parents=True, exist_ok=True)
            created, total_bytes = [], 0
            seen = set()

            for item in files:
                if not isinstance(item, dict):
                    raise ValueError('Every files item must be an object.')
                relative = str(item.get('path', '')).strip().replace('\\', '/')
                content = str(item.get('content', ''))
                if not relative:
                    raise ValueError('Every file needs a path.')
                if relative in seen:
                    raise ValueError(f'Duplicate file path in one batch: {relative}')
                seen.add(relative)
                target = (project_root/relative).resolve()
                if target != project_root and project_root not in target.parents:
                    raise PermissionError(f'File path escapes project folder: {relative}')
                encoded = content.encode('utf-8')
                if len(encoded) > 2_000_000:
                    raise ValueError(f'File exceeds 2 MB limit: {relative}')
                total_bytes += len(encoded)
                if total_bytes > 12_000_000:
                    raise ValueError('Batch exceeds the 12 MB project-write limit.')
                if target.exists() and not overwrite:
                    raise FileExistsError(str(target))
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(content, encoding='utf-8')
                created.append(str(target.relative_to(self.workspace)).replace('\\', '/'))

            verification = self._verify_project(project_root)
            self._write_manifest(project_root, [str(Path(x).relative_to(project)) if x.startswith(project + '/') else x for x in created], verification)
            active_context = self._save_active_project(
                str(project_root.relative_to(self.workspace)).replace('\\', '/'),
                reason='write_files',
            )
            return {
                'created': True,
                'project': str(project_root.relative_to(self.workspace)).replace('\\', '/'),
                'files': created,
                'file_count': len(created),
                'bytes': total_bytes,
                'verification': verification,
                'active_project': active_context,
                'instruction': (
                    'All supplied files are real. If verification.ok is false, repair only the reported files. '
                    'Do not claim the project is working until static verification passes.'
                ),
            }

        if action == 'write_file':
            target = self._safe(arguments.get('path'))
            content = str(arguments.get('content', ''))
            overwrite = bool(arguments.get('overwrite', True))
            if target == self.workspace:
                raise ValueError('A file path is required.')
            if target.exists() and not overwrite:
                raise FileExistsError(str(target))
            encoded = content.encode('utf-8')
            if len(encoded) > 2_000_000:
                raise ValueError('Single file exceeds 2 MB limit.')
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding='utf-8')
            return {'created': True, 'path': str(target), 'relative_path': str(target.relative_to(self.workspace)).replace('\\', '/'), 'bytes': len(encoded)}

        if action == 'verify_project':
            project_root = self._safe(arguments.get('project'))
            if not project_root.is_dir():
                raise FileNotFoundError(str(project_root))
            return self._verify_project(project_root)

        if action == 'inspect_project':
            project_root = self._safe(arguments.get('project'))
            if not project_root.is_dir():
                raise FileNotFoundError(str(project_root))
            project_name = str(
                project_root.relative_to(self.workspace)
            ).replace('\\', '/')
            self._save_active_project(
                project_name,
                reason='inspect_project',
            )
            files = [str(p.relative_to(project_root)).replace('\\', '/') for p in sorted(project_root.rglob('*')) if p.is_file()][:1000]
            manifest = None
            mp = project_root/'.apollo_project.json'
            if mp.exists():
                try: manifest = json.loads(mp.read_text(encoding='utf-8'))
                except Exception: manifest = None
            return {'project': str(project_root.relative_to(self.workspace)).replace('\\', '/'), 'files': files, 'manifest': manifest}

        if action == 'create_folder':
            target = self._safe(arguments.get('path'))
            target.mkdir(parents=True, exist_ok=True)
            return {'created': True, 'path': str(target)}

        if action == 'list_files':
            root = self._safe(arguments.get('path', ''))
            if not root.exists(): return []
            if root.is_file(): return [str(root.relative_to(self.workspace)).replace('\\', '/')]
            files = []
            for p in sorted(root.rglob('*')):
                if p.is_file(): files.append(str(p.relative_to(self.workspace)).replace('\\', '/'))
                if len(files) >= 1000: break
            return files

        if action == 'read_file':
            target = self._safe(arguments.get('path'))
            if not target.is_file(): raise FileNotFoundError(str(target))
            text = target.read_text(encoding='utf-8', errors='replace')
            return {'path': str(target.relative_to(self.workspace)).replace('\\', '/'), 'content': text[:160000], 'truncated': len(text) > 160000}

        raise KeyError(action)
