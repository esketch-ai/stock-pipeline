"""표준 라이브러리만 사용하는 이식 준비 / 경로 복구 / 소스 패키징."""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import plistlib
import shutil
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def prepare(root):
    for name in ('data', 'state', 'cache', 'output', 'logs'):
        (root / name).mkdir(exist_ok=True)
    if not (root / '.env').exists():
        shutil.copyfile(root / '.env.example', root / '.env')
        (root / '.env').chmod(0o600)
    public = root / 'remotion/public'
    public.mkdir(parents=True, exist_ok=True)
    for name in ('cache', 'output', 'data'):
        link = public / name
        if link.is_symlink():
            link.unlink()
        elif link.exists():
            raise RuntimeError(f'기존 디렉터리 확인 필요: {link}')
        link.symlink_to(Path('../..') / name, target_is_directory=True)
    generated = root / 'state/launchd'
    generated.mkdir(parents=True, exist_ok=True)
    for kind, script, hour, minute in (
        ('daily', 'run_pipeline.sh', 2, 0),
        ('dashboard', 'start_dashboard.sh', None, None),
        ('pages', 'update_public_dashboard.sh', 18, 30),
    ):
        entry = {'Label': f'com.stockpipeline.{kind}',
                 'ProgramArguments': ['/bin/zsh', str(root / script)],
                 'WorkingDirectory': str(root),
                 'StandardOutPath': str(root / f'logs/{kind}.out.log'),
                 'StandardErrorPath': str(root / f'logs/{kind}.err.log'),
                 'RunAtLoad': kind == 'dashboard'}
        if hour is not None:
            entry['StartCalendarInterval'] = {'Hour': hour, 'Minute': minute}
        else:
            entry['KeepAlive'] = True
        (generated / f'com.stockpipeline.{kind}.plist').write_bytes(plistlib.dumps(entry))
    print(f'환경 템플릿·상대 자산 링크·launchd 설정 생성: {root}')


def rebase(root, old_root, apply=False):
    old = old_root.rstrip('/')
    if not old.startswith('/') or old == '':
        raise ValueError('--old-root에는 이전 프로젝트의 절대 경로를 지정하세요')
    def rewrite(value):
        if isinstance(value, str) and value.startswith(old + '/'):
            return str(root) + value[len(old):]
        if isinstance(value, list): return [rewrite(v) for v in value]
        if isinstance(value, dict): return {k: rewrite(v) for k, v in value.items()}
        return value
    count = 0
    # 인증 토큰이 있는 state/는 처리하지 않는다.
    for path in (root / 'data').rglob('*.json'):
        original = json.loads(path.read_text(encoding='utf-8'))
        updated = rewrite(original)
        if original == updated: continue
        print(('변경: ' if apply else '예정: ') + str(path.relative_to(root)))
        count += 1
        if apply:
            backup = path.with_suffix('.json.pre-migration')
            if backup.exists(): raise FileExistsError(f'이전 백업이 있습니다: {backup}')
            shutil.copy2(path, backup)
            path.write_text(json.dumps(updated, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'{count}개 파일. ' + ('적용 완료' if apply else '--apply 지정 시 백업 후 적용'))


def source_files(root):
    # 허용 목록: 런타임·비밀·영상·개인별 launchd 설정을 패키징하지 않는다.
    for path in sorted(root.iterdir()):
        if path.is_symlink() or not path.is_file(): continue
        # contact.txt 는 연락처가 실린 개인 파일이라 번들에 넣지 않는다.
        # 예제 파일만 포함해 다른 운영자가 같은 방식으로 설정할 수 있게 한다.
        if (path.suffix in {'.py', '.sh', '.md'} and not path.name.startswith('_')) or path.name in {'.env.example', '.gitignore', 'requirements.txt', 'requirements-tested.txt', 'contact.example.txt', 'INSTALL.md'}:
            yield path
    for folder, extensions in {'docs':{'.md'}, 'tools':{'.py'}, 'static':{'.html','.css','.js'}, 'public-dashboard':{'.html','.css','.js'}, 'remotion/src':{'.ts','.tsx','.css'}}.items():
        for path in sorted((root / folder).rglob('*')):
            if path.is_file() and not path.is_symlink() and path.suffix in extensions:
                yield path
    for name in ('package.json','package-lock.json','tsconfig.json','remotion.config.ts'):
        yield root / 'remotion' / name
    yield root / 'public-dashboard/.nojekyll'


def bundle(root):
    output = root / 'dist/stock-pipeline-source.tar.gz'
    output.parent.mkdir(exist_ok=True)
    files = list(source_files(root))
    checksums = {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    with tarfile.open(output, 'w:gz') as archive:
        for path in files:
            info = archive.gettarinfo(str(path), arcname='stock-pipeline/' + str(path.relative_to(root)))
            info.uid = info.gid = 0
            info.uname = info.gname = ''
            with path.open('rb') as stream: archive.addfile(info, stream)
        manifest = json.dumps(checksums, indent=2).encode()
        info = tarfile.TarInfo('stock-pipeline/SOURCE_SHA256.json')
        info.size = len(manifest)
        archive.addfile(info, io.BytesIO(manifest))
    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    output.with_suffix('.gz.sha256').write_text(f'{digest}  {output.name}\n')
    print(f'{len(files)}개 소스 파일 → {output} ({output.stat().st_size:,} bytes)')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['prepare', 'rebase', 'bundle'])
    parser.add_argument('--root', type=Path, default=ROOT)
    parser.add_argument('--old-root')
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    root = args.root.expanduser().resolve()
    if args.action == 'prepare': prepare(root)
    elif args.action == 'bundle': bundle(root)
    elif not args.old_root: parser.error('rebase에는 --old-root가 필요합니다')
    else: rebase(root, args.old_root, args.apply)


if __name__ == '__main__': main()
