#!/usr/bin/env python3
"""
测试新架构的脚本

从id_list.txt中随机选择几个ID进行测试
"""

import asyncio
import random
import sys
from pathlib import Path

# 添加当前目录到Python路径
sys.path.insert(0, str(Path(__file__).parent))

from fetch_nizima import NizimaFetcher


async def test_single_download(item_id: str) -> bool:
    """测试单个下载"""
    print(f"\n{'='*60}")
    print(f"🧪 测试下载作品: {item_id}")
    print(f"{'='*60}")
    
    try:
        fetcher = NizimaFetcher(item_id, "models/nizima_test")
        success = await fetcher.fetch()
        
        if success:
            print(f"✅ 测试成功: {item_id}")
            return True
        else:
            print(f"❌ 测试失败: {item_id}")
            return False
            
    except Exception as e:
        print(f"❌ 测试异常: {item_id} - {e}")
        return False


async def main():
    """主测试函数"""
    print("🚀 开始测试新的Nizima下载器架构")
    print("=" * 80)
    
    # 读取ID列表
    id_list_file = Path(__file__).parent / "id_list.txt"
    if not id_list_file.exists():
        print("❌ 找不到id_list.txt文件")
        return
        
    with open(id_list_file, "r") as f:
        all_ids = [line.strip() for line in f if line.strip()]
        
    # 随机选择3个ID进行测试
    test_ids = random.sample(all_ids, min(3, len(all_ids)))
    print(f"📋 随机选择的测试ID: {test_ids}")
    
    # 逐个测试
    results = []
    for item_id in test_ids:
        success = await test_single_download(item_id)
        results.append((item_id, success))
        
        # 在测试之间稍作停顿
        await asyncio.sleep(2)
    
    # 输出测试结果
    print(f"\n{'='*80}")
    print("📊 测试结果汇总")
    print(f"{'='*80}")
    
    successful = 0
    for item_id, success in results:
        status = "✅ 成功" if success else "❌ 失败"
        print(f"  {item_id}: {status}")
        if success:
            successful += 1
            
    print(f"\n🎯 总体结果: {successful}/{len(results)} 成功")
    
    if successful == len(results):
        print("🎉 所有测试都通过了！新架构工作正常。")
    else:
        print("⚠️ 部分测试失败，需要进一步调试。")


if __name__ == "__main__":
    asyncio.run(main())
