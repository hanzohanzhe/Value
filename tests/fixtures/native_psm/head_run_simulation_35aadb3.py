# Frozen verbatim copy of the 35aadb3 default-PSM period loop (P0-6 S1).
#
# Source: gridform_core/builtin/scheme_c_1000twh/runtime_compat/
#         modular_simulation_model.py at commit 35aadb3, function run_simulation.
# The VERBATIM segments below are byte-identical copies of the named source
# lines; tests/native_reproduction_harness.py pins the SHA-256 of every
# segment and of the whole source file and refuses to run if either differs.
# Only the two HARNESS REPLACEMENT blocks are authored: they replace the
# netCDF weather / interconnector CSV loading (35aadb3:2365-2591) and the
# per-period weather and interconnector assignment (35aadb3:2600-2690) with
# exact synthetic per-period inputs. Everything else -- accumulator
# initialisation (including total_storage_fee_balance at 2274), the
# forecast-based branch at 2734, the storage-fee carry at 2768/2815, the
# ledger boundary at 2857-2956 and the return tuple -- is the HEAD text.
#
# This file is never imported. The harness compiles it into a namespace
# copied from the *current* kernel module, so the market functions it calls
# (ahead_market_bidding, curtailment_market_bidding, balancing_market_bidding,
# ...) are the live ones; the loop around them is frozen HEAD.
# Do not edit. Regenerate only with
# scripts/capture_native_reproduction_golden.py write-head-copy (refuses to
# run unless the source equals the pinned 35aadb3 bytes).

# >>> VERBATIM A 35aadb3:2252-2364
def run_simulation(periods, generators, batterys, forecast_demands, real_demands, connections, electrolyzer):
    # plot average generation price
    avg_electricity_prices = []
    avg_gen_fees = []
    avg_balancing_fees = []
    avg_curtailment_fees = []
    avg_storage_fees = []
    # storage in each period
    curtailment_fees = []
    # balancing in each period
    balancing_fees = []
    # overall storage fee
    storage_fees = []
    # stored energy in each periods
    store_electricity = []
    # curtailment fee in each period
    generation_costs = []
    # single storage pool
    storage_pool = []
    # overall storage
    total_storage_pool = []
    # balancing fee, initialize as 0，undate only enter balancing(instead of curtail)
    total_storage_fee_balance = 0
    # storage composition
    storage_pools_composition = []
    storage_pool_composition = []
    # selected generators
    accepted_bids = []
    # used energy(discharge)
    usage_storage_pool_composition = []
    gen_fees = []
    # Preallocate as float32 to halve memory vs float64
    ahead_renewables = np.zeros(periods, dtype=np.float32)
    ahead_traditional = np.zeros(periods, dtype=np.float32)
    ahead_other = np.zeros(periods, dtype=np.float32)
    ahead_nuclear = np.zeros(periods, dtype=np.float32)
    balance_renewables = np.zeros(periods, dtype=np.float32)
    balance_traditional = np.zeros(periods, dtype=np.float32)
    balance_other = np.zeros(periods, dtype=np.float32)
    balance_nuclear = np.zeros(periods, dtype=np.float32)
    gen_list_composition  = []
    curtailed_electricity = []
    excess_electricity = []
    total_annual_cost = []
    total_annual_demand = []
    carbon_emission = []
    sold_fees = []
    purchase_fees = []
    total_green_hy = []
    total_renew_capacity = []
    renew_capacity = []
    traditional_gen = {'ccgt': 0, 'ocgt': 0, 'biomass': 0}
    total_annual_energycell = []
    total_income_dict = {}
    excess_energy_dict = {}
    excess_energy_final_dict = {}
    curtailed_energy_dict = {}
    renewable_hy_dict = {}
    flexible_demand_list = []
    interconnector_exports_list = []
    blackout_periods = []  # Track energy deficit (blackout) for each period
    # Full charge-tranche plot history is an optional diagnostic. The frontend
    # defaults generation tracing to off because the compact market ledger
    # already records per-period SOC without O(T^2) dictionary copies.
    retain_storage_tranche_history = os.getenv("SAVE_GENERATION_TRACE", "1") != "0"

    bidding_factor = config.simulation_parameters["bidding_factor"]
    trace_enabled = os.getenv("SAVE_MARKET_TRACE", "1") != "0"
    market_ledger = active_market_ledger()
    market_ledger_full = market_ledger.trace_level == "full"
    trace_scenario = os.getenv("DECARB_SCENARIO", "scenario")
    trace_year = os.getenv("SIMULATION_YEAR", "year")
    trace_run_id = os.getenv("MARKET_TRACE_RUN_ID")
    market_trace_file = None
    income_trace_file = None
    market_writer = None
    income_writer = None
    agent_names_for_trace = [
        getattr(asset, "name", asset.__class__.__name__)
        for asset in list(generators) + list(batterys) + [electrolyzer]
    ]
    if trace_enabled:
        from pathlib import Path as _Path
        trace_parts = ["market_trace_outputs"]
        if trace_run_id:
            trace_parts.extend([trace_run_id, trace_scenario])
        else:
            trace_parts.append(trace_scenario)
        trace_base = os.getenv("MARKET_TRACE_BASE_DIR", "").strip()
        if trace_base:
            trace_root = _Path(trace_base)
        else:
            trace_root = _Path(__file__).resolve().parent
        trace_dir = trace_root.joinpath(*trace_parts)
        trace_dir.mkdir(parents=True, exist_ok=True)
        market_trace_path = trace_dir / f"market_auction_results_{trace_year}.csv"
        income_trace_path = trace_dir / f"agent_period_income_{trace_year}.csv"
        market_trace_file = open(str(market_trace_path), "w", newline="", encoding="utf-8")
        income_trace_file = open(str(income_trace_path), "w", newline="", encoding="utf-8")
        market_writer = csv.DictWriter(market_trace_file, fieldnames=[
            "scenario", "year", "period", "market_stage", "asset_name",
            "accepted_energy_mwh", "accepted_price_gbp_per_mwh", "bid_cost_or_curtail_cost",
            "forecast_demand_mwh", "real_demand_mwh", "period_total_gen_cost_gbp",
            "storage_fee_gbp", "curtailment_fee_gbp", "balancing_fee_gbp",
            "sold_fee_gbp", "purchase_fee_gbp", "energy_deficit_mwh", "excess_energy_mwh",
        ])
        income_writer = csv.DictWriter(income_trace_file, fieldnames=[
            "scenario", "year", "period", "asset_name",
            "ahead_income_gbp", "balancing_income_gbp", "total_income_gbp",
        ])
        market_writer.writeheader()
        income_writer.writeheader()

# <<< VERBATIM A
    # >>> HARNESS REPLACEMENT B for 35aadb3:2365-2591 (weather netCDF and interconnector CSV loading)
    _p06_driver = __p06_synthetic_driver__
    # <<< HARNESS REPLACEMENT B

# >>> VERBATIM C 35aadb3:2592-2599
    for period in range(periods):
        # Memory cleanup every 100 periods to prevent MemoryError
        if period % 100 == 0:
            cleanup_accumulating_lists(total_renew_capacity, renew_capacity, gen_list_composition, 
                                 storage_pool_composition)
            # Periodic GC only; datasets already closed after limits computed
            pass
        
# <<< VERBATIM C
        # >>> HARNESS REPLACEMENT D for 35aadb3:2600-2690 (per-period VRE availability and interconnector assignment)
        _p06_driver.begin_period(period, generators, batterys, connections, electrolyzer)
        # <<< HARNESS REPLACEMENT D
# >>> VERBATIM E 35aadb3:2691-3125

        # chosen generation in wholesale，cost from stored energy and two storage pool variable for plotting
        # accepted_bids use for balancing, other three for plotting
        accepted_bids, total_storage_fee_ahead, per_storage_pool, merge_storage_pool, storage_pool_composition, \
        last_gen_energy, excess_energy, ahead_renewables, ahead_other, ahead_traditional, gen_list, ahead_nuclear,\
            gen_list_name, bids, income_dict,excess_energy_list,renewable_hy_list = ahead_market_bidding(
            generators, batterys,
            forecast_demands[period],
            period, accepted_bids, ahead_renewables, ahead_other, ahead_traditional, ahead_nuclear, bidding_factor,
            retain_storage_tranche_history=retain_storage_tranche_history)
        for key, value in income_dict.items():
            if key in total_income_dict:
                total_income_dict[key] += value
            else:
                total_income_dict[key] = value
        # print(accepted_bids)
        # compare forecast and read demand
        real_demand = real_demands[period]

        renewable_hy_dict[period] = renewable_hy_list
        income_dict_balance = {}
        energy_deficit = 0
        
        # Memory management: Clear lists periodically to prevent MemoryError
        if period % 100 == 0:  # Every 100 periods
            import gc
            gc.collect()
            # Clear accumulated lists to prevent memory bloat
            if len(total_renew_capacity) > 1000:
                total_renew_capacity.clear()
            if len(renew_capacity) > 1000:
                renew_capacity.clear()
        
        for item in generators:
            if type(item) == ExpensiverenewableGenerator:
                total_renew_capacity.append(item.capacity_limit)
        for item in generators:
            if item.name == 'onshore_Edinburgh':
                renew_capacity.append(item.capacity_limit)
        if excess_energy_list:
            excess_energy_dict[period] = excess_energy_list
        else:
            excess_energy_dict[period] = 0
        if real_demand < forecast_demands[period]:
            # return to curtailment fee and charged amount
            curtailed_fee, store_energy, real_list, storage_pool_composition_after, gen_list, curtailed_energy, \
            excess_energy, sold_fee, green_hy, energy_cell_period,curtailed_energy_list = \
                curtailment_market_bidding(period, real_demand, forecast_demands[period], accepted_bids,
                                           last_gen_energy, excess_energy, gen_list, connections, electrolyzer, batterys)
            #print(sold_fee)
            # curtailment fee is a list, add them upu
            total_fee = sum(curtailed_fee)
            curtailed_energy_dict[period] = curtailed_energy_list
            # add curtailment fee in this period to total
            curtailment_fees.append(total_fee)
            curtailed_electricity.append(curtailed_energy)
            excess_electricity.append(excess_energy)
            # no balancing fee, add 0
            balancing_fees.append(0)
            # add storage to overall storage
            store_electricity.append(store_energy)
            sold_fees.append(sum(sold_fee))
            purchase_fees.append(0)
            total_green_hy.append(green_hy)
            gen=[]
            for item in gen_list:
                if item[1] != 0:
                    gen.append(item[0])
            #print('gen', gen)
            #print('generators',generators)
            for item in generators:
                if item not in gen:
                    item.set_real_gen_energy(0)
            excess_energy_final_dict[period] = excess_energy
            blackout_periods.append(0)  # No blackout in curtailment market
        else:
            # ruturn to continue bidding
            balancing_fee, total_storage_fee_balance, real_list, store_energy, storage_pool_composition_after, \
            balance_renewables, balance_other, balance_traditional, gen_list, balance_nuclear, excess_energy, sold_fee, \
            bought_fee, green_hy, energy_cell_period, income_dict_balance, energy_deficit = balancing_market_bidding(generators, period, real_demand, forecast_demands[period],
                                                  accepted_bids, excess_energy, balance_renewables, balance_other,
                                                  balance_traditional, gen_list, balance_nuclear, connections,
                                                  gen_list_name, bids, electrolyzer,excess_energy_list, batterys, bidding_factor)
            blackout_periods.append(energy_deficit)  # Track energy deficit for this period
            for key, value in income_dict_balance.items():
                if key in total_income_dict:
                    total_income_dict[key] += value
                else:
                    total_income_dict[key] = value
            # add continue bidding in this period to total balancing fee list
            balancing_fees.append(sum(balancing_fee))
            curtailed_energy_dict[period] = 0
        #    print(sold_fee)
            # no curtailment, curtailment is 0
            curtailment_fees.append(0)
            curtailed_electricity.append(0)
            excess_electricity.append(excess_energy)
            # no storage, storage is 0
            store_electricity.append(store_energy)
            sold_fees.append(sum(sold_fee))
            purchase_fees.append(sum(bought_fee))
            total_green_hy.append(green_hy)
            gen = []
            for item in gen_list:
                if item[1] != 0:
                    gen.append(item[0])
            #print('gen',gen)
            #print('generators', generators)
            for item in generators:
                if item not in gen:
                    item.set_real_gen_energy(0)
            excess_energy_final_dict[period] = excess_energy
        filtered_list = [sublist for sublist in gen_list if sublist[1] != 0]
        result_dict = {}
        for item in filtered_list:
            key = item[0]
            value = item[1]
            if key in result_dict:
                result_dict[key] += value
            else:
                result_dict[key] = value
        result_list = [[key, value] for key, value in result_dict.items()]
        gen_list_composition.append(result_list)
        # add storage fee to overall storage fee
        storage_fees.append(total_storage_fee_ahead + total_storage_fee_balance)
        # oVeraall cost=storage cost+generation cost+curtailment cost +balancing cost
        gen_fees.append(sum([item1*item2 for _, item1, item2, _ in accepted_bids]))
        total_gen_cost = gen_fees[period]\
                         + storage_fees[period] + curtailment_fees[period] + balancing_fees[period]
        total_annual_cost.append(total_gen_cost)
        total_annual_demand.append(real_demand)
        if real_demand > 0:
            avg_gen_fees.append(gen_fees[period]/real_demand)
            avg_curtailment_fees.append(curtailment_fees[period]/real_demand)
            avg_balancing_fees.append(balancing_fees[period] / real_demand)
            avg_storage_fees.append(storage_fees[period] / real_demand)
            ahead_renewables[period] = ahead_renewables[period] / real_demand
            ahead_other[period] = ahead_other[period] / real_demand
            ahead_traditional[period] = ahead_traditional[period] / real_demand
            ahead_nuclear[period] = ahead_nuclear[period]/ real_demand
            balance_renewables[period] = balance_renewables[period] / real_demand
            balance_other[period] = balance_other[period] / real_demand
            balance_traditional[period] = balance_traditional[period] / real_demand
            balance_nuclear[period] = balance_nuclear[period] / real_demand
            avg_price = total_gen_cost / real_demand
        else: # Avoid division by zero
            avg_gen_fees.append(0)
            avg_curtailment_fees.append(0)
            avg_balancing_fees.append(0)
            avg_storage_fees.append(0)
            avg_price = 0

        total_annual_energycell.append(energy_cell_period)
        total_gen_cost = sum([item1*item2 for _, item1, item2, _ in accepted_bids])\
                         + storage_fees[period] + curtailment_fees[period] + balancing_fees[period]

        # Typed market evidence is appended in memory and flushed in batches by
        # one run-level writer. It observes final quantities after clearing and
        # cannot affect bid construction, sorting or acceptance.
        period_hours = float(os.getenv("PHYSICAL_PERIOD_HOURS", "0.5"))
        dispatch_by_asset = {}
        # `real_list` is a historical settlement intermediate. In balancing
        # periods it contains both the original accepted row and a combined
        # accepted+balancing row for the marginal asset, so summing it double
        # counts physical generation. `result_list` is the already-aggregated
        # final physical composition produced from `gen_list` above.
        for dispatch_asset, dispatch_energy in result_list:
            dispatch_by_asset[dispatch_asset] = (
                dispatch_by_asset.get(dispatch_asset, 0.0) + float(dispatch_energy)
            )
        accepted_supply_mwh = sum(dispatch_by_asset.values()) * period_hours
        real_demand_mwh = float(real_demand) * period_hours
        forecast_demand_mwh = float(forecast_demands[period]) * period_hours
        storage_charge_mwh = float(store_energy or 0.0) * period_hours
        storage_discharge_mwh = sum(
            energy for asset, energy in dispatch_by_asset.items()
            if isinstance(asset, Battery)
        ) * period_hours
        flexible_demand_mwh = float(getattr(electrolyzer, "real_energy", 0.0) or 0.0) * period_hours
        export_mwh = sum(float(getattr(connection, "sold_energy", 0.0) or 0.0) for connection in connections) * period_hours
        blackout_mwh = float(energy_deficit or 0.0) * period_hours
        excess_mwh = float(excess_energy or 0.0) * period_hours
        vre_accepted_mwh = sum(
            energy for asset, energy in dispatch_by_asset.items()
            if isinstance(asset, ExpensiverenewableGenerator)
        ) * period_hours
        import_mwh = sum(
            energy for asset, energy in dispatch_by_asset.items()
            if isinstance(asset, Connection)
        ) * period_hours
        curtailed_mwh = float(curtailed_electricity[period] or 0.0) * period_hours
        # `result_list` follows the retained market's two accounting branches.
        # In the curtailment branch it retains forecast generation diverted into
        # storage, while the balancing branch charges from VRE excess that is not
        # inserted into the final demand-serving composition. Count charge as a
        # final-dispatch load only in the former branch. The unclassified total
        # charge remains visible in `storage_charge_mwh` for storage auditing.
        # Only the forecast-minus-real-demand portion can remain inside
        # `result_list`. Additional charging from VRE availability above the
        # accepted forecast schedule is recorded by the storage agent but is not
        # part of this final-dispatch supply boundary.
        accounted_storage_charge_mwh = min(
            storage_charge_mwh,
            max(forecast_demand_mwh - real_demand_mwh, 0.0),
        )
        raw_balance_residual = (
            accepted_supply_mwh + blackout_mwh
            - real_demand_mwh - accounted_storage_charge_mwh
        )
        # The copied Scheme C settlement exposes some secondary allocations only
        # as annual/accounting variables, not asset dispatch rows. Preserve that
        # raw gap explicitly and close the public ledger with a named compatibility
        # adjustment; never silently relabel it as generation or blackout.
        compatibility_adjustment_mwh = (
            -raw_balance_residual if abs(raw_balance_residual) > 1e-9 else 0.0
        )
        balance_residual = raw_balance_residual + compatibility_adjustment_mwh
        allowed_trace_residual = max(
            1e-5,
            0.001 * max(abs(real_demand_mwh), abs(accepted_supply_mwh), 1.0),
        )
        # This verbose composition trace is intentionally opt-in. The public
        # SQLite ledger already preserves both the raw residual and the named
        # compatibility adjustment; serialising full asset compositions for
        # every exceptional period is useful for development, but needlessly
        # slows and inflates ordinary scientific runs.
        if (
            os.getenv("MARKET_BALANCE_DIAGNOSTIC", "0") == "1"
            and abs(raw_balance_residual) > allowed_trace_residual
        ):
            diagnostic_path = Path(os.getenv("OUTPUT_DIR", ".")) / "market" / "balance-diagnostic.jsonl"
            diagnostic_path.parent.mkdir(parents=True, exist_ok=True)
            def trace_composition(rows):
                return [
                    {
                        "asset": str(getattr(asset, "name", asset.__class__.__name__)),
                        "asset_type": asset.__class__.__name__,
                        "energy_mwh": float(energy) * period_hours,
                    }
                    for asset, energy in rows
                ]
            with diagnostic_path.open("a", encoding="utf-8") as diagnostic_handle:
                diagnostic_handle.write(json.dumps({
                    "year": int(trace_year),
                    "period": int(period),
                    "forecast_demand_mwh": forecast_demand_mwh,
                    "real_demand_mwh": real_demand_mwh,
                    "storage_charge_mwh": storage_charge_mwh,
                    "accounted_storage_charge_mwh": accounted_storage_charge_mwh,
                    "blackout_mwh": blackout_mwh,
                    "raw_residual_mwh": raw_balance_residual,
                    "compatibility_adjustment_mwh": compatibility_adjustment_mwh,
                    "historical_settlement_intermediate": trace_composition(real_list),
                    "aggregated_generation_composition": trace_composition(result_list),
                }, ensure_ascii=False) + "\n")
        market_ledger.record_period(PeriodLedgerRow(
            int(trace_year), period, "final_dispatch",
            forecast_demand_mwh, real_demand_mwh, accepted_supply_mwh,
            storage_charge_mwh, storage_discharge_mwh, flexible_demand_mwh,
            export_mwh, vre_accepted_mwh + curtailed_mwh, vre_accepted_mwh,
            curtailed_mwh, import_mwh, float(avg_price),
            float(total_gen_cost) * period_hours,
            float(avg_price) * accepted_supply_mwh,
            0.0, blackout_mwh, excess_mwh, balance_residual,
            compatibility_adjustment_mwh, raw_balance_residual,
        ))
        if market_ledger_full:
            order_rows = []
            offered_assets = set()
            for order_index, bid in enumerate(bids):
                asset, offer_price, offered_energy = bid[0], float(bid[1]), float(bid[2])
                offered_assets.add(asset)
                accepted_energy = float(dispatch_by_asset.get(asset, 0.0))
                if accepted_energy <= 1e-12:
                    status, reason = "rejected", "not_selected_after_merit_and_balance"
                elif accepted_energy + 1e-12 < offered_energy:
                    status, reason = "partially_accepted", "demand_filled"
                else:
                    status, reason = "accepted", "cleared"
                asset_name = str(getattr(asset, "name", asset.__class__.__name__))
                accepted_mwh = accepted_energy * period_hours
                order_rows.append(OrderLedgerRow(
                    f"{trace_year}:{period}:ahead:{order_index}", int(trace_year), period,
                    "ahead_offer", asset_name, asset.__class__.__name__, "supply",
                    offer_price, offered_energy * period_hours, accepted_mwh,
                    status, reason,
                    float(getattr(asset, "gen_cost", 0.0) or 0.0) * accepted_mwh,
                    float(avg_price) * accepted_mwh,
                ))
            for asset, accepted_energy in dispatch_by_asset.items():
                if asset in offered_assets or accepted_energy <= 1e-12:
                    continue
                asset_name = str(getattr(asset, "name", asset.__class__.__name__))
                accepted_mwh = accepted_energy * period_hours
                order_rows.append(OrderLedgerRow(
                    f"{trace_year}:{period}:supplemental:{len(order_rows)}",
                    int(trace_year), period, "final_dispatch", asset_name,
                    asset.__class__.__name__, "supply", 0.0, accepted_mwh,
                    accepted_mwh, "accepted", "accepted_non_generator_offer",
                    0.0, float(avg_price) * accepted_mwh,
                ))
            market_ledger.record_orders(order_rows)
        market_ledger.record_storage(
            StorageStateRow(
                int(trace_year), period,
                str(getattr(battery, "name", battery.__class__.__name__)),
                float(sum(getattr(battery, "stored_energy", {}).values())),
                0.0,
                float(dispatch_by_asset.get(battery, 0.0)) * period_hours,
                float(getattr(battery, "power_capacity_mw", getattr(battery, "pool_limit", 0.0)) or 0.0),
                float(getattr(battery, "energy_capacity_mwh", getattr(battery, "pool_limit", 0.0)) or 0.0),
            )
            for battery in batterys
        )

        if trace_enabled:
            for accepted_asset, accepted_price, accepted_energy, accepted_cost in accepted_bids:
                market_writer.writerow({
                    "scenario": trace_scenario,
                    "year": trace_year,
                    "period": period,
                    "market_stage": "ahead_accepted",
                    "asset_name": getattr(accepted_asset, "name", str(accepted_asset)),
                    "accepted_energy_mwh": accepted_energy,
                    "accepted_price_gbp_per_mwh": accepted_price,
                    "bid_cost_or_curtail_cost": accepted_cost,
                    "forecast_demand_mwh": forecast_demands[period],
                    "real_demand_mwh": real_demand,
                    "period_total_gen_cost_gbp": total_gen_cost,
                    "storage_fee_gbp": storage_fees[period],
                    "curtailment_fee_gbp": curtailment_fees[period],
                    "balancing_fee_gbp": balancing_fees[period],
                    "sold_fee_gbp": sold_fees[period],
                    "purchase_fee_gbp": purchase_fees[period],
                    "energy_deficit_mwh": energy_deficit,
                    "excess_energy_mwh": excess_energy,
                })
            for dispatch_asset, dispatch_energy in result_list:
                market_writer.writerow({
                    "scenario": trace_scenario,
                    "year": trace_year,
                    "period": period,
                    "market_stage": "real_dispatch",
                    "asset_name": getattr(dispatch_asset, "name", str(dispatch_asset)),
                    "accepted_energy_mwh": dispatch_energy,
                    "accepted_price_gbp_per_mwh": "",
                    "bid_cost_or_curtail_cost": "",
                    "forecast_demand_mwh": forecast_demands[period],
                    "real_demand_mwh": real_demand,
                    "period_total_gen_cost_gbp": total_gen_cost,
                    "storage_fee_gbp": storage_fees[period],
                    "curtailment_fee_gbp": curtailment_fees[period],
                    "balancing_fee_gbp": balancing_fees[period],
                    "sold_fee_gbp": sold_fees[period],
                    "purchase_fee_gbp": purchase_fees[period],
                    "energy_deficit_mwh": energy_deficit,
                    "excess_energy_mwh": excess_energy,
                })
            for agent_name in agent_names_for_trace:
                ahead_income = income_dict.get(agent_name, 0.0)
                balancing_income = income_dict_balance.get(agent_name, 0.0)
                income_writer.writerow({
                    "scenario": trace_scenario,
                    "year": trace_year,
                    "period": period,
                    "asset_name": agent_name,
                    "ahead_income_gbp": ahead_income,
                    "balancing_income_gbp": balancing_income,
                    "total_income_gbp": ahead_income + balancing_income,
                })
            if period % 100 == 0:
                market_trace_file.flush()
                income_trace_file.flush()

        #print(sum([item1*item2 for _, item1, item2, _ in accepted_bids]))
        #print(storage_fees[period])
        #print(curtailment_fees[period])
        #print(balancing_fees[period])
        # average=total/real demand

        #print(storage_pool_composition)
        #print(storage_pool_composition_after)
        #print('1')
        usage_storage = subtract_elements(storage_pool_composition, storage_pool_composition_after)
        # plotting
        generation_costs.append(total_gen_cost)
        if retain_storage_tranche_history:
            storage_pool.append(per_storage_pool)
            total_storage_pool.append(merge_storage_pool)
        avg_electricity_prices.append(avg_price)
        storage_pools_composition.append(storage_pool_composition)
        usage_storage_pool_composition.append(usage_storage)
        total_gen_ems = 0
        for item in gen_list:
            total_gen_ems += item[0].carbon_emission
        total_gen_ems += electrolyzer.body_emission
        total_gen_intensity = 0
        for item in gen_list:
            if hasattr(item[0], 'carbon_intensity'):
                total_gen_intensity += item[0].carbon_intensity * item[1]
        carbon_emission.append((total_gen_ems + total_gen_intensity))
        
        # Collect data for consumption plot
        flexible_demand_list.append(electrolyzer.real_energy)
        interconnector_export = sum(c.sold_energy for c in connections)
        interconnector_exports_list.append(interconnector_export)

        for item in generators:
            if item.name == 'CCGT':
                traditional_gen['ccgt'] += item.real_gen_energy
            elif item.name == 'OCGT':
                traditional_gen['ocgt'] += item.real_gen_energy
            elif item.name == 'bio_and_waste':
                traditional_gen['biomass'] += item.real_gen_energy
        if period == 248:
                if DEBUG_MARKET_STDOUT:
                    print(gen_list_name)

    # Final memory cleanup before returning results
    cleanup_accumulating_lists(total_renew_capacity, renew_capacity, gen_list_composition, 
                                 storage_pool_composition)
    if trace_enabled:
        market_trace_file.flush()
        income_trace_file.flush()
        market_trace_file.close()
        income_trace_file.close()
    
    return (avg_electricity_prices, storage_fees, store_electricity, generation_costs, storage_pool, total_storage_pool, \
           storage_pools_composition, usage_storage_pool_composition, avg_gen_fees, avg_curtailment_fees, \
           avg_balancing_fees, avg_storage_fees, ahead_renewables, ahead_other, ahead_traditional, ahead_nuclear, \
           balance_renewables, balance_other, balance_traditional, balance_nuclear, gen_list_composition, \
           curtailed_electricity, excess_electricity, total_annual_cost, total_annual_demand, carbon_emission, \
           sold_fees, purchase_fees, traditional_gen, total_green_hy,total_renew_capacity, renew_capacity,\
           total_annual_energycell, total_income_dict,excess_energy_dict,excess_energy_final_dict,
            curtailed_energy_dict,renewable_hy_dict, flexible_demand_list, interconnector_exports_list, blackout_periods)
# <<< VERBATIM E
