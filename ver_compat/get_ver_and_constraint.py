from call_graph.get_FDG import *
from extraction.import_to_path import *
from utils.util import *

library_path_prefix = ""
constraint_path_prefix = ""
version_path_prefix = ""
api_path_prefix = ""

def setup_path_4(library_path_prefix_pass, constraint_path_prefix_pass, version_path_prefix_pass, api_path_prefix_pass):
    global library_path_prefix, constraint_path_prefix, version_path_prefix, api_path_prefix
    library_path_prefix = library_path_prefix_pass
    constraint_path_prefix = constraint_path_prefix_pass
    version_path_prefix = version_path_prefix_pass
    api_path_prefix = api_path_prefix_pass
def get_available_version(FDG, sub_graph, python_version, target_proj_dependency, target_library, target_version):
    target_library_constraint = get_library_constraint_from_metadata(target_library, target_version, python_version)
    #print(target_library_constraint)
    target_library_constraint = {k.lower(): v for k, v in target_library_constraint.items()}
    available_versions1 = {}
    available_versions2 = {}
    available_versions = {}
    target_library_dependency = FDG[target_library]        #得到目标库的上游项目，即目标库所依赖其他第三方库   
    #print(target_library_dependency)                                               
    available_versions[target_library] = []
    available_versions[target_library].append(target_version)
    with open(f"{version_path_prefix}/library_version.json", 'r') as file:
        version_ls = json.load(file)
    for proj_dependency in sub_graph:
        #print(proj_dependency)
        flag = False
        if proj_dependency == target_library:
            continue
        if proj_dependency not in target_proj_dependency:
            continue
        condidate_version = []
        if proj_dependency not in target_library_dependency:
            try:
                condidate_version = version_ls[proj_dependency.lower()][python_version]
            except:
                print(proj_dependency.lower())
            #print(proj_dependency)
            if len(condidate_version) >= 30 and proj_dependency != "google-auth":
                #print(proj_dependency)
                condidate_version = condidate_version[-30:]
    
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
            #print(proj_dependency, condidate_version)
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
    #print(available_versions)
    return available_versions

def get_compatibility_dict(available_versions, python_version):
    compatibility_dict = {}
    with open(f"{version_path_prefix}/library_version.json", 'r') as file:
        version_ls = json.load(file)
    for library in available_versions:
        res ={}
        for version in available_versions[library]:
            a = []
            constraint = get_library_constraint_from_metadata(library, version, python_version)
            if not constraint:
                #print(library)
                res[version] = a
            else:
                for l in constraint:
                    #print(f"{library}-{version}, {l}, {constraint[l]}")
                    if l in available_versions.keys():                        
                        if constraint[l] is not None and constraint[l] != "none":
                            for v in version_ls[l][python_version]:
                                if is_version_compat(v, constraint[l]):
                                    a.append(l+'#'+v)
                        else:
                            #a[l] = version_ls[l][python_version]
                            for v in version_ls[l][python_version]:
                                #if l in available_versions.keys() and v in available_versions[l]:
                                a.append(l+'#'+v)
                                    
                res[version] = a
            
            #print(res)
            compatibility_dict[library] = res

    return compatibility_dict

def get_new_lib(target_proj_dependency, python_version):
    new_lib_and_available_version = {}
    for library in target_proj_dependency:
        constraint = get_library_constraint_from_metadata(library, target_proj_dependency[library], python_version)
        #print(constraint)
        for l in constraint:
            if l not in target_proj_dependency.keys() and l not in new_lib_and_available_version.keys():
                with open(f"{version_path_prefix}/library_version.json", 'r') as file:
                    version_ls = json.load(file)
                tmp = []
                try:
                    flag = False
                    for v in version_ls[l][python_version]:
                        if constraint[l] is not None and (">" in constraint[l] or "~" in constraint[l]):
                            if is_version_compat(v, constraint[l]):
                                tmp.append(v)
                        else:
                            flag = True
                            tmp.append(v)
                except:
                    continue
                if flag == False:
                    tmp = list(reversed(tmp)) 
                new_lib_and_available_version[l] = tmp
    if "keras-nightly" in new_lib_and_available_version.keys():
        new_lib_and_available_version.pop("keras-nightly")
    return new_lib_and_available_version

def remove_redundant_dependencies(end_target_proj_dependency, target_library, start_version, target_version, python_version, proj_path):
    #print(target_version)
    all_used_library = get_paths_of_import(proj_path)
    library_call_module = get_library_call_module(target_library)
    library_path = library_path_prefix + target_library + slash + target_library + target_version + slash + library_call_module
    all_used_library2 = get_paths_of_import(library_path)
    new_target_proj_dependency = {}
    redundant_dependencies = []
    start_dependencies = get_library_constraint_from_metadata(target_library, start_version, python_version)
    #print(start_dependencies)
    target_dependencies = get_library_constraint_from_metadata(target_library, target_version, python_version)
    for library in start_dependencies.keys():
        if library not in target_dependencies.keys():
            flag = False
            for i in all_used_library:
                if library in i:
                    flag = True
                    break
            if not flag:
                for i in all_used_library2:
                    if library in i:
                        flag = True
                        break
            if not flag:
                redundant_dependencies.append(library)
    for library in end_target_proj_dependency:
        if library not in redundant_dependencies:
            new_target_proj_dependency[library] = end_target_proj_dependency[library]

    return new_target_proj_dependency