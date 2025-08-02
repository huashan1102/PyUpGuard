from extraction.import_to_path import get_paths_of_import, paths_of_import_file
from extraction.lib_module_and_package_extraction import get_python_modules_and_packages_from_dir, get_python_modules_and_packages_from_init
from extraction.getCall import get_all_used_api
from call_graph.engine import main as cfmain
from .library_version_change import get_version_change
from utils.util import extract_function_defs_from_file, extract_classes_from_file, get_library_call_module, shortenPath
from extraction.library_api_and_module import extract_from_directory
from extraction.get_attribute_from_proj import get_attributes_from_file
from call_graph.get_FDG import get_FDG_from_requirements
from .params_compat import analyzeCompatibility
import json, platform, time, re, ast, os, logging
#from fuzzywuzzy import process
from thefuzz import process

if (platform.system() == 'Windows'):
    slash = "\\"
else:
    slash = r"/"

library_path_prefix = ""
constraint_path_prefix = ""
version_path_prefix = ""
api_path_prefix = ""

def setup_path_2(library_path_prefix_pass, constraint_path_prefix_pass, version_path_prefix_pass, api_path_prefix_pass):
    global library_path_prefix, constraint_path_prefix, version_path_prefix, api_path_prefix
    library_path_prefix = library_path_prefix_pass
    constraint_path_prefix = constraint_path_prefix_pass
    version_path_prefix = version_path_prefix_pass
    api_path_prefix = api_path_prefix_pass

def transform_and_remove_last_segment(input_str):
    # 将点号替换为斜杠
    transformed_str = input_str.replace('.', '/')
    
    # 移除最后一个斜杠及其后面的所有内容
    last_slash_index = transformed_str.rfind('/')
    if last_slash_index != -1:
        transformed_str = transformed_str[:last_slash_index]
    
    return transformed_str

def remove_last_segment(input_str):
    # 移除最后一个斜杠及其后面的所有内容
    tmp = input_str
    last_slash_index = tmp.rfind('/')
    if last_slash_index != -1:
        tmp = tmp[:last_slash_index]
    
    return tmp

def extract_after_last_dot(s):
    # 找到最后一个'.'的位置
    last_dot_index = s.rfind('.')
    # 提取最后一个'.'之后的字符串
    result = s[last_dot_index+1:] if last_dot_index != -1 else s
    return result

def extract_lines(filename, line_number):
    with open(filename, 'r') as file:
        for current_line_number, line in enumerate(file, start=1):
            if current_line_number == line_number:
                #print(f"{current_line_number}-{line.strip()}")
                return line.strip()

def extract_code_info(file_path, start_line, end_line):
    class RaiseVisitor(ast.NodeVisitor):
        def __init__(self):
            self.raise_expressions = []
            self.try_except_level = 0  # 用于跟踪嵌套级别

        def visit_Try(self, node):
            # 进入 Try 节点，增加嵌套级别
            self.try_except_level += 1
            # 遍历 try 块的主体
            for stmt in node.body:
                self.visit(stmt)
            # 遍历 except 块
            for handler in node.handlers:
                self.visit(handler)
            # 遍历 else 块
            if node.orelse:
                for stmt in node.orelse:
                    self.visit(stmt)
            # 遍历 finally 块
            if node.finalbody:
                for stmt in node.finalbody:
                    self.visit(stmt)
            # 离开 Try 节点，减少嵌套级别
            self.try_except_level -= 1

        def visit_Raise(self, node):
            # 仅当不在 try...except 块中时才提取 raise 表达式
            if self.try_except_level == 0:
                if node.exc:  # 如果 raise 有异常信息
                    self.raise_expressions.append(ast.unparse(node.exc))
                else:  # 如果是裸 raise，添加 None 或占位符
                    self.raise_expressions.append(None)
            self.generic_visit(node)

        def visit_ExceptHandler(self, node):
            # 进入 except 块，嵌套级别已经在 visit_Try 中增加，这里直接遍历子节点
            for stmt in node.body:
                self.visit(stmt)

    # 读取文件中的指定行
    with open(file_path, 'r', encoding='utf-8') as file:
        lines = file.readlines()

    # 确保行范围有效
    if start_line < 1 or end_line > len(lines) or start_line > end_line:
        raise ValueError("Invalid line range")

    # 提取指定行范围的代码
    selected_lines = lines[start_line - 1:end_line]
    code_segment = ''.join(selected_lines)

    # 规范化代码，添加一个占位的包装
    normalized_code = f"if True:\n" + "\n".join("    " + line for line in selected_lines)

    # 将规范化的代码解析为 AST
    try:
        tree = ast.parse(normalized_code, mode='exec')
    except:
        return []

    # 使用 RaiseVisitor 查找所有的 raise 表达式
    visitor = RaiseVisitor()
    visitor.visit(tree)

    # 提取的 raise 表达式
    extracted_expressions = visitor.raise_expressions

    return extracted_expressions

def build_reverse_graph(graph):
    """
    构建逆图，即将子节点和父节点的关系反转。
    """
    reverse_graph = {}
    for node, children in graph.items():
        for child in children:
            if child not in reverse_graph:
                reverse_graph[child] = []
            reverse_graph[child].append(node)
    return reverse_graph

def find_parents_chain(reverse_graph, node):
    """
    找到指定节点的所有父节点，并以调用链的方式输出。
    """
    parent_chains = []  # 用来记录所有的父节点链
    visited = set()     # 用来记录已访问的节点
    
    def _find_parents_recursive(current_node, chain):
        # 如果当前节点有父节点且没有被访问过
        if current_node in reverse_graph and current_node not in visited:
            visited.add(current_node)
            # 记录当前节点到调用链
            for parent in reverse_graph[current_node]:
                new_chain = chain + [parent]  # 更新调用链
                parent_chains.append(new_chain)  # 将新链加入结果
                _find_parents_recursive(parent, new_chain)  # 递归查找父节点
    
    # 从目标节点开始查找
    _find_parents_recursive(node, [node])
    return parent_chains

def generate_parts(input_string):
    parts = input_string.split('/')  # 按照"/"分割字符串
    result = []
    
    # 生成每个子字符串
    for i in range(1, len(parts) + 1):
        result.append('/'.join(parts[:i]))
    
    return result

def get_all_related_py_files(py_file):
    res = []
    tmp = remove_last_segment(py_file)
    #print(tmp)
    # 找到所有导入的模块
    import_paths = paths_of_import_file(py_file)
    # 找到所有模块对应的文件
    for import_path in import_paths:
        new_import_path = import_path.replace('.', slash)
        new_py_pkg = tmp + slash + new_import_path
        new_py_file = tmp + slash + new_import_path + ".py"
        if os.path.isdir(new_py_pkg):
            if new_py_pkg + slash + "__init__.py" not in res:
                res.append(new_py_pkg + slash + "__init__.py")
        elif os.path.isfile(new_py_file):
            if new_py_file not in res:
                res.append(new_py_file)
        elif tmp.split(slash)[-1] == import_path.split(slash)[0]:
            new_new_py_pkg = remove_last_segment(tmp) + slash + new_import_path
            new_new_py_file = remove_last_segment(tmp) + slash + new_import_path + ".py"
            if os.path.isdir(new_new_py_pkg):
                if new_new_py_pkg + slash + "__init__.py" not in res:
                    res.append(new_new_py_pkg + slash + "__init__.py")
            elif os.path.isfile(new_new_py_file):
                if new_new_py_file not in res:
                    res.append(new_new_py_file)


    return res

def get_py_files_to_examine(api_to_examine, target_project, target_proj_dependency):
    py_files_to_examine = set()
    #print(api_to_examine)
    for api in api_to_examine:
        if api.endswith("__init__") or api.endswith("__default_init__"):
            #tmp = library_path_prefix + target_project + slash + target_project + target_proj_dependency[target_project] + slash + transform_and_remove_last_segment(transform_and_remove_last_segment(api)) + ".py"
            tmp = generate_parts(transform_and_remove_last_segment(transform_and_remove_last_segment(api)))
            #print(transform_and_remove_last_segment(transform_and_remove_last_segment(api)))
            i = 0
            for j in reversed(tmp):
                if i == 0:
                    py_files_to_examine.add(library_path_prefix + target_project + slash + target_project + target_proj_dependency[target_project] + slash + j + ".py")
                else:
                    py_files_to_examine.add(library_path_prefix + target_project + slash + target_project + target_proj_dependency[target_project] + slash + j + "/" + "__init__.py")
                i = i + 1
            #py_files_to_examine.add(tmp)
        else:
            tmp = generate_parts(transform_and_remove_last_segment(api))
            i = 0
            for j in reversed(tmp):
                if i == 0:
                    py_files_to_examine.add(library_path_prefix + target_project + slash + target_project + target_proj_dependency[target_project] + slash + j + ".py")
                else:
                    py_files_to_examine.add(library_path_prefix + target_project + slash + target_project + target_proj_dependency[target_project] + slash + j + "/" + "__init__.py")
                i = i + 1
            
    new_py_files_to_examine = py_files_to_examine.copy()
    new_py_files_to_examine = list(new_py_files_to_examine)
    for py_file in new_py_files_to_examine:
        res = get_all_related_py_files(py_file)
        for r in res:
            if r not in new_py_files_to_examine:
                new_py_files_to_examine.append(r)

    py_files_to_examine = set(new_py_files_to_examine)
    return py_files_to_examine

def extract_inner_parentheses(s):
    stack = []  # 用来记录括号的嵌套
    result = ""  # 用来存储结果
    inside = False  # 是否在括号内

    #cnt = 0  # 记录括号的数量
    for char in s:
        #print(stack)
        if char == '(':
            if not stack:  # 如果栈为空，说明是第一个括号
                inside = True
            stack.append(char)
        elif char == ')':
            stack.pop()
            if not stack:  # 如果栈为空，说明当前括号对已经结束
                inside = False
            if inside:
                result += char
        if inside:
            result += char
        else:
            result += char
            break
    
    while result.endswith(")"):
        result = result[:-1]
    result = f"{result})"
    return result if result else None

def generate_full_parent_chains(lst):
    result = []
    for sublist in lst:
        for i in range(1, len(sublist) + 1):
            result.append(sublist[:i])
    return result

def full_CG(s, proj_path, target_project, target_library, start_version, target_version, start_library_path, target_library_path, target_library_call_module, proj, path, target_proj_dependency, python_version):
    prefix = "" 
    if target_project != proj:  #例如torchvision-torch，从目标项目为入口得到torchvision实际使用torch的api
        FDG = get_FDG_from_requirements(target_proj_dependency, python_version)
        # 构建逆图
        reverse_graph = build_reverse_graph(FDG)
        # 找到目标库的调用链
        parent_chains = find_parents_chain(reverse_graph, target_project)
        parent_chains = generate_full_parent_chains(parent_chains)

        target_project_call_module = get_library_call_module(target_project)
        if not parent_chains:
            if os.path.isfile('./data/call_graph/' + proj + "-" + target_project + target_proj_dependency[target_project] + '-outside.json'):
                with open('./data/call_graph/' + proj + "-" + target_project + target_proj_dependency[target_project] + '-outside.json', 'r') as file:
                    data = json.load(file)
                if target_library in data.keys():
                    s = data[target_library]
                else:
                    s = []
            else:
                #例如，没有proj-torchvision-outside.json，重新建立调用图
                new_s, y, z, m = get_all_used_api(path, target_project_call_module)

                ls = ""
                for name in new_s:
                    ls += name
                    ls += ","
                
                if ls == "":
                    input1 = {}
                    input2 = []
                    with open('./data/call_graph/' + proj + "-" + target_project + target_proj_dependency[target_project] + '-outside.json', 'w') as file:
                        json.dump(input1, file)
                    with open('./data/call_graph/' + proj + "-" + target_project + target_proj_dependency[target_project] + '-entry.json', 'w') as file:
                        json.dump(input2, file)
                else:
                    target_project_path = library_path_prefix + target_project + slash + target_project + target_proj_dependency[target_project] + slash + target_project_call_module
                    partc = [target_project_path, "--language", "py", "--output", "data/call_graph/" + proj + "-" + target_project + target_proj_dependency[target_project] + ".json", "--entry-functions", ls]
                    cfmain(sys_argv=partc, if_add_package_name = True)

                with open('./data/call_graph/' + proj + "-" + target_project + target_proj_dependency[target_project] + '-outside.json', 'r') as file:
                    data = json.load(file)
                if target_library in data.keys():
                    s = data[target_library]
                else:
                    s = []
            #建立proj-torchvision-torch调用图
            ls = ""
            for name in s:
                ls += name
                ls += ","
            
            if ls == "":
                input1 = {}
                input2 = []
                with open('./data/call_graph/' + proj + "-" + target_project + target_proj_dependency[target_project] + "-" + target_library + target_proj_dependency[target_library] + '-outside.json', 'w') as file:
                    json.dump(input1, file)
                with open('./data/call_graph/' + proj + "-" + target_project + target_proj_dependency[target_project] + "-" + target_library + target_proj_dependency[target_library] + '-entry.json', 'w') as file: 
                    json.dump(input2, file)
            else:
                if os.path.exists(start_library_path):
                    partc = [start_library_path, "--language", "py", "--output", "data/call_graph/" + proj + "-" + target_project + target_proj_dependency[target_project] + "-" + target_library + target_proj_dependency[target_library] + ".json", "--entry-functions", ls]
                else:
                    split_path = start_library_path.split('/')
                    print(split_path)

                    # 去除最后两个部分
                    result = '/'.join(split_path[:-2])
                    partc = [result, "--language", "py", "--output", "data/call_graph/" + proj + "-" + target_project + target_proj_dependency[target_project] + "-" + target_library + target_proj_dependency[target_library] + ".json", "--entry-functions", ls]
                cfmain(sys_argv=partc, if_add_package_name = True)
            #提取proj-torchvision调用的torch的API的全名
            with open('./data/call_graph/' + proj + "-" + target_project + target_proj_dependency[target_project] + "-" + target_library + target_proj_dependency[target_library] + '-entry.json', 'r') as file:
                apis_full_name = json.load(file)
            
            with open('./data/call_graph/' + proj + "-" + target_project + target_proj_dependency[target_project] + '-entry.json', 'r') as file:
                api_to_examine = json.load(file)
        else:
            apis_full_name = []
            api_to_examine = []
            for chain in parent_chains:
                prefix = proj
                i = 0
                for chain_proj in reversed(chain):
                    chain_proj_call_module = get_library_call_module(chain_proj)

                    prefix = prefix + "-" + chain_proj + target_proj_dependency[chain_proj]
                    #print(prefix)
                    if os.path.isfile('./data/call_graph/' + prefix + '-outside.json'):
                        #检查是否有outside.json
                        with open('./data/call_graph/' + prefix + '-outside.json', 'r') as file:
                            data = json.load(file)
                    else:
                        #重新建立调用图
                        if i == 0:
                            new_s, y, z, m = get_all_used_api(path, chain_proj_call_module)

                            ls = ""
                            for name in new_s:
                                ls += name
                                ls += ","
                               
                            if ls == "":
                                input1 = {}
                                input2 = []
                                with open('./data/call_graph/' + prefix + '-outside.json', 'w') as file:
                                    json.dump(input1, file)
                                with open('./data/call_graph/' + prefix + '-entry.json', 'w') as file:
                                    json.dump(input2, file)
                            else:
                                chain_proj_path = library_path_prefix + chain_proj + slash + chain_proj + target_proj_dependency[chain_proj] + slash + chain_proj_call_module
                                partc = [chain_proj_path, "--language", "py", "--output", "data/call_graph/" + prefix + ".json", "--entry-functions", ls]
                                cfmain(sys_argv=partc, if_add_package_name = True)
                        else:
                            #解决一些库的名字就带-的问题
                            pos = prefix.rfind('-')
                            if os.path.exists('./data/call_graph/' + prefix[:pos] + '-outside.json'):
                                with open('./data/call_graph/' + prefix[:pos] + '-outside.json', 'r') as file:
                                    data = json.load(file)
                            else:
                                pos = prefix[:pos].rfind('-')
                                with open('./data/call_graph/' + prefix[:pos] + '-outside.json', 'r') as file:
                                    data = json.load(file)
                            if chain_proj in data.keys():
                                new_s = data[chain_proj]
                            else:
                                new_s = []
                            ls = ""
                            for name in new_s:
                                ls += name
                                ls += ","
                            
                            if ls == "":
                                input1 = {}
                                input2 = []
                                with open('./data/call_graph/' + prefix + '-outside.json', 'w') as file:
                                    json.dump(input1, file)
                                with open('./data/call_graph/' + prefix + '-entry.json', 'w') as file:
                                    json.dump(input2, file)
                            else:
                                chain_proj_path = library_path_prefix + chain_proj + slash + chain_proj + target_proj_dependency[chain_proj] + slash + chain_proj_call_module
                                partc = [chain_proj_path, "--language", "py", "--output", "data/call_graph/" + prefix + ".json", "--entry-functions", ls]
                                cfmain(sys_argv=partc, if_add_package_name = True)
                    i = i + 1                      
                    #prj-A-B-torchvision-torch调用图建立
                    with open('./data/call_graph/' + prefix + '-entry.json', 'r') as file:
                        tmp = json.load(file)
                    api_to_examine = api_to_examine + tmp
                    ls = ""
                    new_s = []
                    with open('./data/call_graph/' + prefix + "-outside.json", 'r') as file:
                        data = json.load(file)
                    if target_library in data.keys():
                        new_s = data[target_library]
                    else:
                        new_s = []
                    for name in new_s:
                        ls += name
                        ls += ","

                    output_path = prefix + "-" + target_library + target_proj_dependency[target_library]
                    if ls == "":
                        input1 = {}
                        input2 = []
                        with open('./data/call_graph/' + output_path + '-outside.json', 'w') as file:
                            json.dump(input1, file)
                        with open('./data/call_graph/' + output_path + '-entry.json', 'w') as file:
                            json.dump(input2, file)
                    else:
                        partc = [start_library_path, "--language", "py", "--output", "data/call_graph/" + output_path + ".json", "--entry-functions", ls]
                        cfmain(sys_argv=partc, if_add_package_name = True)

                    #提取proj-A-B-torchvision调用的torch的API的全名
                    #print(end_output_path)
                    with open('./data/call_graph/' + output_path + '-entry.json', 'r') as file:
                        tmp = json.load(file)
                    apis_full_name = apis_full_name + tmp
                
    else:
        #根据提取的API构建调用图
        #print(f"**************************")
        ls = ""
        for name in s:
            ls += name
            ls += ","
        
        if ls == "":
            input1 = {}
            input2 = []
            with open('./data/call_graph/' + target_project + "-" + target_library + start_version + '-outside.json', 'w') as file:
                json.dump(input1, file)
            with open('./data/call_graph/' + target_project + "-" + target_library + start_version + '-entry.json', 'w') as file:
                json.dump(input2, file)
        else:
            if os.path.exists(start_library_path):
                partc = [start_library_path, "--language", "py", "--output", "data/call_graph/" + proj + "-" + target_library + start_version + ".json", "--entry-functions", ls]
                #print(f"**************************")
            else:
                split_path = start_library_path.split('/')
                #print(split_path)

                # 去除最后两个部分
                result = '/'.join(split_path[:-2])
                partc = [result, "--language", "py", "--output", "data/call_graph/" + proj + "-" + target_library + start_version + ".json", "--entry-functions", ls]
            cfmain(sys_argv=partc, if_add_package_name = True)
        #提取项目调用的API的全名
        with open('./data/call_graph/' + target_project + "-" + target_library + start_version + '-entry.json', 'r') as file:
            apis_full_name = json.load(file)
        api_to_examine = s.copy()
    #logging.info(f"**{apis_full_name}******************")
    return apis_full_name, api_to_examine

def get_all_library_info(library_path, library_call_module, version, lib):
    json_file_path = f"{api_path_prefix}{lib}/{version}.json"
    if not os.path.exists(f"{api_path_prefix}{lib}"):
        os.makedirs(f"{api_path_prefix}{lib}")
    if not os.path.exists(json_file_path):
        res = extract_from_directory(library_path)
        dir = get_python_modules_and_packages_from_dir(library_path, library_call_module)
        init_dir = get_python_modules_and_packages_from_init(library_path, library_call_module)
        dir.update(init_dir)
        res["modules"] = list(dir)
        api_usage_in_target_library, _1, __2, _3  = get_all_used_api(library_path, library_call_module)
        res["api_usage"] = list(api_usage_in_target_library)
        funcs = res["functions"]
        new_funcs = shortenPath(funcs, lib, version)
        res["functions"] = new_funcs
        classes = res["classes"]
        new_classes = shortenPath(classes, lib, version)
        res["classes"] = new_classes
        with open(json_file_path, "w") as f:
            json.dump(res, f)
    with open(json_file_path, "r") as f:
        res = json.load(f)
    return res

def is_target_library_code_conflict(proj_path, target_project, target_library, start_version, target_version, start_library_path, target_library_path, target_library_call_module, proj, path, target_proj_dependency, python_version):
    res = False
    if target_project == proj:
        logging.info(f"Checking {target_project} is compatible with {target_library}{target_version}?...")
    else:
        logging.info(f"Checking {target_project}{target_proj_dependency[target_project]} is compatible with {target_library}{target_version}?...")
    #2、起始版本升级到目标版本后是否有不兼容变更
    #将项目中调用了目标库的API都提取
    #这里需要修改，目前最多考虑了两次调用例如proj-torchvision-torch。实际上可能有更多多层次调用（proj-A-B-torchvision-torch）。已修改2024-11-27
    s, api_calls_dict, api_file_map, api_paras_map = get_all_used_api(proj_path, target_library_call_module) 
    #print(s)
    s = list(set(s))
    api_short_to_full_mapping = {}
    api_full_to_short_mapping = {}

    if len(s) == 0:
        if target_project == proj:
            logging.info(f"{target_project} is compatible with {target_library}{target_version}")
        else:
            logging.info(f"{target_project}{target_proj_dependency[target_project]} is compatible with {target_library}{target_version}")
        return res

    #获取目标库从起始版本和目标版本的API，模块等
    start_api_dict = get_all_library_info(start_library_path, target_library_call_module, start_version, target_library)
    target_api_dict = get_all_library_info(target_library_path, target_library_call_module, target_version, target_library)
    new_s = []
    #将项目中调用了目标库的API都转化为全调用形式
    for i in s:
        if i in start_api_dict['functions']:
            if isinstance(start_api_dict['functions'][i], str):
                new_s.append(start_api_dict['functions'][i])
        elif i in start_api_dict['classes']:
            if isinstance(start_api_dict['classes'][i], str):
                new_s.append(start_api_dict['classes'][i])
        else:
            new_s.append(i)
    apis_full_name, api_to_examine = full_CG(new_s, proj_path, target_project, target_library, start_version, target_version, start_library_path, target_library_path, target_library_call_module, proj, path, target_proj_dependency, python_version) 
    if target_project == proj:
        #对API进行去重，因为同一个API可能匹配了多种调用形式。通过模糊匹配进行去重。
        for i in s:
            api_group = []
            for j in apis_full_name:
                if i.split(".")[-1] == j.split(".")[-1]:
                    api_group.append(j)
            if len(api_group) > 1:
                best_match = process.extractOne(i, api_group)
                for remove in api_group:
                    if remove != best_match[0]:
                        apis_full_name.remove(remove)
    for i in apis_full_name:
        for j in s:
            if i.endswith("__init__") or i.endswith("__default_init__"):
                if i.split(".")[-2] == j.split(".")[-1]:
                    api_short_to_full_mapping[j] = i
                    api_full_to_short_mapping[i] = j
            else:
                if i.split(".")[-1] == j.split(".")[-1]:
                    api_short_to_full_mapping[j] = i
                    api_full_to_short_mapping[i] = j
    
    deprecated_functions, deprecated_classes, deprecated_methods, deprecated_global_vars = get_version_change(start_api_dict, target_api_dict)
         
    #、检查头文件部分是否兼容
    if target_project != proj:
        #  例如proj-torchvision-pillow，torchvision中不是所有的.py文件都被涉及到，需要根据实际涉及到的torchvision API来判断涉及到的.py文件
        py_files_to_examine = get_py_files_to_examine(api_to_examine, target_project, target_proj_dependency)
        pkg_and_module = []
        for py_file in py_files_to_examine:
            tmp = paths_of_import_file(py_file)
            for t in tmp:
                if t not in pkg_and_module:
                    pkg_and_module.append(t)
    else:
        pkg_and_module = get_paths_of_import(proj_path)  #将项目中的import语句都转化成a.b.c的形式
    
    start_dir = set(start_api_dict['modules'])
    target_dir = set(target_api_dict['modules'])
    
    for module in pkg_and_module:
        if module in (start_dir - target_dir) and module.startswith(target_library_call_module):
            if module in target_api_dict["api_usage"]:
                continue

            if target_project != proj:
                logging.info(f"{target_project}{target_proj_dependency[target_project]} is not compatible with {target_library}{target_version}-The {module} is deprecated.")
            else:
                logging.info(f"{proj} is not compatible with {target_library}{target_version}-The {module} is deprecated.")
            res = True
            return res   
    #解决 from PIL import Image, ImageOps, ImageEnhance, PILLOW_VERSION问题
    for module in pkg_and_module:
        if module.startswith(target_library_call_module):
            parts = module.split(".")
            new_module = '.'.join(parts[1:])
        else:
            continue
        if module in deprecated_global_vars:
            #解决torch.jit.annotations误报问题，API-torch.jit.annotations废弃，但是模块-torch.jit.annotations还存在，所有from .import annotations 也会被误报
            if module in target_dir:
                continue
            if module in target_api_dict["api_usage"]:
                continue
            # 解决误报的问题，可以查找import中是否有定义
            flag = 0
            api_path = target_library_path + slash + transform_and_remove_last_segment(module.replace(target_library_call_module+'.', '')) + '.py'
            if os.path.exists(api_path):
                import_api_names = paths_of_import_file(api_path)
                api_last_name = module.split(".")[-1]
                for x in import_api_names:
                    if x.endswith(api_last_name):
                        flag = 1

            if flag == 1:
                continue

            if target_project != proj:
                logging.info(f"{target_project}{target_proj_dependency[target_project]} is not compatible with {target_library}{target_version}-The {module} is deprecated.")
            else:
                logging.info(f"{proj} is not compatible with {target_library}{target_version}-The {module} is deprecated.")
            res = True
            return res
        elif module in deprecated_functions or module in deprecated_classes:
            if module in target_api_dict["api_usage"]:
                continue
            #解决sklearn.metrics.regression.mean_squared_error找不到的问题
            flag = 0
            if "." in new_module:
                init_path = target_library_path + slash + transform_and_remove_last_segment(new_module) + slash + '__init__.py'
                #print(init_path)
                if os.path.exists(init_path):
                    xxx = paths_of_import_file(init_path)
                    for xx in xxx:
                        if xx.split(".")[-1] == new_module.split(".")[-1]:
                            flag = 1
                            break
                    
                    function_names = extract_function_defs_from_file(init_path)
                    class_names = extract_classes_from_file(init_path)
                    import_api_names = paths_of_import_file(init_path)
                    for function_name in function_names:
                        if function_name.endswith(new_module.split(".")[-1]):
                            flag = 1
                            break
                    for class_name in class_names:
                        if class_name.endswith(new_module.split(".")[-1]):
                            flag = 1
                            break
                    for x in import_api_names:
                        if x.endswith(new_module.split(".")[-1]):
                            flag = 1
                            break
            else:
                init_path = target_library_path + slash + '__init__.py'
                if os.path.exists(target_library_path + slash + '__init__.py'):
                    xxx = paths_of_import_file(init_path)
                    for xx in xxx:
                        if xx.split(".")[-1] == new_module.split(".")[-1]:
                            flag = 1
                            break
                    function_names = extract_function_defs_from_file(init_path)
                    class_names = extract_classes_from_file(init_path)
                    import_api_names = paths_of_import_file(init_path)
                    #print(function_names)
                    for function_name in function_names:
                        if function_name.endswith(new_module):
                            flag = 1
                            break
                    for class_name in class_names:
                        if class_name.endswith(new_module):
                            flag = 1
                            break
                    for x in import_api_names:
                        if x.endswith(new_module):
                            flag = 1
                            break
            if flag == 1:
                continue
            # 解决误报的问题，可以查找import中是否有定义
            flag = 0
            api_path = target_library_path + slash + transform_and_remove_last_segment(module.replace(target_library_call_module+'.', '')) + '.py'
            if os.path.exists(api_path):
                import_api_names = paths_of_import_file(api_path)
                api_last_name = module.split(".")[-1]
                for x in import_api_names:
                    if x.endswith(api_last_name):
                        flag = 1

            if flag == 1:
                continue

            if module in deprecated_functions and module in start_api_dict['functions']:
                if isinstance(start_api_dict['functions'][module], str):
                    continue
            #解决torch.nn.functional.pad误报问题，可以查找torch.nn.functional.pyi 是否有def pad
            flag = 0
            pyi_file_path4 = target_library_path + slash + transform_and_remove_last_segment(new_module) + '.pyi'
            if os.path.exists(pyi_file_path4):
                function_names = extract_function_defs_from_file(pyi_file_path4)
                class_names = extract_classes_from_file(pyi_file_path4)
                for function_name in function_names:
                    if function_name.endswith(new_module.split(".")[-1]):
                        flag = 1
                        break
                for class_name in class_names:
                    if class_name.endswith(new_module.split(".")[-1]):
                        flag = 1
                        break
            if flag == 1:
                continue
            
            #解决torch.jit.annotations误报问题，API-torch.jit.annotations废弃，但是模块-torch.jit.annotations还存在，所有from .import annotations 也会被误报
            if module in target_dir:
                continue

            if target_project != proj:
                logging.info(f"{target_project}{target_proj_dependency[target_project]} is not compatible with {target_library}{target_version}-The {module} is deprecated.")
            else:
                logging.info(f"{proj} is not compatible with {target_library}{target_version}-The {module} is deprecated.")
            res = True
            return res 
    #2.2、检查功能代码部分是否兼容
    #检测客户端代码是否使用了废弃的API
    for api in apis_full_name:
        flag3 = 0
        for i in s:
            if i.split(".")[-1] == api.split(".")[-1]:
                flag3 = 1
                break
        if flag3 == 0 and not api.endswith("__init__" ):
            continue    #API匹配误判，跳过
        parts = api.split(".")
        new_api = '.'.join(parts[1:])

        if api.endswith("split") or api.endswith("values") or api.endswith("key"):
            continue      #python内置的函数，跳过

        #检测客户端代码是否使用了废弃的函数，类，方法等
        if new_api.endswith("__init__"):   #检测客户端代码是否使用了废弃的类
            class_api = new_api.replace('.__init__', '')
            flag3 = 0
            if target_project == proj:
                for i in s:
                    if i.split(".")[-1] == class_api.split(".")[-1]:
                        flag3 = 1
                        break
            if flag3 == 0:
                continue    #API匹配误判，跳过
            # 修复检测api位置改变但是通过装饰器是的api还可以正常使用失败问题
            if f"{target_library_call_module}.{class_api}" in deprecated_classes:
                xx = api_full_to_short_mapping[api]
                if xx in target_api_dict["classes"].keys():
                    continue
                if xx in target_api_dict["api_usage"]:
                    continue
                start_class_decorator_path = start_library_path + slash + transform_and_remove_last_segment(class_api) + '.py'
                if not isinstance(start_api_dict['classes'][f"{target_library_call_module}.{class_api}"], str):
                    start_class_decorator = extract_lines(start_class_decorator_path, start_api_dict['classes'][f"{target_library_call_module}.{class_api}"]["lineno"]-1)
                else:
                    start_class_decorator = "x"
                api_last_name = class_api.split(".")[-1]
                flag = 0
                for i in target_api_dict["classes"].keys():
                    if api_last_name in i[0]:
                        target_class_decorator_path = target_library_path + slash + transform_and_remove_last_segment(i[0]) + '.py'
                        if not isinstance(target_api_dict['classes'][f"{target_library_call_module}.{class_api}"], str):
                            target_class_decorator = extract_lines(target_class_decorator_path, target_api_dict['classes'][f"{target_library_call_module}.{class_api}"]["lineno"]-1)
                        else:
                            target_class_decorator = "x"
                        #print()
                        if start_class_decorator.startswith('@') and target_class_decorator.startswith('@'):
                            if start_class_decorator== target_class_decorator:
                                flag = 1
                                break
                if flag == 1:
                    continue
                
                 # 解决误报的问题，可以查找__init__.py文件中是否有定义
                flag = 0
                for xx in s:
                    if xx.endswith(f".{class_api.split('.')[-1]}"):
                        #xx = xx.replace(target_library_call_module+'.', '')
                        parts = xx.split(".")
                        xx = '.'.join(parts[1:])
                        if "." in xx:
                            init_file_path = target_library_path + slash + transform_and_remove_last_segment(xx) + slash + '__init__.py'
                        else:
                            init_file_path = target_library_path + slash + '__init__.py'
                        if os.path.exists(init_file_path):
                            import_api_names = paths_of_import_file(init_file_path)
                            for ii in import_api_names:
                                if ii.endswith(class_api.split('.')[-1]):
                                    flag = 1
                                    break
                            if flag == 1:
                                break
                            #解决*的问题
                            for ii in import_api_names:
                                if ii.endswith(f".*"):
                                    related_file_path = target_library_path + slash + transform_and_remove_last_segment(xx) + slash + transform_and_remove_last_segment(ii) + '.py'
                                    #print(related_file_path)
                                    if os.path.exists(related_file_path):
                                        related_api_names = extract_classes_from_file(related_file_path)
                                        if f"{class_api.split('.')[-1]}" in related_api_names:
                                            flag = 1
                                            break
                            if flag == 1:
                                break
                if flag == 1:
                    continue
                # 解决误报的问题，可以查找import中是否有定义
                #解决_tqdm_notebook
                flag = 0
                api_path = target_library_path + slash + transform_and_remove_last_segment(class_api) + '.py'
                if os.path.exists(api_path):
                    import_api_names = paths_of_import_file(api_path)
                    class_api_last_name = class_api.split(".")[-1]
                    for x in import_api_names:
                        if x.endswith(class_api_last_name):
                            flag = 1
                            break
                    for i in target_api_dict["classes"].keys():
                        if i.endswith(f".{class_api.split('.')[-1]}"):
                            for j in import_api_names:
                                if j.endswith(".*"):
                                    j.replace(".*", "")
                                if j in i:
                                    flag = 1
                                    break
                                if flag == 1:
                                    break
                if flag == 1:
                    continue


                if target_project == proj:
                    logging.info(f"{target_project} is not compatible with {target_library}{target_version}-The {target_library_call_module}.{new_api} is deprecated.")
                else:
                    logging.info(f"{target_project}{target_proj_dependency[target_project]} is not compatible with {target_library}{target_version}-The {target_library_call_module}.{new_api} is deprecated.")
                res = True
                return res
            else:                                             #检测客户端代码是否使用了废弃的属性
                #获取这个类从起始版本到目标版本废弃的属性
                if f"{target_library_call_module}.{class_api}" in start_api_dict["classes"]:
                    if "attributes" in start_api_dict["classes"][f"{target_library_call_module}.{class_api}"]:
                        start_attribute_set = set(start_api_dict["classes"][f"{target_library_call_module}.{class_api}"]['attributes'])
                    else:
                        start_attribute_set = set()
                else:
                    start_attribute_set = set()
                if f"{target_library_call_module}.{class_api}" in target_api_dict["classes"]:
                    if "attributes" in target_api_dict["classes"][f"{target_library_call_module}.{class_api}"]:
                        target_attribute_set = set(target_api_dict["classes"][f"{target_library_call_module}.{class_api}"]['attributes'])
                    else:
                        target_attribute_set = set()
                else:
                    target_attribute_set = set()
                
                deprecated_attribute = start_attribute_set - target_attribute_set
                
                #获取客户端代码调用了的这个类的属性
                filename = ''
                class_string = ''
                class_str = extract_after_last_dot(class_api)
                #print(class_str)
                for key in api_calls_dict:
                    if class_str in key:
                        class_string = api_calls_dict[key]
                for key in api_file_map:
                    if class_string in key:
                        filename = api_file_map[key]
                if len(filename) > 0:
                    proj_class_attribute = get_attributes_from_file(filename, class_string)
                else:
                    proj_class_attribute = None
                
                if proj_class_attribute is not None:
                    for attribute in proj_class_attribute:
                        if attribute in deprecated_attribute:
                            if target_project == proj:
                                logging.info(f"{target_project} is not compatible with {target_library}{target_version}-The {target_library_call_module}.{class_api}.{attribute} is deprecated.")
                            else:
                                logging.info(f"{target_project}{target_proj_dependency[target_project]} is not compatible with {target_library}{target_version}-The {target_library_call_module}.{class_api}.{attribute} is deprecated.")
                            res = True
                            return res
                #print(proj_class_attribute)
        else:
            if api in deprecated_functions:
                xx = api_full_to_short_mapping[api]
                if xx in target_api_dict["functions"].keys():
                    continue
                if xx in target_api_dict["api_usage"]:
                    continue
                # 修复检测api位置改变但是通过装饰器是的api还可以正常使用失败问题
                start_functions_decorator_path = start_library_path + slash + transform_and_remove_last_segment(new_api) + '.py'
                if not isinstance(start_api_dict['functions'][api], str):
                    start_functions_decorator = extract_lines(start_functions_decorator_path, start_api_dict['functions'][api]["lineno"]-1)
                else:
                    start_functions_decorator = "x"
                api_last_name = new_api.split(".")[-1]
                flag = 0
                for i in target_api_dict["functions"].items():
                    #new_i = i[0].replace(target_library_call_module+'.', '')
                    parts = i[0].split(".")
                    new_i = '.'.join(parts[1:])
                    if i[0].endswith(f".{api_last_name}"):
                        target_functions_decorator_path = target_library_path + slash + transform_and_remove_last_segment(new_i) + '.py'
                        if not isinstance(target_api_dict['functions'][i[0]], str):
                            target_functions_decorator = extract_lines(target_functions_decorator_path, target_api_dict['functions'][i[0]]["lineno"]-1)
                        else:
                            target_functions_decorator = "x"

                        flag2 = 0
                        if target_functions_decorator is not None:
                            #print(target_functions_decorator)
                            if target_functions_decorator.startswith('@'):
                                decorator_prefix = re.findall(r'["\'](.*?)["\']', target_functions_decorator)
                                for j in s:
                                    if len(decorator_prefix) > 0:
                                        if j.endswith(api_last_name) and j.startswith(decorator_prefix[0]):
                                            flag = 1
                                            flag2
                                            break
                                if flag2 == 1:
                                    break
                if flag == 1:
                    continue

                # 解决torch.max误报的问题，可以查找__init__.pyi文件中是否有定义。2024-11-20
                new_api_end = new_api.split(".")[-1]
                flag1 = 0
                for xx in s:
                    if xx.endswith(f".{new_api_end}"):
                        if xx in target_api_dict["api_usage"]:
                            flag1 = 1
                            break
                        parts = xx.split(".")
                        xx = '.'.join(parts[1:])
                        #print(xx)
                        if "." in xx:
                            pyi_file_path = target_library_path + slash + transform_and_remove_last_segment(xx) + slash + '__init__.pyi'
                            init_file_path = target_library_path + slash + transform_and_remove_last_segment(xx) + slash + '__init__.py'
                            init_file_path_2 = target_library_path + slash + transform_and_remove_last_segment(transform_and_remove_last_segment(xx)) + slash + '__init__.py'
                        else:
                            pyi_file_path = target_library_path + slash + '__init__.pyi'
                            init_file_path = target_library_path + slash + '__init__.py'
                            init_file_path_2 = target_library_path + slash + '__init__.py'
                        pyi_file_path_2 = target_library_path + slash + '_C' + slash + '__init__.pyi'
                        pyi_file_path_3 = target_library_path + slash + '_C/_VariableFunctions.pyi'
                        pyi_file_path_4 = target_library_path + slash + '__init__.pyi'
                        if os.path.exists(pyi_file_path):
                            function_names = extract_function_defs_from_file(pyi_file_path)
                            import_api_names = paths_of_import_file(pyi_file_path)
                            
                            for ii in import_api_names:
                                if ii.endswith(new_api_end):
                                    flag1 = 1
                                    break
                            if flag1 == 1:
                                break

                            #pyi文件中from import可以改变调用形式，需要进一步处理，已处理2024-12-6
                            if new_api_end in function_names:
                                flag1 = 1
                                break 

                        if os.path.exists(init_file_path):
                            init_import_api_names = paths_of_import_file(init_file_path)
                            for ii in init_import_api_names:
                                if ii.endswith(new_api_end):
                                    flag1 = 1
                                    break
                            if flag1 == 1:
                                break
                        
                        if os.path.exists(init_file_path_2):
                            init_import_api_names = paths_of_import_file(init_file_path_2)
                            for ii in init_import_api_names:
                                if ii.endswith(new_api_end):
                                    flag1 = 1
                                    break
                        if flag1 == 1:  
                            break

                        if os.path.exists(pyi_file_path_2):
                            function_names = extract_function_defs_from_file(pyi_file_path_2)
                            if new_api_end in function_names:
                                flag1 = 1
                                break
                        if os.path.exists(pyi_file_path_3):
                            function_names = extract_function_defs_from_file(pyi_file_path_3)
                            if new_api_end in function_names:
                                flag1 = 1
                                break
                        if os.path.exists(pyi_file_path_4):
                            function_names = extract_function_defs_from_file(pyi_file_path_4)
                            if new_api_end in function_names:
                                flag1 = 1
                                break
                        else:
                            break
                if flag1 == 1:
                    continue

                #解决torch.nn.functional.pad误报问题，可以查找torch.nn.functional.pyi 是否有def pad
                flag1 = 0
                pyi_file_path4 = target_library_path + slash + transform_and_remove_last_segment(new_api) + '.pyi'
                if os.path.exists(pyi_file_path4):
                    function_names = extract_function_defs_from_file(pyi_file_path4)
                    for function_name in function_names:
                        if function_name.endswith(new_api_end):
                            flag1 = 1
                            break
                if flag1 == 1:
                    continue

                #解决匹配错误问题，可能匹配到测试代码中，跳过
                if "testing" in new_api:
                    continue

                # 解决误报的问题，可以查找import中是否有定义
                #解决_tqdm_notebook
                flag = 0            
                api_path = target_library_path + slash + transform_and_remove_last_segment(new_api) + '.py'
                if os.path.exists(api_path):
                    import_api_names = paths_of_import_file(api_path)
                    for x in import_api_names:
                        if x.endswith(new_api.split(".")[-1]):
                            flag = 1
                            break
                    for i in target_api_dict["functions"].keys():
                        if i.endswith(f".{new_api.split('.')[-1]}"):
                            for j in import_api_names:
                                if j.endswith(".*"):
                                    j.replace(".*", "")
                                if j in i:
                                    flag = 1
                                    break
                                if flag == 1:
                                    break
                if flag == 1:
                    continue


                if target_project == proj:
                    logging.info(f"{target_project} is not compatible with {target_library}{target_version}-The {target_library_call_module}.{new_api} is deprecated.")
                else:
                    logging.info(f"{target_project}{target_proj_dependency[target_project]} is not compatible with {target_library}{target_version}-The {target_library_call_module}.{new_api} is deprecated.")
                res = True
                return res
            elif api in deprecated_methods:
                if target_library_call_module + "." + new_api.split(".")[-1] in s:
                    continue
                #解决figure.Figure.colorbar误报问题，因为类Figure继承于FigureBase，而FigureBase中有colorbar方法，所以需要增加基类的判断
                flag1 = 0
                method_last_name = new_api.split(".")[-1] 
                if api.replace(f".{method_last_name}", '') in target_api_dict["classes"].keys():
                    class_definition = extract_lines(target_library_path + slash + transform_and_remove_last_segment(new_api.replace(f".{method_last_name}", '')) + '.py', target_api_dict["classes"][api.replace(f".{method_last_name}", '')]["lineno"])
                else:
                    class_definition = "()"
                #用正则表达式匹配类的基类
                pattern = r'class\s+\w+\s*\(([^)]+)\)'
                match = re.search(pattern, class_definition)
                if match:
                    base_class = match.group(1).strip()
                else:
                    base_class = None
                
                for key in target_api_dict["methods"]:
                    if base_class is not None:
                        if key.endswith(f".{method_last_name}") and base_class in key:
                            flag1 = 1
                            break
                if flag1 == 1:
                    continue

                if target_project == proj:
                    logging.info(f"{target_project} is not compatible with {target_library}{target_version}-The {target_library_call_module}.{new_api} is deprecated.")
                else:
                    logging.info(f"{target_project}{target_proj_dependency[target_project]} is not compatible with {target_library}{target_version}-The {target_library_call_module}.{new_api} is deprecated.")
                res = True
                return res
            elif api in deprecated_global_vars:
                if target_project == proj:
                    logging.info(f"{target_project} is not compatible with {target_library}{target_version}-The {target_library_call_module}.{new_api} is deprecated.")
                else:
                    logging.info(f"{target_project}{target_proj_dependency[target_project]} is not compatible with {target_library}{target_version}-The {target_library_call_module}.{new_api} is deprecated.")
                res = True
                return res 
        
        
        #检测类和函数的装饰器是否改变，即使代码路径没有改变，但是装饰器改变了导致代码不兼容
        if new_api.endswith("__init__") and target_library == 'tensorflow':
            class_api = new_api.replace('.__init__', '')
            start_class_decorator_path = start_library_path + slash + transform_and_remove_last_segment(class_api) + '.py'
            start_class_decorator = extract_lines(start_class_decorator_path, start_api_dict['classes'][f"{target_library_call_module}.{class_api}"]["lineno"]-1)

            target_class_decorator_path = target_library_path + slash + transform_and_remove_last_segment(class_api) + '.py'
            if f"{target_library_call_module}.{class_api}" in target_api_dict["classes"]:
                target_class_decorator = extract_lines(target_class_decorator_path, target_api_dict['classes'][f"{target_library_call_module}.{class_api}"]["lineno"]-1)
            else:
                target_class_decorator = None
            
            if start_class_decorator and start_class_decorator.startswith('@tf_export') and target_class_decorator and target_class_decorator.startswith('@tf_export'):         
                start_matches = re.findall(r'["\'](.*?)["\']', start_class_decorator)
                target_matches = re.findall(r'["\'](.*?)["\']', target_class_decorator)
                if target_matches == start_matches:
                    pass
                elif not bool(set(start_matches).issubset(set(target_matches))) and target_version.startswith("2.") and start_version.startswith("1."):
                    if target_project == proj:
                        logging.info(f"{target_project} is not compatible with {target_library}{target_version}-The {target_library_call_module}.{new_api} is deprecated.")
                    else:
                        logging.info(f"{target_project}{target_proj_dependency[target_project]} is not compatible with {target_library}{target_version}-The {target_library_call_module}.{new_api} is deprecated.")
                    res = True
                    return res
            elif start_class_decorator == "" and target_class_decorator and target_class_decorator.startswith('@tf_export'):
                if "v1=[" in target_class_decorator and target_version.startswith("2.") and start_version.startswith("1."):
                    if target_project == proj:
                        logging.info(f"{target_project} is not compatible with {target_library}{target_version}-The {target_library_call_module}.{new_api} is deprecated.")
                    else:
                        logging.info(f"{target_project}{target_proj_dependency[target_project]} is not compatible with {target_library}{target_version}-The {target_library_call_module}.{new_api} is deprecated.")
                    res = True
                    return res
            #print(target_class_decorator)
        elif target_library == 'tensorflow':
            start_function_decorator_path = target_library_path + slash +transform_and_remove_last_segment(new_api) + '.py'
            try:
                start_function_decorator = extract_lines(start_function_decorator_path, start_api_dict['functions'][api]["lineno"]-1)
            except:
                continue

            target_function_decorator_path = target_library_path + slash +transform_and_remove_last_segment(new_api) + '.py'
            try:
                target_function_decorator = extract_lines(target_function_decorator_path, target_api_dict['functions'][api]["lineno"]-1)
            except:
                continue
            
            if start_function_decorator and start_function_decorator.startswith('@tf_export') and target_function_decorator and target_function_decorator.startswith('@tf_export'):   
                start_matches = re.findall(r'["\'](.*?)["\']', start_function_decorator)
                target_matches = re.findall(r'["\'](.*?)["\']', target_function_decorator)
                #print(start_matches)
                #print(target_matches)
                if target_matches == start_matches:
                    pass
                elif not bool(set(start_matches).issubset(set(target_matches))) and target_version.startswith("2.") and start_version.startswith("1."):
                    logging.info(f"{target_project}-{target_library}-{start_version}-{target_version}（装饰器改变）{new_api}-{start_function_decorator}-{target_function_decorator}")
                    res = True
                    return res
            elif start_function_decorator == "" and target_function_decorator and target_function_decorator.startswith('@tf_export'):
                if "v1=[" in target_function_decorator and target_version.startswith("2.") and start_version.startswith("1."):
                    logging.info(f"{target_project}-{target_library}-{start_version}-{target_version}（装饰器改变）{new_api}-{start_function_decorator}-{target_function_decorator}")
                    res = True
                    return res
        
        
        #参数兼容性检查
        #if new_api in start_api_param_dict and new_api in target_api_param_dict and not new_api.endswith("__init__"):
        if api in start_api_dict['functions'] and api in target_api_dict['functions']:
            #print(new_api)
            start_param = start_api_dict['functions'][api]['parameter']
            target_param = target_api_dict['functions'][api]['parameter']
            
            result = None
            if api in target_api_dict['functions']:
                #print("***********************")
                if os.path.exists(f"{target_library_path}{slash}{transform_and_remove_last_segment(new_api)}.py"):
                    result = extract_lines(f"{target_library_path}{slash}{transform_and_remove_last_segment(new_api)}.py", target_api_dict['functions'][api]["lineno"]-1)
                else:
                    result = None
            if result is not None and result.startswith('@parse_args'):
                parse_args = re.findall(r'["\']([^"\']*)["\']', result)
                #print(parse_args)
            else:
                parse_args = []
            
            try:
                if new_api.endswith("__init__") or new_api.endswith("__default_init__"):
                    actual_usage = api_paras_map[new_api.split('.')[-2]]
                else:
                    actual_usage = api_paras_map[new_api.split('.')[-1]]
            except:
                actual_usage = "()"
            if actual_usage != "()":
                actual_usage = extract_inner_parentheses(actual_usage)
            if not analyzeCompatibility(start_param, target_param, actual_usage, parse_args):
                if target_project == proj:
                    logging.info(f"{target_project} is not compatible with {target_library}{target_version}--（参数不兼容）{new_api}")
                else:
                    logging.info(f"{target_project}{target_proj_dependency[target_project]} is not compatible with {target_library}{target_version}--（参数不兼容）{new_api}")
                res = True
                return res
           
        
        '''
        #检测API的实现代码是否发生变更
        if new_api.endswith("__init__") or new_api.endswith("__default_init__"):
            if new_api.endswith("__default_init__"):
                continue
            start_class_path =  start_library_path + slash + transform_and_remove_last_segment(transform_and_remove_last_segment(new_api)) + '.py'
            target_class_path =  target_library_path + slash + transform_and_remove_last_segment(transform_and_remove_last_segment(new_api)) + '.py'
            start_class_code_exception = extract_code_info(start_class_path, start_api_line['methods'][new_api][0]+1, start_api_line['methods'][new_api][1])
            target_class_code_exception = extract_code_info(target_class_path, target_api_line['methods'][new_api][0]+1, target_api_line['methods'][new_api][1])
            for e in target_class_code_exception:
                if e not in start_class_code_exception:
                    if target_project == proj:
                        print(f"{target_project}-{target_library}-{start_version}-{target_version}（抛出不同的异常）{new_api}")
                    else:
                        print(f"{target_project}{target_proj_dependency[target_project]}-{target_library}-{start_version}-{target_version}（抛出不同的异常）{new_api}")
                    res = True
                    return res
        else:
            start_function_path =  start_library_path + slash + transform_and_remove_last_segment(new_api) + '.py'
            target_function_path =  target_library_path + slash + transform_and_remove_last_segment(new_api) + '.py'
            try:
                start_function_code_exception = extract_code_info(start_function_path, start_api_line['functions'][new_api][0]+1, start_api_line['functions'][new_api][1])
                target_function_code_exception = extract_code_info(target_function_path, target_api_line['functions'][new_api][0]+1, target_api_line['functions'][new_api][1])
            except KeyError:
                start_function_path =  start_library_path + slash + transform_and_remove_last_segment(transform_and_remove_last_segment(new_api)) + '.py'
                target_function_path =  target_library_path + slash + transform_and_remove_last_segment(transform_and_remove_last_segment(new_api)) + '.py'
                start_function_code_exception = extract_code_info(start_function_path, start_api_line['methods'][new_api][0]+1, start_api_line['methods'][new_api][1])
                target_function_code_exception = extract_code_info(target_function_path, target_api_line['methods'][new_api][0]+1, target_api_line['methods'][new_api][1])
            for e in target_function_code_exception:
                if e not in start_function_code_exception:
                    if target_project == proj:
                        print(f"{target_project}-{target_library}-{start_version}-{target_version}（抛出不同的异常）{new_api}")
                    else:
                        print(f"{target_project}{target_proj_dependency[target_project]}-{target_library}-{start_version}-{target_version}（抛出不同的异常）{new_api}")
                    print(e)
                    res = True
                    return res
        '''
    if target_project == proj:
        logging.info(f"{target_project} is compatible with {target_library}{target_version}")
    else:
        logging.info(f"{target_project}{target_proj_dependency[target_project]} is compatible with {target_library}{target_version}")
        
    return res