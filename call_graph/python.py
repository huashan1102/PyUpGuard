import ast
import logging
import os
from subprocess import run

from .graph_model import (Group, Node, Call, Variable,
                    ImportItem, create_fake_node,create_fake_group,
                   _find_links_for_call)
from .util import ShareFlag, djoin, flatten, OWNER_CONST, GROUP_TYPE

def _deal_call_and_variable_pt_call(node):
    assert type(node) == Node
    for variable in node.variables:
        if type(variable.points_to) == Call:
            dummy_call = variable.points_to
            success = False
            for call in node.calls:
                if call.line_number == dummy_call.line_number and call.owner_token == dummy_call.owner_token and call.token == dummy_call.token:
                    success = True
                    variable.points_to = call
                    del dummy_call
                    break
            assert success

    for call in node.calls:
        call.master_node = node


def find_file_group_from_here(here, path_name, file_dic, level=0):
    def find_parent_file_group(node_or_group):
        assert type(node_or_group) in (Node, Group)
        if type(node_or_group) == Group and node_or_group.group_type == "FILE":
                return node_or_group
        parent = find_parent_file_group(node_or_group.parent)
        return parent

    def look_up(regular_name_from_root, file_dic):
        if regular_name_from_root in file_dic:
            return file_dic[regular_name_from_root][1]
        init_name_from_root = regular_name_from_root + ".__init__"
        if init_name_from_root in file_dic:
            return file_dic[init_name_from_root][1]
        return None

    assert type(here) in (Group, Node)
    assert type(level) == int

    here_file_group = find_parent_file_group(here)
    here_name_from_root = here_file_group.name_from_root

    if level==0:
        target_path_first = path_name.split(".")[0]
        root_name = here_name_from_root.split(".")[0]
        res = look_up(path_name, file_dic)
        if res!=None:
            return res

    here_menu_name_from_root = ".".join(here_name_from_root.split(".")[:-1])
    if level-1 > 0:
        delete_dot_num = level-1
        here_menu_name_from_root = ".".join(here_menu_name_from_root.split(".")[:-delete_dot_num])

    if path_name:
        regular_name_from_root = here_menu_name_from_root + "." + path_name
    else:
        regular_name_from_root = here_menu_name_from_root

    if regular_name_from_root.startswith("."):
        regular_name_from_root = regular_name_from_root[1:]

    res = look_up(regular_name_from_root, file_dic)
    if res == None:
        pass
    return res


def get_call_from_func_element(func):
    if type(func) == ast.Attribute:
        owner_token = []
        val = func.value
        while True:
            try:
                if hasattr(val,'attr'):
                    owner_token.append(val.attr)
                else:
                    owner_token.append(val.id)
            except AttributeError:
                pass
            val = getattr(val, 'value', None)
            if not val:
                break
        if owner_token:
            owner_token = djoin(*reversed(owner_token))
        else:
            owner_token = OWNER_CONST.UNKNOWN_VAR

        return Call(token=func.attr, line_number=func.lineno, owner_token=owner_token)
    if type(func) == ast.Name:

        return Call(token=func.id, line_number=func.lineno)
    if type(func) in (ast.Subscript, ast.Call):
        return None
    return None


def make_calls(lines):
    calls = []
    for tree in lines:
        for element in ast.walk(tree):
            if type(element) != ast.Call:
                continue
            call = get_call_from_func_element(element.func)
            if call:
                calls.append(call)
    return calls


def process_assign(element):
    if type(element.value) != ast.Call:
        return []
    call = get_call_from_func_element(element.value.func)

    ret = []
    for target in element.targets:
        if type(target) not in (ast.Name, ast.Attribute):
            continue
        if type(target) == ast.Name:
            token = target.id
        else:
            assert type(target) == ast.Attribute
            if type(target.value) !=ast.Name:
                continue
            token = target.value.id + "." + target.attr

        if call != None:
            ret.append(Variable(token, call, element.lineno))
    return ret


def process_import(element):
    ret = []

    for single_import in element.names:
        assert isinstance(single_import, ast.alias)
        token = single_import.asname or single_import.name
        rhs = single_import.name

        if hasattr(element, 'module'):
            rhs = djoin(element.module, rhs)

        ret.append(Variable(token, points_to=rhs, line_number=element.lineno))
    return ret


def make_local_variables(lines, parent):
    variables = []
    for tree in lines:
        for element in ast.walk(tree):
            if type(element) == ast.Assign:
                variables += process_assign(element)
            if type(element) in (ast.Import, ast.ImportFrom):
                variables += process_import(element)
    if parent.group_type == GROUP_TYPE.CLASS:
        variables.append(Variable('self', parent, lines[0].lineno))

    variables = list(filter(None, variables))
    return variables


def get_inherits(tree):
    return [base.id for base in tree.bases if type(base) == ast.Name]



def get_importitems_Import(el, node_or_group, file_dic):
    assert type(el) == ast.Import
    assert type(node_or_group) in (Node, Group)

    for single_import in el.names:
        absolute_name = single_import.name
        asname = single_import.asname or absolute_name
        file_group = find_file_group_from_here(node_or_group, absolute_name, file_dic)
        if file_group == None:
            file_group = create_fake_group(absolute_name)

        assert type(file_group)==Group and file_group.group_type == "FILE"

        if file_group.name_from_root == node_or_group.name_from_root:
            continue

        node_or_group.import_items.append(ImportItem(el.lineno, file_group, asname))


def get_importitems_ImportFrom(el, node_or_group, file_dic):
    assert type(el) == ast.ImportFrom
    assert type(node_or_group) in (Node, Group)

    source_name = el.module
    level = el.level

    for single_import in el.names:
        target_name = single_import.name
        asname = single_import.asname or target_name
        if target_name == "*":
            file_group = find_file_group_from_here(node_or_group, source_name,file_dic, level)
            if file_group != None:
                assert type(file_group) == Group and file_group.group_type == "FILE"
                node_or_group.import_items.append(ImportItem(el.lineno, file_group, asname))
            continue
        if source_name != None:
            module_or_subpackage_name = source_name + "." + target_name
        else:
            module_or_subpackage_name = target_name
        file_group = find_file_group_from_here(node_or_group, module_or_subpackage_name, file_dic, level)
        if file_group != None:
            assert type(file_group) == Group and file_group.group_type == "FILE"
            node_or_group.import_items.append(ImportItem(el.lineno, file_group, asname))
            continue
        file_group = find_file_group_from_here(node_or_group, source_name, file_dic, level)
        if file_group != None:
            target_nodes_or_groups = find_node_or_group_in_file_group(target_name, file_group, file_dic)
            if len(target_nodes_or_groups) == 0:
                continue
            for target_node_or_group in target_nodes_or_groups:
                node_or_group.import_items.append(ImportItem(el.lineno, target_node_or_group, asname))
        else:
            node_or_group.import_items.append(ImportItem(el.lineno, create_fake_node(module_or_subpackage_name, may_third_party_class = True), asname))


def get_importitems(node_or_group, file_dic):

    assert type(node_or_group) in (Node, Group)


    if node_or_group.flag.import_done == True:
        return

    if node_or_group.flag.import_done == None:
        return

    node_or_group.flag.import_done = None

    tree= find_ast_tree(node_or_group, file_dic)
    if tree == None:
        return
    groups, nodes, body = Python.separate_namespaces(tree)
    if type(node_or_group) == Node:
        body = groups + nodes + body
    elif type(node_or_group) == Group and node_or_group.group_type == "CLASS":
        body = groups + body
    elif type(node_or_group) == Group and node_or_group.group_type == "FILE":
        body = body

    for el in body:
        if type(el) == ast.Import:
            get_importitems_Import(el, node_or_group, file_dic)
        elif type(el) == ast.ImportFrom:
            get_importitems_ImportFrom(el, node_or_group, file_dic)

    node_or_group.flag.import_done = True

def get_class_all_inherits_nodes(class_group):

    assert type(class_group)==Group and class_group.group_type=="CLASS"

    all_super_classes = set()
    to_search_queue = []
    if not hasattr(class_group, r"father_classes"):
        direct_fathers = []
    else:
        direct_fathers = class_group.father_classes
    for direct_father in direct_fathers:
        to_search_queue.append(direct_father)
        all_super_classes.add(direct_father)

    while(len(to_search_queue)!=0):
        t = to_search_queue[0]
        to_search_queue = to_search_queue[1:]
        if not hasattr(t, r"father_classes"):
            continue
        t_fathers = t.father_classes
        for t_father in t_fathers:
            if t_father not in all_super_classes:
                to_search_queue.append(t_father)
                all_super_classes.add(t_father)

    all_inherits_nodes = set()
    for super_class in all_super_classes:
        for node in super_class.nodes:
            all_inherits_nodes.add(node)

    return all_inherits_nodes



def find_node_or_group_in_file_group(node_or_group_name, file_group, file_dic,
                    searched_files = None, is_class=False):


    assert type(node_or_group_name) == str
    if type(file_group)!=Group:

        return []
    assert type(file_group) == Group
    res = []

    if(searched_files!=None and file_group.name_from_root in searched_files):
        return res

    for node in file_group.nodes:
        if node.token == node_or_group_name:
            res.append(node)

    for class_group in file_group.subgroups:
        if class_group.token== node_or_group_name:
            res.append(class_group)

    for global_varibale in file_group.global_variables:
        if global_varibale.token == node_or_group_name:
            if type(global_varibale.points_to) == str:
                pstr = global_varibale.points_to
                global_varibale.points_to = None
                if pstr.find(".")==-1:
                    tmp_res = find_node_or_group_in_file_group(pstr, file_group,file_dic)
                    if len(tmp_res)>0:
                        res += tmp_res
                        global_varibale.points_to = tmp_res
                else:
                    assert pstr.count(".")==1
                    before_dot_pstr = pstr.split(".")[0]
                    after_dot_pstr = pstr.split(".")[1]
                    before_tmp_res = find_node_or_group_in_file_group(before_dot_pstr, file_group, file_dic)
                    if len(before_tmp_res)==0:
                        return []
                    for x in before_tmp_res:
                        if type(x)!=Group:
                            continue
                        after_tmp_res = find_node_or_group_in_file_group(after_dot_pstr, x, file_dic)
                        if len(after_tmp_res) > 0:
                            res += after_tmp_res
                            global_varibale.points_to = after_tmp_res
            elif global_varibale.points_to==None:
                continue
            elif type(global_varibale.points_to)==Call:
                pcall = global_varibale.points_to
                if pcall.is_analyzed == False:
                    file_groups = []
                    for tup in file_dic.values():
                        file_groups.append(tup[1])
                    all_nodes = flatten(g.all_nodes() for g in file_groups)
                    _find_links_for_call(pcall, file_group.root_node, all_nodes)
                res += pcall.results
            else:
                assert type(global_varibale.points_to)==list and len(global_varibale.points_to)>0
                res += global_varibale.points_to

    if len(res)>0:
        return res

    if file_group.group_type == "CLASS":
        all_inherits_nodes = get_class_all_inherits_nodes(file_group)
        for node in all_inherits_nodes:
            if node.token == node_or_group_name:
                res.append(node)

        if len(res) > 0:
            return res

    if file_group.flag.import_done == False:
        get_importitems(file_group, file_dic)

    file_tmp = find_file_group_from_here(file_group, node_or_group_name, file_dic)
    if file_tmp!=None:
        res.append(file_tmp)

    if len(res)>0:
        return res

    if file_group.flag.import_done == True:

        for import_item in file_group.import_items:
            if import_item.asname == node_or_group_name and import_item.item.flag.is_fake == False:
                res.append(import_item.item)

        if len(res)==0:
            if searched_files == None:
                searched_files = set()
            searched_files.add(file_group.name_from_root)

            for import_item in file_group.import_items:
                if import_item.item.flag.is_fake:
                    continue
                if type(import_item.item)==Group and import_item.item.group_type=="FILE":
                    # print("find: ", node_or_group_name, " in ", import_item.item.token)
                    newres = find_node_or_group_in_file_group(node_or_group_name, import_item.item, file_dic, searched_files)
                    if len(newres)!=0:
                        return newres

    return res


def find_node_or_group(name_from_root, file_dic):
    res = []

    # 1. find the file group
    matched_file_names=[]
    for file_name in file_dic.keys():
        if name_from_root.startswith(file_name):
            if len(name_from_root)==len(file_name) or name_from_root[len(file_name)]=='.':
                matched_file_names.append(file_name)

    if len(matched_file_names)==0:
        return None
    assert len(matched_file_names)==1

    file_name_from_root = matched_file_names[0]
    file_group = file_dic[file_name_from_root][1]
    assert type(file_group)==Group and file_group.group_type =="FILE"

    # 2.1 name_from_root represent a file
    if file_name_from_root == name_from_root:
        res.append(file_group)
        return res

    suffix = name_from_root[len(file_name_from_root):] 

    if suffix.count(".") == 1 :
        func_or_class_token = suffix[1:]

        for node in file_group.nodes:
            if node.token == func_or_class_token:
                assert node.name_from_root == name_from_root
                res.append(node)
        for sub_group in file_group.subgroups:
            if sub_group.token == func_or_class_token:
                assert sub_group.name_from_root == name_from_root
                res.append(sub_group)
    else:
        assert suffix.count(".") == 2
        split_list = suffix[1:].split(".")
        class_token, method_token = split_list[0], split_list[1]
        for sub_group in file_group.subgroups:
            if sub_group.token == class_token:
                for node in sub_group.nodes:
                    if node.token == method_token:
                        assert node.name_from_root == name_from_root
                        res.append(node)

    if len(res)==0:
        return None

    return res

def find_ast_tree(node_or_group, file_dic):

    def find_sub_tree_in_a_ast_tree(target, tree):
        assert type(target) in (Node, Group)

        if type(target) == Group:
            assert(target.group_type=="CLASS")
            groups, nodes, body = Python.separate_namespaces(tree)
            for el in groups:
                assert type(el) == ast.ClassDef
                if el.name == target.token and el.lineno == target.line_number:
                    return el
        else:
            assert type(target) == Node
            groups, nodes, body = Python.separate_namespaces(tree)
            for el in nodes:
                assert type(el) == ast.FunctionDef
                if el.name == target.token and el.lineno == target.line_number:
                    return el
        return None



    assert type(node_or_group) in (Node, Group)

    if node_or_group.flag.is_fake:
        return None

    if node_or_group.token == "(global)":
        return None

    if type(node_or_group) == Group:
        group=node_or_group
        if group.group_type == "FILE":
            file_ast = file_dic[group.name_from_root][0]
            return file_ast
        else:
            assert group.group_type == "CLASS"
            file_name_from_root = group.parent.name_from_root
            if file_name_from_root in file_dic:
                file_ast = file_dic[file_name_from_root][0]
                res = find_sub_tree_in_a_ast_tree(group, file_ast)
            else:
                outside_class = group.parent
                file_name_from_root = group.parent.parent.name_from_root
                if file_name_from_root in file_dic:
                    file_ast = file_dic[file_name_from_root][0]
                    outside_class_ast = find_sub_tree_in_a_ast_tree(outside_class, file_ast)
                    res = find_sub_tree_in_a_ast_tree(group, outside_class_ast)
                else:
                    return None


            if res!=None:
                return res

    else:
        assert type(node_or_group) == Node
        node = node_or_group
        assert type(node.parent) == Group
        parent_ast = find_ast_tree(node.parent, file_dic) 
        res = find_sub_tree_in_a_ast_tree(node, parent_ast)
        if res != None:
            return res

#class Python(BaseLanguage):
class Python(object):
    @staticmethod
    def assert_dependencies():
        pass

    @staticmethod
    def get_tree(filename,_):
        def get_tree_with_feature_version(filename, feature_version=None):
            try:
                with open(filename) as f:
                    raw = f.read()
            except ValueError:
                with open(filename, encoding='UTF-8', errors='ignore') as f:
                    raw = f.read()
            if feature_version == None:
                tree = ast.parse(raw)
            else:
                tree = ast.parse(raw, feature_version=feature_version)
            return tree

        def process_refactor_get_tree(filename):
            refactor_py = os.path.join("utils", "refactor.py")
            to_3_prefix = r"python " + refactor_py + " -w -n --no-diffs --add-suffix=3"
            py2_py = filename
            assert os.path.exists(py2_py)
            order_list = ["python", refactor_py, "-w", "-n", "--no-diffs", "--add-suffix=3"]
            order_list.append(py2_py)
            py3_py = py2_py + "3"


            try:
                run(order_list)
                assert os.path.exists(py3_py)
                tree = get_tree_with_feature_version(py3_py, feature_version=(3, 4))
                os.remove(py3_py)
                return tree
            except AssertionError as ae:
                raise SyntaxError
            except SyntaxError as se:
                if os.path.exists(py3_py):
                    os.remove(py3_py)
                raise SyntaxError

        def get_tree_with_feature_version(filename, feature_version=None):
            try:
                with open(filename) as f:
                    raw = f.read()
            except ValueError:
                with open(filename, encoding='UTF-8', errors='ignore') as f:
                    raw = f.read()
            if feature_version == None:
                tree = ast.parse(raw)
            else:
                tree = ast.parse(raw, feature_version=feature_version)
            return tree

        def process_refactor_get_tree(filename):
            to_3_prefix = r"python refactor.py -w -n --no-diffs --add-suffix=3"
            py2_py = filename
            assert os.path.exists(py2_py)
            refactor_py = os.path.join("utils", "refactor.py")
            order_list = ["python", refactor_py, "-w", "-n", "--no-diffs", "--add-suffix=3"]
            order_list.append(py2_py)
            py3_py = py2_py + "3"

            try:
                run(order_list)
                assert os.path.exists(py3_py)
                tree = get_tree_with_feature_version(py3_py, feature_version=(3, 4))
                os.remove(py3_py)
                return tree
            except AssertionError as ae:
                raise SyntaxError
            except SyntaxError as se:
                if os.path.exists(py3_py):
                    os.remove(py3_py)
                raise SyntaxError

        try:
            tree = get_tree_with_feature_version(filename, feature_version=(3, 8))
            return tree
        except:
            try:
                tree = get_tree_with_feature_version(filename)
                return tree
            except:
                try:
                    tree = get_tree_with_feature_version(filename, feature_version=(3, 4))
                    return tree
                except:
                    try:
                        tree = process_refactor_get_tree(filename)
                        return tree
                    except Exception as e:
                        raise e

    @staticmethod
    def separate_namespaces(tree):
        groups = []
        nodes = []
        body = []
        if tree==None:
            return groups, nodes, body
        for el in tree.body:
            if type(el) == ast.FunctionDef:
                nodes.append(el)
            elif type(el) == ast.ClassDef:
                groups.append(el)
            elif getattr(el, 'body', None):
                tup = Python.separate_namespaces(el)
                groups += tup[0]
                nodes += tup[1]
                body += tup[2]
            else:
                body.append(el)

        if hasattr(tree, 'handlers'):
            for el in tree.handlers:
                if type(el) == ast.FunctionDef:
                    nodes.append(el)
                elif type(el) == ast.ClassDef:
                    groups.append(el)
                elif getattr(el, 'body', None):
                    tup = Python.separate_namespaces(el)
                    groups += tup[0]
                    nodes += tup[1]
                    body += tup[2]
                else:
                    body.append(el)

        if hasattr(tree, 'orelse'):
            for el in tree.orelse:
                if type(el) == ast.FunctionDef:
                    nodes.append(el)
                elif type(el) == ast.ClassDef:
                    groups.append(el)
                elif getattr(el, 'body', None):
                    tup = Python.separate_namespaces(el)
                    groups += tup[0]
                    nodes += tup[1]
                    body += tup[2]
                else:
                    body.append(el)


        return groups, nodes, body

    @staticmethod
    def make_nodes(tree, parent):
        token = tree.name
        name_from_root = parent.name_from_root + '.' + token
        line_number = tree.lineno
        calls = make_calls(tree.body)
        variables = make_local_variables(tree.body, parent)
        is_constructor = False
        if parent.group_type == GROUP_TYPE.CLASS and token in ['__init__', '__new__']:
            is_constructor = True

        import_tokens = []
        if parent.group_type == GROUP_TYPE.FILE:
            import_tokens = [djoin(parent.token, token)]

        ret = Node(name_from_root, token, calls, variables, parent, import_tokens=import_tokens,
                     line_number=line_number, is_constructor=is_constructor)

        _deal_call_and_variable_pt_call(ret)

        return [ret]

    @staticmethod
    def make_root_node(lines, parent):
        token = "(global)"
        name_from_root = parent.name_from_root + '.' + token
        line_number = 0
        calls = make_calls(lines)
        variables = make_local_variables(lines, parent)
        ret = Node(name_from_root, token, calls, variables, line_number=line_number, parent=parent)
        _deal_call_and_variable_pt_call(ret)
        return ret


    @staticmethod
    def make_class_group(tree, parent):
        assert type(tree) == ast.ClassDef
        subgroup_trees, node_trees, body_trees = Python.separate_namespaces(tree)

        group_type = GROUP_TYPE.CLASS
        token = tree.name
        display_name = 'Class'
        line_number = tree.lineno

        import_tokens = [djoin(parent.token, token)]
        inherits = get_inherits(tree)

        name_from_root = parent.name_from_root +'.'+token

        class_group = Group(name_from_root, token, group_type, display_name, import_tokens=import_tokens,
                            inherits=inherits, line_number=line_number, parent=parent)

        for node_tree in node_trees:
            class_group.add_node(Python.make_nodes(node_tree, parent=class_group)[0])

        for subgroup_tree in subgroup_trees:
            class_group.add_subgroup(Python.make_class_group(subgroup_tree, parent = class_group))

        return class_group

def get_file_scope_assigns(lines):
    def global_process_assign(element):

        if type(element.value) not in  [ast.Call, ast.Name, ast.Attribute]:
            return []
        if type(element.value) == ast.Call:
            right = get_call_from_func_element(element.value.func) 
        elif type(element.value) == ast.Name:
            right = element.value.id
        else:
            assert type(element.value) == ast.Attribute
            if type(element.value.value) !=ast.Name:
                return []
            right = element.value.value.id + "." + element.value.attr

        if right == None:
            return []

        ret = []
        for target in element.targets:
            if type(target) != ast.Name:
                continue
            token = target.id
            ret.append(Variable(token, right, element.lineno))
        return ret

    variables = []
    for tree in lines:
        for element in ast.walk(tree):
            if type(element) == ast.Assign:
                 variables += global_process_assign(element)

    variables = list(filter(None, variables))

    return variables