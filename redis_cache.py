import redis
import pickle
import logging

# 配置日志
logger = logging.getLogger("redis_cache")

class RedisCache:
    """使用Redis进行缓存的实现"""
    def __init__(self, host='localhost', port=6379, db=0, password=None, prefix='cache:', expire=3600):
        """
        初始化Redis缓存
        
        Args:
            host: Redis服务器主机
            port: Redis服务器端口
            db: Redis数据库编号
            password: Redis密码（如果有）
            prefix: 键前缀，用于区分不同应用的数据
            expire: 缓存数据的过期时间（秒）
        """
        self.prefix = prefix
        self.expire = expire
        self.memory_cache = {}  # 内存缓存，作为Redis不可用时的后备
        try:
            self.redis = redis.Redis(
                host=host,
                port=port,
                db=db,
                password=password,
                socket_connect_timeout=5,
                socket_timeout=5,
                decode_responses=False  # 不要自动解码为字符串，因为我们存储二进制数据
            )
            # 测试连接
            self.redis.ping()
            logger.info(f"Redis缓存已初始化，连接到 {host}:{port}/db{db}")
        except Exception as e:
            logger.error(f"Redis连接失败: {e}")
            logger.error(f"将使用内存缓存作为后备")
            self.redis = None
            
    def _format_key(self, key):
        """格式化键名，添加前缀"""
        return f"{self.prefix}{key}"
            
    def get(self, key, default=None):
        """获取缓存值"""
        try:
            if self.redis:
                formatted_key = self._format_key(key)
                data = self.redis.get(formatted_key)
                
                if data:
                    try:
                        return pickle.loads(data)
                    except Exception as e:
                        logger.error(f"反序列化数据失败: {e}")
                        return default
            else:
                # 如果Redis不可用，使用内存缓存
                return self.memory_cache.get(key, default)
                
            return default
        except Exception as e:
            logger.error(f"获取Redis缓存出错: {e}")
            # 降级到内存缓存
            return self.memory_cache.get(key, default)
                
    def set(self, key, value):
        """设置缓存值"""
        try:
            # 总是更新内存缓存
            self.memory_cache[key] = value
            
            if not self.redis:
                return False
                
            formatted_key = self._format_key(key)
            data = pickle.dumps(value)
            self.redis.set(formatted_key, data, ex=self.expire)
            return True
        except Exception as e:
            logger.error(f"设置Redis缓存出错: {e}")
            return False
                
    def remove(self, key):
        """移除缓存项"""
        try:
            # 从内存缓存中移除
            if key in self.memory_cache:
                del self.memory_cache[key]
            
            if not self.redis:
                return True
                
            formatted_key = self._format_key(key)
            return bool(self.redis.delete(formatted_key))
        except Exception as e:
            logger.error(f"移除Redis缓存出错: {e}")
            return False
                
    def has_key(self, key):
        """检查是否存在键"""
        try:
            # 先检查内存缓存
            if key in self.memory_cache:
                return True
                
            if not self.redis:
                return False
                
            formatted_key = self._format_key(key)
            return bool(self.redis.exists(formatted_key))
        except Exception as e:
            logger.error(f"检查Redis键存在性出错: {e}")
            return key in self.memory_cache
            
    def clear(self):
        """清除所有缓存数据"""
        try:
            # 清除内存缓存
            self.memory_cache.clear()
            
            if not self.redis:
                return
                
            # 清除所有以prefix开头的键
            cursor = 0
            while True:
                cursor, keys = self.redis.scan(cursor, f"{self.prefix}*", 100)
                if keys:
                    self.redis.delete(*keys)
                if cursor == 0:
                    break
            logger.info("Redis缓存已清除")
        except Exception as e:
            logger.error(f"清除Redis缓存出错: {e}")
            
    def get_status(self):
        """获取Redis服务器状态"""
        try:
            if not self.redis:
                return {
                    "status": "disconnected", 
                    "memory_cache_items": len(self.memory_cache)
                }
                
            info = self.redis.info()
            status = {
                "status": "connected",
                "redis_version": info.get("redis_version"),
                "used_memory": info.get("used_memory_human"),
                "connected_clients": info.get("connected_clients"),
                "uptime": info.get("uptime_in_seconds", 0),
                "memory_cache_items": len(self.memory_cache)
            }
            # 获取匹配前缀的键数量
            cursor = 0
            count = 0
            while True:
                cursor, keys = self.redis.scan(cursor, f"{self.prefix}*", 100)
                count += len(keys)
                if cursor == 0:
                    break
                    
            status["cached_items"] = count
            return status
        except Exception as e:
            logger.error(f"获取Redis状态出错: {e}")
            return {
                "status": "error", 
                "message": str(e), 
                "memory_cache_items": len(self.memory_cache)
            } 