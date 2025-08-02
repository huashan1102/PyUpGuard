import os
import ast

def get_python_modules_and_packages_from_dir(directory, target_library):
    paths = []
    for root, dirs, files in os.walk(directory):
        #print(f"Scanning: {root}")
        # 列出所有 Python 文件（模块）
        for file in files:
            if file.endswith('.py'):
                #print(f"Module: {os.path.join(root, file)}")
                file_remove_py = file[:-3]
                #print(file_remove_py)
                paths.append(os.path.join(root, file_remove_py))
                
                
        # 暂存要在下一轮循环中遍历的目录
        temp_dirs = []
        for dir in dirs:
            subdir_path = os.path.join(root, dir)
            paths.append(subdir_path)
            init_file = os.path.join(root, dir, '__init__.py')
            #print(dir)
            if os.path.exists(init_file):
                paths.append(os.path.join(root, dir))

    paths_set = set(paths)
    filtered_set = {item for item in paths_set if not item.endswith('__pycache__')}
    prefix_to_remove = directory + '/'
    #print(prefix_to_remove)
    res = {path.replace(prefix_to_remove, target_library+'/') for path in filtered_set}
    res = {item.replace('/', '.') for item in res}

    return res

def extract_imported_names_from_init_py(project_path):
    """
    从指定项目路径下的 __init__.py 文件中提取导入的名称。
    
    :param project_path: 项目文件夹的路径
    :return: 包含相对路径和导入名称的元组列表
    """
    imported_names = []  # 存储导入名称的列表
    for root, dirs, files in os.walk(project_path):  # 遍历项目路径下的所有目录和文件
        if '__init__.py' in files:  # 检查是否存在 __init__.py 文件
            init_py_path = os.path.join(root, '__init__.py')  # 获取 __init__.py 文件的完整路径
            relative_path = os.path.relpath(root, project_path)  # 计算相对于项目路径的相对路径
            with open(init_py_path, 'r', encoding='utf-8') as f:  # 以 UTF-8 编码打开 __init__.py 文件
                try:
                    tree = ast.parse(f.read(), filename=init_py_path)  # 解析文件内容为 AST
                except SyntaxError as e:
                    print(f"在文件 {init_py_path} 中发现语法错误: {e}")  # 捕获并打印语法错误
                    continue  # 继续处理下一个文件
                for node in ast.walk(tree):  # 遍历 AST 中的每个节点
                    if isinstance(node, ast.ImportFrom):  # 检查节点是否为 ImportFrom
                        for alias in node.names:  # 遍历导入的名称
                            name = alias.name  # 获取导入名称
                            imported_names.append((relative_path, name))  # 添加到导入名称列表
                    elif isinstance(node, ast.Import):  # 检查节点是否为 Import
                        for alias in node.names:  # 遍历导入的名称
                            name = alias.name  # 获取导入名称
                            imported_names.append((relative_path, name))  # 添加到导入名称列表
                    elif isinstance(node, ast.Assign):
                        for target in node.targets:
                            if isinstance(target, ast.Name) and target.id == '__all__':
                                if isinstance(node.value, ast.List):
                                    #return node.value.elts
                                    #return elt.s for elt in node.value.elts if isinstance(elt, ast.Str)
                                    #return [elt.s for elt in node.value.elts if isinstance(elt, ast.Str)]
                                    for elt in node.value.elts:
                                        if isinstance(elt, ast.Str):
                                            imported_names.append((relative_path, elt.s))
    return imported_names  # 返回所有导入名称及其相对路径的列表


def get_python_modules_and_packages_from_init(directory, target_library):
    res = set()  # 用于存储获取的模块和包名称的集合

    # 从指定目录的 __init__.py 文件中提取被导入的名称
    names = extract_imported_names_from_init_py(directory)
    for path, name in names:
        if path == '.':  # 判断是否为当前目录
            res.add(target_library + path + name)  # 添加目标库的模块名称
        else:
            res.add(target_library + '.' + name)  # 添加目标库的子模块名称
        # print(f"子包路径: {path}，导入名称: {name}")  # 可选：调试信息，输出子包路径和导入名称
    return res  # 返回包含所有模块和包名称的集合

'''
directory = '/dataset/lei/libraries/tensorflow/tensorflow1.10.0'  
dirs = list_python_modules_and_packages(directory)
'''
