"""
解密任务实现

负责解密下载的加密文件
"""

from pathlib import Path
from typing import Any

from .base import Task


class DecryptTask(Task):
    """解密任务
    
    使用XOR算法解密下载的文件
    """
    
    XOR_KEY = "AkqeZ-f,7fgx*7WU$6mWZ_98x-nWtdw4Jjky"
    
    def __init__(
        self,
        task_id: str,
        input_file: Path,
        output_file: Path,
        deps_on: list = None
    ):
        """初始化解密任务
        
        Args:
            task_id: 任务ID
            input_file: 输入文件路径
            output_file: 输出文件路径
            deps_on: 依赖的任务ID列表
        """
        super().__init__(task_id, deps_on)
        self.input_file = Path(input_file)
        self.output_file = Path(output_file)
        
    def is_completed(self) -> bool:
        """检查解密文件是否已存在"""
        return (
            self.output_file.exists() 
            and self.output_file.stat().st_size > 0
            and self._is_zip_file(self.output_file)
        )
        
    async def execute(self) -> Path:
        """执行解密"""
        print(f"🔓 解密文件: {self.input_file.name}")
        
        # 检查输入文件是否已经是ZIP格式
        if self._is_zip_file(self.input_file):
            print("✅ 文件已是ZIP格式，无需解密")
            # 直接复制文件
            import shutil
            self.output_file.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(self.input_file, self.output_file)
            self.mark_completed(self.output_file)
            return self.output_file
            
        # 确保输出目录存在
        self.output_file.parent.mkdir(parents=True, exist_ok=True)
        
        try:
            # 读取加密文件
            with open(self.input_file, "rb") as f:
                encrypted_data = f.read()
                
            # XOR解密
            key_bytes = [ord(c) for c in self.XOR_KEY]
            decrypted = bytearray()
            
            for i, byte in enumerate(encrypted_data):
                decrypted.append(byte ^ key_bytes[i % len(key_bytes)])
                
            # 保存解密后的文件
            with open(self.output_file, "wb") as f:
                f.write(decrypted)
                
            # 验证是否为有效的ZIP文件
            if self._is_zip_file(self.output_file):
                print("✅ 解密成功，确认为ZIP文件")
                self.mark_completed(self.output_file)
                return self.output_file
            else:
                error_msg = "解密后不是有效的ZIP文件"
                print(f"❌ {error_msg}")
                self.mark_failed(error_msg)
                raise Exception(error_msg)
                
        except Exception as e:
            error_msg = f"解密失败: {e}"
            print(f"❌ {error_msg}")
            self.mark_failed(error_msg)
            raise Exception(error_msg)
            
    def _is_zip_file(self, file_path: Path) -> bool:
        """检测文件是否为ZIP格式"""
        try:
            with open(file_path, "rb") as f:
                header = f.read(4)
                # ZIP文件的魔数
                return header in [b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08"]
        except Exception:
            return False
