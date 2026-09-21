from typing import Literal

AntiPatternTag = Literal[
    "func_index",           # 对索引字段套用函数
    "implicit_conversion",  # 隐式类型转换
    "select_all",           # 滥用 SELECT *
    "deep_paging",          # 深度分页
    "missing_join_index",   # 连表缺索引
    "other"                 # 兜底选项：遇到了全新的病
]