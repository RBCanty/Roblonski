""" Purely decorative in nature, this code is so that when a Handler Bed is loaded, a message can be printed to the
 console with a concise description of which vials the platform expects there to be loaded. For example, is deck layout
 is such that the first three vials of the first four rows of rack 1 are used and the last row has a fourth vial,
 then on boot-up, the console will display something like 'A1:D3, D4' """

from itertools import zip_longest
from random import shuffle
from typing import NamedTuple


class VialTuple(NamedTuple):
    row_num: int
    row_sym: str
    col_num: int

    def vid(self):
        return f"{self.row_sym}{self.col_num}"


class Edge:
    def __init__(self, primary: int, secondary: list[int], primary_is_row: bool):
        self.primary = primary
        self.secondary = secondary
        self.p_is_row = primary_is_row

    def are_concatenable(self, other):
        if not isinstance(other, Edge):
            return False
        if self.p_is_row != other.p_is_row:
            return False
        if abs(self.primary - other.primary) != 1:
            return False
        try:
            return all(s1 == s2 for s1, s2 in zip_longest(self.secondary, other.secondary, fillvalue=-1))
        except ValueError:
            return False

    def __repr__(self):
        return ("row"*self.p_is_row + "col"*(not self.p_is_row)
                + f"{self.primary}|"
                + ",".join([str(s) for s in self.secondary]))


class Cluster:
    def __init__(self, members: list[VialTuple]):
        self.members = members

    def sorter(self, mode: str):
        """ Mode: R/C (row/column) + N/X (min/max) + I/J/S (row/col/symbol)"""
        mode = mode.upper()
        if 'R' in mode:
            using_bounds = self.row_bounds
        elif 'C' in mode:
            using_bounds = self.col_bounds
        else:
            raise ValueError(f"Mode must contain 'R' (row) or 'C' (column)")

        if 'N' in mode:
            using = using_bounds[0]
        elif 'X' in mode:
            using = using_bounds[1]
        else:
            raise ValueError(f"Mode must contain 'N' (min) or 'X' (max)")

        if 'I' in mode:
            return using.row_num
        elif 'J' in mode:
            return using.col_num
        elif 'S' in mode:
            return using.row_sym
        else:
            raise ValueError(f"Mode must contain 'I' (row), 'J' (col), or 'S' (row symbol)")

    @property
    def row_bounds(self):
        minimum = min(self.members, key=lambda v: v.row_num)
        maximum = max(self.members, key=lambda v: v.row_num)
        return minimum, maximum

    @property
    def col_bounds(self):
        minimum = min(self.members, key=lambda v: v.col_num)
        maximum = max(self.members, key=lambda v: v.col_num)
        return minimum, maximum

    @property
    def right_edge(self):
        _, max_col = self.col_bounds
        return Edge(max_col.col_num, [v.row_num for v in self.members if v.col_num == max_col.col_num], False)

    @property
    def left_edge(self):
        min_col, _ = self.col_bounds
        return Edge(min_col.col_num, [v.row_num for v in self.members if v.col_num == min_col.col_num], False)

    @property
    def top_edge(self):
        min_row, _ = self.row_bounds
        return Edge(min_row.row_num, [v.col_num for v in self.members if v.row_num == min_row.row_num], True)

    @property
    def bottom_edge(self):
        _, max_row = self.row_bounds
        return Edge(max_row.row_num, [v.col_num for v in self.members if v.row_num == max_row.row_num], True)

    def format_block(self):
        if len(self.members) == 1:
            single = self.members[0]
            return f"{single.row_sym}{single.col_num}"
        min_row, max_row = self.row_bounds
        min_col, max_col = self.col_bounds
        return f"{min_row.row_sym}{min_col.col_num}:{max_row.row_sym}{max_col.col_num}"

    def are_concatenable(self, other):
        if not isinstance(other, Cluster):
            print(f"Warning: Cannot judge concatenability of Cluster and {type(other)}")
            return False
        if self.left_edge.are_concatenable(other.right_edge) or other.left_edge.are_concatenable(self.right_edge):
            return True
        if self.top_edge.are_concatenable(other.bottom_edge) or other.top_edge.are_concatenable(self.bottom_edge):
            return True
        return False

    def __add__(self, other):
        if not isinstance(other, Cluster):
            raise ValueError(f"Cannot __add__ Cluster with '{type(other)}'")
        if not self.are_concatenable(other):
            raise ValueError(f"Cannot __add__ two Clusters which are not concatenable.")
        return Cluster(self.members + other.members)

    def __eq__(self, other):
        if not isinstance(other, Cluster):
            print(f"Warning: Cannot judge equality of Cluster and {type(other)}")
            return False
        return self.members == other.members

    def __hash__(self):
        return sum(hash(m) for m in self.members)


def agglomerate(source: list[Cluster]):
    source.sort(key=lambda c: c.sorter('CNJ'))
    source.sort(key=lambda c: c.sorter('RNI'))

    agg = list(_agglomerate(source, init=True))
    agg.sort(key=lambda c: c.sorter('CNJ'))
    agg.sort(key=lambda c: c.sorter('RNI'))

    yield from [c.format_block() for c in agg]


def _agglomerate(source: list[Cluster], running: Cluster = None, init=False):
    if init:
        source = list(_agglomerate(source, running))

    if running is None:
        if not source:
            return
        running = source.pop(0)
    # elif not source
    adjacent_clusters = [c for c in source if running.are_concatenable(c)]
    if not adjacent_clusters:
        yield running
        yield from _agglomerate(source, None)
    else:
        addition = adjacent_clusters.pop(0)
        source.pop(source.index(addition))
        yield from _agglomerate(source, running + addition)


if __name__ == '__main__':
    # vials = [
    #     VialTuple(row_num=1, row_sym="A", col_num=1),
    #     VialTuple(row_num=1, row_sym="A", col_num=3),
    #     VialTuple(row_num=1, row_sym="A", col_num=4),
    #     VialTuple(row_num=2, row_sym="B", col_num=1),
    #     VialTuple(row_num=2, row_sym="B", col_num=3),
    #     VialTuple(row_num=2, row_sym="B", col_num=4),
    #     VialTuple(row_num=3, row_sym="C", col_num=1),
    #     VialTuple(row_num=3, row_sym="C", col_num=3),
    #     VialTuple(row_num=3, row_sym="C", col_num=4),
    #     VialTuple(row_num=4, row_sym="D", col_num=1),
    #     VialTuple(row_num=4, row_sym="D", col_num=2),
    #     VialTuple(row_num=5, row_sym="E", col_num=4),
    # ]

    vials = [
        VialTuple(row_num=ri, row_sym=rs, col_num=cj)
        for cj in [1,2,3,4]
        for ri, rs in enumerate(['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J', 'K', 'L', 'M', 'N', 'O', 'P'], start=1)
        if (rs != 'P') or (cj != 2)
    ]
    shuffle(vials)

    test = agglomerate([Cluster([v, ]) for v in vials])

    for t in test:
        print(t)

    # A1:P4
    # B2:P4
    # C2:P3
    # D3:P3

    # test_cluster = Cluster([
    #     VialTuple(row_num=1, row_sym="A", col_num=1),
    #     VialTuple(row_num=1, row_sym="A", col_num=2),
    #     VialTuple(row_num=1, row_sym="A", col_num=3),
    #     VialTuple(row_num=2, row_sym="B", col_num=1),
    #     VialTuple(row_num=2, row_sym="B", col_num=2),
    #     VialTuple(row_num=2, row_sym="B", col_num=3)
    # ])
    #
    # print(test_cluster.top_edge)
    # print(test_cluster.right_edge)
    # print(test_cluster.bottom_edge)
    # print(test_cluster.left_edge)
    # print(test_cluster.format_block())
