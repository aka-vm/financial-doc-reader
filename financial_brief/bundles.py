"""Bounded folder/ZIP intake for financial briefs and structured ABS deals."""
import shutil
import stat
import zipfile
from pathlib import Path, PurePosixPath

from werkzeug.utils import secure_filename

DOCUMENTS = {'.pdf', '.txt', '.htm', '.html', '.csv', '.xml'}
MAX_FILES = 100
MAX_BYTES = 300 << 20


def relative_name(name):
    path = PurePosixPath(name.replace('\\', '/'))
    if path.is_absolute() or '..' in path.parts or any(':' in part for part in path.parts):
        raise ValueError('Invalid path in document bundle.')
    if not path.parts or any(part.startswith('.') or part == '__MACOSX' for part in path.parts):
        return None
    if path.suffix.lower() not in DOCUMENTS | {'.zip', '.json'}:
        return None
    parts = [secure_filename(part) for part in path.parts]
    if not all(parts):
        raise ValueError('Invalid filename in document bundle.')
    return Path(*parts)


def prepare(paths, folder):
    """Expand one ZIP level; preserve directories and never overwrite a document."""
    root = Path(folder)
    expanded, warnings, seen = [], [], set()
    total = 0
    def add(path, size):
        nonlocal total
        total += size
        if total > MAX_BYTES or len(expanded) >= MAX_FILES:
            raise ValueError('Bundle exceeds 100 documents or 300 MB expanded.')
        if path in seen:
            raise ValueError('Duplicate document path in bundle.')
        seen.add(path)
        expanded.append(path)
    for path in map(Path, paths):
        if path.suffix.lower() != '.zip':
            add(path, path.stat().st_size)
            continue
        try:
            with zipfile.ZipFile(path) as archive:
                for info in archive.infolist():
                    if info.is_dir():
                        continue
                    name = relative_name(info.filename)
                    if name is None or name.suffix.lower() == '.json':
                        continue
                    if name.suffix.lower() == '.zip':
                        raise ValueError('Nested ZIP files are not supported. Upload the documents directly.')
                    if stat.S_ISLNK(info.external_attr >> 16):
                        raise ValueError('Symbolic links are not supported in ZIP files.')
                    target = root / name
                    if target.exists():
                        raise ValueError('Duplicate document path in ZIP bundle.')
                    add(target, info.file_size)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with archive.open(info) as source, target.open('wb') as dest:
                        shutil.copyfileobj(source, dest, length=1 << 20)
        except zipfile.BadZipFile:
            raise ValueError('The ZIP archive could not be read.') from None
    # Prefer original HTML over a text export of the same report.
    originals = {p.with_suffix('') for p in expanded if p.suffix.lower() in {'.htm', '.html'}}
    documents = []
    for path in expanded:
        if path.suffix.lower() == '.json':
            warnings.append(f'Skipped metadata: {path.name}')
        elif path.suffix.lower() == '.txt' and path.with_suffix('') in originals:
            warnings.append(f'Skipped duplicate text export: {path.name}')
        else:
            documents.append(path)
    if not documents:
        raise ValueError('No supported documents found in this bundle.')
    return documents, warnings


def build_deal(paths, folder, backend, model, url, progress, extract_model=None, month_model=None):
    from reader.intake import collect
    from reader.deal import build, to_markdown
    progress(0, 1, 'Identifying reports, contracts and loan tapes')
    docs = collect([str(p) for p in paths], [], str(folder), log=lambda message: None)
    for doc in docs:
        doc['name'] = str(Path(doc['path']).relative_to(folder))
    result = build(docs, backend, model, url, log=lambda message: None, progress=progress, extract_model=extract_model, month_model=month_model)
    title = next((m['report'].get('trust') for m in result['months'] if m['report'].get('trust')), 'ABS deal report')
    return {'type': 'deal', 'title': title, 'markdown': to_markdown(result), 'deal': result}
