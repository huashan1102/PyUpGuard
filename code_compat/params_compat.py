import os
import re
import copy
import subprocess 


class Parameter():
    def __init__(self):
        self.fullItem=""
        self.name=""
        self.position=""
        self.value=""
        self.type=""
    
        
    def __hash__(self):
        return hash(self.fullItem)
    
    def __eq__(self,other):
        return self.fullItem==other.fullItem

    def __repr__(self):
        return self.fullItem

class Update():
    def __init__(self):
        self.pos=-1
        self.type=''
        self.rename=''
        self.rep=''
        self.value=''
        self.dele=''
        self.addPos='' #增加位置参数
        self.addKey='' #增加关键字参数
        self.pos2key=''
        self.key2pos=''


    def __repr__(self):
        # s=f"name:{self.name}, "
        s=''
        if self.pos:
            s+=f"posChange:{self.pos}, "
        if self.type:
            s+=f"typeChange:{self.type}, "
        if self.dele:
            s+=f"delte:{self.dele}, "
        if self.add:
            s+=f"add:{self.add}, "
        s=s.rstrip(', ')
        return s 


#将参数字符串拆分成单个的参数
#apiName(x,y="<bold>Hello, World!</bold>",z:int,w=(p1,p2={1,(1m,23)}),device: Union[Device, int] = None, abbreviated: bool ={'a','b'}) -> str
#默认按逗号进行拆分,也可按'.'进行拆分，比如a.b.c
#拆分参数的时候没有考虑到x="hello,wolrd"带冒号的情况，会错误拆成两个
def get_parameter(p_string,separator=',',space=1):
    #库定义的参数去空格，项目中的参数不去空格，防止出问题
    if space: #默认是去空格的
        p_string=p_string.replace(' ','') #去掉参数中的空格
    
    if p_string=='':
        return []
    
    parameters=[]
    stack=[]
    count_left_min=0 #统计'('的个数
    count_right_min=0 #统计')'的个数

    count_left_middle=0 #统计'['的个数
    count_right_middle=0 #统计']'的个数

    count_left_hua=0 #统计'{'的个数
    count_right_hua=0 #统计'}'的个数

    count_single_yinhao=0 #统计单引号的引号的个数
    count_double_yinhao=0 #统计双引号的引号的个数

    for index,value in enumerate(p_string):
        stack.append(value)
        if (value=="'" or count_single_yinhao) and not count_double_yinhao: #若上一步出现了双引号，则说明此处的单引号是在双引号内的，所以不计算单引号的个数
            if value=="'":
                count_single_yinhao+=1
            if count_single_yinhao&1:
                continue
        
        elif (value=='"' or count_double_yinhao) and not count_single_yinhao: #若上一步出现了单引号，则说明此处的双引号是在单引号内的，所以不计算双引号的个数
            if value=='"':
                count_double_yinhao+=1
            if count_double_yinhao&1:
                continue
        
        count_single_yinhao=0 #重置为0
        count_double_yinhao=0

        #只计算引号之外的括号是否成对出现 
        if value=='(':
            count_left_min+=1
        elif value==')':
            count_right_min+=1
        
        elif value=='[':
            count_left_middle+=1
        elif value==']':
            count_right_middle+=1

        elif value=='{':
            count_left_hua+=1
        elif value=='}':
            count_right_hua+=1
        
    
        #弹栈,遇到分隔符或达到字符串末尾
        if value==separator:
            flagMin=1 #假设左右括号的个数都是相等的
            flagMid=1
            flagHua=1
            if '(' in stack:
                if count_left_min!=count_right_min:
                    flagMin=0
            if '[' in stack:
                if count_left_middle!=count_right_middle:
                    flagMid=0
            if '{' in stack:
                if count_left_hua!=count_right_hua:
                    flagHua=0

            if flagMin and flagMid and flagHua:
                parameters.append(''.join(stack[0:-1]))
                stack.clear()
    
        elif index==len(p_string)-1:
            parameters.append(''.join(stack))


    return parameters

#去掉API中的参数部分
#比如a.b(x,y(2)).c(z=1).d(w=[(1,2)])变成a.b.c.d
def removeParameter(s,flag=0): 
    if '->' in s: #若有返回值，则把返回值也去掉
        s=s.split('->')[0] 
    if flag==0:   #去掉API中所有参数
        stack=[]
        left=0
        right=0
        ans=''
        for index,value in enumerate(s):
            #进栈
            stack.append(value)
            if value=='(':
                left+=1
            if value==')':
                right+=1
            #出栈
            if left==right and left>0 and right>0:
                pos=stack.index('(')
                ans+=''.join(stack[0:pos])
                stack.clear()
                left=0
                right=0
            elif index==len(s)-1:
              ans+=''.join(stack)
    else:  #只去除最后一个API的参数
        i=len(s)-1
        left=0  #记录左括号的个数
        right=0
        pos=len(s)
        while i>=0:
            if s[i]==')':
                right+=1
            if s[i]=='(':
                left+=1
            if left==right and left>0 and right>0:
                pos=i #更新pos
                break
            i-=1
        ans=s[0:pos]

    return ans

#给文件取名字
def getFileName(fileName,extension):
    #step1:先把fileName中的非法字符去除
    fileName=fileName.replace(' ','')
    fileName=fileName.replace('/','')
    fileName=fileName.replace('\\','')
    length=255-len(extension)
    if len(fileName)>length:
        fileName=fileName[0:length] #如果超出了长度，就进行截断
    fileName+=extension 
    return fileName

def updateErrorLst(errorLog,errorLst):
    with open(errorLog,'a') as fw:
        for it in errorLst:
            fw.write(it)
        fw.write('\n')




#查询字典
def querySharedDict(callAPI,sharedDict):
    ansDict={}
    k=removeParameter(callAPI)
    if k in sharedDict:
        ansDict['current']=sharedDict[k]['current']
        ansDict['target']=sharedDict[k]['target']
        return ansDict
    return ansDict


#更新的操作有两种：添加和修改
def updateSharedDict(callAPI,currentDict,targetDict,sharedDict):
    key=removeParameter(callAPI)
    if key not in sharedDict: #没有就添加
        sharedDict[key]={}
        innerDict=sharedDict[key]
        innerDict['current']=currentDict
        innerDict['target']=targetDict
        sharedDict[key]=innerDict #将修改操作更新到共享字典中
    else: #存在则再看是否需要修改
        innerDict=sharedDict[key]
        if sharedDict[key]['current']['matchMethod']=='static' and currentDict['matchMethod']=='dynamic':
            innerDict['current']=currentDict
        if sharedDict[key]['target']['matchMethod']=='static' and targetDict['matchMethod']=='dynamic':
            innerDict['target']=targetDict
        sharedDict[key]=innerDict #将修改操作更新到共享字典中



#判断两个参数的类型是否发生了变更,只要兼容，就认为相同
#Union[int,float],表示类型是int或float
#Optional[int],表示变量的类型是int或值为None,等价于Union[int,None]
#None即可以表示类型也可以表示值
#Optional[Union[int, str]]表示参数的类型为int,str或None
#Union[Callable[[torch.Tensor,str],torch.Tensor],torch.device,str,Dict[str,str],NoneType]=None
def isDifferType(oldType,newType):
    #先从字面值上判断看是否一样
    if oldType==newType:
        return False  
    #若至少存在一个类型注释为空，则认为二者的类型是相同的
    if oldType=="" or newType=="":
        return False
    #若都存在类型注释且注释不同时，才认为二者的类型不同
    else:
        oldLst=[]
        newLst=[]
        oldTypeSet=set() #将类型构造成集合进行比较
        newTypeSet=set()
        if oldType[0]=="'" and oldType[-1]=="'":
            oldType=oldType[1:-1]
        
        if newType[0]=="'" and newType[-1]=="'":
            newType=newType[1:-1]
        
        if 'Union' in oldType:
            pattern='.*?Union\[(.*)\].*?'
            result=re.findall(pattern,oldType)
            oldLst=get_parameter(result[0])
        elif 'Optional' in oldType:
            pattern='.*?Optional\[(.*)\].*?'
            result=re.findall(pattern,oldType)
            oldLst=get_parameter(result[0])
        elif '|' in oldType:
            oldLst=oldType.split('|')
        else: #当oldType就是一个具体的类型而不是集合时，比如int
            oldLst=[oldType]

        for it in oldLst:
            oldTypeSet.add(it.replace(' ',''))
        


        if 'Union' in newType:
            pattern='.*?Union\[(.*)\].*?'
            result=re.findall(pattern,newType)
            newLst=get_parameter(result[0])
        elif 'Optional' in newType:
            pattern='.*?Optional\[(.*)\].*?'
            result=re.findall(pattern,newType)
            newLst=get_parameter(result[0])
        elif '|' in newType:
            newLst=newType.split('|')
        else:
            newLst=[newType]

        for it in newLst:
            newTypeSet.add(it.replace(' ',''))

        # print(oldTypeSet,'-->', newTypeSet)
        #这里oldTypeSet>0是因为避免空集是任意集合的子集的情况
        if len(oldTypeSet)>0 and oldTypeSet.issubset(newTypeSet):
            return False
        else:
            return newType
    






def para2Obj(paraStr):
    paraStr=paraStr.replace(' ','') #去空格
    paraObjLst=[] #保存参数对象
    if '->' in paraStr: #若有有返回值的话去掉返回值
        paraStr=paraStr.split('->')[0]
    if '(' in paraStr[0]:
        paraStr=paraStr[1:-1]
    
    if paraStr:
        lst=get_parameter(paraStr)
    else:
        lst=[]
    if len(lst)>0:
        if 'self' in lst[0]: #self可能也存在类型注释
            lst.remove(lst[0])
        elif 'cls' in lst[0]:
            lst.remove(lst[0])
    for para in lst:
        parameter=Parameter()
        parameter.position=lst.index(para) #当列表中有相同元素时，lst.index会出现问题,但库定义中不会出现相同的参数
        parameter.fullItem=para
        flagMaohao=0
        if ':' in para:
            pos=para.find(':')
            flagMaohao=1 
        
        if flagMaohao and "'" not in para[0:pos] and '"' not in para[0:pos] and '<' not in para[0:pos]: #参数值为字符串时，字符串中也可能出现冒号
            l=para.split(':')
            parameter.name=l[0]
            if '=' in l[1]:
                ll=l[1].split('=')
                parameter.type=ll[0]
                parameter.value=ll[1]
            else:
                parameter.type=l[1]
        elif '=' in para:
            l=para.split('=')
            parameter.name=l[0]
            parameter.value=l[1]
        else:
            parameter.name=para
        paraObjLst.append(parameter)
    
    pos=len(paraObjLst)
    posStar=-1 #记录*的位置
    pos2Star=-1 #记录**的位置, 防止出现(x, y, **kwargs)的形式
    for para in paraObjLst:
        if '**' in para.name:
            pos2Star=para.position
        elif '*' in para.name:
            posStar=para.position
            break
    if posStar!=-1: #优先根据*号拆分
        pos=posStar
    elif pos2Star!=-1:
        pos=pos2Star
    
    posParameters=paraObjLst[0:pos]
    keyParameters=[]
    for para in paraObjLst[pos+1:]:
        if '**' not in para.name:
            keyParameters.append(para)
    
    return posParameters,keyParameters
        



#输入两个api参数部分，判断参数部分有何不同
def findDiffer(oldPara,newPara):
    oldPos,oldKey=para2Obj(oldPara) 
    newPos,newKey=para2Obj(newPara)
    oldPosParaNum=len(oldPos)
    dic={} #保存每个参数应该做哪些修改操作
    #第一轮筛选，先根据名字来找对应关系
    #处理位置参数
    for oldPara in copy.deepcopy(oldPos):
        sameFlag=0
        for newPara in newPos:
            if oldPara.name==newPara.name:
                up=Update()
                if oldPara.position!=newPara.position:
                    up.pos=newPara.position
                ty=isDifferType(oldPara.type,newPara.type)
                if ty: 
                    up.type=ty
                sameFlag=1
                oldPos.remove(oldPara)
                newPos.remove(newPara)
                break
        if sameFlag==1:
            dic[(oldPara.name,oldPara.position)]=up
    
    #处理关键字参数,旧版中没有找到相同名字的参数可能是重命名或删除了
    for oldPara in copy.deepcopy(oldKey):
        sameFlag=0
        for newPara in newKey:
            if oldPara.name==newPara.name:
                up=Update()
                ty=isDifferType(oldPara.type,newPara.type)
                if ty:
                    up.type=ty
                sameFlag=1
                oldKey.remove(oldPara)
                newKey.remove(newPara)
                break
        if sameFlag==1:
            dic[(oldPara.name,oldPara.position)]=up



    #第二轮筛选，根据名字找对应关系，判断是否存在位置参数变到了关键字参数
    for oldPara in copy.deepcopy(oldPos):
        sameFlag=0
        for newPara in newKey:
            if oldPara.name==newPara.name:
                up=Update()
                up.pos2key=oldPara.name #位置参数变成关键字参数
                ty=isDifferType(oldPara.type,newPara.type)
                if ty:
                    up.type=ty
                sameFlag=1
                oldPos.remove(oldPara)
                newKey.remove(newPara)
                break
        if sameFlag==1:
            dic[(oldPara.name,oldPara.position)]=up


    #再判断是否有关键字参数(起始版本)变到了位置参数(目标版本)
    for oldPara in copy.deepcopy(oldKey):
        sameFlag=0
        for newPara in copy.deepcopy(newPos):
            if oldPara.name==newPara.name:
                print(f"key2pos-->{oldPara.name}")
                up=Update()
                up.key2pos=oldPara.name
                ty=isDifferType(oldPara.type, newPara.type)
                if ty:
                    up.type=ty
                sameFlag=1
                oldKey.remove(oldPara)
                newPos.remove(newPara)
                break
        if sameFlag==1:
            dic[(oldPara.name,oldPara.position)]=up



    
    #第三轮筛选，根据对应位置和类型来筛选剩余的位置参数，判断其是否发生了重命名
    for oldPara in copy.deepcopy(oldPos):
        sameFlag=0
        for newPara in newPos:
            if oldPara.position==newPara.position and not isDifferType(oldPara.type,newPara.type): #这里需要加一个类型相同约束吗
                up=Update()
                if oldPara.name!=newPara.name: #参数发生了重命名
                    up.rename=newPara.name
                ty=isDifferType(oldPara.type,newPara.type)
                if ty:
                    up.type=ty
                sameFlag=1
                oldPos.remove(oldPara)
                newPos.remove(newPara)
                break
        if sameFlag==1:
            dic[(oldPara.name,oldPara.position)]=up
        else:#oldPos中剩下的就是删除的
            oldPos.remove(oldPara)
            up=Update()
            up.dele=1
            dic[(oldPara.name,oldPara.position)]=up

    #第四轮筛选，根据类型来判断，剩余的关键字参数是否发生了重命名
    for oldPara in copy.deepcopy(oldKey):
        sameFlag=0
        for newPara in newKey:
            if oldPara.type==newPara.type:
                sameFlag=1
                up=Update()
                up.rename=newPara.name
                oldKey.remove(oldPara)
                newKey.remove(newPara)
                break
        if sameFlag==1:
            dic[(oldPara.name,oldPara.position)]=up
        else:
            oldKey.remove(oldPara)
            up=Update()
            up.dele=1
            dic[(oldPara.name,oldPara.position)]=up
            

    #newPos中剩下的就是替换或新增的
    for para in newPos:
        s=f'{para.name}'
        if para.value:
            s+=f"={para.value}"
        if para.position>=0 and para.position<oldPosParaNum: #如果剩余参数的下标在旧版本参数下标的范围内，则认为是替换操作,反之则认为是新增的
            for key in dic:
                if key[1]==para.position:
                    dic[key].rep=s
                    break
        else:
            up=Update()
            up.addPos=s
            dic[(para.name,para.position)]=up
    
    #newKey中剩下的就是新增的,新增的关键字参数往往都带有默认值，一般不会引起兼容性问题
    for para in newKey:
        s=para.name
        if para.value:
            s+=f"={para.value}"
        up=Update()
        up.addKey=s
        dic[(para.name,para.position)]=up


    #构建修改操作的字典
    updateDict={}
    for key,value in dic.items():
        if key not in updateDict:
            updateDict[key]={}
        if value.dele:
            updateDict[key]['delete']=value.dele
        if value.type:
            updateDict[key]['typeChange']=value.type
        if value.rename:
            updateDict[key]['rename']=value.rename
        if value.pos!=-1:
            updateDict[key]['posChange']=value.pos
        if value.rep:
            updateDict[key]['replace']=value.rep
        if value.pos2key:
            updateDict[key]['pos2key']=value.pos2key
        if value.addPos:
            updateDict[key]['addPos']=value.addPos
        if value.addKey:
            updateDict[key]['addKey']=value.addKey

        if value.key2pos:
            updateDict[key]['key2pos']=value.key2pos
    
    #对字典按照参数的位置进行排序
    ansDict=dict(sorted(updateDict.items(), key=lambda it: it[0][1])) #it[0]代表字典的键，it[0][1]代表键中的第二个元素,即位置
    return ansDict



#判断两个重载API是否兼容
#分位置参数和关键字参数进行分析
#判断标准
#位置参数：位置和名称相同，且类型兼容，认为兼容
#关键字参数：名字相同且类型兼容，认为兼容
def analyzeCompatibility(oldPara,newPara, actual_usage, parse_args):
    #将其转化为参数对象
    oldPara_str = oldPara
    oldPos,oldKey=para2Obj(oldPara)
    #print(type(oldPara))
    newPos,newKey=para2Obj(newPara)
    actualPos, actualKey = para2Obj(actual_usage)
    #print(parse_args)
    #print(f"actualPos:{actualPos},actualKey:{actualKey}")
    #分析位置参数
    if "*args" in newPara:
        return True
    for oldPara in oldPos:
        if oldPara.name.startswith('*'):
            continue
        flag=0
        for newPara in newPos:
            #print(f"oldPara:{oldPara.name},newPara:{newPara.name}, oldPos:{oldPara.position},newPos:{newPara.position}, oldType:{oldPara.type},newType:{newPara.type},{oldPara.value}")
            #if oldPara.name==newPara.name and oldPara.position==newPara.position and not isDifferType(oldPara.type,newPara.type):
            if oldPara.name==newPara.name and not isDifferType(oldPara.type,newPara.type):
                #print(f"pos-->{oldPara.name}")
                flag=1
                break
        new_flag = 1
        for actualPara in actualPos:
            #print(actualPara.name)
            if oldPara.name==actualPara.name:
                new_flag = 0
                break
        if flag==0 and new_flag == 0: #若旧版本的位置参数没有在新版本中找到对应的参数，且实际调用使用了，则不兼容
            if oldPara.value!='': #若旧版本的位置参数不带默认值
                continue
            print("*")
            print(oldPara)
            return False
    
    #再分析新增的位置参数
    for newPara in newPos:
        flag = 0
        if newPara.position>=len(oldPos) and  len(actualPos) > len(oldPos):
            if newPara.value=='': #若新增的位置参数不带默认值
                #解决start_param:(g), target_param:(g, shapes, dtype), actual_usage:(shape, dtype=torch.float32)
                for key in actualPos:
                    if key.name==newPara.name:
                        #print(f"addPos-->{newPara.name}")
                        flag = 1
                        break
                if flag == 1:
                    continue
                if len(parse_args) + len(actualPos) >= len(newPos):
                    break
                s = f"{newPara}"
                if s.endswith("="):
                    continue
                print("*#")
                return False

    #分析关键字参数
    for oldPara in oldKey:
        flag=0
        for newPara in newKey:
            if oldPara.name==newPara.name and not isDifferType(oldPara.type,newPara.type):
                flag=1
                break

        #再判断关键字参数是否变成了位置参数(这种改变是兼容的)
        if flag==0:
            for newPara in newPos:
                if oldPara.name==newPara.name and not isDifferType(oldPara.type,newPara.type):
                    flag=1
                    print(f"key2pos-->{oldPara.name}")
                    break

        if flag==0:
            print("*#$")
            return False
    
    #再分析新增的关键字参数
    #比如(*,x,y) --> (*,x,y,z)，其中z就是新增的
    for newPara in newKey:
        if newPara.name.startswith('*'):
            continue
        flag=0
        for oldPara in oldKey:
            if newPara.name==oldPara.name: #若找到同名的，则不是新增的
                flag=1
                break
        
        if '*' in oldPara_str:
            flag = 1
        if newPara.name in "**kwargs":
            flag = 1
        if flag==0:
            if newPara.value=='': #若新增的关键字参数不带默认值
                print("*#$%")
                return False
    
    return True