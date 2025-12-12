import sys
sys.path.append("../")
from core.preqtester import PreqTester
import json

preqtester = PreqTester("../core/vault/courses.json")
open("prerequisites.json", "w").write(json.dumps(preqtester.cache, indent=4))
