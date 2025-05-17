import os
import logging
import pyodbc
import yaml
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

def get_db_connection():
    """创建数据库连接"""
    try:
        db_config = config['database']
        conn_str = (
            f"DRIVER={db_config['driver']};"
            f"SERVER={db_config['server']};"
            f"DATABASE={db_config['database']};"
            f"UID={db_config['uid']};"
            f"PWD={db_config['pwd']};"
            f"Trusted_Connection={db_config['trusted_connection']};"
        )
        return pyodbc.connect(conn_str)
    except Exception as e:
        logger.error(f"数据库连接失败: {e}")
        raise

def query_phone(phone):
    """查询手机号信息"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # MS SQL Server存储过程调用方式
        # 使用 EXEC 或 EXECUTE 关键字
        cursor.execute("EXEC select_phone @phone=?", (phone,))
        
        # 获取所有结果
        results = cursor.fetchall()
        
        # 关闭连接
        cursor.close()
        conn.close()
        
        return results
    except Exception as e:
        logger.error(f"查询失败: {e}")
        raise

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
        
        # 查询数据库
        results = query_phone(phone)
        
        # 处理查询结果
        if not results:
            await update.message.reply_text(f"未找到手机号 {phone} 的相关记录")
            return
        
        # 构建CSV格式的回复消息
        # 添加表头
        response = "电话\t总充值\t总提现\n"
        
        # 添加数据行
        for row in results:
            phone_num, total_recharge, total_withdraw = row
            # 使用制表符分隔每个字段
            response += f"{phone_num}\t{total_recharge}\t{total_withdraw}\n"
        
        # 发送回复
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

def main():
    """主函数"""
    try:
        # 创建应用
        application = Application.builder().token(config['telegram']['bot_token']).build()
        
        # 添加命令处理器
        application.add_handler(CommandHandler("start", start))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_phone_query))
        
        # 启动机器人
        application.run_polling()
        
    except Exception as e:
        logger.error(f"机器人运行出错: {e}")

if __name__ == '__main__':
    main() 