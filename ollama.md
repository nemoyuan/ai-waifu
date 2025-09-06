

# minicpm
https://github.com/OpenBMB
https://github.com/OpenBMB/MiniCPM-V


# # minicpm-v4.5 (图像、视频和文本)

```bash
# https://ollama.com/openbmb/minicpm-v4.5/tags
ollama pull openbmb/minicpm-v4.5:8b
```

## MiniCPM-o 2.6 (额外接受音频作为输入，并以端到端的方式提供高质量的语音输出)

```bash
# https://ollama.com/openbmb/minicpm-o2.6/tags
ollama pull openbmb/minicpm-o2.6
```


# 使用镜像源
修改dns尝试
```bash
set_dns   
show_dns 
sudo dscacheutil -flushcache # 清理dns缓存
```

或使用镜像
```bash
ollama run hf-mirror.com/xxxx/xxxx
```


```bash
ollama run hf-mirror.com/openbmb/MiniCPM-V-4_5-gguf:Q4_K_M
ollama run hf-mirror.com/openbmb/MiniCPM-V-4_5-gguf:F16
```