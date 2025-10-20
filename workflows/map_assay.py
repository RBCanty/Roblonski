import operator
from functools import reduce
from itertools import batched
from typing import Iterable, Self, Callable

from deck_layout.handler_bed import Placeable, NamePlace


class _Aliquot:
    def __init__(self, name: str, rack: str, vial_id: str):
        self.name = name
        self.rack = rack
        self.vial_id = vial_id


class Stock(_Aliquot):
    def __init__(self, name: str, rack: str, vial_id: str):
        super().__init__(name, rack, vial_id)


    @classmethod
    def from_spec_string(cls, spec_string: str) -> Self:
        spec_string = spec_string.replace(" ", "")
        name, rack, vial_id, *_ = spec_string.split(',')
        return cls(
            name.strip(),
            rack.strip(),
            vial_id.strip()
        )


class Sample(_Aliquot):
    def __init__(self, name: str, rack: str, vial_id: str, composition: Iterable[tuple[str, float]]):
        super().__init__(name, rack, vial_id)
        self.components: dict[str, float] = {}
        for _name, volume in composition:
            self.components.setdefault(_name, 0.0)
            self.components[_name] += volume

    @property
    def dependencies(self) -> set[str]:
        return set(self.components.keys())

    def dependant_of(self, *name: str) -> bool:
        return bool(self.dependencies & set(name))

    @classmethod
    def from_spec_string(cls, spec_string: str) -> Self:
        spec_string = spec_string.replace(" ", "")
        name, rack, vial_id, *_composition = spec_string.split(',')
        return cls(
            name.strip(),
            rack.strip(),
            vial_id.strip(),
            [(spec[0].strip(), float(spec[1])) for spec in batched(_composition, n=2) if (len(spec) == 2) and (spec[0].strip() and spec[1].strip())]
        )

def read_csv(file_path: str) -> tuple[list[Stock], list[Sample]]:
    stocks: list[Stock] = []
    samples: list[Sample] = []
    with open(file_path, 'r') as spec_file:
        for line in spec_file:
            if not line.strip():
                continue
            _type, spec_string = line.split(',', 1)
            if _type.strip().lower() == 'stock':
                stocks.append(Stock.from_spec_string(spec_string))
            elif _type.strip().lower() == 'sample':
                samples.append(Sample.from_spec_string(spec_string))
            else:
                print(f"Comment: {spec_string.strip()}")
    return stocks, samples


def check_aliquots(stocks: list[Stock], samples: list[Sample]) -> set[str]:
    """ returns anything requested that wasn't provided """
    given_components: set[str] = {s.name for s in stocks} | {s.name for s in samples}
    requested_components: set[str] = reduce(operator.or_, [s.dependencies for s in samples], set())
    return requested_components - given_components


def organize_samples(samples: list[Sample]):
    working_list = [s for s in samples]
    sorted_list: list[list[Sample]] = []
    space = set(a.name for a in working_list)
    counter = len(working_list)**2 + 1
    while working_list:
        generation: list[Sample] = []
        for s in working_list:
            if not (s.dependencies & space):
                generation.append(s)
        for s in generation:
            working_list.pop(working_list.index(s))
            space.remove(s.name)
        sorted_list.append(generation)
        counter -= 1
        if counter < 0:
            remainder = "\n  ".join([f"{s.name} <-- {s.dependencies}" for s in working_list])
            raise RuntimeError(f"Sample organization not completable, there may be a cyclic specification!"
                               f"\n  {remainder}")
    return sorted_list


def generate_script(locator: Callable[[str, str], NamePlace], stocks: list[Stock], organized_samples: list[list[Sample]]):
    """ Generator yields a list of specifications for each generation of the organized samples.  Within each list,
     there are tuples of the form (components, destination) where components is itself a list of tuples of the form
     (Placeable, volume) such that 'components' and 'destination' can be passed to
     Gilson241LiquidHandler.prepare_vial()"""
    def _find(name: str):
        for stock in stocks:
            if name == stock.name:
                return stock.rack, stock.vial_id
        for _generation in organized_samples:
            for sample in _generation:
                if name == sample.name:
                    return sample.rack, sample.vial_id
        return None

    def _generate_script(_generation):
        for sample in _generation:
            components: Iterable[tuple[Placeable, float]] = [
                (locator(*position) , d_vol) for d_name, d_vol in sample.components.items()
                if (position := _find(d_name)) is not None
            ]
            destination: Placeable = locator(sample.rack, sample.vial_id)
            yield components, destination

    for generation in organized_samples:
        yield list(_generate_script(generation))


if __name__ == '__main__':
    def trial():
        stocks, samples = read_csv(r'C:\Users\User\Desktop\test_csv_input.txt')
        print()

        if bad_apples := check_aliquots(stocks, samples):
            print(f"Warning! Components requested which were not provided:\n{bad_apples}")
            samples = {s for s in samples if not s.dependant_of(*bad_apples)}

        print("Stocks:")
        for stock in stocks:
            print("\t", stock.name)
        print("Samples:")
        gen_idx = 0
        organized_samples = organize_samples(samples)
        for generation in organized_samples:
            print(f"\t Generation {gen_idx}:")
            for sample in generation:
                print(f"\t\t {sample.name}")
            gen_idx += 1
        print()

        procedure = generate_script(lambda r, v: NamePlace(None, r, v), stocks, organize_samples(samples))
        print("Procedure")
        for step in procedure:
            for step_spec in step:
                print(f"{step_spec[1].lazy_name()}:\n  " + "\n  ".join([f"{_p.lazy_name()}: {_v}" for _p, _v in step_spec[0]]))

    trial()

"""
Example CSV file:

TYPE  ,NAME    ,RACK      ,VIAL  ,COMP1N  ,COMP1V  ,COMP2N  ,COMP2V,COMP3N ,COMP3V

stock ,catalyst,pos_1_rack,A1    ,        ,        ,        ,      ,       ,
stock ,diluent ,pos_1_rack,A2    ,        ,        ,        ,      ,       ,
stock ,quencher,pos_1_rack,A3    ,        ,        ,        ,      ,       ,
sample,sample1 ,pos_1_rack,B1    ,catalyst,100     ,quencher,200   ,diluent,100
sample,sample2 ,pos_1_rack,B2    ,catalyst,200     ,quencher,100   ,diluent,150
sample,sample3 ,pos_1_rack,B3    ,sample1 ,150     ,sample2 ,150   ,diluent,175
sample,sample4 ,pos_1_rack,E1    ,catalyst,200     ,sample2 ,100   ,diluent,125
sample,sample5 ,pos_1_rack,E2    ,sample1 ,150     ,sample3 ,150   ,diluent,200
sample,sample6 ,pos_1_rack,E3    ,sample5 ,150     ,diluent ,100   ,       ,

#sample,bad_sample, pos_1_rack,C1,500,sample7,0.8,$,diluent,1
#sample,circ1,post_1_rack,D1,100,circ2,0.5,$,diluent,2
#sample,circ2,post_1_rack,D1,100,circ1,0.5,$,diluent,2
"""
