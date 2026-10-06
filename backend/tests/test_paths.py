"""路径锚定（M3）：配置与落盘目录不随启动目录漂移，输出目录只有一个事实源。"""

from pathlib import Path

import app.generate as generate_module
from app.api.v1 import files as files_module
from app.config import BASE_DIR, settings
from app.core import provider_config


def test_base_dir_is_backend_root():
    assert (BASE_DIR / "app" / "main.py").is_file()


def test_configured_paths_are_absolute():
    """库、上传目录、向量库、生成物目录都锚定 backend/，不受 CWD 影响。"""
    for value in (settings.upload_dir, settings.vectors_db_path, settings.output_dir):
        assert Path(value).is_absolute()


def test_output_dir_single_source():
    """generate 从 settings 派生；files 下载接口走 generate.output_dir()，不再各自硬编码。"""
    assert Path(settings.output_dir) == Path(generate_module.OUTPUT_DIR)
    assert files_module.output_dir() == generate_module.output_dir()


def test_providers_default_path_is_anchored():
    assert Path(provider_config.DEFAULT_CONFIG_PATH).is_absolute()
    assert Path(provider_config.DEFAULT_CONFIG_PATH).parent == BASE_DIR
