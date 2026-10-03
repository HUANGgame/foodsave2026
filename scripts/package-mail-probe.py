"""Build isolated reviewed CLI package; does not deploy, import API or send mail."""
import importlib.util
from pathlib import Path
root=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('package_f1',root/'scripts/package-f1.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
module.OUT.mkdir(exist_ok=True)
paths=[module.BACKEND/'foodsave'/f'{name}.py' for name in module.RUNTIME]
paths+=[module.BACKEND/'requirements.txt',module.BACKEND/'qa/mail_delivery_probe.py']
print(module.package('foodsave-mail-delivery-probe.zip',paths))
