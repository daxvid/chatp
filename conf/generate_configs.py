
import os

def generate_configs(base_file, count=40, start_num=950):
    with open(base_file, 'r') as f:
        template = f.read()
    
    for i in range(1, count+1):
        new_num = start_num + i
        base_num = 359010 + i
        
        new_content = template.replace("950", str(new_num))
        new_content = new_content.replace("359010", str(base_num))
        
        output_file = f"config{new_num}.yaml"
        with open(output_file, 'w') as f:
            f.write(new_content)

generate_configs('config950.yaml')
