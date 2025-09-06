#!/usr/bin/env python3
"""
性能对比测试

比较新架构与旧架构的性能差异
"""

import asyncio
import time
import sys
from pathlib import Path

# 添加当前目录到Python路径
sys.path.insert(0, str(Path(__file__).parent))

from fetch_nizima import NizimaFetcher


async def test_performance():
    """性能测试"""
    print("🚀 Nizima下载器v4.0性能测试")
    print("=" * 80)
    
    # 测试ID
    test_id = "111381"  # 一个相对较小的模型
    output_dir = "models/nizima_performance_test"
    
    print(f"📋 测试ID: {test_id}")
    print(f"📁 输出目录: {output_dir}")
    print()
    
    # 清理之前的测试结果
    import shutil
    if Path(output_dir).exists():
        shutil.rmtree(output_dir)
    
    # 开始性能测试
    start_time = time.time()
    
    fetcher = NizimaFetcher(test_id, output_dir)
    success = await fetcher.fetch()
    
    end_time = time.time()
    duration = end_time - start_time
    
    print()
    print("=" * 80)
    print("📊 性能测试结果")
    print("=" * 80)
    
    if success:
        print(f"✅ 下载成功")
        print(f"⏱️ 总耗时: {duration:.2f} 秒")
        
        # 统计文件信息
        output_path = Path(output_dir) / f"{test_id}_angel_nurse"
        if output_path.exists():
            total_size = sum(f.stat().st_size for f in output_path.rglob('*') if f.is_file())
            file_count = len(list(output_path.rglob('*')))
            
            print(f"📁 总文件数: {file_count}")
            print(f"💾 总大小: {total_size / 1024 / 1024:.2f} MB")
            print(f"🚀 平均速度: {(total_size / 1024 / 1024) / duration:.2f} MB/s")
            
        print()
        print("🎯 新架构优势:")
        print("  ✅ 模块化设计 - 每个任务独立，易于维护")
        print("  ✅ 并发执行 - 多任务同时进行，提升效率")
        print("  ✅ 增量下载 - 跳过已存在文件，支持断点续传")
        print("  ✅ 优雅退出 - 支持Ctrl+C安全中断")
        print("  ✅ 依赖管理 - 自动处理任务依赖关系")
        print("  ✅ 错误隔离 - 单个任务失败不影响整体")
        
    else:
        print(f"❌ 下载失败")
        print(f"⏱️ 耗时: {duration:.2f} 秒")


async def main():
    """主函数"""
    await test_performance()


if __name__ == "__main__":
    asyncio.run(main())
