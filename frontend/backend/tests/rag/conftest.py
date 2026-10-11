"""Files built in memory for the knowledge-base tests."""
import io
import zipfile
from pathlib import Path

import pytest

SAMPLES = Path(__file__).resolve().parents[2] / 'sample-uploads'


def make_pdf(pages: list[list[str]]) -> bytes:
    """A PDF with one page per list, one line of Helvetica per string."""
    escape = lambda s: s.replace('\\', r'\\').replace('(', r'\(').replace(')', r'\)')
    objects = [
        b'<< /Type /Catalog /Pages 2 0 R >>',
        b'',  # the page tree, written once the pages are known
        b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>',
    ]
    kids = []
    for lines in pages:
        stream = ('BT /F1 12 Tf 14 TL 72 720 Td ' + ' T* '.join(f'({escape(line)}) Tj' for line in lines) + ' ET').encode('latin-1')
        objects.append(b'<< /Length %d >>\nstream\n%s\nendstream' % (len(stream), stream))
        objects.append(b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 3 0 R >> >> /Contents %d 0 R >>' % len(objects))
        kids.append(len(objects))
    objects[1] = b'<< /Type /Pages /Kids [%s] /Count %d >>' % (' '.join(f'{k} 0 R' for k in kids).encode(), len(kids))
    out, offsets = io.BytesIO(b''), []
    out.write(b'%PDF-1.4\n')
    for number, body in enumerate(objects, 1):
        offsets.append(out.tell())
        out.write(b'%d 0 obj\n%s\nendobj\n' % (number, body))
    xref = out.tell()
    out.write(b'xref\n0 %d\n0000000000 65535 f \n' % (len(objects) + 1) + b''.join(b'%010d 00000 n \n' % o for o in offsets))
    out.write(b'trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n' % (len(objects) + 1, xref))
    return out.getvalue()


def make_docx(body_xml: str) -> bytes:
    """A .docx with this XML as the body of word/document.xml."""
    out = io.BytesIO()
    with zipfile.ZipFile(out, 'w') as z:
        z.writestr('word/document.xml', f'<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>{body_xml}</w:body></w:document>')
    return out.getvalue()


@pytest.fixture
def pdf():
    return make_pdf


@pytest.fixture
def docx():
    return make_docx


@pytest.fixture
def sample():
    """Bytes of a file in sample-uploads/."""
    return lambda name: (SAMPLES / name).read_bytes()
