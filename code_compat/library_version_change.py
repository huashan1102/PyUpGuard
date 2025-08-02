import ast
import os    

def remove_init_dots(elements):
    # 创建一个新的集合，用于存储处理后的元素
    new_elements = set()
    
    # 遍历集合中的每个元素
    for element in elements:
        # 检查元素是否包含 '__init__.' 子串
        if '__init__.' in element:
            # 去除 '__init__.' 并添加到新集合中
            new_elements.add(element)
            new_elements.add(element.replace('__init__.', ''))
        else:
            # 如果不包含 '__init__.'，则直接添加到新集合中
            new_elements.add(element)
    
    return new_elements    

def get_version_change(start_api_dict, target_api_dict):
    
    functions_1 = set(start_api_dict['functions'].keys())
    functions_2 = set(target_api_dict['functions'].keys())
    new_function1 = remove_init_dots(functions_1)
    new_function2 = remove_init_dots(functions_2)
    deprecated_functions =  new_function1 - new_function2

    classes_1 = set(start_api_dict['classes'].keys())
    classes_2 = set(target_api_dict['classes'].keys())
    new_class1 = remove_init_dots(classes_1)
    new_class2 = remove_init_dots(classes_2)
    deprecated_classes =  new_class1 - new_class2

    methods_1 = set(start_api_dict['methods'].keys())
    methods_2 = set(target_api_dict['methods'].keys())
    new_method1 = remove_init_dots(methods_1)
    new_method2 = remove_init_dots(methods_2)
    deprecated_methods =  new_method1 - new_method2

    global_vars_1 = set(start_api_dict['global_vars'])
    global_vars_2 = set(target_api_dict['global_vars'])
    new_golobal_var1 = remove_init_dots(global_vars_1)
    new_golobal_var2 = remove_init_dots(global_vars_2)
    deprecated_global_vars =  new_golobal_var1 - new_golobal_var2 

    return deprecated_functions, deprecated_classes, deprecated_methods, deprecated_global_vars