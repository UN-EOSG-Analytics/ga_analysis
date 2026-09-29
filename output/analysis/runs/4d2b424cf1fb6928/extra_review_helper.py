import json
from pathlib import Path
import root_review_helper as helper

helper.JOBS = json.loads((Path(__file__).parent / 'review_assignment_root_extra.json').read_text())
read = helper.read
write = helper.write
