
#　使用python,将tel.txt 文件分成多个文件，　原来的文件大概有1000000行，新的文件每30000行一个，
#　新的文件保存为　tel950.txt/tel951.txt/tel952.txt/tel953.txt ...   

def split_large_file(input_file, lines_per_file=28000, prefix='tel', start_num=950):
    with open(input_file, 'r') as f:
        file_count = start_num
        output_file = None
        
        for i, line in enumerate(f, 1):
            if i % lines_per_file == 1:
                if output_file:
                    output_file.close()
                output_filename = f"{prefix}{file_count}.txt"
                output_file = open(output_filename, 'w')
                file_count += 1
            output_file.write(line)
        
        if output_file:
            output_file.close()

split_large_file('tel.txt')
