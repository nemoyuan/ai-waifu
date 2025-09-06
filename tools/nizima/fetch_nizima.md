# Nizima Live2D模型下载器技术文档

## 概述

本文档详细说明了Nizima平台Live2D模型的资源获取、处理和存储机制。

## 版本说明

### v3.0 (最新版本)
- **新增**: Export文件下载支持（需要购买权限）
- **新增**: Preview和Export模型分离存储
- **优化**: 目录结构更清晰
- **保持**: 所有v2.0功能

### v2.0 (工程级重构版)
- **重构**: 模块化架构设计
- **新增**: 并发下载和重试机制
- **新增**: 安全文件管理和错误恢复
- **新增**: 批量下载支持

### v1.0 (原始版本)
- **基础**: Preview模型下载和解密
- **基础**: 图片下载功能

## API接口

### 作品详情API
- **URL**: `https://nizima.com/api/items/{item_id}/detail`
- **方法**: GET
- **响应格式**: JSON
- **用途**: 获取作品的所有资源信息



curl https://nizima.com/api/items/121287/detail | jq .
curl https://nizima.com/api/items/133518/detail | jq .


### 响应结构
```json
{
  "assetsInfo": {
    "previewLive2DZip": {
      "fileName": "随机文件名.随机后缀",
      "url": "相对路径或完整URL",
      "fallbackUrl": null
    },
    "thumbnailImage": {
      "fileName": "thumb_时间戳.webp",
      "url": "相对路径",
      "fallbackUrl": "备用路径"
    },
    "previewImages": [
      {
        "fileName": "图片名_时间戳.扩展名",
        "url": "相对路径",
        "fallbackUrl": "备用路径"
      }
    ]
  }
}
```

## 资源类型和处理流程

### 1. Preview文件 (预览Live2D模型)

#### 获取方式
- **数据源**: `assetsInfo.previewLive2DZip`
- **URL构建**: `https://storage.googleapis.com/market_view_useritems/{item_id}/{fileName}`
- **文件名**: 随机生成的文件名 + 随机后缀
- **常见后缀**: `.lee`, `.u4j`, `.qi4`, `.1ft`, `.grh`, `.mhe`, `.zip`

### 2. Export文件 (完整Live2D模型) - v3.0新增

#### 获取方式
- **数据源**: `itemContentDetails.書き出しデータ`
- **API端点**: `https://nizima.com/api/items/{itemContentId}/download`
- **请求方法**: POST (FormData: fileName="export.zip")
- **权限要求**: 需要购买作品才能下载 (开发者调试时可以放松要求)
- **文件名**: 固定为 `export.zip`

#### 下载流程
1. 检查 `itemContentDetails.書き出しデータ.isDownloadable`
2. 获取 `itemContentId`
3. POST请求到下载API
4. 解析响应获取临时下载链接
5. 使用临时链接下载文件

#### 文件特征
- **加密状态**: 大部分文件都经过XOR加密
- **检测方法**: 通过文件头检测是否为ZIP格式
  - ZIP文件头: `PK\x03\x04`, `PK\x05\x06`, `PK\x07\x08`
  - 非ZIP文件头: 需要解密

#### 解密算法
```python
XOR_KEY = "AkqeZ-f,7fgx*7WU$6mWZ_98x-nWtdw4Jjky"

def decrypt_file(file_data: bytes) -> bytes:
    key_bytes = [ord(c) for c in XOR_KEY]
    decrypted = bytearray()
    
    for i, byte in enumerate(file_data):
        decrypted.append(byte ^ key_bytes[i % len(key_bytes)])
    
    return bytes(decrypted)
```

#### ZIP解压
- **密码保护**: `ZIP_PASSWORD = "LrND6UfK(j-NmN7tTb+2S&6J56rEdfHJ3+pA"`
- **解压策略**: 
  1. 先尝试使用密码解压
  2. 失败后尝试无密码解压（兼容未加密的.zip文件）

#### 后处理
1. **解密**: XOR解密得到ZIP文件
2. **解压**: 使用密码解压ZIP文件
3. **重命名**: 根据.moc3文件名重命名目录
4. **组织**: 提取Live2D模型文件到指定目录

#### 存放位置

**v3.0版本目录结构**:
```
models/nizima/{item_id}/
├── preview/                   # 预览模型目录
│   └── {model_name}/
│       ├── {model_name}.moc3
│       ├── {model_name}.model3.json
│       ├── {model_name}.physics3.json
│       ├── {model_name}.cdi3.json
│       ├── textures/
│       │   ├── texture_00.png
│       │   └── texture_01.png
│       └── expressions/
│           └── *.exp3.json
├── export/                    # 完整模型目录（如果可下载）
│   └── {model_name}/
│       ├── {model_name}.moc3
│       ├── {model_name}.model3.json
│       ├── {model_name}.physics3.json
│       ├── {model_name}.cdi3.json
│       ├── textures/
│       │   ├── texture_00.png
│       │   └── texture_01.png
│       ├── expressions/
│       │   └── *.exp3.json
│       └── motions/
│           └── *.motion3.json
├── previewImages/             # 预览图片
├── thumbnailImage/            # 缩略图
└── downloads/                 # 原始文件归档
```

**v2.0版本目录结构**:
```
models/nizima/{item_id}/{model_name}/
├── {model_name}.moc3          # Live2D模型文件
├── {model_name}.model3.json   # 模型配置
├── {model_name}.physics3.json # 物理配置
├── {model_name}.cdi3.json     # 用户数据
├── textures/                  # 纹理目录
│   ├── texture_00.png
│   └── texture_01.png
└── *.exp3.json               # 表情文件
```

### 3. 缩略图 (Thumbnail)

#### 获取方式
- **数据源**: `assetsInfo.thumbnailImage`
- **URL构建**: `https://storage.googleapis.com/market_view_useritems/{item_id}/{fileName}`
- **文件名格式**: `thumb_YYYYMMDDHHMMSS.webp`

#### 文件特征
- **格式**: WebP (主要), PNG (少数)
- **加密状态**: 未加密
- **用途**: 作品缩略图展示

#### 后处理
- **直接存储**: 无需解密或转换
- **重命名**: 保持原文件名

#### 存放位置
```
models/nizima/{item_id}/thumbnailImage/
└── thumb_YYYYMMDDHHMMSS.webp
```

### 4. 预览图 (Preview Images)

#### 获取方式
- **数据源**: `assetsInfo.previewImages[]`
- **URL构建**: `https://storage.googleapis.com/market_view_useritems/{item_id}/images/{fileName}`
- **特殊路径**: 注意预览图需要在URL中添加 `/images/` 目录

#### 文件特征
- **格式**: PNG, JPG, WEBP, GIF
- **加密状态**: 未加密
- **用途**: 作品详情页展示

#### 后处理
- **直接存储**: 无需解密或转换
- **重命名**: 保持原文件名

#### 存放位置
```
models/nizima/{item_id}/previewImages/
├── visual_1_YYYYMMDDHHMMSS.png
├── visual_2_YYYYMMDDHHMMSS.png
├── illustration_YYYYMMDDHHMMSS.jpg
└── animation_YYYYMMDDHHMMSS.gif
```

## 下载和重试机制

### 并发下载
- **作品级并发**: 默认3个作品同时下载
- **文件级并发**: 每个作品内部最多5个文件同时下载
- **信号量控制**: 使用asyncio.Semaphore控制并发数

### 重试策略
- **重试次数**: 默认3次重试（总共4次尝试）
- **退避算法**: 指数退避 - 3秒, 6秒, 12秒
- **重试条件**: 网络错误、连接重置、超时等临时性错误

### 失败处理
- **失败记录**: 写入 `models/nizima/fail_list.txt`
- **记录内容**:
  ```
  失败记录 - YYYY-MM-DD HH:MM:SS
  作品ID: {item_id}
  任务类型: {main_file|preview_image|thumbnail}
  失败URL: {url}
  目标路径: {target_path}
  错误信息: {error_message}
  ============================================================
  ```

## 文件管理和安全机制

### 安全操作
1. **备份机制**: 下载前备份现有目录为 `{item_id}_back`
2. **临时处理**: 在 `.temp/{item_id}/` 目录中进行所有处理
3. **原子操作**: 成功后移动到最终位置，失败时自动恢复备份
4. **错误回滚**: 异常时自动清理临时文件并恢复备份

### 目录结构

**v3.0版本目录结构**:
```
models/nizima/
├── {item_id}/                 # 最终存放目录
│   ├── preview/              # 预览模型目录
│   │   └── {model_name}/
│   ├── export/               # 完整模型目录（如果可下载）
│   │   └── {model_name}/
│   ├── previewImages/        # 预览图目录
│   ├── thumbnailImage/       # 缩略图目录
│   └── downloads/            # 原始文件归档
├── {item_id}_back/           # 备份目录（临时）
├── .temp/                    # 临时处理目录
│   └── {item_id}/
│       ├── downloads/        # 下载临时文件
│       └── extracted/        # 解压临时文件
└── fail_list.txt            # 失败记录日志
```

**v2.0版本目录结构**:
```
models/nizima/
├── {item_id}/                 # 最终存放目录
│   ├── {model_name}/         # Live2D模型目录
│   ├── previewImages/        # 预览图目录
│   ├── thumbnailImage/       # 缩略图目录
│   └── downloads/            # 原始文件归档
├── {item_id}_back/           # 备份目录（临时）
├── .temp/                    # 临时处理目录
│   └── {item_id}/
│       ├── downloads/        # 下载临时文件
│       └── extracted/        # 解压临时文件
└── fail_list.txt            # 失败记录日志
```

## 使用示例

### v3.0版本 (推荐)

#### 单个作品下载
```bash
uv run tools/nizima/fetch_nizima_v3.py 128477
```

#### 批量下载
```bash
uv run tools/nizima/fetch_nizima_v3.py 111381 121287 128477 131068 134070 134352
```

#### 自定义参数
```bash
uv run tools/nizima/fetch_nizima_v3.py 128477 --output custom/path --concurrent 5
```

### v2.0版本

#### 单个作品下载
```bash
uv run tools/nizima/fetch_nizima_v2.py 128477
```

#### 批量下载
```bash
uv run tools/nizima/fetch_nizima_v2.py 111381 121287 128477 131068 134070 134352
```

#### 自定义参数
```bash
uv run tools/nizima/fetch_nizima_v2.py 128477 --output custom/path --concurrent 5
```

## 技术特点

### v3.0版本优势
1. **双模型支持**: 同时支持Preview和Export模型下载
2. **权限检测**: 智能检测Export下载权限
3. **目录分离**: Preview和Export模型分别存储
4. **向下兼容**: 保持所有v2.0功能
5. **API集成**: 集成官方下载API
6. **错误处理**: 优雅处理权限不足情况

### v2.0版本优势
1. **工程级架构**: 模块化设计，职责分离
2. **并发性能**: 双层并发提升下载效率
3. **错误恢复**: 完善的重试和回滚机制
4. **安全可靠**: 原子操作和备份机制
5. **格式兼容**: 支持任意随机文件后缀
6. **智能检测**: 基于文件内容而非扩展名判断类型

### 核心组件

#### v3.0版本
- **AssetsManager**: 资源信息管理（增强版）
- **DownloadManager**: 并发下载管理（支持POST请求）
- **FileProcessor**: 文件处理（解密、解压）
- **SafeFileManager**: 安全文件操作
- **NizimaFetcher**: 主控制器（v3.0）

#### v2.0版本
- **AssetsManager**: 资源信息管理
- **DownloadManager**: 并发下载管理
- **FileProcessor**: 文件处理（解密、解压）
- **SafeFileManager**: 安全文件操作
- **NizimaFetcher**: 主控制器（v2.0）

## 版本对比

| 功能特性 | v1.0 | v2.0 | v3.0 |
|---------|------|------|------|
| Preview模型下载 | ✅ | ✅ | ✅ |
| Export模型下载 | ❌ | ❌ | ✅ |
| 图片下载 | ✅ | ✅ | ✅ |
| 批量下载 | ✅ | ✅ | ✅ |
| 并发下载 | ❌ | ✅ | ✅ |
| 重试机制 | ❌ | ✅ | ✅ |
| 安全文件管理 | ❌ | ✅ | ✅ |
| 模块化架构 | ❌ | ✅ | ✅ |
| 目录分离 | ❌ | ❌ | ✅ |
| 权限检测 | ❌ | ❌ | ✅ |

## 注意事项

### 通用注意事项
1. **网络稳定性**: 建议在稳定网络环境下使用
2. **存储空间**: 确保有足够的磁盘空间
3. **并发限制**: 避免设置过高的并发数导致服务器限制
4. **ID有效性**: 确保提供的作品ID是有效的数字ID
5. **权限问题**: 确保对输出目录有写入权限

### v3.0特殊注意事项
1. **Export权限**: Export文件需要购买作品才能下载
2. **目录结构**: 注意新的preview/export分离目录结构
3. **API限制**: Export下载使用官方API，可能有频率限制
4. **兼容性**: 建议使用v3.0版本获得最佳体验

## 故障排除

### 常见问题

#### 1. Export文件下载失败
**错误**: `isDownloadable: false`
**解决**: 该作品需要购买才能下载Export文件，只能下载Preview版本

#### 2. 网络连接错误
**错误**: `Connection reset by peer`
**解决**: 脚本会自动重试，如果持续失败请检查网络连接

#### 3. 解密失败
**错误**: `解密后不是有效的ZIP文件`
**解决**: 文件可能已经是ZIP格式，或者加密方式发生变化

#### 4. 权限错误
**错误**: `Permission denied`
**解决**: 确保对输出目录有写入权限

#### 5. ID无效
**错误**: `无效的作品ID`
**解决**: 检查作品ID是否正确，确保作品存在且公开

## 开发指南

### 添加新功能
1. 在对应的类中添加方法
2. 更新数据结构（如需要）
3. 添加错误处理
4. 编写测试用例
5. 更新文档

### 调试技巧
1. 使用`--concurrent 1`减少并发便于调试
2. 检查`models/nizima/fail_list.txt`查看失败记录
3. 查看临时目录`models/nizima/.temp`了解处理过程
4. 使用详细的日志输出定位问题

### 贡献代码
1. Fork项目
2. 创建功能分支
3. 编写代码和测试
4. 提交Pull Request
5. 等待代码审查

## 更新日志

### v3.0.0 (2025-01-15)
- 🎉 新增Export文件下载支持
- 🎉 新增Preview/Export目录分离
- 🎉 新增权限检测机制
- 🔧 优化API集成
- 🔧 改进错误处理

### v2.0.0 (2025-01-10)
- 🎉 完全重构为模块化架构
- 🎉 新增并发下载支持
- 🎉 新增重试机制
- 🎉 新增安全文件管理
- 🎉 新增批量下载
- 🔧 优化性能和稳定性

### v1.0.0 (2025-01-05)
- 🎉 初始版本
- ✅ 基础Preview模型下载
- ✅ 图片下载功能
- ✅ XOR解密支持

## 总结

Nizima Live2D模型下载器经过三个版本的迭代，已经发展成为一个功能完整、架构优良的工具：

### 🎯 **核心价值**
- **完整性**: 支持所有可下载的资源类型
- **安全性**: 合法合规，尊重版权和付费机制
- **可靠性**: 完善的错误处理和恢复机制
- **高效性**: 并发下载和智能重试
- **易用性**: 简单的命令行界面

### 🚀 **技术亮点**
1. **逆向工程**: 成功解析Nizima平台的加密和API机制
2. **模块化设计**: 清晰的职责分离和可扩展架构
3. **并发优化**: 双层并发控制提升下载效率
4. **安全机制**: 原子操作和备份恢复保证数据安全
5. **智能处理**: 基于文件内容的格式检测和处理

### 📈 **发展历程**
- **v1.0**: 概念验证，基础功能实现
- **v2.0**: 工程化重构，生产级质量
- **v3.0**: 功能完善，支持完整生态

### 🎉 **成果展示**
通过深入分析Nizima平台的技术实现，我们成功创建了一个：
- 支持多种加密格式的解密器
- 高效的并发下载管理器
- 完整的Live2D模型处理流程
- 用户友好的命令行工具

这个项目展示了逆向工程、Web API分析、并发编程、文件处理等多个技术领域的综合应用，是一个优秀的技术实践案例。

---

**注意**: 本工具仅用于下载用户有权访问的内容，请遵守相关法律法规和平台服务条款。
