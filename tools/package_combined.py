"""Package reviewed source/evidence only, excluding local keys and databases."""
from pathlib import Path
from zipfile import ZipFile,ZIP_DEFLATED
from flightcore.myrealtrip import api_key

root=Path.cwd();target=root.parent/'flexible-flights-combined-top20-stage.zip'
if target.exists():raise RuntimeError('Preserving previous package')
with ZipFile(root.parent/'flexible-flights-price-only-stage.zip') as old:
    paths={root/Path(name).relative_to('flexible-flights') for name in old.namelist() if not name.endswith('/')}
for directory in ('flightcore','tests','tools'):
    paths.update(p for p in (root/directory).rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix not in ('.pyc','.db'))
paths.update(root.glob('*.md'))
for name in ('combined-live-20261010.json','combined-google-diagnostic-20261010.json',
             'combined-google-diagnostic-20261010.png','combined-live-fixed-20261010.json',
             'combined-google-fixed-check-20261010.json','combined-google-fixed-check-20261010.png',
             'COMBINED_RESULTS_20261010.json','combined-ui-release-20261010.json',
             'combined-ui-release-20261010-375.png','combined-ui-release-20261010-1280.png'):
    paths.add(root/name)
secret=api_key().encode()
with ZipFile(target,'x',ZIP_DEFLATED) as archive:
    for path in sorted(paths):
        if not path.is_file():continue
        assert path.name!='.env' and path.suffix!='.db'
        data=path.read_bytes();assert secret not in data
        archive.writestr(str(Path('flexible-flights')/path.relative_to(root)),data)
with ZipFile(target) as archive:
    assert archive.testzip() is None
    for name in archive.namelist():
        assert Path(name).name!='.env' and not name.endswith('.db')
        assert secret not in archive.read(name)
    count=len(archive.namelist())
print({'files':count,'bytes':target.stat().st_size,'integrity':'passed','secret_scan':'passed'})
