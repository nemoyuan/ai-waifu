"""
数据模型定义

定义了下载器使用的数据结构
"""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass
class AssetsInfo:
    """资源信息"""
    
    item_id: str
    preview_live2d_zip: Optional[Dict[str, str]] = None
    export_zip_info: Optional[Dict[str, Any]] = None  # 包含itemContentId等信息
    thumbnail_image: Optional[Dict[str, str]] = None
    preview_images: List[Dict[str, str]] = None
    
    def __post_init__(self):
        """初始化后处理"""
        if self.preview_images is None:
            self.preview_images = []
    
    @classmethod
    def from_api_response(cls, data: Dict[str, Any]) -> "AssetsInfo":
        """从API响应创建AssetsInfo"""
        assets_info = data.get("assetsInfo", {})
        item_content_details = data.get("itemContentDetails", {})
        
        # 提取export信息
        export_zip_info = None
        export_data_key = "書き出しデータ"
        if export_data_key in item_content_details:
            export_info = item_content_details[export_data_key]
            # 暂时禁用export下载，因为需要登录认证
            # if export_info.get("isDownloadable", False):
            #     export_zip_info = {
            #         "itemContentId": export_info["itemContentId"],
            #         "fileSize": export_info.get("fileSize", "Unknown"),
            #         "isDownloadable": True,
            #     }
        
        return cls(
            item_id=str(data.get("itemId", "")),
            preview_live2d_zip=assets_info.get("previewLive2DZip"),
            export_zip_info=export_zip_info,
            thumbnail_image=assets_info.get("thumbnailImage"),
            preview_images=assets_info.get("previewImages", []),
        )
