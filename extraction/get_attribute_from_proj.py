import re
import ast

def get_lhs_from_rhs(filename, name):
    # 打开并读取 .py 文件内容
    with open(filename, 'r') as file:
        file_content = file.read()

    # 解析文件内容为 AST（抽象语法树）
    tree = ast.parse(file_content)

    # 遍历 AST 节点，寻找赋值语句
    for node in ast.walk(tree):
        # 查找赋值语句
        if isinstance(node, ast.Assign):
            # 检查赋值目标是否为 name
            for target in node.targets:
                if isinstance(target, ast.Name):
                    # 检查右边是否是调用 name
                    if isinstance(node.value, ast.Call):
                        func = node.value.func
                        if isinstance(func, ast.Name) and func.id == name:
                            # 找到符合条件的赋值语句，返回源代码片段
                            return target.id
    return None

def get_attribute(filename, class_string):
    # 存储结果
    results = []

    # 打开并读取文件内容
    with open(filename, 'r') as file:
        lines = file.readlines()

    # 遍历每一行
    for line in lines:
        # 如果行中包含传入的字符串变量 xxx_string
        if class_string in line:
            # 使用正则表达式匹配 f'{xxx_string}.y', f'{xxx_string}.y.z' 或 f'{xxx_string}.y.z.m' 等形式，提取第一个 y
            # 使用 re.escape 确保 xxx_string 中包含的特殊字符被正确处理
            pattern = re.escape(class_string) + r'\.(\w+)'
            match = re.search(pattern, line)
            if match:
                y_value = match.group(1)  # 提取 y
                results.append(y_value)  # 保存结果 (完整行，y)

    return results

def get_attributes_from_file(filename, class_string):
    lhs = get_lhs_from_rhs(filename, class_string)
    #print(lhs)
    if lhs is not None:
        class_string = lhs
    attributes = get_attribute(filename, class_string)
    return attributes

'''
# 示例用法
filename = '/home/lei/compatibility_analysis/pytorch/1.0/pt.darts/utils.py'  # 替换为你的.py文件路径
class_string = 'dset_cls'  # 传入的字符串变量，替换为需要的 API 名称


lhs = get_lhs_from_rhs(filename, class_string)
if lhs is not None:
    class_string = lhs
attributes = get_attribute(filename, class_string)
print(attributes)

attributes = get_attributes_from_file(filename, class_string)
print(attributes)
'''
