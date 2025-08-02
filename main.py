from code_compat.target_library_conflict import *
from code_compat.non_target_library_conflict import *
from call_graph.get_FDG import * 
from extraction.get_attribute_from_proj import *
from extraction.import_to_path import *
from extraction.getCall import get_all_used_api
from ver_compat.constraint_solver import solving_constraints
from ver_compat.get_ver_and_constraint import *
from ver_change.version_change import *
from utils.util import * 
import platform, argparse, os, json, time, requests, logging


if (platform.system() == 'Windows'):
    slash = "\\"
else:
    slash = r"/" 

library_path_prefix = ""
constraint_path_prefix = ""
version_path_prefix = ""
api_path_prefix = ""
def parse_arguments():
    parser = argparse.ArgumentParser(description="命令行工具示例")
    parser.add_argument('--config', type=str, required=True, help="配置文件路径")
    parser.add_argument('--options', type=bool, required=False, default=False, help="是否强制执行第二步")
    return parser.parse_args()

def prepare_environment(config):
    proj_path = config["projPath"]
    target_project = proj_path.split("/")[-1]
    target_library = config["targetLibrary"]
    target_version = config["targetVersion"]
    log_dir = f"./report/{target_project}/{target_library}/{target_version}"
    os.makedirs(log_dir, exist_ok=True)
    log_path = os.path.join(log_dir, "log.txt")
    open(log_path, 'w').close()
    setup_logging(log_path)
    return target_project, target_library, target_version

def setup_path(library_path_prefix_pass, constraint_path_prefix_pass, version_path_prefix_pass, api_path_prefix_pass):
    global library_path_prefix, constraint_path_prefix, version_path_prefix, api_path_prefix
    library_path_prefix = library_path_prefix_pass
    constraint_path_prefix = constraint_path_prefix_pass
    version_path_prefix = version_path_prefix_pass
    api_path_prefix = api_path_prefix_pass
    setup_path_1(library_path_prefix, constraint_path_prefix, version_path_prefix, api_path_prefix)
    setup_path_2(library_path_prefix, constraint_path_prefix, version_path_prefix, api_path_prefix)
    setup_path_3(library_path_prefix, constraint_path_prefix, version_path_prefix, api_path_prefix)
    setup_path_4(library_path_prefix, constraint_path_prefix, version_path_prefix, api_path_prefix)
    setup_path_5(library_path_prefix, constraint_path_prefix, version_path_prefix, api_path_prefix)

def upgrade_with_conflict_handling(config, target_project, target_library, target_version, python_version, start_proj_dependency, library_path_prefix, version_path_prefix, start_library_path, target_library_call_module):
    compatibility_info = {}
    new_target_version = target_version
    with open(f"{version_path_prefix}/library_version.json", 'r') as file:
        version_ls = json.load(file)
    candidate_versions = version_ls[target_library][python_version]

    filtered_versions = [v for v in reversed(candidate_versions)
                         if compare_version(v, config['startVersion']) and not compare_version(v, target_version) and v != target_version]
    filtered_versions.append(config['startVersion'])

    for version in filtered_versions:
        logging.info(f"{target_project} is not compatible with {target_library}-{new_target_version}, change to {target_library}-{version}")
        new_target_version = version
        target_library_path = get_library_paths(library_path_prefix, target_library, new_target_version, target_library_call_module)
        is_conflict = is_target_library_code_conflict(
            config['projPath'], target_project, target_library, config['startVersion'], new_target_version,
            start_library_path, target_library_path, target_library_call_module, target_project,
            config['projPath'], start_proj_dependency.copy(), python_version
        )
        if not is_conflict:
            key = tuple(sorted([(target_project, "1"), (target_library, version)]))
            compatibility_info[key] = True
            break
    return new_target_version, compatibility_info

def resolve_dependencies(target_proj_dependency, python_version, target_library, new_target_version, FDG, sub_graph):
    available_versions = get_available_version(FDG, sub_graph, python_version, target_proj_dependency, target_library, new_target_version)
    compatibility_dict = get_compatibility_dict(available_versions, python_version)
    return solving_constraints(compatibility_dict, available_versions), available_versions

def finalize_and_save_requirements(target_proj_dependency, sub_graph, compatibility_info, target_library, start_version, target_version, python_version, proj_path, target_project):
    clean_deps = remove_invalid_versions(target_proj_dependency)
    #print(target_proj_dependency)
    tmp = get_new_lib(clean_deps, python_version)
    all_packages = set(sub_graph) | set(tmp)
    end_available_versions = {
        pkg: [clean_deps[pkg]] if pkg in clean_deps else tmp[pkg] for pkg in all_packages
    }

    end_compatibility_dict = get_compatibility_dict(end_available_versions, python_version)
    end_res = solving_constraints(end_compatibility_dict, end_available_versions)
    if end_res is None:
        pass
    else:
        for i in end_res:
            if i not in clean_deps:
                clean_deps[i] = end_res[i]
    clean_deps = remove_redundant_dependencies(clean_deps, target_library, start_version, target_version, python_version, proj_path)

    report_path = f"./report/{target_project}/{target_library}/{target_version}"
    os.makedirs(report_path, exist_ok=True)
    save_dict_to_file(clean_deps, f"{report_path}/requirements.txt")
    return clean_deps

def run_upgrade_process(config, options):
    target_project, target_library, target_version = prepare_environment(config)
    python_version = config["pythonVersion"]
    start_requirements_path = config["requirementsPath"]
    knowledge_path = config["knowledgePath"]

    library_path_prefix = f"{knowledge_path}libraries/"
    version_path_prefix = f"{knowledge_path}"
    setup_path(library_path_prefix, f"{knowledge_path}version_constraint/", version_path_prefix, f"{knowledge_path}library_api/")
    target_library_call_module = get_library_call_module(target_library)

    start_proj_dependency = get_proj_dependency_from_requirements(start_requirements_path)
    start_library_path = get_library_paths(library_path_prefix, target_library, config['startVersion'], target_library_call_module)
    target_library_path = get_library_paths(library_path_prefix, target_library, target_version, target_library_call_module)

    cleanup_temp_files()

    logging.info(f"*************Upgrade {target_library} from {config['startVersion']} to {target_version} in {target_project}*************")

    is_conflict = is_target_library_code_conflict(
        config['projPath'], target_project, target_library, config['startVersion'], target_version,
        start_library_path, target_library_path, target_library_call_module,
        target_project, config['projPath'], start_proj_dependency.copy(), python_version
    )

    if is_conflict and not options:
        new_target_version, compatibility_info = upgrade_with_conflict_handling(
            config, target_project, target_library, target_version, python_version,
            start_proj_dependency, library_path_prefix, version_path_prefix,
            start_library_path, target_library_call_module
        )
    else:
        new_target_version = target_version
        compatibility_info = {tuple(sorted([(target_project, "1"), (target_library, target_version)])): True}

    target_proj_dependency = start_proj_dependency.copy()
    target_proj_dependency[target_library] = new_target_version

    FDG = get_FDG_from_requirements(target_proj_dependency, python_version)
    sub_graph = get_sub_graph(FDG, target_library)
    #print(sub_graph)

    res, available_versions = resolve_dependencies(target_proj_dependency, python_version, target_library, new_target_version, FDG, sub_graph)
    if res != None:
        target_proj_dependency = update_project_dependencies(target_proj_dependency, res)

        target_proj_dependency = resolve_conflict(
            start_proj_dependency, target_proj_dependency, sub_graph,
            compatibility_info, config['projPath'], target_project, target_library,
            python_version, FDG
        )

    finalize_and_save_requirements(
        target_proj_dependency, sub_graph, compatibility_info,
        target_library, config['startVersion'], new_target_version,
        python_version, config['projPath'], target_project
    )

if __name__ == '__main__':
    start = time.time()
    args = parse_arguments()
    config = load_config(args.config)
    run_upgrade_process(config, args.options)
    cleanup_temp_files()
    end = time.time()
    logging.info("*************New requirements.txt has been generated!*************")
    logging.info(f"Time cost: {end - start} s")

    