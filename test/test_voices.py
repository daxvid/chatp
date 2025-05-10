import asyncio
import edge_tts
import logging

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def list_chinese_voices():
    """列出所有可用的中文语音"""
    try:
        # 获取所有语音
        voices = await edge_tts.list_voices()
        
        # 过滤出中文语音
        chinese_voices = [voice for voice in voices if voice["Locale"].startswith("zh-")]
        
        # 按地区排序
        chinese_voices.sort(key=lambda x: x["Locale"])
        
        # 打印语音信息
        logger.info(f"找到 {len(chinese_voices)} 个中文语音:")
        logger.info("-" * 80)
        logger.info(f"{'语音ID':<40} {'地区':<15} {'性别':<10} {'描述'}")
        logger.info("-" * 80)
        
        for voice in chinese_voices:
            voice_id = voice["ShortName"]
            locale = voice["Locale"]
            gender = voice["Gender"]
            description = voice.get("FriendlyName", "")
            
            logger.info(f"{voice_id:<40} {locale:<15} {gender:<10} {description}")
            
    except Exception as e:
        logger.error(f"获取语音列表失败: {e}")

def main():
    """主函数"""
    try:
        # 运行异步函数
        asyncio.run(list_chinese_voices())
    except Exception as e:
        logger.error(f"程序执行失败: {e}")

if __name__ == "__main__":
    main() 