import ast, os, json

from .extractCall import *
#from extractCall import *
#from utils.util import get_path_by_extension
import re


def get_path_by_extension(root_dir, flag='.py'):
    paths = []
    for root, dirs, files in os.walk(root_dir):
        files = [f for f in files if not f[0] == '.']  # skip hidden files such as git files
        dirs[:] = [d for d in dirs if not d[0] == '.']
        for f in files:
            if f.endswith(flag):
                paths.append(os.path.join(root, f))
    return paths
def getSelfAPI(root,importDict,libName):
    ansLst=[]
    for node in ast.iter_child_nodes(root):
        if isinstance(node,ast.ClassDef):
            if len(node.bases)==0: #只关注有继承的类
                continue
            
            bases=[] #可能含有多个继承
            callLst=[]
            defLst=[]
            
            #收集基类信息
            flag=0
            for it in node.bases:
                base=ast.unparse(it)
                if base.split('.')[0] in importDict:
                    base=importDict[base.split('.')[0]]
                if libName in base:
                    flag=1
                    bases.append(base)
            if flag==0: #基类中是否含有指定的第三方库
                continue

            #收集定义的信息
            for n in ast.iter_child_nodes(node):
                if isinstance(n,ast.FunctionDef):
                    defLst.append(n.name)
            
            #递归搜索call节点
            callVisitor=GetFuncCall()
            callVisitor.dfsVisit(node)
            callInfos=callVisitor.func_call
            for Tuple in callInfos:
                callLst.append(Tuple[0])
            
            ansLst.append((bases,defLst,callLst))
    
    return ansLst


# 每次传进来一个.py文件，抽取所有的调用API
# 返回值是一个字典，key是还原后的API+参数，value是还原前的API+参数
def getCallFunction(filePath,libName):
    with open(filePath,'r',encoding='UTF-8') as f:
        codeText=f.read()
        f.seek(0)
        codeLst=f.readlines()
    try:
        root_node=ast.parse(codeText,filename='<unknown>',mode='exec')

        #找出树中所有的模块名
        import_visitor=Import()
        import_visitor.visit(root_node)
        md_names=import_visitor.get_md_name() #dict


        # 找出树中所有的Call节点
        call_visitor=GetFuncCall()
        call_visitor.dfsVisit(root_node)
        all_func_calls=call_visitor.func_call #[(api1,para1,callState, lineno),(api2,para2, callState, lineno),...()]
        
        # 通过赋值语句和import字典来还原每个调用的API
        apiFormatDict={} #保存还原前的API后还原后的API的对应关系
        '''selfAPIs=[] #保存通过self调用的API'''
        for callName,paraStr,callState,lineno in all_func_calls:
            name_parts=callName.split('.') #按.进行字段拆分
            '''if 'self' in name_parts[0]:
                selfAPIs.append((callName,paraStr,callState,lineno))'''
                # continue
            
            #先通过赋值语句进行还原
            #a=A(x)
            #a.b(y) --> A(x).b(y)
            firstModify=callName #此处只考虑了第一个名字
            #firstModify=''
            #print(firstModify)
            #break
            index=-1 #此处改成直接从源码中按行查找 2023.6.15
            for i in range(len(codeLst)):
                if f"{callName}({paraStr})".replace(' ','') in codeLst[i].replace(' ','').rstrip('\n'):
                    index=i
                    break
            
            if index!=-1:
                index-=1
                while index>=0:
                    s=codeLst[index].replace(' ','').rstrip('\n')
                    if name_parts[0]!='self':
                        if f"{name_parts[0]}="==s[0:len(name_parts[0])+1]:
                            pos=s.find('=')
                            #print(f"{callName}({paraStr})")
                            #print(pos)
                            firstModify=s[pos+1:]+'.'+'.'.join(name_parts[1:])
                            #print(s[pos+1:]+'.'+'.'.join(name_parts[1:]))
                            #break
                    else: #self.a=A(), self.a.f() --> A.f()
                        if len(name_parts)>2 and f"{'.'.join(name_parts[0:2])}=" in s:
                            pos=s.find('=')
                            firstModify=s[pos+1:]+'.'+'.'.join(name_parts[2:])
                            #break
                    index-=1
            
            
            #再将import的别名还原成真名
            #from faker import Fake as A
            # A(x).b(y) --> faker.Fake(x).b(y)
            secondModify=firstModify
            # if 'save' in firstModify:
            #     print(firstModify)

            #print(secondModify)
            #break
            #2024-1-29修改 
            name_parts=secondModify.split('.')
            firstParts=name_parts[0]
            pos=firstParts.find('(')
            if pos!=-1:
                temp=firstParts[0:pos]
                res=firstParts[pos:]
            else:
                temp=firstParts
                res=''
            if temp in md_names:
                secondModify=(md_names[temp]+res+'.'+'.'.join(name_parts[1:])).rstrip('.') #当nameparts只有一个元素的会在最后多个点，需要去掉
                # if 'save' in secondModify:
                #     print(secondModify) 
            #函数名和参数分开放，key和value都是tuple
            apiFormatDict[(secondModify,paraStr,callState,lineno)]=(callName,paraStr,callState,lineno)
        
        # 对self调用的API进行还原
        '''if len(selfAPIs)>0:
            selfInfo=getSelfAPI(root_node,md_names,libName)
            if len(selfInfo)>0: 
                for callName,paraStr,callState,lineno in selfAPIs:
                    name_parts=callName.split('.')
                    for bases,defLst,callLst in selfInfo:
                        if callName in callLst and name_parts[-1] not in defLst:
                            name=bases[0]+'.'+'.'.join(name_parts[1:])
                            apiFormatDict[(name,paraStr,callState,lineno)]=(callName,paraStr,callState,lineno)'''


        #print(type(apiFormatDict))
        #把和指定第三方库相关的callAPI都筛选出来
        callDict={} #词字典用于之后的匹配和变更分析
        for key,value in apiFormatDict.items(): #key是还原后的API，value是还原前的API
            if key[0].split('.')[0]==libName:
                callDict[f"{value[2]}#_{value[3]}"]=f"{key[0]}({key[1]})" #2023.10.23，确保预处理插桩和在目标版本插桩字典的键都是一样的
        #print(callDict)
        #按API的行号从小到大排序,便于之后的插桩 
        #sortedCallDict=dict(sorted(callDict.items(),key=lambda x:int(x[0].split('#_')[-1])))
        #print(sortedCallDict)
        return callDict
    
    except SyntaxError as e:
        #print(f"when extract invoked API, parsed {filePath} failed: {e}")
        return {}     #若对当前文件解析失败，则返回空字典

def getCallFunction_wo_libname(filePath):
    with open(filePath,'r',encoding='UTF-8') as f:
        codeText=f.read()
        f.seek(0)
        codeLst=f.readlines()
    try:
        root_node=ast.parse(codeText,filename='<unknown>',mode='exec')

        #找出树中所有的模块名
        import_visitor=Import()
        import_visitor.visit(root_node)
        md_names=import_visitor.get_md_name() #dict


        # 找出树中所有的Call节点
        call_visitor=GetFuncCall()
        call_visitor.dfsVisit(root_node)
        all_func_calls=call_visitor.func_call #[(api1,para1,callState, lineno),(api2,para2, callState, lineno),...()]
        
        # 通过赋值语句和import字典来还原每个调用的API
        apiFormatDict={} #保存还原前的API后还原后的API的对应关系
        '''selfAPIs=[] #保存通过self调用的API'''
        for callName,paraStr,callState,lineno in all_func_calls:
            name_parts=callName.split('.') #按.进行字段拆分
            '''if 'self' in name_parts[0]:
                selfAPIs.append((callName,paraStr,callState,lineno))'''
                # continue
            
            #先通过赋值语句进行还原
            #a=A(x)
            #a.b(y) --> A(x).b(y)
            firstModify=callName #此处只考虑了第一个名字
            #firstModify=''
            #print(firstModify)
            #break
            index=-1 #此处改成直接从源码中按行查找 2023.6.15
            for i in range(len(codeLst)):
                if f"{callName}({paraStr})".replace(' ','') in codeLst[i].replace(' ','').rstrip('\n'):
                    index=i
                    break
            
            if index!=-1:
                index-=1
                while index>=0:
                    s=codeLst[index].replace(' ','').rstrip('\n')
                    if name_parts[0]!='self':
                        if f"{name_parts[0]}="==s[0:len(name_parts[0])+1]:
                            pos=s.find('=')
                            #print(f"{callName}({paraStr})")
                            #print(pos)
                            firstModify=s[pos+1:]+'.'+'.'.join(name_parts[1:])
                            #print(s[pos+1:]+'.'+'.'.join(name_parts[1:]))
                            #break
                    else: #self.a=A(), self.a.f() --> A.f()
                        if len(name_parts)>2 and f"{'.'.join(name_parts[0:2])}=" in s:
                            pos=s.find('=')
                            firstModify=s[pos+1:]+'.'+'.'.join(name_parts[2:])
                            #break
                    index-=1
            
            
            #再将import的别名还原成真名
            #from faker import Fake as A
            # A(x).b(y) --> faker.Fake(x).b(y)
            secondModify=firstModify
            # if 'save' in firstModify:
            #     print(firstModify)

            #print(secondModify)
            #break
            #2024-1-29修改 
            name_parts=secondModify.split('.')
            firstParts=name_parts[0]
            pos=firstParts.find('(')
            if pos!=-1:
                temp=firstParts[0:pos]
                res=firstParts[pos:]
            else:
                temp=firstParts
                res=''
            if temp in md_names:
                secondModify=(md_names[temp]+res+'.'+'.'.join(name_parts[1:])).rstrip('.') #当nameparts只有一个元素的会在最后多个点，需要去掉
                # if 'save' in secondModify:
                #     print(secondModify) 
            #函数名和参数分开放，key和value都是tuple
            apiFormatDict[(secondModify,paraStr,callState,lineno)]=(callName,paraStr,callState,lineno)
        
        # 对self调用的API进行还原
        '''if len(selfAPIs)>0:
            selfInfo=getSelfAPI(root_node,md_names,libName)
            if len(selfInfo)>0: 
                for callName,paraStr,callState,lineno in selfAPIs:
                    name_parts=callName.split('.')
                    for bases,defLst,callLst in selfInfo:
                        if callName in callLst and name_parts[-1] not in defLst:
                            name=bases[0]+'.'+'.'.join(name_parts[1:])
                            apiFormatDict[(name,paraStr,callState,lineno)]=(callName,paraStr,callState,lineno)'''


        #print(type(apiFormatDict))
        #把和指定第三方库相关的callAPI都筛选出来
        callDict={} #词字典用于之后的匹配和变更分析
        for key,value in apiFormatDict.items(): #key是还原后的API，value是还原前的API
            callDict[f"{value[2]}#_{value[3]}"]=f"{key[0]}({key[1]})" #2023.10.23，确保预处理插桩和在目标版本插桩字典的键都是一样的
        #print(callDict)
        #按API的行号从小到大排序,便于之后的插桩 
        #sortedCallDict=dict(sorted(callDict.items(),key=lambda x:int(x[0].split('#_')[-1])))
        #print(sortedCallDict)
        return callDict
    
    except SyntaxError as e:
        #print(f"when extract invoked API, parsed {filePath} failed: {e}")
        return {}       #若对当前文件解析失败，则返回空字典

def extract_parentheses_content(s):
    # 使用正则表达式匹配括号及其内容，包括括号本身
    match = re.search(r'\(([^()]+(?:\([^)]*\))?[^()]*)\)', s)
    if match:
        # 返回括号内的所有内容（不包括括号本身）
        return match.group(0)
    else:
        return ""

def get_last_part_after_first_parenthesis(s):
    # 按第一个 '(' 分割字符串，返回分割后的最后一部分
    parts = s.split('(', 1)  # 仅分割一次
    return parts[-1] if len(parts) > 1 else parts[0]  # 如果有 '('，返回分割后的最后一部分，否则返回原字符串

def get_all_used_api(data_dir, package_name):
    pkg = data_dir.split('/')[-1]
    pkg_ver = data_dir.split('/')[-2]

    if os.path.exists(f"./extraction/tmp.json"):
        with open("./extraction/tmp.json", "r") as f:
            all_results = json.load(f)
    else:
        all_results = {}
        with open("./extraction/tmp.json", "w") as f:
            json.dump(all_results, f)

    if pkg not in all_results:
        all_results[pkg] = {}
        if pkg_ver not in all_results[pkg]:
            all_results[pkg][pkg_ver] = {}

            all_apis = set()
            new_CallDict = {}
            api_file_map = {}
            api_paras_map = {}
            all_files = get_path_by_extension(data_dir)
            for filename in all_files:
                CallDict = getCallFunction_wo_libname(filename)
                values = CallDict.values()
                for value in values:
                    all_apis.add(value.split('(')[0])
                    api_paras_map[value.split('(')[0]] = "("+get_last_part_after_first_parenthesis(value)
                for key in CallDict:
                    new_value = key.split('(')[0]
                    new_key = CallDict[key].split('(')[0]
                    new_CallDict[new_key] = new_value
                    api_file_map[new_value] = filename
            all_results[pkg][pkg_ver]["all_apis"] = list(all_apis)
            all_results[pkg][pkg_ver]["new_CallDict"] = new_CallDict
            all_results[pkg][pkg_ver]["api_file_map"] = api_file_map
            all_results[pkg][pkg_ver]["api_paras_map"] = api_paras_map
            #print(all_results)
            with open("./extraction/tmp.json", "w") as f:
                json.dump(all_results, f)
    else:
        if pkg_ver not in all_results[pkg]:
            all_results[pkg][pkg_ver] = {}

            all_apis = set()
            new_CallDict = {}
            api_file_map = {}
            api_paras_map = {}
            all_files = get_path_by_extension(data_dir)
            for filename in all_files:
                CallDict = getCallFunction_wo_libname(filename)
                values = CallDict.values()
                for value in values:
                    all_apis.add(value.split('(')[0])
                    api_paras_map[value.split('(')[0]] = "("+get_last_part_after_first_parenthesis(value)
                for key in CallDict:
                    new_value = key.split('(')[0]
                    new_key = CallDict[key].split('(')[0]
                    new_CallDict[new_key] = new_value
                    api_file_map[new_value] = filename
            all_results[pkg][pkg_ver]["all_apis"] = list(all_apis)
            all_results[pkg][pkg_ver]["new_CallDict"] = new_CallDict
            all_results[pkg][pkg_ver]["api_file_map"] = api_file_map
            all_results[pkg][pkg_ver]["api_paras_map"] = api_paras_map
            #print(all_results)
            with open("./extraction/tmp.json", "w") as f:
                json.dump(all_results, f)
    
    all_apis = set()
    for i in all_results[pkg][pkg_ver]["all_apis"]:
        if i.startswith(package_name):
            all_apis.add(i)

    new_CallDict = {}
    for key in all_results[pkg][pkg_ver]["new_CallDict"]:
        if key.startswith(package_name):
            new_CallDict[key] = all_results[pkg][pkg_ver]["new_CallDict"][key]

    api_file_map = {}
    for key in all_results[pkg][pkg_ver]["api_file_map"]:
        if key.startswith(package_name):
            api_file_map[key] = all_results[pkg][pkg_ver]["api_file_map"][key]

    api_paras_map = {}
    for key in all_results[pkg][pkg_ver]["api_paras_map"]:
        if key.startswith(package_name):
            api_paras_map[key.split('.')[-1]] = all_results[pkg][pkg_ver]["api_paras_map"][key]
   
    
    '''all_apis = set()
    new_CallDict = {}
    api_file_map = {}
    api_paras_map = {}
    all_file_names = get_path_by_extension(data_dir)
    for filename in all_file_names:
        CallDict = getCallFunction(filename, package_name)
        values = CallDict.values()
        for value in values:
            all_apis.add(value.split('(')[0])
            api_paras_map[value.split('(')[0].split('.')[-1]] = "("+get_last_part_after_first_parenthesis(value)
        for key in CallDict:
            new_value = key.split('(')[0]
            new_key = CallDict[key].split('(')[0]
            new_CallDict[new_key] = new_value
            api_file_map[new_value] = filename'''
    
    
    return all_apis, new_CallDict, api_file_map, api_paras_map

if __name__ == '__main__':
    path = "/dataset/lei/projects/MASTER-pytorch"
    all_apis, new_CallDict, api_file_map, api_paras_map = get_all_used_api(path, "torch")
    print(len(all_apis))