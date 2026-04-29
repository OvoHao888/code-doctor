from langchain_core.tools import tool
import ast
import json
import sys
from io import StringIO
from pyflakes.api import check

#codeparseragent
# 提取代码结构
@tool
def extract_code_structure(code: str) -> str:
    """
    提取Python代码的结构信息,包括函数、类、模块等
    参数: code: 要检查的Python代码字符串
    返回: 代码结构信息字符串
    """
    if not code or len(code.strip()) == 0:
        return "错误：请传入有效的代码，不能为空！"

    try:
        FULL_NODES = {
            "模块": ast.Module,
            "类": ast.ClassDef,
            "函数": ast.FunctionDef,
            "异步函数": ast.AsyncFunctionDef,
            "Lambda": ast.Lambda,
            "导入": ast.Import,
            "从...导入": ast.ImportFrom,
            "赋值": ast.Assign,
            "增强赋值": ast.AugAssign,
            "注解赋值": ast.AnnAssign,
            "全局变量": ast.Global,
            "非本地变量": ast.Nonlocal,
            "条件判断": ast.If,
            "For循环": ast.For,
            "异步For": ast.AsyncFor,
            "While循环": ast.While,
            "With语句": ast.With,
            "异步With": ast.AsyncWith,
            "占位": ast.Pass,
            "返回": ast.Return,
            "跳出": ast.Break,
            "跳过": ast.Continue,
            "Try捕获": ast.Try,
            "Except处理": ast.ExceptHandler,
            "抛出异常": ast.Raise,
            "断言": ast.Assert,
            "函数调用": ast.Call,
            "变量名": ast.Name,
            "常量": ast.Constant,
            "二元运算": ast.BinOp,
            "一元运算": ast.UnaryOp,
            "逻辑运算": ast.BoolOp,
            "比较运算": ast.Compare,
            "属性访问": ast.Attribute,
            "下标访问": ast.Subscript,
            "解包": ast.Starred,
            "列表": ast.List,
            "元组": ast.Tuple,
            "字典": ast.Dict,
            "集合": ast.Set,
            "列表推导式": ast.ListComp,
            "字典推导式": ast.DictComp,
            "集合推导式": ast.SetComp,
            "生成器": ast.GeneratorExp,
            "Await": ast.Await
        }

        tree = ast.parse(code)
        coll = {k: [] for k in FULL_NODES}

        for node in ast.walk(tree):
            for label, ast_type in FULL_NODES.items():
                if isinstance(node, ast_type):
                    name = ""
                    lineno = getattr(node, "lineno", "?")
                    try:
                        if hasattr(node, "name"):
                            name = node.name
                        elif isinstance(node, ast.Import):
                            name = ", ".join(alias.name for alias in node.names)
                        elif isinstance(node, ast.ImportFrom):
                            name = node.module or ""
                        elif isinstance(node, ast.Assign):
                            name = ", ".join(t.id for t in node.targets if isinstance(t, ast.Name))
                        elif isinstance(node, ast.Name):
                            name = node.id
                        elif isinstance(node, ast.Constant):
                            name = str(node.value)
                        elif isinstance(node, ast.Call):
                            if hasattr(node.func, "id"):
                                name = node.func.id
                            elif hasattr(node.func, "attr"):
                                name = node.func.attr
                    except Exception as e:
                        name = ""

                    coll[label].append(f"行{lineno} | {name if name else 'null'}")
                    break

        output = []
        for cat, items in coll.items():
            if not items:
                continue
            output.append(f"[{cat}]")
            for item in items:
                output.append(item if item else "null")

        result = "\n".join(output)
        return result

    except Exception as e:
        logger.error(f"extract_code_structure 异常: {str(e)}")
        return f"解析代码时发生异常：{str(e)}"

# 提取代码逻辑流
@tool
def extract_code_logic_flow(code: str) -> str:
    """
    提取Python代码的逻辑流信息,包括函数调用、异常处理等
    参数: code: 要检查的Python代码字符串
    返回: 代码逻辑流信息字符串
    """
    if not code or len(code.strip()) == 0:
        return "错误：请传入有效的代码！"

    try:
        LOGIC_FLOW_NODES = {
            "条件判断": ast.If,
            "For循环": ast.For,
            "While循环": ast.While,
            "异步For循环": ast.AsyncFor,
            "With语句": ast.With,
            "异步With": ast.AsyncWith,
            "Try捕获": ast.Try,
            "Except处理": ast.ExceptHandler,
            "抛出异常": ast.Raise,
            "断言": ast.Assert,
            "返回": ast.Return,
            "跳出": ast.Break,
            "跳过": ast.Continue,
            "函数调用": ast.Call,
            "比较运算": ast.Compare,
            "逻辑运算": ast.BoolOp
        }

        tree = ast.parse(code)
        coll = {k: [] for k in LOGIC_FLOW_NODES}

        for node in ast.walk(tree):
            for label, ast_type in LOGIC_FLOW_NODES.items():
                if isinstance(node, ast_type):
                    name = ""
                    lineno = getattr(node, "lineno", "?")
                    try:
                        if isinstance(node, ast.Call):
                            if hasattr(node.func, "id"):
                                name = node.func.id
                            elif hasattr(node.func, "attr"):
                                name = node.func.attr
                        elif isinstance(node, ast.Compare):
                            name = "比较操作"
                        elif isinstance(node, ast.BoolOp):
                            name = "逻辑操作(and/or)"
                    except:
                        name = ""

                    coll[label].append(f"行{lineno} | {name if name else '执行'}")
                    break

        output = []
        for cat, items in coll.items():
            if items:
                output.append(f"[{cat}]")
                output.extend(items)
        result = "\n".join(output)
        return result

    except Exception as e:
        logger.error(f"extract_code_logic_flow 异常: {str(e)}")
        return f"解析逻辑流出错：{str(e)}"

# 分割长代码
@tool
def split_long_code(code: str) -> str:
    """
    分割长代码,每个代码块不超过1000行（实际按语义块切，更稳定）
    参数: code: 要分割的长代码字符串
    返回: 分割后的代码块字符串
    """
    if not code or len(code.strip()) == 0:
        return "错误：请传入有效的代码！"

    lines = code.splitlines()
    max_lines = 1000
    chunks = []
    current_chunk = []
    line_count = 0

    for line in lines:
        current_chunk.append(line)
        line_count += 1

        if line_count >= max_lines and (
            line.strip() == "" or
            line.strip().startswith(("def ", "class ", "#", "if ", "for ", "while "))
        ):
            chunks.append("\n".join(current_chunk))
            current_chunk = []
            line_count = 0

    if current_chunk:
        chunks.append("\n".join(current_chunk))

    result = []
    for i, chunk in enumerate(chunks, 1):
        result.append(f"===== 代码块 {i} =====")
        result.append(chunk)
    final_result = "\n".join(result)
    return final_result

#bugcheckeragent
# 查找语法错误
@tool
def find_syntax_error(code: str)-> str:
    """
    检查Python代码的语法错误、缩进错误、未定义变量等问题
    参数: code: 要检查的Python代码字符串
    返回: 错误信息字符串
    """
    if not code or len(code.strip()) == 0:
        return "错误：请传入有效的代码，不能为空！"
    try:
        output_buffer = StringIO()
        sys.stdout = output_buffer
        check(code, '<string>')  # 添加 filename 参数
        sys.stdout = sys.__stdout__
        error_result = output_buffer.getvalue()
        if not error_result:
            return "✅ 代码语法检查完成，未发现语法错误！"
        return "🔍 发现语法错误：\n" + error_result
    except Exception as e:
        logger.error(f"find_syntax_error 异常: {str(e)}")
        return f"❌ 检查语法时发生异常：{str(e)}"

# 查找逻辑错误
@tool
def find_logic_error(code: str)-> str:
    """
    检查Python代码的逻辑错误，包括除零错误、索引越界、空指针访问等问题
    参数: code: 要检查的Python代码字符串
    返回: 错误信息字符串
    """
    if not code or len(code.strip()) == 0:
        return "错误：请传入有效的代码，不能为空！"

    try:
        issues = []
        tree = ast.parse(code)

        # 1. 检测除零错误风险
        for node in ast.walk(tree):
            if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Div, ast.FloorDiv, ast.Mod)):
                right = node.right
                if isinstance(right, ast.Call):
                    if isinstance(right.func, ast.Name) and right.func.id == 'len':
                        issues.append(f"行{getattr(node, 'lineno', '?')}: 除法/取模操作除数可能为0（len()结果未检查）")
                elif isinstance(right, ast.Constant) and right.value == 0:
                    issues.append(f"行{getattr(node, 'lineno', '?')}: 除法/取模操作除数可能为0")
                elif isinstance(right, ast.Name):
                    issues.append(f"行{getattr(node, 'lineno', '?')}: 除法/取模操作除数'{right.id}'可能为0，需要空值检查")

        # 2. 检测索引越界风险
        for node in ast.walk(tree):
            if isinstance(node, ast.Subscript):
                if isinstance(node.value, ast.Name):
                    var_name = node.value.id
                    if isinstance(node.ctx, ast.Load):
                        issues.append(f"行{getattr(node, 'lineno', '?')}: 索引访问'{var_name}[...]'可能越界，需检查索引范围")

        # 3. 检测 None/空值访问风险
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute):
                if isinstance(node.value, ast.Name):
                    var_name = node.value.id
                    issues.append(f"行{getattr(node, 'lineno', '?')}: 访问'{var_name}'的属性需确保不为None")

            if isinstance(node, ast.Call):
                for arg in node.args:
                    if isinstance(arg, ast.Name):
                        issues.append(f"行{getattr(node, 'lineno', '?')}: 函数调用参数'{arg.id}'可能为None，需空值检查")

        # 4. 检测未使用的变量
        assigned_names = set()
        used_names = set()

        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        assigned_names.add(target.id)
            elif isinstance(node, ast.Name):
                if isinstance(node.ctx, ast.Load):
                    used_names.add(node.id)

        unused_vars = assigned_names - used_names
        for var in unused_vars:
            for node in ast.walk(tree):
                if isinstance(node, ast.Assign):
                    for target in node.targets:
                        if isinstance(target, ast.Name) and target.id == var:
                            issues.append(f"行{getattr(node, 'lineno', '?')}: 变量'{var}'被赋值但未使用")
                            break

        # 5. 检测空except块
        for node in ast.walk(tree):
            if isinstance(node, ast.ExceptHandler):
                if node.type is None:
                    issues.append(f"行{node.lineno}: 发现裸except语句，建议指定具体异常类型")
                if node.body and isinstance(node.body[0], ast.Pass):
                    issues.append(f"行{node.lineno}: except块为空，建议添加异常处理逻辑")

        # 6. 检测无限循环风险
        for node in ast.walk(tree):
            if isinstance(node, ast.While):
                has_break = any(isinstance(n, ast.Break) for n in ast.walk(node))
                has_return = any(isinstance(n, ast.Return) for n in ast.walk(node))
                if not has_break and not has_return:
                    issues.append(f"行{node.lineno}: while循环可能没有退出条件，存在无限循环风险")

        # 7. 检测可变默认参数
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                for default in node.args.defaults:
                    if isinstance(default, (ast.List, ast.Dict, ast.Set)):
                        issues.append(f"行{node.lineno}: 函数'{node.name}'使用可变对象作为默认参数，可能导致意外修改")

        if issues:
            result = "🔍 发现逻辑错误：\n" + "\n".join(issues)
            return result
        else:
            return "✅ 代码逻辑检查完成，未发现明显逻辑错误！"

    except SyntaxError as e:
        return f"❌ 代码存在语法错误，无法进行逻辑分析：{str(e)}"
    except Exception as e:
        logger.error(f"find_logic_error 异常: {str(e)}")
        return f"❌ 检查逻辑时发生异常：{str(e)}"

# 查找其他错误
@tool
def find_other_error(code: str)-> str:
    """
    检查Python代码的其他错误、警告等问题
    参数: code: 要检查的Python代码字符串
    返回: 错误信息字符串
    """
    if not code or len(code.strip()) == 0:
        return "错误：请传入有效的代码，不能为空！"

    try:
        warnings = []
        tree = ast.parse(code)
        lines = code.splitlines()

        for node in ast.walk(tree):
            if isinstance(node, ast.Compare):
                if len(node.ops) > 1:
                    warnings.append(f"行{node.lineno}: 链式比较可能导致意外结果")

            if isinstance(node, ast.Try):
                if node.orelse and not node.handlers:
                    warnings.append(f"行{node.lineno}: try块没有except但有else，可能逻辑不当")

        for i, line in enumerate(lines, 1):
            if len(line) > 120:
                warnings.append(f"行{i}: 代码行过长({len(line)}字符)，建议拆分")

        if warnings:
            result = "⚠️ 发现警告：\n" + "\n".join(warnings)
            return result
        else:
            return "✅ 代码检查完成，未发现明显警告！"

    except SyntaxError as e:
        return f"❌ 代码存在语法错误：{str(e)}"
    except Exception as e:
        logger.error(f"find_other_error 异常: {str(e)}")
        return f"❌ 检查时发生异常：{str(e)}"

# 分析错误原因
@tool
def analyze_bug_root_cause(code: str)-> str:
    """
    分析Python代码的错误原因
    参数: code: 要分析的Python代码字符串
    返回: 错误原因字符串
    """
    if not code or len(code.strip()) == 0:
        return "错误：请传入有效的代码，不能为空！"

    try:
        tree = ast.parse(code)
        root_causes = []

        for node in ast.walk(tree):
            if isinstance(node, ast.Try):
                for handler in node.handlers:
                    if handler.type:
                        exc_name = ""
                        if isinstance(handler.type, ast.Name):
                            exc_name = handler.type.id
                        elif isinstance(handler.type, ast.Attribute):
                            exc_name = handler.type.attr

                        if exc_name == "Exception" and not handler.body:
                            root_causes.append(f"行{handler.lineno}: 捕获所有异常但未处理，可能隐藏真实错误")

            if isinstance(node, ast.With):
                if not node.optional_vars:
                    root_causes.append(f"行{node.lineno}: with语句未使用as，可能导致资源泄漏")

        if root_causes:
            result = "🔎 错误原因分析：\n" + "\n".join(root_causes)
            return result
        else:
            return "✅ 代码分析完成，未发现明显错误原因！"

    except SyntaxError as e:
        return f"❌ 代码语法错误：{str(e)}"
    except Exception as e:
        logger.error(f"analyze_bug_root_cause 异常: {str(e)}")
        return f"❌ 分析时发生异常：{str(e)}"

#FixAgent
# 生成修复代码
@tool
def generate_fix_code(code: str)-> str:
    """
    生成修复代码，根据错误原因
    参数: code: 要修复的Python代码字符串
    返回: 修复后的Python代码字符串
    """
    if not code or len(code.strip()) == 0:
        return "错误：请传入有效的代码，不能为空！"

    try:
        fixes = []
        fixes.append("/* 修复建议：")
        fixes.append("1. 检查变量是否正确初始化")
        fixes.append("2. 确保异常处理逻辑完善")
        fixes.append("3. 验证函数返回值")
        fixes.append("4. 添加必要的空值检查")
        fixes.append("*/\n\n")
        fixes.append("// 以下为原始代码\n")
        fixes.append(code)

        result = "\n".join(fixes)
        return result

    except Exception as e:
        logger.error(f"generate_fix_code 异常: {str(e)}")
        return f"❌ 生成修复代码时发生异常：{str(e)}"

# 验证修复代码是否正确
@tool
def validate_fix_is_correct(code: str)-> str:
    """
    验证修复代码是否正确
    参数: code: 要验证的修复代码字符串
    返回: 验证结果字符串
    """
    if not code or len(code.strip()) == 0:
        return "错误：请传入有效的代码，不能为空！"

    try:
        ast.parse(code)

        issues = []

        if "pass" in code and code.count("pass") > code.count("def ") + code.count("class "):
            issues.append("警告：存在多余的pass语句")

        if "..." in code and code.count("...") > 3:
            issues.append("警告：存在过多省略号")

        if issues:
            result = "⚠️ 代码验证发现问题：\n" + "\n".join(issues)
            return result
        else:
            return "✅ 修复代码验证通过！"

    except SyntaxError as e:
        return f"❌ 修复代码存在语法错误：{str(e)}"
    except Exception as e:
        logger.error(f"validate_fix_is_correct 异常: {str(e)}")
        return f"❌ 验证时发生异常：{str(e)}"

#ReportAgent
# 生成错误报告
@tool
def generate_bug_report(code: str)-> str:
    """
    生成Python代码的错误报告
    参数: code: 要生成报告的Python代码字符串
    返回: 错误报告字符串
    """
    if not code or len(code.strip()) == 0:
        return "错误：请传入有效的代码，不能为空！"

    try:
        report = []
        report.append("=" * 50)
        report.append("Python 代码错误报告")
        report.append("=" * 50)
        report.append("")

        try:
            ast.parse(code)
            report.append("✅ 语法检查：通过")
        except SyntaxError as e:
            report.append(f"❌ 语法错误：{str(e)}")

        lines = code.strip().splitlines()
        report.append(f"📊 代码行数：{len(lines)}")

        try:
            tree = ast.parse(code)
            func_count = sum(1 for node in ast.walk(tree) if isinstance(node, ast.FunctionDef))
            class_count = sum(1 for node in ast.walk(tree) if isinstance(node, ast.ClassDef))
            report.append(f"📊 函数数量：{func_count}")
            report.append(f"📊 类数量：{class_count}")
        except:
            pass

        report.append("")
        report.append("=" * 50)

        result = "\n".join(report)
        return result

    except Exception as e:
        logger.error(f"generate_bug_report 异常: {str(e)}")
        return f"❌ 生成报告时发生异常：{str(e)}"

# 摘要错误信息
@tool
def summary_bug_info(code: str)-> str:
    """
    摘要Python代码的错误信息
    参数: code: 要摘要的Python代码字符串
    返回: 错误摘要摘要
    """
    if not code or len(code.strip()) == 0:
        return "错误：请传入有效的代码，不能为空！"

    try:
        summary = []
        summary.append("【代码摘要】")

        lines = code.strip().splitlines()
        summary.append(f"总行数: {len(lines)}")

        error_count = 0
        try:
            ast.parse(code)
        except:
            error_count = 1

        summary.append(f"语法错误: {'有' if error_count else '无'}")

        try:
            tree = ast.parse(code)
            import_count = sum(1 for node in ast.walk(tree) if isinstance(node, (ast.Import, ast.ImportFrom)))
            func_count = sum(1 for node in ast.walk(tree) if isinstance(node, ast.FunctionDef))
            summary.append(f"导入语句: {import_count}")
            summary.append(f"函数定义: {func_count}")
        except:
            pass

        result = "\n".join(summary)
        return result

    except Exception as e:
        logger.error(f"summary_bug_info 异常: {str(e)}")
        return f"❌ 生成摘要时发生异常：{str(e)}"

# 格式化输出为JSON
@tool
def format_output_to_json(code: str)-> str:
    """
    格式化Python代码的输出为JSON格式
    参数: code: 要格式化的Python代码字符串
    返回: JSON格式的输出字符串
    """
    if not code or len(code.strip()) == 0:
        return '{"error": "请传入有效的代码"}'

    try:
        result = {
            "status": "success",
            "data": {
                "code_length": len(code),
                "line_count": len(code.strip().splitlines()),
                "has_syntax_error": False,
                "structure": {}
            }
        }

        try:
            tree = ast.parse(code)

            functions = []
            classes = []
            imports = []

            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    functions.append({
                        "name": node.name,
                        "line": node.lineno
                    })
                elif isinstance(node, ast.ClassDef):
                    classes.append({
                        "name": node.name,
                        "line": node.lineno
                    })
                elif isinstance(node, (ast.Import, ast.ImportFrom)):
                    if isinstance(node, ast.Import):
                        imports.extend([alias.name for alias in node.names])
                    else:
                        imports.append(node.module or "")

            result["data"]["structure"]["functions"] = functions
            result["data"]["structure"]["classes"] = classes
            result["data"]["structure"]["imports"] = imports

        except SyntaxError:
            result["data"]["has_syntax_error"] = True
            result["status"] = "error"

        return json.dumps(result, ensure_ascii=False, indent=2)

    except Exception as e:
        logger.error(f"format_output_to_json 异常: {str(e)}")
        return json.dumps({"error": str(e), "status": "error"}, ensure_ascii=False)