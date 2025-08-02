from z3 import Int, And, Or, simplify, Optimize

def build_order_dict(pkg_dict):
    int_dict = {pkg: Int(pkg) for pkg in pkg_dict}
    order_dict = {
        pkg: {ver: idx for idx, ver in enumerate(ver_dict)}
        for pkg, ver_dict in pkg_dict.items()
    }
    return int_dict, order_dict

def process_dependencies(deps):
    smt_deps = {}
    for dep in deps:
        dep_pkg, dep_ver = dep.split("#")
        smt_deps.setdefault(dep_pkg, []).append(dep_ver)
    return smt_deps

def create_dependency_expr(dep_pkg, smt_vers, int_dict, order_dict):
    if len(smt_vers) == 1 and smt_vers[0] == 'True':
        return Or(*[int_dict[dep_pkg] == ver_id for ver_id in order_dict[dep_pkg].values()])
    
    expr = Or()
    for smt_ver in smt_vers:
        if smt_ver in ('False', 'True'):
            continue
        ver_id = order_dict[dep_pkg].get(smt_ver)
        if ver_id is not None:
            expr = Or(expr, int_dict[dep_pkg] == ver_id)
    return simplify(expr)

def add_dependency_constraints(solver, pkg_dict, order_dict, int_dict):
    for pkg, ver_dict in pkg_dict.items():
        constraints = []
        for ver, deps in ver_dict.items():
            if ver == 'False':
                constraints.append(And(False))
                continue

            ver_id = order_dict[pkg][ver]
            smt_deps = process_dependencies(deps)
            dep_constraints = [
                create_dependency_expr(dep_pkg, smt_vers, int_dict, order_dict)
                for dep_pkg, smt_vers in smt_deps.items()
            ]
            constraints.append(simplify(And(int_dict[pkg] == ver_id, *dep_constraints)))

        constrain = simplify(Or(*constraints, int_dict[pkg] == len(order_dict[pkg])))
        solver.add(constrain)
    
    return solver

def add_install_constraints(solver, constrain_version_dict, order_dict, int_dict):
    for pkg, versions in constrain_version_dict.items():
        expr = Or(*[
            simplify(Or(int_dict[pkg] == order_dict[pkg][ver]))
            for ver in versions
            if ver in order_dict[pkg]
        ]) if versions else False
        solver.add(expr)
    return solver

def parse_z3_model(model, int_dict, order_dict):
    pkg_versions = {}
    for pkg, var in int_dict.items():
        ver_ind = model[var].as_long()
        ver = next((k for k, v in order_dict[pkg].items() if v == ver_ind), None)
        if ver:
            pkg_versions[pkg] = ver
    return pkg_versions

def solving_constraints(pkg_dict, install_dict):
    int_dict, order_dict = build_order_dict(pkg_dict)
    solver = Optimize()
    solver = add_dependency_constraints(solver, pkg_dict, order_dict, int_dict)
    
    reversed_install_dict = {pkg: list(reversed(versions)) for pkg, versions in install_dict.items()}
    solver = add_install_constraints(solver, reversed_install_dict, order_dict, int_dict)
    
    for var in int_dict.values():
        solver.maximize(var)

    try:
        if solver.check():
            return parse_z3_model(solver.model(), int_dict, order_dict)
        return None
    except:
        return None

'''from z3 import Int, And, Or, simplify, Optimize
def build_order_dict(pkg_dict):
    order_dict = dict()
    int_dict = {}
    for pkg in pkg_dict:
        ver_dict = pkg_dict[pkg]
        order_dict[pkg] = dict()
        ind = 0
        int_dict[pkg] = Int(pkg)
        versions = list(ver_dict.keys())
        #has_versions = [v for v in versions if v != 'False']
        #sorted_versions = sorted(has_versions, key=cmp_to_key(cmp_version)) 
        for ver_ in versions:
            order_dict[pkg][ver_] = ind
            ind += 1

    #print(order_dict)
    return int_dict,order_dict


def add_dependency_constrains(solver, pkg_dict, order_dict, int_dict):

    for pkg in pkg_dict:
        ver_dict = pkg_dict[pkg]
        ands = list()
        for ver in ver_dict:
            if ver == 'False':
                ands.append(And(False))  
                continue
            id_ver = order_dict[pkg][ver]
            
            deps = ver_dict[ver].copy()
            ors = list()
            smt_deps = {}
            for dep in deps:  
                dep_pkg, dep_ver = dep.split("#")
                if dep_pkg not in smt_deps:
                    smt_deps[dep_pkg] = []

                smt_deps[dep_pkg].append(dep_ver)
            
            for dep_pkg in smt_deps:
                expr1 = Or()
                if len(smt_deps[dep_pkg])==1 and smt_deps[dep_pkg][0] == 'True': 
                    for v_ in order_dict[dep_pkg]:
                        dep_id = order_dict[dep_pkg][v_]
                        expr = Or(int_dict[dep_pkg]== dep_id)
                        expr1 = Or(expr1,expr)
                        expr1 = simplify(expr1) 

                else:
                    for smt_ver in smt_deps[dep_pkg]:
                        if smt_ver == 'False': 
                            expr = Or(False)  #
                        elif smt_ver == 'True':  
                            print(dep_pkg,'------------')
                            continue  

                        else:
                            try:
                                dep_id = order_dict[dep_pkg][smt_ver]
                            except:
                                continue
                            expr = Or(int_dict[dep_pkg]== dep_id)
                        expr1 = Or(expr1,expr)
                        expr1 = simplify(expr1)  
               

                ors.append(expr1)
            and_expr = And(int_dict[pkg] == id_ver)
            for expr in ors:
                and_expr = And(and_expr, expr)
                and_expr = simplify(and_expr)

            ands.append(and_expr)

    
        constrain = Or()
        for expr in ands:
            constrain = Or(constrain, expr)
            constrain = simplify(constrain)
 
        constrain = simplify(constrain)
        
        # May filter such dependency
        more_id_ver = len(order_dict[pkg].keys())
        constrain = Or(constrain, int_dict[pkg] == more_id_ver)

        solver.add(constrain)
    return solver

def add_install_constrains(solver, constrain_version_dict, order_dict, int_dict):
    # as long as this is satisfied
    for pkg in constrain_version_dict:
        versions = constrain_version_dict[pkg]
        constrain = Or()
        for ver in versions:
            try:
                id_ver = order_dict[pkg][ver]
            except:
                continue
            if id_ver == 'False':
                constrain = Or(False)
            else:
                constrain = Or(constrain, int_dict[pkg] == id_ver)
            constrain = simplify(constrain)

        solver.add(constrain)
    return solver

def parse_z3_model(model, int_dict, order_dict):
    pkgvers = dict()
    for pkg in int_dict:
        var = int_dict[pkg]
        ver_ind = model[var]
        vers = [k for k, v in order_dict[pkg].items() if v == ver_ind] 

        if len(vers) == 0:
            continue  
        else:
            ver = vers[0] 
        pkgvers[pkg] = ver
    return pkgvers


def solving_constraints(pkg_dict, install_dict):
    int_dict, order_dict = build_order_dict(pkg_dict)
    solver = Optimize()
    solver = add_dependency_constrains(solver, pkg_dict, order_dict, int_dict)
    new_install_dict = {}
    for pkg in install_dict:
        new_values = install_dict[pkg]
        new_install_dict[pkg] = list(reversed(new_values))
    solver = add_install_constrains(solver, new_install_dict, order_dict, int_dict) 
    #solver.set("parallel", 4)  # 设置为使用 4 个线程
    #solver.set(timeout=60000)  # 设置超时限制为60秒
    #print(pkg_dict["torchvision"]["0.11.0"])
    for pkg in int_dict:
        var = int_dict[pkg]
        solver.maximize(var)  

    try:
        if solver.check():
            pkgvers = parse_z3_model(solver.model(), int_dict, order_dict)
            return pkgvers
        else:
            return None
    except:
        return None'''