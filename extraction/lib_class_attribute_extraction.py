import ast

class ClassAttributeExtractor(ast.NodeVisitor):
    def __init__(self):
        self.class_attributes = {}

    def visit_ClassDef(self, node):
        attributes = []
        for body_item in node.body:
            # 处理 __init__ 方法
            if isinstance(body_item, ast.FunctionDef) and body_item.name == "__init__":
                self.extract_attributes_from_init(body_item.body, attributes)
        self.class_attributes[node.name] = attributes
        self.generic_visit(node)

    def extract_attributes_from_init(self, statements, attributes):
        # 递归处理 __init__ 方法的所有语句，提取 self.属性 赋值
        for stmt in statements:
            if isinstance(stmt, ast.Assign):
                for target in stmt.targets:
                    if isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name) and target.value.id == "self":
                        attributes.append(target.attr)
            elif isinstance(stmt, (ast.For, ast.While)):
                # 处理循环体内的赋值
                self.extract_attributes_from_init(stmt.body, attributes)
            elif isinstance(stmt, ast.If):
                # 处理条件语句内的赋值
                self.extract_attributes_from_init(stmt.body, attributes)
                self.extract_attributes_from_init(stmt.orelse, attributes)

def get_class_attributes_from_file(file_path, class_name):
    try:
        res = []
        with open(file_path, 'r', encoding='utf-8') as file:
            source_code = file.read()

        # 解析源代码为 AST
        tree = ast.parse(source_code)
        extractor = ClassAttributeExtractor()
        extractor.visit(tree)

        for name, attributes in extractor.class_attributes.items():
            if name == class_name:
                res.extend(attributes)
        return res
    except:
        return []

if __name__ == '__main__':
    file_path = '/home/lei/compatibility_analysis/DC/project/src/lib_extraction/test.py'
    class_name = 'MyClass'