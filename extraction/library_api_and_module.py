import ast
import os
from .lib_class_attribute_extraction import get_class_attributes_from_file

def get_default_value(node):
    """
    Helper function to get the string representation of the default value of a parameter.
    """
    if isinstance(node, ast.Name):
        return node.id
    elif isinstance(node, ast.Lambda):
        return f"lambda {', '.join([arg.arg for arg in node.args.args])}: ..."
    else:
        try:
            return ast.literal_eval(node)
        except Exception:
            return str(node)

def extract_info_from_py_file(file_path, root_dir):
    res = {"functions": {}, "classes": {}, "methods": {}, "global_vars": []}
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            file_content = file.read()
    except UnicodeDecodeError:
        try:
            with open(file_path, 'r', encoding='latin-1') as file:
                file_content = file.read()
        except:
            return {"functions": {}, "classes": {}, "methods": {}, "global_vars": []}
    
    functions = {}
    classes = {}
    methods = {}
    global_vars = []

    api_params_dict = {}
    
    # Parse the Python file content to AST
    try:
        tree = ast.parse(file_content, filename=file_path)
    except:
        return {"functions": {}, "classes": {}, "methods": {}, "global_vars": []}

    # Convert the file path to a dotted path relative to the root directory
    relative_path = os.path.relpath(file_path, root_dir)
    dotted_path = os.path.splitext(relative_path.replace(os.path.sep, '.'))[0]

    # Traverse the AST nodes
    for node in ast.walk(tree):
        # Collect function definitions (top-level functions)
        if isinstance(node, ast.FunctionDef):
            fstart_line = node.lineno
            res["functions"][f"{root_dir.split('/')[-1]}.{dotted_path}.{node.name}"] = {}
            res["functions"][f"{root_dir.split('/')[-1]}.{dotted_path}.{node.name}"]["lineno"] = fstart_line
            
            # Extract function parameters (with default values if any)
            params = []
            defaults = node.args.defaults  # Get the default values for parameters
            varargs = node.args.vararg  # *args or *shapes
            kwargs = node.args.kwarg  # **kwargs

            # Handle *args or *shapes - placed first
            if varargs:
                params.append(f"*{varargs.arg}")
            
            # Regular positional parameters (without default values)
            regular_params = node.args.args[:len(node.args.args) - len(defaults)]
            for param in regular_params:
                params.append(param.arg)

            # Parameters with default values
            for i, param in enumerate(node.args.args[len(regular_params):]):
                default_value = defaults[i]
                default_value_str = get_default_value(default_value)
                params.append(f"{param.arg}={default_value_str}")
            
            # Handle **kwargs - placed last
            if kwargs:
                params.append(f"**{kwargs.arg}")
            
            # Join parameters into a single string, formatted like (param1, param2=default)
            params_str = ', '.join(params)
            res["functions"][f"{root_dir.split('/')[-1]}.{dotted_path}.{node.name}"]["parameter"] = f"({params_str})" 
        # Collect class definitions
        elif isinstance(node, ast.ClassDef):
            class_name = f"{dotted_path}.{node.name}"
            res["classes"][f"{root_dir.split('/')[-1]}.{class_name}"] = {}
            res["classes"][f"{root_dir.split('/')[-1]}.{class_name}"]["lineno"] = node.lineno
            # Extract class attributes
            class_attributes = get_class_attributes_from_file(file_path, node.name)
            res["classes"][f"{root_dir.split('/')[-1]}.{class_name}"]["attributes"] = class_attributes
            # Collect methods in classes
            for class_node in node.body:
                if isinstance(class_node, ast.FunctionDef):
                    method_start = class_node.lineno
                    #method_end = max(getattr(child, 'lineno', method_start) for child in ast.walk(class_node))
                    res["methods"][f"{root_dir.split('/')[-1]}.{class_name}.{class_node.name}"] = {}
                    res["methods"][f"{root_dir.split('/')[-1]}.{class_name}.{class_node.name}"]["lineno"] = method_start

                    # Extract method parameters (with default values if any)
                    params = []
                    defaults = class_node.args.defaults
                    varargs = class_node.args.vararg  # *args or *shapes
                    kwargs = class_node.args.kwarg  # **kwargs

                    # Handle *args or *shapes - placed first
                    if varargs:
                        params.append(f"*{varargs.arg}")
                    
                    # Regular positional parameters (without default values)
                    regular_params = class_node.args.args[:len(class_node.args.args) - len(defaults)]
                    for param in regular_params:
                        params.append(param.arg)

                    # Parameters with default values
                    for i, param in enumerate(class_node.args.args[len(regular_params):]):
                        default_value = defaults[i]
                        default_value_str = get_default_value(default_value)
                        params.append(f"{param.arg}={default_value_str}")

                    # Handle **kwargs - placed last
                    if kwargs:
                        params.append(f"**{kwargs.arg}")
                    
                    # Join parameters into a single string, formatted like (param1, param2=default)
                    params_str = ', '.join(params)
                    res["methods"][f"{root_dir.split('/')[-1]}.{class_name}.{class_node.name}"]["parameter"] = f"({params_str})"
        # Collect global variables (only simple assignments)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    #print(f"{dotted_path}.{target.id}")
                    res["global_vars"].append(f"{root_dir.split('/')[-1]}.{dotted_path}.{target.id}")
    
    return res

def extract_from_directory(directory):
    results = {
        "functions": {},
        "classes": {},
        "methods": {},
        "global_vars": []
    }
    api_params_dict = {}

    for root, _, files in os.walk(directory):
        for file in files:
            if file.endswith('.py'):
                file_path = os.path.join(root, file)
                res = extract_info_from_py_file(file_path, directory)
                #print(directory)
                results["functions"].update(res["functions"])
                results["classes"].update(res["classes"])
                results["methods"].update(res["methods"])
                results["global_vars"].extend(res["global_vars"])

    return results
