# install_local_models.py
import os, sys
from argostranslate import package

MODELS_DIR = os.path.join(os.getcwd(), "models")
if not os.path.isdir(MODELS_DIR):
    print("未找到 models 目录：", MODELS_DIR)
    sys.exit(1)

files = [os.path.join(MODELS_DIR, f) for f in os.listdir(MODELS_DIR) if f.lower().endswith(".argosmodel")]
if not files:
    print("models 目录下没有 .argosmodel 文件")
    sys.exit(1)

for path in files:
    try:
        print("安装：", path)
        package.install_from_path(path)
        print("  ✅ OK")
    except Exception as e:
        print("  ❌ 失败：", e)

print("完成本地安装。")
