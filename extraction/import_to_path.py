import ast
import os

def extract_imports_from_file(file_path):
    """从给定的 Python 文件中提取 import 信息。"""
    try:
        with open(file_path, 'r') as file:
            node = ast.parse(file.read(), filename=file_path)
    except:
        return set()
    imports = []
    for n in ast.walk(node):
        if isinstance(n, ast.Import):
            for alias in n.names:
                imports.append(alias.name)
        elif isinstance(n, ast.ImportFrom):
            if n.module:
                imports.append(n.module)
                for alias in n.names:
                    imports.append(f"{n.module}.{alias.name}")
            else:
                # 处理相对导入的情况
                for alias in n.names:
                    imports.append(alias.name)
    return set(imports)

def infer_directory_structure(imports):
    """根据导入信息推断目录结构。"""
    structure = {}
    for imp in imports:
        parts = imp.split('.')
        cursor = structure
        for part in parts:
            cursor = cursor.setdefault(part, {})
    return structure

def print_directory_structure(structure, prefix=''):
    """将目录结构打印为 'a/b/c' 形式的路径，并返回这些路径的字符串。"""
    paths = []
    if not prefix:
        prefix = ''
    else:
        prefix += '.'

    for key, value in structure.items():
        current_path = prefix + key
        paths.append(current_path)
        if value:  # 如果有子目录
            paths.extend(print_directory_structure(value, current_path))
    return paths

def paths_of_import_file(file_path):
    imports = extract_imports_from_file(file_path)
    structure = infer_directory_structure(imports)
    directory_paths = print_directory_structure(structure)
    directory_paths_set = set(directory_paths)
    return directory_paths_set

def get_path_by_extension(root_dir, flag='.py'):
    paths = []
    for root, dirs, files in os.walk(root_dir):
        files = [f for f in files if not f[0] == '.']  # skip hidden files such as git files
        dirs[:] = [d for d in dirs if not d[0] == '.']
        for f in files:
            if f.endswith(flag):
                paths.append(os.path.join(root, f))
    return paths


def get_paths_of_import(root_dir):
    paths = get_path_by_extension(root_dir)
    directory_paths_set = set()
    for file_path in paths:
        a = paths_of_import_file(file_path)
        #print(a)
        directory_paths_set.update(a)
    return directory_paths_set


