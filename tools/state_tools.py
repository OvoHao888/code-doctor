from langchain_core.tools import tool

@tool
def reset_workflow() -> str:
    """
    重置整个工作流，清除所有状态，从头开始执行
    当总管对结果不满意时调用此工具
    返回: {"reset": true}
    """
    return '{"reset": true}'

@tool
def mark_from_web() -> str:
    """
    标记信息来自网页搜索
    返回: {"is_from_web": true}
    """
    return '{"is_from_web": true}'

@tool
def workflow_complete() -> str:
    """
    标记工作流已完成，结果满意
    返回: {"complete": true}
    """
    return '{"complete": true}'
