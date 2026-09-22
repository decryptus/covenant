"""Check release metadata and installed contents without contacting PyPI."""
import email
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import venv
import zipfile

version = Path('VERSION').read_text().strip()
assert version == Path('RELEASE').read_text().strip()
for name in sys.argv[1:]:
    directory = Path('dist') / name if name in ('auton', 'autond') else Path('dist')
    wheels = list(directory.glob('*.whl'))
    sources = list(directory.glob('*.tar.gz'))
    assert len(wheels) == len(sources) == 1, (name, wheels, sources)
    with zipfile.ZipFile(wheels[0]) as archive:
        files = archive.namelist()
        metadata = email.message_from_bytes(archive.read(next(f for f in files if f.endswith('.dist-info/METADATA'))))
        assert metadata['Name'] == name
        assert metadata['Version'] == version
        assert metadata.get_all('Requires-Dist'), name
        scripts = [f.rsplit('/', 1)[-1] for f in files if '.data/scripts/' in f]
        assert scripts == [name], scripts
        if name == 'auton':
            assert not any(f.startswith('auton/') for f in files), 'Client contains daemon modules'
        else:
            module = 'auton' if name == 'autond' else name
            assert module + '/__init__.py' in files
            assert module + '/modules/' in '\n'.join(files)
    with tarfile.open(sources[0]) as archive:
        members = archive.getnames()
        prefix = members[0].split('/')[0] + '/'
        for required in ('setup.yml', 'pyproject.toml', 'VERSION', 'RELEASE'):
            assert prefix + required in members, required
        metadata = email.message_from_bytes(archive.extractfile(prefix + 'PKG-INFO').read())
        assert metadata['Name'] == name and metadata['Version'] == version
    with tempfile.TemporaryDirectory() as temp:
        venv.create(temp, with_pip=True)
        python = str(Path(temp) / 'bin/python')
        subprocess.run([python, '-m', 'pip', 'install', '--no-deps', str(wheels[0].resolve())], check=True)
        subprocess.run([python, '-c', 'from importlib.metadata import version; import sys; assert version(sys.argv[1]) == sys.argv[2]', name, version], cwd=temp, check=True)
        script = Path(temp) / 'bin' / name
        assert script.is_file()
        compile(script.read_bytes(), str(script), 'exec')
    print('Validated', name, version)
