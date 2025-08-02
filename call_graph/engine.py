import argparse
import collections
import json
import logging
import os
import subprocess
import sys
import time
import platform


from .python import Python, find_node_or_group, get_importitems, find_node_or_group_in_file_group,get_file_scope_assigns
from .graph_model import (Edge, Group, Node, Call, Variable,
                    _find_links_for_call)
from .util import ShareData, LanguageParams, ShareFlag, flatten, GROUP_TYPE

glo_add_package_name = True

TEXT_EXTENSIONS = ('json')
VALID_EXTENSIONS = TEXT_EXTENSIONS


def generate_additional_outside_json(nodes, edges):

    def add_outside_node(outside_node):
        outside_node_name = outside_node.name_from_root
        outside_pack_name = outside_node_name.split(".")[0]
        if outside_pack_name in outside_dic:
            if outside_dic[outside_pack_name].count(outside_node_name)==0:
                outside_dic[outside_pack_name].append(outside_node_name)
        else:
            outside_dic[outside_pack_name] = [outside_node_name]

    outside_dic = {}
    for edge in edges:
        assert type(edge) == Edge
        source_node, dest_node = edge.node0, edge.node1
        if source_node.flag.is_fake == True:
            add_outside_node(source_node)
        if dest_node.flag.is_fake == True:
            add_outside_node(dest_node)

    return json.dumps(outside_dic)

def generate_json(nodes, edges):

    def extra_str_trans(key_str, value_str):

        if key_str.find(r"(global)")!=-1:
            key_str = key_str[:-9]

        init_idx = key_str.find(r"__init__")
        if init_idx != -1 and len(key_str)-init_idx!=8: 
            key_str = key_str[:init_idx-1] + key_str[init_idx+8:]
        if init_idx != -1 and key_str.count(".")==1: 
            key_str = key_str[:init_idx - 1]
        init_idx = value_str.find(r"__init__")
        if init_idx != -1 and len(value_str) - init_idx != 8:  
            value_str = value_str[:init_idx - 1] + value_str[init_idx + 8:]

        return key_str, value_str

    dic = {}
    for edge in edges:
        assert type(edge) == Edge
        key_str, value_str = edge.node0.name_from_root, edge.node1.name_from_root
        key_str, value_str = extra_str_trans(key_str, value_str)
        if key_str == None or value_str == None:
            continue

        if edge.node0.flag.is_fake:
            pass
        if edge.node1.flag.is_fake:
            pass
        if key_str in dic:
            if dic[key_str].count(value_str)==0:
                dic[key_str].append(value_str)
        else:
            dic[key_str] = [value_str]
    return json.dumps(dic)


def write_additional_entry_output_file(found_entry_func_list, outfile, nodes, edges, groups, hide_legend=False,
               no_grouping=False, as_json=True):

    assert as_json == True
    content = json.dumps(found_entry_func_list)
    outfile.write(content)
    return


def write_additional_outside_output_file(outfile, nodes, edges, groups, hide_legend=False,
               no_grouping=False, as_json=True):

    if as_json:
        content = generate_additional_outside_json(nodes, edges)
        outfile.write(content)
        return

def write_file(outfile, nodes, edges, groups, hide_legend=False,
               no_grouping=False, as_json=True):
    if as_json:
        content = generate_json(nodes, edges)
        outfile.write(content)
        return


def get_sources_and_language(raw_source_paths, language):
    assert len(raw_source_paths)==1

    individual_files = []
    for source in sorted(raw_source_paths):
        if os.path.isfile(source):
            individual_files.append((source, True))
            continue
        for root, _, files in os.walk(source):
            for f in files:
                individual_files.append((os.path.join(root, f), False))

    if not individual_files:
        raise AssertionError("No source files found from %r" % raw_source_paths)

    if not language:
        language = Python

    sources = set()
    for source, explicity_added in individual_files:
        if explicity_added or source.endswith('.' + language):
            sources.add(source)
        else:
            pass 

    if not sources:
        raise AssertionError("Could not find any source files given {raw_source_paths} "
                             "and language {language}.")

    sources = sorted(list(sources))


    return sources, language

def make_file_group(tree, filename, rootpath, add_package_name=True):
    add_package_name = glo_add_package_name
    language = Python

    subgroup_trees, node_trees, body_trees = language.separate_namespaces(tree)
    group_type = GROUP_TYPE.FILE
    token = os.path.split(filename)[-1].rsplit('.py' , 1)[0]

    rootpath_size = len(rootpath)

    if (platform.system() == 'Windows'):
        name_from_root = ".".join(filename[rootpath_size:-3].split("\\"))
    else:
        name_from_root = ".".join(filename[rootpath_size:-3].split(r"/"))

    if(name_from_root[0]=='.'):
        name_from_root=name_from_root[1:]

    if (platform.system() == 'Windows'):
        package_name = rootpath.split("\\")[-1]
    else:
        package_name = rootpath.split(r"/")[-1]
    if add_package_name:
        name_from_root = package_name + "." + name_from_root

    line_number = 0
    display_name = 'File'
    import_tokens = []

    global_variables = get_file_scope_assigns(body_trees)

    file_group = Group(name_from_root, token, group_type, display_name, import_tokens,
                       line_number, parent=None, file_absolute_path = filename, global_variables = global_variables)
    for node_tree in node_trees:
        for new_node in language.make_nodes(node_tree, parent=file_group):
            file_group.add_node(new_node)

    file_group.add_node(language.make_root_node(body_trees, parent=file_group), is_root=True)

    for subgroup_tree in subgroup_trees:
        file_group.add_subgroup(language.make_class_group(subgroup_tree, parent=file_group))
    return file_group



def _find_links(node_a, all_nodes):

    links = []
    for call in node_a.calls:
        lsfc = _find_links_for_call(call, node_a, all_nodes)
        assert not isinstance(lsfc[0], Group)
        links.append(lsfc)
    return list(filter(None, links))

def deal_bad_call(call):
    assert type(call) == Call
    output_str =""
    parent = call.master_node.parent
    while(parent.group_type != "FILE"):
        parent = parent.parent
    file_name = parent.name_from_root
    line_number = call.line_number
    node_name = call.master_node.name_from_root

    if call.owner_token:
        call_name = call.owner_token + "." + call.token
    else:
        call_name = call.token


def map_it(root_path, sources, no_trimming, exclude_namespaces, exclude_functions,
           skip_parse_errors, lang_params, entry_functions):


    language = Python
    language.assert_dependencies()

    file_ast_trees = []
    for source in sources:
        try:
            file_ast_trees.append((source, language.get_tree(source, lang_params)))
        except Exception as ex:
            if skip_parse_errors:
                logging.warning("Could not parse %r. (%r) Skipping...", source, ex)
            else:
                raise ex
    file_groups = []
    file_dic={}
    for source, file_ast_tree in file_ast_trees:
        file_group = make_file_group(file_ast_tree, source, root_path)
        file_groups.append(file_group)
        file_dic[file_group.name_from_root]= (file_ast_tree, file_group)

    all_subgroups = flatten(g.all_groups() for g in file_groups)
    all_nodes = flatten(g.all_nodes() for g in file_groups)

    for group in file_groups:
        get_importitems(group, file_dic)

    for node in all_nodes:
        get_importitems(node, file_dic)

    for subgroup in all_subgroups:
        get_importitems(subgroup, file_dic)

    for node in all_nodes:
        node.resolve_variables(file_groups)

    for group in file_groups:
        for subgroup in group.all_groups():
            if len(subgroup.inherits) > 0:
                for node in subgroup.nodes:
                    for i in range(len(node.calls)):
                        call = node.calls[i]
                        if call.token == "super" and call.owner_token == None and node.calls[
                            i - 1].owner_token == "UNKNOWN_VAR":
                            node.calls[i - 1].owner_token = subgroup.inherits[0]

    for group in file_groups:
        for subgroup in group.all_groups():
            subgroup.father_classes = []
            for father_class_token in subgroup.inherits:
                father_class_groups = find_node_or_group_in_file_group(father_class_token, subgroup.parent, file_dic)
                if father_class_groups == None or len(father_class_groups)==0:
                    continue
                for father_class_group in father_class_groups:
                    if type(father_class_group)==Group:
                        subgroup.father_classes.append(father_class_group)
            subgroup.inherits = []

    for group in file_groups:
        for subgroup in group.all_groups():
            subgroup.inherits = []
            for father_class_group in subgroup.father_classes:
                if type(father_class_group)!=Group:
                    pass
                subgroup.inherits.append(father_class_group.nodes)
                if len(father_class_group.father_classes)>0:
                    for grandfather_class_group in father_class_group.father_classes:
                        subgroup.inherits.append(grandfather_class_group.nodes)
            assert type(subgroup.inherits)==list
    bad_calls = []
    edges = []
    is_full = False

    found_entry_func_list = []
    if entry_functions and len(entry_functions)>0:
        to_extend = []
        for name in entry_functions:
            while(name[0]==' '):
                name = name[1:]
            while(name[-1]==' '):
                name = name[:-1]

            nodes = find_node_from_outside(name, file_dic, all_nodes, all_subgroups)

            if len(nodes)==0:
                continue

            found_flag = False
            for node in nodes:
                if type(node)==Node:
                    found_flag = True
                elif type(node)==Group:
                    if node.group_type != "CLASS":
                        continue
                    node = node.get_constructor()
                    found_flag = True
                to_extend.append(node)
                found_entry_func_list.append(node.name_from_root)


        while len(to_extend)>0 :
            node_a = to_extend[0]
            to_extend = to_extend[1:]
            if node_a.flag.calls_analyzed:
                continue

            node_a.flag.calls_analyzed = True
            links = _find_links(node_a, all_nodes)
            for node_bs, bad_call in links:
                if bad_call:
                    bad_calls.append(bad_call)
                if node_bs==None or len(node_bs)==0:
                    continue
                for node_b in node_bs:
                    edges.append(Edge(node_a, node_b))
                    if node_b.flag.calls_analyzed == False and node_b.flag.is_fake == False:
                        to_extend.append(node_b)

    else:
        is_full = True
        for node_a in list(all_nodes):
            links = _find_links(node_a, all_nodes)
            for node_bs, bad_call in links:
                if bad_call:
                    bad_calls.append(bad_call)
                if node_bs==None or len(node_bs)==0:
                    continue
                for node_b in node_bs:
                    edges.append(Edge(node_a, node_b))
    bad_calls_strings = set()
    for bad_call in bad_calls:
        bad_calls_strings.add(bad_call.to_string())
        deal_bad_call(bad_call)
    bad_calls_strings = list(sorted(list(bad_calls_strings)))

    if no_trimming:
        return file_groups, all_nodes, edges,found_entry_func_list
    nodes_with_edges = set()
    for edge in edges:
        nodes_with_edges.add(edge.node0)
        nodes_with_edges.add(edge.node1)

    for node in all_nodes:
        if node not in nodes_with_edges:
            node.remove_from_parent()

    for file_group in file_groups:
        for group in file_group.all_groups():
            if not group.all_nodes():
                group.remove_from_parent()

    file_groups = [g for g in file_groups if g.all_nodes()]
    all_nodes = list(nodes_with_edges)

    return file_groups, all_nodes, edges,found_entry_func_list

def find_node_from_outside(outside_name, file_dic, all_nodes, all_subgroups):
    pack_name = outside_name.split(".")[0]
    outside_name = ".".join(outside_name.split(".")[1:])

    direct_res_list = find_node_or_group(outside_name, file_dic)
    if direct_res_list and len(direct_res_list)>0:
        return direct_res_list

    name_list = list(outside_name.split("."))
    init_file_group = None
    min_len = 10086
    for key,value in file_dic.items():
        if key.endswith("__init__") and len(key) < min_len and key.find("tests")==-1:
            min_len = len(key)
            init_file_group = value[1]

    if init_file_group == None:
        for key, value in file_dic.items():
            if key.endswith(pack_name) and len(key) < min_len:
                min_len = len(key)
                init_file_group = value[1]
    assert init_file_group != None

    file_group = init_file_group
    tmp = None
    for name in name_list:
        if type(tmp)==list and len(tmp)==1:
            tmp = tmp[0]
            file_group = tmp
        if type(file_group)==Group and file_group.group_type=="CLASS":
            tmp = find_node_or_group_in_file_group(name, file_group, file_dic, is_class=True)
        else:
            tmp = find_node_or_group_in_file_group(name, file_group, file_dic)

        assert type(tmp)==list
        longeast_prefix_Node = None
        if len(tmp) == 0:
            if type(file_group)==Node:
                longeast_prefix_Node = file_group
            break

    res_list = []
    for i in tmp:
        if type(i)==Group and i.group_type=="FILE":
            continue
        res_list.append(i)

    if len(res_list)>0:
        assert type(res_list[0]) in (Node, Group)

    if len(res_list)==0:
        assert type(all_nodes)==list and type(all_subgroups)==list
        outside_token = outside_name.split(".")[-1]
        for node in all_nodes:
            if node.token == outside_token:
                if node.parent.group_type=="CLASS":
                    res_list.append(node.parent.get_constructor())
                res_list.append(node)
        for subgroup in all_subgroups:
            if subgroup.group_type!="CLASS":
                continue
            if subgroup.token == outside_token:
                res_list.append(subgroup)
        if len(res_list)>0:
            tmp_record = dict()
            tmp_record[pack_name + "." + outside_name] = len(res_list)
            ShareData.name_base_global_search_record.append(tmp_record)
        else:
            if longeast_prefix_Node!=None:
                res_list = [longeast_prefix_Node]


    return res_list


def code2flow(raw_source_paths, output_file, language=None, hide_legend=True,
              exclude_namespaces=None, exclude_functions=None, entry_functions = None,
              no_grouping=False, no_trimming=False, skip_parse_errors=False,
              lang_params=None, level=logging.INFO):

    if not isinstance(raw_source_paths, list):
        raw_source_paths = [raw_source_paths]
    exclude_namespaces = exclude_namespaces or []
    assert isinstance(exclude_namespaces, list)
    exclude_functions = exclude_functions or []
    assert isinstance(exclude_functions, list)
    lang_params = lang_params or LanguageParams()

    logging.basicConfig(format="Code2Flow: %(message)s", level=level)

    sources, language = get_sources_and_language(raw_source_paths, language)

    output_ext = None
    if isinstance(output_file, str):
        assert '.' in output_file, "Output filename must end in one of: %r." % set(VALID_EXTENSIONS)
        output_ext = output_file.rsplit('.', 1)[1] or ''
        assert output_ext in VALID_EXTENSIONS, "Output filename must end in one of: %r." % set(VALID_EXTENSIONS)

    file_groups, all_nodes, edges, found_entry_func_list = map_it(raw_source_paths[0], sources, no_trimming,\
                                           exclude_namespaces, exclude_functions,\
                                           skip_parse_errors, lang_params, entry_functions)

    if isinstance(output_file, str):
        with open(output_file, 'w') as fh:
            as_json = output_ext == 'json'
            write_file(fh, nodes=all_nodes, edges=edges,
                       groups=file_groups, hide_legend=hide_legend,
                       no_grouping=no_grouping, as_json=as_json)

        additional_outside_output_file = output_file[:-5] + "-outside" + r".json"
        with open(additional_outside_output_file, 'w') as fh:
            write_additional_outside_output_file(fh, nodes=all_nodes, edges=edges,
                       groups=file_groups, hide_legend=hide_legend,
                       no_grouping=no_grouping, as_json=as_json)
        additional_entry_output_file = output_file[:-5] + "-entry" + r".json"
        with open(additional_entry_output_file, 'w') as fh:
            write_additional_entry_output_file(found_entry_func_list, fh, nodes=all_nodes, edges=edges,
                       groups=file_groups, hide_legend=hide_legend,
                       no_grouping=no_grouping, as_json=as_json)

    else:
        write_file(output_file, nodes=all_nodes, edges=edges,
                   groups=file_groups, hide_legend=hide_legend,
                   no_grouping=no_grouping)


def main(sys_argv=None, if_add_package_name = None):
    if if_add_package_name!=None:
        global glo_add_package_name
        glo_add_package_name = if_add_package_name

    parser = argparse.ArgumentParser(
        description="",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument(
        'sources', metavar='sources', nargs='+',
        help='source code file/directory paths.')
    parser.add_argument(
        '--output', '-o', default='out.png',
        help=f'output file path. Supported types are {VALID_EXTENSIONS}.')
    parser.add_argument(
        '--language', choices=['py'],
        help='process this language and ignore all other files.'
             'If omitted, use the suffix of the first source file.')
    parser.add_argument(
        '--entry-functions',
        help='entry functions to generate a sub call graph.')
    parser.add_argument(
        '--exclude-functions',
        help='exclude functions from the output. Comma delimited.')
    parser.add_argument(
        '--exclude-namespaces',
        help='exclude namespaces (Classes, modules, etc) from the output. Comma delimited.')
    parser.add_argument(
        '--no-grouping', action='store_true',
        help='instead of grouping functions into namespaces, let functions float.')
    parser.add_argument(
        '--no-trimming', action='store_true',
        help='show all functions/namespaces whether or not they connect to anything.')
    parser.add_argument(
        '--hide-legend', action='store_true',
        help='by default, Code2flow generates a small legend. This flag hides it.')
    parser.add_argument(
        '--skip-parse-errors', action='store_true',
        help='skip files that the language parser fails on.')
    parser.add_argument(
        '--source-type', choices=['script', 'module'], default='script',
        help='js only. Parse the source as scripts (commonJS) or modules (es6)')
    parser.add_argument(
        '--ruby-version', default='27',
        help='ruby only. Which ruby version to parse? This is passed directly into ruby-parse. Use numbers like 25, 27, or 31.')
    parser.add_argument(
        '--quiet', '-q', action='store_true',
        help='suppress most logging')
    parser.add_argument(
        '--verbose', '-v', action='store_true',
        help='add more logging')

    sys_argv = sys_argv or sys.argv[1:]
    args = parser.parse_args(sys_argv)
    level = logging.INFO
    if args.verbose and args.quiet:
        raise AssertionError("Passed both --verbose and --quiet flags")
    if args.verbose:
        level = logging.DEBUG
    if args.quiet:
        level = logging.WARNING

    exclude_namespaces = list(filter(None, (args.exclude_namespaces or "").split(',')))
    exclude_functions = list(filter(None, (args.exclude_functions or "").split(',')))
    entry_functions = list(filter(None, (args.entry_functions or "").split(',')))
    lang_params = LanguageParams(args.source_type, args.ruby_version)

    code2flow(
        raw_source_paths=args.sources,
        output_file=args.output,
        language=args.language,
        hide_legend=args.hide_legend,
        entry_functions=entry_functions,
        exclude_namespaces=exclude_namespaces,
        exclude_functions=exclude_functions,
        no_grouping=args.no_grouping,
        no_trimming=args.no_trimming,
        skip_parse_errors=True,
        lang_params=lang_params,
        level=level,
    )

if __name__ == '__main__':
    main()

  