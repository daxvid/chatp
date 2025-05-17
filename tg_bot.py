import os
import logging
import yaml
import aiohttp
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

def load_config():
    """加载配置文件"""
    try:
        with open('conf/auth.yaml', 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
    except Exception as e:
        raise Exception(f"加载配置文件失败: {e}")

# 加载配置
config = load_config()

# 设置日志
logging.basicConfig(
    format=config['logging']['format'],
    level=getattr(logging, config['logging']['level']),
    filename=config['logging']['filename']
)
logger = logging.getLogger(__name__)

async def query_phone(phone: str) -> str:
    """通过HTTP API查询手机号信息"""
    try:
        api_config = config['api']
        url = f"{api_config['base_url']}{api_config['endpoint']}?n={phone}"
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=api_config['timeout']) as response:
                if response.status == 200:
                    return await response.text()
                else:
                    logger.error(f"API请求失败: HTTP {response.status}")
                    raise Exception(f"API请求失败: HTTP {response.status}")
    except aiohttp.ClientError as e:
        logger.error(f"API请求出错: {e}")
        raise
    except Exception as e:
        logger.error(f"查询失败: {e}")
        raise

def is_authorized(chat_id: int, user_id: int) -> bool:
    """检查用户是否在指定群组的白名单中"""
    whitelist = config['telegram']['whitelist']
    # 检查群组是否在白名单中
    if chat_id not in whitelist:
        return False
    # 检查用户是否在该群组的白名单中
    return user_id in whitelist[chat_id]

async def check_authorization(update: Update) -> bool:
    """检查用户权限并发送提示消息"""
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    
    if not is_authorized(chat_id, user_id):
        logger.warning(f"未授权访问 - 群组ID: {chat_id}, 用户ID: {user_id}")
        if chat_id < 0:  # 群组消息
            await update.message.reply_text("抱歉，此群组或您没有权限使用此机器人。")
        else:  # 私聊消息
            await update.message.reply_text("抱歉，您没有权限使用此机器人。")
        return False
    return True

async def handle_phone_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理手机号查询命令"""
    try:
        # 检查用户权限
        if not await check_authorization(update):
            return

        # 获取命令文本
        command_text = update.message.text.strip()
        
        # 检查命令格式
        if not command_text.startswith('/查手机'):
            return
        
        # 提取手机号
        phone = command_text.replace('/查手机', '').strip()
        
        # 验证手机号格式
        if not phone.isdigit() or len(phone) != 11:
            await update.message.reply_text("请输入正确的11位手机号码！")
            return
        
        # 查询API
        response = await query_phone(phone)
        
        # 直接返回API响应
        await update.message.reply_text(response)
        
    except Exception as e:
        logger.error(f"处理查询命令时出错: {e}")
        await update.message.reply_text("查询过程中出现错误，请稍后重试")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理 /start 命令"""
    # 检查用户权限
    if not await check_authorization(update):
        return

    chat_type = "群组" if update.effective_chat.id < 0 else "私聊"
    await update.message.reply_text(
        f"欢迎在{chat_type}中使用查询机器人！\n"
        "使用 /查手机 + 手机号 来查询信息\n"
        "例如：/查手机13344445555"
    )

async def delete_webhook(token: str):
    """删除webhook设置"""
    try:
        async with aiohttp.ClientSession() as session:
            url = f"https://api.telegram.org/bot{token}/deleteWebhook"
            async with session.get(url) as response:
                if response.status == 200:
                    result = await response.json()
                    if result.get('ok'):
                        logger.info("成功删除webhook")
                    else:
                        logger.error(f"删除webhook失败: {result.get('description')}")
                else:
                    logger.error(f"删除webhook请求失败: HTTP {response.status}")
    except Exception as e:
        logger.error(f"删除webhook时出错: {e}")
        raise

async def async_main():
    """异步主函数"""
    try:
        # 创建应用
        application = Application.builder().token(config['telegram']['bot_token']).build()
        
        # 删除webhook
        await delete_webhook(config['telegram']['bot_token'])
        
        # 添加命令处理器
        application.add_handler(CommandHandler("start", start))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_phone_query))
        
        # 启动机器人
        logger.info("开始轮询消息...")
        # 使用run_polling而不是await run_polling
        application.run_polling(allowed_updates=Update.ALL_TYPES)
        
    except Exception as e:
        logger.error(f"机器人运行出错: {e}")

def main():
    """主函数入口"""
    import asyncio
    try:
        # 在Windows上需要使用这个策略
        if os.name == 'nt':
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        
        # 运行异步主函数
        asyncio.run(async_main())
    except KeyboardInterrupt:
        logger.info("程序被用户中断")
    except Exception as e:
        logger.error(f"程序运行出错: {e}")

if __name__ == '__main__':
    main() 
