import os
import yaml
import random
import logging
import re

logger = logging.getLogger("response")

class ResponseManager:
    """
    响应管理器，用于根据对话内容提供匹配的回复
    """
    def __init__(self, yaml_file="response.yaml"):
        self.response_data = {}
        self.yaml_file = yaml_file
        self.load_responses()
        
    def load_responses(self):
        """
        从YAML文件加载响应配置
        """
        try:
            if not os.path.exists(self.yaml_file):
                logger.error(f"响应配置文件不存在: {self.yaml_file}")
                return False
                
            with open(self.yaml_file, 'r', encoding='utf-8') as f:
                self.response_data = yaml.safe_load(f)
                
            # 验证配置格式
            valid = self._validate_response_data()
            if valid:
                rule_count = len(self.response_data.get('rules', []))
                logger.info(f"已加载回复配置: {rule_count}条规则")
                return True
            else:
                logger.error("响应配置格式无效")
                return False
                
        except Exception as e:
            logger.error(f"加载响应配置失败: {e}")
            import traceback
            logger.error(f"详细错误: {traceback.format_exc()}")
            return False
            
    def _validate_response_data(self):
        """
        验证加载的响应配置是否有效
        """
        if not isinstance(self.response_data, dict):
            return False
            
        if 'rules' not in self.response_data:
            return False
            
        if not isinstance(self.response_data['rules'], list):
            return False
            
        # 验证每条规则是否都有tags和responses字段
        for rule in self.response_data['rules']:
            if not isinstance(rule, dict):
                return False
                
            if 'tags' not in rule or 'responses' not in rule:
                return False
                
            if not isinstance(rule['tags'], list) or not isinstance(rule['responses'], list):
                return False
                
            if not rule['tags'] or not rule['responses']:
                return False
                
        return True

    def get_all_possible_responses(self):
        """获取所有可能的回复内容"""
        try:
            all_responses = []
            
            # 从ResponseManager获取所有回复规则
            rules = self.response_data.get('rules', [])
            for rule in rules:
                responses = rule.get('responses', [])
                if isinstance(responses, list):
                    all_responses.extend([resp for resp in responses if isinstance(resp, str) and resp.strip()])
            
            # 去重
            all_responses = list(set(all_responses))
            return all_responses
            
        except Exception as e:
            logger.error(f"获取所有可能回复时出错: {e}")
            logger.error(f"详细错误: {traceback.format_exc()}")
            return []
        
    def get_response(self, text):
        """
        根据输入文本提供匹配的回复
        
        参数:
            text (str): 输入的对话文本
            
        返回:
            str: 匹配的回复文本，如果没有匹配则返回None
        """
        if not text or not self.response_data or 'rules' not in self.response_data:
            return None
            
        # 存储每条规则的匹配标签数
        matches = []
        
        # 处理文本，统一小写并去除标点
        processed_text = self._preprocess_text(text)
        
        # 检查每条规则
        for rule_index, rule in enumerate(self.response_data['rules']):
            # 记录匹配的标签数
            matched_tags = 0
            
            # 检查每个标签
            for tag in rule['tags']:
                # 处理标签，统一为小写并去除标点
                processed_tag = self._preprocess_text(tag)
                
                # 检查标签是否在文本中
                if processed_tag in processed_text:
                    matched_tags += 1
                # 也检查原始标签（保留大小写和标点）
                elif tag in text:
                    matched_tags += 1
                
            # 如果有匹配的标签，记录该规则
            if matched_tags > 0:
                matches.append({
                    'rule_index': rule_index,
                    'matched_tags': matched_tags,
                    'total_tags': len(rule['tags']),
                    'match_ratio': matched_tags / len(rule['tags'])
                })
        
        # 按匹配标签数和匹配比例排序
        if matches:
            # 先按匹配标签数排序，再按匹配比例排序
            matches.sort(key=lambda x: (x['matched_tags'], x['match_ratio']), reverse=True)
            
            # 获取匹配最好的规则
            best_match = matches[0]
            best_rule = self.response_data['rules'][best_match['rule_index']]
            
            # 从规则的响应列表中随机选择一个
            response = random.choice(best_rule['responses'])
            
            logger.info(f"匹配规则: 匹配标签 {best_match['matched_tags']}/{best_match['total_tags']}, 匹配比例: {best_match['match_ratio']:.2f}")
            
            return response
        
        # 如果没有匹配的规则，返回None
        return None
        
    def _preprocess_text(self, text):
        """
        预处理文本，统一为小写并去除标点
        """
        # 转为小写
        text = text.lower()
        # 去除标点和特殊字符
        text = re.sub(r'[^\w\s]', '', text)
        return text


if __name__ == "__main__":
    # 设置日志
    logging.basicConfig(level=logging.INFO,
                       format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    
    # 测试
    response_manager = ResponseManager()
    
    # 测试一些输入
    test_inputs = [
        "我想用苹果手机搜索一些东西",
        "我不知道怎么用百度",
        "请问怎么使用谷歌搜索？",
        "没有任何匹配的输入"
    ]
    
    for input_text in test_inputs:
        print(f"\n输入: {input_text}")
        response = response_manager.get_response(input_text)
        print(f"回复: {response if response else '没有匹配的回复'}") 