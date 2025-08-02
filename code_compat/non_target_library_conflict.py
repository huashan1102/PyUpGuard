from .target_library_conflict import is_target_library_code_conflict
from extraction.import_to_path import get_paths_of_import
from call_graph.get_FDG import get_library_dependency_from_metadata
from utils.util import get_library_call_module
import requests, os, json, re, time

library_path_prefix = ""
constraint_path_prefix = ""
version_path_prefix = ""
api_path_prefix = ""

def setup_path_3(library_path_prefix_pass, constraint_path_prefix_pass, version_path_prefix_pass, api_path_prefix_pass):
    global library_path_prefix, constraint_path_prefix, version_path_prefix, api_path_prefix
    library_path_prefix = library_path_prefix_pass
    constraint_path_prefix = constraint_path_prefix_pass
    version_path_prefix = version_path_prefix_pass
    api_path_prefix = api_path_prefix_pass

def get_libraries_depending_on_targetlibrary(proj_dependency, target_library, python_version):
    '''
    target_library=a
    b依赖与a
    return b
    '''
    res = []
    
    for dependency_library in proj_dependency:
        #print(proj_dependency)
        library_list = get_library_dependency_from_metadata(dependency_library, proj_dependency[dependency_library], python_version)
        #print(dependency_library, library_list)
        if target_library in library_list:
            #print(dependency_library)
            res.append(dependency_library)
    #print(res)
    return res
    #print(target_proj_dependency)

def is_library_used(project_path, library_name):
    """
    检查Python项目中是否调用了某个第三方库。

    :param project_path: Python项目的根目录
    :param library_name: 需要检查的第三方库名称
    :return: 如果项目中调用了该库，返回True，否则返回False
    """
    
    # 匹配 import xxx 和 from xxx import xxx 的正则表达式
    import_pattern = re.compile(r'^\s*(import|from)\s+(' + re.escape(library_name) + r')\b')
    #print(import_pattern)    
    # 遍历项目目录中的所有.py文件
    for root, dirs, files in os.walk(project_path):
        for file in files:
            if file.endswith(".py"):
                file_path = os.path.join(root, file)
                with open(file_path, 'r', encoding='utf-8') as f:
                    for line in f:
                        if import_pattern.search(line):
                            return True  # 找到库的引用，立即返回True
                            
    return False  # 如果遍历完所有文件未找到，返回False


def update_compatibility_info(library, target_library, library_version, target_library_start_version, target_library_target_version, start_library_path, target_library_path, target_library_call_module, compatibility_info, target_project, proj_path, target_proj_dependency, python_version):
    if tuple(sorted([(library, library_version), (target_library, target_library_target_version)])) in compatibility_info.keys():
        return compatibility_info
    else:
        if library == target_project:
            is_target_library_conflict = is_target_library_code_conflict(proj_path, target_project, target_library, target_library_start_version, target_library_target_version, start_library_path, target_library_path, target_library_call_module, target_project, proj_path, target_proj_dependency, python_version)
            if is_target_library_conflict:
                #key = tuple(sorted([(target_project, "1"), (target_library, target_library_target_version)]))
                compatibility_info[tuple(sorted([(target_project, "1"), (target_library, target_library_target_version)]))] = False
            else:
                compatibility_info[tuple(sorted([(target_project, "1"), (target_library, target_library_target_version)]))] = True
        else:
            new_target_library_call_module = get_library_call_module(library)
            
            new_proj_path = library_path_prefix + library + '/' + library + library_version + '/' + new_target_library_call_module
            new_target_proj_dependency = target_proj_dependency.copy()
            new_target_proj_dependency[library] = library_version
            is_conflict = is_target_library_code_conflict(new_proj_path, library, target_library, target_library_start_version, target_library_target_version, start_library_path, target_library_path, target_library_call_module, target_project, proj_path, new_target_proj_dependency, python_version)
            if is_conflict:
                compatibility_info[tuple(sorted([(library, library_version), (target_library, target_library_target_version)]))] = False
            else:
                compatibility_info[tuple(sorted([(library, library_version), (target_library, target_library_target_version)]))] = True

    return compatibility_info

def is_non_target_library_code_conflict(target_proj_dependency, proj_path, target_project, target_library, start_version, target_version, start_library_path, target_library_path, target_library_call_module, compatibility_info, python_version):
    
    #print(target_proj_dependency)
    libraries_depending_on_targetlibrary = get_libraries_depending_on_targetlibrary(target_proj_dependency, target_library, python_version) #得到目标库的下游项目
    #print(libraries_depending_on_targetlibrary)
    # 目标项目为library
    # 目标库为target_library
    for library in libraries_depending_on_targetlibrary:
        new_target_library_call_module = get_library_call_module(library)
        
        if not is_library_used(proj_path, new_target_library_call_module):    #如果项目没有使用library则跳过
            #print(proj_path)
            continue
        new_proj_path = library_path_prefix + library + '/' + library + target_proj_dependency[library] + '/' + new_target_library_call_module
        #print(library)
        #start = time.time()
        key1 = tuple(sorted([(library, target_proj_dependency[library]), (target_library, target_version)]))
        #print(compatibility_info)
        if key1 not in compatibility_info.keys():
            #print(key)
            is_conflict = is_target_library_code_conflict(new_proj_path, library, target_library, start_version, target_version, start_library_path, target_library_path, target_library_call_module, target_project, proj_path, target_proj_dependency, python_version)
            if is_conflict:
                compatibility_info[key1] = False
                #continue
            else:
                compatibility_info[key1] = True
                #return library, compatibility_info
        
        if compatibility_info[key1]:
            continue
        else:
            return library, compatibility_info

    return None, compatibility_info
    