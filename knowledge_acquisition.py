from utils.util import *
from extraction.getCall import get_all_used_api
from extraction.lib_module_and_package_extraction import *
from extraction.library_api_and_module import *
from call_graph.get_FDG import * 
import platform, argparse, os, json, time, requests, logging, subprocess
from packaging.specifiers import SpecifierSet
from packaging.version import parse as parse_version
import requests
import tarfile
import zipfile
import os
from packaging import version
from typing import Optional
import shutil
import threading
from multiprocessing import Pool, cpu_count


if (platform.system() == 'Windows'):
    slash = "\\"
else:
    slash = r"/"

library_path_prefix = ""
constraint_path_prefix = ""
version_path_prefix = ""
api_path_prefix = ""

def setup_path(library_path_prefix_pass, constraint_path_prefix_pass, version_path_prefix_pass, api_path_prefix_pass):
    global library_path_prefix, constraint_path_prefix, version_path_prefix, api_path_prefix
    library_path_prefix = library_path_prefix_pass
    constraint_path_prefix = constraint_path_prefix_pass
    version_path_prefix = version_path_prefix_pass
    api_path_prefix = api_path_prefix_pass
    setup_path_1(library_path_prefix, constraint_path_prefix, version_path_prefix, api_path_prefix)
def load_config(config_path):
    # config文件是一个JSON格式文件
    with open(f"./configure/{config_path}", 'r') as file:
        config = json.load(file)
    return config

def get_proj_dependency_from_requirements(file_path):
    requirements_dict = {}
    with open(file_path, 'r') as file:
        for line in file:
            # 移除行首行尾的空格和换行符
            line = line.strip()
            # 如果行不是空行并且不是注释
            if line and not line.startswith('#') and '@' not in line:
                # 按照 '==' 分割包名和版本号
                package, version = line.split('==')
                # 将包名和版本号添加到字典中
                requirements_dict[package.lower()] = version
    return requirements_dict

def get_available_version(FDG, sub_graph, python_version, target_proj_dependency, target_library, target_version):
    target_library_constraint = get_library_constraint_from_metadata(target_library, target_version, python_version)
    available_versions1 = {}
    available_versions2 = {}
    available_versions = {}
    target_library_dependency = FDG[target_library]        #得到目标库的上游项目，即目标库所依赖其他第三方库                                                  
    available_versions[target_library] = []
    available_versions[target_library].append(target_version)
    with open(f"{version_path_prefix}library_version.json", 'r') as file:
        version_ls = json.load(file)
    for proj_dependency in sub_graph:
        #print(proj_dependency)
        flag = False
        if proj_dependency not in target_proj_dependency:
            continue
        condidate_version = []
        if proj_dependency not in target_library_dependency:
            try:
                condidate_version = version_ls[proj_dependency.lower()][python_version]
            except:
                print(proj_dependency.lower())
            #print(proj_dependency)
            if len(condidate_version) >= 150:
                condidate_version = condidate_version[-150:]
            elif len(condidate_version) >= 10:
                condidate_version = condidate_version[-10:]

            if target_proj_dependency[proj_dependency] in condidate_version:  #将起始requirements.txt中的约束版本放在第一个，模拟pip安装
                condidate_version.remove(target_proj_dependency[proj_dependency])
                condidate_version.append(target_proj_dependency[proj_dependency])
                flag = True
            else:
                condidate_version.append(target_proj_dependency[proj_dependency])
                flag = True
            pass
            #condidate_version.append(target_proj_dependency[proj_dependency])
        else:
            try:
                for version in version_ls[proj_dependency][python_version]:
                    try:                    #在目标库起始版本的约束中，但是不在目标版本的约束中
                        if is_version_compat(version, target_library_constraint[proj_dependency]):
                            condidate_version.append(version)
                    except:
                        condidate_version = version_ls[proj_dependency][python_version]
                        break
            except:
                print(proj_dependency)
            if target_proj_dependency[proj_dependency] in condidate_version:  #将起始requirements.txt中的约束版本放在第一个，模拟pip安装
                condidate_version.remove(target_proj_dependency[proj_dependency])
                condidate_version.append(target_proj_dependency[proj_dependency])
                flag = True
        if flag:
            available_versions1[proj_dependency] = condidate_version
        else:
            available_versions2[proj_dependency] = condidate_version
    sorted_available_versions1 = dict(sorted(available_versions1.items(), key=lambda item: len(item[1])))
    #print(sorted_available_versions1)
    sorted_available_versions2 = dict(sorted(available_versions2.items(), key=lambda item: len(item[1])))
    for i in sorted_available_versions1:
        available_versions[i] = sorted_available_versions1[i]
    for i in sorted_available_versions2:
        if i not in available_versions:
            available_versions[i] = sorted_available_versions2[i]
    return available_versions

def filter_versions(version_list):
    return [v for v in version_list if not re.search(r'[a-zA-Z]', v)]

def get_compatible_versions(package_name, python_version):
    url = f"https://pypi.org/pypi/{package_name}/json"
    response = requests.get(url).json()
    compatible_versions = []
    new_python_version = python_version.replace(".", "")
    
    for version, files in response["releases"].items():
        for file_info in files:
            if file_info.get("python_version"):
                #print(file_info["python_version"])
                try:
                    if file_info["python_version"] == f"cp{new_python_version}":
                        compatible_versions.append(version)
                        break
                    elif file_info["python_version"] != None and f"py{python_version.split('.')[0]}" in file_info["python_version"]:
                        if "=" in file_info["requires_python"] or ">" in file_info["requires_python"] or "<" in file_info["requires_python"]:
                            if SpecifierSet(file_info["requires_python"]).contains(python_version):
                                compatible_versions.append(version)
                                break
                    elif file_info["requires_python"] == None:
                        compatible_versions.append(version)
                        break
                    elif SpecifierSet(file_info["requires_python"]).contains(python_version):
                        compatible_versions.append(version)
                        break
                except:
                    pass
    compatible_versions = filter_versions(compatible_versions)
    compatible_versions.sort(key=parse_version)
    if package_name == "torchvision" and "0.11.0" in compatible_versions:
        compatible_versions.remove("0.11.0")
    if package_name == "python-dateutil" and compatible_versions[-1] == "2.9.0":
        compatible_versions.append("2.9.0.post0")
    return compatible_versions

def download_pypi_source(package_name, version = None, python_version = "3.7", output_dir = "."):
    python_dict = {"2.7": "py27", "3.4": "py34", "3.5": "py35", "3.6": "py36", "3.7": "py37", "3.8": "py38", "3.9": "py39", "3.10": "py310", "3.11": "py311"}
    env_name = python_dict[python_version]
    command = f"bash -c 'source /home/lei/anaconda3/bin/activate {env_name} && pip install {package_name}=={version} --no-deps --target=\"{library_path_prefix}{package_name}/{package_name}{version}\"'"
    try:
        subprocess.run(command, shell=True, check=True)
    except:
        pass

def extract_fine_grained_knowledge(lib, version):  
    library_call_module = get_library_call_module(lib)
    library_path = f"{library_path_prefix}{lib}/{lib}{version}/{library_call_module}"
    res = extract_from_directory(library_path)
    print("********************")
    dir = get_python_modules_and_packages_from_dir(library_path, library_call_module)
    init_dir = get_python_modules_and_packages_from_init(library_path, library_call_module)
    dir.update(init_dir)
    res["modules"] = list(dir)
    try:
        api_usage_in_target_library, _1, __2, _3  = get_all_used_api(library_path, library_call_module)
    except:
        api_usage_in_target_library = []
    res["api_usage"] = list(api_usage_in_target_library)       
    funcs = res["functions"]
    new_funcs = shortenPath(funcs, lib, version)
    res["functions"] = new_funcs
    classes = res["classes"]
    new_classes = shortenPath(classes, lib, version)
    res["classes"] = new_classes
    with open(f"{api_path_prefix}{lib}/{version}.json", "w") as f:
        json.dump(res, f)

def task(args):
    lib, version = args
    #print(f"Extracting Knowledge-{lib}-{version}")
    extract_fine_grained_knowledge(lib, version)

    

if __name__ == '__main__':
    start = time.time()

    # 创建ArgumentParser对象
    parser = argparse.ArgumentParser(description="命令行工具示例")
    # 添加--config参数，指定config文件路径
    parser.add_argument('--config', type=str, required=True, help="配置文件路径")
    # 解析命令行参数
    args = parser.parse_args()
    # 获取config文件路径
    config_path = args.config

    # 加载并处理config文件
    config = load_config(config_path)
    
    proj_path = config["projPath"]
    target_project = proj_path.split("/")[-1]
    target_library = config["targetLibrary"]
    start_version = config["startVersion"]
    target_version = config["targetVersion"]
    python_version = config["pythonVersion"]
    start_requirements_path = config["requirementsPath"]
    knowledge_path = config["knowledgePath"]
    library_path_prefix = f"{knowledge_path}libraries/"
    constraint_path_prefix = f"{knowledge_path}version_constraint/"
    version_path_prefix = f"{knowledge_path}"
    api_path_prefix = f"{knowledge_path}library_api/"
    setup_path(library_path_prefix, constraint_path_prefix, version_path_prefix, api_path_prefix)

   
    fake_start_proj_dependency = get_proj_dependency_from_requirements(start_requirements_path)
    start_proj_dependency = {}
    for i in fake_start_proj_dependency:
        if fake_start_proj_dependency[i] == "0.0.0" or fake_start_proj_dependency[i] == "0.0" or fake_start_proj_dependency[i] == "0":
            pass
        else:
            start_proj_dependency[i] = fake_start_proj_dependency[i]
    
    target_proj_dependency = start_proj_dependency.copy()
    target_proj_dependency[target_library] = target_version
    FDG = get_FDG_from_requirements(target_proj_dependency, python_version)
    sub_graph = get_sub_graph(FDG, target_library)
    #获取所有的候选版本
    for i in sub_graph:
        library_call_module = get_library_call_module(i)
        compatible_versions = get_compatible_versions(i, python_version)
        #print(compatible_versions)
        for j in compatible_versions:
            if not os.path.exists(f"{constraint_path_prefix}{i}/{i}{j}/{i}.json"):
                download_from_data(i, j)
            if not os.path.exists(f"{library_path_prefix}{i}/{i}{j}"):
                print(f"Downloading {i}{j}")
                os.makedirs(f"{library_path_prefix}{i}/{i}{j}")
                download_pypi_source(i, j, python_version, output_dir = f"{library_path_prefix}{i}/{i}{j}")
        if not os.path.exists(f"{version_path_prefix}library_version.json"):
            data = {}
        else:
            with open(f"{version_path_prefix}library_version.json", "r") as f:
                data = json.load(f)
        if i not in data:
            data[i] = {}
        if python_version not in data[i]:
            data[i][python_version] = compatible_versions
            with open(f"{version_path_prefix}library_version.json", "w") as f:
                json.dump(data, f)
    
    available_version = get_available_version(FDG, sub_graph, python_version, target_proj_dependency, target_library, target_version)
    available_version[target_library].append(start_version)
    #print(available_version)
    
    all_library = []
    for i in sub_graph:
        #print(i)
        if i not in all_library and i in target_proj_dependency.keys():
            all_library.append(i)
    #print(all_library)
    for lib in all_library:
        if not os.path.exists(f"{api_path_prefix}{lib}/"):
            os.makedirs(f"{api_path_prefix}{lib}/")
    tasks = []
    for lib in all_library:
        for version in available_version[lib]:
            if not os.path.exists(f"{api_path_prefix}{lib}/{version}.json"):
                print(f"Extracting Knowledge-{lib}-{version}")
                tasks.append((lib, version))
    #print(tasks)
    with Pool(processes=min(20, cpu_count())) as pool:
        pool.map(task, tasks)


        
            


    
    