"""
工具函数

包含版本检查、信号处理等通用功能
"""

import json
import signal
import sys
from pathlib import Path
from typing import Optional

# 添加当前目录到路径
sys.path.insert(0, str(Path(__file__).parent))
from tasks.base import request_shutdown


# 脚本版本控制
SCRIPT_VERSION = "v4"


def setup_signal_handlers():
    """设置信号处理器"""

    def signal_handler(signum, frame):
        """信号处理器：优雅处理中断"""
        request_shutdown()
        print("\n🛑 收到中断信号，正在安全停止...")
        print("⏳ 等待当前操作完成，请稍候...")

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)


def check_version(item_id: str, output_dir: str) -> bool:
    """检查作品版本是否为最新

    Args:
        item_id: 作品ID
        output_dir: 输出目录

    Returns:
        bool: 是否为最新版本
    """

    def _check_version_file(version_file: Path, dir_name: str = None) -> bool:
        """检查单个版本文件"""
        try:
            with open(version_file, "r", encoding="utf-8") as f:
                version_data = json.load(f)
            current_version = version_data.get("version")

            if current_version == SCRIPT_VERSION:
                print(f"✅ 作品 {item_id} 已是最新版本 ({SCRIPT_VERSION})，跳过下载")
                if dir_name:
                    print(f"📁 找到目录: {dir_name}")
                return True
            else:
                print(
                    f"🔄 作品 {item_id} 版本不匹配 (本地: {current_version}, 当前: {SCRIPT_VERSION})，需要更新"
                )
                if dir_name:
                    print(f"📁 找到目录: {dir_name}")
                return False
        except Exception:
            return False

    try:
        output_path = Path(output_dir)

        # 首先查找原始格式的目录 {item_id}/
        version_file = output_path / item_id / "version.json"
        if version_file.exists():
            return _check_version_file(version_file)

        # 如果原始格式不存在，查找重命名格式的目录 {item_id}_*/
        for dir_path in output_path.iterdir():
            if dir_path.is_dir() and dir_path.name.startswith(f"{item_id}_"):
                version_file = dir_path / "version.json"
                if version_file.exists():
                    return _check_version_file(version_file, dir_path.name)

        # 都没找到
        return False

    except Exception as e:
        print(f"⚠️ 检查版本失败: {e}")
        return False


async def get_assets_info(item_id: str) -> tuple:
    """获取资源信息

    Args:
        item_id: 作品ID

    Returns:
        tuple: (AssetsInfo, detail_data)
    """
    import aiohttp
    from models import AssetsInfo

    api_url = f"https://nizima.com/api/items/{item_id}/detail"

    async with aiohttp.ClientSession() as session:
        async with session.get(api_url) as response:
            response.raise_for_status()

            # 检查响应类型
            content_type = response.headers.get("content-type", "")
            if "application/json" not in content_type:
                raise ValueError(
                    f"无效的作品ID '{item_id}': API返回了非JSON响应 (content-type: {content_type})"
                )

            data = await response.json()

            # 检查是否有assetsInfo
            if "assetsInfo" not in data:
                raise ValueError(f"无效的作品ID '{item_id}': 响应中缺少assetsInfo字段")

            print(f"📋 获取到资源信息: {item_id}")

            return AssetsInfo.from_api_response(data), data
