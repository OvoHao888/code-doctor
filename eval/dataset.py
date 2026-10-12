"""评测数据集。

设计要点：
1. **必须包含负样本**（has_bug=False 的干净代码）。只有正样本时，一个"永远报 bug"
   的蠢检测器召回率就是 100%，评测毫无意义。
2. 每个样本带 **assertions（隐藏断言）**：把它拼在修复后代码后面执行，退出码必须为 0。
   这是为了防"改成空函数/pass 也能 exit 0"—— 断言里同时检查了原有功能未被破坏。
3. expected_lines / expected_types 用于计算检测的召回率与精确率（行号容差 ±3）。

字段说明：
    id            唯一标识
    category      问题类别
    code          提交给系统的代码
    error         模拟用户提供的运行时错误信息
    has_bug       标准答案：是否存在需要修复的问题
    lines         标准答案：问题所在行号列表
    types         标准答案：问题类型列表
    assertions    隐藏断言（拼在 fixed_code 之后执行，必须 exit 0）
    static_check  可选。**非崩溃类缺陷**（资源泄漏、裸 except）即使不修也不会让程序报错，
                  执行结果无法区分修没修，必须补一个静态断言作为判据：
                    uses_with_open  —— 每个 open() 都必须在 with 块内
                    no_bare_except  —— 不允许出现裸 except
"""

# 用于"除零"类样本的通用边界断言：接受"优雅处理"或"显式抛 ValueError"两种正确修法，
# 但绝不允许仍然抛出 ZeroDivisionError。
NO_ZDIV_ASSERT = '''
try:
    _fixture_call
except ZeroDivisionError:
    raise AssertionError("仍然抛出 ZeroDivisionError，未修复")
except (ValueError, TypeError):
    pass
'''

DATASET = [
    # ==================== 除零 (4) ====================
    {
        "id": "div_zero_literal",
        "category": "除零",
        "code": "def divide(a, b):\n    return a / b\n\nprint(divide(10, 0))\n",
        "error": "ZeroDivisionError: division by zero",
        "has_bug": True,
        "lines": [2],
        "types": ["除零"],
        "assertions": (
            "try:\n    divide(10, 0)\nexcept ZeroDivisionError:\n"
            "    raise AssertionError('仍然抛出 ZeroDivisionError，未修复')\n"
            "except ValueError:\n    pass\n"
            "assert divide(10, 2) == 5.0 or divide(10, 2) == 5, '正常输入结果被破坏'\n"
        ),
    },
    {
        "id": "div_zero_len",
        "category": "除零",
        "code": (
            "def average(numbers):\n"
            "    total = 0\n"
            "    for n in numbers:\n"
            "        total += n\n"
            "    return total / len(numbers)\n\n"
            "print(average([]))\n"
        ),
        "error": "ZeroDivisionError: division by zero",
        "has_bug": True,
        "lines": [5],
        "types": ["除零"],
        "assertions": (
            "try:\n    average([])\nexcept ZeroDivisionError:\n"
            "    raise AssertionError('空列表仍然除零，未修复')\n"
            "except ValueError:\n    pass\n"
            "assert average([2, 4, 6]) == 4, '正常输入结果被破坏'\n"
        ),
    },
    {
        "id": "div_zero_mod",
        "category": "除零",
        "code": "def is_even(n, divisor):\n    return n % divisor == 0\n\nprint(is_even(4, 0))\n",
        "error": "ZeroDivisionError: integer modulo by zero",
        "has_bug": True,
        "lines": [2],
        "types": ["除零"],
        "assertions": (
            "try:\n    is_even(4, 0)\nexcept ZeroDivisionError:\n"
            "    raise AssertionError('取模除零未修复')\n"
            "except ValueError:\n    pass\n"
            "assert is_even(4, 2) is True, '正常输入结果被破坏'\n"
        ),
    },
    {
        "id": "div_zero_ratio",
        "category": "除零",
        "code": (
            "def ratio(part, whole):\n"
            "    return part / whole\n\n"
            "def report(part, whole):\n"
            "    return f'占比 {ratio(part, whole):.2%}'\n\n"
            "print(report(1, 0))\n"
        ),
        "error": "ZeroDivisionError: division by zero",
        "has_bug": True,
        "lines": [2],
        "types": ["除零"],
        "assertions": (
            "try:\n    ratio(1, 0)\nexcept ZeroDivisionError:\n"
            "    raise AssertionError('除零未修复')\n"
            "except ValueError:\n    pass\n"
            "assert abs(ratio(1, 4) - 0.25) < 1e-9, '正常输入结果被破坏'\n"
        ),
    },
    # ==================== 索引越界 (3) ====================
    {
        "id": "index_oob",
        "category": "索引越界",
        "code": "data = [1, 2, 3]\nprint(data[10])\n",
        "error": "IndexError: list index out of range",
        "has_bug": True,
        "lines": [2],
        "types": ["索引越界"],
        "assertions": (
            "import builtins\n"
            "_original = [1, 2, 3]\n"
            "assert _original == [1, 2, 3], '数据被破坏'\n"
        ),
    },
    {
        "id": "index_len_off_by_one",
        "category": "索引越界",
        "code": "items = ['a', 'b', 'c']\nprint(items[len(items)])\n",
        "error": "IndexError: list index out of range",
        "has_bug": True,
        "lines": [2],
        "types": ["索引越界"],
        "assertions": "assert items == ['a', 'b', 'c'], '数据被破坏'\n",
    },
    {
        "id": "index_pop_empty",
        "category": "索引越界",
        "code": "def last_or_error(values):\n    return values[len(values) - 1]\n\nprint(last_or_error([]))\n",
        "error": "IndexError: list index out of range",
        "has_bug": True,
        "lines": [2],
        "types": ["索引越界"],
        "assertions": (
            "try:\n    last_or_error([])\nexcept IndexError:\n"
            "    raise AssertionError('空列表仍然越界，未修复')\n"
            "except ValueError:\n    pass\n"
            "assert last_or_error([7, 8]) == 8, '正常输入结果被破坏'\n"
        ),
    },
    # ==================== 空值解引用 (3) ====================
    {
        "id": "none_attr",
        "category": "空值解引用",
        "code": "def get_name(user):\n    return user.name.upper()\n\nprint(get_name(None))\n",
        "error": "AttributeError: 'NoneType' object has no attribute 'name'",
        "has_bug": True,
        "lines": [2],
        "types": ["空值解引用"],
        "assertions": (
            "try:\n    get_name(None)\nexcept AttributeError:\n"
            "    raise AssertionError('None 仍然被解引用，未修复')\n"
            "except (ValueError, TypeError):\n    pass\n"
        ),
    },
    {
        "id": "none_dict_get",
        "category": "空值解引用",
        "code": (
            "def city_of(config):\n"
            "    return config.get('address').get('city')\n\n"
            "print(city_of({'address': None}))\n"
        ),
        "error": "AttributeError: 'NoneType' object has no attribute 'get'",
        "has_bug": True,
        "lines": [2],
        "types": ["空值解引用"],
        "assertions": (
            "try:\n    city_of({'address': None})\nexcept AttributeError:\n"
            "    raise AssertionError('None 仍被解引用，未修复')\n"
            "except (ValueError, TypeError):\n    pass\n"
            "assert city_of({'address': {'city': '北京'}}) == '北京', '正常输入结果被破坏'\n"
        ),
    },
    {
        "id": "none_return",
        "category": "空值解引用",
        "code": (
            "def find_user(users, uid):\n"
            "    for u in users:\n"
            "        if u['id'] == uid:\n"
            "            return u\n\n"
            "user = find_user([{'id': 1}], 99)\n"
            "print(user['name'])\n"
        ),
        "error": "TypeError: 'NoneType' object is not subscriptable",
        "has_bug": True,
        "lines": [8],
        "types": ["空值解引用"],
        "assertions": (
            "assert find_user([{'id': 1, 'name': 'a'}], 1)['name'] == 'a', '正常输入结果被破坏'\n"
        ),
    },
    # ==================== 可变默认参数 (3) ====================
    {
        "id": "mutable_default_list",
        "category": "可变默认参数",
        "code": (
            "def add_item(item, basket=[]):\n"
            "    basket.append(item)\n"
            "    return basket\n\n"
            "print(add_item('a'))\n"
            "print(add_item('b'))\n"
        ),
        "error": "",
        "has_bug": True,
        "lines": [1],
        "types": ["可变默认参数"],
        "assertions": (
            "assert add_item('x') == ['x'], '默认参数被跨调用共享'\n"
            "assert add_item('y') == ['y'], '默认参数被跨调用共享'\n"
        ),
    },
    {
        "id": "mutable_default_dict",
        "category": "可变默认参数",
        "code": (
            "def record(key, value, store={}):\n"
            "    store[key] = value\n"
            "    return store\n\n"
            "print(record('a', 1))\n"
            "print(record('b', 2))\n"
        ),
        "error": "",
        "has_bug": True,
        "lines": [1],
        "types": ["可变默认参数"],
        "assertions": (
            "assert record('x', 1) == {'x': 1}, '默认字典被跨调用共享'\n"
            "assert record('y', 2) == {'y': 2}, '默认字典被跨调用共享'\n"
        ),
    },
    {
        "id": "mutable_default_accumulate",
        "category": "可变默认参数",
        "code": (
            "def collect(value, acc=[]):\n"
            "    acc.append(value)\n"
            "    return sum(acc)\n\n"
            "print(collect(1))\n"
            "print(collect(2))\n"
        ),
        "error": "",
        "has_bug": True,
        "lines": [1],
        "types": ["可变默认参数"],
        "assertions": (
            "assert collect(5) == 5, '多次调用结果被污染'\n"
            "assert collect(3) == 3, '多次调用结果被污染'\n"
        ),
    },
    # ==================== 资源泄漏 (2) ====================
    {
        "id": "leak_open_read",
        "category": "资源泄漏",
        "code": (
            "def read_first_line(path):\n"
            "    f = open(path)\n"
            "    return f.readline()\n\n"
            "import os\n"
            "p = os.path.join(os.getcwd(), 'sample.txt')\n"
            "with open(p, 'w') as w:\n"
            "    w.write('hello\\n')\n"
            "print(read_first_line(p))\n"
        ),
        "error": "",
        "has_bug": True,
        "lines": [2],
        "types": ["资源泄漏"],
        "static_check": "uses_with_open",
        "assertions": (
            "import os\n"
            "_p = os.path.join(os.getcwd(), 'sample2.txt')\n"
            "with open(_p, 'w') as w:\n    w.write('world\\n')\n"
            "assert read_first_line(_p).strip() == 'world', '正常功能被破坏'\n"
        ),
    },
    {
        "id": "leak_open_write",
        "category": "资源泄漏",
        "code": (
            "def save(path, text):\n"
            "    f = open(path, 'w')\n"
            "    f.write(text)\n\n"
            "import os\n"
            "save(os.path.join(os.getcwd(), 'out.txt'), 'data')\n"
            "print('done')\n"
        ),
        "error": "",
        "has_bug": True,
        "lines": [2],
        "types": ["资源泄漏"],
        "static_check": "uses_with_open",
        "assertions": (
            "import os\n"
            "_p = os.path.join(os.getcwd(), 'out2.txt')\n"
            "save(_p, 'xyz')\n"
            "with open(_p) as r:\n    assert r.read() == 'xyz', '写入功能被破坏'\n"
        ),
    },
    # ==================== 裸 except (2) ====================
    {
        "id": "bare_except_swallow",
        "category": "裸except",
        "code": (
            "def parse_int(text):\n"
            "    try:\n"
            "        return int(text)\n"
            "    except:\n"
            "        return 0\n\n"
            "print(parse_int('abc'))\n"
        ),
        "error": "",
        "has_bug": True,
        "lines": [4],
        "types": ["裸except"],
        "static_check": "no_bare_except",
        "assertions": "assert parse_int('42') == 42, '正常解析功能被破坏'\n",
    },
    {
        "id": "bare_except_pass",
        "category": "裸except",
        "code": (
            "def load(value):\n"
            "    try:\n"
            "        return int(value)\n"
            "    except:\n"
            "        pass\n\n"
            "print(load('nope'))\n"
        ),
        "error": "",
        "has_bug": True,
        "lines": [4],
        "types": ["裸except"],
        "static_check": "no_bare_except",
        "assertions": "assert load('7') == 7, '正常解析功能被破坏'\n",
    },
    # ==================== 死循环 (2) ====================
    {
        "id": "infinite_while",
        "category": "死循环",
        "code": "count = 0\nwhile True:\n    count += 1\n    print(count)\n",
        "error": "",
        "has_bug": True,
        "lines": [2],
        "types": ["死循环"],
        "assertions": "assert isinstance(count, int), '状态被破坏'\n",
    },
    {
        "id": "infinite_loop_retry",
        "category": "死循环",
        "code": (
            "def wait_for(condition):\n"
            "    while True:\n"
            "        if condition:\n"
            "            return True\n\n"
            "print(wait_for(False))\n"
        ),
        "error": "",
        "has_bug": True,
        "lines": [2],
        "types": ["死循环"],
        "assertions": "assert wait_for(True) is True, '正常功能被破坏'\n",
    },
    # ==================== 干净样本（负样本，用于度量误报率）(8) ====================
    {
        "id": "clean_divide_guarded",
        "category": "干净",
        "code": (
            "def divide(a, b):\n"
            "    if b == 0:\n"
            "        raise ValueError('除数不能为 0')\n"
            "    return a / b\n\n"
            "print(divide(10, 2))\n"
        ),
        "error": "",
        "has_bug": False,
        "lines": [],
        "types": [],
        "assertions": "assert divide(10, 2) == 5.0, '功能异常'\n",
    },
    {
        "id": "clean_with_open",
        "category": "干净",
        "code": (
            "import os\n"
            "def read_all(path):\n"
            "    with open(path) as f:\n"
            "        return f.read()\n\n"
            "p = os.path.join(os.getcwd(), 'c.txt')\n"
            "with open(p, 'w') as w:\n"
            "    w.write('ok')\n"
            "print(read_all(p))\n"
        ),
        "error": "",
        "has_bug": False,
        "lines": [],
        "types": [],
        "assertions": "import os\nassert read_all(os.path.join(os.getcwd(), 'c.txt')) == 'ok'\n",
    },
    {
        "id": "clean_specific_except",
        "category": "干净",
        "code": (
            "def parse(text):\n"
            "    try:\n"
            "        return int(text)\n"
            "    except ValueError:\n"
            "        return None\n\n"
            "print(parse('abc'))\n"
        ),
        "error": "",
        "has_bug": False,
        "lines": [],
        "types": [],
        "assertions": "assert parse('5') == 5 and parse('x') is None, '功能异常'\n",
    },
    {
        "id": "clean_default_none",
        "category": "干净",
        "code": (
            "def add_item(item, basket=None):\n"
            "    if basket is None:\n"
            "        basket = []\n"
            "    basket.append(item)\n"
            "    return basket\n\n"
            "print(add_item('a'))\n"
        ),
        "error": "",
        "has_bug": False,
        "lines": [],
        "types": [],
        "assertions": "assert add_item('x') == ['x'] and add_item('y') == ['y'], '功能异常'\n",
    },
    {
        "id": "clean_bounded_loop",
        "category": "干净",
        "code": (
            "def total(n):\n"
            "    s = 0\n"
            "    for i in range(n):\n"
            "        s += i\n"
            "    return s\n\n"
            "print(total(5))\n"
        ),
        "error": "",
        "has_bug": False,
        "lines": [],
        "types": [],
        "assertions": "assert total(5) == 10, '功能异常'\n",
    },
    {
        "id": "clean_index_checked",
        "category": "干净",
        "code": (
            "def safe_get(values, idx):\n"
            "    if 0 <= idx < len(values):\n"
            "        return values[idx]\n"
            "    return None\n\n"
            "print(safe_get([1, 2, 3], 1))\n"
        ),
        "error": "",
        "has_bug": False,
        "lines": [],
        "types": [],
        "assertions": "assert safe_get([1,2,3], 1) == 2 and safe_get([1], 9) is None, '功能异常'\n",
    },
    {
        "id": "clean_none_guarded",
        "category": "干净",
        "code": (
            "def get_name(user):\n"
            "    if user is None:\n"
            "        return ''\n"
            "    return user['name'].upper()\n\n"
            "print(get_name({'name': 'amy'}))\n"
        ),
        "error": "",
        "has_bug": False,
        "lines": [],
        "types": [],
        "assertions": "assert get_name({'name':'amy'}) == 'AMY' and get_name(None) == '', '功能异常'\n",
    },
    {
        "id": "clean_string_ops",
        "category": "干净",
        "code": (
            "def normalize(text):\n"
            "    return text.strip().lower().replace('-', '_')\n\n"
            "print(normalize('  Hello-World  '))\n"
        ),
        "error": "",
        "has_bug": False,
        "lines": [],
        "types": [],
        "assertions": "assert normalize('  A-B  ') == 'a_b', '功能异常'\n",
    },
]
