from pathlib import Path
from uuid import uuid4
import shutil

PROJECT=Path(__file__).resolve().parents[1]


class TemporaryWorkspace:
    """Inherit workspace Windows ACLs instead of Python's private temp ACL."""
    def __init__(self):
        self.path=(PROJECT/('.test-workflow-'+uuid4().hex)).resolve()
        if not self.path.is_relative_to(PROJECT):raise ValueError('Unsafe test workspace')
        self.path.mkdir();self.name=str(self.path)
    def __enter__(self):return self.name
    def __exit__(self,*args):self.cleanup()
    def cleanup(self):
        target=self.path.resolve()
        if target.parent!=PROJECT or not target.name.startswith('.test-workflow-'):raise ValueError('Unsafe test cleanup')
        if target.exists():shutil.rmtree(target)
