"""
Nizima下载器任务模块

基于任务图（Task Graph）的模块化架构
"""

from .base import Task
from .download import DownloadTask
from .decrypt import DecryptTask
from .extract import ExtractTask
from .process import ProcessImagesTask, RenameDirectoryTask
from .save import SaveVersionTask, SaveDetailJsonTask

__all__ = [
    'Task',
    'DownloadTask',
    'DecryptTask', 
    'ExtractTask',
    'ProcessImagesTask',
    'RenameDirectoryTask',
    'SaveVersionTask',
    'SaveDetailJsonTask',
]
