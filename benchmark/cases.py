"""基准对账语义的**单一实现源**。

真值库测试与基准 runner **共用本模块的函数**——否则会出现"基准说达标、
测试说不过"的双口径漂移。

真值记录语义（定一次，写进生成器模块注释）：

- ``expect`` = 主期望（该用例的核心结论字段）；
- ``also_expect`` = 同一注入隐含的其余结论；
- 对账按"**全部非 pass 字段集合**"进行。
"""


def observed_nonpass(observed):
    """从观测结果里抽出"非 pass 字段集合"。

    ``observed`` 是 ``{字段名: 状态}``；状态为 ``ok`` 的不计入。
    """
    if not isinstance(observed, dict):
        return set()
    return {key for key, value in observed.items() if value != "ok"}


def compare_nonpass(expected, observed):
    """对账：返回 ``{"missing": [...], "unexpected": [...], "match": bool}``。

    - ``missing``：期望出现但观测没出现（漏报）；
    - ``unexpected``：观测出现但期望没有（误报）；
    - ``match``：两者相等。
    """
    expected_set = set(expected)
    observed_set = set(observed)
    missing = sorted(expected_set - observed_set)
    unexpected = sorted(observed_set - expected_set)
    return {"missing": missing, "unexpected": unexpected,
            "match": not missing and not unexpected}
