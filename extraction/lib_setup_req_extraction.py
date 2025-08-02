import os
import ast
from subprocess import run

def to_skip_line(line):
    if line.startswith(r'#') or len(line) == 0:
        return True
    if line.startswith(r"-") or line.startswith(r"."):
        return True
    https_idx = line.find(r"https:")
    http_idx = line.find(r"http:")
    fenhao_idx = line.find(r";")
    pound_idx = line.find(r"#")
    if https_idx != -1 or http_idx != -1 or fenhao_idx != -1:
        if pound_idx == -1 or pound_idx > max(https_idx, http_idx, fenhao_idx):
            return True
    return False


def delete_whitespace_and_comments(line):
    pound_idx = line.find(r"#")
    if pound_idx != -1:
        line = line[:pound_idx]
    line = line.replace(' ', '')
    return line


def split_packname_and_cons(line):
    version_ops = [r'<', r'<=', r'!=', r'==', r'>=', r'>', r'~=', r'===']
    min_op_idx = None
    for op in version_ops:
        if line.find(op) != -1:
            if min_op_idx == None:
                min_op_idx = line.find(op)
            else:
                min_op_idx = min(min_op_idx, line.find(op))
    res = []
    if min_op_idx != None:
        res.append(line[:min_op_idx])
        res.append(line[min_op_idx:])
    else:
        res.append(line)
    for i in range(len(res)):
        res[i]=res[i].replace(" ","")
    return res


def read_txt(txt_path):

    clean_lines = []
    try:
        with open(txt_path, 'r', encoding="UTF-8") as f:
            file = f.read()

            for line in file.splitlines():
                line = delete_whitespace_and_comments(line)
                if to_skip_line(line):
                    continue
                clean_lines.append(line)

    except UnicodeDecodeError:
        with open(txt_path, 'r', encoding="UTF-16") as f:
            file = f.read()

            for line in file.splitlines():
                line = delete_whitespace_and_comments(line)
                if to_skip_line(line):
                    continue
                clean_lines.append(line)

    return clean_lines


def get_packname_and_cons(txt_path):
    if txt_path==None:
        return []
    clean_lines = read_txt(txt_path)
    packname_and_cons_res = []
    for line in clean_lines:
        packname_and_cons = split_packname_and_cons(line)
        packname_and_cons_res.append(packname_and_cons)


    return packname_and_cons_res


def get_tree(filename):
    def get_tree_with_feature_version(filename, feature_version=None):
        """
        Get the entire AST for this file

        :param filename str:
        :rtype: ast
        """
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
            print("Could not change %r to python3 (%r) Skipping...", filename, ae)
            raise SyntaxError
        except SyntaxError as se:
            if os.path.exists(py3_py):
                os.remove(py3_py)
            raise SyntaxError

    def get_tree_with_feature_version(filename, feature_version=None):
        """
        Get the entire AST for this file

        :param filename str:
        :rtype: ast
        """
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
            print("Could not change %r to python3 (%r) Skipping...", filename, ae)
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


def get_packname_and_cons_from_setup(setupfilepath):
    try:
        r_node = get_tree(setupfilepath)
    except SyntaxError:
        return []

    install_requires = None
    res = []
    for element in ast.walk(r_node):
        if type(element) == ast.Call and ((type(element.func) == ast.Name and element.func.id == "setup") or
                                          ((type(element.func) == ast.Attribute and type(element.func.value)==ast.Name and element.func.value.id == "setuptools" and element.func.attr=="setup"))):
            for keyword in element.keywords:
                if keyword.arg in ["install_requires","setup_requires"]:
                    install_requires = keyword.value
                    break

            if install_requires == None:
                pass

            break

    if install_requires == None:
        return []

    if type(install_requires) not in [ast.Name, ast.List]:
        return []

    assert type(install_requires) in [ast.Name, ast.List]
    if type(install_requires) == ast.Name:
        to_search_str = install_requires.id
        install_requires = None
        for element in ast.walk(r_node):
            if type(element) == ast.Assign:
                for target in element.targets:
                    if hasattr(target, "id") and target.id == to_search_str and hasattr(element, "value") and type(element.value) == ast.List:
                        install_requires = element.value

    if install_requires == None:
        return []

    assert type(install_requires) == ast.List
    for single_req in install_requires.elts:
        if type(single_req) == ast.BinOp:
            continue

        assert type(single_req) in [ast.Str, ast.Constant]
        if type(single_req)==ast.Str:
            res.append(split_packname_and_cons(single_req.s))
        else:
            res.append(split_packname_and_cons(single_req.value))



    return res