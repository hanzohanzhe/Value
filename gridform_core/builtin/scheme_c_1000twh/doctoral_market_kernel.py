"""Static source-faithful doctoral national-market primitives.

Source: simulation_model.py in the audited decarbonization_cost_research tree.
Original SHA-256: 434f43ca9607ba1b9588826c924d48755965ad99bcf4b3dc0e13089a512e3da0.
Retained source ranges: iterator classes 49-107; asset classes 163-425;
decay_func 526-544; settlement/market functions 609-1605. Original definitions
were copied statically; named source defect corrections are listed below. No original source path,
dynamic AST loading, data reads, plotting, Excel output, or simulation main is
needed at runtime. Income accounting explicitly uses half-hour periods.

This module is an intermediate source-fidelity boundary, not a complete dispatch
engine or a certificate of physical correctness. Callers must supply approved
nuclear capacity and disable both direct electrolyzer loads. The source's local
period batch keys, source storage quantity convention, ramp/budget mutations,
and duplicate accepted/merged balancing real_list entries remain unchanged here.
Declared corrections: preserve every available VRE owner's surplus; report
delivered battery power; aggregate batch incomes even without a thermal bid;
include the source's intended import offers with consistent price/capacity
fields and decrement the remaining deficit. D1-thermal-curtailment associates
previous output by object identity, consumes the source's thermal scan once, and
releases both water and biomass budgets by the actual curtailed quantity.
Tests distinguish these deliberate
differences from unaffected-source parity. The integration layer must handle
approved corrections and accounting; it must not sum real_list blindly. No
annual investment, checkpoint, zonal adaptation, or long-run launch is included.
"""

import gc

PHYSICAL_PERIOD_HOURS = 0.5
DEBUG_MARKET_STDOUT = False
ORIGINAL_SOURCE_SHA256 = "434f43ca9607ba1b9588826c924d48755965ad99bcf4b3dc0e13089a512e3da0"


def physical_period_hours() -> float:
    """Hours represented by one dispatch period in the restored contract."""
    return PHYSICAL_PERIOD_HOURS


class IterLimit(object):
    def __init__(self, wind_limit):
        self.limit = wind_limit
        self.idx = 0
        self.length = len(self.limit)
        self.repeat_count = 0

    def __iter__(self):
        return self

    def __next__(self):
        if self.idx < self.length:
            LIM = self.limit[self.idx]
            if self.repeat_count < 1:
                self.repeat_count += 1
            else:
                self.repeat_count = 0
                self.idx += 1
            return LIM
        else:
            # 重置索引，循环使用数据
            self.idx = 0
            self.repeat_count = 0
            LIM = self.limit[self.idx]
            self.repeat_count += 1
            return LIM


class IterLimit_new(object):
    def __init__(self, wind_limit):
        self.limit = wind_limit
        self.idx = 0
        self.length = len(self.limit)
        self.repeat_count = 0

    def __ge__(self, other):
        pass

    def __abs__(self):
        return abs(self.limit)

    def __iter__(self):
        return self

    def __next__(self):
        if self.idx < self.length:
            LIM = self.limit[self.idx]
            if self.repeat_count < 1:
                self.repeat_count += 1
            else:
                self.repeat_count = 0
                self.idx += 1
            return LIM
        else:
            # 重置索引，循环使用数据
            self.idx = 0
            self.repeat_count = 0
            LIM = self.limit[self.idx]
            self.repeat_count += 1
            return LIM


class Generator:
    def __init__(self, gen_cost, curtail_cost, carbon_emission):
        self.gen_cost = gen_cost
        self.curtail_cost = curtail_cost
        self.carbon_emission = carbon_emission


class Battery:
    def __init__(self, name, pool_limit, per_pool_limit, storage_fee, per_storage_fee, n_1, n_2, carbon_emission, capital_cost=0, battery_type=None):
        self.name = name
        self.pool_limit = pool_limit
        self.per_pool_limit = per_pool_limit
        self.storage_fee = storage_fee
        self.per_storage_fee = per_storage_fee
        self.n_1 = n_1
        self.n_2 = n_2
        self.stored_energy = {}
        self.real_gen_energy = 0
        self.carbon_emission = carbon_emission
        self.capital_cost = capital_cost
        self.run_time = 0
        # 添加电池类型属性，用于确定衰减率
        self.battery_type = battery_type

        # storage function

    def set_stored_energy_var(self, key, value):
        if key in self.stored_energy:
            self.stored_energy[key] += value
        else:
            self.stored_energy[key] = value
        # discharge from storage

    def clr_stored_energy_var(self, key, value):
        if key in self.stored_energy:
            self.stored_energy[key] -= value
            # Remove key if energy becomes negligible or negative
            if self.stored_energy[key] < 0.001:
                del self.stored_energy[key]

    def set_run_time(self):
        self.run_time +=0.5

    def cleanup_negligible_energy(self, threshold=0.001):
        """Remove entries with negligible energy to save memory"""
        keys_to_remove = [k for k, v in self.stored_energy.items() if v < threshold]
        for k in keys_to_remove:
            del self.stored_energy[k]
        return len(keys_to_remove)

    def __str__(self):
        return f"{self.name} "


class GasGenerator(Generator):
    def __init__(self, name, gen_cost, curtail_cost, carbon_emission, capacity_limit, alter_limit, startup_cost,
                 carbon_intensity, capital_cost, carbon_price, fuel_cost,real_gen_energy, unit_time_cost):
         super().__init__(gen_cost, curtail_cost, carbon_emission)
         self.name = name
         self.gen_cost = gen_cost + carbon_price + fuel_cost + unit_time_cost
         self.capacity_limit = capacity_limit
         self.alter_limit = alter_limit
         self.startup_cost = startup_cost
         self.real_gen_energy = real_gen_energy
         self.carbon_intensity = carbon_intensity
         self.capital_cost = capital_cost
         self.carbon_price = carbon_price
         self.fuel_cost = fuel_cost
         self.if_curtail = False
         self.run_time = 0

    def set_real_gen_energy(self, value):
        self.real_gen_energy = value

    def set_if_curtail(self):
        self.if_curtail = True

    def clr_if_curtail(self):
        self.if_curtail = False

    def set_run_time(self):
        self.run_time +=0.5

    def __str__(self):
        return f"{self.name} "


class ExpensiverenewableGenerator(Generator):
    def __init__(self, name, gen_cost, curtail_cost, carbon_emission, capital_cost,real_gen_energy,unit_time_cost,
                 electrolyzer_cost, energy_efficiency, electrolyzer_limit, rampup_rate, capacity_multiplier=0):
        super().__init__(gen_cost, curtail_cost, carbon_emission)
        self.gen_cost = gen_cost + unit_time_cost
        self.name = name
        self.capacity_limit = 0 # This will be updated in the loop
        self.if_curtail = False
        # storage for renewables
        self.stored_energy = {}
        self.real_gen_energy = real_gen_energy
        self.capital_cost = capital_cost
        self.run_time = 0
        self.electrolyzer_cost = electrolyzer_cost
        self.energy_efficiency = energy_efficiency
        self.electrolyzer_limit = electrolyzer_limit
        self.rampup_rate = rampup_rate
        self.real_energy = 0
        self.capacity_multiplier = capacity_multiplier # Add the new attribute

    def set_real_energy(self, value):#这个是真实的电解能量
            self.real_energy = value

    def set_real_gen_energy(self, value):
        self.real_gen_energy = value

    # storage function
    def set_stored_energy_var(self, key, value):
        self.stored_energy.update({key: value})

    # charge from curtailment
    def clr_stored_energy_var(self, key, value):
        self.stored_energy[key] -= value

    def set_if_curtail(self):
        self.if_curtail = True

    def clr_if_curtail(self):
        self.if_curtail = False

    def set_run_time(self):
        self.run_time +=0.5

    def __str__(self):
        return f"{self.name} "


class BiomassGenerator(Generator):
    def __init__(self, name, gen_cost, curtail_cost, carbon_emission, capacity_limit, alter_limit, startup_cost,
                 energy_limit, add_energy, carbon_intensity, capital_cost, carbon_price, fuel_cost,
                 real_gen_energy, unit_time_cost):
        super().__init__(gen_cost, curtail_cost, carbon_emission)
        self.name = name
        self.gen_cost = gen_cost + carbon_price + fuel_cost + unit_time_cost
        self.capacity_limit = capacity_limit
        self.energy_limit = energy_limit
        self.alter_limit = alter_limit
        self.startup_cost = startup_cost
        self.add_energy = add_energy
        self.carbon_intensity = carbon_intensity
        self.real_gen_energy = real_gen_energy
        self.have_gen_energy = real_gen_energy
        self.capital_cost = capital_cost
        self.carbon_price = carbon_price
        self.fuel_cost = fuel_cost
        self.run_time = 0

    def set_real_gen_energy(self, value):
        self.real_gen_energy = value

    def add_energy_limit(self, add_energy):
        self.energy_limit += add_energy

    def add_have_gen_energy(self, value):
        self.have_gen_energy += value

    def dec_have_gen_energy(self, value):
        self.have_gen_energy -= value

    def set_run_time(self):
        self.run_time +=0.5

    def __str__(self):
        return f"{self.name} "


class NuclearGenerator(Generator):
    def __init__(self, name, gen_cost, curtail_cost, carbon_emission, capacity_limit, alter_limit, startup_cost,
                 capital_cost, unit_time_cost):
        super().__init__(gen_cost, curtail_cost, carbon_emission)
        self.gen_cost = gen_cost + unit_time_cost
        self.name = name
        self.capacity_limit = capacity_limit
        self.alter_limit = alter_limit
        self.startup_cost = startup_cost
        self.real_gen_energy = capacity_limit
        self.capital_cost = capital_cost
        self.run_time = 0

    def set_real_gen_energy(self, value):
        self.real_gen_energy = value

    def set_run_time(self):
        self.run_time +=0.5

    def __str__(self):
        return f"{self.name} "


class WaterGenerator(Generator):
    def __init__(self, name, gen_cost, curtail_cost, carbon_emission, capacity_limit, alter_limit, energy_limit,
                 add_energy, capital_cost,real_gen_energy, unit_time_cost):
        super().__init__(gen_cost, curtail_cost, carbon_emission)
        self.gen_cost = gen_cost + unit_time_cost
        self.name = name
        self.capacity_limit = capacity_limit
        self.energy_limit = energy_limit
        self.alter_limit = alter_limit
        self.add_energy = add_energy
        self.real_gen_energy = real_gen_energy
        self.have_gen_energy = real_gen_energy
        self.capital_cost = capital_cost
        self.run_time = 0

    def set_real_gen_energy(self, value):
        self.real_gen_energy = value

    def add_energy_limit(self, add_energy):
        self.energy_limit += add_energy

    def add_have_gen_energy(self, value):
        self.have_gen_energy += value

    def dec_have_gen_energy(self, value):
        self.have_gen_energy -= value

    def set_run_time(self):
        self.run_time +=0.5

    def __str__(self):
        return f"{self.name} "


class Connection:
    def __init__(self, name, capital_cost, carbon_emission, carbon_intensity):
        self.name = name
        self.transfer_constraint = 0
        self.external_price = 0
        self.capital_cost = capital_cost
        self.carbon_emission = carbon_emission
        self.carbon_intensity = carbon_intensity
        self.sold_energy = 0

    def __str__(self):
        return (f"Connection Name: {self.name}, Transfer Constraint: {self.transfer_constraint}, "
                f"External Price: {self.external_price}, Capital Cost: {self.capital_cost}, "
                f"Carbon Emission: {self.carbon_emission}, Carbon Intensity: {self.carbon_intensity}")


class Electrolyzer:
    def __init__(self, name, capital_cost, operational_cost, energy_efficiency, cycle_life, capacity_limit, rampup_rate, body_emission):
        self.capital_cost = capital_cost
        self.operational_cost = operational_cost
        self.energy_efficiency = energy_efficiency
        self.cycle_life = cycle_life
        self.capacity_limit = capacity_limit
        self.rampup_rate = rampup_rate
        self.body_emission = body_emission
        self.real_energy = 0


    def set_real_energy(self, value):
        self.real_energy = value

    def __str__(self):
        return f"{self.name} "


def decay_func(stored_energy, battery_type=None):
    """
    储能衰减函数
    Args:
        stored_energy: 储能字典
        battery_type: 电池类型 ('1c', '0.5c', '0.25c', 'pumped_hydro', 'hydrogen')
    """
    # 根据电池类型确定衰减率
    if battery_type in ['1c', '0.5c', '0.25c']:
        decay_rate = 0.000021  # 0.0021% per period (half hour) for C-rate batteries
    elif battery_type == 'pumped_hydro':
        decay_rate = 0.000001  # 0.0001% per period (half hour) for pumped hydro (very low)
    elif battery_type == 'hydrogen':
        decay_rate = 0.000005  # 0.0005% per period (half hour) for hydrogen storage (low)
    else:
        decay_rate = 0.000021  # 默认衰减率

    for key, value in stored_energy.items():
        stored_energy[key] *= (1 - decay_rate)


def acm_income(bids, list, max_bat_price):
    income_dict = {}
    # D1-income: a storage-only clearance still earns storage settlement.
    max_gen_price = max([subbid[1] for subbid in bids if len(subbid) > 1], default=0)
    period_hours = physical_period_hours()
    for subbid in bids:
        key = subbid[0].name
        value = subbid[2] * period_hours * max_gen_price
        income_dict[key] = income_dict.get(key, 0) + value
    for sublist in list:
        if(type(sublist[0]) == Battery):
            key = sublist[0].name
            value = sublist[1] * period_hours * max_bat_price
            income_dict[key] = income_dict.get(key, 0) + value
    return income_dict


def acm_income_balance(balance_list, max_gen_price, max_bat_price):
    income_dict = {}
    period_hours = physical_period_hours()
    for sublist in balance_list:
        if(type(sublist[0]) == Battery):
            key = sublist[0].name
            value = sublist[1] * period_hours * max_bat_price
            income_dict[key] = income_dict.get(key, 0) + value
        else:
            key = sublist[0].name
            value = sublist[1] * period_hours * max_gen_price
            income_dict[key] = income_dict.get(key, 0) + value
    return income_dict


def _record_downward(actions, generator, quantity, price):
    """Optional acceptance-time evidence; no dispatch or legacy fee change."""
    if actions is not None and quantity > 0:
        actions.append((generator.name, type(generator).__name__, float(quantity), float(price)))


def _curtail_thermal_bid(bid, previous_energy, need_curtailed_energy, gen_list, curtailed_fee, actions=None):
    """Apply one ordered thermal bid using the source ramp limit (D1 repair)."""
    generator = bid[0]
    if bid[2] - previous_energy == generator.alter_limit:
        max_curtail_energy = min(2 * generator.alter_limit, bid[2])
    else:
        max_curtail_energy = (bid[2] - (previous_energy - generator.alter_limit)
                              if previous_energy >= generator.alter_limit else bid[2])
    # A unit already below its previous-output lower bound cannot be curtailed
    # further; negative curtailment must not create generation or negative fees.
    curtailed = min(need_curtailed_energy, max(0, min(bid[2], max_curtail_energy)))
    curtailed_fee.append(curtailed * bid[3])
    _record_downward(actions, generator, curtailed, bid[3])
    bid[2] -= curtailed
    generator.set_real_gen_energy(bid[2])
    for gen in gen_list:
        if gen[0] is generator:
            gen[1] = bid[2]
    if type(generator) in (WaterGenerator, BiomassGenerator):
        generator.dec_have_gen_energy(curtailed)
    return need_curtailed_energy - curtailed


def store_service_three(accepted_bids, new_bids, period, need_curtailed_energy, last_gen_energy, excess_energy,
                        gen_list, connections, electrolyzer, actions=None):
    # D1-thermal-curtailment: the history contains unaccepted offers too, so its
    # independently sorted positions cannot identify accepted generators.
    previous_by_generator = {id(row[0]): row[2] for row in last_gen_energy}
    for bid in accepted_bids:
        if type(bid[0]) != ExpensiverenewableGenerator and id(bid[0]) not in previous_by_generator:
            raise ValueError(f"previous generation missing for {bid[0].name}")
    # initialize the energy to stored as zero
    global curtailed_energy
    store_energy = 0
    # curtailment fee list
    curtailed_fee = []
    curtailed_energy_list = []
    thermal_curtail_applied = False
    soldable = []
    #print(need_curtailed_energy)
    for pool in new_bids:
        if sum(pool[0].stored_energy.values()) <= pool[0].pool_limit and need_curtailed_energy != 0:
            # curtailed_fee.append(need_curtailed_energy*item[1])
            # store the minimum among power limit, the rest of energy limit and available energy
            limit = max(0, pool[0].per_pool_limit - pool[0].stored_energy.get(period, 0) / pool[0].n_1)
            energy = min(limit, need_curtailed_energy,
                                                              (pool[0].pool_limit - sum(
                                                                  pool[0].stored_energy.values())))
            pool[0].set_stored_energy_var(period, pool[0].n_1 * energy)
            # remember this minimum
            store_energy += energy
            # energy needs to be curtailed
            need_curtailed_energy = \
                need_curtailed_energy - \
                energy
            curtailed_fee.append(energy * 0)
    if excess_energy != 0:
        for pool in new_bids:
            if sum(pool[0].stored_energy.values()) <= pool[0].pool_limit and excess_energy != 0:
                # curtailed_fee.append(need_curtailed_energy*item[1])
                # do this again for excess generation
                limit = max(0, pool[0].per_pool_limit - pool[0].stored_energy.get(period, 0) / pool[0].n_1)
                energy = min(limit, excess_energy,(pool[0].pool_limit - sum(pool[0].stored_energy.values())))
                pool[0].set_stored_energy_var(period, pool[0].n_1 * energy )
                # remember this as well
                store_energy += energy
                # final curtailment
                excess_energy = \
                    excess_energy - \
                    energy
    # sell to interconnector before there is curtailment
    sold_fee = []
    for item in connections:
        if item.transfer_constraint < 0:
            soldable.append([item, item.transfer_constraint, item.external_price])
    if not soldable:
        '''没有外售部分，直接电解然后弃电了'''
        sold_fee.append(0)
        for item in connections:
            item.sold_energy = 0
        energy_cell = min((electrolyzer.real_energy + electrolyzer.rampup_rate), electrolyzer.capacity_limit)
        if excess_energy + need_curtailed_energy > 0:
            min_value = min((excess_energy + need_curtailed_energy), energy_cell)
            energy_cell_period = min_value
            if excess_energy > min_value:
                excess_energy -= min_value
                green_hy = min_value * electrolyzer.energy_efficiency
                electrolyzer.set_real_energy(min_value)
            else:
                need_curtailed_energy = (excess_energy + need_curtailed_energy) - min_value
                excess_energy = 0
                green_hy = min_value * electrolyzer.energy_efficiency
                electrolyzer.set_real_energy(min_value)
        else:
            green_hy = 0
            electrolyzer.set_real_energy(0)
            energy_cell_period = 0
        curtailed_energy = need_curtailed_energy
        for item in accepted_bids:
            if need_curtailed_energy != 0:
                if type(item[0]) == ExpensiverenewableGenerator:
                    if item[2] >= need_curtailed_energy:
                        # curtailment fee
                        curtailed_fee.append(need_curtailed_energy * item[3])
                        _record_downward(actions, item[0], need_curtailed_energy, item[3])
                        item[2] = item[2] - need_curtailed_energy
                        item[0].set_real_gen_energy(item[2])
                        curtailed_energy_list.append([item[0], need_curtailed_energy])
                        for gen in gen_list:
                            if gen[0] == item[0]:
                                gen[1] -= need_curtailed_energy
                                break
                        need_curtailed_energy = 0
                        break
                    else:
                        curtailed_fee.append(item[2] * item[3])
                        _record_downward(actions, item[0], item[2], item[3])
                        need_curtailed_energy = need_curtailed_energy - item[2]
                        curtailed_energy_list.append([item[0], item[2]])
                        item[0].set_real_gen_energy(0)
                        for gen in gen_list:
                            if gen[0] == item[0]:
                                gen[1] -= item[2]
                            else:
                                pass
                else:
                    # Preserve the original first-thermal scan (including its
                    # priority over later interleaved VRE bids), but never run
                    # that scan again when the outer loop reaches another unit.
                    if not thermal_curtail_applied:
                        for thermal in accepted_bids:
                            if need_curtailed_energy == 0:
                                break
                            if type(thermal[0]) != ExpensiverenewableGenerator:
                                need_curtailed_energy = _curtail_thermal_bid(
                                    thermal, previous_by_generator[id(thermal[0])],
                                    need_curtailed_energy, gen_list, curtailed_fee, actions)
                        thermal_curtail_applied = True
            # no curtailment means curtailment fee is zero
            elif need_curtailed_energy == 0:
                curtailed_fee.append(0)
                break
    else:
        soldable.sort(key=lambda x: x[2], reverse=True)
        # to see whether the price is positive
        for item in soldable:
            if item[2] > 0:
                # can sell this much of energy
                sell_energy = min(abs(item[1]), (excess_energy + need_curtailed_energy))
                sold_fee.append(sell_energy * item[2])
                item[0].sold_energy = sell_energy
                # rest of energy
                if excess_energy > sell_energy:
                    excess_energy -= sell_energy
                else:
                    need_curtailed_energy = (excess_energy + need_curtailed_energy) - sell_energy
                    excess_energy = 0
            else:
                sold_fee.append(0)
                item[0].sold_energy = 0
        energy_cell = min((electrolyzer.real_energy + electrolyzer.rampup_rate), electrolyzer.capacity_limit)
        if excess_energy + need_curtailed_energy > 0:
            min_value = min((excess_energy + need_curtailed_energy), energy_cell)
            energy_cell_period = min_value
            if excess_energy > min_value:
                excess_energy -= min_value
                green_hy = min_value * electrolyzer.energy_efficiency
                electrolyzer.set_real_energy(min_value)
            else:
                need_curtailed_energy = (excess_energy + need_curtailed_energy) - min_value
                excess_energy = 0
                green_hy = min_value * electrolyzer.energy_efficiency
                electrolyzer.set_real_energy(min_value)
        else:
            green_hy = 0
            electrolyzer.set_real_energy(0)
            energy_cell_period = 0
        curtailed_energy = need_curtailed_energy
        if need_curtailed_energy > 0:
            for item in accepted_bids:
                if need_curtailed_energy != 0:
                    if type(item[0]) == ExpensiverenewableGenerator:
                        if item[2] >= need_curtailed_energy:
                            curtailed_fee.append(need_curtailed_energy * item[3])
                            _record_downward(actions, item[0], need_curtailed_energy, item[3])
                            item[2] = item[2] - need_curtailed_energy
                            item[0].set_real_gen_energy(item[2])
                            curtailed_energy_list.append(curtailed_energy)
                            for gen in gen_list:
                                if gen[0] == item[0]:
                                    gen[1] -= need_curtailed_energy
                                    break
                            need_curtailed_energy = 0
                            break
                        else:
                            curtailed_fee.append(item[2] * item[3])
                            _record_downward(actions, item[0], item[2], item[3])
                            need_curtailed_energy = need_curtailed_energy - item[2]
                            curtailed_energy_list.append(item[2])
                            item[0].set_real_gen_energy(0)
                            for gen in gen_list:
                                if gen[0] == item[0]:
                                    gen[1] -= item[2]
                                else:
                                    pass
                    else:
                        if not thermal_curtail_applied:
                            for thermal in accepted_bids:
                                if need_curtailed_energy == 0:
                                    break
                                if type(thermal[0]) != ExpensiverenewableGenerator:
                                    need_curtailed_energy = _curtail_thermal_bid(
                                        thermal, previous_by_generator[id(thermal[0])],
                                        need_curtailed_energy, gen_list, curtailed_fee, actions)
                            thermal_curtail_applied = True
        else:
            sold_fee.append(0)
    #print(store_energy)
    return (curtailed_fee, store_energy, gen_list, curtailed_energy, excess_energy, sold_fee,green_hy,
            energy_cell_period,curtailed_energy_list)


def ahead_market_bidding(generators, batterys, forecast_demand, period, accepted_bids,  ahead_renewables, ahead_other,
                         ahead_traditional, ahead_nuclear, bidding_factor):
    renewable_hy_list = []
    for gen in generators:
        if type(gen) == ExpensiverenewableGenerator:
            energy = min((gen.real_energy + gen.rampup_rate), gen.electrolyzer_limit)
            if gen.capacity_limit != 0:
                if energy > gen.capacity_limit:
                    gen.capacity_limit = 0
                    renewable_green_hy = gen.capacity_limit * gen.energy_efficiency
                    gen.set_real_energy(gen.capacity_limit)
                    renewable_hy_list.append([gen, gen.capacity_limit * gen.electrolyzer_cost, renewable_green_hy])
                else:
                    gen.capacity_limit -= energy
                    renewable_green_hy = energy * gen.energy_efficiency
                    gen.set_real_energy(energy)
                    renewable_hy_list.append([gen, energy * gen.electrolyzer_cost, renewable_green_hy])
    # bids among generator agent characteristics
    bids = [[gen, gen.gen_cost * bidding_factor, gen.capacity_limit, gen.curtail_cost, 0] for gen in generators]
    # initialize excess energy
    excess_energy = 0
    max_bat_price =0
    # add start-up cost
    gen_list = []
    excess_energy_list = []
    accepted_bids_name = []
    for item in accepted_bids:
        accepted_bids_name.append(item[0])
    for item in bids:
        if (item[0] not in accepted_bids_name and (type(item[0]) != WaterGenerator and type(item[0]) != ExpensiverenewableGenerator)):
            item[1] += item[0].startup_cost
        else:
            pass
        # limit for hydro and biomass, natural storage consideration
        if type(item[0]) == BiomassGenerator or type(item[0]) == WaterGenerator:
            # add natural output of hydro and biomass
            item[0].add_energy_limit(item[0].add_energy)
            #if item[0].energy_limit - item[0].have_gen_energy < item[0].have_gen_energy:
                #bids.remove(item)
    # conisder the storage
    new_bids = [[bat, bat.pool_limit] for bat in batterys]
    # selectable discharge
    for item in new_bids:
        decay_func(item[0].stored_energy, item[0].battery_type)
    # storage composition
    storage_pool_composition = []
    for item in new_bids:
        storage_pool_composition.append([item[0], sum(item[0].stored_energy.values())])
    # print(storage_pool_composition)
    # send storage amount to storage_pool_list
    storage_pool_list = []
    for i in range(len(new_bids)):
        original_dict = new_bids[i][0].stored_energy
        # run through energy period of pool
        for key in original_dict:
            # storage_pool_list 's characteristics [generator，price，stored at which price，charge amount]
            storage_pool_list.append([new_bids[i][0],
                                      ((period - key) * new_bids[i][0].per_storage_fee
                                     + new_bids[i][0].storage_fee) * bidding_factor,
                                      key,
                                      original_dict[key]])
        # storage_pool and merge_storage_pool to plot
        # ps:with discharge
    storage_pool = {}
    if new_bids:  # Safety check to prevent IndexError
        for key, value in new_bids[0][0].stored_energy.items():
            if key in storage_pool:
                storage_pool[key] += value
            else:
                storage_pool[key] = value
    # charge amount in no-charge period is 0（or keyerror）
    # Keep dictionary sparse - only store keys with actual values to save memory
    # Only remove entries with truly negligible energy (< 0.001) to save memory
    # Don't filter by age since decay is slow and old energy still matters
    if storage_pool:
        # Remove entries with negligible energy (below threshold)
        # This helps with memory while preserving all meaningful energy
        ENERGY_THRESHOLD = 0.001  # Remove entries with energy < 0.001
        # Silently remove entries with negligible energy to save memory
        storage_pool = {k: v for k, v in storage_pool.items() if v >= ENERGY_THRESHOLD}
        # Sort efficiently by creating new dict with sorted keys only
        # This avoids creating intermediate large lists
        if storage_pool:
            sorted_keys = sorted(storage_pool.keys())
            storage_pool = {k: storage_pool[k] for k in sorted_keys}
    # overall storage
    merge_storage_pool = {}
    for d in new_bids:
        for key, value in d[0].stored_energy.items():
            if key in merge_storage_pool:
                merge_storage_pool[key] += value
            else:
                merge_storage_pool[key] = value
    if merge_storage_pool:
        # Only remove entries with truly negligible energy (< 0.001) to save memory
        # Don't filter by age since decay is slow and old energy still matters
        ENERGY_THRESHOLD = 0.001  # Remove entries with energy < 0.001
        # Silently remove entries with negligible energy to save memory
        merge_storage_pool = {k: v for k, v in merge_storage_pool.items() if v >= ENERGY_THRESHOLD}
        # Sort efficiently by creating new dict with sorted keys only
        # This avoids creating intermediate large lists
        if merge_storage_pool:
            sorted_keys = sorted(merge_storage_pool.keys())
            merge_storage_pool = {k: merge_storage_pool[k] for k in sorted_keys}

    # Force garbage collection to free memory
    gc.collect()

    new_list = bids + storage_pool_list
    # bid
    new_list.sort(key=lambda x: x[1])
    # print(new_list)
    # benchmark
    demand_met = 0
    # nuclear may lead to excess generation because can't ramp down
    # take down this to check
    real_forecast_demand = 0
    # chosen generators in wholesale market
    last_gen_energy = [(item[0], item[3], item[0].real_gen_energy) for item in bids]
    accepted_gens = []
    accepted_bids_period = []
    # calculate price
    add_price_ahead = []
    for item in new_list:
        # loop if generation is small than demand
        if demand_met < forecast_demand:
            # if generator instead of storage, use this method
            if len(item) == 5:
                # check if beyond limit
                if item[2] != 0:
                    # if no enough capacity
                    if type(item[0]) != ExpensiverenewableGenerator:
                        if type(item[0]) != WaterGenerator and type(item[0]) != BiomassGenerator:
                            if min((item[0].real_gen_energy + item[0].alter_limit), item[2]) <= forecast_demand:
                                energy = min((item[0].real_gen_energy + item[0].alter_limit), item[2])
                                item[0].set_real_gen_energy(
                                    energy)
                                accepted_bids_period.append(
                                    [item[0], item[1], energy,
                                     item[3]])
                                gen_list.append([item[0], energy])
                                forecast_demand -= energy
                                accepted_gens.append(item[0])
                                item[0].set_run_time()
                                if type(item[0]) == NuclearGenerator:
                                    ahead_nuclear[period] += item[1] * energy
                                else:
                                    ahead_traditional[period] += item[1] * energy
                            else:
                                if type(item[0]) != NuclearGenerator:
                                    item[0].set_real_gen_energy(forecast_demand)
                                    accepted_gens.append(item[0])
                                    item[0].set_run_time()
                                    accepted_bids_period.append([item[0], item[1], forecast_demand, item[3]])
                                    gen_list.append([item[0], forecast_demand])
                                    ahead_traditional[period] += item[1] * forecast_demand
                                else:
                                    energy = max((item[0].real_gen_energy - item[0].alter_limit), forecast_demand)
                                    excess_energy = energy - forecast_demand
                                    excess_energy_list.append([item[0],excess_energy])
                                    item[0].set_real_gen_energy(energy)
                                    ahead_nuclear[period] += item[1] * energy
                                    accepted_gens.append(item[0])
                                    item[0].set_run_time()
                                    accepted_bids_period.append([item[0], item[1], energy, item[3]])
                                    gen_list.append([item[0], energy])
                                forecast_demand = 0
                                break
                        else:
                            if min((item[0].real_gen_energy + item[0].alter_limit), item[2],
                                   (item[0].energy_limit - item[0].have_gen_energy)) <= forecast_demand:
                                energy =  min((item[0].real_gen_energy + item[0].alter_limit), item[2],
                                   (item[0].energy_limit - item[0].have_gen_energy))
                                item[0].set_real_gen_energy(energy)
                                accepted_gens.append(item[0])
                                item[0].set_run_time()
                                accepted_bids_period.append(
                                    [item[0], item[1], energy, item[3]])
                                gen_list.append([item[0], energy])
                                forecast_demand -= energy
                                item[0].add_have_gen_energy(energy)
                                ahead_other[period] += item[1] * energy
                            else:
                                item[0].set_real_gen_energy(forecast_demand)
                                accepted_gens.append(item[0])
                                item[0].set_run_time()
                                accepted_bids_period.append([item[0], item[1], forecast_demand, item[3]])
                                gen_list.append([item[0], forecast_demand])
                                ahead_other[period] += item[1] * forecast_demand
                                item[0].add_have_gen_energy(forecast_demand)
                                forecast_demand = 0
                                break
                    else:
                        if item[2] <= forecast_demand:
                            # print(accepted_bids)
                            accepted_gens.append(item[0])
                            item[0].set_run_time()
                            accepted_bids_period.append([item[0], item[1], item[2], item[3]])
                            gen_list.append([item[0], item[2]])
                            item[0].set_real_gen_energy(item[2])
                            ahead_renewables[period] += item[1] * item[2]
                            forecast_demand -= item[2]
                        else:
                            accepted_gens.append(item[0])
                            item[0].set_run_time()
                            accepted_bids_period.append([item[0], item[1], forecast_demand, item[3]])
                            excess_energy = item[2] - forecast_demand
                            excess_energy_list.append([item[0], excess_energy])
                            bids_copy = bids.copy()
                            bids_copy.remove(item)
                            set_gen = set(item[0] for item in accepted_bids_period)
                            for gen in bids_copy:
                                if type(gen[0]) == ExpensiverenewableGenerator and gen[0] not in set_gen:
                                    excess_energy += gen[0].capacity_limit
                                    excess_energy_list.append([item[0], gen[0].capacity_limit])
                            item[0].set_real_gen_energy(forecast_demand)
                            ahead_renewables[period] += item[1] * forecast_demand
                            gen_list.append([item[0], forecast_demand])
                            forecast_demand = 0
                            break
                else:
                    pass
                #print(item[0])
            # if chose storage pool
            else:
                # D1-power: the original discharge path ignored the per-period
                # power limit entirely. All batches share one delivered limit.
                delivered = sum(q for source, q in gen_list if source is item[0])
                item[3] = min(item[3], max(0, item[0].per_pool_limit - delivered) / item[0].n_2)
                if item[3] <= 0:
                    continue
                if item[3] <= (forecast_demand/item[0].n_2):
                    forecast_demand -= item[0].n_2*item[3]
                    gen_list.append([item[0], item[0].n_2*item[3]])
                    # discharge
                    item[0].clr_stored_energy_var(item[2], item[3])
                    # calculate storage cost
                    add_price_ahead.append(item[1] * item[3])
                    max_bat_price = item[1]
                else:
                    item[0].clr_stored_energy_var(item[2], (forecast_demand/item[0].n_2))
                    # D1-delivery: stock withdrawal is demand/n_2; delivered
                    # generation is demand, as in the balancing branch.
                    gen_list.append([item[0], forecast_demand])
                    add_price_ahead.append((forecast_demand/item[0].n_2) * item[1])
                    forecast_demand = 0
                    max_bat_price = item[1]
                    break
        else:
            pass
    # D1-surplus: the original collected this only in the partially accepted
    # VRE branch, and attributed other units to its current item. Rebuild from
    # the available/accepted quantities while retaining non-VRE overgeneration.
    non_vre_rows = [row for row in excess_energy_list if type(row[0]) != ExpensiverenewableGenerator]
    non_vre_excess = max(0, excess_energy - sum(row[1] for row in excess_energy_list))
    accepted_vre = {}
    for source, price, quantity, curtail_cost in accepted_bids_period:
        if type(source) == ExpensiverenewableGenerator:
            accepted_vre[source] = accepted_vre.get(source, 0) + quantity
    excess_energy_list = [[source, max(0, source.capacity_limit - accepted_vre.get(source, 0))]
                          for source in generators if type(source) == ExpensiverenewableGenerator]
    excess_energy_list = non_vre_rows + [row for row in excess_energy_list if row[1] > 0]
    excess_energy = non_vre_excess + sum(row[1] for row in excess_energy_list)
    accepted_bids[:] = accepted_bids_period
    if any(isinstance(obj, NuclearGenerator) for obj in accepted_gens):
        pass
    else:
        for gen in generators:
            if type(gen) == NuclearGenerator:
                gen.set_real_gen_energy(gen.real_gen_energy*0.99)
    # calculate overall storage fee，add each storage pool together
    total_add_price_ahead = sum(add_price_ahead)
    '''
    for item in new_bids:
        if DEBUG_MARKET_STDOUT:
            print(item[0].stored_energy)
    '''
    gen_list_name = []
    for item in gen_list:
        if item[1] != 0:
            gen_list_name.append([item[0].name, item[1]])
    income_dict = acm_income(accepted_bids, gen_list, max_bat_price)
    return accepted_bids, total_add_price_ahead, storage_pool, merge_storage_pool, storage_pool_composition, \
           last_gen_energy, excess_energy, ahead_renewables, ahead_other, ahead_traditional, gen_list, ahead_nuclear, \
        gen_list_name, bids, income_dict,excess_energy_list,renewable_hy_list


def curtailment_market_bidding(period, real_demand, forecast_demand, accepted_bids, last_gen_energy, excess_energy,
                               gen_list, connections,electrolyzer, batterys, actions=None):
    # choose available renewables for charging
    new_bids = [[bat, bat.storage_fee, bat.per_storage_fee, bat.n_1, bat.n_2] for bat in batterys]
    #print(new_bids)
    # curtailment fee rand
    new_bids.sort(key=lambda x: (x[1], x[2], (x[3] * x[4])))
    # new storage pool composition
    storage_pool_composition_after = []
    for item in new_bids:
        storage_pool_composition_after.append([item[0], sum(item[0].stored_energy.values())])
    accepted_bids.sort(key=lambda x: x[3])
    last_gen_energy.sort(key=lambda x: x[1])
    # calculate needed curtailment
    need_curtailed_energy = forecast_demand - real_demand
    # storage service 3(central dispatch curtailment and excess generation instead of attach storage to generator)
    (curtailed_fee, store_energy, gen_list, curtailed_energy, excess_energy, sold_fee,
     green_hy,energy_cell_period,curtailed_energy_list) \
        = store_service_three(accepted_bids, new_bids, period, need_curtailed_energy, last_gen_energy, excess_energy,
                              gen_list, connections,electrolyzer, actions)
    real_list = [[sub_list[0], sub_list[2]] for sub_list in accepted_bids if sub_list[2] != 0]
    #print(curtailed_fee)
    #test_gen.capacity_limit = test_gen.capacity_limit + need_curtailed_energy #恢复
    return curtailed_fee, store_energy, real_list, storage_pool_composition_after, gen_list, curtailed_energy, \
           excess_energy,sold_fee, green_hy,energy_cell_period,curtailed_energy_list


def balancing_market_bidding(generators, period, real_demand, forecast_demand, accepted_bids, excess_energy,
                             balance_renewables, balance_other, balance_traditional, gen_list, balance_nuclear,
                             connections, gen_list_name, bids, electrolyzer,excess_energy_list, batterys, bidding_factor,
                             actions=None):
    # calculate energy gap
    energy_provided = real_demand - forecast_demand
    #print(energy_provided)
    #print('excess_energy', excess_energy)
    # initialize balancing biddings
    balancing_fee = []
    store_energy = 0
    accepted_list = [[sub_list[0], sub_list[2]] for sub_list in accepted_bids]
    balance_list = []
    max_gen_price =0
    max_bat_price =0
    # biddings
    bids.sort(key=lambda x: x[1])
    sold_fee = []
    bought_fee = []
    soldable = []
    buable = []
    for item in connections:
        item.sold_energy = 0
    #gens = iter(bids)
    # rememmber available generators，namely generation after test_gen(included)
    # use test_gen to the marginal generator,，who has rest availability（generators before used up），from hime to bid
    if len(accepted_bids) != 0:
        test_gen = accepted_bids[-1]
    # if only use storage，then test-gen is the first generator
    else:
        test_gen = bids[0]
    #print(test_gen)
    new_bids = [[bat, bat.pool_limit] for bat in batterys]
    if excess_energy_list:
        # 如果需要补充发电的电量小于所有子列表的和，按比例分配
        if energy_provided <= excess_energy:
            total_excess_for_proportion = sum(item[1] for item in excess_energy_list)
            if total_excess_for_proportion > 0:
                for item in excess_energy_list:
                    proportion = item[1] / total_excess_for_proportion
                    energy_from_this = energy_provided * proportion
                    if type(item[0]) != ExpensiverenewableGenerator:
                        # Nuclear minimum output was already generated and
                        # settled in ahead; serving more load does not generate
                        # or sell this same MWh a second time.
                        item[1] -= energy_from_this
                        continue
                    balancing_fee.append(item[0].gen_cost * bidding_factor * energy_from_this)
                    balance_renewables[period] += item[0].gen_cost * bidding_factor * energy_from_this
                    balance_list.append([item[0], energy_from_this])
                    for gen in gen_list:
                        if gen[0] == item[0]:
                            gen[1] += energy_from_this
                            break
                    else:
                        gen_list.append([item[0], energy_from_this])
                    item[1] -= energy_from_this
            excess_energy -= energy_provided
            energy_provided = 0
        #否则就全用上了
        else:
            energy_provided = energy_provided - excess_energy
            excess_energy = 0
            for item in excess_energy_list:
                if type(item[0]) != ExpensiverenewableGenerator:
                    item[1] = 0
                    continue
                if(item[1] == 0):
                    pass
                else:
                    balancing_fee.append(item[0].gen_cost * bidding_factor * item[1])
                    balance_renewables[period] += item[0].gen_cost * bidding_factor * item[1]
                    balance_list.append([item[0], item[1]])
                    for gen in gen_list:
                        if gen[0] == item[0]:
                            gen[1] += item[1]
                            break
                    else:
                        gen_list.append([item[0], item[1]])
                item[1] = 0
    '''
    if excess_energy != 0:
        if excess_energy > energy_provided:
            balancing_fee.append(test_gen[1] * energy_provided)
            balance_renewables[period] += test_gen[1] * energy_provided
            balance_list.append([test_gen[0], energy_provided])
            for gen in gen_list:
                if gen[0] == test_gen[0]:
                    gen[1] += energy_provided
                else:
                    pass
            excess_energy = excess_energy - energy_provided
            energy_provided = 0
        else:
            balancing_fee.append(test_gen[1] * excess_energy)
            balance_renewables[period] += test_gen[1] * excess_energy
            balance_list.append([test_gen[0], excess_energy])
            for gen in gen_list:
                if gen[0] == test_gen[0]:
                    gen[1] += excess_energy
                else:
                    pass
            energy_provided = energy_provided - excess_energy
            excess_energy = 0
    #print('excess_energy', excess_energy)
    '''
    if excess_energy != 0:
        for pool in new_bids:
            if sum(pool[0].stored_energy.values()) <= pool[0].pool_limit and excess_energy != 0:
                # curtailed_fee.append(need_curtailed_energy*item[1])
                # store energy
                limit = max(0, pool[0].per_pool_limit - pool[0].stored_energy.get(period, 0) / pool[0].n_1)
                energy = min(limit, excess_energy, (pool[0].pool_limit - sum(pool[0].stored_energy.values())))
                pool[0].set_stored_energy_var(period, pool[0].n_1 * energy)
                # take down this minimum
                store_energy += energy
                # rest of excess energy
                excess_energy = \
                    excess_energy - energy

    # calculate storage price
    add_price_balance = [0]
    #print('excess_energy', excess_energy)
    #print(energy_provided)
    if energy_provided >= 0:
        # add revelent parameters to storage_pool_list
        storage_pool_list = []
        for i in range(len(new_bids)):
            # change the original_dict
            original_dict = new_bids[i][0].stored_energy
            # run through the original dict
            for key in original_dict:
                # stored energy can only be used after 2 periods
                if period - key >= 2:
                    # storage_pool_list parameter[generator，price，when，charge amount]
                    storage_pool_list.append([new_bids[i][0],
                                              ((period - key) * new_bids[i][0].per_storage_fee
                                              + new_bids[i][0].storage_fee) * bidding_factor,
                                              key,
                                              original_dict[key]])
        # find test_gen，loop from the last one with availability
        search_element = test_gen[0]
        start_index = None
        '''
        bids_name = []
        for item in bids:
            bids_name.append(item[0].name)
        if DEBUG_MARKET_STDOUT:
            print(bids_name)
        '''
        for index, element in enumerate(bids):
            if element[0] == search_element:
                start_index = index
                break
        if start_index is not None:
            # from test_gen to loop
            add_bids = bids[start_index:]
        # add storage and generator，bid together，note that generators in forms of tuple but storage in forms of list to distinguish
        new_list = add_bids + storage_pool_list
        for item in connections:
            if item.transfer_constraint < 0:
                soldable.append([item, item.transfer_constraint, item.external_price])
            else:
                # D1-import: match the common (asset, price, capacity, age)
                # sorting convention; the original never appended these bids.
                buable.append((item, item.external_price, item.transfer_constraint, 0))
        new_list.extend(buable)
        if soldable and excess_energy > 0:
            soldable.sort(key=lambda x: x[2])
            # positive price can sell
            for item in soldable:
                if item[2] > 0:
                    sell_energy = min(abs(item[1]), excess_energy)
                    sold_fee.append(sell_energy * item[2])
                    item[0].sold_energy = sell_energy
                    excess_energy -= sell_energy
                else:
                    sold_fee.append(0)
                    item[0].sold_energy = 0
        if not buable:
            pass
        else:
            sold_fee.append(0)
        if excess_energy != 0:
            energy_cell = min((electrolyzer.real_energy + electrolyzer.rampup_rate), electrolyzer.capacity_limit)
            min_value = min(excess_energy, energy_cell)
            energy_cell_period = min_value
            excess_energy -= min_value
            green_hy = min_value * electrolyzer.energy_efficiency
            electrolyzer.set_real_energy(min_value)
        else:
            green_hy = 0
            electrolyzer.set_real_energy(0)
            energy_cell_period = 0
        # bids
        new_list.sort(key=lambda x: x[1])
        # distinguish storage or generator, distinguish if generate in wholesale
        '''
        new_list_copy = []
        for item in new_list:
            if type(item[0]) != Battery:
                new_list_copy.append(item)
            if DEBUG_MARKET_STDOUT:
                print(new_list_copy)
        '''
        for element in new_list:
            if energy_provided <= 0:
                break
            # if choose generator
            if type(element) == list and len(element) == 5:
                # check the ramp-up down limit
                if element[0] == test_gen[0]:
                    if type(element[0]) != ExpensiverenewableGenerator:
                        if type(element[0]) != WaterGenerator and type(element[0]) != BiomassGenerator:
                            valid_energy = min((element[0].real_gen_energy + element[0].alter_limit), element[2]) - \
                                           test_gen[2]
                            if valid_energy >= energy_provided:
                                balancing_fee.append(element[1] * energy_provided)
                                if type(element[0]) == NuclearGenerator:
                                    balance_nuclear[period] += element[1] * energy_provided
                                else:
                                    balance_traditional[period] += element[1] * energy_provided
                                balance_list.append([element[0], energy_provided])

                                max_gen_price = element[1]
                                for gen in gen_list:
                                    if gen[0] == test_gen[0]:
                                        gen[1] += energy_provided
                                    else:
                                        pass
                                element[0].set_real_gen_energy(test_gen[2] + energy_provided)
                                energy_provided = 0
                                break
                            else:
                                balancing_fee.append(element[1] * valid_energy)
                                balance_list.append([element[0], valid_energy])

                                max_gen_price = element[1]
                                element[0].set_real_gen_energy(test_gen[2] + valid_energy)
                                energy_provided = energy_provided - valid_energy
                                for gen in gen_list:
                                    if gen[0] == test_gen[0]:
                                        gen[1] += valid_energy
                                    else:
                                        pass
                                if type(element[0]) == NuclearGenerator:
                                    balance_nuclear[period] += element[1] * valid_energy
                                else:
                                    balance_traditional[period] += element[1] * valid_energy
                        else:
                            valid_energy = min((element[0].real_gen_energy + element[0].alter_limit), element[2],
                                               (element[0].energy_limit - element[0].have_gen_energy)) - test_gen[2]
                            if valid_energy >= energy_provided:
                                balancing_fee.append(element[1] * energy_provided)
                                balance_other[period] += element[1] * energy_provided
                                balance_list.append([element[0], energy_provided])

                                max_gen_price = element[1]
                                for gen in gen_list:
                                    if gen[0] == test_gen[0]:
                                        gen[1] += energy_provided
                                    else:
                                        pass
                                element[0].set_real_gen_energy(test_gen[2] + energy_provided)
                                element[0].add_have_gen_energy(energy_provided)
                                energy_provided = 0
                                break
                            else:
                                balancing_fee.append(element[1] * valid_energy)
                                balance_other[period] += element[1] * valid_energy
                                balance_list.append([element[0], valid_energy])

                                max_gen_price = element[1]
                                for gen in gen_list:
                                    if gen[0] == test_gen[0]:
                                        gen[1] += valid_energy
                                    else:
                                        pass
                                element[0].set_real_gen_energy(test_gen[2] + valid_energy)
                                element[0].add_have_gen_energy(valid_energy)
                                energy_provided = energy_provided - valid_energy
                    else:
                        pass
                else:
                    if type(element[0]) != ExpensiverenewableGenerator:
                        if type(element[0]) != WaterGenerator and type(element[0]) != BiomassGenerator:
                            valid_energy = min((element[0].real_gen_energy + element[0].alter_limit), element[2])
                            if valid_energy >= energy_provided:
                                balancing_fee.append(element[1] * energy_provided)
                                if type(element[0]) == NuclearGenerator:
                                    balance_nuclear[period] += element[1] * energy_provided
                                else:
                                    balance_traditional[period] += element[1] * energy_provided
                                balance_list.append([element[0], energy_provided])
                                element[0].set_run_time()
                                max_gen_price = element[1]
                                gen_list.append([element[0], energy_provided])
                                element[0].set_real_gen_energy(energy_provided)
                                energy_provided = 0
                                break
                            else:
                                balancing_fee.append(element[1] * valid_energy)
                                if type(element[0]) == NuclearGenerator:
                                    balance_nuclear[period] += element[1] * valid_energy
                                else:
                                    balance_traditional[period] += element[1] * valid_energy
                                balance_list.append([element[0], valid_energy])
                                element[0].set_run_time()
                                max_gen_price = element[1]
                                gen_list.append([element[0], valid_energy])
                                element[0].set_real_gen_energy(valid_energy)
                                energy_provided = energy_provided - valid_energy
                        else:
                            valid_energy = min((element[0].real_gen_energy + element[0].alter_limit), element[2],
                                               (element[0].energy_limit - element[0].have_gen_energy))
                            if valid_energy >= energy_provided:
                                balancing_fee.append(element[1] * energy_provided)
                                balance_other[period] += element[1] * energy_provided
                                balance_list.append([element[0], energy_provided])
                                element[0].set_run_time()
                                max_gen_price = element[1]
                                gen_list.append([element[0], energy_provided])
                                element[0].set_real_gen_energy(energy_provided)
                                element[0].add_have_gen_energy(energy_provided)
                                energy_provided = 0
                                break
                            else:
                                balancing_fee.append(element[1] * valid_energy)
                                balance_other[period] += element[1] * valid_energy
                                balance_list.append([element[0], valid_energy])
                                element[0].set_run_time()
                                max_gen_price = element[1]
                                gen_list.append([element[0], valid_energy])
                                element[0].set_real_gen_energy(valid_energy)
                                element[0].add_have_gen_energy(valid_energy)
                                energy_provided = energy_provided - valid_energy
                    else:
                        '''
                        valid_energy = element[2]
                        if valid_energy >= energy_provided:
                            balancing_fee.append(element[1] * energy_provided)
                            balance_renewables[period] += element[1] * energy_provided
                            element[0].set_real_gen_energy(test_gen[2] + energy_provided)
                            balance_list.append([element[0], energy_provided])
                            gen_list.append([element[0], energy_provided])
                            energy_provided = 0
                            break
                        else:
                            balancing_fee.append(element[1] * valid_energy)
                            balance_renewables[period] += element[1] * valid_energy
                            element[0].set_real_gen_energy(test_gen[2] + energy_provided)
                            balance_list.append([element[0], valid_energy])
                            gen_list.append([element[0], valid_energy])
                            energy_provided = energy_provided - valid_energy
                        '''
                        pass
            # if choose storage pool
            elif type(element) == list and len(element) == 4:
                delivered = sum(q for source, q in gen_list if source is element[0])
                element[3] = min(element[3], max(0, element[0].per_pool_limit - delivered) / element[0].n_2)
                # can't use when empty
                if element[3] != 0:
                    # can only discharge to zero
                    if element[3] <= (energy_provided/element[0].n_2):
                        max_bat_price = element[1]
                        energy_provided -= element[0].n_2*element[3]
                        # discharge from stock
                        element[0].clr_stored_energy_var(element[2], element[3])
                        # calculate cost
                        add_price_balance.append(element[1] * element[3])
                        balance_list.append([element[0], element[0].n_2*element[3]])
                        found = False
                        for gen in gen_list:
                            if gen[0] == element[0]:
                                gen[1] += element[0].n_2*element[3]
                                found = True
                                break
                        if not found:
                            gen_list.append([element[0], element[0].n_2*element[3]])
                    else:
                        max_bat_price = element[1]
                        element[0].clr_stored_energy_var(element[2], (energy_provided/element[0].n_2))
                        add_price_balance.append((energy_provided/element[0].n_2) * element[1])
                        balance_list.append([element[0], energy_provided])
                        found = False
                        for gen in gen_list:
                            if gen[0] == element[0]:
                                gen[1] += energy_provided
                                found = True
                                break
                        if not found:
                            gen_list.append([element[0], energy_provided])
                        energy_provided = 0
                        break
            elif type(element) == tuple and len(element) == 4:
                valid_energy = max(0, element[2])
                if valid_energy >= energy_provided:
                    balancing_fee.append(element[1] * energy_provided)
                    bought_fee.append(element[1] * energy_provided)
                    gen_list.append([element[0], energy_provided])
                    balance_list.append([element[0], energy_provided])
                    max_gen_price = element[1]
                    energy_provided = 0
                    break
                else:
                    balancing_fee.append(element[1] * valid_energy)
                    balance_list.append([element[0], valid_energy])
                    gen_list.append([element[0], valid_energy])
                    bought_fee.append(element[1] * valid_energy)
                    energy_provided -= valid_energy
                    if valid_energy > 0:
                        max_gen_price = element[1]
    else:
        if excess_energy != 0:
            energy_cell = min((electrolyzer.real_energy + electrolyzer.rampup_rate), electrolyzer.capacity_limit)
            min_value = min(excess_energy, energy_cell)
            energy_cell_period = min_value
            excess_energy -= min_value
            green_hy = min_value * electrolyzer.energy_efficiency
            electrolyzer.set_real_energy(min_value)
        else:
            green_hy = 0
            electrolyzer.set_real_energy(0)
            energy_cell_period = 0
    #print('excess_energy', excess_energy)
    #print(energy_provided)
    balance_list_name = []
    for item in balance_list:
        balance_list_name.append([item[0].name, item[1]])
    if energy_provided != 0:
        if DEBUG_MARKET_STDOUT:
            print('insufficient energy', period)
            print(energy_provided)
            print(gen_list_name)
            print(balance_list_name)
            print('----------------------------------------------------', period)
    total_add_price_balance = sum(add_price_balance)
    real_list = [x for x in accepted_list] + [y for y in balance_list if y[0] not in [x[0] for x in accepted_list]] + \
                [[x[0], x[1] + y[1]] for x in accepted_list for y in balance_list if x[0] == y[0]]
    storage_pool_composition_after = []
    for item in new_bids:
        storage_pool_composition_after.append([item[0], sum(item[0].stored_energy.values())])
    income_dict_balance = acm_income_balance(balance_list, max_gen_price, max_bat_price)
    if actions is not None:
        actions.extend((asset.name, float(quantity)) for asset, quantity in balance_list)
    return balancing_fee, total_add_price_balance, real_list, store_energy, storage_pool_composition_after, \
           balance_renewables, balance_other, balance_traditional, gen_list ,balance_nuclear, excess_energy, sold_fee, \
           bought_fee, green_hy, energy_cell_period, income_dict_balance, energy_provided
