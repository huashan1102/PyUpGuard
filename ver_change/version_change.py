from utils.util import *
from code_compat.target_library_conflict import *
from code_compat.non_target_library_conflict import *
from utils.util import *
from ver_compat.get_ver_and_constraint import *
from ver_compat.constraint_solver import solving_constraints

if (platform.system() == 'Windows'):
    slash = "\\"
else:
    slash = r"/" 

library_path_prefix = ""
constraint_path_prefix = ""
version_path_prefix = ""
api_path_prefix = ""

def setup_path_5(library_path_prefix_pass, constraint_path_prefix_pass, version_path_prefix_pass, api_path_prefix_pass):
    global library_path_prefix, constraint_path_prefix, version_path_prefix, api_path_prefix
    library_path_prefix = library_path_prefix_pass
    constraint_path_prefix = constraint_path_prefix_pass
    version_path_prefix = version_path_prefix_pass
    api_path_prefix = api_path_prefix_pass
def resolve_conflict(start_proj_dependency, target_proj_dependency, sub_graph, compatibility_info, proj_path, target_project, target_library, python_version, FDG):
    flag = False

    for library in start_proj_dependency:
        if start_proj_dependency[library] != target_proj_dependency[library]:
            #print(start_proj_dependency, target_proj_dependency)
            library_call_module = get_library_call_module(library)
            
            start_path = library_path_prefix + library + slash + library + start_proj_dependency[library] + slash + library_call_module
            #print(start_path)
            target_path = library_path_prefix + library + slash + library + target_proj_dependency[library] + slash + library_call_module
            #print(target_path)
            #获得与library冲突的库conflict_library
            conflict_library, compatibility_info = is_non_target_library_code_conflict(target_proj_dependency, proj_path, target_project, library, start_proj_dependency[library], target_proj_dependency[library], start_path, target_path, library_call_module, compatibility_info, python_version)
            #print(conflict_library)
            # 检查发生版本变更的库，在版本变更后是否与项目兼容
            if conflict_library is None:
                compatibility_info = update_compatibility_info(target_project, library, "1",start_proj_dependency[library], target_proj_dependency[library], start_path, target_path, library_call_module, compatibility_info, target_project, proj_path, target_proj_dependency, python_version)
                if not compatibility_info[tuple(sorted([(target_project, "1"), (library, target_proj_dependency[library])]))]:
                    available_versions = get_available_version(FDG, sub_graph, python_version, target_proj_dependency, target_library, target_proj_dependency[target_library])
                    #print(available_versions)

                    library_candi_version = available_versions[library]
                    candi_versions = []
                    #将候选版本重新排序，越靠近原始版本和新的优先级更高
                    for i in library_candi_version:
                        if compare_version(i, target_proj_dependency[library]):
                            candi_versions.append(i)
                    for i in reversed(library_candi_version):
                        if not compare_version(i, target_proj_dependency[library]):
                            candi_versions.append(i)
                    
                    for candi_ver in candi_versions:
                        #compatibility_info = update_compatibility_info(target_project, library, candi_ver, start_proj_dependency[library], target_proj_dependency[library], start_path, target_path, library_call_module, compatibility_info, target_project, proj_path, target_proj_dependency)
                        library_target_path = library_path_prefix + library + slash + library + candi_ver + slash + library_call_module
                        compatibility_info = update_compatibility_info(target_project, library, "1", start_proj_dependency[library], candi_ver, start_path, library_target_path, library_call_module, compatibility_info, target_project, proj_path, target_proj_dependency, python_version)
                        if compatibility_info[tuple(sorted([(target_project, "1"), (library, candi_ver)]))]:
                            new_available_versions = available_versions.copy()
                            new_available_versions[library] = []
                            new_available_versions[library].append(candi_ver)
                            compatibility_dict = get_compatibility_dict(new_available_versions, python_version)
                            #print()

                            res = solving_constraints(compatibility_dict, new_available_versions)
                            #print(res)
                            if res is None:
                                continue
                            #更新requirements
                            for i in res:
                                if res[i] != target_proj_dependency[i]:
                                    flag = True
                                    target_proj_dependency[i] = res[i]
                            break
            elif conflict_library is not None:
                if library == target_library:   #torchvision与pillow存在冲突，且pillow为目标库，则修改torchvision的版本
                    conflict_library_call_module = get_library_call_module(conflict_library)
                    
                    conflict_start_path = library_path_prefix + conflict_library + slash + conflict_library + start_proj_dependency[conflict_library] + slash + conflict_library_call_module
                    conflict_target_path = library_path_prefix + conflict_library + slash + conflict_library + target_proj_dependency[conflict_library] + slash + conflict_library_call_module

                    available_versions = get_available_version(FDG, sub_graph, python_version, target_proj_dependency, library, target_proj_dependency[library])

                    conflict_library_candi_version = available_versions[conflict_library]
                    candi_versions = []
                    #将候选版本重新排序，越靠近原始版本和新的优先级更高
                    for i in conflict_library_candi_version:
                        if compare_version(i, target_proj_dependency[conflict_library]):
                            candi_versions.append(i)
                    for i in reversed(conflict_library_candi_version):
                        if not compare_version(i, target_proj_dependency[conflict_library]):
                            candi_versions.append(i)

                    for candi_ver in candi_versions:
                        compatibility_info = update_compatibility_info(conflict_library, library, candi_ver, start_proj_dependency[library], target_proj_dependency[library], start_path, target_path, library_call_module, compatibility_info, target_project, proj_path, target_proj_dependency, python_version)
                        compatibility_info = update_compatibility_info(target_project, conflict_library, "1", target_proj_dependency[conflict_library], candi_ver, conflict_start_path, conflict_target_path, conflict_library_call_module, compatibility_info, target_project, proj_path, target_proj_dependency, python_version)

                        if compatibility_info[tuple(sorted([(conflict_library, candi_ver), (library, target_proj_dependency[library])]))] and compatibility_info[tuple(sorted([(target_project, "1"), (conflict_library, candi_ver)]))]:
                            new_available_versions = available_versions.copy()
                            new_available_versions[conflict_library] = []
                            new_available_versions[conflict_library].append(candi_ver)
                            compatibility_dict = get_compatibility_dict(new_available_versions, python_version)

                            res = solving_constraints(compatibility_dict, new_available_versions)
                            #print(res)
                            #更新requirements
                            for i in res:
                                if res[i] != target_proj_dependency[i]:
                                    flag = True
                                    target_proj_dependency[i] = res[i]
                            break
                else:     #torchvision与pillow存在冲突，且pillow为非目标库，则先修改pillow的版本，如果修改pillow的版本不可行再修改torchvision
                    available_versions = get_available_version(FDG, sub_graph, python_version, target_proj_dependency, target_library, target_proj_dependency[target_library])
                    #print(available_versions)

                    library_candi_version = available_versions[library]
                    candi_versions = []
                    #将候选版本重新排序，越靠近原始版本和新的优先级更高
                    for i in library_candi_version:
                        if compare_version(i, target_proj_dependency[library]):
                            candi_versions.append(i)
                    for i in reversed(library_candi_version):
                        if not compare_version(i, target_proj_dependency[library]):
                            candi_versions.append(i)

                    # 提取项目依赖中所有依赖于pillow且项目实际调用的库，例如（matplotlib, torchvision）
                    tpls_depend_on_library = get_libraries_depending_on_targetlibrary(target_proj_dependency, library, python_version)

                    for candi_ver in candi_versions:
                        library_target_path = library_path_prefix + library + slash + library + candi_ver + slash + library_call_module
                        #print(f"{library}-{candi_ver}")
                        is_all_compat = True
                        for tpl in tpls_depend_on_library:
                            compatibility_info = update_compatibility_info(tpl, library, target_proj_dependency[tpl], start_proj_dependency[library], candi_ver, start_path, library_target_path, library_call_module, compatibility_info, target_project, proj_path, target_proj_dependency, python_version)
                            if not compatibility_info[tuple(sorted([(tpl, target_proj_dependency[tpl]), (library, candi_ver)]))]:
                                is_all_compat = False
                                break
                        if is_all_compat:
                            compatibility_info = update_compatibility_info(target_project, library, "1", target_proj_dependency[library], candi_ver, start_path, library_target_path, library_call_module, compatibility_info, target_project, proj_path, target_proj_dependency, python_version)
                            #is_all_compat = True
                            if not compatibility_info[tuple(sorted([(target_project, "1"), (library, candi_ver)]))]:
                                is_all_compat = False

                        if is_all_compat:
                            new_available_versions = available_versions.copy()
                            new_available_versions[library] = []
                            new_available_versions[library].append(candi_ver)
                            compatibility_dict = get_compatibility_dict(new_available_versions, python_version)
                            #print()

                            res = solving_constraints(compatibility_dict, new_available_versions)
                            #print(res)
                            if res is None:
                                continue
                            #更新requirements
                            for i in res:
                                if res[i] != target_proj_dependency[i]:
                                    flag = True
                                    target_proj_dependency[i] = res[i]
                            break
                    
                    if flag == False:   #目标库为matplotlib，检测到torchvision与Pillow存在冲突。修改pillow的版本不可解，修改torchvision的版本
                        conflict_library_call_module = get_library_call_module(conflict_library)
                        
                        conflict_start_path = library_path_prefix + conflict_library + slash + conflict_library + start_proj_dependency[conflict_library] + slash + conflict_library_call_module
                        conflict_target_path = library_path_prefix + conflict_library + slash + conflict_library + target_proj_dependency[conflict_library] + slash + conflict_library_call_module

                        available_versions = get_available_version(FDG, sub_graph, python_version, target_proj_dependency, target_library, target_proj_dependency[target_library])
                        #print(available_versions)

                        conflict_library_candi_version = available_versions[conflict_library]
                        candi_versions = []
                        #将候选版本重新排序，越靠近原始版本和新的优先级更高
                        for i in conflict_library_candi_version:
                            if compare_version(i, target_proj_dependency[conflict_library]):
                                candi_versions.append(i)
                        for i in reversed(conflict_library_candi_version):
                            if not compare_version(i, target_proj_dependency[conflict_library]):
                                candi_versions.append(i)

                        for candi_ver in candi_versions:
                            compatibility_info = update_compatibility_info(conflict_library, library, candi_ver, start_proj_dependency[library], target_proj_dependency[library], start_path, target_path, library_call_module, compatibility_info, target_project, proj_path, target_proj_dependency, python_version)
                            compatibility_info = update_compatibility_info(target_project, conflict_library, "1", target_proj_dependency[conflict_library], candi_ver, conflict_start_path, conflict_target_path, conflict_library_call_module, compatibility_info, target_project, proj_path, target_proj_dependency, python_version)

                            if compatibility_info[tuple(sorted([(conflict_library, candi_ver), (library, target_proj_dependency[library])]))] and compatibility_info[tuple(sorted([(target_project, "1"), (conflict_library, candi_ver)]))]:
                                new_available_versions = available_versions.copy()
                                new_available_versions[conflict_library] = []
                                new_available_versions[conflict_library].append(candi_ver)
                                compatibility_dict = get_compatibility_dict(new_available_versions, python_version)
                                #print()

                                res = solving_constraints(compatibility_dict, new_available_versions)
                                #print(res)
                                if res is None:
                                    continue
                                #更新requirements
                                for i in res:
                                    if res[i] != target_proj_dependency[i]:
                                        flag = True
                                        target_proj_dependency[i] = res[i]
                                #print(res)
                                break
                    
            
            if flag == True:    
                target_proj_dependency = resolve_conflict(start_proj_dependency, target_proj_dependency, sub_graph, compatibility_info, proj_path, target_project, target_library, python_version, FDG)    

    return target_proj_dependency

