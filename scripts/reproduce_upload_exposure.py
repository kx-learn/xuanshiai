"""手动风险复现：验证静态上传根目录的匿名可读边界。

运行：python -m scripts.reproduce_upload_exposure
只写入 tempfile，不启动服务、不连接数据库、不读取本机上传目录。
"""

import os
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


from fastapi.testclient import TestClient


def main() -> None:
    with TemporaryDirectory() as directory:
        # 必须在导入 app.main 前设置，避免模块级 app 使用本机 UPLOAD_DIR。
        os.environ["ENVIRONMENT"] = "testing"
        os.environ["AUTO_INIT_DB"] = "false"
        os.environ["UPLOAD_DIR"] = directory
        from app.main import create_app

        fixtures = {
            "42/follow-up-img-example.webp": b"private-follow-up-image-sentinel",
            "42/follow-up-voice-example.mp3": b"private-follow-up-voice-sentinel",
            "42/photo-example.webp": b"ordinary-public-image-sentinel",
        }
        for relative_path, payload in fixtures.items():
            target = Path(directory) / relative_path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(payload)

        # 不进入 lifespan；AUTO_INIT_DB=false 双保险，禁止初始化数据库。
        client = TestClient(create_app())
        for relative_path, expected in fixtures.items():
            url = f"/storage/uploads/{relative_path}"
            response = client.get(url)  # 无 Cookie、Authorization 或其他身份信息
            print(f"anonymous GET {url}: {response.status_code}, bytes_match={response.content == expected}")
            assert response.status_code == 200 and response.content == expected, (
                f"预期当前版本暴露 {url}；若已封闭，请改用封闭性回归测试"
            )
        traversal = client.get('/storage/uploads/../outside.txt')
        missing = client.get('/storage/uploads/42/does-not-exist.webp')
        print(f'anonymous traversal GET: {traversal.status_code}')
        print(f'anonymous missing GET: {missing.status_code}')
        assert traversal.status_code in {400, 404}
        assert missing.status_code == 404


if __name__ == "__main__":
    main()
