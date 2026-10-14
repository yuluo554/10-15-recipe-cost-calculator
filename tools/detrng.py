"""确定性伪随机数发生器（splitmix64）。

**为什么不用 stdlib ``random``**：它不承诺跨 Python 版本/平台序列一致，
用它生成的冻结 fixtures 会在别的机器上算出不同结果，破坏"可复现基准"。

splitmix64 是纯整数运算，任意平台上同 seed 必得同序列。
"""

_MASK = (1 << 64) - 1
_GOLDEN = 0x9E3779B97F4A7C15


class SplitMix64(object):
    """splitmix64 生成器：``next_u64()`` 取 64 位无符号整数。"""

    def __init__(self, seed):
        if not isinstance(seed, int) or isinstance(seed, bool):
            raise TypeError("seed 必须是整数")
        self._state = seed & _MASK

    def next_u64(self):
        self._state = (self._state + _GOLDEN) & _MASK
        z = self._state
        z = ((z ^ (z >> 30)) * 0xBF58476D1CE4E5B9) & _MASK
        z = ((z ^ (z >> 27)) * 0x94D049BB133111EB) & _MASK
        return (z ^ (z >> 31)) & _MASK

    def randint(self, low, high):
        """闭区间 ``[low, high]`` 内的整数（拒绝采样，无模偏差）。"""
        if high < low:
            raise ValueError("high 必须 >= low")
        span = high - low + 1
        if span == 1:
            return low
        limit = (1 << 64) - ((1 << 64) % span)
        while True:
            value = self.next_u64()
            if value < limit:
                return low + (value % span)

    def choice(self, seq):
        """从序列里确定性地取一项（按索引取，不依赖 ``set`` 迭代序）。"""
        seq = list(seq)
        if not seq:
            raise ValueError("空序列无法取项")
        return seq[self.randint(0, len(seq) - 1)]
